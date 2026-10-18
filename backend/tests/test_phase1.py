import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.phase1 import PHASE1_VERSION, BLOCKING_BRANCHES, calculate_dynamic_threshold, compute_negative_loads, evaluate_phase1, recommendation_status
from app.scoring_config import INTOLERANCE_PENALTY


CANONICAL_WEIGHTS = {
    "hydration": 0.30, "barrier": 0.15, "irritation": 0.30,
    "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04,
}


def _result(**kw):
    base = {
        "negative_factors": [],
        "interaction_breakdown": [],
        "hard_flags": [],
        "unknown_factors": [],
        "positive_factors": [],
        "dimensions": {},
    }
    base.update(kw)
    return base


def _profile(**kw):
    base = {"intolerances": [], "allergies": [], "restrictions": [], "structured": {}}
    base.update(kw)
    return base


class ComputeNegativeLoadsTests(unittest.TestCase):
    def test_intolerance_counted_once(self):
        # Голая запись непереносимости (без weighted_value) игнорируется,
        # penalty учитывается ровно один раз.
        r = _result(negative_factors=[
            {"ingredient": "parfum", "property": "irritation", "direction": "negative"}
        ])
        neg_dim, _ = compute_negative_loads(r, _profile(intolerances=["fragrance_intolerance"]), ["parfum"])
        self.assertAlmostEqual(neg_dim["irritation"], -INTOLERANCE_PENALTY["dimension_delta"])

    def test_negative_interaction_counted_once(self):
        # Используется weighted_contribution, а НЕ contribution + weighted_contribution.
        r = _result(interaction_breakdown=[
            {"axis": "irritation", "contribution": -0.5, "weighted_contribution": -0.5}
        ])
        neg_dim, _ = compute_negative_loads(r, _profile(), ["a", "b"])
        self.assertAlmostEqual(neg_dim["irritation"], -0.5)

    def test_individual_negative_with_diminishing_returns(self):
        r = _result(negative_factors=[
            {"ingredient": "x", "property": "irritation", "weighted_value": 0.8},
            {"ingredient": "y", "property": "irritation", "weighted_value": 0.6},
        ])
        neg_dim, _ = compute_negative_loads(r, _profile(), ["x", "y"])
        # убывающая отдача: 0.8 + 0.6/2 = 1.1
        self.assertAlmostEqual(neg_dim["irritation"], -1.1)

    def test_no_negative_signal_zero(self):
        neg_dim, _ = compute_negative_loads(_result(), _profile(), ["glycerin"])
        self.assertEqual(neg_dim["irritation"], 0.0)


