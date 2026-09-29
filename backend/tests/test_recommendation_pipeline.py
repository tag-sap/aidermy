"""Тесты целевого recommendation pipeline.

Проверяют, что рекомендации состоят только из полностью завершённых персональных
Match: category hard filter применяется ДО retrieval, PPM не попадает в UI, продукт
без завершённого Match пропускается, а pipeline продолжает обработку кандидатов
той же категории до 3 готовых результатов.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.shelf_service import recommend_products


USER = {
    "id": 1,
    "skin_type": "Чувствительная",
    "age": "25–35",
    "concerns": "Покраснения",
    "allergies": "",
    "custom_text": "",
}


_PID = [0]


def _product(category, name, slug, ingredients):
    _PID[0] += 1
    return {
        "id": _PID[0],
        "name": name,
        "slug": slug,
        "category": category,
        "brand": "",
        "ingredients": ingredients,
    }


class VectorCategoryFilterTests(unittest.TestCase):
    def test_category_hard_filter_before_retrieval(self):
        products = [
            {"id": 1, "name": "Гель для умывания", "slug": "clean", "category": "Очищение", "brand": "", "ingredients": "Aqua, Glycerin"},
            {"id": 2, "name": "Тоник", "slug": "toner", "category": "Тонизирование", "brand": "", "ingredients": "Aqua, Glycerin"},
            {"id": 3, "name": "Крем", "slug": "cream", "category": "Крем", "brand": "", "ingredients": "Aqua, Glycerin"},
        ]
        captured = {}

        def fake_search(weights, k, predicate, allowed_ids=None):
            captured["allowed_ids"] = list(allowed_ids) if allowed_ids is not None else None
            allowed = set(allowed_ids) if allowed_ids is not None else set()
            return [(p["id"], 1.0) for p in products if p["id"] in allowed and predicate(p["id"])]

        from app import vector_retrieval
        with patch("app.database.get_all_canonical_products", return_value=products), \
             patch("app.decision_engine.profile_weights", return_value={}), \
             patch("app.vector_retrieval.VECTOR_INDEX") as idx_mock:
            idx_mock.is_loaded.return_value = True
            idx_mock.search.side_effect = fake_search
            result = vector_retrieval.retrieve_candidates(
                {"skin_type": "Чувствительная", "allergies": []},
                "face",
                "Тонизирование",
                set(),
            )
        # Только продукты категории «Тонизирование» (id=2) попадают в retrieval.
        self.assertEqual(captured["allowed_ids"], [2])
        self.assertEqual([r["slug"] for r in result], ["toner"])


class CompletedMatchPipelineTests(unittest.TestCase):
    def _run(self, candidates, scores_by_ingredients, interactions=None):
        """Запускает recommend_products с контролем детерминированного скора."""
        def det_analysis(profile, ingredients, knowledge=None, interactions=None):
            s = scores_by_ingredients.get(ingredients)
            if s is None:
                return None
            return {"score": s, "confidence": 0.8, "verdict": "Подходит", "summary": ""}

        with patch("app.vector_retrieval.VECTOR_RETRIEVAL_ENABLED", False), \
             patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._load_shelf_products", return_value=[]), \
             patch("app.shelf_service._find_history_score", return_value=(None, None)), \
             patch("app.shelf_service._build_match_interactions", return_value=(interactions or [])), \
             patch("app.shelf_service._deterministic_analysis", side_effect=det_analysis):
            return asyncio.run(recommend_products(USER, "face", "Тонизирование", set()))

    def test_only_completed_matches_returned(self):
        candidates = [
            _product("Тонизирование", "Тоник A", "toner-a", "Aqua, Glycerin, A"),
            _product("Тонизирование", "Тоник B", "toner-b", "Aqua, Glycerin, B"),
        ]
        recs = self._run(candidates, {"Aqua, Glycerin, A": 80})
        self.assertEqual([r["slug"] for r in recs], ["toner-a"])

    def test_pipeline_continues_after_failed_match(self):
        candidates = [
            _product("Тонизирование", "Тоник A", "toner-a", "Aqua, Glycerin, A"),
            _product("Тонизирование", "Тоник B", "toner-b", "Aqua, Glycerin, B"),
            _product("Тонизирование", "Тоник C", "toner-c", "Aqua, Glycerin, C"),
        ]
        recs = self._run(candidates, {"Aqua, Glycerin, B": 70, "Aqua, Glycerin, C": 65})
        self.assertEqual([r["slug"] for r in recs], ["toner-b", "toner-c"])

    def test_pipeline_returns_up_to_3(self):
        candidates = [
            _product("Тонизирование", "Тоник A", "toner-a", "Aqua, Glycerin, A"),
            _product("Тонизирование", "Тоник B", "toner-b", "Aqua, Glycerin, B"),
            _product("Тонизирование", "Тоник C", "toner-c", "Aqua, Glycerin, C"),
            _product("Тонизирование", "Тоник D", "toner-d", "Aqua, Glycerin, D"),
        ]
        recs = self._run(candidates, {
            "Aqua, Glycerin, A": 90, "Aqua, Glycerin, B": 80,
            "Aqua, Glycerin, C": 70, "Aqua, Glycerin, D": 60,
        })
        self.assertEqual(len(recs), 3)

    def test_returns_2_completed_not_raw_third(self):
        candidates = [
            _product("Тонизирование", "Тоник A", "toner-a", "Aqua, Glycerin, A"),
            _product("Тонизирование", "Тоник B", "toner-b", "Aqua, Glycerin, B"),
            _product("Тонизирование", "Тоник C", "toner-c", "Aqua, Glycerin, C"),
        ]
        recs = self._run(candidates, {"Aqua, Glycerin, A": 85, "Aqua, Glycerin, B": 75})
        self.assertEqual([r["slug"] for r in recs], ["toner-a", "toner-b"])

    def test_no_completed_matches_no_fallback(self):
        candidates = [
            _product("Тонизирование", "Тоник A", "toner-a", "Aqua, Glycerin, A"),
            _product("Тонизирование", "Тоник B", "toner-b", "Aqua, Glycerin, B"),
        ]
        recs = self._run(candidates, {})
        self.assertEqual(recs, [])

    def test_interactions_passed_to_deterministic_analysis(self):
        candidates = [
            _product("Тонизирование", "Тоник A", "toner-a", "Aqua, Glycerin, A"),
        ]
        captured = {}

        def det_analysis(profile, ingredients, knowledge=None, interactions=None):
            captured["interactions"] = interactions
            return {"score": 80, "confidence": 0.8, "verdict": "Подходит", "summary": ""}

        with patch("app.vector_retrieval.VECTOR_RETRIEVAL_ENABLED", False), \
             patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._load_shelf_products", return_value=[]), \
             patch("app.shelf_service._find_history_score", return_value=(None, None)), \
             patch("app.shelf_service._build_match_interactions", return_value=[{"type": "internal"}]), \
             patch("app.shelf_service._deterministic_analysis", side_effect=det_analysis):
            asyncio.run(recommend_products(USER, "face", "Тонизирование", set()))
        self.assertEqual(captured["interactions"], [{"type": "internal"}])

    def test_recommendation_result_has_no_ppm_fields(self):
        candidates = [
            _product("Тонизирование", "Тоник A", "toner-a", "Aqua, Glycerin, A"),
        ]
        recs = self._run(candidates, {"Aqua, Glycerin, A": 80})
        self.assertEqual(len(recs), 1)
        for bad in ("vector", "coverage", "representation_type", "unknown_ingredients", "_retrieval_score"):
            self.assertNotIn(bad, recs[0])


if __name__ == "__main__":
    unittest.main()
