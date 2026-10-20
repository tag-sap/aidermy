"""Interaction replacement: замещение индивидуальных эффектов парами."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.interaction_scoring import (
    INTERACTION_REPLACEMENT_VERSION,
    apply_interaction_replacements,
    replacement_admissibility,
)
from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
from app.scoring_engine import score_product_against_profile_canonical

WEIGHTS = {
    "hydration": 0.0, "barrier": 0.0, "irritation": 1.0,
    "sensitization": 0.0, "sebum": 0.0, "pigmentation": 0.0,
}
KNOWLEDGE = {
    "ingredient a": {
        "irritation": {"direction": "positive", "strength": 0.5, "confidence": 0.8},
        "hydration": {"direction": "positive", "strength": 0.4, "confidence": 0.7},
    },
    "ingredient b": {
        "irritation": {"direction": "positive", "strength": 0.5, "confidence": 0.8},
        "hydration": {"direction": "positive", "strength": 0.4, "confidence": 0.7},
    },
    "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}},
}


def _profile():
    sp = normalize_scoring_profile({"skin_type": "Нормальная", "age": "25-35"})
    sp["structured"]["axis_multipliers"] = resolve_personal_profile(
        sp.get("structured") or {}
    )["axis_multipliers"]
    return sp


def _record(**overrides):
    record = {
        "interaction_id": 101,
        "ingredient_a": "ingredient a",
        "ingredient_b": "ingredient b",
        "axis": "irritation",
        "direction": "positive",
        "strength": 0.2,
        "confidence": 0.9,
        "state": "known",
        "source": "pubmed:12345",
        "source_type": "pubmed",
        "interaction_type": "conflict",
        "effect_kind": "absolute",
        "evidence": "clinical trial",
    }
    record.update(overrides)
    return record


def _score(interactions):
    return score_product_against_profile_canonical(
        ingredients=["ingredient a", "ingredient b", "glycerin"],
        canonical_knowledge=KNOWLEDGE,
        user_profile=_profile(),
        canonical_weights=WEIGHTS,
        interactions=interactions,
    )


class AdmissibilityTests(unittest.TestCase):
    def test_delta_semantics_rejected(self):
        self.assertEqual(
            replacement_admissibility(_record(effect_kind="delta"), 0.5), "delta_semantics"
        )

    def test_heuristic_source_rejected(self):
        self.assertEqual(
            replacement_admissibility(_record(source_type="heuristic"), 0.5), "unverified_source"
        )

    def test_low_confidence_rejected(self):
        self.assertEqual(
            replacement_admissibility(_record(confidence=0.2, state="insufficient"), 0.5),
            "insufficient_confidence",
        )

    def test_valid_absolute_record_accepted(self):
        self.assertIsNone(replacement_admissibility(_record(), 0.5))


class ReplacementTests(unittest.TestCase):
    def test_no_interactions_keeps_individual_effects(self):
        baseline = _score(None)
        replacement = apply_interaction_replacements(
            {"irritation": [{"ingredient": "ingredient a", "sign": -1, "value": 0.3}]},
            None,
        )
        self.assertEqual(replacement["applied"], [])
        self.assertEqual(replacement["positive"]["irritation"], [])
        self.assertEqual(replacement["negative"]["irritation"], [0.3])
        self.assertIsNone(baseline.get("interaction_replacement"))

    def test_rejected_interaction_keeps_individual_effects(self):
        result = apply_interaction_replacements(
            {"irritation": [
                {"ingredient": "ingredient a", "sign": -1, "value": 0.3},
                {"ingredient": "ingredient b", "sign": -1, "value": 0.2},
            ]},
            [_record(effect_kind="delta", source_type="heuristic", confidence=0.2, state="insufficient")],
        )
        self.assertEqual(result["applied"], [])
        self.assertEqual(result["negative"]["irritation"], [0.3, 0.2])
        self.assertEqual(result["rejected"][0]["reason"], "delta_semantics")

    def test_replacement_only_on_affected_axis(self):
        result = apply_interaction_replacements(
            {
                "irritation": [
                    {"ingredient": "ingredient a", "sign": -1, "value": 0.3},
                    {"ingredient": "ingredient b", "sign": -1, "value": 0.2},
                ],
                "hydration": [
                    {"ingredient": "ingredient a", "sign": 1, "value": 0.4},
                    {"ingredient": "ingredient b", "sign": 1, "value": 0.3},
                ],
            },
            [_record()],
        )
        self.assertEqual(len(result["applied"]), 1)
        self.assertAlmostEqual(result["negative"]["irritation"][0], 0.18, places=6)
        self.assertEqual(result["positive"]["hydration"], [0.4, 0.3])

    def test_no_double_count(self):
        result = apply_interaction_replacements(
            {"irritation": [
                {"ingredient": "ingredient a", "sign": -1, "value": 0.3},
                {"ingredient": "ingredient b", "sign": -1, "value": 0.2},
            ]},
            [_record()],
        )
        self.assertAlmostEqual(result["negative"]["irritation"][0], 0.18, places=6)
        self.assertNotIn(0.3, result["negative"]["irritation"])
        self.assertNotIn(0.2, result["negative"]["irritation"])

    def test_pair_order_is_irrelevant(self):
        forward = _record(ingredient_a="ingredient a", ingredient_b="ingredient b")
        backward = _record(ingredient_a="ingredient b", ingredient_b="ingredient a")
        first = apply_interaction_replacements({"irritation": []}, [forward])
        second = apply_interaction_replacements({"irritation": []}, [backward])
        self.assertEqual(first["applied"][0]["pair"], second["applied"][0]["pair"])

    def test_duplicate_records_applied_once(self):
        result = apply_interaction_replacements(
            {"irritation": []},
            [_record(interaction_id=1), _record(interaction_id=2)],
        )
        self.assertEqual(len(result["applied"]), 1)
        self.assertAlmostEqual(result["negative"]["irritation"][0], 0.18, places=6)

    def test_conflicting_records_rejected(self):
        result = apply_interaction_replacements(
            {"irritation": [
                {"ingredient": "ingredient a", "sign": -1, "value": 0.3},
                {"ingredient": "ingredient b", "sign": -1, "value": 0.2},
            ]},
            [_record(interaction_id=1, strength=0.2), _record(interaction_id=2, strength=0.8)],
        )
        self.assertEqual(result["applied"], [])
        self.assertEqual(result["rejected"][0]["reason"], "conflicting_records")
        self.assertEqual(result["negative"]["irritation"], [0.3, 0.2])

    def test_shared_ingredient_rejected(self):
        result = apply_interaction_replacements(
            {"irritation": []},
            [
                _record(interaction_id=1, ingredient_a="a", ingredient_b="b"),
                _record(interaction_id=2, ingredient_a="a", ingredient_b="c"),
            ],
        )
        self.assertEqual(result["applied"], [])
        self.assertEqual({item["reason"] for item in result["rejected"]}, {"shared_ingredient"})

    def test_deterministic_regardless_of_record_order(self):
        records = [
            _record(interaction_id=1, ingredient_a="a", ingredient_b="b"),
            _record(interaction_id=2, ingredient_a="c", ingredient_b="d", axis="barrier"),
        ]
        first = apply_interaction_replacements({"irritation": []}, copy.deepcopy(records))
        second = apply_interaction_replacements({"irritation": []}, list(reversed(records)))
        self.assertEqual(first["applied"], second["applied"])


class ScoringIntegrationTests(unittest.TestCase):
    def test_score_uses_replacement_and_trace(self):
        baseline = _score(None)
        result = _score([_record()])
        self.assertIsNotNone(result.get("interaction_replacement"))
        self.assertEqual(result["interaction_replacement"]["version"], INTERACTION_REPLACEMENT_VERSION)
        self.assertEqual(len(result["interaction_replacement"]["applied"]), 1)
        self.assertNotEqual(baseline["score"], result["score"])

        irritation_factors = [
            f for f in result["negative_factors"] if f.get("property") == "irritation"
        ]
        self.assertEqual(len(irritation_factors), 1)
        self.assertIn("+", irritation_factors[0]["ingredient"])

        hydration = [f for f in result["positive_factors"] if f.get("property") == "hydration"]
        self.assertEqual(
            {f["ingredient"] for f in hydration},
            {"ingredient a", "ingredient b", "glycerin"},
        )

    def test_real_heuristic_records_do_not_change_score(self):
        record = _record(
            effect_kind="delta", source_type="heuristic", confidence=0.2,
            state="insufficient", source="seed", evidence="legacy heuristic",
        )
        baseline = _score(None)
        result = _score([record])
        self.assertEqual(baseline["score"], result["score"])
        self.assertEqual(result["interaction_replacement"]["applied"], [])
        self.assertEqual(result["interaction_replacement"]["rejected"][0]["reason"], "delta_semantics")

    def test_score_stays_in_range(self):
        result = _score([_record(strength=1.0, confidence=1.0)])
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_blocked_phase_uses_combined_effect(self):
        profile = _profile()
        profile["structured"]["therapy"] = [{"id": "tretinoin", "active": True}]
        profile["structured"]["procedures"] = [{"id": "recent_peeling", "period": "<7"}]
        from app.phase1 import evaluate_phase1

        result = score_product_against_profile_canonical(
            ingredients=["ingredient a", "ingredient b"],
            canonical_knowledge=KNOWLEDGE,
            user_profile=profile,
            canonical_weights=WEIGHTS,
            interactions=[_record(strength=1.0, confidence=1.0)],
            pre_score_check=lambda preliminary: evaluate_phase1(
                preliminary, profile, ["ingredient a", "ingredient b"]
            ),
        )
        self.assertIn(result["phase1_status"], {"passed", "blocked"})
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


if __name__ == "__main__":
    unittest.main()
