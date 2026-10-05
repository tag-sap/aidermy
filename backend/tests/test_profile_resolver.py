# tests/test_profile_resolver.py
# Тесты для PROFILE MATRIX + PROFILE RESOLVER.
import unittest

from app.profile_matrix import AXES, GOALS, PROFILE_MATRIX
from app.profile_resolver import (
    intolerance_to_ingredients,
    legacy_profile_to_structured,
    normalize_scoring_profile,
    resolve_personal_profile,
)


class ProfileMatrixTests(unittest.TestCase):
    def test_every_id_has_all_axes(self):
        for sid, node in PROFILE_MATRIX.items():
            self.assertEqual(node["id"], sid, f"{sid}: id mismatch")
            self.assertTrue(node.get("category"), f"{sid}: no category")
            self.assertIn(node["mode"], ("score", "warning", "context", "restriction"), f"{sid}: bad mode")
            self.assertEqual(set(node["axes"].keys()), set(AXES), f"{sid}: axes keys mismatch")

    def test_weights_in_unit_interval(self):
        for sid, node in PROFILE_MATRIX.items():
            for axis, w in node["axes"].items():
                self.assertGreaterEqual(w, 0.0, f"{sid}.{axis} < 0")
                self.assertLessEqual(w, 1.0, f"{sid}.{axis} > 1")

    def test_parents_exist(self):
        for sid, node in PROFILE_MATRIX.items():
            p = node.get("parent")
            if p:
                self.assertIn(p, PROFILE_MATRIX, f"{sid}: parent {p} missing")

    def test_goals_not_in_score_matrix(self):
        for g in GOALS:
            self.assertNotIn(g, PROFILE_MATRIX, f"goal {g} должен быть metadata/context")


class ResolverTests(unittest.TestCase):
    def test_returns_only_canonical_axes(self):
        r = resolve_personal_profile({"skin_type": "normal"})
        self.assertEqual(set(r["weights"].keys()), set(AXES))

    def test_weights_normalized(self):
        r = resolve_personal_profile({"skin_type": "oily", "concerns": ["acne_general"]})
        total = sum(r["weights"].values())
        self.assertAlmostEqual(total, 1.0, places=5)

    def test_sensitization_is_used(self):
        # чувствительная кожа/розацеа должны поднимать sensitization > 0.
        r = resolve_personal_profile({"skin_type": "sensitive"})
        self.assertGreater(r["weights"]["sensitization"], 0.0)
        r2 = resolve_personal_profile({"skin_type": "normal", "states": ["rosacea"]})
        self.assertGreater(r2["weights"]["sensitization"], 0.15)

    def test_allergy_not_a_weight(self):
        r = resolve_personal_profile({"skin_type": "normal", "allergies": ["niacinamide"]})
        self.assertEqual(r["allergies"], ["niacinamide"])
        # аллергия не должна менять weights
        base = resolve_personal_profile({"skin_type": "normal"})
        self.assertEqual(r["weights"], base["weights"])

    def test_age_roundtrips_without_changing_weights(self):
        profile = {"skin_type": "normal", "age": "35_45"}
        resolved = resolve_personal_profile(profile)
        self.assertEqual(resolved["age"], "35_45")
        self.assertEqual(
            resolved["weights"],
            resolve_personal_profile({"skin_type": "normal", "age": "under_25"})["weights"],
        )

    def test_structured_constraints_are_merged_for_scoring(self):
        normalized = normalize_scoring_profile({
            "allergies": ["lactic acid"],
            "structured": {
                "allergies": ["alcohol denat"],
                "intolerances": ["fragrance_intolerance", "niacinamide_intolerance"],
            },
        })
        self.assertIn("lactic acid", normalized["allergies"])
        self.assertIn("alcohol denat", normalized["allergies"])
        self.assertIn("fragrance_intolerance", normalized["intolerances"])
        self.assertIn("niacinamide", normalized["restrictions"])

    def test_intolerance_niacinamide(self):
        soft, hard = intolerance_to_ingredients({"intolerances": ["niacinamide_intolerance"]})
        self.assertIn("niacinamide", hard)

    def test_hierarchy_prevents_double_counting(self):
        # pustules затеняет inflammatory_acne и acne_general.
        with_general = resolve_personal_profile(
            {"skin_type": "normal", "concerns": ["acne_general"], "imperfections": ["pustules"]}
        )
        specific_only = resolve_personal_profile({"skin_type": "normal", "imperfections": ["pustules"]})
        self.assertEqual(with_general["weights"], specific_only["weights"])

    def test_therapy_specificity(self):
        r = resolve_personal_profile({
            "skin_type": "dry",
            "therapy": [{"id": "topical_retinoid", "active": True}, {"id": "tretinoin", "active": True}],
        })
        # только tretinoin активен (topical_retinoid затенён)
        self.assertEqual(r["active_therapy"], ["tretinoin"])

    def test_procedure_temporal_decay(self):
        r_recent = resolve_personal_profile({
            "skin_type": "normal",
            "procedures": [{"id": "recent_laser", "period": "<7 days"}],
        })
        r_old = resolve_personal_profile({
            "skin_type": "normal",
            "procedures": [{"id": "recent_laser", "period": ">3 months"}],
        })
        base = resolve_personal_profile({"skin_type": "normal"})
        self.assertGreater(r_recent["weights"]["irritation"], base["weights"]["irritation"])
        self.assertEqual(r_old["weights"], base["weights"])

    def test_legacy_profile(self):
        s = legacy_profile_to_structured({"skin_type": "Жирная", "concerns": ["Акне"], "allergies": ["Отдушки"]})
        self.assertEqual(s["skin_type"], "oily")
        self.assertIn("acne_general", s["concerns"])
        self.assertIn("fragrance_intolerance", s["intolerances"])

    def test_dehydrated_not_double_counted(self):
        # skin_type dehydrated + concern dehydrated_skin — одна сущность (dedup).
        both = resolve_personal_profile({"skin_type": "dehydrated", "concerns": ["dehydrated_skin"]})
        dehydrated_skin_only = resolve_personal_profile({"concerns": ["dehydrated_skin"]})
        # равен самому сильному одиночному, а не сумме двух dehydrated
        self.assertEqual(both["weights"], dehydrated_skin_only["weights"])


if __name__ == "__main__":
    unittest.main()
