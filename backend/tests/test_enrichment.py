import os
import tempfile
import unittest

from app.ingredient_repository import IngredientRepository
from app.ingredient_enrichment import find_unknown_ingredients


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.ensure_ingredient_tables()

    def tearDown(self):
        self._tmp.cleanup()

    def test_find_unknown_ingredients(self):
        self.assertEqual(find_unknown_ingredients(["Glycerin"], self.repo), ["Glycerin"])

    def test_known_ingredient_not_unknown(self):
        self.repo.upsert_ingredient("Glycerin", "Glycerin", "glycerin")
        self.assertEqual(find_unknown_ingredients(["Glycerin"], self.repo), [])

    def test_synonym_resolves_known(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Tocopherol",
            "canonical_name": "Tocopherol",
            "normalized_name": "tocopherol",
            "synonyms": ["Vitamin E"],
        })
        self.assertEqual(find_unknown_ingredients(["Vitamin E"], self.repo), [])

    def test_save_enriched_writes_claims_and_safety(self):
        ing_id = self.repo.save_enriched_ingredient({
            "inci_name": "Fragrance",
            "canonical_name": "Fragrance",
            "normalized_name": "fragrance",
            "functions": ["masking"],
            "irritation_risk": 0.6,
            "claims": [{"property_name": "sensitivity", "direction": "negative", "strength": 0.8, "confidence": 0.9}],
            "allergen": {"is_allergen": True, "allergen_level": "known", "sensitization_potential": 0.7},
        })
        self.assertGreater(ing_id, 0)
        safety = self.repo.get_safety_map()
        self.assertTrue(safety.get("fragrance", {}).get("is_allergen"))
        knowledge = self.repo.get_knowledge_map()
        self.assertIn("sensitivity", knowledge.get("fragrance", {}))


if __name__ == "__main__":
    unittest.main()
