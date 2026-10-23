"""Research orchestration tests. Fake provider only: no network, no paid calls."""
from __future__ import annotations

import threading
import unittest
from datetime import datetime, timedelta, timezone

from app.evaluation import (
    NOT_APPLICABLE,
    FakeResearchProvider,
    ParameterEvaluation,
    ResearchService,
    ParameterEvaluation as PE,
    candidate,
    evaluate,
    get_rules,
    build_snapshot,
    insufficient,
    ok,
    provider_error,
    source_unavailable,
)
from app.evaluation.service import DEFAULT_METHOD_VERSION, EvaluationService
from app.evaluation.store import InMemoryStore

PRODUCT = {"id": 7, "name": "Serum"}
COMP_A = "a" * 64
COMP_B = "b" * 64
PROFILE = {"skin_type": "dry", "concerns": ["dryness"]}  # two questionnaire answers


def composition(comp_hash: str = COMP_A) -> dict:
    return {
        "composition_hash": comp_hash,
        "inci_raw": "Aqua, Glycerin",
        "source": "catalog",
        "verified_at": "2026-10-20",
    }


def evidence_ok(
    parameter_id: str,
    *,
    strength: str = "moderate",
    cost: float = 0.0,
    score: int | None = 75,
    **kwargs,
):
    kwargs.setdefault("confidence", 1.0)
    return ok(
        candidate(
            parameter_id=parameter_id,
            claim=f"{parameter_id}: подтверждённое свойство",
            quote=f"{parameter_id} confirmed property",
            source_text=f"Formula. {parameter_id} confirmed property. End.",
            strength=strength,
            **kwargs,
        ),
        score=score,
        cost_usd=cost,
    )

class ResearchFlowTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.provider = FakeResearchProvider(
            {
                "problem:dryness": evidence_ok("problem:dryness", strength="strong"),
                "skin_type:dry": evidence_ok("skin_type:dry", strength="moderate"),
            }
        )
        self.service = ResearchService(self.store, self.provider, allow_synthetic_evidence=True)

    def _run(self, comp: str = COMP_A, profile=PROFILE, **kwargs):
        return self.service.research_missing(
            product=PRODUCT,
            composition=composition(comp),
            profile=profile,
            **kwargs,
        )

    def _composition_id(self, comp: str = COMP_A) -> int:
        record = self.store.get_composition(PRODUCT["id"], comp)
        self.assertIsNotNone(record, "composition must exist after research")
        return int(record["id"])

    def test_research_creates_evaluations_and_evidence(self):
        report = self._run()
        self.assertEqual(report.researched, ("problem:dryness", "skin_type:dry"))
        self.assertEqual(self.provider.call_count(), 2)

        composition_id = self._composition_id()
        current = {
            item.parameter_id: item
            for item in self.store.current_evaluations(composition_id, DEFAULT_METHOD_VERSION)
        }
        self.assertEqual(current["problem:dryness"].value, 75)
        self.assertEqual(current["skin_type:dry"].value, 75)
        self.assertTrue(current["problem:dryness"].evidence_ids)

        rows = self.store.evidence_for(composition_id, "problem:dryness")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verification"], "confirmed")
        self.assertEqual(rows[0]["composition_id"], composition_id)
        self.assertEqual(rows[0]["parameter_id"], "problem:dryness")

    def test_second_run_reuses_evaluations_without_provider_calls(self):
        self._run()
        calls = self.provider.call_count()
        report = self._run()
        self.assertEqual(self.provider.call_count(), calls)
        self.assertEqual(report.researched, ())
        self.assertEqual(report.enqueued, ())

    def test_existing_current_evaluation_skips_research(self):
        record = self.store.upsert_composition(
            {"product_id": PRODUCT["id"], "composition_hash": COMP_A}
        )
        for parameter_id in ("problem:dryness", "skin_type:dry"):
            self.store.save_evaluation(
                record["id"],
                ParameterEvaluation(
                    parameter_id=parameter_id,
                    status="evaluated",
                    value=70,
                    composition_hash=COMP_A,
                    method_version=DEFAULT_METHOD_VERSION,
                ),
            )
        report = self._run()
        self.assertEqual(self.provider.call_count(), 0)
        self.assertEqual(report.enqueued, ())

    def test_research_request_carries_product_and_composition(self):
        self._run()
        request = self.provider.calls[0]
        self.assertEqual(request.product_id, PRODUCT["id"])
        self.assertEqual(request.product_name, PRODUCT["name"])
        self.assertEqual(request.composition_hash, COMP_A)
        self.assertEqual(request.ingredients, ("Aqua", "Glycerin"))

class ResearchFailureTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()

    def _service(self, provider, **kwargs):
        return ResearchService(self.store, provider, allow_synthetic_evidence=True, **kwargs)

    def _run(self, service, **kwargs):
        return service.research_missing(
            product=PRODUCT, composition=composition(), profile=PROFILE, **kwargs
        )

    def _composition_id(self) -> int:
        return int(self.store.get_composition(PRODUCT["id"], COMP_A)["id"])

    def test_provider_error_leaves_no_success_state(self):
        provider = FakeResearchProvider(default=provider_error("timeout"))
        service = self._service(provider)
        report = self._run(service)
        self.assertEqual(report.failed, ("problem:dryness", "skin_type:dry"))
        composition_id = self._composition_id()
        self.assertEqual(self.store.current_evaluations(composition_id, DEFAULT_METHOD_VERSION), [])
        jobs = self.store.jobs_for(composition_id, "problem:dryness", DEFAULT_METHOD_VERSION)
        self.assertEqual(jobs[0]["status"], "failed")
        self.assertIn("timeout", jobs[0]["last_error"])

    def test_retry_after_failure_can_succeed(self):
        provider = FakeResearchProvider(default=provider_error("timeout"))
        service = self._service(provider)
        self._run(service)
        provider.set_response("problem:dryness", evidence_ok("problem:dryness", strength="strong"))
        provider.set_response("skin_type:dry", evidence_ok("skin_type:dry"))
        report = self._run(service)
        self.assertEqual(report.researched, ("problem:dryness", "skin_type:dry"))
        composition_id = self._composition_id()
        jobs = self.store.jobs_for(composition_id, "problem:dryness", DEFAULT_METHOD_VERSION)
        self.assertEqual([job["status"] for job in jobs], ["failed", "completed"])

    def test_source_unavailable_is_retryable_failure(self):
        provider = FakeResearchProvider(default=source_unavailable("404"))
        service = self._service(provider)
        self._run(service)
        composition_id = self._composition_id()
        jobs = self.store.jobs_for(composition_id, "skin_type:dry", DEFAULT_METHOD_VERSION)
        self.assertEqual(jobs[0]["status"], "failed")
        self.assertIn("источник недоступен", jobs[0]["last_error"])

    def test_all_candidates_rejected_is_a_failure(self):
        bad = ok(
            candidate(
                parameter_id="problem:dryness",
                claim="Выдуманное свойство",
                quote="this sentence is not in the source",
                source_text="Formula: Aqua, Glycerin.",
            )
        )
        provider = FakeResearchProvider(default=bad)
        service = self._service(provider)
        report = self._run(service)
        self.assertEqual(report.failed, ("problem:dryness", "skin_type:dry"))
        composition_id = self._composition_id()
        self.assertEqual(self.store.current_evaluations(composition_id, DEFAULT_METHOD_VERSION), [])
        rows = self.store.evidence_for(composition_id, "problem:dryness")
        self.assertEqual(rows[0]["verification"], "rejected")
        self.assertTrue(rows[0]["rejection_reason"])

class ResearchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()

    def _run(self, service):
        return service.research_missing(
            product=PRODUCT, composition=composition(), profile=PROFILE
        )

    def test_cost_limit_per_job_fails_without_evaluation(self):
        expensive = ok(
            candidate(
                parameter_id="problem:dryness",
                claim="Подтверждённое свойство",
                quote="confirmed property",
                source_text="Formula. confirmed property.",
            ),
            cost_usd=1.0,
        )
        provider = FakeResearchProvider(default=expensive)
        service = ResearchService(self.store, provider, max_cost_per_job=0.1, allow_synthetic_evidence=True)
        report = self._run(service)
        self.assertEqual(report.failed, ("problem:dryness", "skin_type:dry"))
        self.assertEqual(report.cost_usd, 2.0)
        composition_id = int(self.store.get_composition(PRODUCT["id"], COMP_A)["id"])
        self.assertEqual(
            self.store.current_evaluations(composition_id, DEFAULT_METHOD_VERSION), []
        )
        jobs = self.store.jobs_for(composition_id, "problem:dryness", DEFAULT_METHOD_VERSION)
        self.assertIn("лимит стоимости", jobs[0]["last_error"])

    def test_run_budget_defers_remaining_jobs(self):
        provider = FakeResearchProvider(
            {
                "problem:dryness": evidence_ok("problem:dryness", cost=0.4),
                "skin_type:dry": evidence_ok("skin_type:dry", cost=0.4),
            }
        )
        service = ResearchService(
            self.store, provider, max_cost_per_job=1.0, max_cost_per_run=0.3,
            allow_synthetic_evidence=True,
        )
        report = self._run(service)
        self.assertEqual(report.researched, ("problem:dryness",))
        self.assertEqual(report.deferred, ("skin_type:dry",))
        composition_id = int(self.store.get_composition(PRODUCT["id"], COMP_A)["id"])
        jobs = self.store.jobs_for(composition_id, "skin_type:dry", DEFAULT_METHOD_VERSION)
        self.assertEqual(jobs[0]["status"], "pending")

    def test_max_attempts_stops_retries(self):
        provider = FakeResearchProvider(default=provider_error("timeout"))
        service = ResearchService(self.store, provider, max_attempts=1, allow_synthetic_evidence=True)
        self._run(service)
        calls = provider.call_count()
        report = self._run(service)
        self.assertEqual(report.exhausted, ("problem:dryness", "skin_type:dry"))
        self.assertEqual(provider.call_count(), calls)
        self.assertTrue(any("лимит попыток" in note for note in report.notes))


class ResearchFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.provider = FakeResearchProvider(
            {"problem:dryness": evidence_ok("problem:dryness"), "skin_type:dry": evidence_ok("skin_type:dry")}
        )
        self.service = ResearchService(self.store, self.provider, allow_synthetic_evidence=True)

    def test_composition_change_requires_new_research(self):
        self.service.research_missing(
            product=PRODUCT, composition=composition(COMP_A), profile=PROFILE
        )
        calls_after_a = self.provider.call_count()
        report = self.service.research_missing(
            product=PRODUCT, composition=composition(COMP_B), profile=PROFILE
        )
        self.assertEqual(report.researched, ("problem:dryness", "skin_type:dry"))
        self.assertEqual(self.provider.call_count(), calls_after_a + 2)

    def test_old_method_version_requires_new_research(self):
        record = self.store.upsert_composition(
            {
                "product_id": PRODUCT["id"],
                "composition_hash": COMP_A,
                "source": "catalog",
                "verified_at": "2026-10-20",
            }
        )
        for parameter_id in ("problem:dryness", "skin_type:dry"):
            self.store.save_evaluation(
                record["id"],
                ParameterEvaluation(
                    parameter_id=parameter_id,
                    status="evaluated",
                    value=70,
                    composition_hash=COMP_A,
                    method_version="research-0.9.0",
                ),
            )
        report = self.service.research_missing(
            product=PRODUCT, composition=composition(COMP_A), profile=PROFILE
        )
        self.assertEqual(report.researched, ("problem:dryness", "skin_type:dry"))

class ResearchConcurrencyTests(unittest.TestCase):
    def test_parallel_workers_call_provider_once_per_parameter(self):
        store = InMemoryStore()
        provider = FakeResearchProvider(
            {"problem:dryness": evidence_ok("problem:dryness"), "skin_type:dry": evidence_ok("skin_type:dry")}
        )
        service = ResearchService(store, provider, allow_synthetic_evidence=True)
        barrier = threading.Barrier(2)
        reports = []

        def worker(name: str) -> None:
            barrier.wait()
            reports.append(
                service.research_missing(
                    product=PRODUCT,
                    composition=composition(),
                    profile=PROFILE,
                    worker_id=name,
                )
            )

        threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(provider.call_count(), 2, provider.calls)
        composition_id = int(store.get_composition(PRODUCT["id"], COMP_A)["id"])
        self.assertEqual(
            len(store.current_evaluations(composition_id, DEFAULT_METHOD_VERSION)), 2
        )
        researched = sorted(item for report in reports for item in report.researched)
        self.assertEqual(researched, ["problem:dryness", "skin_type:dry"])


