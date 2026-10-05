import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.score_version import SCORE_ENGINE_VERSION
from app.shelf_service import score_product
import app.database as database
from app.database import upsert_analysis


class ScoreEngineVersioningTests(unittest.TestCase):
    def test_new_analysis_stores_version_in_column_and_deterministic_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "analysis.db")
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            connection.execute(
                """CREATE TABLE analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER, product_id INTEGER, slug TEXT, score INTEGER, verdict TEXT,
                    summary TEXT, report TEXT, safe_ingredients TEXT, caution_ingredients TEXT,
                    active_ingredients TEXT, how_to_use TEXT, expectations TEXT, profile_snapshot TEXT,
                    deterministic_json TEXT, score_engine_version TEXT, report_score_engine_version TEXT,
                    created_at TEXT, expires_at TEXT, what_good TEXT, what_caution TEXT
                )"""
            )
            connection.commit()
            connection.close()

            def connect(_db_name):
                result = sqlite3.connect(db_path)
                result.row_factory = sqlite3.Row
                return result

            with patch("app.database.get_connection", side_effect=connect):
                saved = upsert_analysis(
                    user_id=1,
                    product_id=None,
                    slug="new-analysis",
                    score=63,
                    verdict="Требует внимания",
                    deterministic_json='{"normalized_ingredients":["aqua"]}',
                )
                connection = connect(db_path)
                connection.execute(
                    "UPDATE analysis SET report = ?, score_engine_version = ?, report_score_engine_version = ? WHERE id = ?",
                    ('[{"text":"old report"}]', "0.9.0", "0.9.0", saved["id"]),
                )
                connection.commit()
                connection.close()
                refreshed = database.update_analysis_deterministic_result(
                    1,
                    saved["id"],
                    {
                        "score": 81,
                        "confidence": 0.9,
                        "verdict": "Подходит",
                        "summary": "Новое deterministic summary.",
                        "normalized_ingredients": ["aqua"],
                        "goal_evidence": [{"concern": "acne", "verdict": "supports"}],
                    },
                    {"skin_type": "oily"},
                )

        self.assertEqual(refreshed["score"], 81)
        self.assertEqual(refreshed["score_engine_version"], SCORE_ENGINE_VERSION)
        self.assertEqual(refreshed["report_score_engine_version"], "0.9.0")
        self.assertEqual(refreshed["report"], '[{"text":"old report"}]')
        self.assertEqual(
            refreshed["deterministic"]["score_engine_version"],
            SCORE_ENGINE_VERSION,
        )
        self.assertEqual(
            refreshed["goal_evidence"],
            [{"concern": "acne", "verdict": "supports"}],
        )

    def test_current_analysis_is_not_recalculated(self):
        current = {
            "id": 10,
            "score": 72,
            "score_engine_version": SCORE_ENGINE_VERSION,
        }
        with patch("app.database.get_current_analysis", return_value=current), \
             patch("app.database.get_analysis_record") as get_record, \
             patch("app.shelf_service._deterministic_analysis") as calculate:
            score, analysis = score_product(
                {"id": 1},
                {"id": 20, "slug": "product", "ingredients": "Aqua"},
            )

        self.assertEqual(score, 72)
        self.assertIs(analysis, current)
        get_record.assert_not_called()
        calculate.assert_not_called()

    def test_stale_analysis_is_recalculated_and_preserves_goal_evidence(self):
        evidence = [{"concern": "acne", "verdict": "supports"}]
        stale = {
            "id": 11,
            "product_id": 20,
            "slug": "product",
            "score": 35,
            "score_engine_version": None,
            "report": '[{"text":"old report"}]',
            "report_score_engine_version": "0.9.0",
            "deterministic": {"normalized_ingredients": ["aqua"]},
        }
        deterministic = {
            "score": 81,
            "confidence": 0.9,
            "verdict": "Подходит",
            "summary": "Обновлённый результат.",
            "normalized_ingredients": ["aqua"],
            "goal_evidence": evidence,
        }
        refreshed = {
            **stale,
            "score": 81,
            "verdict": "Подходит",
            "score_engine_version": SCORE_ENGINE_VERSION,
            "deterministic": {**deterministic, "score_engine_version": SCORE_ENGINE_VERSION},
        }
        with patch("app.database.get_current_analysis", return_value=None), \
             patch("app.database.get_analysis_record", return_value=stale), \
             patch("app.ingredient_repository.IngredientRepository.get_canonical_knowledge_map", return_value={}), \
             patch("app.shelf_service._build_user_profile", return_value={"skin_type": "oily"}), \
             patch("app.shelf_service._deterministic_analysis", return_value=deterministic), \
             patch("app.services.check_product_with_ai", new_callable=AsyncMock) as check_with_ai, \
             patch("app.database.update_analysis_deterministic_result", return_value=refreshed) as save:
            score, analysis = score_product(
                {"id": 1},
                {"id": 20, "slug": "product", "ingredients": "Aqua"},
            )

        self.assertEqual(score, 81)
        self.assertEqual(analysis["score_engine_version"], SCORE_ENGINE_VERSION)
        self.assertEqual(save.call_args.args[2]["goal_evidence"], evidence)
        self.assertEqual(analysis["report_score_engine_version"], "0.9.0")
        check_with_ai.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
