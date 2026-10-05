# tests/test_report_flow.py
# Фаза 19 — Product Card vs Report: один analysis_id = один источник истины.
#
# Инварианты:
#   1) /api/shelf/analyze (entry point карточки товара) возвращает analysis_id,
#      чтобы карточка могла открыть отчёт по ТОМУ ЖЕ сохранённому анализу;
#   2) повторное открытие отчёта (/api/analysis/report по одному analysis_id)
#      даёт один и тот же score/verdict/report (не пересчитывает Score Engine).
import json
import os
import sys
import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.score_version import SCORE_ENGINE_VERSION
from app.database import upsert_analysis
from app.auth import create_access_token
from app.main import ShelfAnalyzeRequest, _save_system_analysis, app, review_shelf_product
from fastapi.testclient import TestClient

USER_ID = 1
SLUG = "the-ordinary-aha-30-bha-2-peeling-solution-7"
PRODUCT_ID = 3766


class ReportFlowTests(unittest.TestCase):
    def _seed_analysis(self):
        """Создаёт актуальный User Analysis (score/verdict + deterministic)."""
        deterministic = {
            "score": 64,
            "verdict": "Требует внимания",
            "normalized_ingredients": ["aqua", "niacinamide", "panthenol", "glycolic acid"],
            "positive_factors": [
                {"ingredient": "panthenol", "property": "barrier_support", "strength": 0.4, "confidence": 0.8, "position_weight": 0.5}
            ],
            "negative_factors": [
                {"ingredient": "glycolic acid", "property": "irritation", "strength": 0.5, "confidence": 0.9, "position_weight": 0.7}
            ],
        }
        saved = upsert_analysis(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            slug=SLUG,
            score=64,
            verdict="Требует внимания",
            summary="резюме проверки",
            deterministic_json=json.dumps(deterministic, ensure_ascii=False),
        )
        self.assertTrue(saved.get("id"))
        return saved

    def test_shelf_analyze_returns_analysis_id(self):
        """Карточка товара должна получать analysis_id, чтобы открыть отчёт по нему."""
        self._seed_analysis()
        token = create_access_token({"sub": str(USER_ID)})
        client = TestClient(app)
        r = client.post(
            "/api/shelf/analyze",
            json={"slug": SLUG},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 200, f"unexpected {r.status_code}: {r.text}")
        body = r.json()
        analysis = body.get("analysis")
        self.assertIsNotNone(analysis, "analysis payload expected")
        self.assertIsNotNone(analysis.get("id"), "analysis payload must carry analysis_id")

    @patch("app.main._save_system_analysis", return_value={"id": 123})
    @patch("app.services.check_product_with_ai", new_callable=AsyncMock, return_value={
        "score": 0,
        "verdict": "Не рекомендуется",
        "summary": "Нейтральное резюме.",
        "ingredients": "Aqua, Fragrance",
        "deterministic": {"normalized_ingredients": ["aqua", "fragrance"]},
    })
    @patch("app.main._profile_from_user", return_value={})
    @patch("app.shelf_service.score_product", return_value=(None, None))
    @patch("app.database.get_product_by_slug", return_value={
        "id": PRODUCT_ID,
        "slug": SLUG,
        "name": "Тестовый продукт",
        "ingredients": "Aqua, Fragrance",
    })
    @patch("app.database.get_connection")
    def test_shelf_analyze_accepts_zero_score(
        self, get_connection, _product, _score, _profile, _check, _save_analysis
    ):
        from app.auth import get_current_user

        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = None
        get_connection.return_value = connection
        client = TestClient(app)
        previous_override = app.dependency_overrides.get(get_current_user)
        app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID}

        try:
            response = client.post("/api/shelf/analyze", json={"slug": SLUG})
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_current_user, None)
            else:
                app.dependency_overrides[get_current_user] = previous_override

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["score"], 0)
        self.assertEqual(response.json()["analysis"]["id"], 123)

    @patch("app.services.check_product_with_ai", new_callable=AsyncMock, return_value={
        "score": 0,
        "verdict": "Не рекомендуется",
        "summary": "Нейтральное резюме.",
        "ingredients": "Aqua, Fragrance",
    })
    @patch("app.shelf_service.score_product", return_value=(None, None))
    @patch("app.database.get_connection")
    def test_ensure_product_checked_accepts_zero_score(self, get_connection, _score, _check):
        from app.main import _ensure_product_checked

        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = None
        get_connection.return_value = connection
        score, analysis = asyncio.run(
            _ensure_product_checked(
                {"id": USER_ID},
                {"id": PRODUCT_ID, "slug": SLUG, "name": "Тестовый продукт", "ingredients": "Aqua, Fragrance"},
            )
        )

        self.assertEqual(score, 0)
        self.assertEqual(analysis["score"], 0)

    def test_product_detail_reopen_preserves_analysis_id(self):
        """Повторное открытие карточки обязано вернуть сохранённый analysis.id —
        это условие показа кнопки «Посмотреть отчёт» (источник данных карточки —
        get_personalized_analysis, который использует GET /api/products/{slug})."""
        from app.database import get_product_by_slug
        from app.shelf_service import get_personalized_analysis

        saved = self._seed_analysis()
        product = get_product_by_slug(SLUG)
        self.assertIsNotNone(product, "test product must exist in products.db")

        score, analysis = get_personalized_analysis({"id": USER_ID}, product)
        self.assertIsNotNone(analysis, "analysis payload expected on reopen")
        self.assertEqual(
            analysis.get("id"),
            saved["id"],
            "reopened product card must expose the saved analysis_id",
        )
        self.assertEqual(score, 64)
        self.assertEqual(analysis.get("verdict"), "Требует внимания")

    @patch(
        "app.services.generate_full_report",
        new_callable=AsyncMock,
        return_value={
            "score": 64,
            "verdict": "Требует внимания",
            "explanation": "Подробный отчёт.",
            "review": [{"text": "Подробный отчёт.", "sentiment": "positive"}],
            "how_to_use": None,
            "expectations": None,
        },
    )
    @patch("app.main._profile_from_user", return_value={})
    def test_report_reopen_preserves_score_and_report(self, _profile, generate):
        """Повторное открытие отчёта по тому же analysis_id даёт тот же результат."""
        saved = self._seed_analysis()
        analysis_id = saved["id"]
        token = create_access_token({"sub": str(USER_ID)})
        client = TestClient(app)

        r1 = client.post(
            "/api/analysis/report",
            json={"slug": SLUG, "analysis_id": analysis_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r1.status_code, 200, f"unexpected {r1.status_code}: {r1.text}")
        rep1 = r1.json()

        r2 = client.post(
            "/api/analysis/report",
            json={"slug": SLUG, "analysis_id": analysis_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r2.status_code, 200, f"unexpected {r2.status_code}: {r2.text}")
        rep2 = r2.json()
        generate.assert_awaited_once()

        # Инвариант: score/verdict/report совпадают при повторном открытии.
        self.assertEqual(rep1.get("score"), 64)
        self.assertEqual(rep1.get("verdict"), "Требует внимания")
        self.assertEqual(rep1.get("explanation"), "Подробный отчёт.")
        self.assertTrue(rep1.get("report_ready"))
        self.assertNotIn("what_good", rep1)
        self.assertNotIn("what_bad", rep1)
        self.assertEqual(rep1.get("score"), rep2.get("score"))
        self.assertEqual(rep1.get("review"), rep2.get("review"))

    def test_scan_match_can_generate_report_before_catalog_approval(self):
        analysis = {
            "id": 987,
            "product_id": None,
            "slug": "unapproved-scanned-product",
            "score": 0,
            "verdict": "Не рекомендуется",
            "summary": "Нейтральное резюме.",
            "report": None,
            "score_engine_version": SCORE_ENGINE_VERSION,
            "report_score_engine_version": None,
            "deterministic": {
                "product_name": "Сканированный продукт",
                "normalized_ingredients": ["aqua", "glycerin"],
            },
        }
        full_report = {
            "score": 0,
            "verdict": "Не рекомендуется",
            "explanation": "Отчёт по сохранённому результату.",
            "review": [{"text": "Отчёт по сохранённому результату.", "sentiment": "positive"}],
            "how_to_use": None,
            "expectations": None,
        }
        with patch("app.database.get_analysis_by_id", return_value=analysis), \
             patch("app.database.get_product_by_slug", return_value=None), \
             patch("app.main._profile_from_user", return_value={}), \
             patch("app.services.generate_full_report", new_callable=AsyncMock, return_value=full_report) as generate, \
             patch("app.database.save_analysis_details", return_value=True), \
             patch("app.database.save_ai_report", return_value=True):
            response = asyncio.run(
                review_shelf_product(
                    ShelfAnalyzeRequest(slug=analysis["slug"], analysis_id=analysis["id"]),
                    {"id": USER_ID},
                )
            )

        self.assertEqual(response["score"], 0)
        self.assertEqual(response["verdict"], "Не рекомендуется")
        self.assertTrue(response["report_ready"])
        self.assertNotIn("what_good", response)
        self.assertEqual(response["review"], full_report["review"])
        self.assertEqual(generate.await_args.args[:2], ("Сканированный продукт", "aqua, glycerin"))
        self.assertIs(generate.await_args.kwargs["saved_analysis"], analysis)

    def test_cached_report_does_not_regenerate_optional_sections(self):
        analysis = {
            "id": 988,
            "product_id": None,
            "slug": "unapproved-scanned-product",
            "score": 0,
            "summary": "Нейтральное резюме.",
            "report": '[{"text":"Сохранённый отчёт","sentiment":"positive"}]',
            "score_engine_version": SCORE_ENGINE_VERSION,
            "report_score_engine_version": SCORE_ENGINE_VERSION,
            "deterministic": {"normalized_ingredients": ["aqua"]},
            "active_ingredients": None,
            "what_good": None,
            "what_caution": None,
            "how_to_use": None,
            "expectations": None,
        }
        with patch("app.database.get_analysis_by_id", return_value=analysis), \
             patch("app.database.get_product_by_slug", return_value=None), \
             patch("app.services.generate_full_report", new_callable=AsyncMock) as generate:
            response = asyncio.run(
                review_shelf_product(
                    ShelfAnalyzeRequest(slug=analysis["slug"], analysis_id=analysis["id"]),
                    {"id": USER_ID},
                )
            )

        self.assertEqual(response["review"], [{"text": "Сохранённый отчёт", "sentiment": "positive"}])
        generate.assert_not_awaited()

    def test_stale_report_is_regenerated_after_score_engine_version_change(self):
        analysis = {
            "id": 989,
            "product_id": None,
            "slug": "unapproved-scanned-product",
            "score": 62,
            "summary": "Текущий результат.",
            "report": '[{"text":"Устаревший отчёт","sentiment":"positive"}]',
            "score_engine_version": SCORE_ENGINE_VERSION,
            "report_score_engine_version": "0.9.0",
            "deterministic": {"normalized_ingredients": ["aqua"]},
        }
        full_report = {
            "score": 62,
            "verdict": "Требует внимания",
            "explanation": "Новый отчёт.",
            "review": [{"text": "Новый отчёт.", "sentiment": "positive"}],
            "how_to_use": None,
            "expectations": None,
        }
        with patch("app.database.get_analysis_by_id", return_value=analysis), \
             patch("app.database.get_product_by_slug", return_value=None), \
             patch("app.main._profile_from_user", return_value={}), \
             patch("app.services.generate_full_report", new_callable=AsyncMock, return_value=full_report) as generate, \
             patch("app.database.save_analysis_details", return_value=True) as save_details, \
             patch("app.database.save_ai_report", return_value=True):
            response = asyncio.run(
                review_shelf_product(
                    ShelfAnalyzeRequest(slug=analysis["slug"], analysis_id=analysis["id"]),
                    {"id": USER_ID},
                )
            )

        generate.assert_awaited_once()
        self.assertEqual(response["review"], full_report["review"])
        self.assertEqual(
            save_details.call_args.kwargs["report_score_engine_version"],
            SCORE_ENGINE_VERSION,
        )

    def test_zero_score_is_saved_as_a_match(self):
        result = {
            "score": 0,
            "verdict": "Не рекомендуется",
            "summary": "Формула не подходит.",
            "deterministic": {"normalized_ingredients": ["ingredient"]},
        }
        with patch("app.database.upsert_analysis", return_value={"id": 123}) as upsert:
            saved = _save_system_analysis({"id": USER_ID}, None, "zero-score-product", result)
        self.assertEqual(saved["id"], 123)
        self.assertEqual(upsert.call_args.kwargs["score"], 0)


if __name__ == "__main__":
    unittest.main()
