# axes.py
# Фаза 1 — канонические 6 осей индивидуальных эффектов ингредиента.
#
# Устраняет рассинхрон трёх наборов (catalog columns / claims property_name /
# decision_engine.DIMENSIONS). Единый словарь осей и неразрушающий маппинг
# legacy-имён на канонические оси.
#
# НЕ меняет scoring: это только словарь + функции перевода. Scoring продолжает
# читать старые property_name; каноническая карта понадобится на Фазе 2.

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .scoring_config import (
    AXES,
    AXIS_ALIASES,
    AXIS_HARM,
    CANONICAL_TO_LEGACY_DIMENSION,
    LEGACY_TO_CANONICAL_DIMENSION,
    LEGACY_MAPPING_KIND,
)

__all__ = [
    "AXES",
    "AXIS_ALIASES",
    "AXIS_HARM",
    "CANONICAL_TO_LEGACY_DIMENSION",
    "LEGACY_TO_CANONICAL_DIMENSION",
    "LEGACY_MAPPING_KIND",
    "canonicalize_axis",
    "canonicalize_effect",
    "canonicalize_knowledge_map",
    "canonicalize_weights",
    "legacyize_dimensions",
]


# legacy-направления для инверсии.
def _flip_direction(direction: str) -> str:
    d = (direction or "").strip().lower()
    if d in ("positive", "+", "increase", "increases"):
        return "negative"
    if d in ("negative", "-", "decrease", "decreases"):
        return "positive"
    return d


def canonicalize_axis(property_name: str) -> Tuple[Optional[str], bool]:
    """(canonical_axis, direction_flip) для legacy property_name.

    Возвращает (None, False), если имя не соответствует ни одной оси.
    """
    key = (property_name or "").strip().lower().replace(" ", "_")
    return AXIS_ALIASES.get(key, (None, False))


def canonicalize_effect(property_name: str, direction: str) -> Tuple[Optional[str], str]:
    """Переводит legacy effect (property_name, direction) в (axis, canonical_direction)."""
    axis, flip_dir = canonicalize_axis(property_name)
    if axis is None:
        return None, direction
    return axis, (_flip_direction(direction) if flip_dir else (direction or "").strip().lower())


def canonicalize_knowledge_map(knowledge: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Переводит knowledge map {ingredient: {property: {direction, strength, confidence}}}
    в канонические оси {ingredient: {axis: {...}}}.

    Неизвестные оси отбрасываются; в поле '_legacy_property' сохраняется исходное имя
    для трассировки (non-destructive).
    """
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for ingredient, props in (knowledge or {}).items():
        canon: Dict[str, Dict[str, Any]] = {}
        for prop, val in (props or {}).items():
            if not isinstance(val, dict):
                continue
            axis, direction = canonicalize_effect(prop, val.get("direction"))
            if axis is None:
                continue
            canon[axis] = {
                "direction": direction,
                "strength": val.get("strength"),
                "confidence": val.get("confidence"),
                "_legacy_property": prop,
            }
        if canon:
            out[ingredient] = canon
    return out


def canonicalize_weights(legacy_weights: Dict[str, Any]) -> Dict[str, float]:
    """Legacy benefit-oriented weights → canonical benefit-oriented weights.

    Только переименование ключей (sensitivity→irritation, acne_control→sebum,
    brightening→pigmentation); значения не меняются. Оси без legacy-веса = 0.0.
    """
    out = {axis: 0.0 for axis in AXES}
    for legacy, weight in (legacy_weights or {}).items():
        axis = LEGACY_TO_CANONICAL_DIMENSION.get(legacy)
        if axis:
            out[axis] = float(weight)
    return out


def legacyize_dimensions(canonical_dimensions: Dict[str, Any]) -> Dict[str, float]:
    """Canonical dimensions → legacy dimensions (compatibility, для API/tests)."""
    out: Dict[str, float] = {}
    for axis, value in (canonical_dimensions or {}).items():
        legacy = CANONICAL_TO_LEGACY_DIMENSION.get(axis)
        if legacy:
            out[legacy] = value
    return out
