import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.auth import (  # noqa: E402
    ensure_oauth_accounts_table,
    get_oauth_account,
    link_oauth_account,
    create_user_external,
    get_user_by_id,
)
from app.auth_routes import oauth, oauth_success_redirect  # noqa: E402
from app.database import get_connection, AIDERMY_DB  # noqa: E402

PROVIDER = "yandex"
ID_PREFIX = "test-yandex-"
EMAIL_PREFIX = "yandex-test-"


class YandexConfigTests(unittest.TestCase):
    def test_working_scope_is_preserved(self):
        """Рабочий scope зафиксирован: три scope давали invalid_scope у Яндекса."""
        client = oauth.create_client("yandex")
        self.assertEqual(client.client_kwargs.get("scope"), "login:info")

    def test_success_redirect_never_puts_token_in_query(self):
        url = oauth_success_redirect("https://aidermy.ru/", "JWT")
        self.assertEqual(url, "https://aidermy.ru/#token=JWT")
        # Query-вариант попадал в логи nginx и Referer.
        self.assertNotIn("?token=", url)
        self.assertNotIn("token=", url.split("#", 1)[0])

    def test_success_redirect_handles_missing_trailing_slash(self):
        self.assertEqual(
            oauth_success_redirect("https://aidermy.ru", "JWT"),
            "https://aidermy.ru/#token=JWT",
        )


class YandexIdentityTests(unittest.TestCase):
    def setUp(self):
        ensure_oauth_accounts_table()
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT user_id FROM oauth_accounts WHERE provider = ? AND provider_user_id LIKE ?",
            (PROVIDER, ID_PREFIX + "%"),
        ).fetchall()
        user_ids = [r["user_id"] for r in rows]
        cur.execute(
            "DELETE FROM oauth_accounts WHERE provider = ? AND provider_user_id LIKE ?",
            (PROVIDER, ID_PREFIX + "%"),
        )
        for uid in user_ids:
            cur.execute(
                "DELETE FROM users WHERE id = ? AND email LIKE ?",
                (uid, EMAIL_PREFIX + "%"),
            )
        # Пользователи, созданные тестом, но не связанные с oauth_accounts
        # (например, проверка флага подтверждения email).
        cur.execute("DELETE FROM users WHERE email LIKE ?", (EMAIL_PREFIX + "%",))
        conn.commit()
        conn.close()

    def _make_user(self, suffix: str) -> int:
        return create_user_external(
            f"{EMAIL_PREFIX}{suffix}@users.example.invalid",
            f"Yandex Test {suffix}",
            email_verified=False,
        )

    def test_email_from_provider_is_not_marked_verified(self):
        uid = self._make_user("verify")
        user = get_user_by_id(uid)
        self.assertIsNotNone(user)
        self.assertFalse(user.get("is_verified"))
        self.assertIsNone(user.get("email_verified_at"))

    def test_repeat_login_reuses_same_local_user(self):
        uid = self._make_user("repeat")
        link_oauth_account(PROVIDER, ID_PREFIX + "repeat", uid, "")
        account = get_oauth_account(PROVIDER, ID_PREFIX + "repeat")
        self.assertIsNotNone(account)
        self.assertEqual(account["user_id"], uid)

        # Повторный вход: связь обновляется, новый пользователь не создаётся.
        link_oauth_account(PROVIDER, ID_PREFIX + "repeat", uid, "")
        account2 = get_oauth_account(PROVIDER, ID_PREFIX + "repeat")
        self.assertEqual(account2["user_id"], uid)

        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        count = cur.execute(
            "SELECT COUNT(*) AS c FROM oauth_accounts WHERE provider = ? AND provider_user_id = ?",
            (PROVIDER, ID_PREFIX + "repeat"),
        ).fetchone()["c"]
        conn.close()
        self.assertEqual(count, 1)

    def test_identity_is_provider_id_not_email(self):
        # Один и тот же email не должен склеивать две разные внешние идентичности.
        uid_a = self._make_user("a")
        uid_b = self._make_user("b")
        link_oauth_account(PROVIDER, ID_PREFIX + "a", uid_a, "same@example.invalid")
        link_oauth_account(PROVIDER, ID_PREFIX + "b", uid_b, "same@example.invalid")

        self.assertEqual(get_oauth_account(PROVIDER, ID_PREFIX + "a")["user_id"], uid_a)
        self.assertEqual(get_oauth_account(PROVIDER, ID_PREFIX + "b")["user_id"], uid_b)


if __name__ == "__main__":
    unittest.main()
