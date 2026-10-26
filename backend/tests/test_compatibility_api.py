import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import compat_store
from app.auth import get_current_user
from app.compat_routes import setup_compat_routes


class CompatibilityApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp.close()
        self.addCleanup(lambda: os.path.exists(self.temp.name) and os.unlink(self.temp.name))
        self.store_patch = patch.object(compat_store, "AIDERMY_DB", self.temp.name)
        self.ready_patch = patch.object(compat_store, "_SCHEMA_READY", False)
        self.store_patch.start()
        self.ready_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.addCleanup(self.ready_patch.stop)

        self.app = FastAPI()
        self._worker_flag = patch.dict(os.environ, {"AIDERMY_COMPAT_WORKER": "0"})
        self._worker_flag.start()
        self.addCleanup(self._worker_flag.stop)
        setup_compat_routes(self.app)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": 1, "plan": "plus"}
        self.shelf = [
            {"product_id": 1, "cabinet": "face"},
            {"product_id": 2, "cabinet": "face"},
        ]

    def _product(self, product_id):
        return {"id": product_id, "name": f"Product {product_id}", "brand": "Brand", "category": "Увлажнение"}

    def _client(self):
        return TestClient(self.app)

    def test_start_creates_set_immediately_and_checks_owner(self):
        with patch("app.compat_routes.get_user_shelf", return_value=self.shelf), \
                patch("app.compat_routes.get_product_by_id", side_effect=self._product), \
                patch("app.compat_routes.get_user_profile_updated_at", return_value="now"), \
                patch("app.compat_routes.get_balance", return_value={"balance": 10}):
            with self._client() as client:
                response = client.post(
                    "/api/v1/compatibility/tasks/compatibility",
                    json={"product_ids": [1, 2], "profile": {"skin_type": "dry"}, "name": "Test"},
                )
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["set"]["status"], "queued")
                self.assertEqual(body["set"]["product_ids"], [1, 2])
                self.assertEqual(body["set"]["cost"], 1)
                self.assertEqual(body["cost"], 1)
                set_id = body["set"]["id"]
                second = client.post(
                    "/api/v1/compatibility/tasks/compatibility",
                    json={"product_ids": [1, 2], "profile": {"skin_type": "dry"}, "name": "Test"},
                ).json()
                self.assertTrue(second["reused"])
                self.assertEqual(second["task"]["id"], body["task"]["id"])

                self.app.dependency_overrides[get_current_user] = lambda: {"id": 2, "plan": "plus"}
                self.assertEqual(client.get(f"/api/v1/compatibility/sets/{set_id}").status_code, 404)
                self.assertEqual(client.delete(f"/api/v1/compatibility/sets/{set_id}").status_code, 404)

    def test_compatibility_requires_two_unique_shelf_products(self):
        with patch("app.compat_routes.get_user_shelf", return_value=self.shelf), \
                patch("app.compat_routes.get_product_by_id", side_effect=self._product):
            with self._client() as client:
                self.assertEqual(
                    client.post(
                        "/api/v1/compatibility/tasks/compatibility",
                        json={"product_ids": [1], "profile": {}},
                    ).status_code,
                    422,
                )
                self.assertEqual(
                    client.post(
                        "/api/v1/compatibility/tasks/compatibility",
                        json={"product_ids": [1, 1], "profile": {}},
                    ).status_code,
                    422,
                )
                self.assertEqual(
                    client.post(
                        "/api/v1/compatibility/tasks/compatibility",
                        json={"product_ids": [1, 99], "profile": {}},
                    ).status_code,
                    422,
                )

    def test_individual_start_returns_task_immediately(self):
        with patch("app.compat_routes.get_product_by_id", side_effect=self._product), \
                patch("app.compat_routes.get_user_profile_updated_at", return_value="now"):
            with self._client() as client:
                response = client.post(
                    "/api/v1/compatibility/tasks/individual",
                    json={"product_id": 1, "profile": {"skin_type": "dry"}},
                )
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["task"]["kind"], "individual")
                self.assertEqual(body["task"]["status"], "queued")
                self.assertFalse(body["reused"])

    def test_pricing_endpoint_and_insufficient_balance(self):
        with self._client() as client:
            response = client.get("/api/v1/compatibility/pricing?product_count=10")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["cost"], 7)

        with patch("app.compat_routes.get_user_shelf", return_value=self.shelf), \
                patch("app.compat_routes.get_product_by_id", side_effect=self._product), \
                patch("app.compat_routes.get_user_profile_updated_at", return_value="now"), \
                patch("app.compat_routes.get_balance", return_value={"balance": 0}):
            with self._client() as client:
                response = client.post(
                    "/api/v1/compatibility/tasks/compatibility",
                    json={"product_ids": [1, 2], "profile": {}},
                )
                self.assertEqual(response.status_code, 402)
                self.assertIn("баланс", response.json()["detail"])

    def test_batch_quote_and_start_charge_only_missing_products(self):
        shelf = [{"product_id": pid, "cabinet": "face"} for pid in (1, 2, 3, 4, 5)]
        with patch("app.compat_routes.get_user_shelf", return_value=shelf), \
                patch("app.compat_routes.get_product_by_id", side_effect=self._product), \
                patch("app.compat_routes.get_user_profile_updated_at", return_value="now"), \
                patch("app.compat_routes.get_balance", return_value={"balance": 10}), \
                patch("app.compat_routes._missing_product_ids", new=AsyncMock(return_value=[4, 5])):
            with self._client() as client:
                quote = client.post(
                    "/api/v1/compatibility/batch/quote",
                    json={"product_ids": [1, 2, 3, 4, 5], "profile": {"skin_type": "dry"}},
                )
                self.assertEqual(quote.status_code, 200)
                body = quote.json()
                self.assertEqual(body["missing_product_ids"], [4, 5])
                self.assertEqual(body["reused_count"], 3)
                self.assertEqual(body["cost"], 1)
                self.assertTrue(body["sufficient"])

                started = client.post(
                    "/api/v1/compatibility/tasks/compatibility",
                    json={
                        "product_ids": [1, 2, 3, 4, 5],
                        "profile": {"skin_type": "dry"},
                        "name": "Мой набор",
                        "only_missing": True,
                    },
                )
                self.assertEqual(started.status_code, 200)
                result = started.json()
                self.assertEqual(result["cost"], 1)
                self.assertEqual(result["set"]["cost"], 1)
                self.assertEqual(result["set"]["name"], "Мой набор")

    def test_batch_with_all_current_results_does_not_create_a_paid_set(self):
        with patch("app.compat_routes.get_user_shelf", return_value=self.shelf), \
                patch("app.compat_routes.get_product_by_id", side_effect=self._product), \
                patch("app.compat_routes.get_user_profile_updated_at", return_value="now"), \
                patch("app.compat_routes.get_balance", return_value={"balance": 10}), \
                patch("app.compat_routes._missing_product_ids", new=AsyncMock(return_value=[])):
            with self._client() as client:
                started = client.post(
                    "/api/v1/compatibility/tasks/compatibility",
                    json={"product_ids": [1, 2], "profile": {}, "only_missing": True},
                )
                self.assertEqual(started.status_code, 200)
                self.assertEqual(started.json()["cost"], 0)
                self.assertIsNone(started.json()["set"])

    def test_set_can_be_renamed_by_owner(self):
        row = compat_store.create_set(
            user_id=1,
            name="Старое имя",
            product_ids=[1, 2],
            profile={},
            profile_updated_at="now",
            context_key="rename",
        )
        with self._client() as client:
            response = client.patch(
                f"/api/v1/compatibility/sets/{row['id']}",
                json={"name": "Новое имя"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["set"]["name"], "Новое имя")
            self.app.dependency_overrides[get_current_user] = lambda: {"id": 2, "plan": "plus"}
            self.assertEqual(
                client.patch(f"/api/v1/compatibility/sets/{row['id']}", json={"name": "Чужое"}).status_code,
                404,
            )

    def test_retry_reuses_current_results_and_quotes_only_missing(self):
        row = compat_store.create_set(
            user_id=1,
            name="Набор",
            product_ids=[1, 2, 3],
            profile={},
            profile_updated_at="now",
            context_key="retry",
        )
        with patch("app.compat_routes.get_user_shelf", return_value=[
            {"product_id": 1, "cabinet": "face"},
            {"product_id": 2, "cabinet": "face"},
            {"product_id": 3, "cabinet": "face"},
        ]), \
                patch("app.compat_routes.get_product_by_id", side_effect=self._product), \
                patch("app.compat_routes.get_user_profile_updated_at", return_value="now"), \
                patch("app.compat_routes.get_balance", return_value={"balance": 10}), \
                patch("app.compat_routes._missing_product_ids", new=AsyncMock(return_value=[3])):
            with self._client() as client:
                response = client.post(
                    f"/api/v1/compatibility/sets/{row['id']}/retry",
                    json={"profile": {}},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["cost"], 1)
                self.assertEqual(response.json()["set"]["cost"], 1)

    def test_notification_can_be_marked_read_by_owner_only(self):
        notification = compat_store.create_notification(
            user_id=1, event_key="read-me", kind="compatibility_completed",
            title="Готово", body="Отчёт", target_type="compatibility_set", target_id=1,
        )
        with self._client() as client:
            self.assertEqual(client.post(f"/api/v1/notifications/{notification['id']}/read").status_code, 200)
            stored = compat_store.list_notifications(1)[0]
            self.assertTrue(stored["read_at"])
            self.app.dependency_overrides[get_current_user] = lambda: {"id": 2, "plan": "plus"}
            self.assertEqual(client.post(f"/api/v1/notifications/{notification['id']}/read").status_code, 404)

    def test_notifications_can_be_deleted_one_by_one_and_all_at_once(self):
        first = compat_store.create_notification(
            user_id=1, event_key="delete-one", kind="compatibility_completed",
            title="Первое", body="Отчёт", target_type="compatibility_set", target_id=1,
        )
        compat_store.create_notification(
            user_id=1, event_key="delete-all", kind="compatibility_completed",
            title="Второе", body="Отчёт", target_type="compatibility_set", target_id=2,
        )
        with self._client() as client:
            self.assertEqual(client.delete(f"/api/v1/notifications/{first['id']}").status_code, 200)
            self.assertEqual(len(client.get("/api/v1/notifications").json()["notifications"]), 1)
            self.assertEqual(client.delete("/api/v1/notifications").status_code, 200)
            self.assertEqual(client.get("/api/v1/notifications").json()["notifications"], [])
            self.assertEqual(client.delete(f"/api/v1/notifications/{first['id']}").status_code, 404)

    def test_notifications_are_scoped_to_the_current_user(self):
        compat_store.create_notification(
            user_id=1, event_key="e1", kind="compatibility_completed",
            title="Готово", body="Отчёт", target_type="compatibility_set", target_id=1,
        )
        compat_store.create_notification(
            user_id=2, event_key="e2", kind="compatibility_completed",
            title="Чужое", body="Отчёт", target_type="compatibility_set", target_id=2,
        )
        with self._client() as client:
            body = client.get("/api/v1/notifications").json()
            self.assertEqual(len(body["notifications"]), 1)
            self.assertEqual(body["notifications"][0]["title"], "Готово")


if __name__ == "__main__":
    unittest.main()
