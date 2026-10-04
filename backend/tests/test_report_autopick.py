"""Regression: autopick flow — report должен получать INCI даже когда analysis
сохранён без deterministic_json (только score/verdict).

Раньше recommend_products сохранял analysis без deterministic_json, поэтому report
возвращал пустой INCI ("Состав не распознан"), хотя score был рассчитан по составу.
Теперь: (1) recommend сохраняет deterministic_json; (2) generate_full_report
пересчитывает состав из ingredients, если у saved_analysis нет deterministic data.
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class AutopickReportTests(unittest.TestCase):
    def test_report_reanalyzes_when_analysis_has_no_deterministic(self):
        from app import services
        saved = {"score": 68, "verdict": "Подходит", "summary": "..."}
        ingredients = "Water, Glycerin, Niacinamide, Fragrance"
        profile = {"skin_type": "Жирная", "concerns": [], "allergies": [], "custom_text": ""}
        with patch.object(services, "DEEPSEEK_API_KEY", None):
            result = asyncio.run(services.generate_full_report(
                "Test product", ingredients, profile, "Жирная", "Очищение",
                saved_analysis=saved,
            ))
        self.assertTrue(result.get("inci"))
        inci_lower = [str(x).lower() for x in result.get("inci") or []]
        self.assertTrue(any("glycerin" in x for x in inci_lower))

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
