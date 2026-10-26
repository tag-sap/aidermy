import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.scraper.models import ProductImportResult
from app.scraper.service import ProductImportError, import_product


def _result(**overrides):
    values = {
        "name": "Celimax Dual Barrier Cream",
        "brand": "Celimax",
        "description": "A barrier cream.",
        "image_url": "https://example.com/cream.jpg",
        "ingredients_raw": "Water, Glycerin, Ceramide NP",
        "source_url": "https://example.com/product",
    }
    values.update(overrides)
    return ProductImportResult(**values)


class ScraperUrlImportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(
            os.environ,
            {"SCRAPER_HTTPX_ENABLED": "1", "SCRAPER_HTTPX_TIMEOUT": "2"},
            clear=False,
        )
        self.env.start()
        self.valid_url = patch(
            "app.scraper.service.validate_public_url",
            side_effect=lambda value: value,
        )
        self.valid_url.start()

    async def asyncTearDown(self):
        self.valid_url.stop()
        self.env.stop()

    async def test_direct_url_success_uses_httpx_and_returns_inci(self):
        with patch(
            "app.scraper.html_provider.fetch_http",
            new=AsyncMock(return_value=_result()),
        ) as fetch, patch("app.scraper.service._try_extract") as fallback:
            result = await import_product("https://example.com/product")

        self.assertEqual(result.name, "Celimax Dual Barrier Cream")
        self.assertEqual(result.ingredients_raw, "Water, Glycerin, Ceramide NP")
        fetch.assert_awaited_once()
        fallback.assert_not_called()

    async def test_422_is_classified_as_anti_bot_and_reaches_fallback(self):
        request = httpx.Request("GET", "https://example.com/product")
        response = httpx.Response(422, request=request)
        error = httpx.HTTPStatusError("422", request=request, response=response)
        with patch(
            "app.scraper.html_provider.fetch_http",
            new=AsyncMock(side_effect=error),
        ), patch(
            "app.scraper.service._try_extract",
            side_effect=ProductImportError(
                "fallback also refused",
                code="no_product_data",
                status_code=422,
            ),
        ) as fallback:
            with self.assertRaises(ProductImportError) as raised:
                await import_product("https://example.com/product")

        self.assertEqual(raised.exception.code, "anti_bot")
        self.assertEqual(raised.exception.status_code, 422)
        self.assertGreaterEqual(fallback.call_count, 1)

    async def test_403_is_classified_as_access_denied(self):
        request = httpx.Request("GET", "https://example.com/product")
        response = httpx.Response(403, request=request)
        error = httpx.HTTPStatusError("403", request=request, response=response)
        with patch(
            "app.scraper.html_provider.fetch_http",
            new=AsyncMock(side_effect=error),
        ), patch(
            "app.scraper.service._try_extract",
            side_effect=ProductImportError("no browser", code="provider_unavailable"),
        ):
            with self.assertRaises(ProductImportError) as raised:
                await import_product("https://example.com/product")

        self.assertEqual(raised.exception.code, "access_denied")
        self.assertEqual(raised.exception.status_code, 422)

    async def test_timeout_is_not_reported_as_generic_parse_error(self):
        with patch(
            "app.scraper.html_provider.fetch_http",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ), patch(
            "app.scraper.service._try_extract",
            side_effect=ProductImportError("no browser", code="provider_unavailable"),
        ):
            with self.assertRaises(ProductImportError) as raised:
                await import_product("https://example.com/product")

        self.assertEqual(raised.exception.code, "timeout")
        self.assertEqual(raised.exception.status_code, 504)

    async def test_page_without_inci_returns_product_without_inventing_inci(self):
        without_inci = _result(
            description="A barrier cream without a published INCI.",
            ingredients_raw=None,
        )
        with patch(
            "app.scraper.html_provider.fetch_http",
            new=AsyncMock(return_value=without_inci),
        ), patch(
            "app.scraper.service._try_extract",
            side_effect=ProductImportError("no browser", code="provider_unavailable"),
        ):
            result = await import_product("https://example.com/product")

        self.assertEqual(result.name, "Celimax Dual Barrier Cream")
        self.assertIsNone(result.ingredients_raw)
        self.assertTrue(result.has_product_data())

    async def test_unsupported_format_is_explained(self):
        from app.scraper.extractors import UnsupportedPageFormat

        with patch(
            "app.scraper.html_provider.fetch_http",
            new=AsyncMock(side_effect=UnsupportedPageFormat("application/pdf")),
        ), patch(
            "app.scraper.service._try_extract",
            side_effect=ProductImportError("no browser", code="provider_unavailable"),
        ):
            with self.assertRaises(ProductImportError) as raised:
                await import_product("https://example.com/file.pdf")

        self.assertEqual(raised.exception.code, "unsupported_format")
        self.assertEqual(raised.exception.status_code, 422)

    async def test_scrapling_fallback_is_used_when_httpx_has_no_product(self):
        fallback = _result(
            name="Fallback Product",
            brand="Fallback Brand",
            source_url="https://example.com/product",
        )
        with patch(
            "app.scraper.html_provider.fetch_http",
            new=AsyncMock(return_value=ProductImportResult(source_url="https://example.com/product")),
        ), patch("app.scraper.service._try_extract", return_value=fallback) as attempt:
            result = await import_product("https://example.com/product")

        self.assertEqual(result.name, "Fallback Product")
        self.assertGreaterEqual(attempt.call_count, 1)


if __name__ == "__main__":
    unittest.main()
