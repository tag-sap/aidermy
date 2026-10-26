import unittest

from app.scraper.html_provider import extract_html_product, is_blocked_html
from app.scraper.models import ProductImportResult


class HtmlProviderRegressionTests(unittest.TestCase):
    def test_embedded_json_composition_and_title_are_extracted(self):
        html = (
            "<html><head><title>Пэды для лица `CELIMAX` JI WOO GAE очищающие 60 шт</title>"
            "</head><body><h1>Пэды для лица `CELIMAX` JI WOO GAE очищающие 60 шт</h1>"
            "<script>{\\\\\"brand\\\\\":{\\\\\"name\\\\\":\\\\\"Бренд\\\\\","
            "\\\\\"value\\\\\":\\\\\"CELIMAX\\\\\"},\\\\\"composition\\\\\":"
            "{\\\\\"name\\\\\":\\\\\"Состав\\\\\",\\\\\"value\\\\\":\\\\\"Water, Glycerin, "
            "Panthenol, 1,2-Hexanediol\\\\\"}}</script></body></html>"
        )
        result = extract_html_product(html, "https://shop.example/p")
        self.assertEqual(result.name, "Пэды для лица CELIMAX JI WOO GAE очищающие 60 шт")
        self.assertEqual(result.brand, "CELIMAX")
        self.assertIn("Water", result.ingredients_raw or "")

    def test_script_words_do_not_mark_a_normal_page_as_blocked(self):
        html = (
            "<html><head><title>Celimax Cream</title></head><body><h1>Celimax Cream</h1>"
            "<script>window.captcha = {accessDenied: true}</script>"
            "<p>Water, Glycerin, Panthenol</p></body></html>"
        )
        self.assertFalse(is_blocked_html(html))

    def test_actual_challenge_title_is_blocked(self):
        html = "<html><head><title>Gold Apple — checking device</title></head><body>checking device</body></html>"
        self.assertTrue(is_blocked_html(html))

    def test_brand_pipe_product_title_is_valid_product_data(self):
        result = ProductImportResult(
            name="COSRX | Advanced Snail 96 Mucin Power Essence",
            ingredients_raw="Water, Glycerin, Snail Secretion Filtrate",
        )
        self.assertTrue(result.has_product_data())


if __name__ == "__main__":
    unittest.main()
