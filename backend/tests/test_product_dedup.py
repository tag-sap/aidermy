import os
import tempfile
import unittest

from app.product_dedup import (
    match_score,
    normalize_volume,
    normalize_name,
    build_canonical,
    find_or_create_canonical_product,
)


class NormalizationTests(unittest.TestCase):
    def test_normalize_volume(self):
        self.assertEqual(normalize_volume("40 мл"), "40ml")
        self.assertEqual(normalize_volume("50 g"), "50g")
        self.assertEqual(normalize_volume("1.5 oz"), "1.5oz")

    def test_normalize_name_strips_stopwords_and_volume(self):
        name = "Солнцезащитный крем CELIMAX HEART PINK TONE UP 40 мл"
        tokens = normalize_name(name).split()
        self.assertIn("heart", tokens)
        self.assertIn("pink", tokens)
        self.assertIn("tone", tokens)
        self.assertNotIn("крем", tokens)
        self.assertNotIn("40ml", tokens)


class MatchingTests(unittest.TestCase):
    def test_example_russian_vs_english_matches(self):
        a = {"name": "Heart Pink Tone Up Sun Cream"}
        b = {"name": "Солнцезащитный крем CELIMAX HEART PINK TONE UP выравнивающий тон кожи 40 мл"}
        score = match_score(a, b)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0.6)

    def test_different_volume_does_not_match(self):
        a = {"name": "Serum X", "volume": "30ml"}
        b = {"name": "Serum X", "volume": "50ml"}
        self.assertIsNone(match_score(a, b))

    def test_different_brand_does_not_match(self):
        a = {"name": "Hydrating Cream", "brand": "Avene"}
        b = {"name": "Hydrating Cream", "brand": "La Roche"}
        self.assertIsNone(match_score(a, b))

    def test_unrelated_products_do_not_match(self):
        a = {"name": "Vitamin C Serum"}
        b = {"name": "Shampoo for oily hair"}
        self.assertIsNone(match_score(a, b))


class CanonicalMergeTests(unittest.TestCase):
    def test_build_canonical_fills_missing_fields(self):
        a = {"name": "Cream", "brand": "X", "ingredients": "Aqua, Glycerin", "image_url": None, "source_type": "retailer"}
        b = {"name": "Cream 2", "image_url": "https://img", "volume": "50ml", "source_type": "user"}
        c = build_canonical(a, b)
        self.assertEqual(c["name"], "Cream")
        self.assertEqual(c["image_url"], "https://img")
        self.assertEqual(c["volume"], "50ml")

    def test_build_canonical_prefers_higher_priority_source(self):
        a = {"name": "Good Name", "source_type": "official"}
        b = {"name": "Worse Name", "source_type": "ocr"}
        c = build_canonical(a, b)
        self.assertEqual(c["name"], "Good Name")


class IdempotentMergeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "products.db")
        # Простая таблица products для теста.
        import sqlite3
        conn = sqlite3.connect(self.db)
        conn.execute('''
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, slug TEXT, brand TEXT, ingredients TEXT, url TEXT,
                incidecoder_url TEXT, image_url TEXT, category TEXT, volume TEXT,
                description TEXT, sku TEXT, price REAL, currency TEXT,
                source_type TEXT, contributed_by INTEGER, normalized_name TEXT,
                is_canonical INTEGER DEFAULT 1, canonical_id INTEGER, saved_at TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def tearDown(self):
        self._tmp.cleanup()

    def _call(self, payload):
        # Подменяем БД на временную.
        import app.product_dedup as pd
        orig = pd.PRODUCTS_DB if hasattr(pd, "PRODUCTS_DB") else None
        import app.database as db
        old = db.PRODUCTS_DB
        db.PRODUCTS_DB = self.db
        try:
            return find_or_create_canonical_product(payload)
        finally:
            db.PRODUCTS_DB = old

    def test_add_same_product_twice_is_idempotent(self):
        first = self._call({"name": "Heart Pink Cream", "brand": "X", "source_type": "retailer"})
        second = self._call({"name": "Heart Pink Cream", "brand": "X", "source_type": "user"})
        self.assertTrue(first.get("is_new"))
        self.assertFalse(second.get("is_new"))
        self.assertEqual(first["id"], second["id"])

    def test_merge_keeps_best_fields(self):
        self._call({"name": "Heart Pink Tone Up Sun Cream", "image_url": None, "source_type": "retailer"})
        merged = self._call({"name": "Солнцезащитный крем HEART PINK TONE UP 40 мл", "image_url": "https://img/x.jpg", "source_type": "url"})
        self.assertFalse(merged.get("is_new"))
        self.assertEqual(merged.get("image_url"), "https://img/x.jpg")


if __name__ == "__main__":
    unittest.main()