class ResearchEngineIntegrationTests(unittest.TestCase):
    def test_researched_values_feed_arithmetic_mean_without_verdict(self):
        store = InMemoryStore()
        provider = FakeResearchProvider(
            {
                "problem:dryness": evidence_ok("problem:dryness", strength="strong"),
                "skin_type:dry": evidence_ok("skin_type:dry", strength="moderate"),
            }
        )
        ResearchService(store, provider, allow_synthetic_evidence=True).research_missing(
            product=PRODUCT, composition=composition(), profile=PROFILE
        )
        record = store.get_composition(PRODUCT["id"], COMP_A)
        evaluations = store.current_evaluations(record["id"], DEFAULT_METHOD_VERSION)
        result = evaluate(PROFILE, evaluations)
        self.assertEqual(result.total, 75)
        self.assertIsNone(result.verdict)
        self.assertAlmostEqual(result.completeness, 1.0, places=6)

        snapshot = build_snapshot(
            product=PRODUCT,
            composition=record,
            profile=PROFILE,
            evaluations=evaluations,
            result=result,
            rules=get_rules(),
        )
        self.assertEqual(snapshot["total"], 75)
        self.assertIsNone(snapshot["verdict"])


class ResearchStatusTests(unittest.TestCase):
    """Applicability / sufficiency / technical failures are distinct."""

    def setUp(self):
        self.store = InMemoryStore()

    def _run(self, responses, profile=PROFILE):
        provider = FakeResearchProvider(responses)
        service = ResearchService(self.store, provider, allow_synthetic_evidence=True)
        return service, provider, service.research_missing(
            product=PRODUCT, composition=composition(), profile=profile
        )

    def _evaluations(self, comp: str = COMP_A) -> dict:
        record = self.store.get_composition(PRODUCT["id"], comp)
        return {
            item.parameter_id: item
            for item in self.store.current_evaluations(record["id"], DEFAULT_METHOD_VERSION)
        }

    def test_provider_without_sources_is_stored_as_insufficient_without_score(self):
        _, _, report = self._run(
            {
                "problem:dryness": insufficient(),
                "skin_type:dry": insufficient(),
            }
        )
        self.assertEqual(report.insufficient, ("problem:dryness", "skin_type:dry"))
        evaluations = self._evaluations()
        for evaluation in evaluations.values():
            self.assertEqual(evaluation.status, "insufficient_evidence")
            self.assertIsNone(evaluation.value)

    def test_not_applicable_is_stored_without_score(self):
        _, _, report = self._run(
            {
                "problem:dryness": ok(
                    candidate(
                        parameter_id="problem:dryness",
                        claim="Продукт смывается водой",
                        quote="rinse-off cleanser",
                        source_text="This is a rinse-off cleanser.",
                    ),
                    applicability=NOT_APPLICABLE,
                    applicability_reason="Средство смывается и не остаётся на коже.",
                ),
                "skin_type:dry": evidence_ok("skin_type:dry", score=100),
            }
        )
        self.assertEqual(report.not_applicable, ("problem:dryness",))
        self.assertEqual(report.researched, ("skin_type:dry",))
        evaluations = self._evaluations()
        self.assertEqual(evaluations["problem:dryness"].status, "not_applicable")
        self.assertIsNone(evaluations["problem:dryness"].value)

        result = evaluate(PROFILE, list(evaluations.values()))
        self.assertEqual(result.total, 100)  # not_applicable does not lower the mean
        self.assertAlmostEqual(result.completeness, 0.5, places=6)

    def test_invalid_score_fails_the_job_instead_of_being_stored(self):
        provider_response = evidence_ok("problem:dryness", score=30)
        _, provider, report = self._run(
            {"problem:dryness": provider_response, "skin_type:dry": insufficient()}
        )
        self.assertIn("problem:dryness", report.failed)
        self.assertEqual(self._evaluations().get("problem:dryness"), None)
        record = self.store.get_composition(PRODUCT["id"], COMP_A)
        jobs = self.store.jobs_for(record["id"], "problem:dryness", DEFAULT_METHOD_VERSION)
        self.assertEqual(jobs[0]["status"], "failed")
        self.assertIn("некорректный результат оценки", jobs[0]["last_error"])

    def test_provider_error_is_not_masked_as_not_applicable(self):
        _, _, report = self._run(
            {"problem:dryness": provider_error(), "skin_type:dry": evidence_ok("skin_type:dry")}
        )
        self.assertEqual(report.failed, ("problem:dryness",))
        self.assertEqual(report.not_applicable, ())
        self.assertNotIn("problem:dryness", self._evaluations())

    def test_not_applicable_is_revisited_only_when_stale(self):
        responses = {
            "problem:dryness": ok(
                candidate(
                    parameter_id="problem:dryness",
                    claim="Продукт смывается водой",
                    quote="rinse-off cleanser",
                    source_text="This is a rinse-off cleanser.",
                ),
                applicability=NOT_APPLICABLE,
                applicability_reason="Средство смывается.",
            ),
            "skin_type:dry": evidence_ok("skin_type:dry"),
        }
        service, provider, _ = self._run(responses)
        calls = provider.call_count()
        report = service.research_missing(
            product=PRODUCT, composition=composition(), profile=PROFILE
        )
        self.assertEqual(provider.call_count(), calls)
        self.assertEqual(report.researched, ())
        self.assertEqual(report.not_applicable, ())


