import os
import tempfile
import unittest

from app.analysis_service import AnalysisService
from app.decision_engine import DecisionEngine
from app.database import get_connection
from app.ingredient_repository import IngredientRepository
from app.ingredient_enrichment import find_unknown_ingredients, _parse_enrichment_response
from app.research_queue import enqueue_research


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

    def test_catalog_presence_without_canonical_claims_is_not_ready(self):
        self.repo.upsert_ingredient("Glycerin", "Glycerin", "glycerin")
        self.assertEqual(find_unknown_ingredients(["Glycerin"], self.repo), ["Glycerin"])

    def test_known_ingredient_with_canonical_claim_is_not_unknown(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Glycerin",
            "canonical_name": "Glycerin",
            "normalized_name": "glycerin",
            "claims": [{"property_name": "hydration", "direction": "positive", "strength": 0.8, "confidence": 0.9}],
        })
        self.assertEqual(find_unknown_ingredients(["Glycerin"], self.repo), [])

    def test_researched_status_requires_canonical_claim(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Metadata Only",
            "canonical_name": "Metadata Only",
            "normalized_name": "metadata only",
            "functions": ["emulsifier"],
            "confidence": 0.9,
        })
        conn = get_connection(self.repo.db_path)
        row = conn.execute(
            "SELECT research_status FROM ingredients_catalog WHERE normalized_name = ?",
            ("metadata only",),
        ).fetchone()
        conn.close()
        self.assertEqual(row["research_status"], "missing")

        self.repo.save_enriched_ingredient({
            "inci_name": "Metadata Only",
            "canonical_name": "Metadata Only",
            "normalized_name": "metadata only",
            "claims": [{"property_name": "hydration", "direction": "positive",
                        "strength": 0.5, "confidence": 0.8}],
        })
        conn = get_connection(self.repo.db_path)
        row = conn.execute(
            "SELECT research_status FROM ingredients_catalog WHERE normalized_name = ?",
            ("metadata only",),
        ).fetchone()
        conn.close()
        self.assertEqual(row["research_status"], "researched")

    def test_unsupported_goal_claims_are_not_scoring_ready(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Water-Like Test",
            "canonical_name": "Water-Like Test",
            "normalized_name": "water-like test",
            "functions": ["solvent"],
            "confidence": 0.9,
            "claims": [{"property_name": "goal:acne_general:acne_control",
                        "direction": "neutral", "strength": 0.1, "confidence": 0.3}],
        })
        self.assertEqual(
            find_unknown_ingredients(["Water-Like Test"], self.repo),
            ["Water-Like Test"],
        )

    def test_neutral_water_policy_is_preserved(self):
        self.assertEqual(find_unknown_ingredients(["Aqua", "Water", "Eau"], self.repo), [])

    def test_synonym_does_not_create_duplicate_research_candidates(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Tocopherol",
            "canonical_name": "Tocopherol",
            "normalized_name": "tocopherol",
            "synonyms": ["Vitamin E"],
            "claims": [{"property_name": "hydration", "direction": "positive", "strength": 0.8, "confidence": 0.9}],
        })
        self.assertEqual(find_unknown_ingredients(["Vitamin E", "Tocopherol"], self.repo), [])

    def test_bioderma_equivalent_scenario_queues_only_missing_knowledge(self):
        """Safe equivalent of the BIODERMA case; never touches production ids."""
        for name, functions in (
            ("PEG-90 Glyceryl Isostearate", ["emulsifier", "surfactant"]),
            ("Laureth-2", ["emulsifier", "surfactant"]),
            ("Hydrogenated Palm Glycerides Citrate", ["emollient", "emulsifier"]),
        ):
            self.repo.save_enriched_ingredient({
                "inci_name": name,
                "canonical_name": name,
                "normalized_name": name.lower(),
                "functions": functions,
                "skin_effects": ["conditioning"],
                "confidence": 0.7,
            })
        # Water is an existing neutral policy; its stub must not become a task.
        self.repo.save_enriched_ingredient({
            "inci_name": "Water",
            "canonical_name": "Water",
            "normalized_name": "water",
            "functions": ["solvent", "humectant"],
            "skin_effects": ["hydration"],
            "confidence": 0.95,
            "claims": [{"property_name": "goal:acne_general:acne_control",
                        "direction": "neutral", "strength": 0.1, "confidence": 0.3}],
        })

        raw = ("Aqua (Water, Eau), PEG-90 Glyceryl Isostearate, "
               "Laureth-2, Hydrogenated Palm Glycerides Citrate")
        service = AnalysisService(self.repo)
        prepared = service.prepare_product_ingredients(raw)

        self.assertEqual(prepared, [
            "water",
            "peg-90 glyceryl isostearate",
            "laureth-2",
            "hydrogenated palm glycerides citrate",
        ])
        self.assertNotIn("aqua", prepared)
        unknown = find_unknown_ingredients(prepared, self.repo)
        self.assertEqual(unknown, [
            "peg-90 glyceryl isostearate",
            "laureth-2",
            "hydrogenated palm glycerides citrate",
        ])

        task_ids, created = enqueue_research(self.repo, unknown_ingredients=unknown)
        self.assertEqual(created, 3)
        self.assertEqual(len(set(task_ids)), 3)
        _, deduped = enqueue_research(self.repo, unknown_ingredients=unknown)
        self.assertEqual(deduped, 0)

        # Once canonical knowledge is persisted, the next readiness check sees it.
        self.repo.save_enriched_ingredient({
            "inci_name": "PEG-90 Glyceryl Isostearate",
            "normalized_name": "peg-90 glyceryl isostearate",
            "claims": [{"property_name": "hydration", "direction": "positive",
                        "strength": 0.4, "confidence": 0.7}],
        })
        self.assertEqual(find_unknown_ingredients(prepared, self.repo), [
            "laureth-2",
            "hydrogenated palm glycerides citrate",
        ])
        self.assertIn("peg-90 glyceryl isostearate", self.repo.get_canonical_knowledge_map())

    def test_new_analysis_sees_knowledge_saved_by_research(self):
        profile = {"structured": {"skin_type": "normal", "concerns": []}}
        engine = DecisionEngine(AnalysisService(self.repo))
        before = engine.analyze("Test", ["PEG-90 Glyceryl Isostearate"], profile)
        self.assertTrue(any(
            factor.get("ingredient") == "peg-90 glyceryl isostearate"
            for factor in before.get("unknown_factors") or []
        ))

        self.repo.save_enriched_ingredient({
            "inci_name": "PEG-90 Glyceryl Isostearate",
            "normalized_name": "peg-90 glyceryl isostearate",
            "claims": [{"property_name": "hydration", "direction": "positive",
                        "strength": 0.5, "confidence": 0.8}],
        })
        after = engine.analyze("Test", ["PEG-90 Glyceryl Isostearate"], profile)
        self.assertFalse(any(
            factor.get("ingredient") == "peg-90 glyceryl isostearate"
            for factor in after.get("unknown_factors") or []
        ))
        self.assertTrue(any(
            factor.get("ingredient") == "peg-90 glyceryl isostearate"
            for factor in after.get("positive_factors") or []
        ))

    def test_parse_enrichment_json_array(self):
        # AI возвращает JSON-массив — именно его просит промпт.
        records = _parse_enrichment_response(
            '[{"inci_name": "Niacinamide", "canonical_name": "Nicotinamide"}]'
        )
        self.assertEqual(records, [{"inci_name": "Niacinamide", "canonical_name": "Nicotinamide"}])

    def test_parse_enrichment_markdown_array(self):
        # Модель может обернуть массив в ```json ... ```.
        records = _parse_enrichment_response(
            '```json\n[{"inci_name": "Glycerin"}]\n```'
        )
        self.assertEqual(records, [{"inci_name": "Glycerin"}])

    def test_parse_enrichment_dict_wrapper(self):
        records = _parse_enrichment_response(
            '{"ingredients": [{"inci_name": "Zinc PCA"}]}'
        )
        self.assertEqual(records, [{"inci_name": "Zinc PCA"}])

    def test_parse_enrichment_empty_raises(self):
        with self.assertRaises(ValueError):
            _parse_enrichment_response("")

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
