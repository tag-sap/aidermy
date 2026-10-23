"""Search adapter: reuses the project's DuckDuckGo search, adds no new client."""
from __future__ import annotations

import asyncio
import unittest

from app.evaluation import websearch


class QueryBuilderTests(unittest.TestCase):
    def test_queries_cover_product_inci_and_parameters(self):
        queries = websearch.build_research_queries(
            product={"brand": "Brand", "name": "Serum"},
            composition={"inci_raw": "Aqua, Glycerin, Niacinamide, Panthenol"},
            parameter_labels=["Проблема: сухость", "Цель: увлажнение"],
            limit=5,
        )
        self.assertIn("Brand Serum ingredients INCI", queries)
        self.assertIn("Brand Serum incidecoder", queries)
        self.assertTrue(any("Aqua Glycerin" in query for query in queries))
        self.assertTrue(any("Проблема: сухость" in query for query in queries))
        self.assertLessEqual(len(queries), 5)

    def test_queries_are_deduplicated_and_bounded(self):
        queries = websearch.build_research_queries(
            product={"brand": "Brand", "name": "Serum"},
            composition={"inci_raw": ""},
            parameter_labels=["same", "same", "same", "same", "same"],
            limit=3,
        )
        self.assertEqual(len(queries), len(set(queries)))
        self.assertLessEqual(len(queries), 3)

    def test_empty_product_yields_no_product_queries(self):
        self.assertEqual(
            websearch.build_research_queries(product={}, composition={}), ()
        )


class AdapterTests(unittest.TestCase):
    def test_search_delegates_to_the_existing_project_search(self):
        calls: list[tuple[str, int]] = []

        async def fake_search(query: str, *, limit: int = 10):
            calls.append((query, limit))
            return ["https://a.example/p", "https://b.example/p"]

        import app.product_identification as identification

        original = identification.search_web_urls
        identification.search_web_urls = fake_search
        try:
            urls = websearch.DuckDuckGoSourceSearch().search("brand serum", limit=2)
        finally:
            identification.search_web_urls = original

        self.assertEqual(urls, ("https://a.example/p", "https://b.example/p"))
        self.assertEqual(calls, [("brand serum", 2)])

    def test_search_failure_returns_empty_tuple(self):
        import app.product_identification as identification

        async def broken(query: str, *, limit: int = 10):
            raise RuntimeError("antibot")

        original = identification.search_web_urls
        identification.search_web_urls = broken
        try:
            self.assertEqual(websearch.DuckDuckGoSourceSearch().search("q"), ())
        finally:
            identification.search_web_urls = original

    def test_run_async_works_inside_a_running_loop(self):
        async def probe() -> None:
            async def factory():
                await asyncio.sleep(0)
                return "ok"

            self.assertEqual(websearch.run_async(factory), "ok")

        asyncio.run(probe())

    def test_prioritize_candidates_puts_brand_first_and_dedupes(self):
        urls = [
            "https://retailer.example/product",
            "https://brand.example/product",
            "https://brand.example/product",
        ]
        ordered = websearch.prioritize_candidates(urls, {"brand": "Brand"})
        self.assertEqual(ordered[0], "https://brand.example/product")
        self.assertEqual(len(ordered), 2)


if __name__ == "__main__":
    unittest.main()
