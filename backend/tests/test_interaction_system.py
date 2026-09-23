import os
import tempfile
import unittest

from app.ingredient_graph import IngredientGraph
from app.ingredient_repository import IngredientRepository
from app.interaction_system import detect_cross_product_interactions, shadow_compare_interactions
from app.instrumentation import METRICS


class InteractionSystemTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.seed_interactions()
        self.repo.seed_taxonomy()
        self.graph = IngredientGraph(self.repo)
        METRICS.reset()

    def tearDown(self):
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


if __name__ == "__main__":
    unittest.main()
