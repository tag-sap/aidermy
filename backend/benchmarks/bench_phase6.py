# benchmarks/bench_phase6.py
# Фаза 6 — Interaction Pipeline: class routing в production path + устранение O(n²).
#
# Самодостаточный бенчмарк (не требует users/products): temp DB + seed.
# Замеряет: class_lookup_count (O(n), не O(n²)), interaction_lookup_count (exact),
# candidate before/after, DB queries, cache hit/miss, build time.
#
# Запуск:  cd backend && python benchmarks/bench_phase6.py

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.product_model as pm
from app.ingredient_graph import IngredientGraph
from app.ingredient_repository import IngredientRepository
from app.instrumentation import METRICS
from app.interaction_system import build_dynamic_shelf_model


def _seed_repo(db_path):
    repo = IngredientRepository(db_path)
    repo.ensure_ingredient_tables()
    repo.seed_taxonomy()
    repo.seed_interactions()
    return repo


def main():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "bench.db")
    repo = _seed_repo(db_path)
    graph = IngredientGraph(repo)

    # ---------------------------------------------------------------
    # 1) Большой состав: class lookups растут ЛИНЕЙНО (O(n)), не O(n²)
    # ---------------------------------------------------------------
    base = ["Aqua", "Retinol", "Salicylic Acid", "Niacinamide", "Ascorbyl Palmitate",
            "Glycolic Acid", "Benzoyl Peroxide", "Lactic Acid"]
    fill = ["Filler%d" % i for i in range(200)]
    ings = base + fill
    n = len(ings)
    naive_pairs = n * (n - 1) // 2
    naive_class_lookups = n * (n - 1)  # OLD: 2 lookup_classes на каждую пару

    pm._context_cache.clear()
    pm._cache.clear()
    METRICS.reset()
    t0 = time.perf_counter()
    pm.get_or_build_product_model({"id": 99999, "ingredients": ", ".join(ings)},
                                  graph=graph, repository=repo)
    t_build = (time.perf_counter() - t0) * 1000
    snap = METRICS.snapshot()
    c = snap["counters"]
    print("[1] large_composition unique_ings=%d" % n)
    print("    naive_pairs=%d  naive_class_lookups(OLD O(n²))=%d" % (naive_pairs, naive_class_lookups))
    print("    actual_class_lookups(NEW O(n))=%s  actual_interaction_lookups=%s" % (
        c.get("class_lookup_count"), c.get("interaction_lookup_count")))
    print("    static_model_build_ms=%.2f  db_queries=%s" % (t_build, c.get("db_query_count")))

    # ---------------------------------------------------------------
    # 2) Static Product Model: cache-first (build vs hit)
    # ---------------------------------------------------------------
    pm._context_cache.clear()
    pm._cache.clear()
    small = {"id": 1, "ingredients": "Aqua, Retinol, Salicylic Acid"}
    METRICS.reset()
    pm.get_or_build_product_model(small, graph=graph, repository=repo)
    first = METRICS.snapshot()
    METRICS.reset()
    pm.get_or_build_product_model(small, graph=graph, repository=repo)
    second = METRICS.snapshot()
    print("[2] static_model_cache_first")
    print("    first build: db_queries=%s class_lookups=%s build_count=%s" % (
        first["counters"].get("db_query_count"), first["counters"].get("class_lookup_count"),
        first["counters"].get("static_model_build_count")))
    print("    repeat hit : db_queries=%s class_lookups=%s cache_hit=%s cache_miss=%s" % (
        second["counters"].get("db_query_count"), second["counters"].get("class_lookup_count"),
        second["counters"].get("product_model_cache_hit"), second["counters"].get("product_model_cache_miss")))

    # ---------------------------------------------------------------
    # 3) Dynamic Shelf Model: class routing в production path
    # ---------------------------------------------------------------
    pm._context_cache.clear()
    pm._cache.clear()
    # полка из N продуктов, только 1 релевантен кандидату (BHA)
    shelf = [{"id": 100 + i, "name": "Shelf%d" % i, "ingredients": "Aqua, Glycerin"} for i in range(20)]
    shelf.append({"id": 999, "name": "BHA Serum", "ingredients": "Aqua, Salicylic Acid"})
    candidate = {"id": 5000, "name": "Retinol Cream", "ingredients": "Aqua, Retinol"}
    METRICS.reset()
    t0 = time.perf_counter()
    dyn = build_dynamic_shelf_model(shelf, candidate, graph=graph)
    t_dyn = (time.perf_counter() - t0) * 1000
    snap = METRICS.snapshot()
    print("[3] dynamic_shelf_model shelf=%d" % len(shelf))
    print("    before=%d after=%d class_filtered=%d exact_lookups=%d class_pairs=%s" % (
        dyn["before"], dyn["after"], snap["gauges"].get("class_filtered_count"),
        dyn["exact_lookups"], snap["gauges"].get("class_pair_count")))
    print("    class_lookups=%s interaction_lookups=%s dyn_ms=%.2f" % (
        snap["counters"].get("class_lookup_count"), snap["counters"].get("interaction_lookup_count"), t_dyn))


if __name__ == "__main__":
    main()
