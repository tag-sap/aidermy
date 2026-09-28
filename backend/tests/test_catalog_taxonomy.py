import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.catalog_taxonomy import (
    TAXONOMY,
    body_area_keys,
    subcategory_titles,
    canonical_subcategory,
    classify_product,
    taxonomy_payload,
)


class TaxonomyStructureTests(unittest.TestCase):
    def test_five_top_categories(self):
        self.assertEqual(body_area_keys(), ["face", "body", "hair", "makeup", "fragrance"])

    def test_face_subcategories(self):
        titles = subcategory_titles("face")
        for expected in ("Очищение и демакияж", "Сыворотки", "Кремы", "Увлажнение и питание"):
            self.assertIn(expected, titles)

    def test_body_subcategories(self):
        titles = subcategory_titles("body")
        for expected in ("Кремы для тела", "Дезодоранты", "Мыло"):
            self.assertIn(expected, titles)

    def test_no_conflicting_taxonomy_within_area(self):
        # Внутри каждой верхней категории ключи подкатегорий уникальны,
        # «Все товары категории» (all) — навигационный элемент, а не категория.
        for c in TAXONOMY:
            keys = [s["key"] for s in c["categories"] if s["key"] != "all"]
            self.assertEqual(len(keys), len(set(keys)), f"Дубликаты ключей в {c['key']}")
            self.assertNotIn("all", keys)

    def test_taxonomy_payload_shape(self):
        payload = taxonomy_payload()
        self.assertEqual(len(payload), 5)
        for c in payload:
            self.assertIn("key", c)
            self.assertIn("title", c)
            self.assertIn("subcategories", c)

    def test_shelf_cabinets_match_taxonomy(self):
        # Полка не имеет отдельного списка категорий — берёт из таксономии.
        from app.shelf_service import CABINETS
        self.assertEqual([c["key"] for c in CABINETS], [c["key"] for c in TAXONOMY])
        for cab in CABINETS:
            meta = next(c for c in TAXONOMY if c["key"] == cab["key"])
            expected = [s["title"] for s in meta["categories"] if s["key"] != "all"]
            self.assertEqual(cab["categories"], expected)


class ClassificationTests(unittest.TestCase):
    def test_hinoki_body_milk(self):
        c = classify_product({"name": "Hinoki\nBody Milk", "category": ""})
        self.assertEqual(c["body_area"], "body")
        self.assertEqual(c["canonical_category"], "Кремы для тела")

    def test_cosrx_cleanser(self):
        c = classify_product({"name": "COSRX\nLow pH Good Morning Gel Cleanser", "category": ""})
        self.assertEqual(c["body_area"], "face")
        self.assertEqual(c["canonical_category"], "Очищение и демакияж")

    def test_vt_mesh_pact(self):
        c = classify_product({"name": "VT Cosmetics\nCica Light Touch Mesh Pact", "category": ""})
        self.assertEqual(c["body_area"], "makeup")
        self.assertEqual(c["canonical_category"], "Пудры")

    def test_unknown_not_guessed(self):
        c = classify_product({"name": "Неизвестный продукт XYZ", "category": "Другое"})
        self.assertEqual(c["category_source"], "unknown")
        self.assertEqual(c["canonical_category"], "Другое")

    def test_legacy_cream_mapping(self):
        c = classify_product({"name": "Увлажняющий крем", "category": "Крем"})
        self.assertEqual(c["body_area"], "face")
        self.assertEqual(c["canonical_category"], "Кремы")

    def test_fields_present(self):
        c = classify_product({"name": "Сыворотка", "category": ""})
        for field in ("body_area", "product_type", "primary_function",
                      "secondary_functions", "canonical_category",
                      "category_confidence", "category_source"):
            self.assertIn(field, c)


class CanonicalSubcategoryTests(unittest.TestCase):
    def test_legacy_cleansing(self):
        self.assertEqual(canonical_subcategory("face", "Очищение"), "Очищение и демакияж")

    def test_exact_title(self):
        self.assertEqual(canonical_subcategory("face", "Сыворотки"), "Сыворотки")

    def test_unknown(self):
        self.assertEqual(canonical_subcategory("face", "Нечто"), "Другое")


class RecommendationFilterTests(unittest.TestCase):
    def test_shampoo_not_compatible_with_face_serums(self):
        from app.shelf_service import is_product_compatible
        p = {"id": 1, "name": "Шампунь", "category": "", "slug": "sh", "brand": ""}
        ok, _ = is_product_compatible(p, "face", "Сыворотки")
        self.assertFalse(ok)

    def test_serum_compatible_with_face_serums(self):
        from app.shelf_service import is_product_compatible
        p = {"id": 1, "name": "Сыворотка", "category": "", "slug": "ser", "brand": ""}
        ok, _ = is_product_compatible(p, "face", "Сыворотки")
        self.assertTrue(ok)

    def test_unknown_product_not_blocked(self):
        from app.shelf_service import is_product_compatible
        p = {"id": 1, "name": "Нечто неизвестное", "category": "Другое", "slug": "x", "brand": ""}
        ok, _ = is_product_compatible(p, "face", "Кремы")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
