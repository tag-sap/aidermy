"""Tests for the new evaluation layer (v2). No database, no network, no AI."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.evaluation import (
    ContractError,
    ParameterEvaluation,
    RuleSet,
    build_snapshot,
    evaluate,
    get_rules,
    is_current,
    resolve_relevance,
    stale_reason,
    validate_registry,
    verify_snapshot,
)

COMPOSITION = "a" * 64
METHOD = "research-1.0.0"


def ev(
    parameter_id: str,
    value: float | None,
    status: str = "assessed",
    **kwargs,
) -> ParameterEvaluation:
    """Build a stored evaluation; ``assessed`` gets the mandatory fields."""
    if status == "assessed":
        kwargs.setdefault("rationale", f"{parameter_id}: оценка по подтверждённым источникам")
        kwargs.setdefault("evidence_ids", ("1",))
    return ParameterEvaluation(
        parameter_id=parameter_id,
        status=status,
        value=value,
        composition_hash=kwargs.pop("composition_hash", COMPOSITION),
        method_version=kwargs.pop("method_version", METHOD),
        **kwargs,
    )


def dry_profile() -> dict:
    # Two different questionnaire answers → two different parameters.
    return {"skin_type": "dry", "concerns": ["dryness"]}


class RegistryTests(unittest.TestCase):
    def test_registry_mapping_is_consistent(self):
        validate_registry()

    def test_score_criteria_cover_exactly_the_allowed_levels(self):
        from app.evaluation import SCORE_LEVELS, SCORE_LEVEL_CRITERIA, get_rules

        self.assertEqual(tuple(sorted(SCORE_LEVEL_CRITERIA)), tuple(sorted(SCORE_LEVELS)))
        self.assertEqual(tuple(sorted(get_rules().score_levels)), tuple(sorted(SCORE_LEVELS)))
        for level, criterion in SCORE_LEVEL_CRITERIA.items():
            self.assertTrue(criterion.strip(), level)
        self.assertIn("частично", SCORE_LEVEL_CRITERIA[50])
        self.assertIn("не как «неизвестно»", SCORE_LEVEL_CRITERIA[50])

    def test_scale_anchors_are_defined_for_every_parameter(self):
        from app.evaluation import PARAMETERS

        for parameter in PARAMETERS.values():
            values = [value for value, _ in parameter.anchors]
            self.assertIn(0, values, parameter.id)
            self.assertIn(100, values, parameter.id)

    def test_parameter_rejects_non_numeric_anchor(self):
        from app.evaluation import Parameter

        with self.assertRaises(ContractError):
            Parameter(
                id="x",
                label="X",
                definition="d",
                anchors=(("high", "текст"),),
            )

    def test_calibrated_rules_require_sorted_unique_bands(self):
        with self.assertRaises(ContractError):
            RuleSet(
                version="bad",
                aggregation="arithmetic_mean",
                completeness_threshold=0.5,
                verdict_bands=((50, "mid"), (80, "high")),
                calibrated=True,
            )

    def test_calibrated_rules_without_bands_are_rejected(self):
        with self.assertRaises(ContractError):
            RuleSet(
                version="bad",
                aggregation="arithmetic_mean",
                completeness_threshold=0.5,
                verdict_bands=(),
                calibrated=True,
            )


class RelevanceTests(unittest.TestCase):
    def test_dry_skin_requests_its_own_questionnaire_parameters(self):
        relevance = resolve_relevance(dry_profile())
        self.assertEqual(
            relevance.ids, ("problem:dryness", "skin_type:dry")
        )
        labels = {item.id: item.label for item in relevance.parameters}
        self.assertEqual(labels["problem:dryness"], "Проблема: «Сухость / обезвоженность»")
        self.assertEqual(labels["skin_type:dry"], "Тип кожи: «Сухая»")

    def test_production_labels_resolve_to_real_ids(self):
        # The production frontend sends human labels, not ids.
        relevance = resolve_relevance(
            {"concerns": ["Высыпания", "Поры и жирность"], "allergies": ["Отдушки"]}
        )
        self.assertEqual(
            relevance.ids,
            ("intolerance:fragrance_intolerance", "problem:acne_general", "problem:sebum_pores"),
        )
        self.assertEqual(relevance.notes, ())

    def test_branch_options_do_not_create_extra_parameters(self):
        # Refinements (papules, blackheads) belong to the concern card, they are not
        # separate evaluated units, so one card yields exactly one parameter.
        relevance = resolve_relevance(
            {"structured": {"concerns": ["acne_general"]}, "concerns": ["Высыпания"]}
        )
        self.assertEqual(relevance.ids, ("problem:acne_general",))

    def test_inactive_therapy_does_not_create_relevance(self):
        inactive = resolve_relevance(
            {"structured": {"therapy": [{"id": "tretinoin", "active": False}]}}
        )
        active = resolve_relevance(
            {"structured": {"therapy": [{"id": "tretinoin", "active": True}]}}
        )
        self.assertEqual(inactive.weights, {})
        self.assertEqual(active.ids, ("therapy:tretinoin",))

    def test_procedure_period_is_part_of_the_parameter_identity(self):
        recent = resolve_relevance(
            {"structured": {"procedures": [{"id": "recent_laser", "period": "<7 days"}]}}
        )
        two_weeks = resolve_relevance(
            {"structured": {"procedures": [{"id": "recent_laser", "period": "7-14"}]}}
        )
        self.assertEqual(recent.ids, ("procedure:recent_laser@<7",))
        self.assertEqual(two_weeks.ids, ("procedure:recent_laser@7-14",))

    def test_old_procedure_creates_no_restriction_but_is_reported(self):
        old = resolve_relevance(
            {"structured": {"procedures": [{"id": "recent_laser", "period": ">3m"}]}}
        )
        self.assertEqual(old.weights, {})
        self.assertTrue(any("более 3 месяцев" in note for note in old.notes))

    def test_dict_shaped_therapy_is_understood(self):
        relevance = resolve_relevance(
            {"structured": {"therapy": {"tretinoin": True, "aha_therapy": False}}}
        )
        self.assertEqual(relevance.ids, ("therapy:tretinoin",))

    def test_allergies_add_their_own_intolerance_parameter(self):
        relevance = resolve_relevance(
            {"skin_type": "normal", "allergies": ["fragrance_intolerance"]}
        )
        self.assertEqual(
            relevance.ids, ("intolerance:fragrance_intolerance", "skin_type:normal")
        )

    def test_specific_ingredient_becomes_its_own_parameter(self):
        relevance = resolve_relevance(
            {
                "structured": {
                    "intolerances": [
                        {"type": "specific_ingredient", "ingredient_id": "Niacinamide"}
                    ]
                }
            }
        )
        self.assertEqual(relevance.ids, ("intolerance:ingredient:niacinamide",))

    def test_unknown_answers_are_reported_not_guessed(self):
        relevance = resolve_relevance(
            {"concerns": ["something else"], "structured": {"therapy": [{"id": "unknown_drug"}]}}
        )
        self.assertEqual(relevance.weights, {})
        self.assertTrue(any("не удалось сопоставить" in note for note in relevance.notes))

    def test_age_is_context_not_an_evaluated_parameter(self):
        relevance = resolve_relevance({"age": "25_35"})
        self.assertEqual(relevance.weights, {})

    def test_empty_profile_yields_no_parameters(self):
        self.assertEqual(resolve_relevance({}).weights, {})


class EngineTests(unittest.TestCase):
    def test_pending_parameter_is_excluded_not_zeroed(self):
        result = evaluate(
            dry_profile(),
            [ev("problem:dryness", 100), ev("skin_type:dry", None, status="pending")],
        )
        self.assertEqual(result.total, 100)
        self.assertAlmostEqual(result.completeness, 0.5, places=6)
        pending = next(item for item in result.parameters if item.parameter_id == "skin_type:dry")
        self.assertIsNone(pending.value)
        self.assertFalse(pending.included)
        self.assertEqual(pending.status, "pending")

    def test_arithmetic_mean_uses_equal_shares(self):
        result = evaluate(
            dry_profile(),
            [ev("problem:dryness", 100), ev("skin_type:dry", 50)],
        )
        self.assertEqual(result.total, 75)
        weights = {item.parameter_id: item.weight for item in result.parameters}
        self.assertAlmostEqual(weights["problem:dryness"], 0.5, places=6)
        self.assertAlmostEqual(weights["skin_type:dry"], 0.5, places=6)

    def test_fractional_mean_keeps_sub_scores_unchanged(self):
        profile = {"skin_type": "dry", "concerns": ["dryness"], "goals": ["hydration"]}
        result = evaluate(
            profile,
            [
                ev("problem:dryness", 100),
                ev("skin_type:dry", 75),
                ev("goal:hydration", 0),
            ],
        )
        self.assertAlmostEqual(result.total, 175 / 3, places=2)
        values = {item.parameter_id: item.value for item in result.parameters}
        self.assertEqual(values["problem:dryness"], 100)
        self.assertEqual(values["skin_type:dry"], 75)
        self.assertEqual(values["goal:hydration"], 0)

    def test_no_assessed_parameter_means_no_total(self):
        result = evaluate({"skin_type": "sensitive"}, [ev("problem:sensitivity", 100)])
        self.assertIsNone(result.total)
        self.assertIsNone(result.verdict)
        self.assertTrue(any("итоговая совместимость не определена" in text
                            for text in result.limitations))

    def test_missing_evaluation_is_pending_not_zero_or_fifty(self):
        result = evaluate(dry_profile(), [])
        self.assertIsNone(result.total)
        for item in result.parameters:
            self.assertIsNone(item.value)
            self.assertFalse(item.included)
            self.assertEqual(item.status, "pending")

    def test_insufficient_status_is_excluded_with_reason(self):
        result = evaluate(
            dry_profile(),
            [
                ev("problem:dryness", 75),
                ev("skin_type:dry", None, status="insufficient_evidence", limitations=("нет источников",)),
            ],
        )
        self.assertEqual(result.total, 75)
        barrier = next(item for item in result.parameters if item.parameter_id == "skin_type:dry")
        self.assertFalse(barrier.included)
        self.assertEqual(barrier.status, "insufficient_evidence")
        self.assertIn("недостаточно доказательств", barrier.reason)
        self.assertTrue(any("нет источников" in text for text in result.limitations))

    def test_not_applicable_is_excluded_and_does_not_change_the_mean(self):
        result = evaluate(
            dry_profile(),
            [
                ev("problem:dryness", 100),
                ev(
                    "skin_type:dry",
                    None,
                    status="not_applicable",
                    rationale="Параметр не применяется: продукт смывается.",
                ),
            ],
        )
        self.assertEqual(result.total, 100)
        excluded = next(item for item in result.parameters if item.parameter_id == "skin_type:dry")
        self.assertFalse(excluded.included)
        self.assertIsNone(excluded.value)
        self.assertEqual(excluded.status, "not_applicable")
        self.assertIn("неприменим", excluded.reason)

    def test_legacy_evaluated_rows_are_never_scored(self):
        legacy = ParameterEvaluation(
            parameter_id="problem:dryness",
            status="evaluated",
            value=80,
            composition_hash=COMPOSITION,
            method_version=METHOD,
        )
        result = evaluate(dry_profile(), [legacy])
        self.assertIsNone(result.total)
        excluded = next(item for item in result.parameters if item.parameter_id == "problem:dryness")
        self.assertFalse(excluded.included)
        self.assertIn("прежней методике", excluded.reason)

    def test_legacy_contradictory_status_is_excluded(self):
        result = evaluate(
            dry_profile(),
            [ev("problem:dryness", 75), ev("skin_type:dry", None, status="contradictory_evidence")],
        )
        barrier = next(item for item in result.parameters if item.parameter_id == "skin_type:dry")
        self.assertFalse(barrier.included)
        self.assertIn("противоречие", barrier.reason)

    def test_verdict_is_suppressed_until_rules_are_calibrated(self):
        full = [ev("problem:dryness", 100), ev("skin_type:dry", 100)]
        result = evaluate(dry_profile(), full)
        self.assertIsNotNone(result.total)
        self.assertIsNone(result.verdict)
        self.assertTrue(any("не откалиброваны" in text for text in result.limitations))

    def test_calibrated_rules_enable_verdict(self):
        rules = RuleSet(
            version="9.9.9-test",
            aggregation="arithmetic_mean",
            completeness_threshold=0.5,
            verdict_bands=((80, "high"), (50, "medium"), (0, "low")),
            calibrated=True,
        )
        result = evaluate(dry_profile(), [ev("problem:dryness", 100), ev("skin_type:dry", 100)], rules)
        self.assertEqual(result.verdict, "high")
        self.assertEqual(result.rule_version, "9.9.9-test")

    def test_same_input_same_hash_regardless_of_order(self):
        evaluations = [ev("problem:dryness", 75), ev("skin_type:dry", 75)]
        first = evaluate(dry_profile(), evaluations)
        second = evaluate(dry_profile(), list(reversed(evaluations)))
        self.assertEqual(first.input_hash, second.input_hash)
        self.assertEqual(first.as_dict(), second.as_dict())

    def test_different_values_change_hash(self):
        first = evaluate(dry_profile(), [ev("problem:dryness", 75), ev("skin_type:dry", 75)])
        second = evaluate(dry_profile(), [ev("problem:dryness", 50), ev("skin_type:dry", 75)])
        self.assertNotEqual(first.input_hash, second.input_hash)

    def test_duplicate_evaluations_are_rejected(self):
        with self.assertRaises(ContractError):
            evaluate(dry_profile(), [ev("problem:dryness", 75), ev("problem:dryness", 100)])

    def test_score_outside_allowed_levels_is_rejected(self):
        for value in (101, 30, 62, -25):
            with self.assertRaises(ContractError, msg=f"value {value}"):
                ev("problem:dryness", value)

    def test_value_requires_assessed_status(self):
        with self.assertRaises(ContractError):
            ev("problem:dryness", 50, status="stale")

    def test_assessed_requires_explanation_and_evidence(self):
        with self.assertRaises(ContractError):
            ParameterEvaluation(
                parameter_id="problem:dryness",
                status="assessed",
                value=75,
                composition_hash=COMPOSITION,
                method_version=METHOD,
                evidence_ids=("1",),
            )
        with self.assertRaises(ContractError):
            ParameterEvaluation(
                parameter_id="problem:dryness",
                status="assessed",
                value=75,
                composition_hash=COMPOSITION,
                method_version=METHOD,
                rationale="объяснение",
            )

    def test_completeness_does_not_gate_the_total(self):
        # One assessed parameter out of three is enough: no coverage penalty.
        profile = {"skin_type": "dry", "concerns": ["dryness"], "goals": ["hydration"]}
        result = evaluate(profile, [ev("problem:dryness", 75)])
        self.assertEqual(result.total, 75)
        self.assertAlmostEqual(result.completeness, 1 / 3, places=6)
        self.assertFalse(any("порог" in text for text in result.limitations))

    def test_min_confidence_excludes_unknown_confidence(self):
        rules = RuleSet(
            version="9.9.9-conf",
            aggregation="arithmetic_mean",
            completeness_threshold=0.5,
            verdict_bands=((0, "low"),),
            calibrated=False,
            min_confidence=0.5,
        )
        result = evaluate(
            dry_profile(),
            [
                ev("problem:dryness", 100),  # confidence is None
                ev("skin_type:dry", 75, confidence=0.9),
            ],
            rules,
        )
        hydration = next(item for item in result.parameters if item.parameter_id == "problem:dryness")
        self.assertFalse(hydration.included)
        self.assertEqual(hydration.status, "insufficient_evidence")

class FreshnessTests(unittest.TestCase):
    def test_composition_change_invalidates(self):
        evaluation = ev("problem:dryness", 75)
        reason = stale_reason(evaluation, composition_hash="b" * 64, method_version=METHOD)
        self.assertIn("состав", reason)
        self.assertFalse(is_current(evaluation, composition_hash="b" * 64, method_version=METHOD))

    def test_method_version_change_invalidates(self):
        evaluation = ev("problem:dryness", 75)
        reason = stale_reason(evaluation, composition_hash=COMPOSITION, method_version="research-2.0.0")
        self.assertIn("методик", reason)

    def test_expired_valid_until_invalidates(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        evaluation = ev("problem:dryness", 75, valid_until=past)
        self.assertIn(
            "valid_until",
            stale_reason(evaluation, composition_hash=COMPOSITION, method_version=METHOD),
        )

    def test_future_valid_until_stays_current(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        evaluation = ev("problem:dryness", 75, valid_until=future)
        self.assertIsNone(
            stale_reason(evaluation, composition_hash=COMPOSITION, method_version=METHOD)
        )

    def test_invalid_valid_until_is_treated_as_stale(self):
        evaluation = ev("problem:dryness", 75, valid_until="not-a-date")
        reason = stale_reason(evaluation, composition_hash=COMPOSITION, method_version=METHOD)
        self.assertIn("valid_until", reason)


class SnapshotTests(unittest.TestCase):
    def _snapshot(self):
        evaluations = [ev("problem:dryness", 100), ev("skin_type:dry", 75)]
        result = evaluate(dry_profile(), evaluations)
        return build_snapshot(
            product={"id": 42, "name": "Test Cream"},
            composition={
                "composition_hash": COMPOSITION,
                "source": "catalog",
                "verified_at": "2026-10-20",
            },
            profile={"skin_type": "dry", "allergies": ["fragrance_intolerance"]},
            evaluations=evaluations,
            result=result,
            rules=get_rules(),
        )

    def test_snapshot_contains_versions_and_hash(self):
        snapshot = self._snapshot()
        self.assertEqual(snapshot["rule_version"], get_rules().version)
        self.assertEqual(snapshot["composition"]["hash"], COMPOSITION)
        self.assertTrue(snapshot["snapshot_id"])
        self.assertTrue(verify_snapshot(snapshot))

    def test_snapshot_does_not_store_raw_allergies(self):
        snapshot = self._snapshot()
        self.assertNotIn("fragrance", str(snapshot["profile"]))
        self.assertEqual(snapshot["profile"]["intolerance_count"], 1)

    def test_snapshot_tampering_is_detected(self):
        snapshot = self._snapshot()
        snapshot["total"] = 99
        self.assertFalse(verify_snapshot(snapshot))

    def test_snapshot_rejects_foreign_composition(self):
        evaluations = [ev("problem:dryness", 100, composition_hash="c" * 64)]
        result = evaluate(dry_profile(), evaluations)
        with self.assertRaises(ContractError):
            build_snapshot(
                product={"id": 1, "name": "X"},
                composition={"composition_hash": COMPOSITION},
                profile=dry_profile(),
                evaluations=evaluations,
                result=result,
                rules=get_rules(),
            )


if __name__ == "__main__":
    unittest.main()
