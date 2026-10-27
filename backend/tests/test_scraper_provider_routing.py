import os
import unittest
from unittest.mock import AsyncMock, patch

from app.scraper.models import ProductImportResult
from app.scraper.service import (
    _domain_matches,
    _scrapper_enabled_for,
    clear_import_cache,
    import_product,
)


def _result(**overrides):
    values = {
        "name": "Celimax Dual Barrier Cream",
        "brand": "Celimax",
        "description": "A barrier cream.",
        "ingredients_raw": "Water, Glycerin, Ceramide NP",
        "source_url": "https://example.com/product",
    }
    values.update(overrides)
    return ProductImportResult(**values)


class ProviderRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_import_cache()
        self.env = patch.dict(
            os.environ,
            {
                "SCRAPER_HTTPX_ENABLED": "0",
                "SCRAPER_IMPORT_CACHE_TTL": "0",
                "SCRAPPER_URL": "",
                "SCRAPPER_DOMAINS": "goldapple.ru",
            },
            clear=False,
        )
        self.env.start()
        self.valid_url = patch(
            "app.scraper.service.validate_public_url",
            side_effect=lambda value: value,
        )
        self.valid_url.start()

    async def asyncTearDown(self):
        clear_import_cache()
        self.valid_url.stop()
        self.env.stop()

    def test_domain_matching_does_not_use_substring_tricks(self):
        self.assertTrue(_domain_matches("www.goldapple.ru", "goldapple.ru"))
        self.assertTrue(_domain_matches("goldapple.ru", "goldapple.ru,example.com"))
        self.assertFalse(_domain_matches("notgoldapple.ru", "goldapple.ru"))

    def test_scrapper_is_disabled_without_a_configured_url(self):
        self.assertFalse(_scrapper_enabled_for("goldapple.ru"))

    def test_scrapper_is_enabled_for_an_explicit_domain(self):
        with patch.dict(os.environ, {"SCRAPPER_URL": "http://127.0.0.1:3000"}):
            self.assertTrue(_scrapper_enabled_for("www.goldapple.ru"))
            self.assertFalse(_scrapper_enabled_for("podrygka.ru"))

    async def test_short_ttl_cache_skips_a_second_browser_request(self):
        with patch.dict(
            os.environ,
            {"SCRAPER_HTTPX_ENABLED": "1", "SCRAPER_IMPORT_CACHE_TTL": "60"},
        ), patch(
            "app.scraper.html_provider.fetch_http",
            new=AsyncMock(return_value=_result()),
        ) as fetch:
            first = await import_product("https://example.com/product")
            second = await import_product("https://example.com/product")

        self.assertEqual(first.name, second.name)
        fetch.assert_awaited_once()

    async def test_configured_scrapper_is_used_before_browser_fallback(self):
        with patch.dict(
            os.environ,
            {
                "SCRAPPER_URL": "http://127.0.0.1:3000",
                "SCRAPPER_DOMAINS": "example.com",
            },
        ), patch(
            "app.scraper.scrapper_provider.fetch_scrapper",
            new=AsyncMock(return_value=_result()),
        ) as scrapper:
            result = await import_product("https://example.com/product")

        self.assertEqual(result.ingredients_raw, "Water, Glycerin, Ceramide NP")
        scrapper.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
