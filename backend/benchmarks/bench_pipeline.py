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


if __name__ == "__main__":
    asyncio.run(run())
