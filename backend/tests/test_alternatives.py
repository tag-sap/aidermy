"""Подбор альтернатив: сходство состава, порядок и отсев исходного продукта."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import alternatives_service as service


SOURCE = {
    "id": 100,
    "slug": "source-toner",
    "name": "Celimax\n\n\nDual Barrier Creamy Toner",
    "brand": "Celimax",
    "image_url": "https://img/source.png",
    "volume": "150 ml",
    "catalog_category": "Восстановление кожного барьера",
    "catalog_subcategory": "Тоники",
    "taxonomy_category": "Уход для лица",
    "ingredients": "Water, Glycerin, Niacinamide, Panthenol, Ceramide NP, Allantoin",
}

CLOSE = {
    "id": 101,
    "slug": "close-toner",
    "name": "Other Brand\n\n\nBarrier Toner",
    "brand": "Other Brand",
    "image_url": "https://img/close.png",
    "volume": "150 ml",
    "catalog_category": "Восстановление кожного барьера",
    "catalog_subcategory": "Тоники",
    "ingredients": "Water, Glycerin, Niacinamide, Panthenol, Ceramide NP",
}

FAR = {
    "id": 102,
    "slug": "far-toner",
    "name": "Another\n\n\nAcid Toner",
    "brand": "Another",
    "image_url": "https://img/far.png",
    "volume": "150 ml",
    "catalog_category": "Восстановление кожного барьера",
    "catalog_subcategory": "Тоники",
    "ingredients": "Water, Glycolic Acid, Alcohol Denat, Parfum, Limonene",
}

DUPLICATE = {**SOURCE, "id": 103, "slug": "dup"}


class AlternativesTests(unittest.TestCase):
    def test_similar_product_ranks_first_and_source_is_excluded(self):
        with patch.object(service, "get_product_by_id", return_value=SOURCE), \
             patch.object(service, "_load_candidates", return_value=[DUPLICATE, FAR, CLOSE]), \
             patch("app.ingredient_repository.IngredientRepository") as repo, \
             patch.object(service, "_build_user_profile", create=True):
            repo.return_value.get_canonical_knowledge_map.return_value = {}
            with patch("app.shelf_service._deterministic_analysis", return_value=None):
                result = service.find_alternatives({"id": 7}, 100)

        ids = [item["id"] for item in result["items"]]
        self.assertEqual(result["reason"], "ok")
        self.assertNotIn(100, ids)
        self.assertNotIn(103, ids)
        self.assertEqual(ids[0], 101)
        close = result["items"][0]
        self.assertTrue(close["reasons"])
        self.assertTrue(close["differences"])
        self.assertGreater(close["similarity"], 0.4)

    def test_unknown_product_returns_empty(self):
        with patch.object(service, "get_product_by_id", return_value=None):
            result = service.find_alternatives({"id": 7}, 404404)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["reason"], "product_not_found")

    def test_reasons_and_differences_are_human_readable(self):
        source_set = service._ingredient_set(SOURCE["ingredients"])
        close_set = service._ingredient_set(CLOSE["ingredients"])
        reasons = service._reasons(
            source=SOURCE,
            candidate=CLOSE,
            shared=source_set & close_set,
            shared_notable=source_set & close_set,
            jaccard=0.8,
            same_function=True,
            category="Восстановление кожного барьера",
        )
        differences = service._differences(
            source=SOURCE,
            candidate=CLOSE,
            source_set=source_set,
            candidate_set=close_set,
            source_notable={"allantoin"},
            candidate_notable=set(),
            category="Восстановление кожного барьера",
        )
        self.assertIn("Та же категория каталога", reasons[0])
        self.assertTrue(any("ключевые компоненты" in reason for reason in reasons))
        self.assertTrue(any("Без компонентов исходного" in text for text in differences))


if __name__ == "__main__":
    unittest.main()
