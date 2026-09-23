import os
import tempfile
import unittest

from app.ingredient_graph import IngredientGraph
from app.ingredient_repository import IngredientRepository
from app.instrumentation import METRICS


class TaxonomyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.seed_taxonomy()
        self.graph = IngredientGraph(self.repo)
        METRICS.reset()

    def tearDown(self):
        METRICS.reset()
        self._tmp.cleanup()

    def test_seed_taxonomy_creates_8_classes(self):
        classes = self.repo.get_all_classes()
        self.assertEqual(len(classes), 8)
        # идемпотентность: повторный seed не добавляет классов
        self.assertEqual(self.repo.seed_taxonomy(), 0)

    def test_ingredient_to_classes(self):
        self.assertEqual(self.graph.lookup_classes("Retinol"), ["retinoids"])
        self.assertIn("vitamin_c", self.graph.lookup_classes("ascorbyl palmitate"))
        self.assertEqual(self.graph.lookup_classes("UnknownThing"), [])

    def test_multiple_classes_with_parent(self):
        # salicylic acid → bha + exfoliants (предок)
        classes = self.graph.lookup_classes("Salicylic Acid")
        self.assertIn("bha", classes)
        self.assertIn("exfoliants", classes)

    def test_aha_resolves_to_exfoliants(self):
        classes = self.graph.lookup_classes("Glycolic Acid")
        self.assertIn("aha", classes)
        self.assertIn("exfoliants", classes)

    def test_class_route_relevant(self):
        shelf = [{"name": "BHA", "ingredients": "Aqua, Salicylic Acid"}]
        cand = [{"name": "Retinol", "ingredients": "Aqua, Retinol"}]
        r = self.graph.class_route(shelf, cand)
        self.assertEqual(r["before"], 1)
        self.assertEqual(r["after"], 1)  # релевантная пара (retinoid × bha)

    def test_class_route_filtered(self):
        shelf = [{"name": "Plain", "ingredients": "Aqua, Glycerin"}]
        cand = [{"name": "Other", "ingredients": "Aqua, Panthenol"}]
        r = self.graph.class_route(shelf, cand)
        self.assertEqual(r["before"], 1)
        self.assertEqual(r["after"], 0)  # нет релевантных классов

    def test_no_false_positive_from_class(self):
        # класс витамин C для ascorbyl palmitate есть, но exact interaction unknown
        self.assertIn("vitamin_c", self.graph.lookup_classes("ascorbyl palmitate"))
        self.repo.seed_interactions()
        self.graph.invalidate()
        r = self.graph.lookup_interaction("ascorbyl palmitate", "niacinamide")
        self.assertEqual(r["state"], "unknown")  # не фабрикуем interaction из класса

    def test_class_route_metrics(self):
        shelf = [{"name": "BHA", "ingredients": "Aqua, Salicylic Acid"}]
        cand = [{"name": "Retinol", "ingredients": "Aqua, Retinol"},
                {"name": "Plain", "ingredients": "Aqua, Glycerin"}]
        self.graph.class_route(shelf, cand)
        g = METRICS.snapshot()["gauges"]
        self.assertEqual(g["interaction_candidate_count_before"], 2)
        self.assertEqual(g["interaction_candidate_count_after"], 1)
        self.assertEqual(g["class_filtered_count"], 1)
        self.assertGreaterEqual(g["class_pair_count"], 1)


if __name__ == "__main__":
    unittest.main()
