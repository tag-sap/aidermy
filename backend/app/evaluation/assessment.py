"""Deterministic mapping: validated evidence → parameter evaluation + explanation.

The model never chooses the number. It supplies claims with verbatim quotes and a
direction; this module turns the weight of *confirmed* evidence into a value using
fixed bands and writes the user-facing explanation for ONE questionnaire parameter.

Guarantees:
  * no confirmed evidence          → ``insufficient_evidence``, value None;
  * neutral-only evidence          → ``insufficient_evidence`` (absence of effect
    is not a measured value and never treated as harm);
  * balanced support/contradiction → ``contradictory_evidence``, value None
    (a midpoint would hide the contradiction; 50 is never a default);
  * a value always carries the ids of the evidence it was derived from;
  * the explanation answers the parameter's own question, quotes confirmed claims
    only, and never asserts treatment, safety or harm beyond the quotes.
"""
from __future__ import annotations

from typing import Sequence

from .contracts import (
    STATUS_CONTRADICTORY,
    STATUS_EVALUATED,
    STATUS_INSUFFICIENT,
    ContractError,
    Parameter,
    ParameterEvaluation,
)
from .evidence import Evidence
from .parameters import PARAMETERS

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

# Neutral, non-medical wording: the value describes the balance of quotes for the
# parameter's requirement, not a clinical outcome.
BAND_TEXT = {
    80: "подтверждённые данные соответствуют требованию пункта",
    70: "подтверждённые данные скорее соответствуют требованию пункта",
    60: "есть только слабые подтверждения соответствия требованию",
    40: "есть слабые подтверждения несоответствия требованию",
    30: "подтверждённые данные скорее не соответствуют требованию пункта",
    20: "подтверждённые данные не соответствуют требованию пункта",
}

DIRECTION_LABEL = {"supports": "За требование", "contradicts": "Против требования",
                   "neutral": "Без эффекта"}



def as_parameter(parameter: Parameter | str) -> Parameter:
    """Accept a catalog parameter or its id (strict: unknown ids fail fast)."""
    if isinstance(parameter, Parameter):
        return parameter
    item = PARAMETERS.get(str(parameter))
    if item is None:
        raise ContractError(f"unknown parameter: {parameter!r}")
    return item


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


def explain(
    parameter: Parameter | str,
    evidence: Sequence[Evidence],
    *,
    value: int | None = None,
    conclusion: str = "",
) -> str:
    """Explanation bound to one questionnaire parameter.

    Only confirmed claims/quotes are quoted back; the conclusion sentence is
    produced by fixed rules, never by a model.
    """
    item = as_parameter(parameter)
    parts: list[str] = [f"{item.label}. {item.question}"]
    if conclusion:
        parts.append(conclusion)
    if value is not None:
        parts.append(f"Оценка {value}/100.")
    for entry in evidence:
        if not entry.usable:
            continue
        parts.append(
            f'{DIRECTION_LABEL[entry.direction]}: {_short(entry.claim)} — '
            f"«{_short(entry.quote)}» ({entry.source.host})."
        )
    if any(entry.usable for entry in evidence):
        parts.append(
            "Учтены только цитаты, найденные в тексте источника; утверждения без "
            "цитат не использованы."
        )
    return " ".join(parts)


def _evaluation(
    parameter: Parameter,
    *,
    status: str,
    value: float | None,
    confidence: float | None,
    composition_hash: str,
    method_version: str,
    evaluated_at: str,
    evidence_ids: Sequence[int],
    rationale: str,
    limitations: Sequence[str],
) -> ParameterEvaluation:
    return ParameterEvaluation(
        parameter_id=parameter.id,
        status=status,
        value=value,
        confidence=confidence,
        composition_hash=composition_hash,
        method_version=method_version,
        evidence_ids=tuple(str(item) for item in evidence_ids),
        rationale=rationale,
        limitations=tuple(limitations),
        evaluated_at=evaluated_at,
    )


