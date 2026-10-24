"""Shelf capacity and billing idempotency (no network or LLM calls)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import (  # noqa: E402
    AIDERMY_DB,
    ShelfLimitError,
    add_product_to_shelf,
    change_balance,
    get_balance,
    get_connection,
    get_user_shelf,
)
from app.plans import SHELF_LIMITS
from app.shelf_refresh import refresh_quote  # noqa: E402


class ShelfCapacityTests(unittest.TestCase):
    def setUp(self):
        self.emails = []
        self.user_id = self._make_user("free")

    def tearDown(self):
        conn = get_connection(AIDERMY_DB)
        with conn:
            for email in self.emails:
                row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
                if row:
                    conn.execute("DELETE FROM shelf_products WHERE user_id = ?", (row["id"],))
                    conn.execute("DELETE FROM balance_transactions WHERE user_id = ?", (row["id"],))
                conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.close()

    def _make_user(self, plan: str) -> int:
        email = f"shelf-capacity-{plan}-{os.getpid()}-{len(self.emails)}@users.example.invalid"
        self.emails.append(email)
        conn = get_connection(AIDERMY_DB)
        with conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, name, balance, plan) VALUES (?, '', '', 20, ?)",
                (email, plan),
            )
            return int(cur.lastrowid)

    def _fill(self, count: int, start: int = 1) -> None:
        for product_id in range(start, start + count):
            add_product_to_shelf(self.user_id, product_id)

    def test_free_is_limited_to_five_products(self):
        self._fill(5)
        with self.assertRaises(ShelfLimitError):
            add_product_to_shelf(self.user_id, 6)
        self.assertEqual(len(get_user_shelf(self.user_id)), 5)

    def test_plus_and_pro_limits(self):
        self.assertEqual(SHELF_LIMITS, {"free": 5, "plus": 10, "pro": 15})
        for plan, limit in (("plus", 10), ("pro", 15)):
            user_id = self._make_user(plan)
            for product_id in range(1, limit + 1):
                add_product_to_shelf(user_id, product_id)
            with self.assertRaises(ShelfLimitError):
                add_product_to_shelf(user_id, limit + 1)

    def test_duplicate_retry_is_safe_even_at_capacity(self):
        self._fill(5)
        first = add_product_to_shelf(self.user_id, 5)
        second = add_product_to_shelf(self.user_id, 5)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(get_user_shelf(self.user_id)), 5)

    def test_downgrade_keeps_products_and_blocks_new_ones(self):
        user_id = self._make_user("pro")
        for product_id in range(1, 13):
            add_product_to_shelf(user_id, product_id)
        conn = get_connection(AIDERMY_DB)
        with conn:
            conn.execute("UPDATE users SET plan = 'free' WHERE id = ?", (user_id,))
        conn.close()
        self.assertEqual(len(get_user_shelf(user_id)), 12)
        with self.assertRaises(ShelfLimitError):
            add_product_to_shelf(user_id, 13)

    def test_balance_is_idempotent_and_never_negative(self):
        first = change_balance(self.user_id, -1, "evaluation_check", "test", idempotency_key="same-key")
        second = change_balance(self.user_id, -1, "evaluation_check", "test", idempotency_key="same-key")
        self.assertEqual(first, 19)
        self.assertEqual(second, 19)
        self.assertIsNone(change_balance(self.user_id, -100, "evaluation_check", "test"))
        self.assertEqual(get_balance(self.user_id)["balance"], 19)

    def test_refresh_quote_is_fixed_and_cheaper_than_individual(self):
        self.assertEqual(refresh_quote(0), 0)
        self.assertEqual(refresh_quote(1), 1)
        self.assertEqual(refresh_quote(5), 4)
        self.assertLess(refresh_quote(15), 15)


if __name__ == "__main__":
    unittest.main()
