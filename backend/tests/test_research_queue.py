# tests/test_research_queue.py
# Фаза 9 — Batch Research Engine: dedup, batch, canonical output, failure isolation.

import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from app import research_queue as rq
from app.ingredient_repository import IngredientRepository
from app.instrumentation import METRICS


class ResearchQueueTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.ensure_ingredient_tables()
        self.repo.ensure_research_tables()
        rq.RESEARCH_POLL_INTERVAL = 0.01
        METRICS.reset()

    def tearDown(self):
        METRICS.reset()
        self._tmp.cleanup()

    # ---------------------------------------------------------------
    # Deduplication
    # ---------------------------------------------------------------
    def test_ingredient_dedup(self):
        tid1, created1 = self.repo.enqueue_research_task(
            rq.INGREDIENT_RESEARCH, rq._ingredient_dedup_key("Retinal"), {"ingredient": "retinal"}
        )
        tid2, created2 = self.repo.enqueue_research_task(
            rq.INGREDIENT_RESEARCH, rq._ingredient_dedup_key("Retinal"), {"ingredient": "retinal"}
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(tid1, tid2)

    def test_interaction_dedup_order_independent(self):
        tid1, _ = self.repo.enqueue_research_task(
            rq.INTERACTION_RESEARCH, rq._interaction_dedup_key("Retinol", "Glycolic Acid"),
            {"ingredient_a": "retinol", "ingredient_b": "glycolic acid"},
        )
        tid2, created2 = self.repo.enqueue_research_task(
            rq.INTERACTION_RESEARCH, rq._interaction_dedup_key("Glycolic Acid", "Retinol"),
            {"ingredient_a": "glycolic acid", "ingredient_b": "retinol"},
        )
        self.assertEqual(tid1, tid2)
        self.assertFalse(created2)

    def test_one_task_multiple_waiters(self):
        ids1, _ = rq.enqueue_research(self.repo, unknown_ingredients=["Retinal"])
        ids2, created2 = rq.enqueue_research(self.repo, unknown_ingredients=["Retinal"])
        self.assertEqual(ids1, ids2)
        self.assertEqual(created2, 0)

    def test_pending_task_reused(self):
        rq.enqueue_research(self.repo, unknown_ingredients=["Retinal"])
        ids, created = rq.enqueue_research(self.repo, unknown_ingredients=["Retinal"])
        self.assertEqual(created, 0)

    def test_processing_task_reused(self):
        rq.enqueue_research(self.repo, unknown_ingredients=["Retinal"])
        self.repo.claim_pending_research_tasks(10)  # → processing
        ids, created = rq.enqueue_research(self.repo, unknown_ingredients=["Retinal"])
        self.assertEqual(created, 0)

    # ---------------------------------------------------------------
    # Batch size / multiple batches
    # ---------------------------------------------------------------
    def test_batch_size_limits_claim(self):
        for i in range(10):
            self.repo.enqueue_research_task(rq.INGREDIENT_RESEARCH, f"ingredient:ing{i}", {"ingredient": f"ing{i}"})
        rq.RESEARCH_BATCH_SIZE = 4
        try:
            claimed = self.repo.claim_pending_research_tasks(rq.RESEARCH_BATCH_SIZE)
            self.assertEqual(len(claimed), 4)
        finally:
            rq.RESEARCH_BATCH_SIZE = 25

    def test_one_ai_request_for_many(self):
        calls = []

        async def fake_call(names):
            calls.append(list(names))
            return [
                {"inci_name": n, "canonical_name": n,
                 "effects": [{"axis": "hydration", "direction": "positive",
                              "effect_magnitude": "moderate", "confidence": 0.8}]}
                for n in names
            ]

        with patch.object(rq, "_call_ingredient_research", side_effect=fake_call):
            status = asyncio.run(rq.run_research(
                repository=self.repo, unknown_ingredients=["a", "b", "c"], timeout=5
            ))
        self.assertEqual(status, "completed")
        self.assertEqual(len(calls), 1)  # один AI-запрос
        self.assertEqual(len(calls[0]), 3)

    def test_multiple_batches(self):
        calls = []

        async def fake_call(names):
            calls.append(list(names))
            return [{"inci_name": n, "effects": []} for n in names]

        rq.RESEARCH_BATCH_SIZE = 2
        try:
            with patch.object(rq, "_call_ingredient_research", side_effect=fake_call):
                asyncio.run(rq.run_research(
                    repository=self.repo, unknown_ingredients=[f"i{i}" for i in range(5)], timeout=5
                ))
        finally:
            rq.RESEARCH_BATCH_SIZE = 25
        self.assertEqual(len(calls), 3)  # 5 / batch 2 = 3 batch'а

    # ---------------------------------------------------------------
    # Canonical output / unknown / insufficient / interaction
    # ---------------------------------------------------------------
    def test_canonical_output_saved(self):
        record = {
            "inci_name": "Retinal", "canonical_name": "Retinal",
            "effects": [{"axis": "irritation", "direction": "positive",
                         "effect_magnitude": "moderate", "confidence": 0.8}],
        }
        self.assertTrue(rq._save_ingredient_result(self.repo, "retinal", record))
        cm = self.repo.get_canonical_knowledge_map()
        self.assertIn("retinal", cm)
        self.assertIn("irritation", cm["retinal"])
        self.assertEqual(cm["retinal"]["irritation"]["direction"], "positive")

    def test_unknown_not_neutral(self):
        # effects пуст → ингредиент сохранён, но без канонических эффектов (не neutral).
        record = {"inci_name": "X", "canonical_name": "X", "effects": []}
        rq._save_ingredient_result(self.repo, "x", record)
        cm = self.repo.get_canonical_knowledge_map()
        self.assertNotIn("x", cm)

    def test_insufficient_evidence_not_scored(self):
        # direction=unknown → эффект не попадает в knowledge (не становится neutral).
        record = {
            "inci_name": "X", "canonical_name": "X",
            "effects": [{"axis": "sebum", "direction": "unknown",
                         "effect_magnitude": "weak", "confidence": 0.1}],
        }
        rq._save_ingredient_result(self.repo, "x", record)
        cm = self.repo.get_canonical_knowledge_map()
        self.assertNotIn("x", cm)

    def test_interaction_not_from_individual(self):
        # interaction сохраняется только из поля "interactions", не из individual effects.
        record = {
            "ingredient_a": "retinol", "ingredient_b": "salicylic acid",
            "interactions": [{"axis": "irritation", "direction": "positive",
                              "effect_magnitude": "moderate", "confidence": 0.7}],
        }
        self.assertTrue(rq._save_interaction_result(self.repo, record))
        interactions = self.repo.get_all_interactions()
        self.assertEqual(len(interactions), 1)
        self.assertEqual(interactions[0]["axis"], "irritation")

    # ---------------------------------------------------------------
    # Failure / retry / isolation
    # ---------------------------------------------------------------
    def test_retry_on_failure(self):
        tid, _ = self.repo.enqueue_research_task(rq.INGREDIENT_RESEARCH, "ingredient:x", {"ingredient": "x"})
        self.repo.claim_pending_research_tasks(10)  # attempts = 1
        self.assertEqual(self.repo.fail_research_task(tid, "err", max_attempts=3), "pending")

    def test_failed_after_max_attempts(self):
        tid, _ = self.repo.enqueue_research_task(rq.INGREDIENT_RESEARCH, "ingredient:x", {"ingredient": "x"})
        for _ in range(3):
            self.repo.claim_pending_research_tasks(10)
            status = self.repo.fail_research_task(tid, "err", max_attempts=3)
        self.assertEqual(status, "failed")

    def test_failed_research_status(self):
        async def fake_call(names):
            return None  # AI недоступен

        with patch.object(rq, "_call_ingredient_research", side_effect=fake_call):
            status = asyncio.run(rq.run_research(
                repository=self.repo, unknown_ingredients=["X"], timeout=5
            ))
        self.assertEqual(status, "failed")

    def test_invalid_item_does_not_break_batch(self):
        async def fake_call(names):
            # вернём результаты только для a и b (c отсутствует)
            return [
                {"inci_name": "a", "effects": [{"axis": "hydration", "direction": "positive",
                                                "effect_magnitude": "weak", "confidence": 0.7}]},
                {"inci_name": "b", "effects": [{"axis": "barrier", "direction": "positive",
                                                "effect_magnitude": "weak", "confidence": 0.7}]},
            ]

        with patch.object(rq, "_call_ingredient_research", side_effect=fake_call):
            asyncio.run(rq.run_research(repository=self.repo, unknown_ingredients=["a", "b", "c"], timeout=5))
        cm = self.repo.get_canonical_knowledge_map()
        self.assertIn("a", cm)
        self.assertIn("b", cm)
        self.assertNotIn("c", cm)  # c не сломал остальные результаты

    def test_kg_update_and_invalidation(self):
        record = {
            "inci_name": "Retinal", "effects": [{"axis": "irritation", "direction": "positive",
                                                 "effect_magnitude": "moderate", "confidence": 0.8}],
        }
        rq._save_ingredient_result(self.repo, "retinal", record)
        rq.invalidate_knowledge_caches()
        from app.ingredient_graph import IngredientGraph
        graph = IngredientGraph(self.repo)
        self.assertEqual(graph.lookup_effect("retinal", "irritation")["direction"], "positive")


if __name__ == "__main__":
    unittest.main()