class EvaluatePhase1Tests(unittest.TestCase):
    def test_passed_when_no_negative(self):
        ph = evaluate_phase1(_result(), _profile(), ["glycerin"])
        self.assertEqual(ph["status"], "passed")
        self.assertEqual(ph["violations"], [])

    def test_blocked_single_branch(self):
        r = _result(negative_factors=[
            {"ingredient": "fragrance", "property": "irritation", "weighted_value": 1.0}
        ])
        with patch(
            "app.scoring_engine._profile_negative_multiplier",
            side_effect=lambda axis, profile: 1.6 if axis == "irritation" else 1.0,
        ):
            ph = evaluate_phase1(r, _profile(), ["fragrance"])
        self.assertEqual(ph["status"], "blocked")
        self.assertTrue(any(v["axis"] == "irritation" for v in ph["violations"]))
        self.assertEqual(ph["branches"]["irritation"]["threshold"], 0.4)

    def test_blocked_multiple_branches(self):
        r = _result(negative_factors=[
            {"ingredient": "fragrance", "property": "irritation", "weighted_value": 1.0},
            {"ingredient": "sensitizer", "property": "sensitization", "weighted_value": 0.8},
        ])
        with patch(
            "app.scoring_engine._profile_negative_multiplier",
            side_effect=lambda axis, profile: (
                1.6 if axis in ("irritation", "sensitization") else 1.0
            ),
        ):
            ph = evaluate_phase1(r, _profile(), ["fragrance", "sensitizer"])
        self.assertEqual(ph["status"], "blocked")
        axes = {v["axis"] for v in ph["violations"]}
        self.assertIn("irritation", axes)
        self.assertIn("sensitization", axes)

    def test_positive_does_not_compensate(self):
        r = _result(
            positive_factors=[
                {"ingredient": "glycerin", "property": "hydration", "weighted_value": 1.5}
            ],
            negative_factors=[
                {"ingredient": "fragrance", "property": "irritation", "weighted_value": 1.0}
            ],
        )
        with patch(
            "app.scoring_engine._profile_negative_multiplier",
            side_effect=lambda axis, profile: 1.6 if axis == "irritation" else 1.0,
        ):
            ph = evaluate_phase1(r, _profile(), ["glycerin", "fragrance"])
        self.assertEqual(ph["status"], "blocked")

    def test_load_equal_threshold_blocks(self):
        # «достигает или пересекает порог»: load == threshold -> блокировка (>=).
        r = _result(negative_factors=[
            {"ingredient": "x", "property": "irritation", "weighted_value": 0.4}
        ])
        with patch(
            "app.scoring_engine._profile_negative_multiplier",
            return_value=1.6,
        ):
            ph = evaluate_phase1(r, _profile(), ["x"])
        self.assertEqual(ph["status"], "blocked")
        self.assertEqual(ph["branches"]["irritation"]["threshold"], 0.4)
        self.assertTrue(ph["branches"]["irritation"]["violated"])

    def test_hard_flag_blocks(self):
        r = _result(hard_flags=[
            {"type": "allergy", "ingredient": "niacinamide", "severity": "high", "message": "x"}
        ])
        ph = evaluate_phase1(r, _profile(), ["niacinamide"])
        self.assertEqual(ph["status"], "blocked")
        self.assertEqual(ph["hard_violations"][0]["type"], "allergy")

    def test_empty_insufficient(self):
        ph = evaluate_phase1(_result(), _profile(), [])
        self.assertEqual(ph["status"], "insufficient_data")

    def test_all_unknown_insufficient(self):
        r = _result(unknown_factors=[{"ingredient": "mystery", "position": 1, "reason": "unknown_ingredient"}])
        ph = evaluate_phase1(r, _profile(), ["mystery"])
        self.assertEqual(ph["status"], "insufficient_data")

    def test_positive_factor_cannot_resolve_fully_unknown_ingredient_coverage(self):
        r = _result(
            unknown_factors=[
                {"ingredient": "mystery", "position": 1, "reason": "unknown_ingredient"}
            ],
            positive_factors=[
                {"ingredient": "glycerin", "property": "hydration", "weighted_value": 0.5}
            ],
        )
        ph = evaluate_phase1(r, _profile(), ["mystery"])
        self.assertEqual(ph["status"], "insufficient_data")

    def test_unknown_mixed_with_known_not_insufficient(self):
        r = _result(
            unknown_factors=[{"ingredient": "mystery", "position": 1, "reason": "unknown_ingredient"}],
            positive_factors=[{"ingredient": "glycerin", "property": "hydration", "weighted_value": 0.5}],
        )
        ph = evaluate_phase1(r, _profile(), ["glycerin", "mystery"])
        self.assertEqual(ph["status"], "passed")




class RecommendationStatusTests(unittest.TestCase):
    def test_blocked_overrides_high_score(self):
        ph = {"status": "blocked"}
        self.assertEqual(recommendation_status(ph, 95), "Не рекомендовано")

    def test_insufficient(self):
        self.assertEqual(recommendation_status({"status": "insufficient_data"}, 40), "Недостаточно данных")

    def test_recommended(self):
        self.assertEqual(recommendation_status({"status": "passed"}, 82), "Рекомендовано")

    def test_needs_attention(self):
        self.assertEqual(recommendation_status({"status": "passed"}, 45), "Требует внимания")



