# tests/test_product_identification.py
import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.database as database
from app.product_identification import (
    _is_matching_product,
    _normalize,
    find_product_in_db,
    has_reliable_inci,
    web_search_product,
)
from app.scraper.models import ProductImportResult
from app.vision_service import _coerce_identification


class ProductIdentificationTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(_normalize(" La Roche-Posay  "), "la roche posay")
        self.assertEqual(_normalize(""), "")

    def test_coerce_identification(self):
        self.assertEqual(_coerce_identification("x"), {"brand": "", "name": "", "variant": None, "type": None, "confidence": 0.0})
        r = _coerce_identification({"brand": "CeraVe", "name": "Foaming", "confidence": "0.9"})
        self.assertEqual(r["brand"], "CeraVe")
        self.assertEqual(r["confidence"], 0.9)

    def test_has_reliable_inci(self):
        self.assertFalse(has_reliable_inci(None))
        self.assertFalse(has_reliable_inci({"ingredients": ""}))
        self.assertFalse(has_reliable_inci({"ingredients": "Aqua"}))
        self.assertTrue(has_reliable_inci({"ingredients": "Aqua, Glycerin"}))


class FindProductInDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self._old = database.PRODUCTS_DB
        database.PRODUCTS_DB = self.tmp
        conn = database.get_connection(database.PRODUCTS_DB)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, brand TEXT, "
            "image_url TEXT, category TEXT, ingredients TEXT, is_canonical INTEGER DEFAULT 1, source_url TEXT)"
        )
        cur.execute(
            "INSERT INTO products (name, slug, brand, ingredients, is_canonical) "
            "VALUES ('The Ordinary\nNiacinamide 10%', 'the-ordinary-niacinamide', 'The Ordinary', 'Aqua, Niacinamide, Zinc', 1)"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.PRODUCTS_DB = self._old
        try:
            if os.path.exists(self.tmp):
                os.remove(self.tmp)
        except PermissionError:
            pass

    def test_find_by_brand_and_name(self):
        p = find_product_in_db("The Ordinary", "Niacinamide")
        self.assertIsNotNone(p)
        self.assertIn("Niacinamide", p["ingredients"])

    def test_name_only_without_brand_is_not_found(self):
        # «Название» есть, но бренд не совпадает -> не считаем найденным.
        p = find_product_in_db("CeraVe", "Niacinamide 10%")
        self.assertIsNone(p)

    def test_no_identity_returns_none(self):
        self.assertIsNone(find_product_in_db("", ""))


class CosrxLookupTests(unittest.TestCase):
    """Сценарий бага: Vision верно определил COSRX, но поиск в БД не находил товар.

    Бренд хранится только в имени (первая строка), колонка brand пустая — как в
    реальном каталоге. Если товар найден и INCI надёжный — Web Search вызывать не нужно.
    """

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self._old = database.PRODUCTS_DB
        database.PRODUCTS_DB = self.tmp
        conn = database.get_connection(database.PRODUCTS_DB)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, brand TEXT, "
            "image_url TEXT, category TEXT, ingredients TEXT, is_canonical INTEGER DEFAULT 1, source_url TEXT)"
        )
        # Бренд в имени (первая строка), brand-колонка пустая — воспроизводит реальный каталог.
        cur.execute(
            "INSERT INTO products (name, slug, brand, ingredients, is_canonical) "
            "VALUES ('COSRX\nLow pH Good Morning Gel Cleanser', 'cosrx-low-ph-good-morning-gel-cleanser', '', "
            "'Water, Glycerin, Betaine, Sodium Cocoyl Isethionate, Citric Acid', 1)"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.PRODUCTS_DB = self._old
        try:
            if os.path.exists(self.tmp):
                os.remove(self.tmp)
        except PermissionError:
            pass

    def test_cosrx_found_by_brand_and_name_with_reliable_inci(self):
        p = find_product_in_db("COSRX", "Low pH Good Morning Gel Cleanser")
        self.assertIsNotNone(p)
        # INCI надёжный -> Web Search НЕ нужен, используем существующий товар.
        self.assertTrue(has_reliable_inci(p))
        self.assertIn("Glycerin", p["ingredients"])

    def test_cosrx_case_and_spacing_variation(self):
        p = find_product_in_db("cosrx", "  low pH   good morning gel cleanser  ")
        self.assertIsNotNone(p)
        self.assertTrue(has_reliable_inci(p))

    def test_cosrx_hyphen_and_punctuation_variation(self):
        p = find_product_in_db("COSRX", "Low-pH Good Morning Gel Cleanser")
        self.assertIsNotNone(p)


class IsMatchingProductTests(unittest.TestCase):
    def test_brand_and_name_match(self):
        self.assertTrue(_is_matching_product("La Roche-Posay", "Anthelios 50+", "La Roche-Posay", "Anthelios"))

    def test_wrong_brand_rejected(self):
        self.assertFalse(_is_matching_product("CeraVe", "Anthelios", "La Roche-Posay", "Anthelios"))

    def test_wrong_name_rejected(self):
        self.assertFalse(_is_matching_product("La Roche-Posay", "Toleriane", "La Roche-Posay", "Anthelios"))

    def test_variant_must_be_present(self):
        # Вариант из Vision не встречается ни в исходном имени, ни в импортированном.
        self.assertFalse(_is_matching_product("CeraVe", "Foaming Cleanser", "CeraVe", "Foaming Cleanser", "SPF 30"))

    def test_empty_name_rejected(self):
        self.assertFalse(_is_matching_product("CeraVe", "Foaming", "CeraVe", ""))


class WebSearchProductTests(unittest.TestCase):
    def test_returns_none_when_no_url(self):
        with patch("app.product_identification._search_product_url", new=AsyncMock(return_value=None)):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios"))
        self.assertIsNone(result)

    def test_pipeline_search_scraper_inci(self):
        imported = ProductImportResult(
            name="Anthelios 50+", brand="La Roche-Posay", ingredients_raw="Aqua, Glycerin, Homosalate"
        )
        with patch("app.product_identification._search_product_url", new=AsyncMock(return_value="https://example.com/p")), \
             patch("app.scraper.import_product", new=AsyncMock(return_value=imported)):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios", "50+"))
        self.assertIsNotNone(result)
        self.assertEqual(result["ingredients"], "Aqua, Glycerin, Homosalate")
        self.assertEqual(result["source_url"], "https://example.com/p")

    def test_rejects_mismatched_product(self):
        imported = ProductImportResult(
            name="Toleriane", brand="La Roche-Posay", ingredients_raw="Aqua, Glycerin"
        )
        with patch("app.product_identification._search_product_url", new=AsyncMock(return_value="https://example.com/p")), \
             patch("app.scraper.import_product", new=AsyncMock(return_value=imported)):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios"))
        self.assertIsNone(result)

    def test_rejects_product_without_reliable_inci(self):
        imported = ProductImportResult(name="Anthelios 50+", brand="La Roche-Posay", ingredients_raw="Aqua")
        with patch("app.product_identification._search_product_url", new=AsyncMock(return_value="https://example.com/p")), \
             patch("app.scraper.import_product", new=AsyncMock(return_value=imported)):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
