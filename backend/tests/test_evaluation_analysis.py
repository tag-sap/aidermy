"""End-to-end analysis mechanic: scan -> shared research -> per-parameter results."""
from __future__ import annotations

import unittest

from app.evaluation.analysis import AnalysisService
from app.evaluation.documents import DocumentLibrary, FakeDocumentFetcher, SourceDocument
from app.evaluation.evidence import validate_candidates
from app.evaluation.research import (
    ResearchOutcome,
    candidate,
    insufficient,
    ok,
)
from app.evaluation.research_service import ResearchService
from app.evaluation.store import InMemoryStore

PRODUCT = {"id": 7, "name": "Serum"}
COMPOSITION = {
    "composition_hash": "a" * 64,
    "inci_raw": "Aqua, Glycerin, Niacinamide",
    "source": "https://brand.example/serum",
    "verified_at": "2026-10-20",
}
PROFILE = {"skin_type": "dry", "concerns": ["dryness"]}
URL = "https://brand.example/serum"
PAGE_TEXT = (
    "Ingredient list: Aqua, Glycerin, Niacinamide. Glycerin helps keep the skin "
    "hydrated and supports the skin barrier. The formula is suitable for dry skin "
    "and can be used twice daily."
)
QUOTES = {
    "problem:dryness": "Glycerin helps keep the skin hydrated",
    "skin_type:dry": "suitable for dry skin",
}


class DocumentProvider:
    """Provider that only answers from the documents it receives."""

    name = "document-fake"

    def __init__(self, scores=None, insufficient_for=()):
        self.calls = []
        self.scores = dict(scores or {"problem:dryness": 75, "skin_type:dry": 100})
        self.insufficient_for = set(insufficient_for)

    def research(self, request):
        self.calls.append(request)
        if request.parameter_id in self.insufficient_for:
            return insufficient("в источнике нет ответа")
        if not request.documents:
            return insufficient("нет источников")
        document = request.documents[0]
        return ok(
            candidate(
                parameter_id=request.parameter_id,
                claim=f"{request.parameter_label}: подтверждено источником",
                quote=QUOTES[request.parameter_id],
                url=document.url,
                source_text=document.text,
                retrieved_at=document.retrieved_at,
                provenance=document.provenance,
            ),
            score=self.scores.get(request.parameter_id, 75),
        )

    def call_count(self, parameter_id=None):
        if parameter_id is None:
            return len(self.calls)
        return sum(1 for call in self.calls if call.parameter_id == parameter_id)


def make_service(store, provider, fetcher=None, **kwargs) -> AnalysisService:
    return AnalysisService(
        store,
        provider=provider,
        fetcher=fetcher,
        allow_synthetic_evidence=True,
        **kwargs,
    )


def run(service, **overrides):
    payload = dict(
        product=PRODUCT,
        composition=COMPOSITION,
        profile=PROFILE,
        source_urls=(URL,),
    )
    payload.update(overrides)
    return service.analyze(**payload)


class GapScanTests(unittest.TestCase):
    def test_plan_reports_every_gap_before_research(self):
        store = InMemoryStore()
        provider = DocumentProvider()
        service = ResearchService(store, provider, allow_synthetic_evidence=True)
        plan = service.plan(product=PRODUCT, composition=COMPOSITION, profile=PROFILE)
        self.assertEqual(plan.needed, ("problem:dryness", "skin_type:dry"))
        self.assertEqual(
            [(gap.parameter_id, gap.reason) for gap in plan.gaps],
            [("problem:dryness", "missing"), ("skin_type:dry", "missing")],
        )
        self.assertEqual(provider.call_count(), 0)

    def test_unverified_composition_is_blocked_before_any_research(self):
        store = InMemoryStore()
        provider = DocumentProvider()
        fetcher = FakeDocumentFetcher({URL: PAGE_TEXT})
        report = run(
            make_service(store, provider, fetcher),
            composition={**COMPOSITION, "verified_at": ""},
        )
        self.assertEqual(report.analysis.status, "blocked")
        self.assertFalse(report.analysis.is_final)
        self.assertIsNone(report.snapshot["total"])
        self.assertEqual(provider.call_count(), 0)
        self.assertEqual(fetcher.calls, [])


class SharedResearchTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.provider = DocumentProvider()
        self.fetcher = FakeDocumentFetcher({URL: PAGE_TEXT})
        self.service = make_service(self.store, self.provider, self.fetcher)

    def test_all_parameters_are_answered_from_one_download(self):
        report = run(self.service)
        self.assertEqual(self.fetcher.calls, [URL])
        self.assertEqual(self.provider.call_count(), 2)
        self.assertEqual(len(report.research.researched), 2)
        self.assertEqual(report.research.documents_fetched, 1)
        for request in self.provider.calls:
            self.assertEqual([doc.url for doc in request.documents], [URL])

    def test_each_parameter_keeps_its_own_result(self):
        report = run(self.service)
        values = {
            item["parameter_id"]: item["value"]
            for item in report.snapshot["parameters"]
        }
        self.assertEqual(values, {"problem:dryness": 75, "skin_type:dry": 100})
        self.assertEqual(report.snapshot["total"], 87.5)
        self.assertEqual(report.analysis.status, "complete")
        self.assertTrue(report.analysis.is_final)

    def test_documents_are_stored_once_and_reused_on_the_next_run(self):
        run(self.service)
        composition_id = self.store.get_composition(
            PRODUCT["id"], COMPOSITION["composition_hash"]
        )["id"]
        self.assertEqual(len(self.store.documents_for(composition_id)), 1)
        self.assertEqual(len(self.store.evidence_for(composition_id, "problem:dryness")), 1)
        calls_before = self.provider.call_count()
        fetches_before = len(self.fetcher.calls)

        second = run(self.service)
        self.assertEqual(self.provider.call_count(), calls_before)
        self.assertEqual(len(self.fetcher.calls), fetches_before)
        self.assertIsNone(second.research)
        self.assertTrue(second.is_final)

    def test_candidate_from_another_page_is_rejected(self):
        document = SourceDocument(
            url=URL, text=PAGE_TEXT, retrieved_at="2026-10-01T00:00:00+00:00"
        )
        evidence = validate_candidates(
            [
                candidate(
                    parameter_id="problem:dryness",
                    claim="unknown page",
                    quote=QUOTES["problem:dryness"],
                    url="https://elsewhere.example/page",
                    source_text=document.text,
                    provenance="fetched",
                )
            ],
            product_id=PRODUCT["id"],
            composition_hash=COMPOSITION["composition_hash"],
            parameter_id="problem:dryness",
            documents=(document,),
        )
        self.assertEqual(evidence[0].verification, "rejected")
        self.assertIn("загруженных документов", evidence[0].rejection_reason)



class HonestIncompletenessTests(unittest.TestCase):
    def test_missing_evidence_is_not_presented_as_a_final_report(self):
        store = InMemoryStore()
        provider = DocumentProvider(insufficient_for={"skin_type:dry"})
        report = run(make_service(store, provider, FakeDocumentFetcher({URL: PAGE_TEXT})))
        self.assertEqual(report.analysis.status, "incomplete")
        self.assertFalse(report.analysis.is_final)
        self.assertEqual(report.snapshot["total"], 75)
        self.assertEqual(
            [gap["parameter_id"] for gap in report.analysis.as_dict()["gaps"]],
            ["skin_type:dry"],
        )
        self.assertIn("неполный", " ".join(report.analysis.notes))

    def test_insufficient_parameters_are_researched_with_the_shared_documents(self):
        store = InMemoryStore()
        provider = DocumentProvider(insufficient_for={"skin_type:dry"})
        fetcher = FakeDocumentFetcher({URL: PAGE_TEXT})
        service = make_service(store, provider, fetcher)
        run(service)
        calls_before = provider.call_count("skin_type:dry")
        run(service)
        self.assertEqual(provider.call_count("skin_type:dry"), calls_before + 1)
        self.assertEqual(len(fetcher.calls), 1)
        last = provider.calls[-1]
        self.assertEqual([doc.url for doc in last.documents], [URL])

    def test_attempt_limit_stops_re_research_and_reuses_the_result(self):
        store = InMemoryStore()
        provider = DocumentProvider(insufficient_for={"skin_type:dry"})
        service = make_service(
            store, provider, FakeDocumentFetcher({URL: PAGE_TEXT}), max_attempts=1
        )
        run(service)
        calls_before = provider.call_count()
        report = run(service)
        self.assertEqual(provider.call_count(), calls_before)
        self.assertIn("skin_type:dry", report.analysis.exhausted_parameters)
        self.assertFalse(report.is_final)

    def test_no_valid_scores_gives_null_total_and_disabled_verdict(self):
        store = InMemoryStore()
        provider = DocumentProvider(insufficient_for={"problem:dryness", "skin_type:dry"})
        report = run(make_service(store, provider, FakeDocumentFetcher({URL: PAGE_TEXT})))
        self.assertIsNone(report.snapshot["total"])
        self.assertIsNone(report.snapshot["verdict"])
        self.assertEqual(report.analysis.assessed_parameters, ())
        self.assertFalse(report.is_final)

    def test_failed_research_is_marked_failed(self):
        store = InMemoryStore()

        class Failing:
            name = "failing"

            def research(self, request):
                return ResearchOutcome(
                    status="provider_error", error="timeout", provider="x"
                )

        report = run(make_service(store, Failing(), FakeDocumentFetcher({URL: PAGE_TEXT})))
        self.assertEqual(report.analysis.status, "failed")
        self.assertFalse(report.is_final)
        self.assertIsNone(report.snapshot["total"])
        self.assertEqual(len(report.analysis.failed_parameters), 2)



