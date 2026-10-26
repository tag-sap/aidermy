import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.catalog_search import rank_products
from app.catalog_taxonomy import is_target_skincare


class CatalogSearchTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "id": 241,
                "name": "Celimax\n\n\nDual Barrier Skin Wearable Cream",
                "brand": "Celimax",
                "variant": "",
                "category": "Крем",
                "subcategory": "Кремы",
                "catalog_category": "Восстановление кожного барьера",
                "catalog_subcategory": "Кремы с церамидами",
            },
            {
                "id": 220,
                "name": "Celimax\n\n\nDual Barrier Wearable Cream",
                "brand": "Celimax",
                "variant": "",
                "category": "Крем",
                "subcategory": "Кремы",
                "catalog_category": "Восстановление кожного барьера",
                "catalog_subcategory": "Кремы с церамидами",
            },
            {
                "id": 242,
                "name": "Celimax\n\n\nDual Barrier Watery Sun Cream",
                "brand": "Celimax",
                "variant": "",
                "category": "Крем",
                "subcategory": "Кремы",
                "catalog_category": "Защита от солнца",
                "catalog_subcategory": "Для лица",
            },
            {
                "id": 1,
                "name": "CeraVe Moisturizing Cream",
                "brand": "CeraVe",
                "variant": "",
                "category": "Крем",
                "subcategory": "Кремы",
            },
        ]

    def _ids(self, query):
        return [row["id"] for row in rank_products(self.rows, query, limit=20)[0]]

    def test_exact_product_name_ranks_first(self):
        self.assertEqual(self._ids("celimax dual barrier skin wearable cream")[0], 241)

    def test_typos_and_missing_letters_are_ranked(self):
        ids = self._ids("celimaks dual barer skin wearible cream")
        self.assertEqual(ids[0], 241)

    def test_russian_transliteration_and_keyboard_layout(self):
        self.assertEqual(self._ids("селимакс дуал барьер скин веарабле крем")[0], 241)
        self.assertIn(241, self._ids("судишфч dual barrier skin wearable cream"))

    def test_brand_only_and_partial_title(self):
        ids = self._ids("celimax")
        self.assertEqual(set(ids[:3]), {241, 220, 242})
        self.assertIn(241, self._ids("dual barrier wearable"))

    def test_similar_products_are_not_merged(self):
        ids = self._ids("celimax watery sun cream")
        self.assertEqual(ids[0], 242)
        self.assertNotEqual(ids[0], 241)

    def test_empty_short_and_missing_queries_are_empty(self):
        self.assertEqual(self._ids(""), [])
        self.assertEqual(self._ids("c"), [])
        self.assertEqual(self._ids("product that does not exist"), [])

    def test_skin_barrier_products_are_still_target_skincare(self):
        self.assertTrue(is_target_skincare(self.rows[0]))
        self.assertFalse(is_target_skincare({
            "name": "Body cream",
            "category": "Крем",
            "catalog_category": "Уход для тела",
        }))
        self.assertFalse(is_target_skincare({
            "name": "Cream for legs",
            "category": "Крем",
            "catalog_category": "Для ног",
        }))


if __name__ == "__main__":
    unittest.main()
