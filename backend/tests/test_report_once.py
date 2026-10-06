"""Regression: единый report input -> один LLM-вызов -> валидация на противоречия.

Кейс ARAVIA Hyaluron Filler Hydrating Cream (25%): значимый отрицательный вклад
не должен в отчёте описываться как «существенных минусов ... не выявлено».
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import _build_report_input, _validate_report_once


class ReportOnceValidationTests(unittest.TestCase):
    def _inp(self):
        return {
            "score": 25,
            "verdict": "Не рекомендуется",
            "positive_factors": [],
            "negative_factors": [],
            "positive": [{"axis": "hydration", "label": "увлажнение", "significance": "significant"}],
            "negative": [{"axis": "sensitization", "label": "сенсибилизация", "significance": "significant"}],
            "weak": [{"axis": "sebum", "label": "себум/жирность", "significance": "weak"}],
        }

    def test_rejects_significant_negative_claimed_absent(self):
        output = {
            "explanation": "Существенных минусов по сенсибилизации не выявлено.",
            "expectations": None,
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_rejects_medical_claim(self):
        output = {
            "explanation": "PEG-100 стеарат ослабляет барьер.",
            "expectations": None,
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_rejects_technical_keys(self):
        output = {
            "explanation": "hydration поддерживает увлажнение.",
            "expectations": None,
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_accepts_correct_output(self):
        output = {
            "explanation": "Состав требует внимания: есть потенциально нежелательные факторы сенсибилизации.",
            "expectations": None,
        }
        self.assertTrue(_validate_report_once(self._inp(), output))

    def test_rejects_score_changes_and_legacy_sections(self):
        output = {
            "explanation": "Состав требует внимания.",
            "expectations": None,
            "score": 100,
        }
        self.assertFalse(_validate_report_once(self._inp(), output))


class ReportInputTests(unittest.TestCase):
    def test_build_input_classifies_axes(self):
        analysis = {
            "score": 25,
            "verdict": "Не рекомендуется",
            "dimensions": {"hydration": 3.0, "irritation": -2.0, "sensitization": -0.1},
            "priorities": {"hydration": 0.31, "barrier": 0.15, "irritation": 0.31, "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04},
        }
        inp = _build_report_input(analysis)
        self.assertIn("увлажнение", [p["label"] for p in inp["positive"]])
        self.assertIn("раздражение", [n["label"] for n in inp["negative"]])
        self.assertIn("сенсибилизация", [w["label"] for w in inp["weak"]])


if __name__ == "__main__":
    unittest.main()
