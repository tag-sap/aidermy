"""Regression-тесты: pipeline идентификации не зависает бесконечно."""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scraper.service import import_product, ProductImportError
from app.scraper.models import ProductImportResult
from app.product_identification import web_search_product


class ScraperTimeoutTests(unittest.TestCase):
    def test_import_product_timeout_raises_controlled_error(self):
        """Зависший fetcher не держит запрос вечно — wait_for возвращает управляемую ошибку."""
        def slow_extract(fetcher, url):
            import time
            time.sleep(5)
            return ProductImportResult(name="x")

        with patch("app.scraper.service.validate_public_url", return_value="https://example.com/p"), \
             patch("app.scraper.service.SCRAPER_FETCH_TIMEOUT", 0.1), \
             patch("app.scraper.service._try_extract", side_effect=slow_extract):
            with self.assertRaises(ProductImportError):
                asyncio.run(import_product("https://example.com/p"))


class WebSearchErrorTests(unittest.TestCase):
    def test_web_search_scraper_error_returns_none(self):
        """Ошибка scraper после найденного URL возвращает None, а не зависает."""
        with patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=["https://example.com/p"])), \
             patch("app.scraper.import_product", new=AsyncMock(side_effect=Exception("scraper failed"))):
            result = asyncio.run(web_search_product("Brand", "Product"))
        self.assertIsNone(result)

    def test_web_search_no_url_returns_none(self):
        """Нет подходящего URL — возвращаем None, не выдумываем и не зависаем."""
        with patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=[])):
            result = asyncio.run(web_search_product("Brand", "Product"))
        self.assertIsNone(result)

    def test_web_search_falls_back_to_next_url(self):
        """Первый URL (официальный сайт) не даёт состав — пробуем следующий URL."""
        good = ProductImportResult(
            name="Advanced Snail 96 Mucin Power Essence",
            brand="COSRX",
            ingredients_raw="Water, Glycerin, Snail Secretion Filtrate",
        )
        with patch("app.product_identification._search_product_urls",
                   new=AsyncMock(return_value=["https://cosrx.com/p", "https://incidecoder.com/p"])), \
             patch("app.scraper.import_product",
                   new=AsyncMock(side_effect=[ProductImportError("blocked"), good])):
            result = asyncio.run(web_search_product("COSRX", "Advanced Snail 96 Mucin Power Essence"))
        self.assertIsNotNone(result)
        self.assertIn("Snail", result["ingredients"])
        self.assertEqual(result["source_url"], "https://incidecoder.com/p")


if __name__ == "__main__":
    unittest.main()