class ResearchReviewWindowTests(unittest.TestCase):
    """Non-scoring results are only cached for the review window."""

    OLD = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    RECENT = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    def _store(self, status: str, age: str) -> InMemoryStore:
        store = InMemoryStore()
        record = store.upsert_composition({**composition(), "product_id": PRODUCT["id"]})
        value = 75 if status == "assessed" else None
        for parameter_id in ("problem:dryness", "skin_type:dry"):
            store.save_evaluation(
                int(record["id"]),
                ParameterEvaluation(
                    parameter_id=parameter_id,
                    status=status,
                    value=value,
                    composition_hash=COMP_A,
                    method_version=DEFAULT_METHOD_VERSION,
                    rationale="Сохранённый результат предыдущего запуска.",
                    evidence_ids=("1",) if status == "assessed" else (),
                    evaluated_at=age,
                ),
            )
        return store

    def _run(self, store: InMemoryStore):
        provider = FakeResearchProvider(
            {
                "problem:dryness": insufficient(),
                "skin_type:dry": insufficient(),
            }
        )
        service = ResearchService(store, provider, allow_synthetic_evidence=True)
        report = service.research_missing(
            product=PRODUCT, composition=composition(), profile=PROFILE
        )
        return provider, report

    def test_old_insufficient_results_are_researched_again(self):
        provider, report = self._run(self._store("insufficient_evidence", self.OLD))
        self.assertEqual(report.insufficient, ("problem:dryness", "skin_type:dry"))
        self.assertEqual(provider.call_count(), 2)

    def test_old_not_applicable_results_are_researched_again(self):
        provider, report = self._run(self._store("not_applicable", self.OLD))
        self.assertEqual(report.insufficient, ("problem:dryness", "skin_type:dry"))
        self.assertEqual(provider.call_count(), 2)

    def test_recent_insufficient_is_still_a_gap(self):
        # "Not enough evidence" is not knowledge to reuse, even inside the review
        # window: the parameter stays a research candidate.
        provider, report = self._run(self._store("insufficient_evidence", self.RECENT))
        self.assertEqual(provider.call_count(), 2)

    def test_recent_not_applicable_is_reused(self):
        provider, report = self._run(self._store("not_applicable", self.RECENT))
        self.assertEqual(report.researched, ())
        self.assertEqual(provider.call_count(), 0)

    def test_assessed_result_is_reused_regardless_of_age(self):
        old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        provider, report = self._run(self._store("assessed", old))
        self.assertEqual(report.researched, ())
        self.assertEqual(provider.call_count(), 0)

    def test_window_can_be_disabled_explicitly(self):
        store = self._store("not_applicable", self.OLD)
        provider = FakeResearchProvider(
            {"problem:dryness": insufficient(), "skin_type:dry": insufficient()}
        )
        service = ResearchService(
            store, provider, allow_synthetic_evidence=True, review_after_days=None
        )
        report = service.research_missing(
            product=PRODUCT, composition=composition(), profile=PROFILE
        )
        self.assertEqual(report.researched, ())
        self.assertEqual(provider.call_count(), 0)


if __name__ == "__main__":
    unittest.main()
