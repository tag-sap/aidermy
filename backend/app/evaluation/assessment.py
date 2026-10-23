"""Deterministic validation of the research model's assessment.

The model makes the cosmetological judgement and chooses one of the five allowed
scores. This module does NOT derive a score from quotes: it validates the
proposal and stores exactly one of three outcomes.

  * ``not_applicable``      — the parameter does not apply to this product
    (only when the proposal gives a reason and cites at least one confirmed,
    fetched source for *this* parameter: applicability is checked against the
    evidence, not against the name of the section);
  * ``insufficient_evidence``— applicable, but the evidence does not support a
    score (never mapped to 0/50, never treated as harm);
  * ``assessed``            — an allowed score plus an explanation plus references
    to confirmed, stored evidence.

Intolerance parameters additionally pass a deterministic INCI check
(``evaluation/inci.py``): an unverifiable composition never yields a score or an
exclusion, and a present ingredient contradicts "not applicable" / 100.

Structural violations (a score outside 0/25/50/75/100, a score without a
sufficient-evidence decision, missing explanation, references to rejected or
missing evidence, treatment claims) raise ``ContractError``. The research
service turns that into a failed job — a technical/protocol error is never
disguised as ``not_applicable`` or ``insufficient_evidence``.

Limitation: this layer verifies structure and grounding, not the correctness of
the model's cosmetological reasoning.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from .contracts import (
    SCORE_LEVELS,
    STATUS_ASSESSED,
    STATUS_INSUFFICIENT,
    STATUS_NOT_APPLICABLE,
    ContractError,
    Parameter,
    ParameterEvaluation,
)
from .evidence import Evidence
from .inci import NOT_LISTED, PRESENT, UNVERIFIABLE, InciCheck, check_intolerance
from .parameters import PARAMETERS
from .research import APPLICABLE, APPLICABILITY, NOT_APPLICABLE, AssessmentProposal

ASSESS_RULE_VERSION = "assessment-3.1.0"
MIN_RATIONALE_CHARS = 30

# Model text must not assert clinical outcomes. Source quotes are exempt: they
# are verbatim source text, not our conclusion.
FORBIDDEN_CLAIMS = (
    "лечит",
    "вылеч",
    "излеч",
    "гарантиру",
    "безопасен",
    "безвреден",
)
INSUFFICIENT_MARKERS = ("недостаточно данных", "нет данных", "данных нет")


def as_parameter(parameter: Parameter | str) -> Parameter:
    """Accept a catalog parameter or its id (strict: unknown ids fail fast)."""
    if isinstance(parameter, Parameter):
        return parameter
    item = PARAMETERS.get(str(parameter))
    if item is None:
        raise ContractError(f"unknown parameter: {parameter!r}")
    return item


def _short(text: str, limit: int = 180) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _check_model_text(parameter: Parameter, text: str, *, field: str) -> None:
    lowered = str(text or "").casefold()
    for marker in FORBIDDEN_CLAIMS:
        if marker in lowered:
            raise ContractError(
                f"{parameter.id}: {field} contains an unverified clinical claim "
                f"({marker!r}); the model must describe correspondence, not treatment"
            )


DIRECTION_LABEL = {
    "supports": "За требование",
    "contradicts": "Против требования",
    "neutral": "Без отношения к требованию",
}


def explain(
    parameter: Parameter | str,
    answer: str,
    evidence: Sequence[Evidence] = (),
    *,
    value: int | float | None = None,
) -> str:
    """Assemble the user-facing explanation from the model's answer and quotes.

    The model's ``answer`` is the human-readable reasoning produced in the same
    research cycle; quotes are appended verbatim so the user can check it.
    """
    item = as_parameter(parameter)
    parts: list[str] = [f"{item.label}. {item.question}"]
    if answer:
        parts.append(answer.strip())
    if value is not None:
        parts.append(f"Оценка {int(value)}/100.")
    for entry in evidence:
        if not entry.usable:
            continue
        parts.append(
            f'{DIRECTION_LABEL[entry.direction]}: {_short(entry.claim)} — '
            f"«{_short(entry.quote)}» ({entry.source.host})."
        )
    if any(entry.usable for entry in evidence):
        parts.append(
            "Цитаты приведены дословно из указанных источников; выводы сверх них "
            "не делаются."
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
    evidence_ids: Sequence[str],
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
        limitations=tuple(dict.fromkeys(limitations)),
        evaluated_at=evaluated_at,
    )


def _resolve_refs(
    parameter: Parameter,
    proposal: AssessmentProposal,
    evidence: Sequence[Evidence],
    evidence_ids: Sequence[str],
) -> tuple[list[Evidence], list[str]]:
    if len(evidence_ids) != len(evidence):
        raise ContractError(
            f"{parameter.id}: evidence and evidence ids must be aligned"
        )
    refs: list[int] = []
    for raw in proposal.evidence_refs:
        try:
            ref = int(raw)
        except (TypeError, ValueError) as exc:
            raise ContractError(f"{parameter.id}: evidence ref is not an index: {raw!r}") from exc
        if not 0 <= ref < len(evidence):
            raise ContractError(
                f"{parameter.id}: evidence ref {ref} is out of range "
                f"(0..{len(evidence) - 1})"
            )
        if ref not in refs:
            refs.append(ref)
    used = [evidence[ref] for ref in refs]
    ids = [str(evidence_ids[ref]) for ref in refs]
    rejected = [entry for entry in used if not entry.usable]
    if rejected:
        raise ContractError(
            f"{parameter.id}: assessment references evidence rejected by validation "
            f"({rejected[0].rejection_reason or 'без причины'})"
        )
    return used, ids



def assess(
    parameter: Parameter | str,
    proposal: AssessmentProposal | None,
    evidence: Sequence[Evidence] = (),
    *,
    composition_hash: str,
    method_version: str,
    evaluated_at: str,
    evidence_ids: Sequence[str] = (),
    composition: Mapping | None = None,
    allowed_scores: Sequence[int] = SCORE_LEVELS,
    rule_version: str = ASSESS_RULE_VERSION,
    allow_synthetic_evidence: bool = False,
) -> ParameterEvaluation:
    """Validate the model's proposal and store exactly one outcome.

    ``proposal is None`` means the provider found no sources: the parameter is
    applicable but has no evidence, so it is stored as ``insufficient_evidence``
    (never as ``not_applicable`` and never with a score).

    ``composition`` is the verified composition record used for a deterministic
    INCI check of intolerance parameters. ``allow_synthetic_evidence`` is an
    explicit test-only opt-in: without it, evidence whose provenance is not
    ``fetched`` cannot produce a score or an exclusion.
    """
    item = as_parameter(parameter)
    evidence = list(evidence)
    allowed = tuple(int(level) for level in allowed_scores)
    checked: InciCheck | None = check_intolerance(item, composition)

    base = dict(
        composition_hash=composition_hash,
        method_version=method_version,
        evaluated_at=evaluated_at,
    )

    if proposal is None:
        initial = [
            "Параметр применим, но доказательств недостаточно — оценка не выставляется.",
            "Отсутствие подтверждений пользы не является доказательством вреда.",
            f"Правила оценки: {rule_version} (не откалиброваны).",
        ]
        if checked is not None:
            initial.append(f"INCI: {checked.reason}.")
        return _evaluation(
            item,
            status=STATUS_INSUFFICIENT,
            value=None,
            confidence=None,
            evidence_ids=(),
            rationale=explain(
                item,
                "Провайдер не вернул ни источников, ни оценки: подтверждённых данных "
                "нет, поэтому балл не выставляется.",
            ),
            limitations=initial,
            **base,
        )

    if proposal.parameter_id != item.id:
        raise ContractError(
            f"proposal parameter_id {proposal.parameter_id!r} does not match {item.id!r}"
        )
    if proposal.applicability not in APPLICABILITY:
        raise ContractError(f"{item.id}: unknown applicability {proposal.applicability!r}")

    used: list[Evidence] = []
    used_ids: list[str] = []
    if proposal.evidence_refs:
        used, used_ids = _resolve_refs(item, proposal, evidence, evidence_ids)
    confirmed = [entry for entry in used if entry.usable]
    fetched = [entry for entry in confirmed if entry.fetched]
    provenance_ok = allow_synthetic_evidence or bool(fetched)

    limitations: list[str] = [
        f"Правила оценки: {rule_version}; допустимые баллы {list(allowed)} "
        "(не откалиброваны).",
        "Балл выбран моделью по критериям уровня; детерминированная часть проверила "
        "структуру, допустимость балла и ссылки на подтверждённые доказательства.",
    ]
    limitations.extend(str(text) for text in proposal.limitations if str(text).strip())
    limitations.extend(
        f"Противоречие: {text}" for text in proposal.contradictions if str(text).strip()
    )
    limitations.extend(
        f"Неизвестно: {text}" for text in proposal.important_unknowns if str(text).strip()
    )

    # Deterministic INCI gate for intolerance parameters. It can only constrain
    # the model: an unverifiable composition never yields a score or an exclusion,
    # and a present ingredient forbids "not applicable" / "100".
    if checked is not None:
        limitations.append(f"INCI: {checked.reason}.")
        if checked.status == NOT_LISTED:
            limitations.append(
                "Отсутствие компонента в заявленном INCI не гарантирует отсутствие "
                "риска: список состава может быть неполным."
            )
        if checked.status == UNVERIFIABLE:
            return _evaluation(
                item,
                status=STATUS_INSUFFICIENT,
                value=None,
                confidence=None,
                evidence_ids=used_ids,
                rationale=explain(
                    item,
                    f"Надёжно проверить состав не удалось: {checked.reason}.",
                    used,
                ),
                limitations=limitations
                + [
                    "Параметр применим, но состав нельзя проверить надёжно — "
                    "балл не выставляется."
                ],
                **base,
            )
        if proposal.applicability == NOT_APPLICABLE:
            limitations.append(
                "Неприменимость не принимается: наличие компонента проверяется по "
                "подтверждённому составу, поэтому параметр остаётся применимым."
            )
            return _evaluation(
                item,
                status=STATUS_INSUFFICIENT,
                value=None,
                confidence=None,
                evidence_ids=used_ids,
                rationale=explain(
                    item,
                    str(proposal.applicability_reason or "").strip()
                    or "Модель не привела обоснования неприменимости.",
                    used,
                ),
                limitations=limitations,
                **base,
            )

    # A. Applicability. "Not applicable" is a claim about the product, so it must
    # be grounded in a confirmed source. There is deliberately no category-level
    # ban: the decision is checked against the evidence for this parameter.
    if proposal.applicability == NOT_APPLICABLE:
        if proposal.score is not None:
            raise ContractError(f"{item.id}: not_applicable must not carry a score")
        reason = str(proposal.applicability_reason or "").strip()
        if not reason:
            limitations.append("Неприменимость без обоснования не принимается.")
            return _evaluation(
                item,
                status=STATUS_INSUFFICIENT,
                value=None,
                confidence=None,
                evidence_ids=used_ids,
                rationale=explain(
                    item, "Модель не привела обоснования неприменимости.", used
                ),
                limitations=limitations,
                **base,
            )
        if not confirmed:
            limitations.append(
                "Неприменимость нельзя обосновать отсутствием данных: подтверждённых "
                "источников нет, поэтому фиксируется недостаток доказательств."
            )
            return _evaluation(
                item,
                status=STATUS_INSUFFICIENT,
                value=None,
                confidence=None,
                evidence_ids=used_ids,
                rationale=explain(item, reason, used),
                limitations=limitations,
                **base,
            )
        if not provenance_ok:
            sources = ", ".join(sorted({entry.provenance for entry in confirmed}))
            limitations.append(
                f"Источник не подтверждён как загруженный (provenance={sources}): "
                "неприменимость на его основании не принимается."
            )
            return _evaluation(
                item,
                status=STATUS_INSUFFICIENT,
                value=None,
                confidence=None,
                evidence_ids=used_ids,
                rationale=explain(item, reason, used),
                limitations=limitations,
                **base,
            )
        return _evaluation(
            item,
            status=STATUS_NOT_APPLICABLE,
            value=None,
            confidence=None,
            evidence_ids=used_ids,
            rationale=explain(
                item, f"Параметр не применяется к этому продукту: {reason}", used
            ),
            limitations=limitations,
            **base,
        )


    # B. Sufficiency / score.
    if not proposal.sufficient:
        if proposal.score is not None:
            raise ContractError(
                f"{item.id}: a score is only allowed when the evidence is sufficient"
            )
        answer = str(proposal.rationale or "").strip() or (
            "Проверяемых данных недостаточно для обоснованной оценки."
        )
        limitations.append(
            "Параметр применим, но доказательств недостаточно — балл не выставляется."
        )
        limitations.append(
            "Отсутствие подтверждений соответствия не является доказательством вреда."
        )
        return _evaluation(
            item,
            status=STATUS_INSUFFICIENT,
            value=None,
            confidence=None,
            evidence_ids=used_ids,
            rationale=explain(item, answer, used),
            limitations=limitations,
            **base,
        )

    score = proposal.score
    if score is None:
        raise ContractError(
            f"{item.id}: a sufficient assessment must contain one of {list(allowed)}"
        )
    if int(score) not in allowed:
        raise ContractError(
            f"{item.id}: score {score!r} is not allowed; expected one of {list(allowed)}"
        )
    answer = str(proposal.rationale or "").strip()
    if len(answer) < MIN_RATIONALE_CHARS:
        raise ContractError(
            f"{item.id}: a score requires a meaningful explanation "
            f"(>= {MIN_RATIONALE_CHARS} characters)"
        )
    _check_model_text(item, answer, field="rationale")
    for entry in confirmed:
        _check_model_text(item, entry.claim, field="claim")
    if any(marker in answer.casefold() for marker in INSUFFICIENT_MARKERS):
        raise ContractError(
            f"{item.id}: the explanation says there is not enough data but a score "
            "was provided — the sufficiency decision is inconsistent"
        )
    if not confirmed or not used_ids:
        raise ContractError(
            f"{item.id}: an assessed parameter requires references to confirmed evidence"
        )

    # A verified composition contradicts "the component is absent".
    if checked is not None and checked.status == PRESENT and int(score) == 100:
        raise ContractError(
            f"{item.id}: score 100 contradicts the verified composition "
            f"(found: {', '.join(checked.matched)})"
        )

    # Only a source the provider declared as fetched may back a production score.
    if not provenance_ok:
        sources = ", ".join(sorted({entry.provenance for entry in confirmed}))
        limitations.append(
            f"Источник не подтверждён как загруженный (provenance={sources}): "
            "в production такой источник не может обосновать балл."
        )
        return _evaluation(
            item,
            status=STATUS_INSUFFICIENT,
            value=None,
            confidence=None,
            evidence_ids=used_ids,
            rationale=explain(item, answer, used),
            limitations=limitations,
            **base,
        )

    limitations.append(
        "Проверено: цитата найдена в тексте, переданном провайдером; независимая "
        "загрузка страницы системой не выполнялась."
    )
    confidence = round(
        sum(float(entry.confidence) for entry in confirmed) / len(confirmed), 3
    )
    return _evaluation(
        item,
        status=STATUS_ASSESSED,
        value=float(int(score)),
        confidence=confidence,
        evidence_ids=used_ids,
        rationale=explain(item, answer, used, value=int(score)),
        limitations=limitations,
        **base,
    )