class PersistenceTests(unittest.TestCase):
    """Phase 1 не теряется при сохранении/восстановлении deterministic_json."""

    def _row(self, deterministic):
        import json
        return {
            "id": 1, "user_id": 1, "product_id": None, "slug": "x",
            "verdict": "", "summary": "", "score": 50,
            "safe_ingredients": "[]", "caution_ingredients": "[]",
            "active_ingredients": None, "how_to_use": None, "expectations": None,
            "report": None, "what_good": None, "what_caution": None,
            "score_engine_version": "1.2.0",
            "report_score_engine_version": None, "report_prompt_version": None,
            "report_generator_version": None, "created_at": None, "expires_at": None,
            "deterministic_json": json.dumps(deterministic),
        }

    def test_roundtrip_preserves_phase1(self):
        from app.database import _analysis_to_dict
        det = {
            "score_engine_version": "1.2.0",
            "phase1_version": "1.0.0",
            "phase1": {"status": "blocked", "violations": [{"axis": "irritation"}]},
            "recommendation_status": "Не рекомендовано",
        }
        d = _analysis_to_dict(self._row(det))
        self.assertEqual(d["phase1_version"], "1.0.0")
        self.assertEqual(d["deterministic"]["phase1"]["status"], "blocked")
        self.assertEqual(d["deterministic"]["recommendation_status"], "Не рекомендовано")

    def test_missing_phase1_version_is_none(self):
        from app.database import _analysis_to_dict
        d = _analysis_to_dict(self._row({"score_engine_version": "1.2.0"}))
        self.assertIsNone(d.get("phase1_version"))


class BlockedFormulaTests(unittest.TestCase):
    """Формула корректировки заблокированной ячейки: axis_value - threshold/2."""

    WEIGHTS = {"hydration": 0.30, "barrier": 0.15, "irritation": 0.30,
               "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04}

    def _sp(self):
        from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
        profile = {"skin_type": "Нормальная", "concerns": [], "allergies": [], "intolerances": []}
        sp = normalize_scoring_profile(profile)
        sp["structured"]["axis_multipliers"] = resolve_personal_profile(sp.get("structured") or {})["axis_multipliers"]
        return sp

    def _gate(self, negative_dimensions, violated_axes, thresholds):
        branches = {}
        for ax in self.WEIGHTS:
            branches[ax] = {
                "axis": ax,
                "load": max(0.0, -negative_dimensions.get(ax, 0.0)),
                "blocking": ax in violated_axes,
                "threshold": thresholds.get(ax),
                "violated": ax in violated_axes,
                "factor_count": 0,
            }
        return lambda preliminary: {
            "status": "blocked",
            "branches": branches,
            "violations": [branches[ax] for ax in violated_axes],
            "hard_violations": [],
            "negative_dimensions": negative_dimensions,
            "version": "test",
        }

    def _score(self, negative_dimensions, violated_axes, thresholds, knowledge):
        from app.scoring_engine import score_product_against_profile_canonical
        return score_product_against_profile_canonical(
            ingredients=["glycerin"],
            canonical_knowledge=knowledge,
            user_profile=self._sp(),
            canonical_weights=self.WEIGHTS,
            pre_score_check=self._gate(negative_dimensions, violated_axes, thresholds),
        )

    def test_blocked_value_axis_value_minus_threshold_half(self):
        # axis_value = 0.45, threshold = 0.47 -> 0.45 - 0.235 = 0.215
        knowledge = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}}}
        result = self._score({"irritation": -0.45}, ["irritation"], {"irritation": 0.47}, knowledge)
        self.assertEqual(result["phase1_status"], "blocked")
        self.assertAlmostEqual(result["dimensions"]["irritation"], -(0.45 - 0.47 / 2), places=4)

    def test_blocked_branch_ignores_phase2_positives(self):
        knowledge = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}}}
        result = self._score({"irritation": -0.45}, ["irritation"], {"irritation": 0.47}, knowledge)
        # Положительные эффекты фазы 2 не применяются: hydration остаётся нулевой.
        self.assertEqual(result["dimensions"]["hydration"], 0.0)
        self.assertTrue(result["positive_factors"])  # факты собраны, но в балл не входят

    def test_global_block_uses_negative_load_for_all_cells(self):
        # Пересечение одной оси -> статус blocked, все ячейки на негативной нагрузке.
        knowledge = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}}}
        result = self._score({"irritation": -0.6, "sebum": -0.2}, ["irritation"], {"irritation": 0.47}, knowledge)
        self.assertEqual(result["phase1_status"], "blocked")
        # не-нарушенная ось sebum сохраняет свою негативную нагрузку
        self.assertAlmostEqual(result["dimensions"]["sebum"], -0.2, places=4)
        # нарушенная ось скорректирована
        self.assertAlmostEqual(result["dimensions"]["irritation"], -(0.6 - 0.47 / 2), places=4)

    def test_non_tracked_axis_does_not_block(self):
        # Ось с multiplier <= 1 (не блокирующая) не запускает блокировку сама по себе.
        from app.phase1 import evaluate_phase1
        r = {
            "negative_factors": [{"ingredient": "x", "property": "sebum", "weighted_value": 0.5}],
            "interaction_breakdown": [], "hard_flags": [], "unknown_factors": [],
            "positive_factors": [], "dimensions": {},
        }
        with patch("app.scoring_engine._profile_negative_multiplier", return_value=1.0):
            ph = evaluate_phase1(r, _profile(), ["x"])
        self.assertEqual(ph["status"], "passed")
        self.assertFalse(ph["branches"]["sebum"]["blocking"])


