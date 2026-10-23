"""API tests for `/api/v1/evaluation` using TestClient + in-memory storage."""
from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user, get_current_user_optional
from app.evaluation import ParameterEvaluation
from app.evaluation.api import require_admin, setup_evaluation_routes
from app.evaluation.service import DEFAULT_METHOD_VERSION, EvaluationService
from app.evaluation.store import InMemoryStore

HASH = "a" * 64
PRODUCT = {"id": 7, "name": "Test Cream"}
COMPOSITION = {"composition_hash": HASH, "source": "catalog", "verified_at": "2026-10-20"}
PROFILE = {"skin_type": "dry", "concerns": ["dryness"]}


def make_client(store: InMemoryStore | None = None, user_id: int = 1, admin: bool = True):
    store = store or InMemoryStore()
    app = FastAPI()
    setup_evaluation_routes(app, store=store)
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
    app.dependency_overrides[get_current_user_optional] = lambda: None
    if admin:
        app.dependency_overrides[require_admin] = lambda: None
    return TestClient(app), store, app


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
    def test_preview_returns_total_without_persistence(self):
        client, store, _ = make_client()
        response = client.post(
            "/api/v1/evaluation/preview",
            json={
                "profile": PROFILE,
                "evaluations": [
                    {
                        "parameter_id": "problem:dryness",
                        "value": 100,
                        "rationale": "Подтверждённые источники соответствуют требованию.",
                        "evidence_ids": ["1"],
                    },
                    {
                        "parameter_id": "skin_type:dry",
                        "value": 50,
                        "rationale": "Источники частично соответствуют требованию пункта.",
                        "evidence_ids": ["2"],
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["total"], 75)
        self.assertIsNone(result["verdict"])
        self.assertEqual(store.snapshot_count(), 0)

    def test_preview_rejects_out_of_scale_value(self):
        client, _, _ = make_client()
        for value in (150, 30):
            response = client.post(
                "/api/v1/evaluation/preview",
                json={
                    "profile": PROFILE,
                    "evaluations": [{"parameter_id": "problem:dryness", "value": value}],
                },
            )
            self.assertEqual(response.status_code, 422, value)

    def test_preview_rejects_assessed_without_reason_or_evidence(self):
        client, _, _ = make_client()
        response = client.post(
            "/api/v1/evaluation/preview",
            json={
                "profile": PROFILE,
                "evaluations": [{"parameter_id": "problem:dryness", "value": 75}],
            },
        )
        self.assertEqual(response.status_code, 422)


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


if __name__ == "__main__":
    unittest.main()
