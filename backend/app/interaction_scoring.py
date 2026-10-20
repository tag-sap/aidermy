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

import os
from typing import Any, Dict, List, Optional, Tuple

from .axes import AXES, AXIS_HARM
from .ingredient_normalizer import normalize_ingredient_name

# Правила interaction contribution вынесены в scoring_config.py (versioned источник истины).
from .scoring_config import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    INTERACTION_CONFIDENCE_DEFAULT,
    INTERACTION_SCORING_ENABLED_DEFAULT,
    INTERACTION_SCORING_VERSION,
    INTERACTION_STRENGTH_MAP,
    INTERACTION_STRENGTH_UNKNOWN_DEFAULT,
    NEGATIVE_DIRECTIONS,
    POSITIVE_DIRECTIONS,
)

# Feature flag: False = legacy score бит-в-бит (регрессия). True = + interaction contribution.
# Хранится как МУТАБЕЛЬНЫЙ runtime-флаг (тесты переключают его напрямую), а не в конфиге.
INTERACTION_SCORING_ENABLED = bool(INTERACTION_SCORING_ENABLED_DEFAULT)

# Строковый strength → вес (детерминированно). Числовой strength проходит clamp(0,1).
_STRENGTH_MAP: Dict[str, float] = dict(INTERACTION_STRENGTH_MAP)

_POSITIVE_DIRECTIONS = frozenset(POSITIVE_DIRECTIONS)
_NEGATIVE_DIRECTIONS = frozenset(NEGATIVE_DIRECTIONS)


def strength_weight(strength: Any) -> float:
    """Магнитуда взаимодействия → вес [0,1]. strength ≠ confidence."""
    if isinstance(strength, bool):
        strength = int(strength)
    if isinstance(strength, (int, float)):
        return max(0.0, min(1.0, float(strength)))
    key = str(strength or "").strip().lower()
    return _STRENGTH_MAP.get(key, INTERACTION_STRENGTH_UNKNOWN_DEFAULT)


def confidence_policy(confidence: Any) -> float:
    """Надёжность знания → вес [0,1]. Линейная (по умолчанию v1)."""
    try:
        return max(0.0, min(1.0, float(confidence or INTERACTION_CONFIDENCE_DEFAULT)))
    except (TypeError, ValueError):
        return INTERACTION_CONFIDENCE_DEFAULT


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


# ===========================================================================
# Interaction replacement (v1.0.0) — замещение индивидуальных эффектов пары.
#
# effect_kind="absolute": strength — ПОЛНЫЙ совместный эффект пары на оси.
# effect_kind="delta": изменение относительно индивидуальных эффектов; к
# замещению не допускается (нельзя восстановить полный эффект).
#
# Допуск: state=known (confidence >= DEFAULT_CONFIDENCE_THRESHOLD), непустые
# evidence/source, source_type не из эвристик/AI.
# ===========================================================================
INTERACTION_REPLACEMENT_VERSION = "1.0.0"

INTERACTION_REPLACEMENT_ENABLED = os.getenv(
    "INTERACTION_REPLACEMENT_ENABLED", "1"
).strip().lower() not in {"0", "false", "no", "off"}

ADMISSIBLE_SOURCE_TYPES = frozenset({
    "pubmed", "clinical", "clinical_trial", "regulatory", "in_vitro",
    "literature", "expert_review", "label",
})


def replacement_admissibility(record: Dict[str, Any], min_confidence: float) -> Optional[str]:
    """None, если запись допускается к замещению; иначе — причина отказа."""
    if str((record or {}).get("effect_kind") or "delta").strip().lower() != "absolute":
        return "delta_semantics"
    if str((record or {}).get("state") or "") != "known":
        return "insufficient_confidence"
    try:
        confidence = float((record or {}).get("confidence") or 0.0)
    except (TypeError, ValueError):
        return "invalid_confidence"
    if confidence < min_confidence:
        return "insufficient_confidence"
    if str((record or {}).get("source_type") or "").strip().lower() not in ADMISSIBLE_SOURCE_TYPES:
        return "unverified_source"
    if not str((record or {}).get("evidence") or "").strip():
        return "missing_evidence"
    if not str((record or {}).get("source") or "").strip():
        return "missing_source"
    axis = str((record or {}).get("axis") or "")
    if axis not in AXES:
        return "invalid_axis"
    if interaction_sign(axis, (record or {}).get("direction")) == 0.0:
        return "unknown_direction"
    return None


