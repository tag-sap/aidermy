import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Тесты должны использовать то же хранилище, что и приложение (Postgres из .env),
# иначе guest_sessions/users окажутся в разных БД.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.database import AIDERMY_DB, get_connection  # noqa: E402
from app.guest_service import (  # noqa: E402
    GuestSessionError,
    claim_guest_result,
    consume_guest_check,
    create_guest_session,
    finalize_guest_claim,
    get_guest_result,
    load_guest_session,
    refund_guest_check,
    store_guest_result,
)

PROFILE = {
    "age": "25-35",
    "concerns": ["dryness"],
    "allergies": [],
    "custom_text": "",
    "quiz_answers": None,
    "skin_type_determined": None,
    "structured": {
        "skin_type": "dry",
        "concerns": ["dryness"],
        "therapy": [],
        "procedures": [],
    },
}
EMAIL_PREFIX = "guest-flow-test-"


class GuestFlowTests(unittest.TestCase):
    def setUp(self):
        self._session_ids = []
        self._user_ids = []
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    # --- helpers ---
    def _cleanup(self):
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        for sid in self._session_ids:
            cur.execute("DELETE FROM guest_sessions WHERE id = ?", (sid,))
        cur.execute("DELETE FROM users WHERE email LIKE ?", (EMAIL_PREFIX + "%",))
        conn.commit()
        conn.close()
        self._session_ids = []
        self._user_ids = []

    def _session(self, profile=None):
        token = create_guest_session(profile or PROFILE)["guest_token"]
        self._session_ids.append(load_guest_session(token)["id"])
        return token

    def _user(self, suffix):
        from app.auth import create_user_external

        uid = create_user_external(f"{EMAIL_PREFIX}{suffix}@users.example.invalid", "Guest Test")
        self._user_ids.append(uid)
        return uid

    # --- tests ---
    def test_profile_is_required(self):
        for bad in ({}, {"skin_type": "dry"}, {"structured": {}}):
            with self.assertRaises(GuestSessionError) as ctx:
                create_guest_session(bad)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_session_created_for_completed_profile(self):
        token = self._session()
        self.assertTrue(token)
        session = load_guest_session(token)
        self.assertIsNone(session["check_used_at"])

    def test_only_one_check_per_session(self):
        token = self._session()
        consume_guest_check(token)
        with self.assertRaises(GuestSessionError) as ctx:
            consume_guest_check(token)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_used_session_cannot_be_restored(self):
        """Сервер не даёт «продолжить» сеанс после израсходованной проверки."""
        token = self._session()
        consume_guest_check(token)
        for _ in range(3):
            with self.assertRaises(GuestSessionError) as ctx:
                consume_guest_check(token)
            self.assertEqual(ctx.exception.status_code, 409)

    def test_unknown_token_is_rejected(self):
        with self.assertRaises(GuestSessionError) as ctx:
            consume_guest_check("stale-token-from-previous-visit")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_session_is_rejected(self):
        token = self._session()
        session = load_guest_session(token)
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        cur.execute(
            "UPDATE guest_sessions SET expires_at = ? WHERE id = ?",
            (datetime.now(timezone.utc) - timedelta(minutes=1), session["id"]),
        )
        conn.commit()
        conn.close()
        with self.assertRaises(GuestSessionError) as ctx:
            consume_guest_check(token)
        self.assertEqual(ctx.exception.status_code, 410)

    def test_refund_allows_retry_after_technical_failure(self):
        token = self._session()
        session = consume_guest_check(token)
        refund_guest_check(session["id"])
        again = consume_guest_check(token)
        self.assertEqual(again["id"], session["id"])

    def test_result_roundtrip(self):
        token = self._session()
        session = consume_guest_check(token)
        store_guest_result(session["id"], {"score": 61, "verdict": "Подходит", "product_name": "X"})
        data = get_guest_result(token)
        self.assertEqual(data["score"], 61)
        self.assertEqual(data["_session"]["id"], session["id"])

    def test_claim_is_idempotent_and_links_single_analysis(self):
        token = self._session()
        session = consume_guest_check(token)
        store_guest_result(session["id"], {"score": 61, "verdict": "Подходит"})
        uid = self._user("owner")

        first = claim_guest_result(token, uid)
        self.assertFalse(first["already_claimed"])
        finalize_guest_claim(first["session_id"], 777001)

        second = claim_guest_result(token, uid)
        self.assertTrue(second["already_claimed"])
        self.assertEqual(second["analysis_id"], 777001)

    def test_claim_by_another_user_is_rejected(self):
        token = self._session()
        session = consume_guest_check(token)
        store_guest_result(session["id"], {"score": 61, "verdict": "Подходит"})
        owner = self._user("owner2")
        stranger = self._user("stranger2")

        claim_guest_result(token, owner)
        with self.assertRaises(GuestSessionError) as ctx:
            claim_guest_result(token, stranger)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_claim_without_result_is_rejected(self):
        token = self._session()
        consume_guest_check(token)
        with self.assertRaises(GuestSessionError) as ctx:
            claim_guest_result(token, self._user("empty"))
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
