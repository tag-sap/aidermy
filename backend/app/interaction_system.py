# interaction_system.py
# Фаза 3B — Interaction System в SHADOW MODE.
#
# Сравнивает legacy CONFLICT_RULES (old) с новым knowledge lookup (new),
# НЕ влияя на пользовательский score / verdict / ranking. Только логирует
# расхождения в METRICS и возвращает отчёт.

from __future__ import annotations

from typing import Any, Dict, List

from .instrumentation import METRICS


def detect_cross_product_interactions(
    shelf_products: List[Dict[str, Any]],
    candidate: Dict[str, Any],
    graph=None,
) -> Dict[str, Any]:
    """Реальный class routing: exact lookup ТОЛЬКО для релевантных ingredient-пар.

    candidate × shelf → классы → class routing → релевантные пары → exact lookup.
    НЕ влияет на score (shadow-only). Метрики: before/after/exact_lookup/class_filtered/class_pair.
    """
    from .ingredient_graph import GRAPH

    g = graph or GRAPH
    routes = g._repo.get_class_routes()

    cand_ings = list(dict.fromkeys(g._split_ingredients(candidate.get("ingredients"))))
    shelf_ings: List[str] = []
    for sp in shelf_products:
        for i in g._split_ingredients(sp.get("ingredients")):
            if i not in shelf_ings:
                shelf_ings.append(i)

    cand_classes = {i: set(g.lookup_classes(i)) for i in cand_ings}
    shelf_classes = {i: set(g.lookup_classes(i)) for i in shelf_ings}

    before = 0
    after = 0
    exact_lookups = 0
    class_pairs: set = set()
    results: List[Dict[str, Any]] = []
    for ci in cand_ings:
        cc = cand_classes[ci]
        for si in shelf_ings:
            before += 1
            sc = shelf_classes[si]
            if not cc or not sc:
                continue
            if g._classes_relevant(cc, sc, routes):
                after += 1
                g._collect_class_pairs(cc, sc, routes, class_pairs)
                exact_lookups += 1
                results.append(g.lookup_interaction(ci, si))

    METRICS.set_gauge("interaction_candidate_count_before", before)
    METRICS.set_gauge("interaction_candidate_count_after", after)
    METRICS.set_gauge("interaction_exact_lookup_count", exact_lookups)
    METRICS.set_gauge("class_filtered_count", before - after)
    METRICS.set_gauge("class_pair_count", len(class_pairs))
    return {"before": before, "after": after, "exact_lookups": exact_lookups, "results": results}


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
