# tests/test_analysis_lifecycle.py
# Фаза 2 — жизненный цикл актуальности User Analysis.
#
# Инварианты:
#   - non-shelf: TTL 7 дней → expired → get_current_analysis = None;
#   - profile change: created_at < profile_updated_at → obsolete → None;
#   - shelf: ttl_days=None → бессрочный (expires_at = NULL, TTL не применяется);
#   - shelf → remove: set_analysis_expiry → снова ограниченный TTL.
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import (
    upsert_analysis,
    get_current_analysis,
    set_analysis_expiry,
    touch_user_profile_updated_at,
    get_connection,
    AIDERMY_DB,
)
from app.score_version import SCORE_ENGINE_VERSION

USER_ID = 1
PRODUCT_ID = 3766
SLUG = "the-ordinary-aha-30-bha-2-peeling-solution-7"


def _set_created_at(conn, user_id, product_id, ts):
    conn.execute(
        "UPDATE analysis SET created_at = ? WHERE user_id = ? AND product_id = ?",
        (ts, user_id, product_id),
    )


class AnalysisLifecycleTests(unittest.TestCase):
    def _remove_test_user(self):
        conn = get_connection(AIDERMY_DB)
        conn.execute("DELETE FROM users WHERE id = ?", (USER_ID,))
        conn.commit()
        conn.close()

    def _seed(self, ttl_days=7):
        conn = get_connection(AIDERMY_DB)
        inserted = conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (USER_ID, "lifecycle-test@example.invalid", "test-only-hash"),
        ).rowcount
        conn.commit()
        conn.close()
        if inserted:
            self.addCleanup(self._remove_test_user)
        det = {"score": 64, "verdict": "Требует внимания", "normalized_ingredients": ["aqua", "glycerin"]}
        return upsert_analysis(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            slug=SLUG,
            score=64,
            verdict="Требует внимания",
            summary="резюме",
            deterministic_json=json.dumps(det, ensure_ascii=False),
            ttl_days=ttl_days,
        )

    def test_current_analysis_returned(self):
        saved = self._seed()
        cur = get_current_analysis(USER_ID, product_id=PRODUCT_ID)
        self.assertIsNotNone(cur)
        self.assertEqual(cur["id"], saved["id"])
        self.assertEqual(cur["score"], 64)
        self.assertEqual(cur["score_engine_version"], SCORE_ENGINE_VERSION)
        self.assertEqual(cur["deterministic"]["score_engine_version"], SCORE_ENGINE_VERSION)

    def test_stale_score_engine_version_is_not_current(self):
        self._seed()
        conn = get_connection(AIDERMY_DB)
        conn.execute(
            "UPDATE analysis SET score_engine_version = ? WHERE user_id = ? AND product_id = ?",
            ("0.9.0", USER_ID, PRODUCT_ID),
        )
        conn.commit()
        conn.close()
        self.assertIsNone(get_current_analysis(USER_ID, product_id=PRODUCT_ID))

    def test_ttl_expired_returns_none(self):
        self._seed(ttl_days=7)
        conn = get_connection(AIDERMY_DB)
        conn.execute(
            "UPDATE analysis SET expires_at = '2000-01-01 00:00:00' WHERE user_id = ? AND product_id = ?",
            (USER_ID, PRODUCT_ID),
        )
        conn.commit()
        conn.close()
        self.assertIsNone(get_current_analysis(USER_ID, product_id=PRODUCT_ID))

    def test_profile_change_returns_none(self):
        self._seed(ttl_days=7)
        conn = get_connection(AIDERMY_DB)
        _set_created_at(conn, USER_ID, PRODUCT_ID, "2000-01-01 00:00:00")
        conn.commit()
        conn.close()
        touch_user_profile_updated_at(USER_ID)  # profile_updated_at = NOW > created_at
        self.assertIsNone(get_current_analysis(USER_ID, product_id=PRODUCT_ID))

    def test_shelf_ttl_none_is_infinite(self):
        saved = self._seed(ttl_days=None)
        cur = get_current_analysis(USER_ID, product_id=PRODUCT_ID)
        self.assertIsNotNone(cur)
        self.assertEqual(cur["id"], saved["id"])
        self.assertIsNone(cur.get("expires_at"))

    def test_shelf_remove_sets_ttl(self):
        self._seed(ttl_days=None)
        set_analysis_expiry(USER_ID, PRODUCT_ID, days=7)
        cur = get_current_analysis(USER_ID, product_id=PRODUCT_ID)
        self.assertIsNotNone(cur)  # ещё не истёк, но TTL появился
        self.assertIsNotNone(cur.get("expires_at"))


if __name__ == "__main__":
    unittest.main()
