import asyncio
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scrapling.parser import Selector

from app import database
from app.scraper.extractors import extract_product
from app.scraper.models import ProductImportResult
from app.scraper.service import ProductImportError, import_product, validate_public_url


class ProductImportTests(unittest.TestCase):
    def test_json_ld_extracts_product_and_ingredients(self):
        page = Selector("""
            <html><head><meta property="og:image" content="/fallback.jpg"></head><body>
              <script type="application/ld+json">
                {"@type":"Product","name":"Calm Cream","brand":{"name":"Aidermy"},
                 "image":"/cream.jpg","offers":{"price":"19.90","priceCurrency":"EUR"},
                 "ingredients":"Aqua, Glycerin, Niacinamide"}
              </script>
            </body></html>
        """)

        result = extract_product(page, "https://shop.example/item")

        self.assertEqual(result.name, "Calm Cream")
        self.assertEqual(result.brand, "Aidermy")
        self.assertEqual(result.image_url, "https://shop.example/cream.jpg")
        self.assertEqual(result.price, 19.9)
        self.assertEqual(result.ingredients_raw, "Aqua, Glycerin, Niacinamide")

    def test_dom_extracts_product_and_ingredients(self):
        page = Selector("""
            <html><body>
              <h1>Daily Lotion</h1><div class="brand">Simple Brand</div>
              <div class="description">A light daily lotion.</div>
              <section class="ingredients">Ingredients: Aqua, Panthenol, Squalane</section>
            </body></html>
        """)

        result = extract_product(page, "https://shop.example/item")

        self.assertEqual(result.name, "Daily Lotion")
        self.assertEqual(result.ingredients_raw, "Aqua, Panthenol, Squalane")

    def test_missing_ingredients_is_none(self):
        page = Selector("<html><body><h1>Simple Product</h1><p>Just a description.</p></body></html>")

        result = extract_product(page, "https://shop.example/item")

        self.assertEqual(result.name, "Simple Product")
        self.assertIsNone(result.ingredients_raw)

    def test_dynamic_fetch_is_used_after_basic_fetch(self):
        empty = Selector("<html><body><h1>Loading...</h1></body></html>")
        rendered = Selector("<html><body><h1>Rendered Cream</h1><div class='ingredients'>Aqua, Glycerin</div></body></html>")

        with patch("app.scraper.service._fetch", side_effect=[empty, rendered]) as fetch:
            result = asyncio.run(import_product("https://example.com/product"))

        self.assertEqual(result.name, "Rendered Cream")
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[1].args[0], "dynamic")

    def test_invalid_url_is_rejected(self):
        with self.assertRaises(ProductImportError):
            validate_public_url("file:///etc/passwd")

    def test_duplicate_upsert_does_not_create_product(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = f"{directory}/products.db"
            original_path = database.PRODUCTS_DB
            database.PRODUCTS_DB = database_path
            try:
                conn = sqlite3.connect(database_path)
                conn.row_factory = sqlite3.Row
                conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT UNIQUE, brand TEXT, ingredients TEXT, url TEXT, incidecoder_url TEXT, image_url TEXT, category TEXT, volume TEXT, description TEXT, sku TEXT, price REAL, currency TEXT, source_type TEXT, contributed_by INTEGER, normalized_name TEXT, is_canonical INTEGER DEFAULT 1, canonical_id INTEGER, saved_at TEXT)")
                conn.commit()
                conn.close()

                product = ProductImportResult(
                    name="Calm Cream",
                    brand="Aidermy",
                    ingredients_raw="Aqua, Glycerin",
                    source_url="https://shop.example/item",
                ).to_dict()
                first = database.upsert_imported_product(product)
                second = database.upsert_imported_product({**product, "image_url": "https://shop.example/cream.jpg"})

                conn = sqlite3.connect(database_path)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)
                self.assertEqual(first["id"], second["id"])
                self.assertEqual(conn.execute("SELECT image_url FROM products").fetchone()[0], "https://shop.example/cream.jpg")
                conn.close()
            finally:
                database.PRODUCTS_DB = original_path


if __name__ == "__main__":
    unittest.main()
