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


def ev(parameter_id: str, value: float | None, status: str = "evaluated", **kwargs) -> ParameterEvaluation:
    return ParameterEvaluation(
        parameter_id=parameter_id,
        status=status,
        value=value,
        composition_hash=kwargs.pop("composition_hash", COMPOSITION),
        method_version=kwargs.pop("method_version", METHOD),
        **kwargs,
    )


def dry_profile() -> dict:
    return {"skin_type": "dry", "concerns": ["dryness"]}


class RegistryTests(unittest.TestCase):
    def test_registry_mapping_is_consistent(self):
        validate_registry()

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
                aggregation="weighted_mean",
                completeness_threshold=0.5,
                verdict_bands=((50, "mid"), (80, "high")),
                calibrated=True,
            )

    def test_calibrated_rules_without_bands_are_rejected(self):
        with self.assertRaises(ContractError):
            RuleSet(
                version="bad",
                aggregation="weighted_mean",
                completeness_threshold=0.5,
                verdict_bands=(),
                calibrated=True,
            )


class RelevanceTests(unittest.TestCase):
    def test_dry_skin_requests_hydration_and_barrier(self):
        relevance = resolve_relevance(dry_profile())
        self.assertIn("hydration", relevance.weights)
        self.assertIn("barrier", relevance.weights)

    def test_weights_use_max_not_sum(self):
        one = resolve_relevance({"skin_type": "oily"})
        many = resolve_relevance(
            {"skin_type": "oily", "concerns": ["acne_general", "blackheads", "closed_comedones"]}
        )
        self.assertEqual(one.weights.get("sebum"), 1.0)
        self.assertEqual(many.weights.get("sebum"), 1.0)
        self.assertLessEqual(many.weights.get("comedogenicity"), 1.0)

    def test_inactive_therapy_does_not_create_relevance(self):
        inactive = resolve_relevance(
            {"structured": {"therapy": [{"id": "tretinoin", "active": False}]}}
        )
        active = resolve_relevance(
            {"structured": {"therapy": [{"id": "tretinoin", "active": True}]}}
        )
        self.assertNotIn("therapy_safety", inactive.weights)
        self.assertIn("therapy_safety", active.weights)

    def test_old_procedure_does_not_create_relevance(self):
        recent = resolve_relevance(
            {"structured": {"procedures": [{"id": "recent_laser", "period": "<7 days"}]}}
        )
        old = resolve_relevance(
            {"structured": {"procedures": [{"id": "recent_laser", "period": "30+ days"}]}}
        )
        self.assertIn("procedure_safety", recent.weights)
        self.assertNotIn("procedure_safety", old.weights)

    def test_dict_shaped_therapy_is_understood(self):
        relevance = resolve_relevance(
            {"structured": {"therapy": {"tretinoin": True, "aha_therapy": False}}}
        )
        self.assertIn("therapy_safety", relevance.weights)

    def test_allergies_add_fragrance_parameter_and_note(self):
        relevance = resolve_relevance({"skin_type": "normal", "allergies": ["fragrance"]})
        self.assertIn("fragrance_allergen", relevance.weights)
        self.assertTrue(any("аллерг" in note.lower() for note in relevance.notes))

    def test_empty_profile_yields_no_parameters(self):
        self.assertEqual(resolve_relevance({}).weights, {})


