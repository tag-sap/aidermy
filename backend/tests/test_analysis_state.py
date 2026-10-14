# test_analysis_state.py
# Проверка единой модели состояния: User Analysis (история) — единственный
# источник score, а AI Report — отдельная сущность, которая НЕ пересчитывает score.

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.shelf_service import normalize_history_analysis, score_product
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



    def test_blocked_history_preserves_phase1_and_hides_normal_score(self):
        analysis = normalize_history_analysis({
            "verdict": "Не рекомендован",
            "summary": "Есть блокирующий фактор",
            "score": 82,
            "phase1_status": "blocked",
            "recommendation_status": "not_recommended",
            "negative_only_score": 24,
        })

        self.assertIsNone(analysis["score"])
        self.assertEqual(analysis["phase1_status"], "blocked")
        self.assertEqual(analysis["recommendation_status"], "not_recommended")
        self.assertEqual(analysis["negative_only_score"], 24)

    def test_insufficient_data_history_does_not_expose_normal_score(self):
        analysis = normalize_history_analysis({
            "score": 70,
            "deterministic_json": (
                '{"phase1":{"status":"insufficient_data"},'
                '"phase1_version":"v1","negative_only_score":null}'
            ),
        })

        self.assertIsNone(analysis["score"])
        self.assertEqual(analysis["phase1_status"], "insufficient_data")
        self.assertEqual(analysis["phase1_version"], "v1")

    def test_passed_history_keeps_normal_score(self):
        analysis = normalize_history_analysis({
            "score": 61,
            "phase1_status": "passed",
            "recommendation_status": "recommended",
        })

        self.assertEqual(analysis["score"], 61)
        self.assertEqual(analysis["phase1_status"], "passed")

class ScoreProductPhase1GateTests(unittest.TestCase):
    def test_blocked_saved_analysis_never_returns_normal_score_or_falls_back(self):
        blocked = {
            "score": 82,
            "phase1_status": "blocked",
            "recommendation_status": "not_recommended",
        }
        with patch(
            "app.shelf_service._analysis_from_analysis_table",
            return_value=(82, blocked),
        ), patch(
            "app.database.get_analysis_record"
        ) as get_record, patch(
            "app.shelf_service._find_history_score"
        ) as find_history:
            score, analysis = score_product(
                {"id": "test-user"},
                {"id": "test-product", "slug": "test-product"},
            )

        self.assertIsNone(score)
        self.assertIs(analysis, blocked)
        get_record.assert_not_called()
        find_history.assert_not_called()

    def test_insufficient_data_saved_analysis_never_returns_normal_score(self):
        insufficient = {
            "score": 70,
            "deterministic": {"phase1": {"status": "insufficient_data"}},
        }
        with patch(
            "app.shelf_service._analysis_from_analysis_table",
            return_value=(70, insufficient),
        ), patch(
            "app.database.get_analysis_record"
        ) as get_record:
            score, analysis = score_product(
                {"id": "test-user"},
                {"id": "test-product", "slug": "test-product"},
            )

        self.assertIsNone(score)
        self.assertIs(analysis, insufficient)
        get_record.assert_not_called()


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
        self.assertEqual(report, [{"text": "детерминированное", "sentiment": "negative"}])
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
        self.assertEqual(report, [{"text": "детерминированное резюме", "sentiment": "negative"}])


if __name__ == "__main__":
    unittest.main()
