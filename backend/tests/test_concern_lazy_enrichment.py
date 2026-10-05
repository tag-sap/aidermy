import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.analysis_service import AnalysisService
from app.decision_engine import DecisionEngine
from app.goal_evidence import find_missing_concern_pairs
from app.ingredient_enrichment import (
    find_missing_concern_evidence,
    persist_concern_evidence_claims,
)
from app.ingredient_repository import IngredientRepository
from app.services import check_product_with_ingredients


class ConcernLazyEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = IngredientRepository(os.path.join(self.temp_dir.name, "knowledge.db"))
        self.repository.ensure_ingredient_tables()
        for name, properties in (
            ("Glycerin", [{"property_name": "hydration", "direction": "positive", "strength": 0.9, "confidence": 0.9}]),
            ("Niacinamide", [{"property_name": "brightening", "direction": "negative", "strength": 0.6, "confidence": 0.8}]),
        ):
            self.repository.save_enriched_ingredient({
                "inci_name": name,
                "canonical_name": name,
                "normalized_name": name.lower(),
                "claims": properties,
            })

    def tearDown(self):
        self.temp_dir.cleanup()

    def _engine(self):
        return DecisionEngine(AnalysisService(self.repository))

    def _check(self, profile, provider, ingredients="Glycerin, Niacinamide"):
        with patch("app.services.DEEPSEEK_API_KEY", "test-key"), \
             patch("app.decision_engine.DecisionEngine", side_effect=self._engine), \
             patch("app.research_queue.run_research", new_callable=AsyncMock) as research, \
             patch("app.services._enrich_knowledge_with_ai", new_callable=AsyncMock, side_effect=provider) as enrich:
            result = asyncio.run(check_product_with_ingredients(
                "Test serum",
                "normal",
                profile,
                ingredients,
            ))
        research.assert_not_awaited()
        return result, enrich

    @staticmethod
    def _record(ingredient, concern, property_name, direction="positive"):
        return [{
            "ingredient": ingredient,
            "concern_id": concern,
            "claims": [{
                "property": property_name,
                "direction": direction,
                "strength": 0.8,
                "confidence": 0.8,
                "evidence_level": "moderate",
                "evidence": "A specific ingredient property relevant to the selected concern.",
            }],
        }]

    def test_missing_pair_is_enriched_persisted_and_used_without_score_change(self):
        profile = {"structured": {"skin_type": "normal", "concerns": ["acne_general"]}}
        ingredients = ["Glycerin", "Niacinamide"]
        baseline = self._engine().analyze("Test serum", ingredients, profile)["score"]
        provider = AsyncMock(return_value=self._record("niacinamide", "acne_general", "acne_control"))

        result, enrich = self._check(profile, provider)

        enrich.assert_awaited_once()
        requested_pairs = enrich.await_args.args[1]
        self.assertEqual(
            [(pair["ingredient"], pair["concern_id"]) for pair in requested_pairs],
            [("glycerin", "acne_general"), ("niacinamide", "acne_general")],
        )
        self.assertEqual(result["goal_evidence"][0]["verdict"], "supports")
        self.assertEqual(result["score"], baseline)
        stored = self.repository.get_goal_evidence_map()["niacinamide"]
        self.assertIn("goal:acne_general:acne_control", stored)

    def test_existing_pair_is_reused_across_users_without_another_provider_call(self):
        first_profile = {"structured": {"skin_type": "normal", "concerns": ["acne_general"]}}
        provider = AsyncMock(return_value=self._record("niacinamide", "acne_general", "acne_control"))
        first_result, first_enrich = self._check(first_profile, provider, ingredients="Niacinamide")
        self.assertEqual(first_result["goal_evidence"][0]["verdict"], "supports")
        first_enrich.assert_awaited_once()

        second_profile = {"structured": {"skin_type": "oily", "concerns": ["acne_general"]}}
        second_provider = AsyncMock(return_value=None)
        result, enrich = self._check(second_profile, second_provider, ingredients="Niacinamide")

        enrich.assert_not_awaited()
        self.assertEqual(result["goal_evidence"][0]["verdict"], "supports")

    def test_only_missing_pairs_are_requested_for_multiple_ingredients_and_concerns(self):
        persist_concern_evidence_claims(
            self._record("glycerin", "acne_general", "acne_control"),
            [{
                "ingredient": "glycerin",
                "concern_id": "acne_general",
                "properties": ["acne_control", "anti_acne"],
            }],
            self.repository,
        )
        profile = {
            "structured": {
                "skin_type": "oily",
                "concerns": ["acne_general", "closed_comedones"],
            }
        }

        missing = find_missing_concern_evidence(
            profile,
            ["glycerin", "niacinamide"],
            self.repository,
        )

        self.assertEqual(
            [(pair["ingredient"], pair["concern_id"]) for pair in missing],
            [
                ("niacinamide", "acne_general"),
                ("glycerin", "closed_comedones"),
                ("niacinamide", "closed_comedones"),
            ],
        )

    def test_provider_cannot_persist_unrequested_pair_or_property(self):
        requested = [{
            "ingredient": "niacinamide",
            "concern_id": "acne_general",
            "properties": ["acne_control", "anti_acne"],
        }]
        records = self._record("niacinamide", "closed_comedones", "comedogenicity")
        records += self._record("niacinamide", "acne_general", "hydration")

        inserted = persist_concern_evidence_claims(records, requested, self.repository)

        self.assertEqual(inserted, 0)
        self.assertNotIn(
            "goal:acne_general:hydration",
            self.repository.get_goal_evidence_map()["niacinamide"],
        )

    def test_scoped_concern_claim_does_not_enter_score_engine_axes(self):
        missing = [{
            "ingredient": "niacinamide",
            "concern_id": "dehydrated_skin",
            "properties": ["hydration", "moisturizing", "humectant"],
        }]
        persist_concern_evidence_claims(
            self._record("niacinamide", "dehydrated_skin", "hydration"),
            missing,
            self.repository,
        )

        knowledge = self.repository.get_canonical_knowledge_map()

        self.assertNotIn("hydration", knowledge.get("niacinamide", {}))
        self.assertEqual(
            self.repository.get_goal_evidence_map()["niacinamide"]["goal:dehydrated_skin:hydration"]["direction"],
            "positive",
        )

    def test_failed_enrichment_keeps_insufficient_data_and_returns_analysis(self):
        profile = {"structured": {"skin_type": "normal", "concerns": ["acne_general"]}}
        provider = AsyncMock(return_value=None)

        result, enrich = self._check(profile, provider)

        enrich.assert_awaited_once()
        self.assertIsInstance(result.get("score"), int)
        self.assertEqual(result["goal_evidence"][0]["verdict"], "insufficient_data")

    def test_legacy_score_knowledge_still_contributes_to_deterministic_analysis(self):
        result = self._engine().analyze(
            "Test serum",
            ["Glycerin", "Niacinamide"],
            {"structured": {"skin_type": "normal", "concerns": []}},
        )

        self.assertTrue(any(factor["ingredient"] == "glycerin" for factor in result["positive_factors"]))

    def test_goal_knowledge_lookup_is_limited_to_current_product_ingredients(self):
        knowledge = self.repository.get_goal_evidence_map(["niacinamide"])

        self.assertEqual(set(knowledge), {"niacinamide"})

    def test_missing_pair_detection_is_scoped_to_supplied_product_ingredients(self):
        pairs = find_missing_concern_pairs(
            {"structured": {"concerns": ["acne_general"]}},
            ["niacinamide"],
            {},
        )

        self.assertEqual([pair["ingredient"] for pair in pairs], ["niacinamide"])


if __name__ == "__main__":
    unittest.main()
