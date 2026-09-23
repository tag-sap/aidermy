# interaction_system.py
# Фаза 3B — Interaction System в SHADOW MODE.
#
# Сравнивает legacy CONFLICT_RULES (old) с новым knowledge lookup (new),
# НЕ влияя на пользовательский score / verdict / ranking. Только логирует
# расхождения в METRICS и возвращает отчёт.

from __future__ import annotations

from typing import Any, Dict, List

from .instrumentation import METRICS


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
