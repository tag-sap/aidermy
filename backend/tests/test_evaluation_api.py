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
PROFILE = {"skin_type": "dry"}


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
        self.assertEqual(len(body["parameters"]), 12)
        self.assertFalse(body["rules"]["calibrated"])
        self.assertTrue(all("anchors" in item for item in body["parameters"]))


class PreviewEndpointTests(unittest.TestCase):
    def test_preview_returns_total_without_persistence(self):
        client, store, _ = make_client()
        response = client.post(
            "/api/v1/evaluation/preview",
            json={
                "profile": PROFILE,
                "evaluations": [
                    {"parameter_id": "hydration", "value": 80},
                    {"parameter_id": "barrier", "value": 60},
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["total"], 70)
        self.assertIsNone(result["verdict"])
        self.assertEqual(store.snapshot_count(), 0)

    def test_preview_rejects_out_of_scale_value(self):
        client, _, _ = make_client()
        response = client.post(
            "/api/v1/evaluation/preview",
            json={
                "profile": PROFILE,
                "evaluations": [{"parameter_id": "hydration", "value": 150}],
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
        self.assertEqual(body["pending_parameters"], ["barrier", "hydration"])
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
        for parameter_id, value in (("hydration", 80), ("barrier", 60)):
            service.record_evaluation(
                record["id"],
                ParameterEvaluation(
                    parameter_id=parameter_id,
                    status="evaluated",
                    value=value,
                    composition_hash=HASH,
                    method_version=DEFAULT_METHOD_VERSION,
                ),
            )
        body = self._create(client).json()
        self.assertEqual(body["snapshot"]["total"], 70)
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
            json={"product_id": 7, "composition_hash": HASH, "parameters": ["hydration"]},
        )
        self.assertIn(response.status_code, (401, 403))

    def test_unregistered_composition_returns_404(self):
        client, _, _ = make_client()
        response = client.post(
            "/api/v1/evaluation/research-jobs",
            json={"product_id": 7, "composition_hash": HASH, "parameters": ["hydration"]},
        )
        self.assertEqual(response.status_code, 404)

    def test_jobs_are_created_once(self):
        client, store, _ = make_client()
        EvaluationService(store).ensure_composition(7, COMPOSITION)
        payload = {
            "product_id": 7,
            "composition_hash": HASH,
            "parameters": ["hydration", "barrier"],
        }
        first = client.post("/api/v1/evaluation/research-jobs", json=payload)
        second = client.post("/api/v1/evaluation/research-jobs", json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["created"], ["hydration", "barrier"])
        self.assertEqual(second.json()["created"], [])


if __name__ == "__main__":
    unittest.main()
