import unittest

from app.goal_evidence import evaluate_goal_evidence


def profile(*concerns):
    return {
        "structured": {
            "skin_type": "oily",
            "concerns": list(concerns),
            "imperfections": [],
            "states": [],
        }
    }


def claim(direction, strength=1.0, confidence=1.0, **metadata):
    return {
        "direction": direction,
        "strength": strength,
        "confidence": confidence,
        "evidence_level": "moderate",
        "source_url": None,
        **metadata,
    }


class GoalEvidenceTests(unittest.TestCase):
    def test_acne_and_closed_comedones_use_separate_explicit_claims(self):
        result = evaluate_goal_evidence(
            profile("acne_general", "closed_comedones"),
            ["ingredient-a"],
            {
                "ingredient-a": {
                    "acne_control": claim("positive"),
                }
            },
        )

        self.assertEqual([item["verdict"] for item in result], ["supports", "insufficient_data"])
        self.assertEqual(result[0]["evidence"][0]["property"], "acne_control")

    def test_comedogenicity_evidence_does_not_become_acne_evidence(self):
        result = evaluate_goal_evidence(
            profile("acne_general", "closed_comedones"),
            ["ingredient-a"],
            {
                "ingredient-a": {
                    "comedogenicity": claim("positive"),
                }
            },
        )

        self.assertEqual([item["verdict"] for item in result], ["insufficient_data", "may_hinder"])

    def test_maps_existing_direct_effects_to_selected_concerns(self):
        result = evaluate_goal_evidence(
            profile(
                "post_acne_pigmentation",
                "dehydrated_skin",
                "impaired_barrier",
                "irritation_prone",
            ),
            ["ingredient-a"],
            {
                "ingredient-a": {
                    "brightening": claim("positive"),
                    "hydration": claim("positive"),
                    "barrier_support": claim("positive"),
                    "irritation": claim("positive"),
                }
            },
        )

        self.assertEqual(
            [item["verdict"] for item in result],
            ["supports", "supports", "supports", "may_hinder"],
        )

    def test_sensitivity_property_uses_legacy_soothing_direction(self):
        result = evaluate_goal_evidence(
            profile("irritation_prone"),
            ["ingredient-a"],
            {"ingredient-a": {"sensitivity": claim("positive")}},
        )

        self.assertEqual(result[0]["verdict"], "supports")

    def test_conflicts_use_strength_and_confidence_not_claim_count(self):
        result = evaluate_goal_evidence(
            profile("dehydrated_skin"),
            ["strong-support", "weak-support", "strong-hinder"],
            {
                "strong-support": {"hydration": claim("positive", 1.0, 1.0)},
                "weak-support": {"hydration": claim("positive", 0.1, 0.1)},
                "strong-hinder": {"hydration": claim("negative", 0.8, 1.0)},
            },
        )

        self.assertEqual(result[0]["verdict"], "supports")

    def test_equal_conflicting_evidence_is_neutral(self):
        result = evaluate_goal_evidence(
            profile("dehydrated_skin"),
            ["support", "hinder"],
            {
                "support": {"hydration": claim("positive", 0.8, 0.5)},
                "hinder": {"hydration": claim("negative", 0.4, 1.0)},
            },
        )

        self.assertEqual(result[0]["verdict"], "neutral")

    def test_unknown_evidence_and_empty_profile_are_safe(self):
        self.assertEqual(
            evaluate_goal_evidence(profile("acne_general"), ["unknown"], {}),
            [{
                "concern_id": "acne_general",
                "label": "Акне",
                "verdict": "insufficient_data",
                "evidence": [],
            }],
        )
        self.assertEqual(evaluate_goal_evidence(profile(), ["ingredient-a"], {}), [])

    def test_skin_type_alone_does_not_create_goal(self):
        self.assertEqual(
            evaluate_goal_evidence(
                {"structured": {"skin_type": "oily", "concerns": []}},
                ["ingredient-a"],
                {},
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
