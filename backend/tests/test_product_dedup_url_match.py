import unittest

from app.product_dedup import match_score


class UrlImportDedupTests(unittest.TestCase):
    def test_exact_name_with_wrong_catalog_category_is_still_a_match(self):
        catalog = {
            "name": "COSRX\n\n\nAdvanced Snail 96 Mucin Power Essence",
            "brand": None,
            "category": "Тонер",
        }
        imported = {
            "name": "Advanced Snail 96 Mucin Power Essence",
            "brand": "COSRX official",
            "category": "Сыворотка",
        }
        self.assertIsNotNone(match_score(catalog, imported))

    def test_unrelated_products_with_different_categories_stay_separate(self):
        self.assertIsNone(match_score(
            {"name": "Vitamin C Serum", "category": "Сыворотка"},
            {"name": "Shampoo for oily hair", "category": "Волосы"},
        ))

    def test_official_brand_suffix_does_not_block_a_match(self):
        self.assertIsNotNone(match_score(
            {"name": "Advanced Snail 96 Essence", "brand": "COSRX"},
            {"name": "Advanced Snail 96 Essence", "brand": "COSRX official"},
        ))


if __name__ == "__main__":
    unittest.main()