if __name__ == "__main__":
    unittest.main()


class Phase2UnchangedIntegrationTests(unittest.TestCase):
    """Phase 2 score не меняется при успешном допуске."""

    KNOWLEDGE = {
        "glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}},
        "panthenol": {"barrier": {"direction": "positive", "strength": 0.8, "confidence": 0.9}},
    }

    def test_score_identical_with_and_without_phase1(self):
        from app.scoring_engine import score_product_against_profile_canonical
        from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile

        profile = {"skin_type": "Нормальная", "concerns": [], "allergies": [], "intolerances": []}
        sp = normalize_scoring_profile(profile)
        sp["structured"]["axis_multipliers"] = resolve_personal_profile(sp.get("structured") or {})["axis_multipliers"]

        from app.decision_engine import DecisionEngine, profile_weights
        weights = profile_weights(profile, "Нормальная")
        direct = score_product_against_profile_canonical(
            ingredients=["glycerin", "panthenol"],
            canonical_knowledge=self.KNOWLEDGE,
            user_profile=sp,
            canonical_weights=weights,
        )

        eng = DecisionEngine()
        full = eng.analyze("Test", "Glycerin, Panthenol", profile, skin_type="Нормальная", knowledge=self.KNOWLEDGE)

        self.assertEqual(full["score"], direct["score"])
        self.assertEqual(full["phase1_status"], "passed")
        self.assertEqual(full["recommendation_status"], "Рекомендовано")

    def test_phase1_runs_before_axis_aggregation(self):
        """Phase 1 получает факторы до агрегации осей Phase 2."""
        from app.scoring_engine import score_product_against_profile_canonical
        from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
        from app.decision_engine import profile_weights

        profile = {
            "skin_type": "Нормальная",
            "concerns": [],
            "allergies": [],
            "intolerances": [],
        }
        sp = normalize_scoring_profile(profile)
        sp["structured"]["axis_multipliers"] = resolve_personal_profile(
            sp.get("structured") or {}
        )["axis_multipliers"]

        observed = {}

        def gate(preliminary):
            observed["dimensions"] = dict(preliminary["dimensions"])
            observed["positive_factors"] = list(preliminary["positive_factors"])
            return {"status": "passed"}

        result = score_product_against_profile_canonical(
            ingredients=["glycerin", "panthenol"],
            canonical_knowledge=self.KNOWLEDGE,
            user_profile=sp,
            canonical_weights=profile_weights(profile, "Нормальная"),
            pre_score_check=gate,
        )

        self.assertTrue(observed["positive_factors"])
        self.assertTrue(all(value == 0 for value in observed["dimensions"].values()))
        self.assertEqual(result["phase1_status"], "passed")
        self.assertTrue(any(value != 0 for value in result["dimensions"].values()))

    def test_phase1_gate_skips_phase2_final_score(self):
        """При blocked/insufficient_data финальная формула Phase 2 не вызывается."""
        from unittest.mock import patch
        import app.scoring_engine as scoring_engine
        from app.scoring_engine import score_product_against_profile_canonical
        from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
        from app.decision_engine import profile_weights

        profile = {
            "skin_type": "Нормальная",
            "concerns": [],
            "allergies": [],
            "intolerances": [],
        }
        sp = normalize_scoring_profile(profile)
        sp["structured"]["axis_multipliers"] = resolve_personal_profile(
            sp.get("structured") or {}
        )["axis_multipliers"]
        weights = profile_weights(profile, "Нормальная")

        # insufficient_data не должен выдавать фиктивный числовой результат.
        with patch.object(
            scoring_engine.math,
            "tanh",
            side_effect=AssertionError("No score for insufficient_data"),
        ):
            result = score_product_against_profile_canonical(
                ingredients=["glycerin", "panthenol"],
                canonical_knowledge=self.KNOWLEDGE,
                user_profile=sp,
                canonical_weights=weights,
                pre_score_check=lambda _preliminary: {
                    "status": "insufficient_data"
                },
            )
        self.assertIsNone(result.get("score"))
        self.assertEqual(result["phase1"]["status"], "insufficient_data")

        # blocked: числовой результат только по отрицательным эффектам.
        result = score_product_against_profile_canonical(
            ingredients=["glycerin", "panthenol"],
            canonical_knowledge=self.KNOWLEDGE,
            user_profile=sp,
            canonical_weights=weights,
            pre_score_check=lambda _preliminary: {
                "status": "blocked",
                "negative_dimensions": {},
                "branches": {},
            },
        )
        self.assertIsInstance(result.get("score"), int)
        self.assertEqual(result["phase1"]["status"], "blocked")


    def test_real_phase1_gate_blocks_negative_load_despite_positive_factors(self):
        """Положительные факторы не компенсируют превышение порога Phase 1."""
        import app.scoring_engine as scoring_engine
        from app.phase1 import evaluate_phase1
        from app.scoring_engine import score_product_against_profile_canonical
        from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
        from app.decision_engine import profile_weights

        ingredients = ["fragrance", "glycerin", "panthenol"]
        knowledge = {
            "fragrance": {"irritation": {
                "direction": "positive", "strength": 1.0, "confidence": 1.0
            }},
            "glycerin": {"hydration": {
                "direction": "positive", "strength": 0.9, "confidence": 0.95
            }},
            "panthenol": {"barrier": {
                "direction": "positive", "strength": 0.8, "confidence": 0.9
            }},
        }
        profile = {
            "skin_type": "Нормальная", "concerns": [],
            "allergies": [], "intolerances": [],
        }
        sp = normalize_scoring_profile(profile)
        sp["structured"]["axis_multipliers"] = resolve_personal_profile(
            sp.get("structured") or {}
        )["axis_multipliers"]
        weights = profile_weights(profile, "Нормальная")

        def run_phase1(preliminary):
            return evaluate_phase1(preliminary, sp, ingredients)

        with patch(
            "app.scoring_engine._profile_negative_multiplier",
            side_effect=lambda axis, _profile: 1.6 if axis == "irritation" else 1.0,
        ):
            result = score_product_against_profile_canonical(
                ingredients=ingredients,
                canonical_knowledge=knowledge,
                user_profile=sp,
                canonical_weights=weights,
                pre_score_check=run_phase1,
            )

        self.assertTrue(result["positive_factors"])
        self.assertEqual(result["phase1"]["status"], "blocked")
        self.assertEqual(result["phase1"]["branches"]["irritation"]["threshold"], 0.4)
        self.assertTrue(result["phase1"]["branches"]["irritation"]["violated"])
        self.assertIsInstance(result["score"], int)
        self.assertLessEqual(
            result["score"], 50,
            "Положительные факторы не должны улучшать балл при blocked",
        )

    def test_result_carries_phase1_fields(self):
        from app.decision_engine import DecisionEngine
        eng = DecisionEngine()
        full = eng.analyze("Test", "Glycerin, Panthenol", {"skin_type": "Нормальная", "allergies": [], "intolerances": []}, skin_type="Нормальная", knowledge=self.KNOWLEDGE)
        self.assertIn("phase1", full)
        self.assertIn("phase1_status", full)
        self.assertIn("recommendation_status", full)
        self.assertIn("phase1_version", full)
        self.assertEqual(full["phase1"]["version"], PHASE1_VERSION)

    def test_dynamic_threshold_uses_multiplier_formula(self):
        """Ось активируется только при multiplier > 1; порог равен 2 - multiplier."""
        with patch("app.scoring_engine._profile_negative_multiplier", return_value=1.0):
            self.assertIsNone(calculate_dynamic_threshold("hydration", {}))

        with patch("app.scoring_engine._profile_negative_multiplier", return_value=1.6):
            self.assertEqual(calculate_dynamic_threshold("hydration", {}), 0.4)

        with patch("app.scoring_engine._profile_negative_multiplier", return_value=2.0):
            self.assertEqual(calculate_dynamic_threshold("hydration", {}), 0.0)

        # Даже если вызывающая функция получает значение выше максимума,
        # порог ограничивается нулём.
        with patch("app.scoring_engine._profile_negative_multiplier", return_value=2.5):
            self.assertEqual(calculate_dynamic_threshold("hydration", {}), 0.0)

    def test_sensitive_profile_does_not_multiply_ingredient_load(self):
        """Профиль больше не усиливает отрицательные вклады напрямую."""
        from app.decision_engine import DecisionEngine

        knowledge = {
            "fragrance": {
                "irritation": {
                    "direction": "negative",
                    "strength": 0.6,
                    "confidence": 0.8,
                }
            },
            "glycerin": {
                "hydration": {
                    "direction": "positive",
                    "strength": 0.9,
                    "confidence": 0.95,
                }
            },
        }
        eng = DecisionEngine()
        neutral = eng.analyze(
            "T", "Fragrance, Glycerin",
            {"skin_type": "Нормальная", "allergies": [], "intolerances": []},
            skin_type="Нормальная", knowledge=knowledge,
        )
        sensitive = eng.analyze(
            "T", "Fragrance, Glycerin",
            {"skin_type": "Чувствительная", "sensitivity": "high", "allergies": [], "intolerances": []},
            skin_type="Чувствительная", knowledge=knowledge,
        )

        load_neutral = neutral["phase1"]["branches"]["irritation"]["load"]
        load_sensitive = sensitive["phase1"]["branches"]["irritation"]["load"]
        self.assertAlmostEqual(load_sensitive, load_neutral)
        neutral_branch = neutral["phase1"]["branches"]["irritation"]
        sensitive_branch = sensitive["phase1"]["branches"]["irritation"]
        self.assertFalse(neutral_branch["blocking"])
        self.assertIsNone(neutral_branch["threshold"])
        self.assertTrue(sensitive_branch["blocking"])
        self.assertIsNotNone(sensitive_branch["threshold"])


