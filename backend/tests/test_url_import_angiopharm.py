"""Regression coverage for the Angiopharm-style URL import path.

These tests are deliberately network-free: the HTML fixture mirrors the
OpenCart structure (multiple h1s, JSON name, relative product image and a
composition section followed by page JavaScript).
"""
from __future__ import annotations

import unittest

from app.evaluation.knowledge import assess_composition
from app.image_storage import _validate_public_image_url
from app.models import CheckWithIngredientsRequest, Profile
from app.product_dedup import build_canonical
from app.scraper.html_provider import _absolute_image, extract_html_product
from app.shelf_service import normalize_imported_category

URL = "https://angiopharm.com/katalog/896-ekspress-lifting-maska"
PROFILE = Profile(age="25-34", concerns=[], allergies=[], intolerances=[])

HTML = """
<html>
<head>
  <title>Ангиофарм - купить ЭКСПРЕСС-ЛИФТИНГ МАСКА, 75 МЛ в Новосибирске</title>
</head>
<body>
  <h1>Войдите или создайте учетную запись</h1>
  <h1>Каталог</h1>
  <h1>ЭКСПРЕСС-ЛИФТИНГ МАСКА, 75 МЛ</h1>
  <img src="/image/catalog/products/AG20.jpg" alt="ЭКСПРЕСС-ЛИФТИНГ МАСКА, 75 МЛ">
  <h3>Состав</h3>
  <div id="tab-sostav">
    AQUA, CAPRYLIC/CAPRIC TRIGLYCERIDE, GLYCERIN, SIMMONDSIA CHINENSIS (JOJOBA) SEED OIL,
    SODIUM PHOSPHATE <!-- $('#product-product select[name=quantity]') -->
  </div>
</body>
</html>
"""


class AngiopharmExtractionTests(unittest.TestCase):
    def test_name_brand_image_and_inci_are_extracted_from_page_data(self):
        result = extract_html_product(HTML, URL)
        self.assertEqual(result.name, "ЭКСПРЕСС-ЛИФТИНГ МАСКА, 75 МЛ")
        self.assertEqual(result.brand, "AngioPharm")
        self.assertEqual(
            result.image_url,
            "https://angiopharm.com/image/catalog/products/AG20.jpg",
        )
        self.assertIn("AQUA", result.ingredients_raw or "")
        self.assertIn("SODIUM PHOSPHATE", result.ingredients_raw or "")
        self.assertNotIn("<!--", result.ingredients_raw or "")
        self.assertNotIn("product-product", result.ingredients_raw or "")
        self.assertEqual(result.name_source, "heading")

    def test_slug_is_a_marked_last_resort_when_standard_fields_are_absent(self):
        result = extract_html_product("<html><body></body></html>", URL)
        self.assertEqual(result.name, "Ekspress Lifting Maska")
        self.assertEqual(result.name_source, "slug")

    def test_relative_product_image_is_resolved(self):
        self.assertEqual(
            _absolute_image("/image/catalog/products/AG20.jpg", URL),
            "https://angiopharm.com/image/catalog/products/AG20.jpg",
        )

    def test_mask_is_mapped_to_the_canonical_aidermy_category(self):
        self.assertEqual(
            normalize_imported_category("Специальный уход", "Экспресс-лифтинг маска"),
            "Маски",
        )
        self.assertEqual(
            normalize_imported_category("Маска", "Экспресс-лифтинг маска"),
            "Маски",
        )

    def test_processed_image_is_not_replaced_by_a_reimported_remote_url(self):
        merged = build_canonical(
            {
                "name": "Mask",
                "source_type": "url",
                "image_url": "https://storage.yandexcloud.net/aidermy-images/processed/mask.png",
            },
            {
                "name": "Mask",
                "source_type": "url",
                "image_url": "https://angiopharm.com/image/catalog/products/AG20.jpg",
            },
        )
        self.assertEqual(
            merged["image_url"],
            "https://storage.yandexcloud.net/aidermy-images/processed/mask.png",
        )


class ImportedCompositionTests(unittest.TestCase):
    def test_user_imported_url_composition_can_be_analysed(self):
        state = assess_composition(
            {"source_type": "url", "url": URL},
            {"inci_raw": "Aqua, Glycerin, Panthenol", "source": URL},
            status="unverified",
        )
        self.assertTrue(state.usable)
        self.assertTrue(state.auto_verify)
        self.assertEqual(state.reason, "user_confirmed")

    def test_private_image_urls_are_rejected_before_download(self):
        with self.assertRaises(ValueError):
            _validate_public_image_url("http://127.0.0.1/secret.png")
        with self.assertRaises(ValueError):
            _validate_public_image_url("http://localhost/secret.png")

    def test_blank_brand_or_short_inci_is_rejected_by_the_api_model(self):
        with self.assertRaises(ValueError):
            CheckWithIngredientsRequest(
                product_name="Mask",
                skin_type="dry",
                profile=PROFILE,
                ingredients="Aqua, Glycerin",
                brand="",
            )
        with self.assertRaises(ValueError):
            CheckWithIngredientsRequest(
                product_name="Mask",
                skin_type="dry",
                profile=PROFILE,
                ingredients="Aqua",
                brand="AngioPharm",
            )


if __name__ == "__main__":
    unittest.main()
