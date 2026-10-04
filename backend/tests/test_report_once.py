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
            "positive": [{"axis": "hydration", "label": "увлажнение", "significance": "significant"}],
            "negative": [{"axis": "sensitization", "label": "сенсибилизация", "significance": "significant"}],
            "weak": [{"axis": "sebum", "label": "себум/жирность", "significance": "weak"}],
        }

    def test_rejects_significant_negative_claimed_absent(self):
        output = {
            "summary": [{"text": "Совместимость ограниченная.", "sentiment": "negative"}],
            "positive": [{"text": "Состав поддерживает увлажнение.", "sentiment": "positive"}],
            "negative": [{"text": "Существенных минусов по сенсибилизации не выявлено.", "sentiment": "negative"}],
            "expectations": "",
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_rejects_medical_claim(self):
        output = {
            "summary": [{"text": "Совместимость ограниченная.", "sentiment": "negative"}],
            "positive": [{"text": "Состав поддерживает увлажнение.", "sentiment": "positive"}],
            "negative": [{"text": "PEG-100 стеарат ослабляет барьер.", "sentiment": "negative"}],
            "expectations": "",
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_rejects_technical_keys(self):
        output = {
            "summary": [{"text": "hydration поддерживает увлажнение.", "sentiment": "positive"}],
            "positive": [{"text": "Состав поддерживает увлажнение.", "sentiment": "positive"}],
            "negative": [{"text": "Сенсибилизация.", "sentiment": "negative"}],
            "expectations": "",
        }
        self.assertFalse(_validate_report_once(self._inp(), output))

    def test_accepts_correct_output(self):
        output = {
            "summary": [{"text": "Совместимость ограниченная: в составе есть компоненты, которые могут быть нежелательны.", "sentiment": "negative"}],
            "positive": [{"text": "Состав поддерживает увлажнение.", "sentiment": "positive"}],
            "negative": [{"text": "В составе есть компоненты, которые могут быть нежелательны.", "sentiment": "negative"}],
            "expectations": "",
        }
        self.assertTrue(_validate_report_once(self._inp(), output))


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
