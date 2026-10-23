"""API tests for `/api/v1/evaluation` using TestClient + in-memory storage."""
from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user, get_current_user_optional
from app.evaluation import ParameterEvaluation, candidate, validate_candidate
from app.evaluation.api import require_admin, setup_evaluation_routes
from app.evaluation.service import DEFAULT_METHOD_VERSION, EvaluationService
from app.evaluation.store import InMemoryStore

HASH = "a" * 64
OTHER_HASH = "b" * 64
PRODUCT = {"id": 7, "name": "Test Cream"}
COMPOSITION = {"composition_hash": HASH, "source": "catalog", "verified_at": "2026-10-20"}
PROFILE = {"skin_type": "dry", "concerns": ["dryness"]}
INCI = "Aqua, Glycerin, Niacinamide"


def make_client(
    store: InMemoryStore | None = None,
    user_id: int = 1,
    admin: bool = True,
    optional_user: dict | None = None,
):
    store = store or InMemoryStore()
    app = FastAPI()
    setup_evaluation_routes(app, store=store)
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
    app.dependency_overrides[get_current_user_optional] = lambda: optional_user
    if admin:
        app.dependency_overrides[require_admin] = lambda: None
    return TestClient(app), store, app


def seed_evidence(
    store: InMemoryStore,
    parameter_id: str,
    *,
    provenance: str = "fetched",
    composition_hash: str = HASH,
    product_id: int = 7,
) -> tuple[dict, list[int]]:
    record = store.upsert_composition(
        {
            "product_id": product_id,
            "composition_hash": composition_hash,
            "inci_raw": INCI,
            "source": "catalog",
            "verified_at": "2026-10-20",
        }
    )
    evidence = validate_candidate(
        candidate(
            parameter_id=parameter_id,
            claim="Источник описывает состав продукта",
            quote="Full ingredients are listed on this page",
            source_text="Full ingredients are listed on this page",
            provenance=provenance,
            confidence=1.0,
        ),
        product_id=product_id,
        composition_hash=composition_hash,
        parameter_id=parameter_id,
    )
    return record, store.save_evidence(record["id"], [evidence])


def preview_payload(
    evaluations: list[dict],
    *,
    composition_hash: str = HASH,
    with_composition: bool = True,
) -> dict:
    payload: dict = {"profile": PROFILE, "evaluations": evaluations}
    if with_composition:
        payload["composition"] = {"composition_hash": composition_hash, "inci_raw": INCI}
    return payload


class ParametersEndpointTests(unittest.TestCase):
    def test_registry_and_rules_are_exposed(self):
        client, _, _ = make_client()
        response = client.get("/api/v1/evaluation/parameters")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(len(body["parameters"]), 80)
        self.assertFalse(body["rules"]["calibrated"])
        self.assertTrue(all("anchors" in item for item in body["parameters"]))

    def test_questionnaire_catalog_is_exposed(self):
        client, _, _ = make_client()
        body = client.get("/api/v1/evaluation/parameters").json()
        questionnaire = body["questionnaire"]
        self.assertEqual(questionnaire["version"], "quiz-1.0.0")
        sections = {item["id"]: item for item in questionnaire["sections"]}
        self.assertEqual(
            list(sections),
            ["skin_type", "age", "problem", "therapy", "procedure", "intolerance", "goal"],
        )
        self.assertFalse(sections["age"]["evaluated"])
        self.assertIn(
            {"id": "hydration", "label": "Увлажнить кожу"}, sections["goal"]["options"]
        )
        periods = [item["id"] for item in sections["procedure"]["modifiers"]]
        self.assertEqual(periods, ["<7", "7-14", "14-30", "1-3m", ">3m"])
        parameter = next(
            item for item in body["parameters"] if item["id"] == "goal:hydration"
        )
        self.assertEqual(parameter["section"], "goal")
        self.assertTrue(parameter["question"])
        self.assertEqual(body["score_levels"], [0, 25, 50, 75, 100])
        self.assertEqual(set(body["score_criteria"]), {"0", "25", "50", "75", "100"})
        self.assertIn("частично", body["score_criteria"]["50"])
        self.assertIn("not_applicable", body["statuses"])


