import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import HTTPException  # noqa: E402

from app import billing_routes  # noqa: E402
from app.account_deletion import delete_user_account  # noqa: E402
from app.auth import create_user, get_user_by_id  # noqa: E402
from app.consents import get_user_consents, record_consent  # noqa: E402
from app.database import (  # noqa: E402
    AIDERMY_DB,
    get_analysis_record,
    get_connection,
    upsert_analysis,
)

EMAIL_PREFIX = "legal-test-"


class BillingGuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._cleanup()
        self.user_id = create_user(f"{EMAIL_PREFIX}billing@users.example.invalid", "TestPass12345!")

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email LIKE ?", (EMAIL_PREFIX + "%",))
        conn.commit()
        conn.close()
        # Тестовые согласия не должны оставаться без пользователя.
        try:
            conn = get_connection(AIDERMY_DB)
            cur = conn.cursor()
            cur.execute("DELETE FROM user_consents WHERE user_id NOT IN (SELECT id FROM users)")
            conn.commit()
            conn.close()
        except Exception:
            pass

    async def test_catalog_reports_prices_not_defined(self):
        catalog = await billing_routes.billing_catalog()
        self.assertFalse(catalog["prices_defined"])
        self.assertFalse(catalog["payments_configured"])
        self.assertTrue(all(not p["available"] for p in catalog["plans"]))

    async def test_order_blocked_without_price(self):
        with self.assertRaises(HTTPException) as ctx:
            await billing_routes.create_order(
                billing_routes.OrderRequest(plan="plus"),
                current_user={"id": self.user_id},
            )
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_order_requires_consent_and_provider(self):
        with patch.dict(billing_routes.PLAN_PRICES, {"plus": 100}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                await billing_routes.create_order(
                    billing_routes.OrderRequest(plan="plus"),
                    current_user={"id": self.user_id},
                )
            self.assertEqual(ctx.exception.status_code, 409)

            record_consent(self.user_id, "offer", "checkout")
            with self.assertRaises(HTTPException) as ctx2:
                await billing_routes.create_order(
                    billing_routes.OrderRequest(plan="plus"),
                    current_user={"id": self.user_id},
                )
            # Провайдер не настроен: заказ не создаётся, платёж не инициируется.
            self.assertEqual(ctx2.exception.status_code, 503)


class AccountDeletionTests(unittest.TestCase):
    def setUp(self):
        self._cleanup()
        self.owner = create_user(f"{EMAIL_PREFIX}owner@users.example.invalid", "TestPass12345!")
        self.other = create_user(f"{EMAIL_PREFIX}other@users.example.invalid", "TestPass12345!")

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email LIKE ?", (EMAIL_PREFIX + "%",))
        conn.commit()
        conn.close()

    def test_deletes_related_data_and_keeps_other_account(self):
        slug = f"{EMAIL_PREFIX}product"
        upsert_analysis(
            user_id=self.owner,
            product_id=None,
            slug=slug,
            score=50,
            verdict="Подходит",
        )
        record_consent(self.owner, "offer", "registration")

        result = delete_user_account(self.owner)
        self.assertGreater(result["total"], 0)

        self.assertIsNone(get_user_by_id(self.owner))
        self.assertIsNone(get_analysis_record(self.owner, slug=slug))
        self.assertEqual(get_user_consents(self.owner), {})

        # Чужой аккаунт не затронут.
        self.assertIsNotNone(get_user_by_id(self.other))

    def test_second_deletion_is_safe(self):
        delete_user_account(self.owner)
        second = delete_user_account(self.owner)
        self.assertEqual(second["deleted"].get("users"), 0)


if __name__ == "__main__":
    unittest.main()
