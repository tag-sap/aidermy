# tests/test_community.py

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.profile_similarity import (
    ProfileSimilarityService,
    COMMUNITY_SIMILARITY_THRESHOLD,
    COMMUNITY_MIN_PERSONALIZED_REVIEWS,
)

PROFILE_A = {
    "skin_type": "Сухая",
    "age": "25–35",
    "concerns": ["Акне", "Пигментация"],
    "allergies": ["Отдушки"],
}
PROFILE_B = {
    "skin_type": "Жирная",
    "age": "45+",
    "concerns": ["Морщины"],
    "allergies": [],
}


class TestSimilarity(unittest.TestCase):
    def setUp(self):
        self.service = ProfileSimilarityService()

    def test_identical_profiles_high(self):
        self.assertEqual(self.service.similarity(PROFILE_A, PROFILE_A), 100)

    def test_different_profiles_low(self):
        self.assertLess(self.service.similarity(PROFILE_A, PROFILE_B), COMMUNITY_SIMILARITY_THRESHOLD)

    def test_threshold_configurable(self):
        self.assertGreaterEqual(COMMUNITY_SIMILARITY_THRESHOLD, 0)
        self.assertLessEqual(COMMUNITY_SIMILARITY_THRESHOLD, 100)


class TestCommunityService(unittest.TestCase):
    def setUp(self):
        import app.database as database
        import json

        self.tmp = tempfile.mktemp(suffix=".db")
        self._old_aidermy = database.AIDERMY_DB
        database.AIDERMY_DB = self.tmp

        conn = database.get_connection(database.AIDERMY_DB)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, name TEXT, "
            "skin_type TEXT, age TEXT, concerns TEXT, allergies TEXT)"
        )
        cur.execute(
            """CREATE TABLE reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL, slug TEXT DEFAULT '', rating INTEGER NOT NULL,
                text TEXT DEFAULT '', usage_duration TEXT DEFAULT '', tags TEXT DEFAULT '[]',
                visibility TEXT DEFAULT 'ANONYMOUS', profile_snapshot TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, product_id))"""
        )
        cur.execute(
            """CREATE TABLE review_helpful_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(review_id, user_id))"""
        )
        conn.commit()
        conn.close()

        from app.community_service import CommunityIntelligenceService

        self.service = CommunityIntelligenceService()

        conn = database.get_connection(database.AIDERMY_DB)
        cur = conn.cursor()
        for uid, profile in [(1, PROFILE_A), (2, PROFILE_B), (3, PROFILE_A)]:
            cur.execute(
                "INSERT INTO users (id, email, name, skin_type, age, concerns, allergies) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, f"u{uid}@t.com", f"User{uid}", profile["skin_type"], profile["age"],
                 ",".join(profile["concerns"]), ",".join(profile["allergies"])),
            )
            cur.execute(
                "INSERT INTO reviews (user_id, product_id, slug, rating, text, profile_snapshot) VALUES (?, 100, 'p', ?, ?, ?)",
                (uid, 5 - uid % 3, f"review {uid}", json.dumps(profile, ensure_ascii=False)),
            )
        conn.commit()
        conn.close()

    def tearDown(self):
        import app.database as database

        database.AIDERMY_DB = self._old_aidermy
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def _user(self, uid):
        return {"id": uid, "email": f"u{uid}@t.com", "name": f"User{uid}"}

    def test_community_rating_aggregation(self):
        rating = self.service.get_product_community_rating(100)
        self.assertEqual(rating["count"], 3)
        self.assertIsNotNone(rating["average"])

    def test_personalized_rating_below_minimum_unavailable(self):
        rating = self.service.get_personalized_community_rating(100, PROFILE_A)
        self.assertFalse(rating["available"])
        self.assertEqual(rating["count"], 2)

    def test_duplicate_review_upserts(self):
        self.service.create_review(self._user(1), 100, "p", 4, "updated", "", [], "ANONYMOUS", PROFILE_A)
        import app.database as database

        conn = database.get_connection(database.AIDERMY_DB)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM reviews WHERE user_id = 1 AND product_id = 100")
        n = cur.fetchone()["n"]
        conn.close()
        self.assertEqual(n, 1)

    def test_helpful_vote_own_review_rejected(self):
        self.assertEqual(self.service.toggle_helpful_vote(self._user(1), 1)["status"], "own_review")

    def test_helpful_vote_toggle(self):
        r1 = self.service.toggle_helpful_vote(self._user(2), 1)
        self.assertTrue(r1["helpful"])
        r2 = self.service.toggle_helpful_vote(self._user(2), 1)
        self.assertFalse(r2["helpful"])

    def test_delete_review(self):
        self.service.delete_review(self._user(1), 1)
        self.assertEqual(self.service.get_product_community_rating(100)["count"], 2)


if __name__ == "__main__":
    unittest.main()
