# test_analysis_state.py
# Проверка единой модели состояния: User Analysis (история) — единственный
# источник score, а AI Report — отдельная сущность, которая НЕ пересчитывает score.

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.shelf_service import normalize_history_analysis
from app.services import generate_ai_report


class NormalizeAnalysisTests(unittest.TestCase):
    def test_report_included_from_ai_report_column(self):
        analysis = normalize_history_analysis({
            "verdict": "Подходит",
            "summary": "детерминированное резюме",
            "score": 61,
            "safe_ingredients": '["Glycerin"]',
            "caution_ingredients": '["Alcohol"]',
            "ai_report": "человеческая рецензия",
        })
        self.assertEqual(analysis["score"], 61)
        self.assertEqual(analysis["report"], "человеческая рецензия")

    def test_report_none_when_missing(self):
        analysis = normalize_history_analysis({"verdict": "x", "summary": "y", "score": 61})
        self.assertIsNone(analysis["report"])


class AIReportTests(unittest.TestCase):
    def test_report_uses_existing_score_not_recomputed(self):
        # Score берётся из уже существующего анализа и передаётся в AI как есть.
        analysis = {
            "score": 44,
            "safe_ingredients": ["Glycerin"],
            "caution_ingredients": ["Alcohol"],
            "summary": "детерминированное",
        }
        with patch("app.ai_summary.summarize_with_ai", return_value="AI-рецензия") as mock:
            report = asyncio.run(generate_ai_report("Крем", analysis, {"skin_type": "Жирная"}))
        self.assertEqual(report, "AI-рецензия")
        call_args = mock.call_args[0]
        self.assertEqual(call_args[1], 44)  # переданный score == исходному

    def test_report_falls_back_to_existing_summary(self):
        analysis = {
            "score": 44,
            "safe_ingredients": [],
            "caution_ingredients": [],
            "summary": "детерминированное резюме",
        }
        with patch("app.ai_summary.summarize_with_ai", return_value=None):
            report = asyncio.run(generate_ai_report("Крем", analysis, {}))
        self.assertEqual(report, "детерминированное резюме")


if __name__ == "__main__":
    unittest.main()
