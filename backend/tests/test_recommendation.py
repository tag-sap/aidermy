import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.shelf_service import (
    _aggregate_scores,
    compute_cabinet_compatibility,
    is_product_compatible,
    recommend_products,
    compute_product_compatibility,
)


USER = {
    "id": 1,
    "skin_type": "Чувствительная",
    "age": "25–35",
    "concerns": "Покраснения",
    "allergies": "",
    "custom_text": "",
}


_PID = [0]


def _product(category, name, slug, ingredients="Aqua, Glycerin"):
    _PID[0] += 1
    return {"id": _PID[0], "name": name, "slug": slug, "category": category, "brand": "", "ingredients": ingredients}


class CompatibilityTests(unittest.TestCase):
    def test_cleanser_not_compatible_with_moisturizer(self):
        p = _product("Крем", "Увлажняющий крем", "cream-1")
        ok, _reason = is_product_compatible(p, "face", "Очищение")
        self.assertFalse(ok)

    def test_cleanser_compatible_with_cleansing(self):
        p = _product("Очищение", "Гель для умывания", "cleanser-1")
        ok, _reason = is_product_compatible(p, "face", "Очищение")
        self.assertTrue(ok)

    def test_face_product_not_compatible_with_hair(self):
        p = _product("Крем", "Крем для лица", "face-cream")
        ok, reason = is_product_compatible(p, "hair", "Шампуни")
        self.assertFalse(ok)
        self.assertIn("Лицо", reason)


