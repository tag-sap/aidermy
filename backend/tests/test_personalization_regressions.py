import unittest

from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
from app.scoring_engine import score_product_against_profile


class PersonalizationRegressionTests(unittest.TestCase):
    def test_oily_skin_alone_does_not_infer_acne_goal(self):
        from app.profile_structuring import _skin_goals_from_concerns

        self.assertEqual(_skin_goals_from_concerns({"skin_type": "oily"}), [])

    def test_legacy_concerns_merge_into_partial_structured_profile(self):
        profile = normalize_scoring_profile({
            "skin_type": "oily",
            "concerns": ["acne_general"],
            "structured": {"skin_type": "oily", "concerns": []},
        })

        resolved = resolve_personal_profile(profile["structured"])
        baseline = resolve_personal_profile({})["weights"]
        self.assertIn("acne_general", resolved["selected_ids"])
        self.assertNotEqual(resolved["weights"], baseline)

    def test_external_skin_type_is_preserved_with_structured_profile(self):
        profile = normalize_scoring_profile({
            "skin_type": "dry",
            "structured": {"concerns": ["dehydrated_skin"]},
        })
        localized = normalize_scoring_profile({
            "structured": {"skin_type": "Чувствительная"},
        })

        self.assertEqual(profile["structured"]["skin_type"], "dry")
        self.assertEqual(localized["structured"]["skin_type"], "sensitive")
        self.assertNotEqual(
            resolve_personal_profile(profile["structured"])["weights"],
            resolve_personal_profile({})["weights"],
        )

    def test_severity_changes_resolved_personal_weights(self):
        mild = resolve_personal_profile({
            "concerns": [{"id": "acne_general", "severity": "low"}],
        })
        severe = resolve_personal_profile({
            "concerns": [{"id": "acne_general", "severity": "high"}],
        })

        self.assertNotEqual(mild["axis_multipliers"], severe["axis_multipliers"])
        self.assertEqual(severe["concern_severity"]["acne_general"], "high")
        knowledge = {
            "fragrance": {
                "sensitivity": {
                    "direction": "negative", "strength": 0.8, "confidence": 0.9,
                }
            }
        }
        weights = {
            "hydration": 0.0, "barrier_support": 0.0, "sensitivity": 1.0,
            "acne_control": 0.0, "brightening": 0.0,
        }
        mild_score = score_product_against_profile(
            ["fragrance"], knowledge,
            {"concerns": [{"id": "acne_general", "severity": "low"}]}, weights,
        )
        severe_score = score_product_against_profile(
            ["fragrance"], knowledge,
            {"concerns": [{"id": "acne_general", "severity": "high"}]}, weights,
        )
        self.assertGreater(
            severe_score["negative_factors"][0]["axis_multiplier"],
            mild_score["negative_factors"][0]["axis_multiplier"],
        )

    def test_procedure_period_uses_procedure_decay(self):
        recent = resolve_personal_profile({
            "procedures": [{"id": "professional_peel", "period": "<7"}],
        })
        old = resolve_personal_profile({
            "procedures": [{"id": "professional_peel", "period": ">3 months"}],
        })

        self.assertIn("professional_peel", recent["active_procedures"])
        self.assertGreater(
            recent["weights"]["irritation"], old["weights"]["irritation"]
        )

    def test_high_sensitivity_amplifies_negative_irritation_evidence(self):
        ingredients = ["fragrance"]
        knowledge = {
            "fragrance": {
                "sensitivity": {
                    "direction": "negative",
                    "strength": 0.8,
                    "confidence": 0.9,
                }
            }
        }
        weights = {
            "hydration": 0.0,
            "barrier_support": 0.0,
            "sensitivity": 1.0,
            "acne_control": 0.0,
            "brightening": 0.0,
        }
        ordinary = score_product_against_profile(
            ingredients, knowledge, {"structured": {"sensitivity": "low"}}, weights
        )
        sensitive = score_product_against_profile(
            ingredients, knowledge,
            {"structured": {"sensitivity": "high"}}, weights
        )

        self.assertGreater(
            sensitive["negative_factors"][0]["profile_multiplier"],
            ordinary["negative_factors"][0]["profile_multiplier"],
        )
        self.assertLess(sensitive["score"], ordinary["score"])
        ordinary_factor = ordinary["negative_factors"][0]
        sensitive_factor = sensitive["negative_factors"][0]
        self.assertGreater(
            sensitive_factor["weighted_value"], ordinary_factor["weighted_value"]
        )


