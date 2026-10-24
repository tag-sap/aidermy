"""Score Engine report semantics: absence of benefit is not harm."""
from __future__ import annotations

import unittest

from app.evaluation.analysis import _item_verdict, _overall_verdict


class VerdictSemanticsTests(unittest.TestCase):
    def test_low_goal_benefit_is_neutral_not_harm(self):
        self.assertEqual(_item_verdict("goal:hydration", 0, None), "neutral")
        self.assertEqual(_item_verdict("problem:dryness", 0, None), "neutral")

    def test_missing_data_is_unknown(self):
        self.assertEqual(_item_verdict("goal:hydration", None, None), "unknown")

    def test_confirmed_therapy_risk_can_be_negative(self):
        evidence = [{
            "verification": "confirmed",
            "direction": "contradicts",
            "strength": "strong",
            "confidence": 0.9,
            "claim": "Подтверждённый конфликт.",
        }]
        self.assertEqual(_item_verdict("therapy:retinoid", 50, None, evidence), "negative")

    def test_intolerance_absence_satisfies_restriction(self):
        absent = {"state": "absent"}
        present = {"state": "present"}
        self.assertEqual(_item_verdict("intolerance:niacinamide", 0, absent), "positive")
        self.assertEqual(_item_verdict("intolerance:niacinamide", 0, present), "negative")

    def test_critical_factor_wins_over_many_neutral_cards(self):
        overall = _overall_verdict([
            {"parameter_id": "problem:dryness", "verdict": "neutral", "label": "Сухость", "verdict_label": "Смешанный результат"},
            {"parameter_id": "goal:hydration", "verdict": "neutral", "label": "Увлажнение", "verdict_label": "Влияние неясно"},
            {"parameter_id": "therapy:retinoid", "verdict": "negative", "label": "Ретиноид", "verdict_label": "Конфликт с лечением"},
        ])
        self.assertEqual(overall["verdict"], "Не подходит")


if __name__ == "__main__":
    unittest.main()