class EngineTests(unittest.TestCase):
    def test_total_is_not_diluted_by_missing_parameters(self):
        result = evaluate(
            {"skin_type": "dry"},
            [ev("hydration", 80), ev("barrier", None, status="not_researched")],
        )
        self.assertEqual(result.total, 80)
        self.assertAlmostEqual(result.completeness, 1.0 / 1.6, places=6)

    def test_insufficient_completeness_produces_no_total(self):
        result = evaluate({"skin_type": "sensitive"}, [ev("irritation", 90)])
        self.assertIsNone(result.total)
        self.assertIsNone(result.verdict)
        self.assertLess(result.completeness, get_rules().completeness_threshold)
        self.assertTrue(any("Полнота" in text for text in result.limitations))

    def test_missing_evaluation_is_never_zero_or_fifty(self):
        result = evaluate(dry_profile(), [])
        self.assertIsNone(result.total)
        for item in result.parameters:
            self.assertIsNone(item.value)
            self.assertFalse(item.included)
            self.assertEqual(item.status, "not_researched")

    def test_insufficient_status_is_excluded_with_reason(self):
        result = evaluate(
            dry_profile(),
            [
                ev("hydration", 70),
                ev("barrier", None, status="insufficient_evidence", limitations=("нет источников",)),
            ],
        )
        barrier = next(item for item in result.parameters if item.parameter_id == "barrier")
        self.assertFalse(barrier.included)
        self.assertEqual(barrier.status, "insufficient_evidence")
        self.assertIn("недостаточно доказательств", barrier.reason)
        self.assertTrue(any("нет источников" in text for text in result.limitations))

    def test_contradictory_evidence_is_excluded(self):
        result = evaluate(
            dry_profile(),
            [ev("hydration", 70), ev("barrier", None, status="contradictory_evidence")],
        )
        barrier = next(item for item in result.parameters if item.parameter_id == "barrier")
        self.assertFalse(barrier.included)
        self.assertIn("противоречат", barrier.reason)

    def test_verdict_is_suppressed_until_rules_are_calibrated(self):
        full = [ev("hydration", 90), ev("barrier", 90)]
        result = evaluate(dry_profile(), full)
        self.assertIsNotNone(result.total)
        self.assertIsNone(result.verdict)
        self.assertTrue(any("не откалиброваны" in text for text in result.limitations))

    def test_calibrated_rules_enable_verdict(self):
        rules = RuleSet(
            version="9.9.9-test",
            aggregation="weighted_mean",
            completeness_threshold=0.5,
            verdict_bands=((80, "high"), (50, "medium"), (0, "low")),
            calibrated=True,
        )
        result = evaluate(dry_profile(), [ev("hydration", 90), ev("barrier", 90)], rules)
        self.assertEqual(result.verdict, "high")
        self.assertEqual(result.rule_version, "9.9.9-test")

    def test_same_input_same_hash_regardless_of_order(self):
        evaluations = [ev("hydration", 70), ev("barrier", 60)]
        first = evaluate(dry_profile(), evaluations)
        second = evaluate(dry_profile(), list(reversed(evaluations)))
        self.assertEqual(first.input_hash, second.input_hash)
        self.assertEqual(first.as_dict(), second.as_dict())

    def test_different_values_change_hash(self):
        first = evaluate(dry_profile(), [ev("hydration", 70), ev("barrier", 60)])
        second = evaluate(dry_profile(), [ev("hydration", 71), ev("barrier", 60)])
        self.assertNotEqual(first.input_hash, second.input_hash)

    def test_duplicate_evaluations_are_rejected(self):
        with self.assertRaises(ContractError):
            evaluate(dry_profile(), [ev("hydration", 70), ev("hydration", 80)])

    def test_value_outside_scale_is_rejected(self):
        with self.assertRaises(ContractError):
            ev("hydration", 101)

    def test_value_requires_evaluated_status(self):
        with self.assertRaises(ContractError):
            ev("hydration", 50, status="stale")

    def test_min_confidence_excludes_unknown_confidence(self):
        rules = RuleSet(
            version="9.9.9-conf",
            aggregation="weighted_mean",
            completeness_threshold=0.5,
            verdict_bands=((0, "low"),),
            calibrated=False,
            min_confidence=0.5,
        )
        result = evaluate(
            {"skin_type": "dry"},
            [
                ev("hydration", 80),  # confidence is None
                ev("barrier", 60, confidence=0.9),
            ],
            rules,
        )
        hydration = next(item for item in result.parameters if item.parameter_id == "hydration")
        self.assertFalse(hydration.included)
        self.assertEqual(hydration.status, "insufficient_evidence")

class FreshnessTests(unittest.TestCase):
    def test_composition_change_invalidates(self):
        evaluation = ev("hydration", 70)
        reason = stale_reason(evaluation, composition_hash="b" * 64, method_version=METHOD)
        self.assertIn("состав", reason)
        self.assertFalse(is_current(evaluation, composition_hash="b" * 64, method_version=METHOD))

    def test_method_version_change_invalidates(self):
        evaluation = ev("hydration", 70)
        reason = stale_reason(evaluation, composition_hash=COMPOSITION, method_version="research-2.0.0")
        self.assertIn("методик", reason)

    def test_expired_valid_until_invalidates(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        evaluation = ev("hydration", 70, valid_until=past)
        self.assertIn(
            "valid_until",
            stale_reason(evaluation, composition_hash=COMPOSITION, method_version=METHOD),
        )

    def test_future_valid_until_stays_current(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        evaluation = ev("hydration", 70, valid_until=future)
        self.assertIsNone(
            stale_reason(evaluation, composition_hash=COMPOSITION, method_version=METHOD)
        )

    def test_invalid_valid_until_is_treated_as_stale(self):
        evaluation = ev("hydration", 70, valid_until="not-a-date")
        reason = stale_reason(evaluation, composition_hash=COMPOSITION, method_version=METHOD)
        self.assertIn("valid_until", reason)


class SnapshotTests(unittest.TestCase):
    def _snapshot(self):
        evaluations = [ev("hydration", 80), ev("barrier", 60)]
        result = evaluate(dry_profile(), evaluations)
        return build_snapshot(
            product={"id": 42, "name": "Test Cream"},
            composition={
                "composition_hash": COMPOSITION,
                "source": "catalog",
                "verified_at": "2026-10-20",
            },
            profile={"skin_type": "dry", "allergies": ["fragrance"]},
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
        self.assertEqual(snapshot["profile"]["allergy_count"], 1)

    def test_snapshot_tampering_is_detected(self):
        snapshot = self._snapshot()
        snapshot["total"] = 99
        self.assertFalse(verify_snapshot(snapshot))

    def test_snapshot_rejects_foreign_composition(self):
        evaluations = [ev("hydration", 80, composition_hash="c" * 64)]
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
