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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import upsert_analysis
from app.auth import create_access_token
from app.main import app
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

    def test_report_reopen_preserves_score_and_report(self):
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

        # Инвариант: score/verdict/report совпадают при повторном открытии.
        self.assertEqual(rep1.get("score"), 64)
        self.assertEqual(rep1.get("score"), rep2.get("score"))
        self.assertEqual(rep1.get("review"), rep2.get("review"))


if __name__ == "__main__":
    unittest.main()
