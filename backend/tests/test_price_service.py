"""Цены: разбор разметки и отсев неподходящих предложений.

Тесты офлайн: разметка магазина передаётся строкой, сеть не используется.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.price_service import (
    _looks_like_sample,
    _matches_product,
    extract_price_from_html,
    parse_volume,
)

JSON_LD_PAGE = """
<html><head><title>Celimax Dual Barrier Creamy Toner 150 ml — купить</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"Product","name":"Celimax Dual Barrier Creamy Toner 150 ml",
"brand":{"@type":"Brand","name":"Celimax"},
"offers":{"@type":"Offer","price":"1590","priceCurrency":"RUB","availability":"InStock"}}]}
</script></head><body>...</body></html>
"""

META_PAGE = """
<html><head><title>The Ordinary Niacinamide 10% + Zinc 1% 30ml</title>
<meta property="product:price:amount" content="890.00">
<meta property="product:price:currency" content="RUB">
</head><body></body></html>
"""

NO_PRICE_PAGE = """
<html><head><title>Celimax Dual Barrier Creamy Toner 150 ml</title></head><body>Цена по запросу</body></html>
"""


class VolumeParsingTests(unittest.TestCase):
    def test_ml_and_grams(self):
        self.assertAlmostEqual(parse_volume("150 ml")["ml"], 150)
        self.assertAlmostEqual(parse_volume("50мл")["ml"], 50)
        self.assertAlmostEqual(parse_volume("75 g")["ml"], 75)

    def test_ounces_are_converted(self):
        self.assertAlmostEqual(parse_volume("1.7 fl oz")["ml"], 50.27, places=1)

    def test_no_volume(self):
        self.assertIsNone(parse_volume("крем без объёма"))


class SampleDetectionTests(unittest.TestCase):
    def test_samples_and_sets_rejected(self):
        self.assertTrue(_looks_like_sample("Пробник крема", 5))
        self.assertTrue(_looks_like_sample("Миниатюра 10 ml", 10))
        self.assertTrue(_looks_like_sample("Подарочный набор", 150))
        self.assertTrue(_looks_like_sample("Travel size", 120))

    def test_full_size_allowed(self):
        self.assertFalse(_looks_like_sample("Celimax Dual Barrier Creamy Toner", 150))


class HtmlPriceTests(unittest.TestCase):
    def test_json_ld_offer_is_used(self):
        found = extract_price_from_html(JSON_LD_PAGE, "https://goldapple.ru/p/1")
        self.assertEqual(found["price"], 1590.0)
        self.assertEqual(found["currency"], "RUB")
        self.assertEqual(found["volume_ml"], 150)
        self.assertEqual(found["brand"], "Celimax")

    def test_meta_price_is_used(self):
        found = extract_price_from_html(META_PAGE, "https://letu.ru/p/1")
        self.assertEqual(found["price"], 890.0)
        self.assertEqual(found["volume_ml"], 30)

    def test_page_without_structured_price_returns_none(self):
        self.assertIsNone(extract_price_from_html(NO_PRICE_PAGE, "https://shop.ru/p/1"))


class ProductMatchingTests(unittest.TestCase):
    product = {
        "id": 1,
        "name": "Celimax\n\n\nDual Barrier Creamy Toner",
        "volume": "150 ml",
    }
    candidate = {
        "title": "Celimax Dual Barrier Creamy Toner 150 ml",
        "brand": "Celimax",
        "volume_ml": 150,
    }

    def test_same_product_matches(self):
        self.assertTrue(
            _matches_product(
                self.product, self.candidate, brand="Celimax", name="Dual Barrier Creamy Toner"
            )
        )

    def test_other_volume_is_rejected(self):
        candidate = {**self.candidate, "title": "Celimax Dual Barrier Creamy Toner 30 ml", "volume_ml": 30}
        self.assertFalse(
            _matches_product(self.product, candidate, brand="Celimax", name="Dual Barrier Creamy Toner")
        )

    def test_other_brand_is_rejected(self):
        candidate = {**self.candidate, "title": "Dr. Althea 147 Barrier Cream 150 ml", "brand": "Dr. Althea"}
        self.assertFalse(
            _matches_product(self.product, candidate, brand="Celimax", name="Dual Barrier Creamy Toner")
        )

    def test_translated_title_matches_by_distinctive_word(self):
        candidate = {
            "title": "Aravia Интенсивный крем для чувствительной кожи с куперозом / Couperose Intensive Cream 150 мл",
            "brand": "Aravia",
            "volume_ml": 150,
        }
        self.assertTrue(
            _matches_product(
                self.product,
                candidate,
                brand="ARAVIA Professional",
                name="Couperose Intensive Cream",
            )
        )

    def test_sample_is_rejected(self):
        candidate = {**self.candidate, "title": "Celimax Dual Barrier Creamy Toner пробник 10 ml", "volume_ml": 10}
        self.assertFalse(
            _matches_product(self.product, candidate, brand="Celimax", name="Dual Barrier Creamy Toner")
        )


if __name__ == "__main__":
    unittest.main()
