"""Report context must carry the Phase 1 / recommendation status.

Section 3 of the report contract: the LLM receives the first-phase result and,
only when phase 1 passed, the second-phase result. Blocked / insufficient_data
must not leak a fake 0% score or a positive verdict.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import _build_report_input, _report_input_text


def _analysis(phase1_status, score=None, neg_only=None):
    return {
        "score": score,
        "verdict": "Не рекомендовано" if phase1_status == "blocked" else "Подходит",
        "phase1": {"status": phase1_status},
        "phase1_status": phase1_status,
        "recommendation_status": (
            "Не рекомендовано" if phase1_status == "blocked"
            else "Недостаточно данных" if phase1_status == "insufficient_data"
            else "Рекомендовано"
        ),
        "negative_only_score": neg_only,
        "dimensions": {},
        "priorities": {},
        "positive_factors": [],
        "negative_factors": [],
        "normalized_ingredients": ["glycerin"],
        "goal_evidence": [],
    }


class ReportPhaseStatusBuildInputTests(unittest.TestCase):
    def test_build_input_keeps_phase1_status(self):
        inp = _build_report_input(_analysis("blocked", neg_only=21))
        self.assertEqual(inp["phase1_status"], "blocked")
        self.assertEqual(inp["negative_only_score"], 21)

    def test_build_input_score_none_for_blocked(self):
        inp = _build_report_input(_analysis("blocked"))
        self.assertIsNone(inp["score"])

    def test_build_input_keeps_recommendation_status(self):
        inp = _build_report_input(_analysis("insufficient_data"))
        self.assertEqual(inp["recommendation_status"], "Недостаточно данных")


class ReportPhaseStatusTextTests(unittest.TestCase):
    def test_text_blocked_no_zero_score(self):
        text = _report_input_text(_build_report_input(_analysis("blocked", neg_only=21)))
        self.assertIn("ЗАБЛОКИРОВАНО", text)
        self.assertIn("21%", text)
        self.assertNotIn("0%", text)

    def test_text_insufficient_no_score(self):
        text = _report_input_text(_build_report_input(_analysis("insufficient_data")))
        self.assertIn("НЕДОСТАТОЧНО ДАННЫХ", text)
        self.assertNotIn("Рассчитанный результат", text)

    def test_text_passed_shows_score(self):
        a = _analysis("passed", score=72)
        text = _report_input_text(_build_report_input(a))
        self.assertIn("72%", text)

    def test_text_blocked_instructs_no_positive_compensation(self):
        text = _report_input_text(_build_report_input(_analysis("blocked", neg_only=21)))
        self.assertIn("НЕ утверждай пригодность", text)


class ReportPhaseStatusContextTests(unittest.TestCase):
    def test_context_includes_phase_status_in_deterministic_input(self):
        from app.report_prompt import build_report_context
        analysis = _analysis("blocked", neg_only=21)
        ctx = build_report_context("Test", analysis, {}, "Скрабы и пилинги")
        self.assertIn("category_knowledge", ctx)
        self.assertIn("ЗАБЛОКИРОВАНО", ctx["deterministic_input"])


if __name__ == "__main__":
    unittest.main()
