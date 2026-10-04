"""Regression: детерминированное объяснение баланса score для AI-контекста.

_score_balance_text считает вклад каждой оси по той же формуле tanh(raw/S)*weight,
чтобы AI мог объяснить, какие факторы дали положительный, а какие — отрицательный
вклад, и почему итог такой (не «список хороших/плохих ингредиентов»).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import _score_balance_text


class ScoreBalanceTextTests(unittest.TestCase):
    def test_positive_and_negative_separated(self):
        analysis = {
            "dimensions": {"hydration": 3.0, "irritation": -0.7, "sebum": 0.0},
            "priorities": {"hydration": 0.31, "irritation": 0.31, "sebum": 0.15, "barrier": 0.15, "sensitization": 0.04, "pigmentation": 0.04},
        }
        text = _score_balance_text(analysis)
        self.assertIn("Положительный вклад", text)
        self.assertIn("Отрицательный вклад", text)
        self.assertIn("Итог (сумма вкладов)", text)

    def test_negative_axis_uses_minus_sign(self):
        analysis = {
            "dimensions": {"irritation": -0.7},
            "priorities": {"hydration": 0.31, "irritation": 0.31, "sebum": 0.15, "barrier": 0.15, "sensitization": 0.04, "pigmentation": 0.04},
        }
        text = _score_balance_text(analysis)
        self.assertIn("−", text)  # знак минуса для отрицательной оси

    def test_net_matches_score_roughly(self):
        import math
        from app.scoring_config import SATURATION_SCALE
        dims = {"hydration": 3.0, "irritation": -0.7, "sebum": 0.0}
        prio = {"hydration": 0.31, "irritation": 0.31, "sebum": 0.15, "barrier": 0.15, "sensitization": 0.04, "pigmentation": 0.04}
        expected = sum(math.tanh(dims.get(a, 0.0)/SATURATION_SCALE)*prio.get(a, 0.0) for a in prio) / sum(prio.values())
        analysis = {"dimensions": dims, "priorities": prio}
        text = _score_balance_text(analysis)
        self.assertIn(f"{expected*100:.1f}%", text)


if __name__ == "__main__":
    unittest.main()


class SignificanceMarkerTests(unittest.TestCase):
    def _bal(self, dims):
        prio = {"hydration": 0.31, "irritation": 0.31, "sebum": 0.15, "barrier": 0.15, "sensitization": 0.04, "pigmentation": 0.04}
        return _score_balance_text({"dimensions": dims, "priorities": prio})

    def test_weak_negative_marked_weak(self):
        text = self._bal({"sensitization": -0.09})  # -0.5 п.п. -> [слабо]
        self.assertIn("[слабо]", text)
        self.assertNotIn("[значимо]", text)

    def test_strong_negative_marked_significant(self):
        text = self._bal({"irritation": -2.0})  # большой отрицательный вклад
        self.assertIn("[значимо]", text)

    def test_strong_positive_marked_significant(self):
        text = self._bal({"hydration": 3.0})
        self.assertIn("[значимо]", text)
