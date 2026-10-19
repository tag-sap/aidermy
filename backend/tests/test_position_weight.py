"""Инварианты позиционного веса INCI (позиция → величина вклада, не классификация)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.analysis_service import AnalysisService
from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
from app.scoring_config import (
    POSITION_WEIGHT_DECAY,
    POSITION_WEIGHT_MAX,
    POSITION_WEIGHT_SINGLE,
    SATURATION_SCALE,
)
from app.scoring_engine import (
    calculate_position_weight,
    clamp,
    normalize_position_config,
    score_product_against_profile,
    score_product_against_profile_canonical,
)

WEIGHTS = {
    "hydration": 0.30, "barrier": 0.15, "irritation": 0.30,
    "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04,
}
KNOWLEDGE = {
    "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}},
    "citric acid": {"irritation": {"direction": "positive", "strength": 0.7, "confidence": 0.6}},
}


def _profile(skin_type="Нормальная", concerns=None):
    profile = {
        "skin_type": skin_type,
        "concerns": concerns or [],
        "allergies": [],
        "intolerances": [],
        "restrictions": [],
    }
    sp = normalize_scoring_profile(profile)
    sp["structured"]["axis_multipliers"] = resolve_personal_profile(
        sp.get("structured") or {}
    )["axis_multipliers"]
    return sp


def _score(ingredients, config=None, profile=None, knowledge=None):
    return score_product_against_profile_canonical(
        ingredients=list(ingredients),
        canonical_knowledge=knowledge or KNOWLEDGE,
        user_profile=profile or _profile(),
        canonical_weights=WEIGHTS,
        position_config=config,
    )


class PositionWeightMathTests(unittest.TestCase):
    def test_default_formula_unchanged(self):
        for position, total in ((1, 10), (5, 10), (10, 10), (3, 7)):
            expected = clamp(
                POSITION_WEIGHT_MAX - (position / max(total, 1)) * POSITION_WEIGHT_DECAY
            )
            self.assertAlmostEqual(
                calculate_position_weight(position, total), expected, places=9
            )

    def test_default_weight_monotonic_decreasing(self):
        weights = [calculate_position_weight(i, 20) for i in range(1, 21)]
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertEqual(weights[0], 1.0)
        self.assertAlmostEqual(weights[-1], 0.5, places=6)

    def test_single_ingredient_weight(self):
        self.assertEqual(calculate_position_weight(1, 1), POSITION_WEIGHT_SINGLE)
        self.assertEqual(calculate_position_weight(1, 1, {"mode": "power"}), POSITION_WEIGHT_SINGLE)

    def test_legacy_config_matches_default(self):
        for position in range(1, 11):
            self.assertAlmostEqual(
                calculate_position_weight(position, 10, {"mode": "legacy"}),
                calculate_position_weight(position, 10),
                places=9,
            )

    def test_power_mode_bounds_monotonic(self):
        config = {"mode": "power", "exponent": 1.0, "min_weight": 0.2}
        weights = [calculate_position_weight(i, 25, config) for i in range(1, 26)]
        self.assertAlmostEqual(weights[0], 1.0, places=9)
        self.assertAlmostEqual(weights[-1], 0.2, places=9)
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_two_phase_early_plateau_then_decay(self):
        config = {"mode": "two_phase", "early_fraction": 0.3, "min_weight": 0.2}
        total = 20
        early = [calculate_position_weight(i, total, config) for i in range(1, 7)]
        self.assertTrue(all(w == 1.0 for w in early), early)
        late = calculate_position_weight(total, total, config)
        self.assertAlmostEqual(late, 0.2, places=9)

    def test_none_mode_disables_position(self):
        for position in (1, 5, 20):
            self.assertEqual(calculate_position_weight(position, 20, {"mode": "none"}), 1.0)

    def test_config_normalization_is_safe(self):
        self.assertIsNone(normalize_position_config(None))
        self.assertIsNone(normalize_position_config({}))
        cfg = normalize_position_config({
            "mode": "unknown", "apply_to": "unknown",
            "min_weight": 5, "exponent": -3, "early_fraction": 9,
        })
        self.assertEqual(cfg["mode"], "legacy")
        self.assertEqual(cfg["apply_to"], "both")
        cfg = normalize_position_config({"mode": "power", "min_weight": 5, "exponent": -3})
        self.assertEqual(cfg["min_weight"], 1.0)
        self.assertEqual(cfg["exponent"], 0.0)
        cfg = normalize_position_config({"mode": "two_phase", "early_fraction": 9})
        self.assertEqual(cfg["early_fraction"], 1.0)


class PositionPipelineTests(unittest.TestCase):
    def test_position_preserved_after_parse_and_normalize(self):
        service = AnalysisService()
        prepared = service.prepare_product_ingredients(
            "Aqua/Water/Eau, Glycerin, Citric Acid"
        )
        # Вода остаётся в списке (baseline-поведение prepare_product_ingredients),
        # порядок исходного INCI сохраняется без пересортировки.
        self.assertEqual(prepared, ["aqua", "glycerin", "citric acid"])

    def test_duplicates_keep_their_positions(self):
        service = AnalysisService()
        prepared = service.prepare_product_ingredients("Glycerin, Glycerin, Citric Acid")
        self.assertEqual(prepared, ["glycerin", "glycerin", "citric acid"])
        self.assertEqual(len(prepared), 3)

    def test_same_inci_same_weights(self):
        ingredients = ["water", "glycerin", "citric acid"]
        first = _score(ingredients, {"mode": "power", "exponent": 1.0, "min_weight": 0.2})
        second = _score(ingredients, {"mode": "power", "exponent": 1.0, "min_weight": 0.2})
        self.assertEqual(first["score"], second["score"])
        self.assertEqual(first["dimensions"], second["dimensions"])

    def test_no_repeated_application(self):
        """weighted_value == strength * confidence * position_weight (ровно один раз)."""
        result = _score(["glycerin", "citric acid"], {"mode": "power", "min_weight": 0.2})
        for factor in result["positive_factors"] + result["negative_factors"]:
            expected = (
                factor["strength"] * factor["confidence"] * factor["position_weight"]
            )
            self.assertAlmostEqual(factor["weighted_value"], expected, places=5)

    def test_classification_unchanged(self):
        ingredients = ["glycerin", "water", "citric acid"]
        base = _score(ingredients)
        candidate = _score(ingredients, {"mode": "power", "exponent": 1.5, "min_weight": 0.1})

        def signature(result):
            return sorted(
                (f["ingredient"], f["property"], f["direction"])
                for f in result["positive_factors"] + result["negative_factors"]
            )

        self.assertEqual(signature(base), signature(candidate))

    def test_position_only_scales_magnitude(self):
        ingredients = ["glycerin", "water", "citric acid"]
        base = _score(ingredients)
        candidate = _score(ingredients, {"mode": "power", "exponent": 1.0, "min_weight": 0.2})
        base_map = {
            (f["ingredient"], f["property"]): f["weighted_value"]
            for f in base["positive_factors"] + base["negative_factors"]
        }
        cand_map = {
            (f["ingredient"], f["property"]): f["weighted_value"]
            for f in candidate["positive_factors"] + candidate["negative_factors"]
        }
        self.assertEqual(set(base_map), set(cand_map))
        # Поздние ингредиенты в power-режиме получают меньший вес.
        for ingredient in ("water", "citric acid"):
            for (name, prop), value in cand_map.items():
                if name == ingredient:
                    self.assertLessEqual(value, base_map[(name, prop)] + 1e-6)
        # Последний ингредиент (Citric Acid) получает меньший вес → меньший штраф.
        self.assertLess(
            cand_map[("citric acid", "irritation")],
            base_map[("citric acid", "irritation")],
        )
        self.assertGreaterEqual(candidate["score"], base["score"])

    def test_apply_to_negative_keeps_positive_weight_at_one(self):
        config = {"mode": "power", "exponent": 1.0, "min_weight": 0.2, "apply_to": "negative"}
        result = _score(["glycerin", "water", "citric acid"], config)
        self.assertTrue(result["positive_factors"])
        self.assertTrue(result["negative_factors"])
        self.assertTrue(all(f["position_weight"] == 1.0 for f in result["positive_factors"]))
        self.assertTrue(any(f["position_weight"] < 1.0 for f in result["negative_factors"]))

    def test_phase1_thresholds_unchanged(self):
        profile = _profile("sensitive", ["irritation_prone"])
        ingredients = ["water", "glycerin", "citric acid"]
        base = _score(ingredients, profile=profile)
        candidate = _score(
            ingredients, {"mode": "power", "exponent": 2.0, "min_weight": 0.05}, profile=profile
        )
        self.assertEqual(base["phase1_status"], candidate["phase1_status"])
        base_branches = (base.get("phase1") or {}).get("branches") or {}
        cand_branches = (candidate.get("phase1") or {}).get("branches") or {}
        self.assertEqual(set(base_branches), set(cand_branches))
        for axis in base_branches:
            self.assertEqual(
                base_branches[axis].get("threshold"), cand_branches[axis].get("threshold")
            )

    def test_global_formula_unchanged(self):
        result = _score(["glycerin", "citric acid"], {"mode": "power", "min_weight": 0.2})
        expected_total = 0.0
        for axis, weight in WEIGHTS.items():
            expected_total += (
                __import__("math").tanh(result["dimensions"].get(axis, 0.0) / SATURATION_SCALE)
                * weight
            )
        expected_score = int(round(clamp(50.0 + 50.0 * (expected_total / sum(WEIGHTS.values())), 0.0, 100.0)))
        # dimensions в результате округлены до 3 знаков → допускаем 1 пункт.
        self.assertLessEqual(abs(result["score"] - expected_score), 1)

    def test_position_model_recorded(self):
        base = _score(["glycerin"])
        self.assertEqual(base["position_model"], {"mode": "legacy", "apply_to": "both"})
        configured = _score(
            ["glycerin"], {"mode": "power", "exponent": 1.0, "min_weight": 0.2}
        )
        self.assertEqual(configured["position_model"]["mode"], "power")
        self.assertEqual(configured["position_model"]["min_weight"], 0.2)

    def test_legacy_wrapper_accepts_position_config(self):
        from app.axes import canonicalize_weights

        legacy_knowledge = {
            "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}},
        }
        legacy_weights = {"hydration": 0.3}
        config = {"mode": "power", "exponent": 1.0, "min_weight": 0.2}
        legacy = score_product_against_profile(
            ["glycerin"], legacy_knowledge, _profile(), legacy_weights,
            position_config=config,
        )
        canonical = score_product_against_profile_canonical(
            ["glycerin"], legacy_knowledge, _profile(),
            canonicalize_weights(legacy_weights), position_config=config,
        )
        self.assertEqual(legacy["score"], canonical["score"])


if __name__ == "__main__":
    unittest.main()
