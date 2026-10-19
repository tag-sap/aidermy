"""Регрессии: непереносимость ниацинамида доходит до Score Engine."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.profile_resolver import (
    intolerance_ingredient_aliases,
    intolerance_to_ingredients,
    normalize_scoring_profile,
    resolve_personal_profile,
)
from app.scoring_config import HARD_FLAG_SCORE_CAP
from app.scoring_engine import (
    apply_hard_filters,
    score_product_against_profile_canonical,
)

WEIGHTS = {
    "hydration": 0.20, "barrier": 0.30, "irritation": 0.20,
    "sensitization": 0.10, "sebum": 0.10, "pigmentation": 0.10,
}
KNOWLEDGE = {
    "niacinamide": {"barrier": {"direction": "positive", "strength": 0.8, "confidence": 0.9}},
    "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}},
}
BASE_PROFILE = {"skin_type": "Нормальная", "age": "25-35", "concerns": []}


def _profile(**extra):
    profile = dict(BASE_PROFILE)
    profile.update(extra)
    sp = normalize_scoring_profile(profile)
    sp["structured"]["axis_multipliers"] = resolve_personal_profile(
        sp.get("structured") or {}
    )["axis_multipliers"]
    return sp


def _score(profile):
    return score_product_against_profile_canonical(
        ingredients=["glycerin", "niacinamide"],
        canonical_knowledge=KNOWLEDGE,
        user_profile=profile,
        canonical_weights=WEIGHTS,
    )


class NiacinamideIntoleranceTests(unittest.TestCase):
    def test_aliases_resolve_label_and_id(self):
        self.assertIn("niacinamide", intolerance_ingredient_aliases("Ниацинамид"))
        self.assertIn("niacinamide", intolerance_ingredient_aliases("niacinamide_intolerance"))
        self.assertIn("niacinamide", intolerance_ingredient_aliases("ниацинамид"))

    def test_legacy_label_becomes_ingredient(self):
        profile = _profile(allergies=["Ниацинамид"])
        self.assertIn("niacinamide", profile["allergies"])

    def test_structured_id_becomes_hard_restriction(self):
        soft, hard = intolerance_to_ingredients({"intolerances": ["niacinamide_intolerance"]})
        self.assertEqual(soft, [])
        self.assertIn("niacinamide", hard)

    def test_structured_id_reaches_hard_flags(self):
        profile = _profile(structured={"intolerances": ["niacinamide_intolerance"]})
        self.assertIn("niacinamide", profile["allergies"])
        result = _score(profile)
        self.assertTrue(result["hard_flags"])
        self.assertEqual(result["hard_flags"][0]["ingredient"], "niacinamide")
        self.assertLessEqual(result["score"], HARD_FLAG_SCORE_CAP)

    def test_legacy_label_blocks_scoring(self):
        result = _score(_profile(allergies=["Ниацинамид"]))
        self.assertTrue(result["hard_flags"])
        self.assertLessEqual(result["score"], HARD_FLAG_SCORE_CAP)

    def test_hard_filter_matches_inci(self):
        violations = apply_hard_filters(
            _profile(allergies=["Ниацинамид"]),
            ["aqua", "niacinamide", "glycerin"],
        )
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["type"], "allergy")

    def test_selected_intolerance_survives_merge(self):
        profile = normalize_scoring_profile({
            **BASE_PROFILE,
            "allergies": ["Ниацинамид"],
            "structured": {"intolerances": ["niacinamide_intolerance"]},
        })
        self.assertIn("niacinamide", profile["allergies"])
        self.assertIn("niacinamide", profile["restrictions"])
        self.assertIn("niacinamide_intolerance", profile["structured"]["intolerances"])

    def test_profile_without_intolerance_is_unaffected(self):
        result = _score(_profile())
        self.assertFalse(result["hard_flags"])
        self.assertGreater(result["score"], HARD_FLAG_SCORE_CAP)

    def test_category_intolerance_is_soft(self):
        profile = _profile(structured={"intolerances": ["fragrance_intolerance"]})
        self.assertIn("fragrance_intolerance", profile["intolerances"])
        result = _score(profile)
        self.assertFalse(result["hard_flags"])


if __name__ == "__main__":
    unittest.main()
