"""Regression: signed-нормализация score вокруг нейтральной точки 50%.

Проверяет семантику:
  raw=0  -> 50% (нейтральная совместимость, отсутствие эффекта не штраф и не бонус);
  raw>0  -> >50% (положительный вклад);
  raw<0  -> <50% (отрицательный вклад);
  отсутствие sebum-эффекта не штрафует продукт;
  реальный отрицательный sebum/irritation не обнуляется;
  сильные значения насыщаются.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scoring_engine import score_product_against_profile_canonical

# Веса (сумма = 1.0) для предсказуемого расчёта.
W = {"hydration": 0.4, "barrier": 0.2, "irritation": 0.2, "sensitization": 0.05, "sebum": 0.1, "pigmentation": 0.05}


def _score(ingredients, knowledge, profile=None, weights=None):
    return score_product_against_profile_canonical(
        ingredients, knowledge, profile or {}, weights or W,
    )


class ScoreNeutralPointTests(unittest.TestCase):
    def test_raw_zero_is_neutral(self):
        # Неизвестный ингредиент -> нет факторов -> raw=0 по всем осям -> 50%.
        res = _score(["unknownxyz"], {})
        self.assertEqual(int(res["score"]), 50)

    def test_positive_raw_above_neutral(self):
        knowledge = {"glyc": {"hydration": {"direction": "positive", "strength": 1.0, "confidence": 0.9}}}
        res = _score(["glyc"], knowledge)
        self.assertGreater(int(res["score"]), 50)

    def test_negative_raw_below_neutral(self):
        # irritation (harm axis), direction positive -> знак -1 -> отрицательный вклад.
        knowledge = {"acid": {"irritation": {"direction": "positive", "strength": 1.0, "confidence": 0.9}}}
        res = _score(["acid"], knowledge)
        self.assertLess(int(res["score"]), 50)

    def test_absence_of_sebum_no_penalty(self):
        # Только положительная гидратация, sebum=0 -> НЕ штраф.
        knowledge = {"glyc": {"hydration": {"direction": "positive", "strength": 1.0, "confidence": 0.9}}}
        res = _score(["glyc"], knowledge)
        self.assertGreater(int(res["score"]), 50)

    def test_real_negative_sebum_is_negative(self):
        # sebum (harm axis), direction positive (повышает себум) -> ниже 50.
        knowledge = {"oil": {"sebum": {"direction": "positive", "strength": 1.0, "confidence": 0.9}}}
        res = _score(["oil"], knowledge)
        self.assertLess(int(res["score"]), 50)

    def test_negative_irritation_not_zeroed(self):
        # Отрицательный вклад по irritation НЕ обнуляется (score < 50, а не 0 с потерей знака).
        knowledge = {"acid": {"irritation": {"direction": "positive", "strength": 0.5, "confidence": 0.9}}}
        res = _score(["acid"], knowledge)
        self.assertLess(int(res["score"]), 50)
        self.assertGreater(int(res["score"]), 0)

    def test_strong_values_saturate(self):
        # Очень сильный положительный вклад насыщается (score близок к 70, но не бесконечен).
        knowledge = {"glyc": {"hydration": {"direction": "positive", "strength": 10.0, "confidence": 1.0}}}
        res = _score(["glyc"], knowledge)
        self.assertLess(int(res["score"]), 100)
        self.assertGreaterEqual(int(res["score"]), 60)

    def test_determinism(self):
        knowledge = {"glyc": {"hydration": {"direction": "positive", "strength": 1.0, "confidence": 0.9}}}
        a = _score(["glyc"], knowledge)
        b = _score(["glyc"], knowledge)
        self.assertEqual(int(a["score"]), int(b["score"]))

    def test_hard_flags_cap_score(self):
        # Аллергия на ингредиент -> hard flag -> score ограничен сверху HARD_FLAG_SCORE_CAP.
        from app.scoring_config import HARD_FLAG_SCORE_CAP
        knowledge = {"glyc": {"hydration": {"direction": "positive", "strength": 1.0, "confidence": 0.9}}}
        res = _score(["glyc"], knowledge, profile={"allergies": ["glyc"]})
        self.assertTrue(res["hard_flags"], "expected hard flag for allergy")
        self.assertLessEqual(int(res["score"]), HARD_FLAG_SCORE_CAP)


if __name__ == "__main__":
    unittest.main()
