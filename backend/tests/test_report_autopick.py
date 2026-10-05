"""The report explains saved Match data and never reruns the product analysis."""
import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class AutopickReportTests(unittest.TestCase):
    def test_report_does_not_reanalyze_when_deterministic_payload_is_missing(self):
        from app import services
        saved = {"score": 68, "verdict": "Подходит", "summary": "..."}
        ingredients = "Water, Glycerin, Niacinamide, Fragrance"
        profile = {"skin_type": "Жирная", "concerns": [], "allergies": [], "custom_text": ""}
        with patch.object(services, "DEEPSEEK_API_KEY", None):
            with patch("app.decision_engine.DecisionEngine.analyze") as analyze:
                result = asyncio.run(services.generate_full_report(
                    "Test product", ingredients, profile, "Жирная", "Очищение",
                    saved_analysis=saved,
                ))
        self.assertEqual(result["score"], 68)
        self.assertEqual(result["verdict"], "Подходит")
        self.assertEqual(result["explanation"], "...")
        analyze.assert_not_called()

    def test_balance_text_uses_saved_deterministic_when_present(self):
        from app.services import _score_balance_text
        det = {
            "dimensions": {"hydration": 2.0, "barrier": 1.0, "irritation": 0.5, "sensitization": -0.1, "sebum": 0.0, "pigmentation": 0.1},
            "priorities": {"hydration": 0.31, "barrier": 0.15, "irritation": 0.31, "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04},
        }
        text = _score_balance_text(det)
        self.assertIn("значимо", text)
        self.assertIn("слабо", text)


if __name__ == "__main__":
    unittest.main()
