"""
Shadow Layer 4 — profile context scoring.

ВАЖНО:
- не подключается к production Score Engine;
- не меняет production score;
- используется только для calibration/shadow evaluation.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple


# Только доказанные на calibration выборке правила.
#
# penalty применяется непосредственно к canonical dimension
# ДО существующего tanh().
#
# Значения здесь намеренно параметризованы evaluator'ом.
RULES = {
    "tretinoin_x_retinoids": {
        "context": "tretinoin",
        "signal": "retinoids",
        "axis": "irritation",
    },
    "tretinoin_x_aha": {
        "context": "tretinoin",
        "signal": "aha",
        "axis": "irritation",
    },
    "tretinoin_x_bha": {
        "context": "tretinoin",
        "signal": "bha",
        "axis": "irritation",
    },
    "tretinoin_x_pha": {
        "context": "tretinoin",
        "signal": "pha",
        "axis": "irritation",
    },
    "professional_peel_x_aha": {
        "context": "professional_peel",
        "signal": "aha",
        "axis": "irritation",
    },
    "professional_peel_x_bha": {
        "context": "professional_peel",
        "signal": "bha",
        "axis": "irritation",
    },
    "professional_peel_x_pha": {
        "context": "professional_peel",
        "signal": "pha",
        "axis": "irritation",
    },
    "reactive_skin_x_allergen": {
        "context": "reactive_skin",
        "signal": "allergen",
        "axis": "sensitization",
    },
    "reactive_skin_x_sensitizer": {
        "context": "reactive_skin",
        "signal": "sensitizer",
        "axis": "sensitization",
    },
    "reactive_skin_x_fragrance_allergen": {
        "context": "reactive_skin",
        "signal": "fragrance_allergens",
        "axis": "sensitization",
    },
    "reactive_skin_x_essential_oils": {
        "context": "reactive_skin",
        "signal": "essential_oils",
        "axis": "sensitization",
    },
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _classes_for_ingredient(graph, ingredient: str) -> Set[str]:
    try:
        values = graph.lookup_classes(ingredient) or []
    except Exception:
        return set()

    result: Set[str] = set()

    for value in values:
        if isinstance(value, str):
            result.add(value.lower())
        elif isinstance(value, dict):
            name = value.get("name") or value.get("id")
            if name:
                result.add(str(name).lower())

    return result


def _signals_for_ingredient(
    graph,
    safety_map: Dict[str, Dict[str, Any]],
    ingredient: str,
) -> Set[str]:
    signals = _classes_for_ingredient(graph, ingredient)

    safety = safety_map.get(ingredient.strip().lower()) or {}

    if safety.get("is_allergen"):
        signals.add("allergen")

    if safety.get("is_sensitizer"):
        signals.add("sensitizer")

    return signals


def evaluate_product_context(
    *,
    ingredients: Iterable[str],
    active_contexts: Iterable[str],
    graph,
    safety_map: Dict[str, Dict[str, Any]],
    penalties: Dict[str, float],
) -> Dict[str, Any]:
    """
    Возвращает только shadow breakdown.

    penalty — абсолютное уменьшение соответствующей canonical dimension.

    Для reactive_skin × essential_oils используется diminishing returns:
    1-е масло получает полный penalty, последующие — penalty / rank.
    """

    contexts = {str(x).strip().lower() for x in active_contexts if str(x).strip()}

    dimensions_delta: Dict[str, float] = {}
    breakdown: List[Dict[str, Any]] = []

    # Счётчик однотипных essential_oils внутри одного контекста.
    essential_oil_rank = 0

    for raw_ingredient in ingredients:
        ingredient = str(raw_ingredient).strip()
        if not ingredient:
            continue

        signals = _signals_for_ingredient(graph, safety_map, ingredient)

        for rule_name, rule in RULES.items():
            context = rule["context"]
            signal = rule["signal"]

            if context not in contexts:
                continue

            if signal not in signals:
                continue

            base_penalty = max(
                0.0,
                _safe_float(penalties.get(rule_name), 0.0),
            )

            if base_penalty <= 0:
                continue

            penalty = base_penalty

            if rule_name == "reactive_skin_x_essential_oils":
                essential_oil_rank += 1
                penalty = base_penalty / essential_oil_rank

            axis = rule["axis"]
            dimensions_delta[axis] = (
                dimensions_delta.get(axis, 0.0) - penalty
            )

            breakdown.append({
                "rule": rule_name,
                "context": context,
                "signal": signal,
                "ingredient": ingredient,
                "axis": axis,
                "penalty": penalty,
                **(
                    {"rank": essential_oil_rank}
                    if rule_name == "reactive_skin_x_essential_oils"
                    else {}
                ),
            })

    return {
        "dimensions_delta": dimensions_delta,
        "breakdown": breakdown,
    }


def apply_shadow_dimensions(
    dimensions: Dict[str, Any],
    shadow: Dict[str, Any],
) -> Dict[str, float]:
    result = {
        str(axis): _safe_float(value)
        for axis, value in (dimensions or {}).items()
    }

    for axis, delta in (shadow.get("dimensions_delta") or {}).items():
        result[axis] = result.get(axis, 0.0) + _safe_float(delta)

    return result


def calculate_score_from_dimensions(
    dimensions: Dict[str, Any],
    weights: Dict[str, Any],
    saturation_scale: float,
) -> int:
    import math

    scale = max(_safe_float(saturation_scale, 1.5), 1e-9)

    weighted_total = 0.0
    weight_total = 0.0

    for axis, weight_raw in (weights or {}).items():
        weight = _safe_float(weight_raw)

        if weight <= 0:
            continue

        contribution = math.tanh(
            _safe_float(dimensions.get(axis), 0.0) / scale
        )

        weighted_total += contribution * weight
        weight_total += weight

    avg = weighted_total / max(weight_total, 1e-9)

    return int(round(max(0.0, min(100.0, 50.0 + 50.0 * avg))))
