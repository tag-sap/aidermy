"""Composition readiness: use trustworthy catalog INCI, never a bare string."""
from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user, get_current_user_optional
from app.evaluation.api import setup_evaluation_routes
from app.evaluation.documents import FakeDocumentFetcher
from app.evaluation.knowledge import assess_composition
from app.evaluation.store import InMemoryStore

PROFILE = {"skin_type": "dry", "concerns": ["dryness"]}
INCI = "Aqua, Glycerin, Niacinamide, Panthenol"
TRUSTED = "https://incidecoder.com/products/test-serum"
UNTRUSTED = "https://brand.example/products/test-serum"
PAGE = f"Ingredients: {INCI}. Glycerin hydrates dry skin."


def make_client(*, ingredients=INCI, url=UNTRUSTED, page=PAGE):
    app = FastAPI()
    store = InMemoryStore()
    setup_evaluation_routes(app, store=store)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    app.dependency_overrides[get_current_user_optional] = lambda: None
    app.state.evaluation_product_loader = lambda product_id: {
        "id": product_id,
        "name": "Brand\nTest Serum",
        "brand": "Brand",
        "ingredients": ingredients,
        "url": url,
    }
    app.state.evaluation_document_fetcher = FakeDocumentFetcher({url: page})
    return TestClient(app), store


class CompositionAssessmentTests(unittest.TestCase):
    def test_trusted_complete_inci_is_usable_and_needs_automatic_verification(self):
        state = assess_composition(
            {"url": TRUSTED}, {"inci_raw": INCI, "source": TRUSTED}, status="unverified"
        )
        self.assertTrue(state.usable)
        self.assertTrue(state.auto_verify)
        self.assertEqual(state.reason, "trusted_catalog")
        self.assertEqual(state.source_host, "incidecoder.com")

    def test_untrusted_source_stays_unconfirmed(self):
        state = assess_composition(
            {"url": UNTRUSTED}, {"inci_raw": INCI, "source": UNTRUSTED}, status="unverified"
        )
        self.assertFalse(state.usable)
        self.assertFalse(state.auto_verify)
        self.assertEqual(state.action, "check_source")

    def test_empty_and_single_token_inci_are_not_usable(self):
        missing = assess_composition({}, {"inci_raw": ""})
        single = assess_composition({}, {"inci_raw": "Aqua"})
        truncated = assess_composition({}, {"inci_raw": "Aqua, Glycerin,"})
        self.assertEqual(missing.reason, "missing")
        self.assertEqual(single.reason, "incomplete")
        self.assertEqual(truncated.reason, "incomplete")
        self.assertFalse(missing.usable or single.usable or truncated.usable)

    def test_active_composition_is_confirmed_even_without_trusted_host(self):
        state = assess_composition(
            {"url": UNTRUSTED}, {"inci_raw": INCI, "source": UNTRUSTED}, status="active"
        )
        self.assertTrue(state.usable)
        self.assertEqual(state.reason, "confirmed")

    def test_superseded_composition_is_not_revived_automatically(self):
        state = assess_composition(
            {"url": TRUSTED}, {"inci_raw": INCI, "source": TRUSTED}, status="superseded"
        )
        self.assertFalse(state.usable)
        self.assertFalse(state.auto_verify)
        self.assertEqual(state.reason, "superseded")
class CompositionApiTests(unittest.TestCase):
    def test_status_auto_verifies_trusted_catalog_inci_without_spending(self):
        client, store = make_client(url=TRUSTED)
        response = client.post("/api/v1/evaluation/products/5/status", json={"profile": PROFILE})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["composition"]["status"], "active")
        self.assertTrue(body["composition"]["verified_at"])
        self.assertTrue(body["composition_state"]["usable"])
        self.assertEqual(body["composition_state"]["reason"], "confirmed")
        self.assertNotEqual(body["analysis"]["status"], "blocked")
        self.assertEqual(len(body["analysis"]["gaps"]), 2)
        record = store.get_composition(5, body["composition"]["composition_hash"])
        self.assertEqual(record["status"], "active")

    def test_analyze_works_with_trusted_catalog_without_admin_verification(self):
        client, _ = make_client(url=TRUSTED)
        response = client.post(
            "/api/v1/evaluation/products/5/analyze",
            json={"profile": PROFILE, "verify_catalog_inci": False},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertNotEqual(body["analysis"]["status"], "blocked")
        self.assertEqual(body["composition"]["status"], "active")
        self.assertTrue(body["composition_state"]["usable"])

    def test_check_endpoint_verifies_trusted_catalog_inci(self):
        client, _ = make_client(url=TRUSTED)
        response = client.post("/api/v1/evaluation/products/5/composition/check", json={})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["checked"])
        self.assertEqual(body["composition"]["status"], "active")
        self.assertTrue(body["composition_state"]["usable"])

    def test_check_endpoint_verifies_untrusted_source_only_if_inci_is_in_the_page(self):
        client, _ = make_client(url=UNTRUSTED)
        response = client.post("/api/v1/evaluation/products/5/composition/check", json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["checked"])
        self.assertEqual(response.json()["composition"]["status"], "active")

    def test_check_endpoint_refuses_untrusted_source_without_matching_inci(self):
        client, _ = make_client(
            url=UNTRUSTED,
            page="A product page without the formula. It only describes how to apply the serum.",
        )
        response = client.post("/api/v1/evaluation/products/5/composition/check", json={})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["checked"])
        self.assertEqual(body["composition"]["status"], "unverified")
        self.assertIn("не найден", body["message"])

    def test_missing_inci_returns_a_concrete_next_action(self):
        client, _ = make_client(ingredients="", url="")
        response = client.post("/api/v1/evaluation/products/5/status", json={"profile": PROFILE})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["analysis"]["status"], "blocked")
        self.assertFalse(body["composition_state"]["usable"])
        self.assertEqual(body["composition_state"]["reason"], "missing")
        self.assertEqual(body["composition_state"]["action"], "provide_inci")

    def test_status_returns_a_saved_snapshot_without_reanalysis(self):
        client, store = make_client(url=TRUSTED)
        store.latest_snapshot = lambda **kwargs: {
            "total": 75,
            "created_at": "2026-10-23T15:00:00+00:00",
            "parameters": [{"parameter_id": "skin_type:dry", "value": 75}],
        }
        response = client.post(
            "/api/v1/evaluation/products/5/status", json={"profile": PROFILE}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["snapshot"]["total"], 75)

    def test_changed_inci_creates_a_new_composition_hash(self):
        client, store = make_client(url=TRUSTED)
        first = client.post(
            "/api/v1/evaluation/products/5/status", json={"profile": PROFILE}
        ).json()["composition"]["composition_hash"]
        client.app.state.evaluation_product_loader = lambda product_id: {
            "id": product_id,
            "name": "Brand\nTest Serum",
            "brand": "Brand",
            "ingredients": "Aqua, Glycerin, Panthenol, Allantoin",
            "url": TRUSTED,
        }
        second = client.post(
            "/api/v1/evaluation/products/5/status", json={"profile": PROFILE}
        ).json()["composition"]["composition_hash"]
        self.assertNotEqual(first, second)
        self.assertIsNotNone(store.get_composition(5, first))
        self.assertIsNotNone(store.get_composition(5, second))


if __name__ == "__main__":
    unittest.main()

