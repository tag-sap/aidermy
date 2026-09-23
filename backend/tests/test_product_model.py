import os
import tempfile
import unittest

import app.product_model as pm
from app.ingredient_graph import IngredientGraph
from app.ingredient_repository import IngredientRepository
from app.instrumentation import METRICS
from app.product_model import (
    build_static_product_model,
    composition_hash,
    get_or_build_product_model,
)


class ProductModelTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.ensure_ingredient_tables()
        self.repo.seed_taxonomy()
        self.repo.seed_interactions()
        self.repo.save_enriched_ingredient({
            "inci_name": "Retinol",
            "claims": [
                {"property_name": "irritation_risk", "direction": "positive", "strength": 0.7, "confidence": 0.8},
            ],
        })
        self.graph = IngredientGraph(self.repo)
        pm._cache.clear()
        pm._context_cache.clear()
        METRICS.reset()

    def tearDown(self):
        pm._cache.clear()
        pm._context_cache.clear()
        METRICS.reset()
        self._tmp.cleanup()

    def test_build_model_has_hash_and_classes(self):
        p = {"id": 1, "ingredients": "Aqua, Retinol"}
        m = build_static_product_model(p, graph=self.graph)
        self.assertEqual(m["composition_hash"], composition_hash("Aqua, Retinol"))
        self.assertIn("retinoids", m["classes"])

    def test_cache_miss_then_hit(self):
        p = {"id": 1, "ingredients": "Aqua, Retinol"}
        m1 = get_or_build_product_model(p, graph=self.graph, repository=self.repo)
        m2 = get_or_build_product_model(p, graph=self.graph, repository=self.repo)
        c = METRICS.snapshot()["counters"]
        self.assertEqual(c.get("product_model_cache_miss"), 1)
        self.assertEqual(c.get("product_model_cache_hit"), 1)
        self.assertEqual(m1, m2)

    def test_composition_hash_invalidation(self):
        p1 = {"id": 1, "ingredients": "Aqua, Retinol"}
        p2 = {"id": 1, "ingredients": "Aqua, Salicylic Acid"}
        m1 = get_or_build_product_model(p1, graph=self.graph, repository=self.repo)
        m2 = get_or_build_product_model(p2, graph=self.graph, repository=self.repo)
        self.assertNotEqual(m1["composition_hash"], m2["composition_hash"])

    def test_model_version_invalidation(self):
        p = {"id": 1, "ingredients": "Aqua, Retinol"}
        m1 = get_or_build_product_model(p, graph=self.graph, repository=self.repo)
        self.assertEqual(m1["model_version"], "v1")
        pm.MODEL_VERSION = "v2"
        try:
            m2 = get_or_build_product_model(p, graph=self.graph, repository=self.repo)
            self.assertEqual(m2["model_version"], "v2")
        finally:
            pm.MODEL_VERSION = "v1"

    def test_internal_interaction_ids_are_references(self):
        p = {"id": 1, "ingredients": "Aqua, Retinol, Salicylic Acid"}
        m = build_static_product_model(p, graph=self.graph)
        ids = m["internal_interaction_ids"]
        self.assertTrue(ids)
        self.assertTrue(all(isinstance(i, int) for i in ids))  # ссылки (id), не копии

    def test_model_has_no_user_specific_data(self):
        p = {"id": 1, "ingredients": "Aqua, Retinol"}
        m = build_static_product_model(p, graph=self.graph)
        for bad in ("user_profile", "score", "verdict", "shelf_compatibility", "hard_constraints", "personalized_score"):
            self.assertNotIn(bad, m)

    def test_effects_known_and_unknown_not_zero(self):
        p = {"id": 1, "ingredients": "Aqua, Retinol"}
        m = build_static_product_model(p, graph=self.graph)
        effects = m["individual_effects"]
        self.assertIn("retinol", effects)
        self.assertIn("irritation", effects["retinol"])
        # unknown (hydration) НЕ в 0 и НЕ в effects
        self.assertNotIn("hydration", effects["retinol"])

    # ------------------------------------------------------------------
    # Фаза 6 — ProductContext, единый механизм версий, O(n) class lookups.
    # ------------------------------------------------------------------
    def test_get_current_versions(self):
        v = pm.get_current_versions()
        self.assertEqual(
            set(v.keys()),
            {"taxonomy_version", "knowledge_version", "interaction_version", "model_version"},
        )
        self.assertEqual(v["model_version"], "v1")

    def test_build_product_context_resolves_classes_once(self):
        ings = ["retinol", "salicylic acid", "niacinamide", "glycerin", "aqua",
                "filler1", "filler2", "filler3", "filler4", "filler5"]
        METRICS.reset()
        ctx = pm.build_product_context(ings, graph=self.graph)
        self.assertEqual(METRICS.snapshot()["counters"].get("class_lookup_count"), len(ings))
        self.assertIn("ingredient_to_classes", ctx)
        self.assertIn("class_to_ingredients", ctx)
        self.assertIn("relevant_internal_pairs", ctx)
        # retinol × salicylic acid релевантны (retinoids × bha)
        self.assertIn(("retinol", "salicylic acid"), ctx["relevant_internal_pairs"])

    def test_context_cache_hit_miss(self):
        ings = ["Retinol", "Salicylic Acid"]
        METRICS.reset()
        c1 = pm.get_or_build_product_context(ings, graph=self.graph)
        c2 = pm.get_or_build_product_context(ings, graph=self.graph)
        c = METRICS.snapshot()["counters"]
        self.assertEqual(c.get("product_context_cache_miss"), 1)
        self.assertEqual(c.get("product_context_cache_hit"), 1)
        self.assertEqual(c1, c2)

    def test_large_composition_class_lookups_linear(self):
        base = ["Retinol", "Salicylic Acid", "Niacinamide", "Aqua"]
        fill = ["Filler%d" % i for i in range(100)]
        ings = base + fill
        n = len(ings)
        METRICS.reset()
        pm.build_product_context(ings, graph=self.graph)
        cls = METRICS.snapshot()["counters"].get("class_lookup_count", 0)
        # Линейно: ровно n class lookups, а не n*(n-1) пар.
        self.assertEqual(cls, n)

    def test_context_version_invalidation(self):
        ings = ["Retinol", "Salicylic Acid"]
        c1 = pm.get_or_build_product_context(ings, graph=self.graph)
        old = pm.MODEL_VERSION
        pm.MODEL_VERSION = "v2"
        try:
            METRICS.reset()
            c2 = pm.get_or_build_product_context(ings, graph=self.graph)
            # Новая версия → miss (кэш инвалидирован), а не hit.
            self.assertEqual(METRICS.snapshot()["counters"].get("product_context_cache_miss"), 1)
            self.assertIsNot(c1, c2)
        finally:
            pm.MODEL_VERSION = old


if __name__ == "__main__":
    unittest.main()
