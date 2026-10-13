"""Blocked/insufficient analyses persist with score=NULL (two-phase contract).

Проверяет, что NULL-балл не превращается в 0 ни при записи, ни при чтении.
"""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import (
    upsert_analysis,
    get_analysis_record,
    get_connection,
)

USER_ID = 91001
PRODUCT_ID = 999901
SLUG = "blocked-persistence-test-product"


class BlockedAnalysisPersistenceTests(unittest.TestCase):
    def _cleanup(self):
        conn = get_connection()
        conn.execute("DELETE FROM analysis WHERE user_id = ?", (USER_ID,))
        conn.execute("DELETE FROM users WHERE id = ?", (USER_ID,))
        conn.commit()
        conn.close()

    def _seed_user(self):
        conn = get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (USER_ID, "blocked-persist@example.invalid", "test-hash"),
        )
        conn.commit()
        conn.close()
        self.addCleanup(self._cleanup)

    def test_blocked_saved_with_null_score(self):
        self._seed_user()
        det = {
            "score": None,
            "phase1": {"status": "blocked"},
            "phase1_status": "blocked",
            "normalized_ingredients": ["fragrance"],
        }
        saved = upsert_analysis(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            slug=SLUG,
            score=None,
            verdict="Не рекомендовано",
            summary="Обычная оценка не рассчитана: первая фаза не пройдена.",
            deterministic_json=json.dumps(det, ensure_ascii=False),
        )
        self.assertIsNotNone(saved)
        self.assertIsNone(saved["score"])

        record = get_analysis_record(USER_ID, product_id=PRODUCT_ID)
        self.assertIsNotNone(record)
        self.assertIsNone(record["score"])
        self.assertEqual(record["verdict"], "Не рекомендовано")
        self.assertEqual(record["phase1_status"], "blocked")

    def test_insufficient_data_saved_with_null_score(self):
        self._seed_user()
        det = {
            "score": None,
            "phase1": {"status": "insufficient_data"},
            "phase1_status": "insufficient_data",
            "normalized_ingredients": [],
        }
        saved = upsert_analysis(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            slug=SLUG,
            score=None,
            verdict="Недостаточно данных",
            summary="Недостаточно данных для достоверной оценки.",
            deterministic_json=json.dumps(det, ensure_ascii=False),
        )
        self.assertIsNotNone(saved)
        self.assertIsNone(saved["score"])


if __name__ == "__main__":
    unittest.main()