class PreviewEndpointTests(unittest.TestCase):
    def _assessed(self, parameter_id: str, evidence_id: int, *, value=75, rationale=None):
        return {
            "parameter_id": parameter_id,
            "status": "assessed",
            "value": value,
            "rationale": rationale
            or "Подтверждённые источники соответствуют требованию пункта.",
            "evidence_ids": [str(evidence_id)],
        }

    def test_preview_requires_explicit_status(self):
        client, _, _ = make_client()
        response = client.post(
            "/api/v1/evaluation/preview",
            json={
                "profile": PROFILE,
                "evaluations": [
                    {
                        "parameter_id": "problem:dryness",
                        "value": 75,
                        "rationale": "Подтверждённые источники соответствуют.",
                        "evidence_ids": ["1"],
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_assessed_preview_requires_authentication(self):
        client, store, _ = make_client(optional_user=None)
        _, ids = seed_evidence(store, "problem:dryness")
        response = client.post(
            "/api/v1/evaluation/preview",
            json=preview_payload([self._assessed("problem:dryness", ids[0])]),
        )
        self.assertEqual(response.status_code, 403)

    def test_assessed_preview_requires_stored_evidence(self):
        client, store, _ = make_client(optional_user={"id": 1})
        seed_evidence(store, "problem:dryness")
        response = client.post(
            "/api/v1/evaluation/preview",
            json=preview_payload([self._assessed("problem:dryness", 999999)]),
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("not stored", response.json()["detail"])

    def test_assessed_preview_rejects_synthetic_evidence(self):
        client, store, _ = make_client(optional_user={"id": 1})
        _, ids = seed_evidence(store, "problem:dryness", provenance="synthetic")
        response = client.post(
            "/api/v1/evaluation/preview",
            json=preview_payload([self._assessed("problem:dryness", ids[0])]),
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("not fetched", response.json()["detail"])

    def test_assessed_preview_rejects_evidence_of_another_parameter(self):
        client, store, _ = make_client(optional_user={"id": 1})
        _, ids = seed_evidence(store, "skin_type:dry")
        response = client.post(
            "/api/v1/evaluation/preview",
            json=preview_payload([self._assessed("problem:dryness", ids[0])]),
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("another parameter", response.json()["detail"])

    def test_assessed_preview_rejects_evidence_of_another_composition(self):
        client, store, _ = make_client(optional_user={"id": 1})
        _, ids = seed_evidence(store, "problem:dryness", composition_hash=HASH)
        response = client.post(
            "/api/v1/evaluation/preview",
            json=preview_payload(
                [self._assessed("problem:dryness", ids[0])],
                composition_hash=OTHER_HASH,
            ),
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("another composition", response.json()["detail"])

    def test_preview_returns_total_without_persistence(self):
        client, store, _ = make_client(optional_user={"id": 1})
        _, dryness_ids = seed_evidence(store, "problem:dryness")
        _, dry_ids = seed_evidence(store, "skin_type:dry")
        response = client.post(
            "/api/v1/evaluation/preview",
            json=preview_payload(
                [
                    self._assessed("problem:dryness", dryness_ids[0], value=100),
                    self._assessed("skin_type:dry", dry_ids[0], value=50),
                ]
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertEqual(result["total"], 75)
        self.assertIsNone(result["verdict"])
        self.assertEqual(store.snapshot_count(), 0)

    def test_preview_rejects_out_of_scale_value(self):
        client, store, _ = make_client(optional_user={"id": 1})
        _, ids = seed_evidence(store, "problem:dryness")
        for value in (150, 30):
            response = client.post(
                "/api/v1/evaluation/preview",
                json=preview_payload([self._assessed("problem:dryness", ids[0], value=value)]),
            )
            self.assertEqual(response.status_code, 422, value)

    def test_preview_rejects_assessed_without_reason(self):
        client, store, _ = make_client(optional_user={"id": 1})
        _, ids = seed_evidence(store, "problem:dryness")
        payload = self._assessed("problem:dryness", ids[0])
        payload["rationale"] = ""
        response = client.post(
            "/api/v1/evaluation/preview", json=preview_payload([payload])
        )
        self.assertEqual(response.status_code, 422)

    def test_non_scoring_preview_needs_no_evidence(self):
        client, _, _ = make_client(optional_user=None)
        response = client.post(
            "/api/v1/evaluation/preview",
            json=preview_payload(
                [
                    {
                        "parameter_id": "problem:dryness",
                        "status": "insufficient_evidence",
                        "rationale": "Источников нет.",
                    }
                ],
                with_composition=False,
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["result"]["total"])


class SnapshotEndpointTests(unittest.TestCase):
    def _create(self, client, payload=None):
        return client.post(
            "/api/v1/evaluation/snapshots",
            json=payload
            or {"profile": PROFILE, "product": PRODUCT, "composition": COMPOSITION},
        )

    def test_snapshot_is_created_with_pending_parameters(self):
        client, store, _ = make_client()
        response = self._create(client)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pending_parameters"], ["problem:dryness", "skin_type:dry"])
        self.assertIsNone(body["snapshot"]["total"])
        self.assertFalse(body["reused"])
        self.assertEqual(store.snapshot_count(), 1)

    def test_repeated_request_reuses_snapshot(self):
        client, store, _ = make_client()
        first = self._create(client).json()["snapshot"]["snapshot_id"]
        second = self._create(client).json()
        self.assertTrue(second["reused"])
        self.assertEqual(second["snapshot"]["snapshot_id"], first)
        self.assertEqual(store.snapshot_count(), 1)

    def test_total_is_returned_when_evaluations_exist(self):
        client, store, _ = make_client()
        service = EvaluationService(store)
        record = service.ensure_composition(7, COMPOSITION)
        for parameter_id, value in (("problem:dryness", 100), ("skin_type:dry", 50)):
            service.record_evaluation(
                record["id"],
                ParameterEvaluation(
                    parameter_id=parameter_id,
                    status="assessed",
                    value=value,
                    rationale=f"{parameter_id}: подтверждённые источники.",
                    evidence_ids=("1",),
                    composition_hash=HASH,
                    method_version=DEFAULT_METHOD_VERSION,
                ),
            )
        body = self._create(client).json()
        self.assertEqual(body["snapshot"]["total"], 75)
        self.assertEqual(body["pending_parameters"], [])

    def test_non_assessed_results_are_not_reported_as_scores(self):
        client, store, _ = make_client()
        service = EvaluationService(store)
        record = service.ensure_composition(7, COMPOSITION)
        service.record_evaluation(
            record["id"],
            ParameterEvaluation(
                parameter_id="problem:dryness",
                status="assessed",
                value=100,
                rationale="problem:dryness: подтверждённые источники.",
                evidence_ids=("1",),
                composition_hash=HASH,
                method_version=DEFAULT_METHOD_VERSION,
            ),
        )
        service.record_evaluation(
            record["id"],
            ParameterEvaluation(
                parameter_id="skin_type:dry",
                status="not_applicable",
                rationale="Параметр не применяется к этому формату продукта.",
                composition_hash=HASH,
                method_version=DEFAULT_METHOD_VERSION,
            ),
        )
        body = self._create(client).json()
        reported = [item["parameter_id"] for item in body["snapshot"]["parameters"]]
        self.assertEqual(reported, ["problem:dryness"])
        self.assertEqual(body["snapshot"]["total"], 100)
        self.assertEqual(body["pending_parameters"], [])

class SnapshotReadTests(unittest.TestCase):
    def _create(self, client):
        return client.post(
            "/api/v1/evaluation/snapshots",
            json={"profile": PROFILE, "product": PRODUCT, "composition": COMPOSITION},
        )

    def test_unknown_snapshot_returns_404(self):
        client, _, _ = make_client()
        response = client.get("/api/v1/evaluation/snapshots/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_snapshot_of_another_user_is_forbidden(self):
        client, _, app = make_client(user_id=1)
        snapshot_id = self._create(client).json()["snapshot"]["snapshot_id"]
        app.dependency_overrides[get_current_user] = lambda: {"id": 2}
        response = client.get(f"/api/v1/evaluation/snapshots/{snapshot_id}")
        self.assertEqual(response.status_code, 403)

    def test_tampered_snapshot_returns_conflict(self):
        client, store, _ = make_client()
        snapshot_id = self._create(client).json()["snapshot"]["snapshot_id"]
        store._snapshots[snapshot_id]["total"] = 99
        response = client.get(f"/api/v1/evaluation/snapshots/{snapshot_id}")
        self.assertEqual(response.status_code, 409)

    def test_owner_can_read_snapshot(self):
        client, _, _ = make_client()
        snapshot_id = self._create(client).json()["snapshot"]["snapshot_id"]
        response = client.get(f"/api/v1/evaluation/snapshots/{snapshot_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["snapshot"]["snapshot_id"], snapshot_id)


class ResearchEndpointTests(unittest.TestCase):
    def test_research_requires_admin(self):
        client, _, _ = make_client(admin=False)
        response = client.post(
            "/api/v1/evaluation/research-jobs",
            json={"product_id": 7, "composition_hash": HASH, "parameters": ["problem:dryness"]},
        )
        self.assertIn(response.status_code, (401, 403))

    def test_unregistered_composition_returns_404(self):
        client, _, _ = make_client()
        response = client.post(
            "/api/v1/evaluation/research-jobs",
            json={"product_id": 7, "composition_hash": HASH, "parameters": ["problem:dryness"]},
        )
        self.assertEqual(response.status_code, 404)

    def test_unverified_composition_is_rejected(self):
        client, store, _ = make_client()
        record = store.upsert_composition(
            {"product_id": 7, "composition_hash": HASH, "inci_raw": "Aqua"}
        )
        self.assertEqual(record["status"], "unverified")
        response = client.post(
            "/api/v1/evaluation/research-jobs",
            json={"product_id": 7, "composition_hash": HASH, "parameters": ["problem:dryness"]},
        )
        self.assertEqual(response.status_code, 409)

    def test_jobs_are_created_once(self):
        client, store, _ = make_client()
        EvaluationService(store).ensure_composition(7, COMPOSITION)
        payload = {
            "product_id": 7,
            "composition_hash": HASH,
            "parameters": ["problem:dryness", "skin_type:dry"],
        }
        first = client.post("/api/v1/evaluation/research-jobs", json=payload)
        second = client.post("/api/v1/evaluation/research-jobs", json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["created"], ["problem:dryness", "skin_type:dry"])
        self.assertEqual(second.json()["created"], [])


class AnalyzeEndpointTests(unittest.TestCase):
    """The end-to-end endpoint: scan, optional shared research, honest report."""

    URL = "https://brand.example/serum"
    PAGE = (
        "Ingredient list: Aqua, Glycerin, Niacinamide. Glycerin helps keep the skin "
        "hydrated and supports the skin barrier. The formula is suitable for dry skin."
    )
    QUOTES = {
        "problem:dryness": "Glycerin helps keep the skin hydrated",
        "skin_type:dry": "suitable for dry skin",
    }

    def _payload(self, **overrides):
        payload = {
            "product": PRODUCT,
            "composition": {**COMPOSITION, "inci_raw": INCI},
            "profile": PROFILE,
            "source_urls": [self.URL],
        }
        payload.update(overrides)
        return payload

    def _provider(self):
        from app.evaluation.research import candidate, ok

        class Provider:
            name = "fake-documents"

            def __init__(self):
                self.calls = []

            def research(self, request):
                self.calls.append(request)
                document = request.documents[0]
                return ok(
                    candidate(
                        parameter_id=request.parameter_id,
                        claim="Подтверждено источником",
                        quote=self_quotes[request.parameter_id],
                        url=document.url,
                        source_text=document.text,
                        retrieved_at=document.retrieved_at,
                        provenance=document.provenance,
                    ),
                    score=75,
                )

        self_quotes = dict(self.QUOTES)
        return Provider()

    def _fetcher(self):
        from app.evaluation.documents import FakeDocumentFetcher

        return FakeDocumentFetcher({self.URL: self.PAGE})

    def test_analyze_reports_gaps_without_research(self):
        client, _, _ = make_client()
        response = client.post("/api/v1/evaluation/analyze", json=self._payload())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["analysis"]["status"], "incomplete")
        self.assertFalse(body["analysis"]["is_final"])
        self.assertEqual(len(body["analysis"]["gaps"]), 2)
        self.assertIsNone(body["snapshot"]["total"])

    def test_analyze_requires_product_or_composition(self):
        client, _, _ = make_client()
        response = client.post(
            "/api/v1/evaluation/analyze", json={"profile": PROFILE}
        )
        self.assertEqual(response.status_code, 422)

    def test_analyze_research_without_provider_is_503(self):
        client, _, _ = make_client()
        response = client.post("/api/v1/evaluation/analyze/research", json=self._payload())
        self.assertEqual(response.status_code, 503, response.text)

    def test_analyze_research_completes_the_report(self):
        client, store, app = make_client()
        app.state.evaluation_research_provider = self._provider()
        app.state.evaluation_document_fetcher = self._fetcher()
        app.state.evaluation_allow_synthetic_evidence = True

        response = client.post("/api/v1/evaluation/analyze/research", json=self._payload())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["analysis"]["status"], "complete")
        self.assertTrue(body["analysis"]["is_final"])
        self.assertEqual(body["snapshot"]["total"], 75)
        self.assertEqual(body["research"]["documents_fetched"], 1)
        self.assertEqual(body["snapshot"]["analysis"]["status"], "complete")

    def test_analyze_research_requires_admin(self):
        client, _, app = make_client(admin=False)
        app.state.evaluation_research_provider = self._provider()
        response = client.post("/api/v1/evaluation/analyze/research", json=self._payload())
        self.assertEqual(response.status_code, 401)

    def test_analyze_unverified_composition_is_blocked(self):
        client, _, _ = make_client()
        payload = self._payload(
            composition={"composition_hash": OTHER_HASH, "source": "catalog"}
        )
        response = client.post("/api/v1/evaluation/analyze", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["analysis"]["status"], "blocked")


class ProductEndpointTests(unittest.TestCase):
    """Catalog product path: status -> analyze (no spend) -> admin research."""

    URL = "https://brand.example/serum"
    PAGE = (
        "Ingredient list: Aqua, Glycerin, Niacinamide. Glycerin helps keep the skin "
        "hydrated and supports the skin barrier. The formula is suitable for dry skin."
    )
    QUOTES = {
        "problem:dryness": "Glycerin helps keep the skin hydrated",
        "skin_type:dry": "suitable for dry skin",
    }

    def _loader(self, ingredients: str = "Aqua, Glycerin, Niacinamide"):
        return lambda product_id: {
            "id": product_id,
            "name": "Brand\nSerum",
            "brand": "Brand",
            "ingredients": ingredients,
            "url": self.URL,
        }

    def _provider(self):
        from app.evaluation.research import candidate, ok

        quotes = dict(self.QUOTES)

        class Provider:
            name = "fake-documents"

            def __init__(self):
                self.calls = []

            def research(self, request):
                self.calls.append(request)
                document = request.documents[0]
                return ok(
                    candidate(
                        parameter_id=request.parameter_id,
                        claim="Подтверждено источником",
                        quote=quotes[request.parameter_id],
                        url=document.url,
                        source_text=document.text,
                        retrieved_at=document.retrieved_at,
                        provenance=document.provenance,
                    ),
                    score=75,
                )

        return Provider()

    def _search(self):
        class Search:
            name = "fake-search"

            def __init__(self):
                self.queries = []

            def search(self, query, *, limit=5):
                self.queries.append(query)
                return ()

        return Search()

    def _wired(self, *, admin=True, ingredients="Aqua, Glycerin, Niacinamide"):
        from app.evaluation.documents import FakeDocumentFetcher

        client, store, app = make_client(admin=admin)
        provider = self._provider()
        search = self._search()
        app.state.evaluation_product_loader = self._loader(ingredients)
        app.state.evaluation_research_provider = provider
        app.state.evaluation_document_fetcher = FakeDocumentFetcher({self.URL: self.PAGE})
        app.state.evaluation_source_search = search
        app.state.evaluation_allow_synthetic_evidence = True
        return client, store, app, provider, search

    def test_status_reports_known_and_missing_parameters(self):
        client, store, _, provider, search = self._wired()
        response = client.post("/api/v1/evaluation/products/1/status", json={"profile": PROFILE})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["product"]["brand"], "Brand")
        self.assertEqual(body["product"]["name"], "Serum")
        self.assertEqual(body["analysis"]["status"], "blocked")
        self.assertEqual(len(body["analysis"]["gaps"]), 2)
        self.assertIn(self.URL, body["source_urls"])
        self.assertEqual(provider.calls, [])
        self.assertEqual(search.queries, [])

    def test_analyze_does_not_verify_the_composition_or_spend(self):
        client, store, _, provider, search = self._wired()
        response = client.post(
            "/api/v1/evaluation/products/1/analyze",
            json={"profile": PROFILE, "verify_catalog_inci": True},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["analysis"]["status"], "blocked")
        self.assertFalse(body["analysis"]["is_final"])
        self.assertEqual(provider.calls, [])
        self.assertEqual(search.queries, [])

    def test_admin_research_verifies_catalog_inci_and_completes(self):
        client, store, _, provider, search = self._wired()
        response = client.post(
            "/api/v1/evaluation/products/1/research", json={"profile": PROFILE}
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["composition"]["status"], "active")
        self.assertEqual(body["analysis"]["status"], "complete")
        self.assertTrue(body["analysis"]["is_final"])
        self.assertEqual(body["snapshot"]["total"], 75)
        self.assertEqual(len(provider.calls), 2)
        self.assertTrue(search.queries)

    def test_admin_research_refuses_unreliable_inci(self):
        client, store, _, provider, _ = self._wired(ingredients="Aqua")
        response = client.post(
            "/api/v1/evaluation/products/1/research", json={"profile": PROFILE}
        )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(provider.calls, [])

    def test_admin_research_requires_admin(self):
        client, store, _, provider, _ = self._wired(admin=False)
        response = client.post(
            "/api/v1/evaluation/products/1/research", json={"profile": PROFILE}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(provider.calls, [])

    def test_configure_evaluation_makes_the_http_path_work(self):
        from app.evaluation.documents import FakeDocumentFetcher
        from app.evaluation.runtime import configure_evaluation

        app = FastAPI()
        configure_evaluation(
            app,
            store=InMemoryStore(),
            provider=self._provider(),
            fetcher=FakeDocumentFetcher({self.URL: self.PAGE}),
            search=self._search(),
            allow_synthetic_evidence=True,
        )
        app.state.evaluation_product_loader = self._loader()
        app.dependency_overrides[get_current_user] = lambda: {"id": 1}
        app.dependency_overrides[require_admin] = lambda: None
        response = TestClient(app).post(
            "/api/v1/evaluation/products/1/research", json={"profile": PROFILE}
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["analysis"]["status"], "complete")
        self.assertEqual(body["snapshot"]["total"], 75)
        self.assertTrue(body["analysis"]["is_final"])

    def test_research_after_status_upgrades_the_unverified_composition(self):
        client, store, _, provider, _ = self._wired()
        status = client.post(
            "/api/v1/evaluation/products/1/status", json={"profile": PROFILE}
        )
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["composition"]["status"], "unverified")

        research = client.post(
            "/api/v1/evaluation/products/1/research", json={"profile": PROFILE}
        )
        self.assertEqual(research.status_code, 200, research.text)
        body = research.json()
        self.assertEqual(body["composition"]["status"], "active")
        self.assertEqual(body["analysis"]["status"], "complete")
        self.assertTrue(body["analysis"]["is_final"])
        self.assertEqual(len(provider.calls), 2)

    def test_health_reports_wiring(self):
        client, _, _, _, _ = self._wired()
        response = client.get("/api/v1/evaluation/health")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["storage"]["configured"])
        self.assertEqual(body["research"]["provider"], "fake-documents")
        self.assertEqual(body["research"]["fetcher"], "fake")
        self.assertEqual(body["research"]["search"], "fake-search")
        self.assertIn("schema", body)


class RuntimeWiringTests(unittest.TestCase):
    def test_provider_is_absent_without_a_key(self):
        from app.evaluation.runtime import build_research_provider

        self.assertIsNone(build_research_provider(api_key=""))

    def test_provider_is_built_with_a_key(self):
        from app.evaluation.runtime import build_research_provider

        provider = build_research_provider(api_key="test-key")
        self.assertEqual(provider.name, "llm")
        self.assertEqual(provider.api_key, "test-key")

    def test_fetcher_can_be_disabled(self):
        from app.evaluation.runtime import build_document_fetcher

        self.assertIsNone(build_document_fetcher(enabled=False))
        self.assertEqual(build_document_fetcher().name, "http")

    def test_configure_evaluation_attaches_everything_and_registers_routes(self):
        from app.evaluation.runtime import configure_evaluation

        app = FastAPI()
        store = InMemoryStore()
        configure_evaluation(app, store=store, provider=None, fetcher=None)
        self.assertIs(app.state.evaluation_store, store)
        self.assertFalse(app.state.evaluation_allow_synthetic_evidence)
        app.dependency_overrides[get_current_user] = lambda: {"id": 1}
        response = TestClient(app).post(
            "/api/v1/evaluation/analyze", json={"profile": PROFILE}
        )
        self.assertEqual(response.status_code, 422)
        from app.evaluation.runtime import configure_evaluation

        app = FastAPI()
        store = InMemoryStore()
        configure_evaluation(app, store=store, provider=None, fetcher=None)
        self.assertIs(app.state.evaluation_store, store)
        self.assertFalse(app.state.evaluation_allow_synthetic_evidence)
        app.dependency_overrides[get_current_user] = lambda: {"id": 1}
        response = TestClient(app).post(
            "/api/v1/evaluation/analyze", json={"profile": PROFILE}
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
