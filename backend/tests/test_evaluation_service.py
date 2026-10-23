"""Service + store tests for evaluation v2 (no database, no AI)."""
from __future__ import annotations

import unittest

from app.evaluation import ParameterEvaluation, RuleSet
from app.evaluation.service import EvaluationService
from app.evaluation.store import StoreError, InMemoryStore

COMP_A = "a" * 64
COMP_B = "b" * 64
PRODUCT = {"id": 7, "name": "Test Serum"}
PROFILE = {"skin_type": "dry", "concerns": ["dryness"]}


def ev(
    parameter_id: str,
    value: float | None,
    status: str = "assessed",
    composition=COMP_A,
    **kwargs,
):
    if status == "assessed":
        kwargs.setdefault("rationale", f"{parameter_id}: оценка по подтверждённым источникам")
        kwargs.setdefault("evidence_ids", ("1",))
    return ParameterEvaluation(
        parameter_id=parameter_id,
        status=status,
        value=value,
        composition_hash=composition,
        method_version=kwargs.pop("method_version", "research-1.0.0-draft"),
        **kwargs,
    )


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.service = EvaluationService(self.store)

    def _composition(self, comp_hash=COMP_A):
        return {"composition_hash": comp_hash, "source": "catalog", "verified_at": "2026-10-20"}

    def _composition_id(self, comp_hash=COMP_A):
        record = self.service.ensure_composition(7, self._composition(comp_hash))
        return record["id"]

    def test_first_build_reports_pending_parameters(self):
        result = self.service.build(
            product=PRODUCT, composition=self._composition(), profile=PROFILE
        )
        self.assertEqual(result.pending_parameters, ("problem:dryness", "skin_type:dry"))
        self.assertIsNone(result.snapshot["total"])
        self.assertFalse(result.reused)
        self.assertEqual(self.store.snapshot_count(), 1)

    def test_repeated_build_reuses_snapshot(self):
        first = self.service.build(product=PRODUCT, composition=self._composition(), profile=PROFILE)
        second = self.service.build(product=PRODUCT, composition=self._composition(), profile=PROFILE)
        self.assertTrue(second.reused)
        self.assertEqual(first.snapshot["snapshot_id"], second.snapshot["snapshot_id"])
        self.assertEqual(self.store.snapshot_count(), 1)

    def test_total_appears_when_all_relevant_parameters_are_evaluated(self):
        composition_id = self._composition_id()
        self.service.record_evaluation(composition_id, ev("problem:dryness", 100))
        self.service.record_evaluation(composition_id, ev("skin_type:dry", 50))
        result = self.service.build(
            product=PRODUCT, composition=self._composition(), profile=PROFILE
        )
        self.assertEqual(result.snapshot["total"], 75)
        self.assertEqual(result.pending_parameters, ())
        self.assertAlmostEqual(result.snapshot["completeness"], 1.0, places=6)

    def test_new_evaluation_supersedes_old_one_but_history_is_kept(self):
        composition_id = self._composition_id()
        self.service.record_evaluation(composition_id, ev("problem:dryness", 25))
        self.service.record_evaluation(composition_id, ev("problem:dryness", 100))
        current = self.store.current_evaluations(composition_id, "research-1.0.0-draft")
        hydration = next(item for item in current if item.parameter_id == "problem:dryness")
        self.assertEqual(hydration.value, 100)
        self.assertEqual(len(self.store.evaluation_history(composition_id, "problem:dryness")), 2)

    def test_composition_change_invalidates_saved_evaluations(self):
        composition_id = self._composition_id(COMP_A)
        self.service.record_evaluation(composition_id, ev("problem:dryness", 100))
        result = self.service.build(
            product=PRODUCT, composition=self._composition(COMP_B), profile=PROFILE
        )
        self.assertIn("problem:dryness", result.pending_parameters)
        self.assertIsNone(result.snapshot["total"])
        self.assertEqual(result.snapshot["composition"]["hash"], COMP_B)

    def test_insufficient_evidence_is_not_requested_again(self):
        strict = RuleSet(
            version="test-strict",
            aggregation="arithmetic_mean",
            completeness_threshold=0.9,
            verdict_bands=((0, "low"),),
            calibrated=False,
        )
        service = EvaluationService(self.store, rules=strict)
        composition_id = self._composition_id()
        service.record_evaluation(
            composition_id, ev("problem:dryness", None, status="insufficient_evidence")
        )
        service.record_evaluation(composition_id, ev("skin_type:dry", 50))
        result = service.build(
            product=PRODUCT, composition=self._composition(), profile=PROFILE
        )
        # The stored insufficient result is reused: no new research is requested,
        # and it never becomes a score (the remaining assessed parameter is used).
        self.assertEqual(result.pending_parameters, ())
        self.assertEqual(result.snapshot["total"], 50)
        self.assertEqual(
            [item["parameter_id"] for item in result.snapshot["parameters"]],
            ["skin_type:dry"],
        )

    def test_non_assessed_results_are_kept_in_storage_but_not_in_the_report(self):
        composition_id = self._composition_id()
        self.service.record_evaluation(composition_id, ev("problem:dryness", 100))
        self.service.record_evaluation(
            composition_id,
            ev(
                "skin_type:dry",
                None,
                status="not_applicable",
                rationale="Параметр не применяется к этому формату продукта.",
            ),
        )
        result = self.service.build(
            product=PRODUCT, composition=self._composition(), profile=PROFILE
        )
        reported = [item["parameter_id"] for item in result.snapshot["parameters"]]
        self.assertEqual(reported, ["problem:dryness"])
        self.assertEqual(result.snapshot["total"], 100)

        stored = {
            item.parameter_id: item
            for item in self.store.current_evaluations(composition_id, "research-1.0.0-draft")
        }
        self.assertEqual(stored["skin_type:dry"].status, "not_applicable")
        self.assertIsNone(stored["skin_type:dry"].value)
        self.assertTrue(stored["skin_type:dry"].rationale)

    def test_research_jobs_are_deduplicated(self):
        composition_id = self._composition_id()
        first = self.service.enqueue_research(composition_id, ["problem:dryness", "skin_type:dry"])
        second = self.service.enqueue_research(composition_id, ["problem:dryness"])
        self.assertEqual(first, ["problem:dryness", "skin_type:dry"])
        self.assertEqual(second, [])
        self.assertEqual(self.store.job_count(), 2)

    def test_snapshot_integrity_is_checked_on_read(self):
        result = self.service.build(product=PRODUCT, composition=self._composition(), profile=PROFILE)
        snapshot_id = result.snapshot["snapshot_id"]
        self.store._snapshots[snapshot_id]["total"] = 99
        with self.assertRaises(StoreError):
            self.service.snapshot(snapshot_id)

    def test_method_version_mismatch_is_rejected(self):
        composition_id = self._composition_id()
        with self.assertRaises(StoreError):
            self.service.record_evaluation(
                composition_id, ev("problem:dryness", 75, method_version="other-method")
            )

    def test_relevance_fingerprint_is_stable(self):
        first = self.service.relevance_fingerprint(PROFILE)
        second = self.service.relevance_fingerprint({"skin_type": "dry", "concerns": ["dryness"]})
        self.assertEqual(first["hash"], second["hash"])
        self.assertIn("problem:dryness", first["weights"])


if __name__ == "__main__":
    unittest.main()
