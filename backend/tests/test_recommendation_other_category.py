"""Тесты исключения категории «Другое» из рекомендательного движка.

Категория «Другое» должна исключаться из candidate pool рекомендаций (и векторный
retrieval, и legacy SQL), но при этом товары «Другое» остаются доступны в каталоге,
поиске, карточке и могут добавляться на полку вручную.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.shelf_service import (
    _is_other_category,
    is_product_compatible,
    recommend_products,
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
    return {
        "id": _PID[0],
        "name": name,
        "slug": slug,
        "category": category,
        "brand": "",
        "ingredients": ingredients,
    }


class OtherCategoryDetectionTests(unittest.TestCase):
    def test_other_category_is_detected(self):
        p = _product("Другое", "Продукт без категории", "other-1")
        self.assertTrue(_is_other_category(p))

    def test_empty_category_is_detected_as_other(self):
        p = _product("", "Продукт без категории", "other-2")
        self.assertTrue(_is_other_category(p))

    def test_known_category_is_not_other(self):
        p = _product("Очищение", "Гель для умывания A", "clean-1")
        self.assertFalse(_is_other_category(p))


class RecommendationExclusionTests(unittest.TestCase):
    def setUp(self):
        self._upsert_patcher = patch("app.database.upsert_analysis")
        self._upsert_patcher.start()
        self.addCleanup(self._upsert_patcher.stop)

    def test_other_category_not_recommended(self):
        candidates = [
            _product("Другое", "Продукт без категории", "other-1"),
            _product("Очищение", "Гель для умывания A", "clean-a"),
        ]
        with patch("app.vector_retrieval.VECTOR_RETRIEVAL_ENABLED", False), \
             patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._load_shelf_products", return_value=[]), \
             patch("app.shelf_service._find_history_score", return_value=(80, None)):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение и демакияж", set()))
        slugs = [r["slug"] for r in recs]
        self.assertNotIn("other-1", slugs)
        self.assertIn("clean-a", slugs)

    def test_valid_category_still_recommended_with_score(self):
        candidates = [
            _product("Очищение", "Гель для умывания A", "clean-a"),
        ]
        with patch("app.vector_retrieval.VECTOR_RETRIEVAL_ENABLED", False), \
             patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._load_shelf_products", return_value=[]), \
             patch("app.shelf_service._find_history_score", return_value=(80, None)):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение и демакияж", set()))
        self.assertEqual([r["slug"] for r in recs], ["clean-a"])

    def test_other_not_used_as_fallback(self):
        # Если подходящих товаров нет, «Другое» НЕ должно добивать выдачу.
        candidates = [
            _product("Другое", "Продукт без категории", "other-1"),
            _product("Другое", "Ещё один без категории", "other-2"),
        ]
        with patch("app.vector_retrieval.VECTOR_RETRIEVAL_ENABLED", False), \
             patch("app.shelf_service._query_candidates", return_value=candidates), \
             patch("app.shelf_service._load_shelf_products", return_value=[]), \
             patch("app.shelf_service._find_history_score", return_value=(80, None)):
            recs = asyncio.run(recommend_products(USER, "face", "Очищение и демакияж", set()))
        self.assertEqual(recs, [])


class VectorRetrievalExclusionTests(unittest.TestCase):
    def test_retrieve_candidates_excludes_other(self):
        products = [
            {"id": 1, "name": "Продукт без категории", "slug": "other-1", "category": "Другое", "brand": "", "ingredients": "Aqua, Glycerin"},
            {"id": 2, "name": "Гель для умывания A", "slug": "clean-a", "category": "Очищение", "brand": "", "ingredients": "Aqua, Glycerin"},
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
                "Очищение и демакияж",
                set(),
            )
        slugs = [r["slug"] for r in result]
        self.assertNotIn("other-1", slugs)
        self.assertIn("clean-a", slugs)
        # Category hard filter применяется ДО retrieval: search получает только id категории.
        self.assertEqual(captured["allowed_ids"], [2])


class ManualShelfAndCatalogTests(unittest.TestCase):
    def test_manual_shelf_addition_allowed_for_other(self):
        # Ручное добавление на полку для «Другое» по-прежнему разрешено.
        p = _product("Другое", "Продукт без категории", "other-1")
        ok, _reason = is_product_compatible(p, "face", "Крем")
        self.assertTrue(ok)

    def test_is_other_category_does_not_change_compatibility(self):
        # Фильтр рекомендаций не должен влиять на совместимость «Другое».
        p = _product("Другое", "Продукт без категории", "other-1")
        self.assertTrue(_is_other_category(p))
        ok, _reason = is_product_compatible(p, "face", "Очищение и демакияж")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