def apply_interaction_replacements(
    individual_by_axis: Dict[str, List[Dict[str, Any]]],
    interactions: Optional[List[Dict[str, Any]]],
    min_confidence: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Dict[str, Any]:
    """Детерминированное замещение индивидуальных эффектов парами.

    individual_by_axis: {axis: [{"ingredient", "sign", "value", ...}]}.
    Возвращает positive/negative magnitudes по осям, applied и rejected.
    """
    threshold = float(min_confidence)
    rejected: List[Dict[str, Any]] = []
    groups: Dict[Tuple[Tuple[str, str], str], List[Dict[str, Any]]] = {}

    for record in interactions or []:
        a = normalize_ingredient_name(str((record or {}).get("ingredient_a") or ""))
        b = normalize_ingredient_name(str((record or {}).get("ingredient_b") or ""))
        pair = tuple(sorted([a, b]))
        axis = str((record or {}).get("axis") or "")
        base = {"interaction_id": (record or {}).get("interaction_id"), "pair": list(pair), "axis": axis}
        if not a or not b or a == b:
            rejected.append({**base, "reason": "invalid_pair"})
            continue
        reason = replacement_admissibility(record, threshold)
        if reason:
            rejected.append({
                **base,
                "reason": reason,
                "confidence": (record or {}).get("confidence"),
                "source_type": (record or {}).get("source_type"),
                "effect_kind": (record or {}).get("effect_kind"),
            })
            continue
        groups.setdefault((pair, axis), []).append(record)

    # Одна пара + ось: согласованные дубли схлопываем, противоречивые — отклоняем.
    candidates: Dict[Tuple[Tuple[str, str], str], Dict[str, Any]] = {}
    for (pair, axis), records in groups.items():
        signatures = {
            (str(r.get("direction")).strip().lower(), round(float(r.get("strength") or 0.0), 6))
            for r in records
        }
        if len(signatures) > 1:
            rejected.append({
                "interaction_id": None,
                "pair": list(pair),
                "axis": axis,
                "reason": "conflicting_records",
            })
            continue
        best = max(
            records,
            key=lambda r: (float(r.get("confidence") or 0.0), int(r.get("interaction_id") or 0)),
        )
        candidates[(pair, axis)] = best

    # Общий ингредиент на одной оси: два замещения одного эффекта невозможны.
    by_axis: Dict[str, List[Tuple[Tuple[str, str], Dict[str, Any]]]] = {}
    for (pair, axis), record in candidates.items():
        by_axis.setdefault(axis, []).append((pair, record))

    accepted: Dict[Tuple[Tuple[str, str], str], Dict[str, Any]] = {}
    for axis, items in sorted(by_axis.items()):
        degree: Dict[str, int] = {}
        for pair, _ in items:
            degree[pair[0]] = degree.get(pair[0], 0) + 1
            degree[pair[1]] = degree.get(pair[1], 0) + 1
        for pair, record in sorted(items, key=lambda item: item[0]):
            if degree.get(pair[0], 0) > 1 or degree.get(pair[1], 0) > 1:
                rejected.append({
                    "interaction_id": record.get("interaction_id"),
                    "pair": list(pair),
                    "axis": axis,
                    "reason": "shared_ingredient",
                })
            else:
                accepted[(pair, axis)] = record

    positive: Dict[str, List[float]] = {axis: [] for axis in AXES}
    negative: Dict[str, List[float]] = {axis: [] for axis in AXES}
    applied: List[Dict[str, Any]] = []

    for axis in AXES:
        entries = list(individual_by_axis.get(axis) or [])
        axis_accepted = [
            (pair, record) for (pair, ax), record in sorted(accepted.items()) if ax == axis
        ]
        replaced = {ingredient for pair, _ in axis_accepted for ingredient in pair}

        for entry in entries:
            if entry.get("ingredient") in replaced:
                continue
            target = positive if float(entry.get("sign") or 0.0) > 0 else negative
            target[axis].append(float(entry.get("value") or 0.0))

        for pair, record in axis_accepted:
            sign = interaction_sign(axis, record.get("direction"))
            magnitude = strength_weight(record.get("strength"))
            contribution = abs(sign * magnitude * confidence_policy(record.get("confidence")))
            target = positive if sign > 0 else negative
            target[axis].append(contribution)
            applied.append({
                "interaction_id": record.get("interaction_id"),
                "pair": list(pair),
                "axis": axis,
                "direction": record.get("direction"),
                "individual_before": [
                    {
                        "ingredient": entry.get("ingredient"),
                        "value": round(float(entry.get("value") or 0.0), 6),
                        "sign": entry.get("sign"),
                    }
                    for entry in entries
                    if entry.get("ingredient") in pair
                ],
                "combined_effect": round(magnitude, 6),
                "effective_contribution": round(contribution, 6),
                "confidence": confidence_policy(record.get("confidence")),
                "source": record.get("source"),
                "source_type": record.get("source_type"),
                "evidence": record.get("evidence"),
                "interaction_type": record.get("interaction_type"),
            })

    return {
        "version": INTERACTION_REPLACEMENT_VERSION,
        "positive": positive,
        "negative": negative,
        "applied": applied,
        "rejected": rejected,
    }