def assess(
    parameter: Parameter | str,
    evidence: Sequence[Evidence],
    *,
    composition_hash: str,
    method_version: str,
    evaluated_at: str,
    evidence_ids: Sequence[int] = (),
    rule_version: str = EVIDENCE_RULE_VERSION,
) -> ParameterEvaluation:
    """Turn validated evidence into a stored evaluation (no invented numbers)."""
    item = as_parameter(parameter)
    usable = [entry for entry in evidence if entry.usable and entry.parameter_id == item.id]
    rejected = [entry for entry in evidence if not entry.usable]
    limitations: list[str] = []

    if rejected:
        reasons = sorted({entry.rejection_reason for entry in rejected if entry.rejection_reason})
        limitations.append(
            f"Отклонено кандидатов: {len(rejected)}"
            + (f" ({'; '.join(reasons[:3])})" if reasons else "")
        )

    common = dict(
        composition_hash=composition_hash,
        method_version=method_version,
        evaluated_at=evaluated_at,
        evidence_ids=evidence_ids,
        limitations=limitations,
    )

    if not usable:
        limitations.append("Подтверждённых доказательств нет — значение не вычисляется.")
        limitations.append(
            "Отсутствие подтверждений пользы не является доказательством вреда."
        )
        return _evaluation(
            item,
            status=STATUS_INSUFFICIENT,
            value=None,
            confidence=None,
            rationale=explain(
                item,
                (),
                conclusion=(
                    "Подтверждённых данных по этому пункту нет, поэтому числовая "
                    "оценка не рассчитывается."
                ),
            ),
            **common,
        )

    if all(entry.direction == "neutral" for entry in usable):
        limitations.append(
            "Есть только свидетельства отсутствия эффекта; это не измеренное значение "
            "и не доказательство вреда."
        )
        return _evaluation(
            item,
            status=STATUS_INSUFFICIENT,
            value=None,
            confidence=None,
            rationale=explain(
                item,
                usable,
                conclusion=(
                    "Подтверждено только отсутствие эффекта — этого недостаточно для "
                    "числовой оценки."
                ),
            ),
            **common,
        )

    net = net_score(usable)
    has_support = any(entry.direction == "supports" for entry in usable)
    has_harm = any(entry.direction == "contradicts" for entry in usable)

    if has_support and has_harm and abs(net) <= BALANCE_EPSILON:
        limitations.append(
            "Доказательства «за» и «против» сопоставимы: числовая оценка не выводится, "
            "пока противоречие не разрешено."
        )
        limitations.append(
            f"Правила сопоставления доказательств: {rule_version} "
            "(не откалиброваны по независимым эталонам)."
        )
        return _evaluation(
            item,
            status=STATUS_CONTRADICTORY,
            value=None,
            confidence=None,
            rationale=explain(
                item,
                usable,
                conclusion=(
                    "Источники противоречат друг другу по этому пункту; оценка не "
                    "рассчитывается, противоречие указано в ограничениях."
                ),
            ),
            **common,
        )

    value = value_for_net(net)
    limitations.append(
        f"Значение получено из доказательств по фиксированным полосам ({rule_version}); "
        "полосы не откалиброваны по независимым эталонам."
    )
    limitations.append(
        "Значение отражает баланс подтверждающих и противоречащих цитат по этому "
        "пункту, а не клиническую пригодность продукта."
    )
    if has_support and has_harm:
        limitations.append(
            "В источниках есть и подтверждения, и возражения по пункту: итог отражает "
            "их соотношение."
        )

    confidence = round(sum(float(entry.confidence) for entry in usable) / len(usable), 3)
    return _evaluation(
        item,
        status=STATUS_EVALUATED,
        value=float(value),
        confidence=confidence,
        rationale=explain(
            item,
            usable,
            value=value,
            conclusion=BAND_TEXT.get(value, "данных недостаточно для вывода") + ".",
        ),
        **common,
    )
