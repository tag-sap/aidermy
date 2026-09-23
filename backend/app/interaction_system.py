# interaction_system.py
# Фаза 3B — Interaction System в SHADOW MODE.
#
# Сравнивает legacy CONFLICT_RULES (old) с новым knowledge lookup (new),
# НЕ влияя на пользовательский score / verdict / ranking. Только логирует
# расхождения в METRICS и возвращает отчёт.

from __future__ import annotations

from typing import Any, Dict, List

from .instrumentation import METRICS


def _relevant_cross_pairs(cand_ctx: Dict[str, Any], shelf_ctx: Dict[str, Any], routes) -> tuple:
    """Кросс-продуктовые релевантные ingredient-пары по классам (без повторного class lookup)."""
    cand_cti = cand_ctx["class_to_ingredients"]
    shelf_cti = shelf_ctx["class_to_ingredients"]
    pairs: set = set()
    class_pairs: set = set()
    for route_a, route_b in routes:
        a, b = set(route_a), set(route_b)
        for ca in a:
            for cb in b:
                ci_list = cand_cti.get(ca, [])
                si_list = shelf_cti.get(cb, [])
                if ci_list and si_list:
                    class_pairs.add((ca, cb))
                    for ci in ci_list:
                        for si in si_list:
                            pairs.add(tuple(sorted([ci, si])))
                ci_list2 = cand_cti.get(cb, [])
                si_list2 = shelf_cti.get(ca, [])
                if ci_list2 and si_list2:
                    class_pairs.add((cb, ca))
                    for ci in ci_list2:
                        for si in si_list2:
                            pairs.add(tuple(sorted([ci, si])))
    return pairs, class_pairs


def build_dynamic_shelf_model(
    shelf_products: List[Dict[str, Any]],
    candidate: Dict[str, Any],
    graph=None,
) -> Dict[str, Any]:
    """Dynamic Shelf Model (production path, Фаза 6).

    Строится поверх Static Product Models (cache-first классы) + ProductContext
    (классы резолвены один раз). Pipeline:
        Static Product Models → class routing → только relevant ingredient pairs
        → exact interaction lookup.

    НЕ влияет на score/verdict/ranking/hard constraints (scoring остаётся отдельным).
    Ставит метрики before/after/filtered/exact/class_pair.
    """
    from .ingredient_graph import GRAPH
    from .product_model import get_or_build_product_model, get_or_build_product_context

    g = graph or GRAPH
    repo = getattr(g, "_repo", None)
    routes = g._repo.get_class_routes()

    # Static Product Models (объективное состояние продуктов, cache-first).
    shelf_models = [get_or_build_product_model(p, graph=g, repository=repo) for p in shelf_products]
    cand_model = get_or_build_product_model(candidate, graph=g, repository=repo)
    cand_classes = set(cand_model.get("classes") or [])

    # ProductContext для кандидата — классы резолвены один раз.
    cand_ctx = get_or_build_product_context(cand_model["ingredient_names"], graph=g)

    before = len(shelf_products)
    after = 0
    exact_lookups = 0
    class_pairs: set = set()
    results: List[Dict[str, Any]] = []

    for sm in shelf_models:
        sc = set(sm.get("classes") or [])
        if not cand_classes or not sc:
            continue
        if not g._classes_relevant(cand_classes, sc, routes):
            continue
        after += 1
        shelf_ctx = get_or_build_product_context(sm["ingredient_names"], graph=g)
        pairs, cps = _relevant_cross_pairs(cand_ctx, shelf_ctx, routes)
        class_pairs |= cps
        for a, b in pairs:
            exact_lookups += 1
            results.append(g.lookup_interaction(a, b))

    METRICS.set_gauge("interaction_candidate_count_before", before)
    METRICS.set_gauge("interaction_candidate_count_after", after)
    METRICS.set_gauge("class_filtered_count", before - after)
    METRICS.set_gauge("class_pair_count", len(class_pairs))
    METRICS.set_gauge("interaction_exact_lookup_count", exact_lookups)
    return {
        "before": before,
        "after": after,
        "exact_lookups": exact_lookups,
        "class_pairs": len(class_pairs),
        "results": results,
    }


def flatten_cross_product_interactions(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Флаттенит результаты Dynamic Shelf Model в плоские interaction-записи (Фаза 7).

    Каждая запись: ingredient_a/ingredient_b/type="cross" + поля lookup
    (axis/direction/strength/confidence/state). Готовы для Scoring Engine.
    """
    out: List[Dict[str, Any]] = []
    for r in results or []:
        a, b = r.get("a"), r.get("b")
        for rec in r.get("records", []):
            rec = dict(rec)
            rec["ingredient_a"] = a
            rec["ingredient_b"] = b
            rec["type"] = "cross"
            out.append(rec)
    return out


def detect_cross_product_interactions(
    shelf_products: List[Dict[str, Any]],
    candidate: Dict[str, Any],
    graph=None,
) -> Dict[str, Any]:
    """Реальный class routing: exact lookup ТОЛЬКО для релевантных ingredient-пар.

    Фаза 6 — обёртка над build_dynamic_shelf_model (context-based, без O(n²) class lookups).
    НЕ влияет на score (shadow-only). Ставит interaction_exact_lookup_count.
    """
    return build_dynamic_shelf_model(shelf_products, candidate, graph=graph)


def shadow_compare_interactions(
    shelf_products: List[Dict[str, Any]],
    candidate: Dict[str, Any],
    graph=None,
) -> Dict[str, Any]:
    """Shadow-сравнение OLD vs NEW для кандидата на фоне текущей полки.

    OLD: compute_shelf_compatibility (CONFLICT_RULES) → список конфликтов.
    NEW: IngredientGraph.lookup_interaction по совпавшим ингредиентам.

    Возвращает отчёт; НЕ меняет score. Логирует match/mismatch в METRICS.
    """
    from .shelf_compatibility import compute_shelf_compatibility
    from .ingredient_graph import GRAPH

    g = graph or GRAPH

    old_result = compute_shelf_compatibility(list(shelf_products) + [candidate])
    old_conflicts = old_result.get("conflicts") or []

    comparisons: List[Dict[str, Any]] = []
    matches = 0
    for c in old_conflicts:
        a_list = c.get("a") or []
        b_list = c.get("b") or []
        new_results = []
        for a in a_list:
            for b in b_list:
                r = g.lookup_interaction(a, b)
                new_results.append({
                    "a": r["a"], "b": r["b"], "state": r["state"], "records": r["records"],
                })
        matched = any(r["state"] != "unknown" for r in new_results)
        if matched:
            matches += 1
            METRICS.increment("interaction_match")
        else:
            METRICS.increment("interaction_mismatch")
        comparisons.append({
            "label": c.get("label"),
            "old_rule_result": "conflict",
            "matched_ingredients": {"a": list(a_list), "b": list(b_list)},
            "new_interaction_results": new_results,
            "match": matched,
        })

    mismatches = len(comparisons) - matches
    METRICS.set_gauge("old_new_mismatch_count", mismatches)
    return {
        "old_conflicts": len(old_conflicts),
        "matches": matches,
        "mismatches": mismatches,
        "comparisons": comparisons,
    }
