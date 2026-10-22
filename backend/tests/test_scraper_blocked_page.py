import unittest

from app.scraper.extractors import is_blocked_page
from app.scraper.models import ProductImportResult


class GoldAppleChallengeTests(unittest.TestCase):
    def test_checking_device_is_detected(self):
        html = "<title>Gold Apple — checking device</title><p>checking device</p>"
        self.assertTrue(is_blocked_page(html))

    def test_normal_product_page_is_not_blocked(self):
        self.assertFalse(is_blocked_page("COSRX Ac Collection Calming Foam Cleanser Aqua, Glycerin"))

    def test_challenge_page_is_not_a_product(self):
        result = ProductImportResult(
            name="Gold Apple — checking device",
            description="checking device",
            image_url="https://goldapple.ru/logo.svg",
        )
        self.assertFalse(result.has_product_data())
