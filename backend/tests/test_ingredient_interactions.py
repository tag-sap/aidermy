import os
import tempfile
import unittest

from app.ingredient_graph import EffectState, IngredientGraph
from app.ingredient_repository import IngredientRepository
from app.instrumentation import METRICS


class IngredientInteractionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        METRICS.reset()

    def tearDown(self):
        METRICS.reset()
        self._tmp.cleanup()

    def test_seed_migration_inserts_29_records_idempotently(self):
        first = self.repo.seed_interactions()
        second = self.repo.seed_interactions()
        self.assertEqual(first, 29)
        self.assertEqual(second, 0)  # idempotent
        self.assertEqual(len(self.repo.get_all_interactions()), 29)

    def test_seed_data_marked_low_confidence(self):
        self.repo.seed_interactions()
        rows = self.repo.get_all_interactions()
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertEqual(r["source"], "seed")
            self.assertEqual(r["confidence"], 0.2)
            self.assertIn("legacy heuristic", r["evidence"])

    def test_ab_equals_ba(self):
        graph = IngredientGraph(self.repo)
        r1 = graph.lookup_interaction("Retinol", "Salicylic Acid")
        r2 = graph.lookup_interaction("Salicylic Acid", "Retinol")
        self.assertEqual((r1["a"], r1["b"]), (r2["a"], r2["b"]))
        self.assertEqual(r1["state"], r2["state"])

    def test_canonical_pair_ordering(self):
        a = self.repo.save_interaction("Zinc Oxide", "Alpha Acid", "irritation", "positive", confidence=0.9)
        self.assertLess(a["ingredient_a"], a["ingredient_b"])

    def test_duplicate_prevention(self):
        self.repo.save_interaction("AlphaX", "BetaY", "irritation", "positive", confidence=0.9)
        self.repo.save_interaction("BetaY", "AlphaX", "irritation", "positive", confidence=0.9)
        graph = IngredientGraph(self.repo)
        r = graph.lookup_interaction("AlphaX", "BetaY")
        self.assertEqual(len(r["records"]), 1)

    def test_known_state(self):
        graph = IngredientGraph(self.repo)
        graph._repo.save_interaction("X", "Y", "irritation", "positive", confidence=0.9)
        graph.invalidate()
        r = graph.lookup_interaction("X", "Y")
        self.assertEqual(r["state"], EffectState.KNOWN)

    def test_insufficient_state_seed(self):
        self.repo.seed_interactions()
        graph = IngredientGraph(self.repo)
        r = graph.lookup_interaction("Retinol", "Salicylic Acid")
        self.assertEqual(r["state"], EffectState.INSUFFICIENT)

    def test_unknown_state(self):
        graph = IngredientGraph(self.repo)
        r = graph.lookup_interaction("Glycerin", "Panthenol")
        self.assertEqual(r["state"], EffectState.UNKNOWN)

    def test_cache_miss_then_hit(self):
        graph = IngredientGraph(self.repo)
        graph.lookup_interaction("Retinol", "Salicylic Acid")  # miss
        graph.lookup_interaction("Retinol", "Salicylic Acid")  # hit
        c = METRICS.snapshot()["counters"]
        self.assertEqual(c.get("cache_miss"), 1)
        self.assertEqual(c.get("cache_hit"), 1)

    def test_no_db_query_on_cache_hit(self):
        graph = IngredientGraph(self.repo)
        graph.lookup_interaction("Retinol", "Salicylic Acid")
        METRICS.reset()
        graph.lookup_interaction("Retinol", "Salicylic Acid")
        self.assertEqual(METRICS.snapshot()["counters"].get("db_query_count", 0), 0)

    def test_preserves_confidence_evidence_source(self):
        self.repo.save_interaction(
            "A", "B", "irritation", "positive",
            strength=0.6, confidence=0.85, evidence="pubmed:123", source="pubmed",
        )
        graph = IngredientGraph(self.repo)
        r = graph.lookup_interaction("A", "B")
        rec = r["records"][0]
        self.assertEqual(rec["confidence"], 0.85)
        self.assertEqual(rec["source"], "pubmed")
        self.assertEqual(rec["evidence"], "pubmed:123")


if __name__ == "__main__":
    unittest.main()
