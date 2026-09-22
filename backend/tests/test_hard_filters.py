import unittest

from app.scoring_engine import apply_hard_filters, score_product_against_profile


class HardFilterTests(unittest.TestCase):
    def setUp(self):
        self.weights = {
            "hydration": 0.35,
            "barrier_support": 0.25,
            "sensitivity": 0.2,
            "acne_control": 0.1,
            "brightening": 0.1,
        }

    def test_restriction_excludes_product(self):
        profile = {"restrictions": ["Niacinamide"], "allergies": [], "intolerances": []}
        violations = apply_hard_filters(profile, ["Water", "Glycerin", "Niacinamide"])
        self.assertTrue(any(v["type"] == "restriction" for v in violations))

    def test_allergy_excludes_product(self):
        profile = {"restrictions": [], "allergies": ["lactic acid"], "intolerances": []}
        violations = apply_hard_filters(profile, ["Lactic Acid", "Glycerin"])
        self.assertTrue(any(v["type"] == "allergy" for v in violations))

    def test_no_violation_when_clean(self):
        profile = {"restrictions": ["Niacinamide"], "allergies": [], "intolerances": []}
        self.assertEqual(apply_hard_filters(profile, ["Water", "Glycerin"]), [])

    def test_intolerance_lowers_score_but_no_hard_flag(self):
        # Непереносимость — мягкий негатив, а не hard exclusion.
        profile = {
            "skin_type": "dry",
            "concerns": [],
            "allergies": [],
            "intolerances": ["alcohol"],
            "restrictions": [],
        }
        knowledge = {
            "alcohol": {"sensitivity": {"direction": "negative", "strength": 0.8, "confidence": 0.9}},
            "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}},
        }
        result = score_product_against_profile(
            ["Alcohol", "Glycerin"], knowledge, profile, self.weights
        )
        self.assertFalse(any(f.get("type") == "allergy" for f in result["hard_flags"]))
        self.assertTrue(any(f.get("ingredient") == "alcohol" for f in result["negative_factors"]))


if __name__ == "__main__":
    unittest.main()
