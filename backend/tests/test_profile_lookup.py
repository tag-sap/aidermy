import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.database as database
from app.database import get_user_profile
from app.shelf_service import _find_history_score


class ProfileLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self._old = database.AIDERMY_DB
        database.AIDERMY_DB = self.tmp

        conn = database.get_connection(database.AIDERMY_DB)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, "
            "skin_type TEXT, age TEXT, concerns TEXT, allergies TEXT, custom_text TEXT)"
        )
        cur.execute(
            "CREATE TABLE user_profiles (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, "
            "skin_type TEXT, age TEXT, concerns TEXT, allergies TEXT, custom_text TEXT, "
            "quiz_answers TEXT, skin_type_determined TEXT, updated_at TEXT)"
        )
        cur.execute(
            "CREATE TABLE check_history (id INTEGER PRIMARY KEY, user_id INTEGER, product_name TEXT, "
            "skin_type TEXT, score INTEGER, verdict TEXT, summary TEXT, ingredients TEXT, "
            "slug TEXT, image_url TEXT, active_ingredients TEXT, how_to_use TEXT, "
            "expectations TEXT, safe_ingredients TEXT, caution_ingredients TEXT, "
            "profile_snapshot TEXT, created_at TEXT, deleted_at TEXT)"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.AIDERMY_DB = self._old
        try:
            if os.path.exists(self.tmp):
                os.remove(self.tmp)
        except PermissionError:
            pass

    def _seed(self):
        conn = database.get_connection(database.AIDERMY_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (id, email, name, skin_type) VALUES (1, 'u@t.com', 'U', NULL)"
        )
        cur.execute(
            "INSERT INTO user_profiles (user_id, name, skin_type) VALUES (1, 'U', 'Чувствительная')"
        )
        conn.commit()
        conn.close()

    def test_profile_reads_user_profiles_over_users(self):
        self._seed()
        profile = get_user_profile(1)
        self.assertEqual(profile["skin_type"], "Чувствительная")

    def test_profile_falls_back_to_users(self):
        conn = database.get_connection(database.AIDERMY_DB)
        cur = conn.cursor()
        cur.execute("INSERT INTO users (id, email, name, skin_type) VALUES (2, 'u2@t.com', 'U2', 'Нормальная')")
        conn.commit()
        conn.close()

        profile = get_user_profile(2)
        self.assertEqual(profile["skin_type"], "Нормальная")

    def test_history_score_skips_stale_skin_type(self):
        self._seed()
        conn = database.get_connection(database.AIDERMY_DB)
        cur = conn.cursor()
        # Устаревшая запись под «Нормальная» (не должна вернуться).
        cur.execute(
            "INSERT INTO check_history (user_id, product_name, skin_type, score, verdict, summary, slug) "
            "VALUES (1, 'Крем', 'Нормальная', 100, 'Подходит', 'нормальной кожи', 'cream')"
        )
        # Актуальная запись под «Чувствительная».
        cur.execute(
            "INSERT INTO check_history (user_id, product_name, skin_type, score, verdict, summary, slug) "
            "VALUES (1, 'Крем', 'Чувствительная', 60, 'Требует внимания', 'чувствительной кожи', 'cream')"
        )
        conn.commit()
        conn.close()

        user = {"id": 1}
        product = {"id": 1, "name": "Крем", "slug": "cream"}
        score, analysis = _find_history_score(user, product)
        self.assertEqual(score, 60)
        self.assertIn("чувствительной", analysis.get("summary", ""))


if __name__ == "__main__":
    unittest.main()
