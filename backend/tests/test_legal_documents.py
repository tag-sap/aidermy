import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.auth import create_user  # noqa: E402
from app.consents import (  # noqa: E402
    ConsentError,
    consent_history,
    get_user_consents,
    has_current_consent,
    record_consent,
)
from app.database import AIDERMY_DB, get_connection  # noqa: E402
from app.legal_documents import EXECUTOR, LEGAL_DOCUMENTS  # noqa: E402

EMAIL_PREFIX = "legal-test-"


class LegalDocumentsTests(unittest.TestCase):
    def test_documents_are_drafts_with_versions(self):
        for slug in ("requisites", "offer", "privacy", "payment", "delete-account"):
            doc = LEGAL_DOCUMENTS[slug]
            self.assertEqual(doc["status"], "draft")
            self.assertTrue(doc["version"].startswith("draft-"))

    def test_requisites_have_no_invented_data(self):
        self.assertEqual(EXECUTOR["inn"], "")
        self.assertEqual(EXECUTOR["phone"], "")
        self.assertEqual(EXECUTOR["email"], "aidermy@yandex.com")


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self._cleanup()
        self.user_id = create_user(f"{EMAIL_PREFIX}consent@example.com", "TestPass12345!")

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email LIKE ?", (EMAIL_PREFIX + "%",))
        conn.commit()
        conn.close()
        try:
            conn = get_connection(AIDERMY_DB)
            cur = conn.cursor()
            cur.execute("DELETE FROM user_consents WHERE user_id NOT IN (SELECT id FROM users)")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def test_consent_records_server_side_version(self):
        row = record_consent(self.user_id, "offer", "registration")
        self.assertEqual(row["consent_type"], "offer")
        self.assertEqual(row["document_version"], LEGAL_DOCUMENTS["offer"]["version"])
        self.assertTrue(has_current_consent(self.user_id, "offer"))
        self.assertEqual(len(consent_history(self.user_id)), 1)

    def test_client_cannot_submit_old_version(self):
        with self.assertRaises(ConsentError) as ctx:
            record_consent(self.user_id, "offer", "checkout", client_version="draft-0")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_unknown_consent_type_is_rejected(self):
        with self.assertRaises(ConsentError) as ctx:
            record_consent(self.user_id, "marketing", "checkout")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_existing_user_has_no_implicit_consent(self):
        self.assertFalse(has_current_consent(self.user_id, "offer"))
        self.assertEqual(get_user_consents(self.user_id), {})


class RegistrationConsentTests(unittest.IsolatedAsyncioTestCase):
    """Регистрация без согласия с офертой невозможна; согласие пишется сервером."""

    def setUp(self):
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email LIKE ?", (EMAIL_PREFIX + "%",))
        conn.commit()
        conn.close()
        try:
            conn = get_connection(AIDERMY_DB)
            cur = conn.cursor()
            cur.execute("DELETE FROM user_consents WHERE user_id NOT IN (SELECT id FROM users)")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _request(self):
        from starlette.requests import Request

        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/auth/register",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )

    async def test_registration_without_consent_is_rejected(self):
        from fastapi import HTTPException

        from app.auth_routes import UserRegister, register

        with self.assertRaises(HTTPException) as ctx:
            await register(
                UserRegister(
                    email=f"{EMAIL_PREFIX}noconsent@example.com",
                    password="TestPass12345!",
                    name="No Consent",
                    accept_offer=False,
                ),
                self._request(),
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # Пользователь не создан.
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id FROM users WHERE email = ?",
            (f"{EMAIL_PREFIX}noconsent@example.com",),
        ).fetchone()
        conn.close()
        self.assertIsNone(row)

    async def test_registration_with_consent_records_version(self):
        from app.auth_routes import UserRegister, register

        result = await register(
            UserRegister(
                email=f"{EMAIL_PREFIX}consent-ok@example.com",
                password="TestPass12345!",
                name="Consent OK",
                accept_offer=True,
            ),
            self._request(),
        )
        user_id = result["user"]["id"]
        self.assertTrue(has_current_consent(user_id, "offer"))
        history = consent_history(user_id)
        self.assertEqual(history[0]["context"], "registration")
        self.assertEqual(history[0]["document_version"], LEGAL_DOCUMENTS["offer"]["version"])


if __name__ == "__main__":
    unittest.main()
