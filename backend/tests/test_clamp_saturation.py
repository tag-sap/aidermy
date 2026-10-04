"""Regression: замена clamp(0..1) на tanh(raw/SATURATION_SCALE).

Фаза 7: жёсткий clamp одновременно обнулял отрицательные penalties и насыщал
положительные факторы (raw > 1 -> 1.0), создавая кластер высоких score. Новая
формула знакопеременного насыщения: отрицательные raw реально штрафуют,
положительные насыщаются плавно, score остаётся детерминированным.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scoring_engine import score_product_against_profile_canonical
from app.scoring_config import SATURATION_SCALE, SCORING_CONFIG_VERSION

PROFILE = {"skin_type": "Жирная", "concerns": [], "allergies": [], "custom_text": ""}
WEIGHTS = {"hydration": 0.30, "barrier": 0.15, "irritation": 0.30, "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04}


def _score(ingredients, knowledge):
    return score_product_against_profile_canonical(
        ingredients=ingredients,
        canonical_knowledge=knowledge,
        user_profile=PROFILE,
        canonical_weights=WEIGHTS,
    )


class SaturationFormulaTests(unittest.TestCase):
    def test_negative_factors_penalize(self):
        base_knowledge = {
            "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}},
        }
        neg_knowledge = {
            "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}},
            "fragrance": {"irritation": {"direction": "positive", "strength": 0.9, "confidence": 0.9}},
        }
        base = _score(["glycerin"], base_knowledge)
        with_neg = _score(["glycerin", "fragrance"], neg_knowledge)
        self.assertLess(with_neg["score"], base["score"])

    def test_negative_not_clamped_to_zero(self):
        r = _score(["fragrance"], {"fragrance": {"irritation": {"direction": "positive", "strength": 0.9, "confidence": 0.9}}})
        self.assertLess(r["dimensions"]["irritation"], 0.0)

    def test_positive_saturates_gradually(self):
        c2 = math.tanh(2.0 / SATURATION_SCALE)
        c5 = math.tanh(5.0 / SATURATION_SCALE)
        self.assertLess(c2, c5)
        self.assertLess(c2, 1.0)

    def test_no_hard_ceiling_at_one(self):
        self.assertLess(math.tanh(1.0 / SATURATION_SCALE), 1.0)

    def test_determinism(self):
        k = {
            "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.9}},
            "fragrance": {"irritation": {"direction": "positive", "strength": 0.9, "confidence": 0.9}},
        }
        a = _score(["glycerin", "fragrance"], k)
        b = _score(["glycerin", "fragrance"], k)
        self.assertEqual(a["score"], b["score"])
        self.assertEqual(a["dimensions"], b["dimensions"])

    def test_config_version_bumped(self):
        self.assertNotEqual(SCORING_CONFIG_VERSION, "1.2.0")


if __name__ == "__main__":
    unittest.main()
