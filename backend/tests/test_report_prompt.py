# tests/test_report_prompt.py
# Regression: управляемый Report prompt (версии, production, rollback) + генерация
# отчёта поверх deterministic result (score/verdict НЕ меняются prompt'ом).

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.database as database
from app import report_prompt as rp


def _analysis_row_schema() -> str:
    return """
    CREATE TABLE analysis (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        product_id INTEGER,
        slug TEXT,
        score INTEGER,
        verdict TEXT,
        summary TEXT,
        report TEXT,
        safe_ingredients TEXT,
        caution_ingredients TEXT,
        active_ingredients TEXT,
        how_to_use TEXT,
        expectations TEXT,
        profile_snapshot TEXT,
        deterministic_json TEXT,
        score_engine_version TEXT,
        report_score_engine_version TEXT,
        report_prompt_version TEXT,
        created_at TEXT,
        expires_at TEXT,
        what_good TEXT,
        what_caution TEXT
    )
    """


class ReportPromptStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "aidermy.db")
        self.patch = patch.object(database, "AIDERMY_DB", self.db_path)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def test_production_prompt_seeded_as_v1(self):
        p = rp.get_production_report_prompt()
        self.assertEqual(p["version"], 1)
        self.assertTrue(p["is_production"])
        self.assertIn("{{product_name}}", p["user_prompt_template"])

    def test_create_new_version(self):
        rp.get_production_report_prompt()
        v2 = rp.create_report_prompt("v2", "sys2", "user2 {{product_name}}", "desc", "tester")
        self.assertEqual(v2["version"], 2)
        self.assertFalse(v2["is_production"])
        # старая версия не изменяется
        v1 = rp.get_report_prompt_by_version(1)
        self.assertEqual(v1["version"], 1)
        self.assertTrue(v1["is_production"])

    def test_publish_switches_production_without_deleting(self):
        rp.get_production_report_prompt()
        v2 = rp.create_report_prompt("v2", "s", "u {{product_name}}")
        prod = rp.publish_report_prompt(v2["id"])
        self.assertTrue(prod["is_production"])
        self.assertEqual(rp.get_production_report_prompt()["version"], 2)
        # v1 сохранена, но больше не production
        self.assertFalse(rp.get_report_prompt_by_version(1)["is_production"])
        self.assertEqual(len(rp.list_report_prompts()), 2)

    def test_rollback_to_previous_version(self):
        rp.get_production_report_prompt()
        v2 = rp.create_report_prompt("v2", "s", "u {{product_name}}")
        rp.publish_report_prompt(v2["id"])
        # откат на v1
        v1 = rp.get_report_prompt_by_version(1)
        rp.publish_report_prompt(v1["id"])
        self.assertEqual(rp.get_production_report_prompt()["version"], 1)

    def test_render_report_prompt(self):
        prompt = {"system_prompt": "SYS", "user_prompt_template": "Hi {{product_name}} / {{skin_type}}"}
        out = rp.render_report_prompt(prompt, {"product_name": "Крем", "skin_type": "Жирная"})
        self.assertEqual(out["system"], "SYS")
        self.assertEqual(out["user"], "Hi Крем / Жирная")


