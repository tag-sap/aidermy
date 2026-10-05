"""Regression: report не должен содержать внутренние термины Score Engine."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import _validate_report_once, _deterministic_balance_fragments


class ReportHumanTermsTests(unittest.TestCase):
    def _inp(self):
        return {
            "score": 55,
            "verdict": "Требует внимания",
            "positive": [{"axis": "hydration", "label": "увлажнение", "significance": "significant"}],
            "negative": [],
            "weak": [],
        }

    def test_rejects_contribution_term(self):
        output = {
            "explanation": "Фактор увлажнения даёт положительный вклад.",
            "how_to_use": None,
            "expectations": None,
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_rejects_neutral_zone_term(self):
        output = {
            "explanation": "Балл находится ниже нейтральной зоны.",
            "how_to_use": None,
            "expectations": None,
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_accepts_human_text(self):
        output = {
            "explanation": "Состав поддерживает увлажнение.",
            "how_to_use": None,
            "expectations": None,
        }
        self.assertTrue(_validate_report_once(self._inp(), output))

    def test_deterministic_fragments_are_human(self):
        analysis = {
            "score": 31,
            "verdict": "Не рекомендуется",
            "dimensions": {"hydration": 3.0, "irritation": -2.0},
            "priorities": {"hydration": 0.4, "barrier": 0.2, "irritation": 0.4, "sensitization": 0.0, "sebum": 0.0, "pigmentation": 0.0},
        }
        good, bad = _deterministic_balance_fragments(analysis)
        for f in good + bad:
            low = f["text"].lower()
            self.assertNotIn("вклад", low)
            self.assertNotIn("нейтральн", low)
            self.assertNotIn("балл", low)


if __name__ == "__main__":
    unittest.main()
