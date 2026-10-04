"""Regression: score < 50 с одновременно positive и negative deterministic factors."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import _validate_report_once, _deterministic_balance_fragments


class ReportNegativeSideTests(unittest.TestCase):
    def _inp(self):
        return {
            "score": 37,
            "verdict": "Не рекомендуется",
            "positive": [{"axis": "hydration", "label": "увлажнение", "significance": "significant"}],
            "negative": [{"axis": "irritation", "label": "раздражение", "significance": "significant"}],
            "weak": [],
        }

    def test_accepts_balanced_output(self):
        output = {
            "summary": [{"text": "Итог 37% ниже нейтральной зоны.", "sentiment": "negative"}],
            "positive": [{"text": "Увлажнение даёт значимый положительный вклад.", "sentiment": "positive"}],
            "negative": [{"text": "Раздражение даёт значимый отрицательный вклад.", "sentiment": "negative"}],
            "expectations": "Отрицательные вклады перевешивают положительные.",
        }
        self.assertTrue(_validate_report_once(self._inp(), output))

    def test_rejects_when_negative_side_omitted(self):
        output = {
            "summary": [{"text": "Итог 37% ниже нейтральной зоны.", "sentiment": "negative"}],
            "positive": [{"text": "Увлажнение даёт значимый положительный вклад.", "sentiment": "positive"}],
            "negative": [],
            "expectations": "",
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_rejects_no_negative_factors_phrase(self):
        output = {
            "summary": [{"text": "Итог 37%.", "sentiment": "negative"}],
            "positive": [{"text": "Увлажнение.", "sentiment": "positive"}],
            "negative": [{"text": "Существенных отрицательных факторов нет.", "sentiment": "negative"}],
            "expectations": "",
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_rejects_advice_in_expectations(self):
        output = {
            "summary": [{"text": "Итог 37%.", "sentiment": "negative"}],
            "positive": [{"text": "Увлажнение.", "sentiment": "positive"}],
            "negative": [{"text": "Раздражение.", "sentiment": "negative"}],
            "expectations": "Лучше не включать в routine без проверки.",
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_balance_fragments_reflects_both_sides(self):
        analysis = {
            "score": 37,
            "verdict": "Не рекомендуется",
            "dimensions": {"hydration": 3.0, "irritation": -2.0, "sensitization": -0.1},
            "priorities": {"hydration": 0.31, "barrier": 0.15, "irritation": 0.31, "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04},
        }
        good, bad = _deterministic_balance_fragments(analysis)
        self.assertTrue(any("положительный" in f["text"] for f in good))
        self.assertTrue(any("отрицательный" in f["text"] for f in bad))


if __name__ == "__main__":
    unittest.main()