class ReportPromptPersistenceTests(unittest.TestCase):
    """report_prompt_version сохраняется независимо от score_engine_version."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "aidermy.db")
        self.patch = patch.object(database, "AIDERMY_DB", self.db_path)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_analysis_row_schema())
        conn.execute(
            "INSERT INTO analysis (id, user_id, product_id, slug, score, verdict, summary, "
            "score_engine_version) VALUES (1, 7, 10, 'x', 71, 'Подходит', 's', '1.2.0')"
        )
        conn.commit()
        conn.close()

    def test_save_analysis_details_stores_report_prompt_version(self):
        ok = database.save_analysis_details(
            7, 10, "x", report='[{"text":"t"}]', report_score_engine_version="1.2.0",
            report_prompt_version=3,
        )
        self.assertTrue(ok)
        saved = database.get_analysis_by_id(7, 1)
        self.assertEqual(saved["report_prompt_version"], "3")
        self.assertEqual(saved["score_engine_version"], "1.2.0")

    def test_report_prompt_version_defaults_to_none(self):
        database.save_analysis_details(7, 10, "x", report='[{"text":"t"}]')
        saved = database.get_analysis_by_id(7, 1)
        self.assertIsNone(saved["report_prompt_version"])


class ReportGenerationUsesPromptTests(unittest.IsolatedAsyncioTestCase):
    def _analysis(self):
        return {
            "score": 75,
            "verdict": "Подходит",
            "dimensions": {"hydration": 1.0, "barrier": 0.5, "irritation": -0.3,
                           "sensitization": 0.0, "sebum": 0.0, "pigmentation": 0.0},
            "priorities": {"hydration": 0.3, "barrier": 0.2, "irritation": 0.3,
                           "sensitization": 0.05, "sebum": 0.1, "pigmentation": 0.05},
            "positive_factors": [{"ingredient": "glycerin", "property": "hydration",
                                  "direction": "positive", "strength": 0.9,
                                  "confidence": 0.9, "position_weight": 1.0}],
            "negative_factors": [],
            "normalized_ingredients": ["water", "glycerin"],
            "goal_evidence": [],
        }

    async def test_generate_report_once_uses_prompt_and_returns_version(self):
        from app import services

        content = json.dumps({"explanation": "Формула подходит вашему профилю.",
                              "how_to_use": None, "expectations": None}, ensure_ascii=False)
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"choices": [{"message": {"content": content}}]}
        fake_client = AsyncMock()
        fake_client.post = AsyncMock(return_value=fake_resp)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)

        prompt = {"version": 7, "system_prompt": "SYS instructions",
                  "user_prompt_template": "USER {{product_name}} {{skin_type}}"}

        with patch.object(services, "DEEPSEEK_API_KEY", "test"), \
             patch.object(services.httpx, "AsyncClient", return_value=fake_client):
            result = await services.generate_report_once(
                "Крем", self._analysis(), {"skin_type": "Жирная"}, "", prompt=prompt,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["report_prompt_version"], 7)
        # сообщения реально содержат рендер prompt (system + user)
        sent = fake_client.post.call_args.kwargs["json"]["messages"]
        self.assertEqual(sent[0]["role"], "system")
        self.assertEqual(sent[0]["content"], "SYS instructions")
        self.assertEqual(sent[1]["role"], "user")
        self.assertIn("USER Крем Жирная", sent[1]["content"])

    async def test_generate_report_once_does_not_change_score(self):
        from app import services

        with patch.object(services, "DEEPSEEK_API_KEY", None):
            # без API key -> None; score/verdict вообще не трогаются
            result = await services.generate_report_once("Крем", self._analysis(), {})
        self.assertIsNone(result)


class ReportGenerationReliabilityTests(unittest.IsolatedAsyncioTestCase):
    """Report остаётся рабочим даже при полном отказе/браке LLM."""

    def _analysis(self):
        return {
            "score": 67,
            "verdict": "Хорошо подходит",
            "dimensions": {
                "hydration": 0.8,
                "barrier": 0.6,
                "irritation": -0.4,
                "sensitization": 0.0,
                "sebum": 0.0,
                "pigmentation": 0.0,
            },
            "priorities": {
                "hydration": 0.3,
                "barrier": 0.2,
                "irritation": 0.3,
                "sensitization": 0.05,
                "sebum": 0.1,
                "pigmentation": 0.05,
            },
            "positive_factors": [
                {
                    "ingredient": "glycerin",
                    "property": "hydration",
                    "direction": "positive",
                    "strength": 0.9,
                    "confidence": 0.9,
                    "position_weight": 1.0,
                }
            ],
            "negative_factors": [
                {
                    "ingredient": "fragrance",
                    "property": "irritation",
                    "direction": "negative",
                    "strength": 0.8,
                    "confidence": 0.9,
                    "position_weight": 1.0,
                }
            ],
            "normalized_ingredients": [
                "water",
                "glycerin",
                "fragrance",
            ],
            "goal_evidence": [
                {
                    "concern_id": "sensitive",
                    "label": "чувствительность",
                    "verdict": "may_hinder",
                    "evidence": [
                        {
                            "ingredient": "fragrance",
                            "property": "irritation",
                            "verdict": "may_hinder",
                            "evidence_level": "high",
                            "source_title": "Stored evidence",
                        }
                    ],
                }
            ],
        }

    async def test_broken_json_falls_back_to_deterministic_report(self):
        from app import services

        with patch.object(
            services,
            "generate_report_once",
            new=AsyncMock(return_value=None),
        ):
            result = await services.generate_full_report(
                "Крем",
                "water, glycerin, fragrance",
                {"skin_type": "Чувствительная", "concerns": ["sensitive"]},
                product_type="Крем",
                saved_analysis=self._analysis(),
            )

        self.assertEqual(result["score"], 67)
        self.assertEqual(result["verdict"], "Хорошо подходит")
        self.assertTrue(result["explanation"])

        text = result["explanation"].lower()

        # Fallback должен быть человеческим, а не технической заглушкой.
        self.assertNotIn("не удалось сформировать отчёт", text)
        self.assertNotIn("ошибка", text)
        self.assertNotIn("json", text)
        self.assertNotIn("score engine", text)

        # Должна сохраниться реальная персонализация.
        self.assertIn("отдушка", text)
        self.assertIn("чувствительност", text)

    async def test_llm_timeout_still_returns_deterministic_report(self):
        from app import services

        with patch.object(
            services,
            "generate_report_once",
            new=AsyncMock(side_effect=TimeoutError("LLM timeout")),
        ):
            # generate_full_report сейчас вызывает generate_report_once
            # только при наличии API key; fallback должен остаться доступным.
            with patch.object(services, "DEEPSEEK_API_KEY", "test"):
                try:
                    result = await services.generate_full_report(
                        "Крем",
                        "water, glycerin, fragrance",
                        {"skin_type": "Чувствительная", "concerns": ["sensitive"]},
                        product_type="Крем",
                        saved_analysis=self._analysis(),
                    )
                except TimeoutError:
                    self.fail("generate_full_report пробросил ошибку LLM вместо fallback")

        self.assertEqual(result["score"], 67)
        self.assertEqual(result["verdict"], "Хорошо подходит")
        self.assertTrue(result["explanation"])

    async def test_saved_verdict_is_not_recalculated_by_fallback(self):
        from app import services

        analysis = self._analysis()
        analysis["score"] = 67
        analysis["verdict"] = "Мой сохранённый verdict"

        with patch.object(
            services,
            "generate_report_once",
            new=AsyncMock(return_value=None),
        ):
            result = await services.generate_full_report(
                "Крем",
                "water, glycerin, fragrance",
                {"skin_type": "Чувствительная", "concerns": ["sensitive"]},
                product_type="Крем",
                saved_analysis=analysis,
            )

        self.assertEqual(result["score"], 67)
        self.assertEqual(result["verdict"], "Мой сохранённый verdict")
        self.assertIn("мой сохранённый verdict", result["explanation"].lower())

    async def test_llm_invalid_output_does_not_expose_placeholder(self):
        from app import services

        # Имитируем уже полностью отфильтрованный/непригодный ответ LLM.
        with patch.object(
            services,
            "generate_report_once",
            new=AsyncMock(return_value=None),
        ):
            result = await services.generate_full_report(
                "Крем",
                "water, glycerin, fragrance",
                {"skin_type": "Чувствительная", "concerns": ["sensitive"]},
                product_type="Крем",
                saved_analysis=self._analysis(),
            )

        self.assertIsInstance(result, dict)
        self.assertIsInstance(result["review"], list)
        self.assertGreaterEqual(len(result["review"]), 1)
        self.assertEqual(result["review"][0]["text"], result["explanation"])


    async def test_validator_allows_normal_human_effect_terms(self):
        from app import services

        inp = {
            "score": 67,
            "verdict": "Хорошо подходит",
            "positive": [
                {
                    "label": "Увлажнение",
                    "significance": "significant",
                    "contribution": 8.0,
                }
            ],
            "negative": [
                {
                    "label": "Раздражение",
                    "significance": "moderate",
                    "contribution": -3.0,
                }
            ],
        }

        output = {
            "summary": (
                "В составе есть компоненты для увлажнения и поддержки "
                "барьера, что работает в пользу ваших целей. "
                "При этом раздражение остаётся ограничивающим фактором."
            ),
            "expectations": None,
        }

        self.assertTrue(services._validate_report_once(inp, output))

    async def test_validator_rejects_medical_claim_but_not_axis_word(self):
        from app import services

        inp = {
            "score": 67,
            "verdict": "Хорошо подходит",
            "positive": [],
            "negative": [],
        }

        safe_output = {
            "summary": "Состав поддерживает увлажнение и барьер.",
            "expectations": None,
        }

        medical_output = {
            "summary": "Этот компонент укрепляет барьер и лечит проблему.",
            "expectations": None,
        }

        self.assertTrue(services._validate_report_once(inp, safe_output))
        self.assertFalse(services._validate_report_once(inp, medical_output))

    async def test_fallback_names_significant_ingredient(self):
        from app import services

        analysis = self._analysis()

        fallback = services._build_deterministic_report_fallback(analysis)

        self.assertIsInstance(fallback, str)
        self.assertTrue(fallback.strip())

        # В fallback должен попасть реальный значимый фактор,
        # а не абстрактное "есть положительные факторы".
        self.assertIn("глицерин", fallback.lower())
        self.assertIn("отдушка", fallback.lower())

    async def test_fallback_preserves_saved_verdict(self):
        from app import services

        analysis = self._analysis()
        analysis["score"] = 67
        analysis["verdict"] = "МОЙ СОХРАНЁННЫЙ VERDICT"

        fallback = services._build_deterministic_report_fallback(analysis)

        self.assertIn("МОЙ СОХРАНЁННЫЙ VERDICT", fallback)
        self.assertNotIn("Хорошо подходит", fallback)

    async def test_fallback_does_not_invent_goal_evidence(self):
        from app import services

        analysis = self._analysis()
        analysis["goal_evidence"] = []

        fallback = services._build_deterministic_report_fallback(analysis)

        # Без goal_evidence нельзя превращать фактор в доказанную
        # связь с конкретной пользовательской проблемой.
        self.assertNotIn("вашей чувствительности", fallback.lower())
        self.assertNotIn("ваших высыпаниях", fallback.lower())

    async def test_generate_report_once_accepts_json_code_fence(self):
        from app import services

        content = """```json
{
  "summary": "В составе есть глицерин для поддержки увлажнения.",
  "expectations": null
}
```"""

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }

        fake_client = AsyncMock()
        fake_client.post = AsyncMock(return_value=fake_resp)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)

        prompt = {
            "version": 8,
            "system_prompt": "SYS",
            "user_prompt_template": "USER {{product_name}}",
        }

        with patch.object(services, "DEEPSEEK_API_KEY", "test"), \
             patch.object(
                 services.httpx,
                 "AsyncClient",
                 return_value=fake_client,
             ):
            result = await services.generate_report_once(
                "Крем",
                self._analysis(),
                {"skin_type": "Жирная"},
                "",
                prompt=prompt,
            )

        self.assertIsNotNone(result)
        self.assertIn("глицерин", result["summary"].lower())

    async def test_generate_report_once_accepts_json_with_surrounding_text(self):
        from app import services

        content = """
        Вот готовый отчёт:

        {
          "summary": "В составе есть глицерин для поддержки увлажнения.",
          "expectations": null
        }

        """

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }

        fake_client = AsyncMock()
        fake_client.post = AsyncMock(return_value=fake_resp)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)

        prompt = {
            "version": 9,
            "system_prompt": "SYS",
            "user_prompt_template": "USER {{product_name}}",
        }

        with patch.object(services, "DEEPSEEK_API_KEY", "test"), \
             patch.object(
                 services.httpx,
                 "AsyncClient",
                 return_value=fake_client,
             ):
            result = await services.generate_report_once(
                "Крем",
                self._analysis(),
                {"skin_type": "Жирная"},
                "",
                prompt=prompt,
            )

        self.assertIsNotNone(result)
        self.assertIn("глицерин", result["summary"].lower())

    async def test_generate_full_report_falls_back_when_llm_is_unusable(self):
        from app import services

        analysis = self._analysis()

        with patch.object(services, "DEEPSEEK_API_KEY", "test"), \
             patch.object(
                 services,
                 "generate_report_once",
                 new=AsyncMock(return_value=None),
             ):
            result = await services.generate_full_report(
                product_name="Тестовый крем",
                ingredients="water, glycerin, fragrance",
                profile={"skin_type": "Чувствительная"},
                saved_analysis={
                    "score": 67,
                    "verdict": "Хорошо подходит",
                    "deterministic": analysis,
                },
            )

        self.assertEqual(result["score"], 67)
        self.assertEqual(result["verdict"], "Хорошо подходит")
        self.assertTrue(result["explanation"].strip())
        self.assertIn("глицерин", result["explanation"].lower())
        self.assertIn("отдушка", result["explanation"].lower())
        self.assertNotEqual(
            result["explanation"],
            "Не удалось сформировать отчёт.",
        )


class ReportPromptRoutesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "aidermy.db")
        self.products_path = os.path.join(self.temp_dir.name, "products.db")
        self.db_patch = patch.object(database, "AIDERMY_DB", self.db_path)
        self.products_patch = patch.object(database, "PRODUCTS_DB", self.products_path)
        self.db_patch.start()
        self.products_patch.start()
        self.addCleanup(self.products_patch.stop)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(_analysis_row_schema())
        conn.commit()
        conn.close()

        from app.report_prompt_routes import setup_report_prompt_routes
        app = FastAPI()
        setup_report_prompt_routes(app)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_report_page_requires_auth(self):
        self.assertEqual(self.client.get("/admin/report").status_code, 401)

    def test_prompts_list_requires_auth(self):
        self.assertEqual(self.client.get("/admin/report/api/prompts").status_code, 401)

    def test_prompts_list_with_auth(self):
        r = self.client.get("/admin/report/api/prompts", auth=("admin", "aidermy2026"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["production"]["version"], 1)

    def test_create_and_publish(self):
        r = self.client.post("/admin/report/api/prompts", json={
            "name": "v2", "system_prompt": "s", "user_prompt_template": "u {{product_name}}",
        }, auth=("admin", "aidermy2026"))
        self.assertEqual(r.status_code, 200)
        v2 = r.json()
        self.assertEqual(v2["version"], 2)
        r2 = self.client.post(f"/admin/report/api/prompts/{v2['id']}/publish", auth=("admin", "aidermy2026"))
        self.assertEqual(r2.status_code, 200)
        data = self.client.get("/admin/report/api/prompts", auth=("admin", "aidermy2026")).json()
        self.assertEqual(data["production"]["version"], 2)

    def test_test_generation_does_not_save(self):
        from app import report_prompt_routes as rpr
        from app import services

        det = {"score": 71, "verdict": "Подходит", "dimensions": {}, "priorities": {},
               "positive_factors": [], "negative_factors": [], "normalized_ingredients": ["aqua"],
               "goal_evidence": [], "score_engine_version": "1.2.0"}
        profile = {"skin_type": "Жирная"}
        product = {"id": 1, "slug": "x", "name": "X"}
        with patch.object(rpr, "_compute_deterministic", return_value=(det, profile, product, "X", "")), \
             patch.object(services, "generate_report_once", new=AsyncMock(return_value=None)):
            r = self.client.post("/admin/report/api/test",
                                 json={"user_id": 7, "slug": "x"},
                                 auth=("admin", "aidermy2026"))
        self.assertEqual(r.status_code, 200)
        conn = sqlite3.connect(self.db_path)
        n = conn.execute("SELECT COUNT(*) FROM analysis").fetchone()[0]
        conn.close()
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
