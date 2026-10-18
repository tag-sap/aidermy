import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import (  # noqa: E402
    _ingredient_is_allowed,
    _ground_report_text,
    _RU_INGREDIENT_NAMES,
)


class IngredientAllowanceTests(unittest.TestCase):
    def test_niacinamide_canonical_name_is_correct(self):
        # Регрессия: раньше канон был «niacinamid», из-за чего любой отчёт
        # с упоминанием ниацинамида отбраковывался grounding'ом.
        self.assertEqual(_RU_INGREDIENT_NAMES["ниацинамид"], "niacinamide")

    def test_exact_and_variant_matching(self):
        allowed = {"niacinamide", "water", "ceramide np"}
        self.assertTrue(_ingredient_is_allowed("niacinamide", allowed))
        self.assertTrue(_ingredient_is_allowed("ceramide", allowed))
        self.assertTrue(_ingredient_is_allowed("ceramide np", allowed))

    def test_no_substring_false_positive(self):
        self.assertFalse(_ingredient_is_allowed("water", {"watermelon"}))
        self.assertFalse(_ingredient_is_allowed("fragrance", {"water"}))


class ReportGroundingTests(unittest.TestCase):
    def _det(self, axes=("barrier", "hydration")):
        return {
            "positive_factors": [{"property": a} for a in axes],
            "negative_factors": [],
            "normalized_ingredients": ["niacinamide", "water", "glycerin"],
            "goal_evidence": [],
        }

    def test_niacinamide_mention_is_accepted(self):
        text = "Ниацинамид и глицерин поддерживают барьер и увлажнение."
        grounded = _ground_report_text(
            text, {"niacinamide", "water", "glycerin"}, False, self._det()
        )
        self.assertIsNotNone(grounded, "упоминание ниацинамида не должно отбраковываться")

    def test_unknown_ingredient_is_rejected(self):
        text = "В составе есть ретинол для увлажнения."
        grounded = _ground_report_text(
            text, {"niacinamide", "water", "glycerin"}, False, self._det()
        )
        self.assertIsNone(grounded)

    def test_forbidden_effect_is_rejected(self):
        text = "Продукт увлажняет и разглаживает морщины."
        grounded = _ground_report_text(
            text, {"niacinamide", "water", "glycerin"}, False, self._det()
        )
        self.assertIsNone(grounded)

    def test_unmodeled_axis_is_rejected(self):
        text = "Средство увлажняет и снижает жирность кожи."
        grounded = _ground_report_text(
            text, {"niacinamide", "water", "glycerin"}, False, self._det()
        )
        self.assertIsNone(grounded)

    def test_plain_text_without_claims_is_accepted(self):
        text = "Оценка сформирована по составу и профилю кожи."
        grounded = _ground_report_text(
            text, {"niacinamide", "water", "glycerin"}, False, self._det()
        )
        self.assertIsNotNone(grounded)


if __name__ == "__main__":
    unittest.main()
