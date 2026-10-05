import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.database as database
from app.admin_routes import setup_admin_routes
from app.score_version import SCORE_ENGINE_VERSION


class AdminAnalysisHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "aidermy.db")
        self.products_path = os.path.join(self.temp_dir.name, "products.db")
        self.db_patch = patch.object(database, "AIDERMY_DB", self.db_path)
        self.products_patch = patch.object(database, "PRODUCTS_DB", self.products_path)
        self.db_patch.start()
        self.products_patch.start()
        self.addCleanup(self.products_patch.stop)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        self._create_databases()

        app = FastAPI()
        setup_admin_routes(app)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _connect(self, path=None):
        connection = sqlite3.connect(path or self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _database(self, path=None):
        connection = self._connect(path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _create_databases(self):
        with self._database() as conn:
            conn.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email TEXT,
                    name TEXT,
                    is_verified INTEGER,
                    created_at TEXT,
                    skin_type TEXT,
                    age TEXT,
                    concerns TEXT,
                    allergies TEXT,
                    custom_text TEXT,
                    profile_updated_at TEXT
                );
                CREATE TABLE user_profiles (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER UNIQUE,
                    name TEXT,
                    skin_type TEXT,
                    age TEXT,
                    concerns TEXT,
                    allergies TEXT,
                    custom_text TEXT,
                    quiz_answers TEXT,
                    skin_type_determined TEXT,
                    structured_profile TEXT,
                    updated_at TEXT
                );
                CREATE TABLE analysis (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER,
                    slug TEXT,
                    score INTEGER,
                    verdict TEXT,
                    summary TEXT,
                    report TEXT,
                    safe_ingredients TEXT,
                    caution_ingredients TEXT,
                    active_ingredients TEXT,
                    how_to_use TEXT,
                    expectations TEXT,
                    profile_snapshot TEXT,
                    deterministic_json TEXT,
                    score_engine_version TEXT,
                    report_score_engine_version TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    what_good TEXT,
                    what_caution TEXT
                );
                CREATE TABLE check_history (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    product_name TEXT,
                    skin_type TEXT,
                    score INTEGER,
                    verdict TEXT,
                    summary TEXT,
                    ai_report TEXT,
                    deleted_at TEXT,
                    created_at TEXT
                );
                CREATE TABLE shelf_products (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    product_id INTEGER
                );
                CREATE TABLE ingredient_claims (
                    id INTEGER PRIMARY KEY,
                    ingredient_id INTEGER,
                    property TEXT,
                    source_type TEXT
                );
                CREATE TABLE ingredients_catalog (
                    id INTEGER PRIMARY KEY,
                    knowledge_confidence REAL,
                    normalized_name TEXT,
                    inci_name TEXT,
                    research_status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE allergen_sensitizer (
                    ingredient_id INTEGER,
                    is_allergen INTEGER,
                    is_sensitizer INTEGER,
                    allergen_level TEXT
                );
                CREATE TABLE pending_products (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    product_name TEXT,
                    ingredients TEXT,
                    slug TEXT,
                    status TEXT,
                    created_at TEXT
                );
                INSERT INTO users (id, name, skin_type) VALUES (1, 'User', 'oily');
                INSERT INTO user_profiles (
                    user_id, name, skin_type, concerns, allergies, quiz_answers, structured_profile
                ) VALUES (1, 'User', 'oily', 'acne', '', '{"pores":"visible"}', '{}');
                """
            )
        with self._database(self.products_path) as conn:
            conn.execute(
                "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, ingredients TEXT, canonical_id INTEGER)"
            )
            conn.execute(
                "INSERT INTO products VALUES (20, 'Product', 'product', 'Aqua, Glycerin', NULL)"
            )

    def _seed_analysis(
        self,
        *,
        user_id=1,
        version="0.9.0",
        report_version="0.9.0",
        deterministic=None,
        score=33,
    ):
        deterministic = deterministic or {
            "score": 33,
            "verdict": "Не рекомендуется",
            "summary": "Old result",
            "normalized_ingredients": ["aqua", "glycerin"],
            "goal_evidence": [{"concern_id": "acne", "verdict": "supports"}],
        }
        with self._database() as conn:
            cursor = conn.execute(
                """
                INSERT INTO analysis (
                    user_id, product_id, slug, score, verdict, summary, report,
                    profile_snapshot, deterministic_json, score_engine_version,
                    report_score_engine_version, created_at
                ) VALUES (?, 20, 'product', ?, 'Не рекомендуется', 'Old result',
                          '[{"text":"cached report"}]', '{}', ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    user_id,
                    score,
                    json.dumps(deterministic, ensure_ascii=False),
                    version,
                    report_version,
                ),
            )
            return cursor.lastrowid

    def test_admin_status_counts_only_stale_analyses_and_requires_auth(self):
        self._seed_analysis(version="0.9.0")
        self._seed_analysis(
            version=SCORE_ENGINE_VERSION,
            report_version=SCORE_ENGINE_VERSION,
            deterministic={"score": 71, "score_engine_version": SCORE_ENGINE_VERSION},
            score=71,
        )
        self._seed_analysis(
            version=None,
            report_version=None,
            deterministic={"score": 71, "score_engine_version": SCORE_ENGINE_VERSION},
        )

        self.assertEqual(self.client.get("/api/admin/history/status").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/history/recalculate-stale").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/history/clear").status_code, 401)
        response = self.client.get(
            "/api/admin/history/status", auth=("admin", "aidermy2026")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stale_count"], 1)
        self.assertEqual(response.json()["score_engine_version"], SCORE_ENGINE_VERSION)

    def test_init_db_migrates_analysis_deterministic_json_column(self):
        with tempfile.TemporaryDirectory() as migration_dir:
            aidermy_path = os.path.join(migration_dir, "aidermy.db")
            products_path = os.path.join(migration_dir, "products.db")
            conn = sqlite3.connect(aidermy_path)
            try:
                conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
                conn.execute(
                    """
                    CREATE TABLE analysis (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        product_id INTEGER,
                        slug TEXT,
                        score INTEGER NOT NULL,
                        verdict TEXT NOT NULL,
                        summary TEXT,
                        report TEXT,
                        created_at TEXT,
                        expires_at TEXT
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            with patch.object(database, "AIDERMY_DB", aidermy_path), patch.object(
                database, "PRODUCTS_DB", products_path
            ):
                database.init_db()
                conn = sqlite3.connect(aidermy_path)
                try:
                    columns = {
                        row[1] for row in conn.execute("PRAGMA table_info(analysis)")
                    }
                finally:
                    conn.close()

        self.assertIn("deterministic_json", columns)

    def test_admin_history_controls_render_in_existing_history_tab(self):
        response = self.client.get("/admin", auth=("admin", "aidermy2026"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("История анализов", response.text)
        self.assertIn("Пересчитать устаревшие", response.text)
        self.assertIn("Очистить историю", response.text)
        self.assertIn("/api/admin/history/recalculate-stale", response.text)
        self.assertIn("/api/admin/history/clear", response.text)

    def test_recalculation_updates_only_stale_match_and_never_calls_ai(self):
        stale_id = self._seed_analysis()
        current_id = self._seed_analysis(
            version=SCORE_ENGINE_VERSION,
            report_version=SCORE_ENGINE_VERSION,
            deterministic={"score": 71, "score_engine_version": SCORE_ENGINE_VERSION},
            score=71,
        )
        result = {
            "score": 79,
            "confidence": 0.9,
            "verdict": "Подходит",
            "summary": "Current deterministic result",
            "normalized_ingredients": ["aqua", "glycerin"],
            "goal_evidence": [{"concern_id": "acne", "verdict": "neutral"}],
        }
        with patch(
            "app.ingredient_repository.IngredientRepository.get_canonical_knowledge_map",
            return_value={},
        ), patch(
            "app.shelf_service._deterministic_analysis", return_value=result
        ) as deterministic, patch(
            "app.services.generate_report_once", new_callable=AsyncMock
        ) as report, patch(
            "app.services.check_product_with_ai", new_callable=AsyncMock
        ) as check_ai:
            response = self.client.post(
                "/api/admin/history/recalculate-stale",
                auth=("admin", "aidermy2026"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {key: response.json()[key] for key in ("processed", "updated", "failed")},
            {"processed": 1, "updated": 1, "failed": 0},
        )
        deterministic.assert_called_once()
        report.assert_not_awaited()
        check_ai.assert_not_awaited()
        with self._database() as conn:
            refreshed = conn.execute(
                "SELECT * FROM analysis WHERE id = ?", (stale_id,)
            ).fetchone()
            untouched = conn.execute(
                "SELECT * FROM analysis WHERE id = ?", (current_id,)
            ).fetchone()
        self.assertEqual(refreshed["score"], 79)
        self.assertEqual(refreshed["verdict"], "Подходит")
        self.assertEqual(refreshed["score_engine_version"], SCORE_ENGINE_VERSION)
        self.assertEqual(
            json.loads(refreshed["deterministic_json"])["goal_evidence"],
            result["goal_evidence"],
        )
        self.assertEqual(refreshed["report_score_engine_version"], "0.9.0")
        self.assertEqual(refreshed["report"], '[{"text":"cached report"}]')
        self.assertEqual(untouched["score"], 71)
        self.assertEqual(untouched["score_engine_version"], SCORE_ENGINE_VERSION)

    def test_recalculation_reports_per_analysis_failures_and_is_repeat_safe(self):
        valid_id = self._seed_analysis()
        missing_user_id = self._seed_analysis(user_id=404)
        result = {
            "score": 79,
            "confidence": 0.9,
            "verdict": "Подходит",
            "summary": "Current deterministic result",
            "normalized_ingredients": ["aqua"],
            "goal_evidence": [],
        }
        with patch(
            "app.ingredient_repository.IngredientRepository.get_canonical_knowledge_map",
            return_value={},
        ), patch("app.shelf_service._deterministic_analysis", return_value=result):
            response = self.client.post(
                "/api/admin/history/recalculate-stale",
                auth=("admin", "aidermy2026"),
            )
            second = self.client.post(
                "/api/admin/history/recalculate-stale",
                auth=("admin", "aidermy2026"),
            )

        self.assertEqual(response.json()["processed"], 2)
        self.assertEqual(response.json()["updated"], 1)
        self.assertEqual(response.json()["failed"], 1)
        self.assertEqual(response.json()["errors"][0]["analysis_id"], missing_user_id)
        self.assertEqual(
            {key: second.json()[key] for key in ("processed", "updated", "failed")},
            {"processed": 1, "updated": 0, "failed": 1},
        )
        with self._database() as conn:
            self.assertEqual(
                conn.execute("SELECT score_engine_version FROM analysis WHERE id = ?", (valid_id,)).fetchone()[0],
                SCORE_ENGINE_VERSION,
            )

    def test_recalculation_preserves_saved_goal_evidence_if_engine_omits_it(self):
        analysis_id = self._seed_analysis()
        result = {
            "score": 79,
            "confidence": 0.9,
            "verdict": "Подходит",
            "summary": "Current deterministic result",
            "normalized_ingredients": ["aqua"],
        }
        with patch(
            "app.ingredient_repository.IngredientRepository.get_canonical_knowledge_map",
            return_value={},
        ), patch("app.shelf_service._deterministic_analysis", return_value=result):
            response = self.client.post(
                "/api/admin/history/recalculate-stale",
                auth=("admin", "aidermy2026"),
            )

        self.assertEqual(response.json()["updated"], 1)
        with self._database() as conn:
            saved = conn.execute(
                "SELECT deterministic_json FROM analysis WHERE id = ?", (analysis_id,)
            ).fetchone()
        self.assertEqual(
            json.loads(saved["deterministic_json"])["goal_evidence"],
            [{"concern_id": "acne", "verdict": "supports"}],
        )

    def test_clear_removes_only_user_history_and_preserves_user_data(self):
        self._seed_analysis()
        with self._database() as conn:
            conn.execute(
                "INSERT INTO check_history (user_id, product_name, score, ai_report) VALUES (1, 'User check', 50, 'report')"
            )
            conn.execute(
                "INSERT INTO check_history (user_id, product_name, score) VALUES (NULL, 'Guest check', 60)"
            )
            conn.execute("INSERT INTO shelf_products (user_id, product_id) VALUES (1, 20)")
            conn.execute("INSERT INTO ingredient_claims (ingredient_id, property) VALUES (1, 'hydration')")

        response = self.client.post(
            "/api/admin/history/clear", auth=("admin", "aidermy2026")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"analyses_deleted": 1, "legacy_history_deleted": 1})

        with self._database() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM analysis").fetchone()[0], 0)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM check_history WHERE user_id IS NOT NULL").fetchone()[0],
                0,
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM check_history").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users WHERE id = 1").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM user_profiles WHERE user_id = 1").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT quiz_answers FROM user_profiles WHERE user_id = 1").fetchone()[0], '{"pores":"visible"}')
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM shelf_products WHERE user_id = 1").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ingredient_claims").fetchone()[0], 1)
        with self._database(self.products_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)

        recreated = database.upsert_analysis(
            user_id=1,
            product_id=20,
            slug="product",
            score=68,
            verdict="Требует внимания",
            deterministic_json='{"score":68}',
        )
        self.assertEqual(recreated["score"], 68)

    def test_clear_is_transactional_and_second_execution_is_safe(self):
        self._seed_analysis()
        with self._database() as conn:
            conn.execute("INSERT INTO check_history (user_id, product_name, score) VALUES (1, 'Check', 50)")
            conn.execute(
                """
                CREATE TRIGGER reject_history_delete BEFORE DELETE ON check_history
                BEGIN SELECT RAISE(ABORT, 'blocked'); END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            database.clear_analysis_history()
        with self._database() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM analysis").fetchone()[0], 1)
            conn.execute("DROP TRIGGER reject_history_delete")

        first = database.clear_analysis_history()
        second = database.clear_analysis_history()
        self.assertEqual(first, {"analyses_deleted": 1, "legacy_history_deleted": 1})
        self.assertEqual(second, {"analyses_deleted": 0, "legacy_history_deleted": 0})


if __name__ == "__main__":
    unittest.main()
