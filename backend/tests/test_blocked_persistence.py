# -*- coding: utf-8 -*-
"""Персистентность результата Phase 1 с единым каноническим score."""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import (
    upsert_analysis,
    get_analysis_record,
    get_current_analysis,
    get_connection,
    _analysis_to_dict,
)
from app.shelf_service import score_product

USER_ID = 910001
PRODUCT_ID = 999901
SLUG = "blocked-persist-test"


def _deterministic(phase1_status="blocked"):
    return {
        "score": 37 if phase1_status == "blocked" else None,
        "phase1": {"status": phase1_status},
        "phase1_status": phase1_status,
        "recommendation_status": "Не рекомендовано" if phase1_status == "blocked" else "Недостаточно данных",
        "normalized_ingredients": ["fragrance"],
    }


class BlockedPersistenceTests(unittest.TestCase):
    def _cleanup(self):
        conn = get_connection()
        conn.execute("DELETE FROM analysis WHERE user_id = ?", (USER_ID,))
        conn.execute("DELETE FROM users WHERE id = ?", (USER_ID,))
        conn.commit()
        conn.close()

    def _seed_user(self):
        conn = get_connection()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, password_hash TEXT, "
            "name TEXT, profile_updated_at TIMESTAMP)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (USER_ID, "blocked-persist@example.invalid", "test-hash"),
        )
        conn.commit()
        conn.close()
        self.addCleanup(self._cleanup)

    def test_blocked_saved_with_canonical_score(self):
        self._seed_user()
        saved = upsert_analysis(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            slug=SLUG,
            score=37,
            verdict="Не рекомендовано",
            summary="первая фаза не пройдена",
            deterministic_json=json.dumps(_deterministic(), ensure_ascii=False),
        )
        self.assertIsNotNone(saved)
        self.assertEqual(saved["score"], 37)
        self.assertEqual(saved["phase1_status"], "blocked")

    def test_insufficient_data_saved_with_null_score(self):
        self._seed_user()
        saved = upsert_analysis(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            slug=SLUG,
            score=None,
            verdict="Недостаточно данных",
            summary="недостаточно данных",
            deterministic_json=json.dumps(_deterministic("insufficient_data"), ensure_ascii=False),
        )
        self.assertIsNone(saved["score"])
        self.assertEqual(saved["phase1_status"], "insufficient_data")

    def test_read_restores_phase1_status(self):
        self._seed_user()
        upsert_analysis(
            user_id=USER_ID, product_id=PRODUCT_ID, slug=SLUG,
            score=37, verdict="Не рекомендовано", summary="блок",
            deterministic_json=json.dumps(_deterministic(), ensure_ascii=False),
        )
        record = get_analysis_record(USER_ID, product_id=PRODUCT_ID)
        self.assertEqual(record["score"], 37)
        self.assertEqual(record["phase1_status"], "blocked")
        self.assertEqual(record["recommendation_status"], "Не рекомендовано")

    def test_current_analysis_returns_blocked(self):
        self._seed_user()
        upsert_analysis(
            user_id=USER_ID, product_id=PRODUCT_ID, slug=SLUG,
            score=37, verdict="Не рекомендовано", summary="блок",
            deterministic_json=json.dumps(_deterministic(), ensure_ascii=False),
        )
        cur = get_current_analysis(USER_ID, product_id=PRODUCT_ID)
        self.assertIsNotNone(cur)
        self.assertEqual(cur["score"], 37)
        self.assertEqual(cur["phase1_status"], "blocked")

    def test_score_product_returns_blocked_analysis(self):
        self._seed_user()
        upsert_analysis(
            user_id=USER_ID, product_id=PRODUCT_ID, slug=SLUG,
            score=37, verdict="Не рекомендовано", summary="блок",
            deterministic_json=json.dumps(_deterministic(), ensure_ascii=False),
        )
        user = {"id": USER_ID}
        product = {"id": PRODUCT_ID, "slug": SLUG, "name": "BlockedProd", "ingredients": "Fragrance"}
        score, analysis = score_product(user, product)
        self.assertEqual(score, 37)
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.get("phase1_status"), "blocked")


if __name__ == "__main__":
    unittest.main()