class BlockedFormulaTests(unittest.TestCase):
    """Формула корректировки заблокированной ячейки: axis_value - threshold/2."""

    WEIGHTS = {"hydration": 0.30, "barrier": 0.15, "irritation": 0.30,
               "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04}

    def _sp(self):
        from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
        profile = {"skin_type": "Нормальная", "concerns": [], "allergies": [], "intolerances": []}
        sp = normalize_scoring_profile(profile)
        sp["structured"]["axis_multipliers"] = resolve_personal_profile(sp.get("structured") or {})["axis_multipliers"]
        return sp

    def _gate(self, negative_dimensions, violated_axes, thresholds):
        branches = {}
        for ax in self.WEIGHTS:
            branches[ax] = {
                "axis": ax,
                "load": max(0.0, -negative_dimensions.get(ax, 0.0)),
                "blocking": ax in violated_axes,
                "threshold": thresholds.get(ax),
                "violated": ax in violated_axes,
                "factor_count": 0,
            }
        return lambda preliminary: {
            "status": "blocked",
            "branches": branches,
            "violations": [branches[ax] for ax in violated_axes],
            "hard_violations": [],
            "negative_dimensions": negative_dimensions,
            "version": "test",
        }

    def _score(self, negative_dimensions, violated_axes, thresholds, knowledge):
        from app.scoring_engine import score_product_against_profile_canonical
        return score_product_against_profile_canonical(
            ingredients=["glycerin"],
            canonical_knowledge=knowledge,
            user_profile=self._sp(),
            canonical_weights=self.WEIGHTS,
            pre_score_check=self._gate(negative_dimensions, violated_axes, thresholds),
        )

    def test_blocked_value_axis_value_minus_threshold_half(self):
        # axis_value = 0.45, threshold = 0.47 -> 0.45 - 0.235 = 0.215
        knowledge = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}}}
        result = self._score({"irritation": -0.45}, ["irritation"], {"irritation": 0.47}, knowledge)
        self.assertEqual(result["phase1_status"], "blocked")
        self.assertAlmostEqual(result["dimensions"]["irritation"], -(0.45 - 0.47 / 2), places=4)

    def test_blocked_branch_ignores_phase2_positives(self):
        knowledge = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}}}
        result = self._score({"irritation": -0.45}, ["irritation"], {"irritation": 0.47}, knowledge)
        # Положительные эффекты фазы 2 не применяются: hydration остаётся нулевой.
        self.assertEqual(result["dimensions"]["hydration"], 0.0)
        self.assertTrue(result["positive_factors"])  # факты собраны, но в балл не входят

    def test_global_block_uses_negative_load_for_all_cells(self):
        # Пересечение одной оси -> статус blocked, все ячейки на негативной нагрузке.
        knowledge = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}}}
        result = self._score({"irritation": -0.6, "sebum": -0.2}, ["irritation"], {"irritation": 0.47}, knowledge)
        self.assertEqual(result["phase1_status"], "blocked")
        # не-нарушенная ось sebum сохраняет свою негативную нагрузку
        self.assertAlmostEqual(result["dimensions"]["sebum"], -0.2, places=4)
        # нарушенная ось скорректирована
        self.assertAlmostEqual(result["dimensions"]["irritation"], -(0.6 - 0.47 / 2), places=4)

    def test_non_tracked_axis_does_not_block(self):
        # Ось с multiplier <= 1 (не блокирующая) не запускает блокировку сама по себе.
        from app.phase1 import evaluate_phase1
        r = {
            "negative_factors": [{"ingredient": "x", "property": "sebum", "weighted_value": 0.5}],
            "interaction_breakdown": [], "hard_flags": [], "unknown_factors": [],
            "positive_factors": [], "dimensions": {},
        }
        with patch("app.scoring_engine._profile_negative_multiplier", return_value=1.0):
            ph = evaluate_phase1(r, _profile(), ["x"])
        self.assertEqual(ph["status"], "passed")
        self.assertFalse(ph["branches"]["sebum"]["blocking"])


if __name__ == "__main__":
    unittest.main()
