# tests/test_canonical_scoring.py
# Фаза 8 — canonical six-axis scoring + legacy compatibility layer.

import unittest

from app.axes import (
    AXES,
    CANONICAL_TO_LEGACY_DIMENSION,
    LEGACY_MAPPING_KIND,
    canonicalize_knowledge_map,
    canonicalize_weights,
    legacyize_dimensions,
)
from app.scoring_engine import (
    _canonical_direction_sign,
    score_product_against_profile,
    score_product_against_profile_canonical,
)


class AxesCompatibilityTests(unittest.TestCase):
    def test_canonical_six_axes(self):
        self.assertEqual(
            set(AXES),
            {"hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation"},
        )

    def test_canonicalize_weights_renames(self):
        legacy = {"hydration": 0.35, "barrier_support": 0.25, "sensitivity": 0.2,
                  "acne_control": 0.1, "brightening": 0.1}
        cw = canonicalize_weights(legacy)
        self.assertAlmostEqual(cw["hydration"], 0.35)
        self.assertAlmostEqual(cw["barrier"], 0.25)
        self.assertAlmostEqual(cw["irritation"], 0.2)
        self.assertAlmostEqual(cw["sebum"], 0.1)
        self.assertAlmostEqual(cw["pigmentation"], 0.1)
        self.assertAlmostEqual(cw["sensitization"], 0.0)

    def test_legacyize_dimensions_drops_sensitization(self):
        canon = {"hydration": 0.5, "barrier": 0.3, "irritation": -0.1, "sensitization": 0.2,
                 "sebum": 0.1, "pigmentation": 0.0}
        legacy = legacyize_dimensions(canon)
        self.assertEqual(set(legacy), {"hydration", "barrier_support", "sensitivity",
                                       "acne_control", "brightening"})
        self.assertAlmostEqual(legacy["barrier_support"], 0.3)
        self.assertAlmostEqual(legacy["sensitivity"], -0.1)

    def test_mapping_kind_marked(self):
        self.assertEqual(LEGACY_MAPPING_KIND["hydration"], "exact")
        self.assertEqual(LEGACY_MAPPING_KIND["barrier_support"], "exact")
        self.assertEqual(LEGACY_MAPPING_KIND["sensitivity"], "approximate")
        self.assertEqual(LEGACY_MAPPING_KIND["acne_control"], "approximate")
        self.assertEqual(LEGACY_MAPPING_KIND["brightening"], "approximate")
        self.assertEqual(LEGACY_MAPPING_KIND["sensitization"], "canonical-only")
        self.assertIsNone(CANONICAL_TO_LEGACY_DIMENSION["sensitization"])


class CanonicalScoringTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"skin_type": "dry", "concerns": [], "allergies": [],
                        "intolerances": [], "restrictions": []}
        self.legacy_weights = {"hydration": 0.35, "barrier_support": 0.25, "sensitivity": 0.2,
                               "acne_control": 0.1, "brightening": 0.1}
        self.cw = canonicalize_weights(self.legacy_weights)

    def test_canonical_dimensions_have_six_axes(self):
        k = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.9}}}
        r = score_product_against_profile_canonical(["glycerin"], k, self.profile, self.cw)
        self.assertEqual(set(r["dimensions"].keys()), set(AXES))

    def test_individual_effect_maps_to_canonical_axis(self):
        k = canonicalize_knowledge_map(
            {"fragrance": {"sensitivity": {"direction": "negative", "strength": 0.9, "confidence": 0.9}}}
        )
        r = score_product_against_profile_canonical(["fragrance"], k, self.profile, self.cw)
        props = {f["property"] for f in r["positive_factors"] + r["negative_factors"]}
        self.assertIn("irritation", props)
        self.assertNotIn("sensitivity", props)
        self.assertTrue(any(f["property"] == "irritation" and f["direction"] == "negative"
                            for f in r["negative_factors"]))

    def test_no_canonical_legacy_canonical_loop(self):
        k = canonicalize_knowledge_map({
            "niacinamide": {
                "barrier_support": {"direction": "positive", "strength": 0.8, "confidence": 0.9},
                "brightening": {"direction": "positive", "strength": 0.6, "confidence": 0.8},
            }
        })
        r = score_product_against_profile_canonical(["niacinamide"], k, self.profile, self.cw)
        self.assertTrue(set(r["dimensions"].keys()) <= set(AXES))
        for legacy in ("barrier_support", "sensitivity", "acne_control", "brightening"):
            self.assertNotIn(legacy, r["dimensions"])

    def test_direction_sign_all_six_axes(self):
        self.assertEqual(_canonical_direction_sign("hydration", "positive"), 1.0)
        self.assertEqual(_canonical_direction_sign("barrier", "negative"), -1.0)
        self.assertEqual(_canonical_direction_sign("irritation", "positive"), -1.0)
        self.assertEqual(_canonical_direction_sign("sensitization", "negative"), 1.0)
        self.assertEqual(_canonical_direction_sign("sebum", "positive"), -1.0)
        self.assertEqual(_canonical_direction_sign("pigmentation", "negative"), 1.0)

    def test_unknown_axis_not_scored(self):
        k = {"glycerin": {"comedogenicity": {"direction": "positive", "strength": 0.9, "confidence": 0.9}}}
        canon = canonicalize_knowledge_map(k)
        self.assertEqual(canon, {})
        r = score_product_against_profile_canonical(["glycerin"], canon, self.profile, self.cw)
        self.assertGreaterEqual(r["score"], 40)

    # ------------------------------------------------------------------
    # Фаза 9-fix: comedogenicity/acne_control НЕ попадают в sebum.
    # ------------------------------------------------------------------
    def test_acne_control_negative_does_not_become_sebum(self):
        legacy = {"c13-16 isoparaffin": {"acne_control": {"direction": "negative",
                                                          "strength": 0.8, "confidence": 0.9}}}
        canon = canonicalize_knowledge_map(legacy)
        # acne_control → не ось → весь ингредиент отброшен (нет валидных осей)
        self.assertNotIn("c13-16 isoparaffin", canon)

    def test_ingredient_not_safe_and_caution_from_acne_control(self):
        # Isoparaffin: hydration positive (valid) + acne_control negative (не ось).
        # Должен попасть только в safe (hydration), НЕ в caution.
        legacy = {
            "c13-16 isoparaffin": {
                "hydration": {"direction": "positive", "strength": 0.5, "confidence": 0.7},
                "acne_control": {"direction": "negative", "strength": 0.8, "confidence": 0.9},
            }
        }
        canon = canonicalize_knowledge_map(legacy)
        self.assertIn("hydration", canon["c13-16 isoparaffin"])
        self.assertNotIn("sebum", canon["c13-16 isoparaffin"])
        r = score_product_against_profile_canonical(["c13-16 isoparaffin"], canon, self.profile, self.cw)
        safe = {f["ingredient"] for f in r["positive_factors"]}
        caution = {f["ingredient"] for f in r["negative_factors"]}
        self.assertIn("c13-16 isoparaffin", safe)
        self.assertNotIn("c13-16 isoparaffin", caution)

    def test_valid_sebum_effect_still_scored(self):
        # настоящий sebum effect (sebum positive = повышение себума) → negative factor.
        canon = {"x": {"sebum": {"direction": "positive", "strength": 0.8, "confidence": 0.9}}}
        r = score_product_against_profile_canonical(["x"], canon, self.profile, self.cw)
        self.assertTrue(any(f["property"] == "sebum" and f["direction"] == "negative"
                            for f in r["negative_factors"]))


class LegacyWrapperRegressionTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"skin_type": "dry", "concerns": [], "allergies": [],
                        "intolerances": [], "restrictions": []}
        self.weights = {"hydration": 0.35, "barrier_support": 0.25, "sensitivity": 0.2,
                        "acne_control": 0.1, "brightening": 0.1}

    def test_wrapper_returns_legacy_dimensions(self):
        k = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.9}}}
        r = score_product_against_profile(["glycerin"], k, self.profile, self.weights)
        self.assertEqual(set(r["dimensions"].keys()),
                         {"hydration", "barrier_support", "sensitivity", "acne_control", "brightening"})

    def test_wrapper_and_canonical_same_score(self):
        k = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.9}},
             "niacinamide": {"barrier_support": {"direction": "positive", "strength": 0.8, "confidence": 0.9}}}
        legacy = score_product_against_profile(["glycerin", "niacinamide"], k, self.profile, self.weights)
        canon_k = canonicalize_knowledge_map(k)
        canon = score_product_against_profile_canonical(
            ["glycerin", "niacinamide"], canon_k, self.profile, canonicalize_weights(self.weights)
        )
        self.assertEqual(legacy["score"], canon["score"])

    def test_wrapper_factor_property_is_legacy(self):
        k = {"fragrance": {"sensitivity": {"direction": "negative", "strength": 0.9, "confidence": 0.9}}}
        r = score_product_against_profile(["fragrance"], k, self.profile, self.weights)
        self.assertTrue(any(f["property"] == "sensitivity" for f in r["negative_factors"]))


if __name__ == "__main__":
    unittest.main()
