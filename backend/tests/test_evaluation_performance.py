"""Reproducible performance/regression checks for the evaluation hot path.

The provider and fetcher sleep on purpose: these tests measure orchestration
overhead, not an external service. No network and no paid calls are used.
"""
from __future__ import annotations

import threading
import time
import unittest

from app.evaluation.analysis import AnalysisService
from app.evaluation.contracts import ParameterEvaluation
from app.evaluation.documents import FakeDocumentFetcher
from app.evaluation.parameters import resolve_parameters
from app.evaluation.research import candidate, ok
from app.evaluation.service import DEFAULT_METHOD_VERSION, EvaluationService
from app.evaluation.store import InMemoryStore

PRODUCT = {"id": 99, "name": "Perf Serum", "brand": "Brand"}
COMPOSITION = {
    "composition_hash": "c" * 64,
    "inci_raw": "Aqua, Glycerin",
    "source": "https://brand.example/perf-serum",
    "verified_at": "2026-10-20",
}
URL = "https://brand.example/perf-serum"
PAGE = (
    "Formula Aqua Glycerin. Glycerin helps keep the skin hydrated. "
    "The formula is suitable for dry skin. End."
)
PROFILE = {"skin_type": "dry", "concerns": ["dryness"]}
QUOTE = "Glycerin helps keep the skin hydrated"
PARAMETERS = tuple(item.id for item in resolve_parameters(PROFILE).parameters)


class CountingStore(InMemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.counts: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def current_evaluations(self, *args, **kwargs):
        self._count("current_evaluations")
        return super().current_evaluations(*args, **kwargs)

    def evidence_for_many(self, *args, **kwargs):
        self._count("evidence_for_many")
        return super().evidence_for_many(*args, **kwargs)

    def claim_job(self, *args, **kwargs):
        self._count("claim_job")
        return super().claim_job(*args, **kwargs)

    def save_snapshot(self, *args, **kwargs):
        self._count("save_snapshot")
        return super().save_snapshot(*args, **kwargs)

    def save_documents(self, *args, **kwargs):
        self._count("save_documents")
        return super().save_documents(*args, **kwargs)


class SleepingProvider:
    def __init__(self, delay: float = 0.0, *, barrier: int | None = None) -> None:
        self.delay = delay
        self.calls: list[str] = []
        self._barrier = threading.Barrier(barrier, timeout=3) if barrier else None

    def research(self, request):
        self.calls.append(request.parameter_id)
        if self._barrier is not None:
            self._barrier.wait()
        if self.delay:
            time.sleep(self.delay)
        document = request.documents[0]
        return ok(
            candidate(
                parameter_id=request.parameter_id,
                claim="подтверждено источником",
                quote=QUOTE,
                url=document.url,
                source_text=document.text,
                retrieved_at=document.retrieved_at,
                provenance=document.provenance,
            ),
            score=75,
        )


class FailingProvider:
    def research(self, request):
        raise AssertionError(f"unexpected research call: {request.parameter_id}")


class EvaluationPerformanceTests(unittest.TestCase):
    def _service(self, store, provider, *, concurrency: int = 4) -> AnalysisService:
        return AnalysisService(
            store,
            provider=provider,
            fetcher=FakeDocumentFetcher({URL: PAGE}),
            allow_synthetic_evidence=True,
            max_concurrency=concurrency,
        )

    def _run(self, service):
        return service.analyze(
            product=PRODUCT,
            composition=COMPOSITION,
            profile=PROFILE,
            source_urls=(URL,),
            user_id=1,
        )

    def test_first_analysis_runs_independent_provider_calls_in_parallel(self):
        store = CountingStore()
        provider = SleepingProvider(delay=0.12, barrier=len(PARAMETERS))
        started = time.perf_counter()
        report = self._run(self._service(store, provider, concurrency=len(PARAMETERS)))
        elapsed = time.perf_counter() - started

        self.assertEqual(len(provider.calls), len(PARAMETERS))
        self.assertEqual(report.research.researched, PARAMETERS)
        self.assertEqual(len(report.analysis.assessed_parameters), len(PARAMETERS))
        # Sequential calls would take at least PARAMETERS * delay; the barrier
        # would break too. This catches accidental serialization regressions.
        self.assertLess(elapsed, 0.75)
        self.assertLess(report.timings["total_ms"], 750)
        self.assertEqual(store.counts.get("save_snapshot"), 1)
        self.assertEqual(store.counts.get("evidence_for_many"), 1)

    def test_cached_recheck_reuses_snapshot_and_never_calls_provider(self):
        store = CountingStore()
        first = self._run(self._service(store, SleepingProvider()))
        snapshots = store.snapshot_count()
        before = dict(store.counts)
        started = time.perf_counter()
        second = self._run(self._service(store, FailingProvider()))
        elapsed = time.perf_counter() - started

        self.assertEqual(second.snapshot["snapshot_id"], first.snapshot["snapshot_id"])
        self.assertEqual(store.snapshot_count(), snapshots)
        self.assertEqual(store.counts.get("save_snapshot", 0), 1)
        self.assertFalse(second.research)
        self.assertLess(elapsed, 0.5)
        self.assertLess(second.timings["total_ms"], 500)
        self.assertEqual(second.timings["needed"], 0)
        for name in ("claim_job", "save_snapshot", "save_documents"):
            self.assertEqual(store.counts.get(name, 0), before.get(name, 0), name)

    def test_partial_results_only_research_the_missing_parameter(self):
        store = CountingStore()
        service = EvaluationService(store)
        first_parameter = PARAMETERS[0]
        record = service.ensure_composition(PRODUCT["id"], COMPOSITION)
        service.record_evaluation(
            record["id"],
            ParameterEvaluation(
                parameter_id=first_parameter,
                status="assessed",
                value=75,
                composition_hash=COMPOSITION["composition_hash"],
                method_version=DEFAULT_METHOD_VERSION,
                evidence_ids=(1,),
                rationale="already assessed",
            ),
        )
        provider = SleepingProvider()
        report = self._run(self._service(store, provider))

        self.assertEqual(provider.calls, [PARAMETERS[1]])
        self.assertEqual(report.research.researched, (PARAMETERS[1],))
        self.assertEqual(
            sorted(report.analysis.assessed_parameters), sorted(PARAMETERS)
        )
        self.assertEqual(store.counts.get("evidence_for_many"), 1)


if __name__ == "__main__":
    unittest.main()