class KnowledgeReuseTests(unittest.TestCase):
    def test_product_loader_supplies_composition_and_seed_urls(self):
        store = InMemoryStore()
        provider = DocumentProvider()

        def loader(product_id: int):
            return {
                "id": product_id,
                "name": "Catalog Serum",
                "ingredients": "Aqua, Glycerin",
                "url": "https://catalog.example/serum",
            }

        class Repository:
            def get_goal_evidence_map(self, ingredients=None):
                return {
                    "glycerin": {
                        "hydration": {"source_url": "https://study.example/glycerin"}
                    }
                }

        fetcher = FakeDocumentFetcher(
            {
                "https://catalog.example/serum": PAGE_TEXT,
                "https://study.example/glycerin": PAGE_TEXT + " Study details.",
            }
        )
        service = make_service(store, provider, fetcher)
        report = service.analyze_product(
            PRODUCT["id"],
            profile=PROFILE,
            verified_at="2026-10-20",
            product_loader=loader,
            repository=Repository(),
        )
        self.assertEqual(report.analysis.status, "complete")
        self.assertEqual(report.product["name"], "Catalog Serum")
        self.assertIn("https://catalog.example/serum", fetcher.calls)
        self.assertIn("https://study.example/glycerin", fetcher.calls)
        self.assertEqual(report.composition["status"], "active")

    def test_unverified_catalog_product_is_blocked(self):
        store = InMemoryStore()
        service = make_service(
            store, DocumentProvider(), FakeDocumentFetcher({URL: PAGE_TEXT})
        )
        report = service.analyze_product(
            PRODUCT["id"],
            profile=PROFILE,
            product_loader=lambda product_id: {
                "id": product_id,
                "name": "Catalog Serum",
                "ingredients": "Aqua, Glycerin",
                "url": URL,
            },
        )
        self.assertEqual(report.analysis.status, "blocked")

    def test_missing_product_is_reported(self):
        from app.evaluation.knowledge import ProductNotFound

        store = InMemoryStore()
        service = make_service(store, DocumentProvider())
        with self.assertRaises(ProductNotFound):
            service.analyze_product(
                PRODUCT["id"], profile=PROFILE, product_loader=lambda product_id: None
            )


class SnapshotAnalysisTests(unittest.TestCase):
    def test_snapshot_carries_analysis_state_and_completion_creates_a_new_snapshot(self):
        store = InMemoryStore()
        provider = DocumentProvider(insufficient_for={"skin_type:dry"})
        fetcher = FakeDocumentFetcher({URL: PAGE_TEXT})
        service = make_service(store, provider, fetcher)

        incomplete = run(service, allow_research=False)
        self.assertEqual(incomplete.analysis.status, "incomplete")
        self.assertFalse(incomplete.snapshot["analysis"]["is_final"])

        provider.insufficient_for.clear()
        completed = run(service)
        self.assertEqual(completed.analysis.status, "complete")
        self.assertTrue(completed.snapshot["analysis"]["is_final"])
        self.assertNotEqual(
            incomplete.snapshot["snapshot_id"], completed.snapshot["snapshot_id"]
        )

    def test_no_research_means_gaps_are_reported_not_ignored(self):
        store = InMemoryStore()
        report = run(make_service(store, DocumentProvider()), allow_research=False)
        self.assertEqual(report.analysis.status, "incomplete")
        self.assertEqual(len(report.analysis.as_dict()["gaps"]), 2)
        self.assertIsNone(report.research)


if __name__ == "__main__":
    unittest.main()

