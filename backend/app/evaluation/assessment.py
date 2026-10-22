"""Deterministic mapping: validated evidence -> parameter evaluation.

The model never chooses the number. It only supplies claims with quotes and a
direction; the mapping below turns the *weight of confirmed evidence* into a
value using fixed bands. The bands are a documented design decision, versioned
and explicitly **not calibrated** yet.

Guarantees:
  * no confirmed evidence  -> ``insufficient_evidence``, value is None;
  * neutral-only evidence  -> ``insufficient_evidence`` (absence of effect is not
    a measured value, and never treated as harm);
  * a value always carries the ids of the evidence it was derived from;
  * rationale text is assembled only from confirmed claims and quotes.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from .contracts import (
    STATUS_EVALUATED,
    STATUS_INSUFFICIENT,
    ParameterEvaluation,
)
from .evidence import Evidence

EVIDENCE_RULE_VERSION = "evidence-bands-1.0.0"

STRENGTH_WEIGHT = {"weak": 0.3, "moderate": 0.6, "strong": 1.0}

# (minimum net score, value). Net score lies in [-1, 1].
_BANDS = (
    (0.60, 80),
    (0.30, 70),
    (0.001, 60),
)
_HARM_BANDS = (
    (-0.60, 20),
    (-0.30, 30),
    (-0.001, 40),
)
BALANCE_EPSILON = 0.05
# "Not enough evidence" prior: without it a single weak claim would look as
# decisive as a strong one, because the ratio alone ignores evidence amount.
EVIDENCE_BASELINE = 0.6


def evidence_weight(evidence: Evidence) -> float:
    return STRENGTH_WEIGHT[evidence.strength] * float(evidence.confidence)


def net_score(evidence: Sequence[Evidence]) -> float:
    support = sum(evidence_weight(item) for item in evidence if item.direction == "supports")
    harm = sum(evidence_weight(item) for item in evidence if item.direction == "contradicts")
    denominator = support + harm + EVIDENCE_BASELINE
    if denominator <= 0:
        return 0.0
    return (support - harm) / denominator


def value_for_net(net: float) -> int:
    if net >= 0:
        for threshold, value in _BANDS:
            if net >= threshold:
                return value
        return 50
    for threshold, value in _HARM_BANDS:
        if net <= threshold:
            return value
    return 50


def _short(text: str, limit: int = 140) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def explain(evidence: Iterable[Evidence]) -> str:
    """Rationale built strictly from confirmed claims and quotes."""
    lines: list[str] = []
    labels = {"supports": "Подтверждено", "contradicts": "Противоречит", "neutral": "Без эффекта"}
    for item in evidence:
        if not item.usable:
            continue
        lines.append(
            f'{labels[item.direction]}: {_short(item.claim)} — «{_short(item.quote)}» '
            f"({item.source.host})."
        )
    return " ".join(lines)


def assess(
    parameter_id: str,
    evidence: Sequence[Evidence],
    *,
    composition_hash: str,
    method_version: str,
    evaluated_at: str,
    evidence_ids: Sequence[int] = (),
    rule_version: str = EVIDENCE_RULE_VERSION,
) -> ParameterEvaluation:
    """Turn validated evidence into a stored evaluation (no invented numbers)."""
    usable = [item for item in evidence if item.usable and item.parameter_id == parameter_id]
    rejected = [item for item in evidence if not item.usable]
    limitations: list[str] = []

    if rejected:
        reasons = sorted({item.rejection_reason for item in rejected if item.rejection_reason})
        limitations.append(
            f"Отклонено кандидатов: {len(rejected)}"
            + (f" ({'; '.join(reasons[:3])})" if reasons else "")
        )

    if not usable:
        limitations.append("Подтверждённых доказательств нет — значение не вычисляется.")
        return ParameterEvaluation(
            parameter_id=parameter_id,
            status=STATUS_INSUFFICIENT,
            value=None,
            confidence=None,
            composition_hash=composition_hash,
            method_version=method_version,
            evidence_ids=tuple(str(item) for item in evidence_ids),
            rationale="",
            limitations=tuple(limitations),
            evaluated_at=evaluated_at,
        )

    if all(item.direction == "neutral" for item in usable):
        limitations.append(
            "Есть только свидетельства отсутствия эффекта; это не измеренное значение "
            "и не доказательство вреда."
        )
        return ParameterEvaluation(
            parameter_id=parameter_id,
            status=STATUS_INSUFFICIENT,
            value=None,
            confidence=None,
            composition_hash=composition_hash,
            method_version=method_version,
            evidence_ids=tuple(str(item) for item in evidence_ids),
            rationale=explain(usable),
            limitations=tuple(limitations),
            evaluated_at=evaluated_at,
        )

    net = net_score(usable)
    value = value_for_net(net)
    if abs(net) <= BALANCE_EPSILON and any(item.direction == "supports" for item in usable) \
            and any(item.direction == "contradicts" for item in usable):
        limitations.append(
            "Доказательства в пользу и против сопоставимы: значение отражает баланс, "
            "а не отсутствие данных."
        )
    limitations.append(
        f"Значение получено из доказательств по фиксированным полосам ({rule_version}); "
        "полосы не откалиброваны по независимым эталонам."
    )

    weights = [evidence_weight(item) for item in usable]
    confidence = round(sum(w * item.confidence for w, item in zip(weights, usable)) / sum(weights), 3)

    return ParameterEvaluation(
        parameter_id=parameter_id,
        status=STATUS_EVALUATED,
        value=float(value),
        confidence=confidence,
        composition_hash=composition_hash,
        method_version=method_version,
        evidence_ids=tuple(str(item) for item in evidence_ids),
        rationale=explain(usable),
        limitations=tuple(limitations),
        evaluated_at=evaluated_at,
    )
