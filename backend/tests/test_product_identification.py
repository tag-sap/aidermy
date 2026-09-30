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
from app.scraper.extractors import _brand_from_domain, _INGREDIENT_LABELS
from app.vision_service import _coerce_identification


class ProductIdentificationTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(_normalize(" La Roche-Posay  "), "la roche posay")
        self.assertEqual(_normalize(""), "")

    def test_coerce_identification(self):
        base = _coerce_identification("x")
        self.assertEqual(base["brand"], "")
        self.assertEqual(base["product_name"], "")
        self.assertEqual(base["name"], "")
        self.assertIsNone(base["manufacturer"])
        self.assertIsNone(base["category"])
        self.assertEqual(base["confidence"], 0.0)
        r = _coerce_identification({"brand": "CeraVe", "name": "Foaming", "confidence": "0.9"})
        self.assertEqual(r["brand"], "CeraVe")
        self.assertEqual(r["product_name"], "Foaming")
        self.assertEqual(r["confidence"], 0.9)

    def test_structured_output_keeps_manufacturer(self):
        ident = _coerce_identification({
            "brand": "COSRX",
            "product_name": "Advanced Snail 96 Mucin Power Essence",
            "manufacturer": "COSRX Inc",
            "category": "Сыворотка",
        })
        self.assertEqual(ident["brand"], "COSRX")
        self.assertEqual(ident["product_name"], "Advanced Snail 96 Mucin Power Essence")
        self.assertEqual(ident["manufacturer"], "COSRX Inc")
        self.assertEqual(ident["category"], "Сыворотка")
        self.assertEqual(ident["name"], "Advanced Snail 96 Mucin Power Essence")

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
        with patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=[])):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios"))
        self.assertIsNone(result)

    def test_pipeline_search_scraper_inci(self):
        imported = ProductImportResult(
            name="Anthelios 50+", brand="La Roche-Posay", ingredients_raw="Aqua, Glycerin, Homosalate"
        )
        with patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=["https://example.com/p"])), \
             patch("app.scraper.import_product", new=AsyncMock(return_value=imported)):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios", "50+"))
        self.assertIsNotNone(result)
        self.assertEqual(result["ingredients"], "Aqua, Glycerin, Homosalate")
        self.assertEqual(result["source_url"], "https://example.com/p")

    def test_rejects_mismatched_product(self):
        imported = ProductImportResult(
            name="Toleriane", brand="La Roche-Posay", ingredients_raw="Aqua, Glycerin"
        )
        with patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=["https://example.com/p"])), \
             patch("app.scraper.import_product", new=AsyncMock(return_value=imported)):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios"))
        self.assertIsNone(result)

    def test_rejects_product_without_reliable_inci(self):
        imported = ProductImportResult(name="Anthelios 50+", brand="La Roche-Posay", ingredients_raw="Aqua")
        with patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=["https://example.com/p"])), \
             patch("app.scraper.import_product", new=AsyncMock(return_value=imported)):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios"))
        self.assertIsNone(result)


class WebSearchSaveAndReuseTests(unittest.TestCase):
    """Сценарий: Vision → Web Search → URL → scraper → сохранение → повторный поиск из БД."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self._old = database.PRODUCTS_DB
        database.PRODUCTS_DB = self.tmp
        conn = database.get_connection(database.PRODUCTS_DB)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT UNIQUE, brand TEXT, manufacturer TEXT, "
            "ingredients TEXT, url TEXT, incidecoder_url TEXT, image_url TEXT, category TEXT, volume TEXT, "
            "description TEXT, sku TEXT, price REAL, currency TEXT, source_type TEXT, contributed_by INTEGER, "
            "normalized_name TEXT, is_canonical INTEGER DEFAULT 1, canonical_id INTEGER, saved_at TEXT)"
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

    def test_new_product_saved_and_reused_without_web_search(self):
        from app.product_dedup import find_or_create_canonical_product

        imported = ProductImportResult(name="Anthelios 50+", brand="La Roche-Posay", ingredients_raw="Aqua, Glycerin, Homosalate")
        with patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=["https://example.com/p"])), \
             patch("app.scraper.import_product", new=AsyncMock(return_value=imported)):
            found = asyncio.run(web_search_product("La Roche-Posay", "Anthelios", "50+"))
        self.assertIsNotNone(found)

        # Эндпоинт /api/product/web-search сохраняет продукт через find_or_create_canonical_product.
        saved = find_or_create_canonical_product({
            "name": found["name"],
            "brand": found["brand"],
            "ingredients": found["ingredients"],
            "url": found.get("source_url") or "",
            "source_type": "web_search",
        })
        self.assertIsNotNone(saved)
        self.assertTrue(saved.get("ingredients"))

        # Повторный поиск находит продукт из БД (Web Search не вызывается).
        p = find_product_in_db("La Roche-Posay", "Anthelios")
        self.assertIsNotNone(p)
        self.assertTrue(has_reliable_inci(p))

    def test_wrong_variant_not_accepted_by_web_search(self):
        # Vision определил variant "50+", но scraper вернул "Anthelios 30" — другой вариант.
        imported = ProductImportResult(name="Anthelios 30", brand="La Roche-Posay", ingredients_raw="Aqua, Glycerin, Homosalate")
        with patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=["https://example.com/p"])), \
             patch("app.scraper.import_product", new=AsyncMock(return_value=imported)):
            result = asyncio.run(web_search_product("La Roche-Posay", "Anthelios", "50+"))
        self.assertIsNone(result)


class BrandFromDomainTests(unittest.TestCase):
    def test_official_domain_resolves_brand(self):
        self.assertEqual(_brand_from_domain("https://theordinary.com/product/serum"), "The Ordinary")

    def test_subdomain_resolves_brand(self):
        self.assertEqual(_brand_from_domain("https://us.cosrx.com/products/x"), "COSRX")

    def test_unknown_domain_returns_none(self):
        self.assertIsNone(_brand_from_domain("https://some-random-shop.com/x"))


class ProductImportResultValidationTests(unittest.TestCase):
    def test_site_title_is_not_product_data(self):
        # «Brand | Slogan» — заголовок сайта, а не название продукта.
        r = ProductImportResult(name="COSRX | EXPECTING TOMORROW", ingredients_raw="Water, Glycerin")
        self.assertFalse(r.has_product_data())

    def test_huge_ingredients_is_not_product_data(self):
        # «Состав» = весь текст страницы (не INCI) — не валидные данные товара.
        r = ProductImportResult(name="Advanced Snail 96", ingredients_raw="x" * 16000)
        self.assertFalse(r.has_product_data())

    def test_valid_product_data(self):
        r = ProductImportResult(name="Advanced Snail 96 Mucin Power Essence", brand="COSRX", ingredients_raw="Water, Glycerin, Snail Secretion Filtrate")
        self.assertTrue(r.has_product_data())

    def test_ingredient_label_does_not_capture_entire_page(self):
        # DOTALL-greedy раньше захватывал весь текст страницы — теперь ограничен.
        text = "Ingredients: Water, Glycerin, Niacinamide." + ("x" * 20000)
        m = _INGREDIENT_LABELS.search(text)
        self.assertIsNotNone(m)
        self.assertLessEqual(len(m.group(1)), 8000)


if __name__ == "__main__":
    unittest.main()
