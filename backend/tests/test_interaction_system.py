import os
import tempfile
import unittest

import app.product_model as pm
from app.ingredient_graph import IngredientGraph
from app.ingredient_repository import IngredientRepository
from app.interaction_system import (
    build_dynamic_shelf_model,
    detect_cross_product_interactions,
    flatten_cross_product_interactions,
    shadow_compare_interactions,
)
from app.instrumentation import METRICS


class InteractionSystemTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.ensure_ingredient_tables()
        self.repo.seed_interactions()
        self.repo.seed_taxonomy()
        self.graph = IngredientGraph(self.repo)
        pm._cache.clear()
        pm._context_cache.clear()
        METRICS.reset()

    def tearDown(self):
        pm._cache.clear()
        pm._context_cache.clear()
        METRICS.reset()
        self._tmp.cleanup()

    def test_shadow_match(self):
        # shelf с BHA, кандидат с retinol → OLD конфликт + NEW interaction (seed) найдена
        shelf = [{"name": "BHA Serum", "category": "Сыворотки", "ingredients": "Aqua, Salicylic Acid", "score": 80}]
        candidate = {"name": "Retinol Cream", "category": "Увлажнение", "ingredients": "Aqua, Retinol", "score": 80}
        report = shadow_compare_interactions(shelf, candidate, graph=self.graph)
        self.assertGreaterEqual(report["old_conflicts"], 1)
        self.assertEqual(report["mismatches"], 0)
        self.assertGreaterEqual(report["matches"], 1)

    def test_shadow_mismatch(self):
        # shelf с BHA, кандидат с retinal (fragment, нет в seed) → OLD конфликт, NEW unknown
        shelf = [{"name": "BHA Serum", "category": "Сыворотки", "ingredients": "Aqua, Salicylic Acid", "score": 80}]
        candidate = {"name": "Retinal Cream", "category": "Увлажнение", "ingredients": "Aqua, Retinal", "score": 80}
        report = shadow_compare_interactions(shelf, candidate, graph=self.graph)
        self.assertGreaterEqual(report["old_conflicts"], 1)
        self.assertGreaterEqual(report["mismatches"], 1)

    def test_does_not_change_score(self):
        # shadow-функция возвращает отчёт и не модифицирует вход
        shelf = [{"name": "BHA Serum", "category": "Сыворотки", "ingredients": "Aqua, Salicylic Acid", "score": 80}]
        candidate = {"name": "Retinol Cream", "category": "Увлажнение", "ingredients": "Aqua, Retinol", "score": 80}
        candidate_before = dict(candidate)
        shadow_compare_interactions(shelf, candidate, graph=self.graph)
        self.assertEqual(candidate, candidate_before)

    def test_detect_cross_product_class_routing(self):
        # exact lookup только после class routing
        shelf = [
            {"name": "BHA Serum", "ingredients": "Aqua, Salicylic Acid"},
            {"name": "Plain", "ingredients": "Aqua, Glycerin"},
        ]
        candidate = {"name": "Retinol Cream", "ingredients": "Aqua, Retinol"}
        rep = detect_cross_product_interactions(shelf, candidate, graph=self.graph)
        self.assertEqual(rep["before"], 2)   # 2 shelf × 1 candidate
        self.assertEqual(rep["after"], 1)    # только BHA релевантен
        self.assertGreaterEqual(rep["exact_lookups"], 1)  # retinol × salicylic acid
        g = METRICS.snapshot()["gauges"]
        self.assertEqual(g["interaction_exact_lookup_count"], rep["exact_lookups"])
        self.assertEqual(g["class_filtered_count"], 1)

    def test_class_membership_does_not_create_interaction(self):
        # vitamin_c (ascorbyl palmitate) × niacinamide: класс релевантен, exact unknown
        shelf = [{"name": "Niac", "ingredients": "Aqua, Niacinamide"}]
        candidate = {"name": "VC", "ingredients": "Aqua, Ascorbyl Palmitate"}
        rep = detect_cross_product_interactions(shelf, candidate, graph=self.graph)
        states = {r["state"] for r in rep["results"]}
        self.assertIn("unknown", states)
        self.assertNotIn("known", states)

    # ------------------------------------------------------------------
    # Фаза 6 — Dynamic Shelf Model поверх Static Product Models.
    # ------------------------------------------------------------------
    def test_dynamic_shelf_model_class_routing(self):
        shelf = [
            {"id": 1, "name": "BHA Serum", "ingredients": "Aqua, Salicylic Acid"},
            {"id": 2, "name": "Plain", "ingredients": "Aqua, Glycerin"},
        ]
        candidate = {"id": 3, "name": "Retinol Cream", "ingredients": "Aqua, Retinol"}
        dyn = build_dynamic_shelf_model(shelf, candidate, graph=self.graph)
        self.assertEqual(dyn["before"], 2)   # 2 shelf × 1 candidate
        self.assertEqual(dyn["after"], 1)    # только BHA релевантен
        self.assertGreaterEqual(dyn["exact_lookups"], 1)
        g = METRICS.snapshot()["gauges"]
        self.assertEqual(g["interaction_candidate_count_before"], 2)
        self.assertEqual(g["interaction_candidate_count_after"], 1)
        self.assertEqual(g["class_filtered_count"], 1)
        self.assertEqual(g["interaction_exact_lookup_count"], dyn["exact_lookups"])

    def test_dynamic_shelf_model_unknown_not_zero(self):
        shelf = [{"id": 1, "name": "Niac", "ingredients": "Aqua, Niacinamide"}]
        candidate = {"id": 2, "name": "VC", "ingredients": "Aqua, Ascorbyl Palmitate"}
        dyn = build_dynamic_shelf_model(shelf, candidate, graph=self.graph)
        states = {r["state"] for r in dyn["results"]}
        self.assertIn("unknown", states)
        self.assertNotIn("known", states)

    def test_dynamic_shelf_model_does_not_change_score(self):
        shelf = [{"id": 1, "name": "BHA Serum", "ingredients": "Aqua, Salicylic Acid", "score": 80}]
        candidate = {"id": 2, "name": "Retinol Cream", "ingredients": "Aqua, Retinol", "score": 80}
        shelf_before = [dict(p) for p in shelf]
        cand_before = dict(candidate)
        build_dynamic_shelf_model(shelf, candidate, graph=self.graph)
        self.assertEqual(shelf, shelf_before)
        self.assertEqual(candidate, cand_before)

    def test_dynamic_shelf_model_reuses_static_model_cache(self):
        # повторный вызов → static model/context из кэша (product_model_cache_hit)
        shelf = [{"id": 1, "name": "BHA Serum", "ingredients": "Aqua, Salicylic Acid"}]
        candidate = {"id": 2, "name": "Retinol Cream", "ingredients": "Aqua, Retinol"}
        build_dynamic_shelf_model(shelf, candidate, graph=self.graph)
        METRICS.reset()
        build_dynamic_shelf_model(shelf, candidate, graph=self.graph)
        c = METRICS.snapshot()["counters"]
        self.assertGreaterEqual(c.get("product_model_cache_hit", 0), 2)  # 2 shelf-модели из кэша
        self.assertGreaterEqual(c.get("product_context_cache_hit", 0), 1)

    # ------------------------------------------------------------------
    # Фаза 7 — подготовка interaction-записей для Scoring Engine.
    # ------------------------------------------------------------------
    def test_internal_interactions_are_insufficient_for_seed(self):
        # seed interactions (confidence=0.2) → insufficient, НЕ known → не влияют на score.
        from app.product_model import get_internal_interactions
        product = {"id": 1, "ingredients": "Aqua, Retinol, Salicylic Acid"}
        records = get_internal_interactions(product, graph=self.graph)
        self.assertTrue(records)
        self.assertTrue(all(r["state"] == "insufficient" for r in records))
        self.assertFalse(any(r["state"] == "known" for r in records))

    def test_flatten_cross_product_interactions(self):
        shelf = [{"id": 1, "name": "BHA Serum", "ingredients": "Aqua, Salicylic Acid"}]
        candidate = {"id": 2, "name": "Retinol Cream", "ingredients": "Aqua, Retinol"}
        dyn = build_dynamic_shelf_model(shelf, candidate, graph=self.graph)
        flat = flatten_cross_product_interactions(dyn["results"])
        self.assertTrue(flat)
        self.assertTrue(all(r["type"] == "cross" for r in flat))
        self.assertTrue(all("ingredient_a" in r and "ingredient_b" in r for r in flat))


if __name__ == "__main__":
    unittest.main()
