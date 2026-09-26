# tests/test_export_calibration.py
# Проверяет экспорт calibration dataset и централизацию scoring-конфига.

import os
import tempfile
import unittest

from app.analysis_service import AnalysisService
from app.export_calibration import (
    SYNTHETIC_PROFILES,
    _ingredient_contributions,
    sample_products,
    score_one,
)
from app.ingredient_repository import IngredientRepository


class SyntheticProfilesTests(unittest.TestCase):
    def test_ten_profiles_unique(self):
        self.assertEqual(len(SYNTHETIC_PROFILES), 10)
        ids = [p["id"] for p in SYNTHETIC_PROFILES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_profiles_have_supported_fields(self):
        for p in SYNTHETIC_PROFILES:
            for key in ("id", "label", "skin_type", "concerns",
                        "allergies", "intolerances", "restrictions", "preferences"):
                self.assertIn(key, p)
            self.assertTrue(p["skin_type"])


class SamplingTests(unittest.TestCase):
    def _products(self, n=120):
        out = []
        for i in range(n):
            cat = ["Крем", "Сыворотка", "Очищение", "Другое"][i % 4]
            out.append({
                "id": i + 1,
                "name": f"P{i}",
                "category": cat,
                "ingredients": ", ".join(f"ing{x}" for x in range(1, (i % 40) + 1)),
            })
        return out

    def test_deterministic_same_seed(self):
        products = self._products()
        a = sample_products(products, 40, seed=7)
        b = sample_products(self._products(), 40, seed=7)
        self.assertEqual([p["id"] for p in a], [p["id"] for p in b])

    def test_diverse_categories(self):
        products = self._products()
        sample = sample_products(products, 40, seed=7)
        cats = {p["category"] for p in sample}
        self.assertGreater(len(cats), 1)


class ScoringBreakdownTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.ensure_ingredient_tables()
        self.repo.save_enriched_ingredient({
            "inci_name": "Glycerin",
            "claims": [{"property_name": "hydration", "direction": "positive",
                        "strength": 0.9, "confidence": 0.9}],
        })
        self.repo.save_enriched_ingredient({
            "inci_name": "Fragrance",
            "claims": [{"property_name": "sensitivity", "direction": "negative",
                        "strength": 0.9, "confidence": 0.9}],
        })

    def tearDown(self):
        self._tmp.cleanup()

    def test_score_one_produces_rich_breakdown(self):
        service = AnalysisService(self.repo)
        knowledge = self.repo.get_canonical_knowledge_map()
        product = {"id": 1, "name": "Test Cream", "brand": None,
                   "category": "Крем", "ingredients": "Glycerin, Fragrance"}
        record = score_one(product, SYNTHETIC_PROFILES[0], service, knowledge)

        self.assertIn("scoring", record)
        s = record["scoring"]
        self.assertIsInstance(s["final_score"], int)
        self.assertGreater(s["parameter_scores"]["hydration"], 0)
        self.assertLess(s["parameter_scores"]["irritation"], 0)
        self.assertTrue(s["ingredient_contributions"])
        self.assertEqual(
            {c["ingredient_name"] for c in s["ingredient_contributions"]},
            {"glycerin", "fragrance"},
        )

    def test_ingredient_contributions_axis_sums_match(self):
        service = AnalysisService(self.repo)
        knowledge = self.repo.get_canonical_knowledge_map()
        product = {"id": 1, "name": "T", "brand": None,
                   "category": "Крем", "ingredients": "Glycerin, Fragrance"}
        record = score_one(product, SYNTHETIC_PROFILES[0], service, knowledge)
        s = record["scoring"]
        sums = {axis: 0.0 for axis in s["parameter_scores"]}
        for c in s["ingredient_contributions"]:
            for axis, v in c["parameters"].items():
                sums[axis] += v
        # Движок округляет dimensions до 3 знаков — сверяем с допуском 1e-3.
        for axis in s["parameter_scores"]:
            self.assertAlmostEqual(sums[axis], s["parameter_scores"][axis], places=3)


class ConfigCentralizationTests(unittest.TestCase):
    def test_axes_from_config(self):
        from app import axes, scoring_config
        self.assertEqual(axes.AXES, scoring_config.AXES)
        self.assertEqual(axes.AXIS_HARM, scoring_config.AXIS_HARM)
        self.assertEqual(axes.AXIS_ALIASES, scoring_config.AXIS_ALIASES)
        self.assertEqual(axes.CANONICAL_TO_LEGACY_DIMENSION, scoring_config.CANONICAL_TO_LEGACY_DIMENSION)

    def test_decision_engine_weights_from_config(self):
        from app import decision_engine, scoring_config
        self.assertEqual(decision_engine.DEFAULT_PRIORITIES, scoring_config.DEFAULT_PRIORITIES)
        self.assertEqual(decision_engine.SKIN_TYPE_WEIGHTS, scoring_config.SKIN_TYPE_WEIGHTS)
        self.assertEqual(decision_engine.CONCERN_WEIGHTS, scoring_config.CONCERN_WEIGHTS)
        self.assertEqual(decision_engine.VERDICT_GOOD, scoring_config.VERDICT_GOOD)

    def test_interaction_scoring_from_config(self):
        from app import interaction_scoring, scoring_config
        self.assertEqual(interaction_scoring.INTERACTION_SCORING_VERSION, scoring_config.INTERACTION_SCORING_VERSION)
        self.assertEqual(interaction_scoring._STRENGTH_MAP, scoring_config.INTERACTION_STRENGTH_MAP)

    def test_config_version_present(self):
        from app.scoring_config import SCORING_CONFIG, SCORING_CONFIG_VERSION
        self.assertEqual(SCORING_CONFIG["scoring_config_version"], SCORING_CONFIG_VERSION)


if __name__ == "__main__":
    unittest.main()
