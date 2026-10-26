import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import product_identification
from app.scraper.models import ProductImportResult


class _Response:
    status_code = 200

    def json(self):
        return {"results": [
            {"url": "https://shop.example/product"},
            {"url": "https://shop.example/product"},
            {"url": "https://second.example/product"},
        ]}


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, *args, **kwargs):
        return _Response()


class SearchProviderTests(unittest.TestCase):
    def test_searxng_is_preferred_and_deduplicates_urls(self):
        with patch.dict(os.environ, {"SEARXNG_URL": "http://127.0.0.1:8888"}), \
                patch.object(product_identification.httpx, "AsyncClient", return_value=_Client()):
            urls = asyncio.run(product_identification.search_web_urls("Celimax", limit=10))
        self.assertEqual(urls, ["https://shop.example/product", "https://second.example/product"])

    def test_successful_search_is_cached(self):
        imported = ProductImportResult(
            name="Celimax Dual Barrier Skin Wearable Cream",
            brand="Celimax",
            ingredients_raw="Water, Glycerin, Ceramide NP",
        )
        product_identification._WEB_SEARCH_CACHE.clear()
        with patch.dict(os.environ, {"WEB_SEARCH_CACHE_TTL": "3600"}), \
                patch("app.product_identification._search_product_urls", new=AsyncMock(return_value=["https://example.com/p"])), \
                patch("app.scraper.import_product", new=AsyncMock(return_value=imported)) as scraper:
            first = asyncio.run(product_identification.web_search_product("Celimax", "Dual Barrier Skin Wearable Cream"))
            second = asyncio.run(product_identification.web_search_product("Celimax", "Dual Barrier Skin Wearable Cream"))
        self.assertEqual(first["ingredients"], second["ingredients"])
        self.assertEqual(scraper.await_count, 1)
        product_identification._WEB_SEARCH_CACHE.clear()


if __name__ == "__main__":
    unittest.main()