class RecommendationTests(unittest.TestCase):
    def _candidates(self):
        return [
            _product("Очищение", "Гель для умывания A", "clean-a", "Aqua, Glycerin"),
            _product("Крем", "Увлажняющий крем B", "cream-b", "Aqua, Glycerin"),
            _product("Очищение", "Пенка для умывания C", "clean-c", "Aqua, Glycerin"),
        ]

    def test_cleansing_does_not_return_moisturizer(self):
        with patch("app.shelf_service._query_candidates", return_value=self._candidates()):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение", set()))
        names = [r["name"] for r in recs]
        self.assertNotIn("Увлажняющий крем B", names)
        for name in names:
            self.assertNotIn("крем", name.lower())

    def test_existing_products_are_excluded(self):
        candidates = self._candidates()
        with patch("app.shelf_service._query_candidates", return_value=candidates):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение", {"clean-a"}))
        names = [r["name"] for r in recs]
        self.assertNotIn("Гель для умывания A", names)

    def test_ranking_uses_existing_score_desc(self):
        candidates = [
            _product("Очищение", "A", "a", "Aqua, Glycerin, Cocamidopropyl Betaine"),
            _product("Очищение", "B", "b", "Aqua, Niacinamide, Salicylic Acid"),
            _product("Очищение", "C", "c", "Aqua, Panthenol, Sodium Hyaluronate"),
        ]
        scores = {"a": 76, "b": 95, "c": 84}

        def fake_analysis(profile, ingredients):
            return {"score": 0, "confidence": 1.0}

        with patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._find_history_score", side_effect=lambda u, p, **kw: (scores.get(p["slug"], None), None)), \
             patch("app.shelf_service._deterministic_analysis", side_effect=fake_analysis):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение", set()))

        self.assertEqual(len(recs), 3)
        ordered = [r["score"] for r in recs]
        self.assertEqual(ordered, sorted(ordered, reverse=True))
        self.assertEqual(recs[0]["slug"], "b")

    def test_unknown_ingredients_are_neutral_not_demoted(self):
        candidates = [
            _product("Очищение", "Scored", "scored", "Aqua, Glycerin, Betaine"),
            _product("Очищение", "Unknown", "unknown", "Aqua, MysteryIngredientX"),
        ]

        with patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._find_history_score", side_effect=lambda u, p, **kw: (80, None) if p["slug"] == "scored" else (None, None)), \
             patch("app.shelf_service._deterministic_analysis", return_value={"confidence": 0.0}):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение", set()))

        self.assertEqual(recs[0]["slug"], "scored")
        self.assertEqual(len(recs), 2)
        # unknown не выбрасывается и не получает None: нейтральная оценка + статус
        self.assertEqual(recs[1]["score"], 60)
        self.assertTrue(recs[1].get("needs_enrichment"))

    def test_research_failure_does_not_break_recommendation(self):
        # Если Research (batch) не удался — рекомендация всё равно возвращается,
        # а unknown остаётся needs_enrichment (без ложного точного score).
        candidates = [
            _product("Очищение", "A", "a", "Aqua, Glycerin, UnknownX"),
            _product("Очищение", "B", "b", "Aqua, Glycerin"),
        ]
        with patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._find_history_score", return_value=(None, None)), \
             patch("app.shelf_service._deterministic_analysis", return_value={"confidence": 0.0}), \
             patch("app.ingredient_enrichment.find_unknown_ingredients", return_value=["UnknownX"]), \
             patch("app.services.DEEPSEEK_API_KEY", "test-key"), \
             patch("app.research_queue.run_research", side_effect=RuntimeError("research boom")):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение", set()))
        self.assertEqual(len(recs), 2)
        self.assertTrue(any(r.get("needs_enrichment") for r in recs))

    def test_compute_product_compatibility_uses_history(self):
        # История проверок — приоритетный источник (тот же, что в подборе).
        with patch("app.shelf_service._find_history_score", return_value=(85, {"summary": "ok"})):
            score = compute_product_compatibility(USER, {"ingredients": "Aqua"}, knowledge={}, history=[])
        self.assertEqual(score, 85)

    def test_compute_product_compatibility_deterministic_without_history(self):
        # Нет истории → deterministic Score Engine по knowledge map.
        with patch("app.shelf_service._find_history_score", return_value=(None, None)), \
             patch("app.shelf_service._build_user_profile", return_value={"skin_type": "Чувствительная"}), \
             patch("app.shelf_service._deterministic_analysis", return_value={"confidence": 0.9, "score": 99}):
            score = compute_product_compatibility(USER, {"ingredients": "Aqua, Glycerin"}, knowledge={}, history=[])
        self.assertEqual(score, 99)

    def test_compute_product_compatibility_none_when_unknown(self):
        # Нет ни истории, ни валидного знания → None («Не проверен»).
        with patch("app.shelf_service._find_history_score", return_value=(None, None)), \
             patch("app.shelf_service._build_user_profile", return_value={"skin_type": ""}), \
             patch("app.shelf_service._deterministic_analysis", return_value={"confidence": 0.0}):
            score = compute_product_compatibility(USER, {"ingredients": "Aqua, MysteryX"}, knowledge={}, history=[])
        self.assertIsNone(score)

    def test_recommend_empty_shelf_returns_no_shelf_compatibility(self):
        # Пустая полка → Shelf Compatibility не применяется, ранжирование только по Product Compatibility.
        candidates = [
            _product("Очищение", "A", "a", "Aqua, Glycerin"),
            _product("Очищение", "B", "b", "Aqua, Niacinamide"),
        ]
        scores = {"a": 76, "b": 95}
        with patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._load_shelf_products", return_value=[]), \
             patch("app.shelf_service._find_history_score", side_effect=lambda u, p, **kw: (scores.get(p["slug"], None), None)):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение", set()))
        self.assertEqual([r["slug"] for r in recs], ["b", "a"])
        for r in recs:
            self.assertIsNone(r["shelf_compatibility"])

    def test_recommend_shelf_conflict_affects_ranking(self):
        # На полке ретинол → кандидат с салициловой кислотой (AHA/BHA) конфликтует,
        # его Shelf Compatibility ниже, и он ранжируется ниже при равном Product Compatibility.
        candidates = [
            _product("Очищение", "A", "a", "Aqua, Salicylic Acid"),
            _product("Очищение", "B", "b", "Aqua, Glycerin"),
        ]
        shelf = [{"name": "Retinol Serum", "category": "Сыворотки", "ingredients": "Aqua, Retinol", "score": 90, "slug": "retinol-serum"}]
        scores = {"a": 80, "b": 80}
        with patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._load_shelf_products", return_value=shelf), \
             patch("app.shelf_service._find_history_score", side_effect=lambda u, p, **kw: (scores.get(p["slug"], None), None)):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение", set()))
        self.assertEqual([r["slug"] for r in recs], ["b", "a"])
        by = {r["slug"]: r for r in recs}
        # Product Compatibility одинаковый (не уничтожен), Shelf Compatibility разный.
        self.assertEqual(by["a"]["score"], 80)
        self.assertEqual(by["b"]["score"], 80)
        self.assertIsNotNone(by["a"]["shelf_compatibility"])
        self.assertIsNotNone(by["b"]["shelf_compatibility"])
        self.assertLess(by["a"]["shelf_compatibility"], by["b"]["shelf_compatibility"])


class ShelfAggregationTests(unittest.TestCase):
    def test_aggregate_skips_missing_scores(self):
        items = [{"score": 80}, {"score": None}, {"score": 60}]
        self.assertEqual(_aggregate_scores(items), 70)

    def test_aggregate_none_when_no_valid_scores(self):
        self.assertIsNone(_aggregate_scores([{"score": None}, {}]))

    def test_cabinet_compatibility_none_when_empty(self):
        self.assertIsNone(compute_cabinet_compatibility(USER, []))


if __name__ == "__main__":
    unittest.main()
