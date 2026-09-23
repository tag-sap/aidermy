import os
import tempfile
import unittest

from app.axes import AXES
from app.ingredient_graph import EffectState, IngredientGraph
from app.ingredient_repository import IngredientRepository
from app.instrumentation import METRICS
from app.scoring_engine import score_product_against_profile


class IngredientGraphTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.ensure_ingredient_tables()
        self.repo.save_enriched_ingredient({
            "inci_name": "Retinol",
            "claims": [
                {"property_name": "irritation_risk", "direction": "positive", "strength": 0.7, "confidence": 0.8},
                {"property_name": "brightening", "direction": "positive", "strength": 0.5, "confidence": 0.9},
            ],
        })
        self.repo.save_enriched_ingredient({
            "inci_name": "WeakThing",
            "claims": [
                {"property_name": "hydration", "direction": "positive", "strength": 0.8, "confidence": 0.2},
            ],
        })
        METRICS.reset()

    def tearDown(self):
        METRICS.reset()
        self._tmp.cleanup()

    def test_cache_miss_then_hit(self):
        graph = IngredientGraph(self.repo)
        graph.get_knowledge_map()
        graph.get_knowledge_map()
        c = METRICS.snapshot()["counters"]
        self.assertEqual(c.get("cache_miss"), 1)
        self.assertEqual(c.get("cache_hit"), 1)

    def test_repeat_lookup_is_cached(self):
        graph = IngredientGraph(self.repo)
        self.assertEqual(graph.lookup_effect("Retinol", "irritation"), graph.lookup_effect("Retinol", "irritation"))

    def test_no_extra_db_queries_after_cache(self):
        graph = IngredientGraph(self.repo)
        METRICS.reset()
        graph.get_canonical_knowledge_map()
        miss_db = METRICS.snapshot()["counters"].get("db_query_count", 0)
        METRICS.reset()
        graph.get_canonical_knowledge_map()
        hit_db = METRICS.snapshot()["counters"].get("db_query_count", 0)
        self.assertGreater(miss_db, 0)
        self.assertEqual(hit_db, 0)

    def test_invalidate_forces_cache_miss(self):
        graph = IngredientGraph(self.repo)
        graph.get_knowledge_map()
        graph.invalidate()
        METRICS.reset()
        graph.get_knowledge_map()
        self.assertEqual(METRICS.snapshot()["counters"].get("cache_miss"), 1)

    def test_known_state(self):
        e = IngredientGraph(self.repo).lookup_effect("Retinol", "irritation")
        self.assertEqual(e["state"], EffectState.KNOWN)
        self.assertEqual(e["direction"], "positive")
        self.assertEqual(e["strength"], 0.7)

    def test_insufficient_confidence(self):
        e = IngredientGraph(self.repo).lookup_effect("WeakThing", "hydration")
        self.assertEqual(e["state"], EffectState.INSUFFICIENT)
        self.assertEqual(e["direction"], "positive")
        self.assertEqual(e["confidence"], 0.2)

    def test_unknown_state(self):
        e = IngredientGraph(self.repo).lookup_effect("Retinol", "sebum")
        self.assertEqual(e["state"], EffectState.UNKNOWN)

    def test_unknown_is_not_zero(self):
        e = IngredientGraph(self.repo).lookup_effect("Retinol", "sebum")
        self.assertIsNone(e.get("direction"))
        self.assertIsNone(e.get("strength"))

    def test_invalid_axis_is_unknown(self):
        e = IngredientGraph(self.repo).lookup_effect("Retinol", "comedogenicity")
        self.assertEqual(e["state"], EffectState.UNKNOWN)
        self.assertEqual(e.get("reason"), "invalid_axis")

    def test_canonical_six_axes_only(self):
        cm = IngredientGraph(self.repo).get_canonical_knowledge_map()
        self.assertIn("retinol", cm)
        for ing, axes in cm.items():
            for axis in axes:
                self.assertIn(axis, AXES)

    def test_legacy_alias_not_leaking(self):
        graph = IngredientGraph(self.repo)
        self.assertEqual(graph.lookup_effect("Retinol", "irritation")["direction"], "positive")
        self.assertEqual(graph.lookup_effect("Retinol", "pigmentation")["direction"], "negative")
        self.assertNotIn("brightening", graph.get_canonical_knowledge_map()["retinol"])
        self.assertNotIn("irritation_risk", graph.get_canonical_knowledge_map()["retinol"])

    def test_deterministic_result(self):
        graph = IngredientGraph(self.repo)
        self.assertEqual(graph.lookup_effects("Retinol"), graph.lookup_effects("Retinol"))

    def test_interaction_unknown_for_non_seed_pair(self):
        r = IngredientGraph(self.repo).lookup_interaction("Glycerin", "Panthenol")
        self.assertEqual(r["state"], EffectState.UNKNOWN)
        self.assertEqual(r["records"], [])

    def test_regression_legacy_score_identical(self):
        graph = IngredientGraph(self.repo)
        direct = self.repo.get_knowledge_map()
        cached = graph.get_knowledge_map()
        self.assertEqual(direct, cached)
        profile = {"skin_type": "Чувствительная", "allergies": [], "intolerances": [], "restrictions": []}
        priorities = {"hydration": 0.35, "barrier_support": 0.25, "sensitivity": 0.2, "acne_control": 0.1, "brightening": 0.1}
        s1 = score_product_against_profile(["Retinol"], direct, profile, priorities)["score"]
        s2 = score_product_against_profile(["Retinol"], cached, profile, priorities)["score"]
        self.assertEqual(s1, s2)

    def test_threshold_is_configurable(self):
        strict = IngredientGraph(self.repo, confidence_threshold=0.9)
        self.assertEqual(strict.lookup_effect("Retinol", "irritation")["state"], EffectState.INSUFFICIENT)
        loose = IngredientGraph(self.repo, confidence_threshold=0.1)
        self.assertEqual(loose.lookup_effect("WeakThing", "hydration")["state"], EffectState.KNOWN)


if __name__ == "__main__":
    unittest.main()
