# benchmarks/bench_pipeline.py
# Бенчмарк пайплайна (Фаза 0+1) на базе METRICS.
#
# Запуск:  cd backend && . venv/bin/activate && python benchmarks/bench_pipeline.py
# Читает METRICS (db_query_count, ai_call_count, pipeline_duration, ingredient_count,
# interaction_candidate_count) и замеряет wall-clock.
#
# Сценарии (маппинг на Test A–H):
#   A_recommend   — новый подбор (рекомендация)
#   B_repeat      — повторный подбор (тот же вход) — отсутствие кэша модели
#   C_known_reuse — переиспользование знания известного ингредиента
#   H_determinism — одинаковый результат при одинаковом входе (correctness)

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.instrumentation import METRICS
from app.database import get_connection, AIDERMY_DB
from app.shelf_service import recommend_products
from app.ingredient_enrichment import find_unknown_ingredients


def user3():
    c = get_connection(AIDERMY_DB)
    row = dict(c.execute("SELECT * FROM users WHERE id=3").fetchone())
    c.close()
    return {
        "id": row["id"], "skin_type": row["skin_type"], "age": row["age"],
        "concerns": row["concerns"], "allergies": row["allergies"],
        "custom_text": row["custom_text"],
    }


async def run():
    u = user3()

    METRICS.reset()
    t0 = time.perf_counter()
    recs = await recommend_products(u, "face", "Очищение", set())
    t1 = time.perf_counter()
    print("A_recommend  wall_ms=%d  %s" % ((t1 - t0) * 1000, json.dumps(METRICS.snapshot(), ensure_ascii=False)))

    METRICS.reset()
    t0 = time.perf_counter()
    recs2 = await recommend_products(u, "face", "Очищение", set())
    t1 = time.perf_counter()
    print("B_repeat     wall_ms=%d  %s" % ((t1 - t0) * 1000, json.dumps(METRICS.snapshot(), ensure_ascii=False)))

    print("H_determinism same=%s" % ([r.get("slug") for r in recs] == [r.get("slug") for r in recs2]))

    METRICS.reset()
    unk = find_unknown_ingredients(["Glycerin", "Aqua", "Niacinamide", "Hyaluronic Acid"])
    print("C_known_reuse unknown=%d  %s" % (len(unk), json.dumps(METRICS.snapshot(), ensure_ascii=False)))

    # G: graph cache (cache-first): первый lookup = miss (DB), второй = hit (без DB)
    from app.ingredient_graph import GRAPH
    GRAPH.invalidate()
    METRICS.reset()
    GRAPH.get_canonical_knowledge_map()
    miss_snap = METRICS.snapshot()
    METRICS.reset()
    GRAPH.get_canonical_knowledge_map()
    hit_snap = METRICS.snapshot()
    print("G_graph_cache miss=%s hit=%s" % (
        json.dumps(miss_snap, ensure_ascii=False),
        json.dumps(hit_snap, ensure_ascii=False),
    ))

    # H: interaction lookup (известная seed-пара vs неизвестная)
    from app.ingredient_graph import GRAPH as G2
    G2.invalidate()
    METRICS.reset()
    t0 = time.perf_counter()
    known = G2.lookup_interaction("Retinol", "Salicylic Acid")
    t_known = (time.perf_counter() - t0) * 1000
    unknown = G2.lookup_interaction("Glycerin", "Panthenol")
    print("H_interaction known=%s unknown=%s lookup_ms=%.2f %s" % (
        known["state"], unknown["state"], t_known, json.dumps(METRICS.snapshot(), ensure_ascii=False)))

    # I: class routing (before/after candidate counts) — 44 candidates × 2 shelf
    from app.shelf_service import _query_candidates, _load_shelf_products, _build_user_profile
    from app.ingredient_graph import GRAPH as G3
    G3.invalidate()
    profile = _build_user_profile(u)
    cands = _query_candidates("face", "Очищение")
    shelf = _load_shelf_products(u, "face", knowledge=G3.get_canonical_knowledge_map(), history=[])
    cand_products = [{"name": c.get("name"), "ingredients": c.get("ingredients") or ""} for c in cands]
    METRICS.reset()
    route = G3.class_route(shelf, cand_products)
    print("I_class_routing before=%d after=%d %s" % (
        route["before"], route["after"], json.dumps(METRICS.snapshot(), ensure_ascii=False)))

    # J: static product model (первый запуск = build, повторный = cache hit)
    import app.product_model as pm
    from app.ingredient_repository import IngredientRepository as IR
    pm._cache.clear()
    cand0 = cands[0] if cands else {"id": 1, "ingredients": "Aqua"}
    METRICS.reset()
    m1 = pm.get_or_build_product_model(cand0, graph=G3, repository=IR())
    first_snap = METRICS.snapshot()
    METRICS.reset()
    m2 = pm.get_or_build_product_model(cand0, graph=G3, repository=IR())
    second_snap = METRICS.snapshot()
    print("J_static_model first=%s second=%s same=%s" % (
        json.dumps(first_snap, ensure_ascii=False),
        json.dumps(second_snap, ensure_ascii=False),
        m1 == m2,
    ))

    # K: большой состав — class lookups растут ЛИНЕЙНО (Фаза 6), не как O(n²)
    import app.product_model as pm2
    from app.ingredient_repository import IngredientRepository as IR2
    pm2._context_cache.clear()
    pm2._cache.clear()
    _base = ["Aqua", "Retinol", "Salicylic Acid", "Niacinamide", "Ascorbyl Palmitate"]
    _fill = ["Filler%d" % i for i in range(200)]
    large_ings = _base + _fill
    big_product = {"id": 99999, "ingredients": ", ".join(large_ings)}
    n = len(large_ings)
    naive_pairs = n * (n - 1) // 2
    naive_class_lookups = n * (n - 1)  # OLD: 2 class lookup на каждую пару
    METRICS.reset()
    t0 = time.perf_counter()
    pm2.get_or_build_product_model(big_product, graph=G3, repository=IR2())
    t_big = (time.perf_counter() - t0) * 1000
    snap = METRICS.snapshot()
    cls = snap["counters"].get("class_lookup_count", 0)
    print("K_large_composition unique_ings=%d naive_pairs=%d naive_class_lookups=%d "
          "actual_class_lookups=%d build_ms=%.2f %s" % (
              n, naive_pairs, naive_class_lookups, cls, t_big, json.dumps(snap, ensure_ascii=False)))

    # L: dynamic shelf model — class routing в production path (Фаза 6)
    from app.interaction_system import build_dynamic_shelf_model
    pm2._context_cache.clear()
    pm2._cache.clear()
    shelf_for_dyn = [{"id": 100 + i, "name": p.get("name"), "ingredients": p.get("ingredients") or ""}
                     for i, p in enumerate(shelf)]
    cand_for_dyn = {"id": 900, "name": cands[0].get("name"), "ingredients": cands[0].get("ingredients") or ""}
    METRICS.reset()
    dyn = build_dynamic_shelf_model(shelf_for_dyn, cand_for_dyn, graph=G3)
    print("L_dynamic_shelf_model before=%d after=%d exact=%d %s" % (
        dyn["before"], dyn["after"], dyn["exact_lookups"], json.dumps(METRICS.snapshot(), ensure_ascii=False)))


if __name__ == "__main__":
    asyncio.run(run())
