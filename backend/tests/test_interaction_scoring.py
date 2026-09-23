# tests/test_interaction_scoring.py
# Фаза 7 — Interaction Contribution model + integration (versioned, deterministic).
#
# Проверяет: направления (6 осей × 2), strength≠confidence, aggregation,
# unknown/insufficient vs known, feature-flag regression (disabled == legacy),
# anti-double-counting, versioning, cross-product shelf integration.

import unittest

from app import interaction_scoring as iscore
from app.interaction_scoring import (
    aggregate_interactions,
    confidence_policy,
    interaction_contribution,
    interaction_sign,
    strength_weight,
)
from app.scoring_engine import score_product_against_profile
from app.shelf_compatibility import compute_shelf_compatibility


def _known(axis, direction, strength=0.8, confidence=0.9, **kw):
    return {
        "state": "known",
        "axis": axis,
        "direction": direction,
        "strength": strength,
        "confidence": confidence,
        "type": "internal",
        "ingredient_a": "a",
        "ingredient_b": "b",
        **kw,
    }


class InteractionSignTests(unittest.TestCase):
    def test_benefit_axes_positive_is_positive(self):
        self.assertEqual(interaction_sign("hydration", "positive"), 1.0)
        self.assertEqual(interaction_sign("barrier", "positive"), 1.0)

    def test_benefit_axes_negative_is_negative(self):
        self.assertEqual(interaction_sign("hydration", "negative"), -1.0)
        self.assertEqual(interaction_sign("barrier", "negative"), -1.0)

    def test_harm_axes_positive_is_negative(self):
        for axis in ("irritation", "sensitization", "sebum", "pigmentation"):
            self.assertEqual(interaction_sign(axis, "positive"), -1.0, axis)

    def test_harm_axes_negative_is_positive(self):
        for axis in ("irritation", "sensitization", "sebum", "pigmentation"):
            self.assertEqual(interaction_sign(axis, "negative"), 1.0, axis)

    def test_unknown_direction_is_zero(self):
        self.assertEqual(interaction_sign("irritation", "sideways"), 0.0)


class StrengthConfidenceTests(unittest.TestCase):
    def test_strength_numeric_clamped(self):
        self.assertEqual(strength_weight(0.5), 0.5)
        self.assertEqual(strength_weight(2.0), 1.0)
        self.assertEqual(strength_weight(-1.0), 0.0)

    def test_strength_string_mapping(self):
        self.assertEqual(strength_weight("strong"), 1.0)
        self.assertEqual(strength_weight("moderate"), 0.6)
        self.assertEqual(strength_weight("weak"), 0.3)

    def test_confidence_policy_linear(self):
        self.assertEqual(confidence_policy(0.91), 0.91)
        self.assertEqual(confidence_policy(1.5), 1.0)
        self.assertEqual(confidence_policy(None), 0.0)

    def test_strength_not_confidence(self):
        # strong + low confidence НЕ должен давать сильный contribution.
        strong_low_conf = _known("irritation", "positive", strength="strong", confidence=0.31)
        c = interaction_contribution(strong_low_conf)
        self.assertAlmostEqual(c["contribution"], -0.31)


class InteractionContributionTests(unittest.TestCase):
    def test_known_irritation_positive_is_negative(self):
        c = interaction_contribution(_known("irritation", "positive", strength=0.8, confidence=0.9))
        # Фаза 8: contribution идёт напрямую в canonical axis (без legacy-маппинга).
        self.assertEqual(c["axis"], "irritation")
        self.assertNotIn("dimension", c)
        self.assertAlmostEqual(c["contribution"], -0.72)

    def test_insufficient_no_contribution(self):
        rec = {"state": "insufficient", "axis": "irritation", "direction": "positive",
               "strength": 0.8, "confidence": 0.3}
        self.assertIsNone(interaction_contribution(rec))

    def test_unknown_no_contribution(self):
        rec = {"state": "unknown", "axis": "irritation", "direction": "positive"}
        self.assertIsNone(interaction_contribution(rec))

    def test_unknown_axis_no_contribution(self):
        self.assertIsNone(interaction_contribution(_known("nonexistent", "positive")))

    def test_unknown_direction_no_contribution(self):
        self.assertIsNone(interaction_contribution(_known("irritation", "sideways")))


class AggregationTests(unittest.TestCase):
    def test_aggregation_sum_per_dimension(self):
        records = [
            _known("irritation", "positive", strength=0.5, confidence=1.0),  # -0.5
            _known("irritation", "positive", strength=0.5, confidence=1.0),  # -0.5
            _known("irritation", "negative", strength=0.5, confidence=1.0),  # +0.5
        ]
        agg, breakdown = aggregate_interactions(records)
        # Фаза 8: агрегация по canonical axis (irritation), а не legacy sensitivity.
        self.assertAlmostEqual(agg["irritation"], -0.5)
        self.assertEqual(len(breakdown), 3)

    def test_aggregation_order_independent(self):
        r1 = _known("irritation", "positive", strength=0.8, confidence=0.9)
        r2 = _known("barrier", "negative", strength=0.7, confidence=0.8)
        agg1, _ = aggregate_interactions([r1, r2])
        agg2, _ = aggregate_interactions([r2, r1])
        self.assertEqual(agg1, agg2)


class ScoreIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"skin_type": "dry", "concerns": [], "allergies": [],
                        "intolerances": [], "restrictions": []}
        self.weights = {"hydration": 0.35, "barrier_support": 0.25, "sensitivity": 0.2,
                        "acne_control": 0.1, "brightening": 0.1}
        self.knowledge = {
            "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.9}},
        }

    def tearDown(self):
        iscore.INTERACTION_SCORING_ENABLED = False

    def _score(self, interactions, enabled):
        iscore.INTERACTION_SCORING_ENABLED = enabled
        try:
            return score_product_against_profile(
                ["glycerin"], self.knowledge, self.profile, self.weights, interactions=interactions
            )
        finally:
            iscore.INTERACTION_SCORING_ENABLED = False

    def test_disabled_equals_old_score(self):
        base = score_product_against_profile(["glycerin"], self.knowledge, self.profile, self.weights)
        disabled = self._score([_known("hydration", "negative", strength=0.9, confidence=0.9)], enabled=False)
        self.assertEqual(base["score"], disabled["score"])
        self.assertEqual(base["dimensions"], disabled["dimensions"])

    def test_enabled_known_changes_score(self):
        base = score_product_against_profile(["glycerin"], self.knowledge, self.profile, self.weights)
        enabled = self._score([_known("hydration", "negative", strength=0.9, confidence=0.9)], enabled=True)
        # hydration- (известно) уменьшает benefit-ось hydration → score ниже
        self.assertLess(enabled["score"], base["score"])

    def test_enabled_unknown_unchanged(self):
        base = score_product_against_profile(["glycerin"], self.knowledge, self.profile, self.weights)
        enabled = self._score([{"state": "unknown", "axis": "hydration", "direction": "negative"}], enabled=True)
        self.assertEqual(base["score"], enabled["score"])

    def test_enabled_insufficient_unchanged(self):
        base = score_product_against_profile(["glycerin"], self.knowledge, self.profile, self.weights)
        enabled = self._score(
            [{"state": "insufficient", "axis": "hydration", "direction": "negative",
              "strength": 0.9, "confidence": 0.3}], enabled=True
        )
        self.assertEqual(base["score"], enabled["score"])

    def test_anti_double_counting(self):
        # individual (glycerin hydration+) + interaction (hydration-) — три разных источника
        # не дублируются: dimensions = +0.81 (individual) + (-0.81) (interaction) = 0.0.
        iscore.INTERACTION_SCORING_ENABLED = True
        try:
            r = score_product_against_profile(
                ["glycerin"], self.knowledge, self.profile, self.weights,
                interactions=[_known("hydration", "negative", strength=0.9, confidence=0.9)],
            )
        finally:
            iscore.INTERACTION_SCORING_ENABLED = False
        self.assertAlmostEqual(r["dimensions"]["hydration"], 0.0, places=3)
        self.assertEqual(len(r["interaction_breakdown"]), 1)

    def test_version_in_result(self):
        r = score_product_against_profile(["glycerin"], self.knowledge, self.profile, self.weights)
        self.assertEqual(r["interaction_scoring_version"], iscore.INTERACTION_SCORING_VERSION)


class ShelfIntegrationTests(unittest.TestCase):
    def tearDown(self):
        iscore.INTERACTION_SCORING_ENABLED = False

    def _products(self):
        return [
            {"name": "A", "category": "Сыворотки", "ingredients": "Aqua", "score": 80},
            {"name": "B", "category": "Увлажнение", "ingredients": "Aqua", "score": 80},
        ]

    def test_disabled_equals_old(self):
        products = self._products()
        base = compute_shelf_compatibility(products)
        rec = _known("irritation", "positive", strength=0.9, confidence=0.9, type="cross")
        iscore.INTERACTION_SCORING_ENABLED = False
        disabled = compute_shelf_compatibility(products, interactions=[rec])
        self.assertEqual(base["score"], disabled["score"])

    def test_cross_product_known_reduces_score(self):
        products = self._products()
        base = compute_shelf_compatibility(products)
        rec = _known("irritation", "positive", strength=0.9, confidence=0.9, type="cross")
        iscore.INTERACTION_SCORING_ENABLED = True
        try:
            enabled = compute_shelf_compatibility(products, interactions=[rec])
        finally:
            iscore.INTERACTION_SCORING_ENABLED = False
        self.assertLess(enabled["score"], base["score"])


if __name__ == "__main__":
    unittest.main()