class ScoreMathRegressionTests(unittest.TestCase):
    knowledge = {
        "irritant": {
            "irritation": {"direction": "positive", "strength": 0.95, "confidence": 0.95}
        },
        "weak_humectant": {
            "hydration": {"direction": "positive", "strength": 0.12, "confidence": 0.5}
        },
    }
    ingredients = ["irritant", "weak_humectant", "weak_humectant", "weak_humectant"]

    def score(self, profile, ingredients=None, knowledge=None):
        from app.scoring_engine import score_product_against_profile_canonical

        normalized = normalize_scoring_profile({"structured": profile})
        resolved = resolve_personal_profile(normalized["structured"])
        return score_product_against_profile_canonical(
            ingredients or self.ingredients,
            knowledge or self.knowledge,
            normalized,
            resolved["weights"],
            saturation_scale=1.5,
        )

    def test_normal_sensitive_and_reactive_profiles_have_ordered_risk(self):
        normal = self.score({"skin_type": "normal"})
        sensitive = self.score({"skin_type": "sensitive"})
        reactive = self.score({
            "skin_type": "sensitive",
            "concerns": [{"id": "reactive_skin", "severity": "high"}],
        })

        self.assertGreater(normal["score"], sensitive["score"])
        self.assertGreater(sensitive["score"], reactive["score"])

    def test_concern_severity_strengthens_negative_factor(self):
        low = self.score({
            "skin_type": "sensitive",
            "concerns": [{"id": "irritation_prone", "severity": "low"}],
        })
        high = self.score({
            "skin_type": "sensitive",
            "concerns": [{"id": "irritation_prone", "severity": "high"}],
        })

        self.assertGreater(low["score"], high["score"])
        self.assertGreater(
            high["negative_factors"][0]["profile_multiplier"],
            low["negative_factors"][0]["profile_multiplier"],
        )

    def test_treatment_combinations_accumulate_through_profile_interactions(self):
        base = self.score({"skin_type": "sensitive"})
        treatments = {
            "adapalene": [{"id": "adapalene", "active": True}],
            "benzoyl peroxide": [{"id": "benzoyl_peroxide", "active": True}],
            "antibiotics": [{"id": "topical_antibiotic", "active": True}],
            "adapalene + benzoyl peroxide": [
                {"id": "adapalene", "active": True},
                {"id": "benzoyl_peroxide", "active": True},
            ],
            "all treatments": [
                {"id": "adapalene", "active": True},
                {"id": "benzoyl_peroxide", "active": True},
                {"id": "topical_antibiotic", "active": True},
            ],
        }
        results = {
            name: self.score({"skin_type": "sensitive", "therapy": therapy})
            for name, therapy in treatments.items()
        }

        self.assertLess(results["adapalene"]["score"], base["score"])
        self.assertLess(results["benzoyl peroxide"]["score"], base["score"])
        self.assertLess(results["antibiotics"]["score"], base["score"])
        self.assertLess(
            results["adapalene + benzoyl peroxide"]["negative_factors"][0]["profile_multiplier"],
            results["all treatments"]["negative_factors"][0]["profile_multiplier"],
        )
        self.assertLess(results["all treatments"]["score"], base["score"])

    def test_severe_conflict_does_not_make_treatment_or_recent_procedure_helpful(self):
        base_profile = {
            "skin_type": "sensitive",
            "concerns": [{"id": "irritation_prone", "severity": "high"}],
        }
        base = self.score(base_profile)
        adapalene = self.score({
            **base_profile,
            "therapy": [{"id": "adapalene", "active": True}],
        })
        all_treatments = self.score({
            **base_profile,
            "therapy": [
                {"id": "adapalene", "active": True},
                {"id": "benzoyl_peroxide", "active": True},
                {"id": "topical_antibiotic", "active": True},
            ],
        })
        recent_peel = self.score({
            **base_profile,
            "procedures": [{"id": "professional_peel", "period": "<7"}],
        })
        old_peel = self.score({
            **base_profile,
            "procedures": [{"id": "professional_peel", "period": ">3 months"}],
        })

        self.assertLessEqual(adapalene["score"], base["score"])
        self.assertLessEqual(all_treatments["score"], adapalene["score"])
        self.assertLessEqual(recent_peel["score"], old_peel["score"])
        self.assertGreater(
            adapalene["negative_factors"][0]["weighted_value"],
            base["negative_factors"][0]["weighted_value"],
        )
        self.assertGreater(
            recent_peel["negative_factors"][0]["weighted_value"],
            old_peel["negative_factors"][0]["weighted_value"],
        )

    def test_recent_procedure_affects_score_more_than_old_procedure(self):
        base = self.score({"skin_type": "sensitive"})
        recent = self.score({
            "skin_type": "sensitive",
            "procedures": [{"id": "recent_peeling", "period": "<7"}],
        })
        old = self.score({
            "skin_type": "sensitive",
            "procedures": [{"id": "recent_peeling", "period": ">3 months"}],
        })

        self.assertLess(recent["score"], old["score"])
        self.assertEqual(old["score"], base["score"])

    def test_goal_without_deterministic_evidence_does_not_change_score(self):
        without_goal = self.score({"skin_type": "normal"})
        with_goal = self.score({"skin_type": "normal", "goals": ["calm_soothe"]})

        self.assertEqual(with_goal["score"], without_goal["score"])
        self.assertEqual(with_goal["dimensions"], without_goal["dimensions"])

    def test_strong_negative_conflict_is_not_cancelled_by_weak_positives(self):
        result = self.score({
            "skin_type": "sensitive",
            "concerns": [{"id": "irritation_prone", "severity": "high"}],
        })

        self.assertEqual(len(result["positive_factors"]), 3)
        self.assertEqual(len(result["negative_factors"]), 1)
        self.assertLess(result["score"], 45)

    def test_unknown_ingredients_reduce_evidence_confidence(self):
        result = self.score(
            {"skin_type": "normal"},
            ingredients=["known_humectant", "unknown_one", "unknown_two"],
            knowledge={
                "known_humectant": {
                    "hydration": {
                        "direction": "positive", "strength": 0.8, "confidence": 0.9
                    }
                }
            },
        )

        self.assertAlmostEqual(result["confidence"], 0.3, places=2)

    def test_deterministic_json_preserves_score_driving_factors(self):
        import json
        from app.database import _versioned_deterministic_json
        from app.decision_engine import DecisionEngine

        result = DecisionEngine().analyze(
            "synthetic test product",
            self.ingredients,
            {"skin_type": "sensitive", "concerns": [
                {"id": "irritation_prone", "severity": "high"}
            ]},
            knowledge=self.knowledge,
            saturation_scale=1.5,
        )
        persisted = json.loads(_versioned_deterministic_json(result)[0])

        for key in (
            "score", "dimensions", "positive_factors", "negative_factors",
            "hard_flags", "profile_effects", "confidence",
        ):
            self.assertEqual(persisted[key], result[key])


if __name__ == "__main__":
    unittest.main()
