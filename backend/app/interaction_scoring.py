# interaction_scoring.py
# Фаза 7 — Interaction Contribution model (versioned, deterministic).
#
# Принцип: Knowledge Graph хранит знание, Dynamic/Static Model передаёт
# ПОДТВЕРЖДЁННЫЕ interactions (state=known), Scoring Engine детерминированно
# переводит их в числовой contribution. LLM никогда не задаёт score/penalty.
#
# Модель (v1):
#   contribution = direction_sign × strength_weight(strength) × confidence_policy(confidence)
#
#   - direction_sign: ±1 (зависит от «вредности» оси и направления).
#   - strength_weight: величина взаимодействия (магнитуда), НЕ надёжность.
#   - confidence_policy: надёжность знания (уже отфильтрована порогом state=known).
#
#   known        → участвует в score (confidence ≥ threshold).
#   insufficient → НЕ участвует (сохраняется для diagnostics).
#   unknown      → не влияет (отсутствие знания ≠ нейтральность).

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .axes import AXES, AXIS_HARM

# Единая версия правил interaction contribution. Входит в идентичность score.
INTERACTION_SCORING_VERSION = "v1"

# Feature flag: False = legacy score бит-в-бит (регрессия). True = + interaction contribution.
INTERACTION_SCORING_ENABLED = False

# Строковый strength → вес (детерминированно). Числовой strength проходит clamp(0,1).
_STRENGTH_MAP: Dict[str, float] = {
    "strong": 1.0, "high": 1.0,
    "moderate": 0.6, "medium": 0.6,
    "weak": 0.3, "low": 0.3,
}

_POSITIVE_DIRECTIONS = frozenset({"positive", "+", "increase", "increases"})
_NEGATIVE_DIRECTIONS = frozenset({"negative", "-", "decrease", "decreases"})


def strength_weight(strength: Any) -> float:
    """Магнитуда взаимодействия → вес [0,1]. strength ≠ confidence."""
    if isinstance(strength, bool):
        strength = int(strength)
    if isinstance(strength, (int, float)):
        return max(0.0, min(1.0, float(strength)))
    key = str(strength or "").strip().lower()
    return _STRENGTH_MAP.get(key, 0.5)


def confidence_policy(confidence: Any) -> float:
    """Надёжность знания → вес [0,1]. Линейная (по умолчанию v1)."""
    try:
        return max(0.0, min(1.0, float(confidence or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def interaction_sign(axis: str, direction: str) -> float:
    """±1: benefit-oriented знак для canonical axis (endpoint-oriented direction).

    benefit-ось (hydration/barrier): positive = хорошо → +1.
    harm-ось (irritation/sensitization/sebum/pigmentation): positive = плохо → -1.
    """
    harm = axis in AXIS_HARM
    d = str(direction or "").strip().lower()
    if d in _POSITIVE_DIRECTIONS:
        positive = True
    elif d in _NEGATIVE_DIRECTIONS:
        positive = False
    else:
        # Неизвестное направление → нейтральный знак 0 (не участвует).
        return 0.0
    return -1.0 if (positive == harm) else 1.0


def interaction_contribution(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Переводит один interaction-запись в contribution-разбивку (canonical).

    Возвращает None, если interaction НЕ участвует в score
    (state != known, неизвестная ось, неизвестное направление).
    Ось идёт НАПРЯМУЮ в canonical scoring dimension (без legacy-маппинга).
    """
    if (record or {}).get("state") != "known":
        return None
    axis = str(record.get("axis") or "")
    if axis not in AXES:
        return None
    sign = interaction_sign(axis, record.get("direction"))
    if sign == 0.0:
        return None
    magnitude = strength_weight(record.get("strength")) * confidence_policy(record.get("confidence"))
    contribution = sign * magnitude
    return {
        "interaction_id": record.get("interaction_id"),
        "type": record.get("type", "interaction"),
        "ingredient_a": record.get("ingredient_a"),
        "ingredient_b": record.get("ingredient_b"),
        "axis": axis,
        "direction": record.get("direction"),
        "strength": record.get("strength"),
        "confidence": record.get("confidence"),
        "state": record.get("state"),
        "contribution": round(contribution, 6),
    }


def aggregate_interactions(records: List[Dict[str, Any]]) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
    """Детерминированная агрегация contributions по canonical осям.

    Политика (v1): СУММА contributions в рамках одной canonical оси. Совместима с
    суммированием individual effects + saturation clamp(0,1) в scoring.
    Порядок записей не влияет (сложение коммутативно).

    Возвращает (agg_by_axis, breakdown).
    """
    agg: Dict[str, float] = {}
    breakdown: List[Dict[str, Any]] = []
    for rec in records or []:
        contrib = interaction_contribution(rec)
        if contrib is None:
            continue
        axis = contrib["axis"]
        agg[axis] = agg.get(axis, 0.0) + contrib["contribution"]
        breakdown.append(contrib)
    return agg, breakdown
