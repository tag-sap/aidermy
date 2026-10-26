import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import bs4  # noqa: F401
except Exception:  # pragma: no cover - optional in a minimal env
    bs4 = None

from app.scraper.html_provider import extract_html_product


@unittest.skipIf(bs4 is None, "Beautiful Soup is not installed")
class HtmlProviderTests(unittest.TestCase):
    def test_extracts_product_and_inci_without_inventing_values(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product",
         "name":"Celimax Dual Barrier Skin Wearable Cream",
         "brand":{"@type":"Brand","name":"Celimax"},
         "image":"https://example.com/celimax.png",
         "description":"Ingredients: Water, Glycerin, Ceramide NP, Panthenol",
         "offers":{"@type":"Offer","price":"2500","priceCurrency":"RUB"}}
        </script></head><body><h1>Celimax</h1></body></html>
        """
        result = extract_html_product(html, "https://example.com/p")
        self.assertEqual(result.name, "Celimax Dual Barrier Skin Wearable Cream")
        self.assertEqual(result.brand, "Celimax")
        self.assertIn("Water", result.ingredients_raw or "")
        self.assertEqual(result.source_url, "https://example.com/p")

    def test_missing_inci_is_null_not_guessed(self):
        html = """
        <html><head><meta property="og:title" content="Celimax Cream">
        <meta property="og:site_name" content="Celimax"></head><body></body></html>
        """
        result = extract_html_product(html, "https://example.com/p")
        self.assertEqual(result.name, "Celimax Cream")
        self.assertIsNone(result.ingredients_raw)

    def test_unrelated_short_inci_is_not_accepted(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"Celimax Cream","brand":{"name":"Celimax"},
         "description":"Ingredients: See packaging"}
        </script></head></html>
        """
        result = extract_html_product(html, "https://example.com/p")
        self.assertIsNone(result.ingredients_raw)


if __name__ == "__main__":
    unittest.main()
