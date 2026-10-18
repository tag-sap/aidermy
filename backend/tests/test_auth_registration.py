import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.auth import get_password_hash, verify_password  # noqa: E402


class PasswordHashingTests(unittest.TestCase):
    def test_hash_is_salted_and_verifiable(self):
        h1 = get_password_hash("TestPass12345!")
        h2 = get_password_hash("TestPass12345!")
        self.assertNotEqual(h1, h2, "соль должна делать хеши разными")
        self.assertTrue(verify_password("TestPass12345!", h1))
        self.assertTrue(verify_password("TestPass12345!", h2))
        self.assertFalse(verify_password("wrong", h1))

    def test_hash_does_not_contain_plaintext(self):
        h = get_password_hash("SuperSecret123")
        self.assertNotIn("SuperSecret123", h)


class EmailVerificationPolicyTests(unittest.TestCase):
    """Подтверждение email требуется только когда оно реально настроено."""

    def test_requires_verification_when_smtp_configured(self):
        with patch.dict(os.environ, {"EMAIL_USER": "a@b.c", "EMAIL_PASSWORD": "x"}, clear=False):
            os.environ.pop("REQUIRE_EMAIL_VERIFICATION", None)
            from app.auth_routes import _require_email_verification
            self.assertTrue(_require_email_verification())

    def test_no_verification_without_smtp(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMAIL_USER", None)
            os.environ.pop("EMAIL_PASSWORD", None)
            os.environ.pop("REQUIRE_EMAIL_VERIFICATION", None)
            from app.auth_routes import _require_email_verification, _email_delivery_configured
            self.assertFalse(_email_delivery_configured())
            self.assertFalse(_require_email_verification())

    def test_explicit_flag_wins(self):
        with patch.dict(os.environ, {"REQUIRE_EMAIL_VERIFICATION": "true"}, clear=False):
            from app.auth_routes import _require_email_verification
            self.assertTrue(_require_email_verification())
        with patch.dict(os.environ, {"REQUIRE_EMAIL_VERIFICATION": "false"}, clear=False):
            from app.auth_routes import _require_email_verification
            self.assertFalse(_require_email_verification())


if __name__ == "__main__":
    unittest.main()
