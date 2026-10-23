"""Deterministic Score Engine v3.

Input:  user profile + stored parameter evaluations + one versioned rule set.
Output: per-parameter results, total (plain arithmetic mean of assessed scores),
verdict (only when the rule set is calibrated), limitations and a reproducible
hash.

Guarantees:
  * pure function — no I/O, no randomness, no AI;
  * identical input + identical rule version => identical output and hash;
  * the relevant set is exactly the questionnaire options the user selected
    (``parameters.resolve_parameters``), never a universal product scorecard;
  * only ``assessed`` results enter the average; ``pending``, ``not_applicable``
    and ``insufficient_evidence`` are excluded and never replaced by 0/50;
  * no weights, coverage gates, penalties or confidence bonuses;
  * the total is a plain arithmetic mean and may be fractional (e.g. 62.5);
    it is rounded only for display of the average, never the sub-scores;
  * the verdict stays disabled while ``calibrated=false``.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from .contracts import (
    LEGACY_STATUS_CONTRADICTORY,
    LEGACY_STATUS_EVALUATED,
    LEGACY_STATUS_NOT_RESEARCHED,
    STATUS_ASSESSED,
    STATUS_INSUFFICIENT,
    STATUS_NOT_APPLICABLE,
    STATUS_PENDING,
    STATUS_STALE,
    EngineResult,
    ParameterEvaluation,
    ParameterResult,
    RuleSet,
    assert_unique,
    sha256_of,
)
from .parameters import resolve_parameters
from .rules import get_rules

_STATUS_REASON = {
    STATUS_PENDING: "оценка ещё не рассчитана",
    STATUS_NOT_APPLICABLE: "параметр неприменим к продукту",
    STATUS_INSUFFICIENT: "недостаточно доказательств для оценки",
    STATUS_STALE: "оценка устарела относительно текущего состава или методики",
    LEGACY_STATUS_EVALUATED: "оценка по прежней методике не используется",
    LEGACY_STATUS_NOT_RESEARCHED: "оценка ещё не рассчитана",
    LEGACY_STATUS_CONTRADICTORY: "прежняя методика зафиксировала противоречие",
}


def _verdict_for(total: float, rules: RuleSet) -> str | None:
    if not rules.calibrated:
        return None
    for threshold, label in sorted(rules.verdict_bands, reverse=True):
        if total >= threshold:
            return label
    return None


def evaluate(
    profile: Mapping | None,
    evaluations: Sequence[ParameterEvaluation],
    rules: RuleSet | None = None,
) -> EngineResult:
    rules = rules or get_rules()
    assert_unique(evaluations)

    resolved = resolve_parameters(profile)
    limitations: list[str] = list(resolved.notes)

    # Questionnaire answers only select WHICH parameters matter. Every selected
    # parameter gets the same share: no importance weights, no blockers.
    share = 1.0 / len(resolved.parameters) if resolved.parameters else 0.0
    weights = {parameter.id: share for parameter in resolved.parameters}
    by_id = {parameter.id: parameter for parameter in resolved.parameters}

    if not weights:
        payload = {
            "relevance": {},
            "evaluations": sorted(
                [e.as_dict() for e in evaluations], key=lambda d: d["parameter_id"]
            ),
            "rules": rules.hash,
        }
        return EngineResult(
            parameters=(),
            total=None,
            verdict=None,
            completeness=0.0,
            limitations=tuple(
                limitations + ["В анкете нет ответов, определяющих параметры оценки."]
            ),
            rule_version=rules.version,
            input_hash=sha256_of(payload),
        )

    by_parameter = {item.parameter_id: item for item in evaluations}
    results: list[ParameterResult] = []
    covered_weight = 0.0

    for parameter_id, weight in sorted(weights.items(), key=lambda kv: (-kv[1], kv[0])):
        parameter = by_id[parameter_id]
        evaluation = by_parameter.get(parameter_id)

        if evaluation is None:
            results.append(
                ParameterResult(
                    parameter_id=parameter_id,
                    label=parameter.label,
                    weight=weight,
                    value=None,
                    status=STATUS_PENDING,
                    included=False,
                    reason=_STATUS_REASON[STATUS_PENDING],
                )
            )
            continue

        if evaluation.status != STATUS_ASSESSED:
            results.append(
                ParameterResult(
                    parameter_id=parameter_id,
                    label=parameter.label,
                    weight=weight,
                    value=None,
                    status=evaluation.status,
                    included=False,
                    reason=_STATUS_REASON.get(evaluation.status, "оценка недоступна"),
                )
            )
            if evaluation.limitations:
                limitations.extend(
                    f"{parameter.label}: {text}" for text in evaluation.limitations
                )
            continue
        if rules.min_confidence > 0 and (
            evaluation.confidence is None
            or evaluation.confidence < rules.min_confidence
        ):
            results.append(
                ParameterResult(
                    parameter_id=parameter_id,
                    label=parameter.label,
                    weight=weight,
                    value=None,
                    status=STATUS_INSUFFICIENT,
                    included=False,
                    reason="уверенность ниже порога правил",
                )
            )
            continue

        covered_weight += weight
        results.append(
            ParameterResult(
                parameter_id=parameter_id,
                label=parameter.label,
                weight=weight,
                value=float(evaluation.value),
                status=STATUS_ASSESSED,
                included=True,
                reason=evaluation.rationale or "оценка подтверждена сохранёнными доказательствами",
            )
        )

    completeness = round(covered_weight, 6)   # diagnostics only; never affects the total
    assessed_scores = [float(r.value) for r in results if r.included and r.value is not None]
    total: float | None = None
    verdict: str | None = None

    if not assessed_scores:
        # No score exists. It is not 0 and not 50: the compatibility is unknown.
        limitations.append(
            "Нет ни одной оценённой оценки — итоговая совместимость не определена. "
            "Пропуски не заменяются нулём или нейтральным баллом."
        )
    else:
        total = round(sum(assessed_scores) / len(assessed_scores), 2)
        verdict = _verdict_for(total, rules)
        if not rules.calibrated:
            limitations.append(
                "Пороговые значения вердикта не откалиброваны по независимым эталонам, "
                "поэтому вердикт не выводится. Балл — не вероятность эффективности "
                "или безопасности."
            )

    payload = {
        "relevance": {k: round(v, 6) for k, v in weights.items()},
        "evaluations": sorted(
            [e.as_dict() for e in evaluations if e.parameter_id in weights],
            key=lambda d: d["parameter_id"],
        ),
        "rules": rules.hash,
    }

    return EngineResult(
        parameters=tuple(results),
        total=total,
        verdict=verdict,
        completeness=completeness,
        limitations=tuple(dict.fromkeys(limitations)),
        rule_version=rules.version,
        input_hash=sha256_of(payload),
    )
