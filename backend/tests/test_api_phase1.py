import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class CheckProductIngredientsPhase1Tests(unittest.IsolatedAsyncioTestCase):
    """API-путь /api/check не теряет статус Phase 1 и не превращает None в 0."""

    def _deterministic(self, score, phase1_status):
        return {
            "score": score,
            "phase1": {
                "status": phase1_status,
                "violations": [{"axis": "irritation", "load": 1.0, "threshold": 0.7, "violated": True}] if phase1_status == "blocked" else [],
                "branches": {},
                "version": "1.0.0",
            },
            "phase1_status": phase1_status,
            "phase1_version": "1.0.0",
            "recommendation_status": "Не рекомендовано" if phase1_status == "blocked" else "Рекомендовано",
            "negative_only_score": 18 if phase1_status == "blocked" else None,
            "verdict": "Не рекомендовано" if phase1_status == "blocked" else "Подходит",
            "summary": "s",
            "safe_ingredients": [],
            "caution_ingredients": ["fragrance"],
            "goal_evidence": [],
            "normalized_ingredients": ["fragrance"],
        }

    async def _run(self, deterministic):
        engine = MagicMock()
        engine.analysis_service.prepare_product_ingredients.return_value = ["fragrance"]
        engine.analysis_service.repository = MagicMock()
        engine.analyze.return_value = deterministic
        with patch("app.decision_engine.DecisionEngine", return_value=engine), \
             patch("app.services.DEEPSEEK_API_KEY", None), \
             patch("app.product_model.get_internal_interactions", return_value=None):
            from app.services import check_product_with_ingredients
            return await check_product_with_ingredients("Test", "Нормальная", {}, "Fragrance")

    async def test_blocked_preserves_none_score_and_status(self):
        result = await self._run(self._deterministic(None, "blocked"))
        self.assertIsNone(result["score"])
        self.assertEqual(result["phase1_status"], "blocked")
        self.assertEqual(result["recommendation_status"], "Не рекомендовано")
        self.assertEqual(result["negative_only_score"], 18)
        self.assertEqual(result["phase1_violations"][0]["axis"], "irritation")

    async def test_insufficient_data_preserves_none_score(self):
        result = await self._run(self._deterministic(None, "insufficient_data"))
        self.assertIsNone(result["score"])
        self.assertEqual(result["phase1_status"], "insufficient_data")

    async def test_passed_returns_score(self):
        result = await self._run(self._deterministic(64, "passed"))
        self.assertEqual(result["score"], 64)
        self.assertEqual(result["phase1_status"], "passed")


if __name__ == "__main__":
    unittest.main()
