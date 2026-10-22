"""Deterministic Score Engine v2 (aggregation variant A).

Input:  user profile + stored parameter evaluations + one versioned rule set.
Output: per-parameter results, total (if enough data), verdict (only when the
rule set is calibrated), completeness, limitations and a reproducible hash.

Guarantees:
  * pure function — no I/O, no randomness, no AI;
  * identical input + identical rule version => identical output and hash;
  * a missing evaluation is never replaced by 0/50/"neutral": it is excluded
    and reduces completeness;
  * weights come only from questionnaire relevance, normalized over the
    relevant set; missing parameters do not dilute the total;
  * the total is computed only when completeness >= rule threshold.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from .contracts import (
    STATUS_CONTRADICTORY,
    STATUS_EVALUATED,
    STATUS_INSUFFICIENT,
    STATUS_NOT_RESEARCHED,
    STATUS_STALE,
    EngineResult,
    ParameterEvaluation,
    ParameterResult,
    RuleSet,
    assert_unique,
    normalized_weights,
    sha256_of,
)
from .parameters import PARAMETERS, resolve_relevance
from .rules import get_rules

_STATUS_REASON = {
    STATUS_INSUFFICIENT: "недостаточно доказательств для оценки",
    STATUS_CONTRADICTORY: "источники противоречат друг другу",
    STATUS_STALE: "оценка устарела относительно текущего состава или методики",
    STATUS_NOT_RESEARCHED: "оценка ещё не рассчитана",
}


def _verdict_for(total: int, rules: RuleSet) -> str | None:
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

    relevance = resolve_relevance(profile)
    weights = normalized_weights(relevance.weights)
    limitations: list[str] = list(relevance.notes)

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
        parameter = PARAMETERS[parameter_id]
        evaluation = by_parameter.get(parameter_id)

        if evaluation is None:
            results.append(
                ParameterResult(
                    parameter_id=parameter_id,
                    label=parameter.label,
                    weight=weight,
                    value=None,
                    status=STATUS_NOT_RESEARCHED,
                    included=False,
                    reason=_STATUS_REASON[STATUS_NOT_RESEARCHED],
                )
            )
            continue

        if evaluation.status != STATUS_EVALUATED:
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
        if evaluation.confidence is not None and evaluation.confidence < rules.min_confidence:
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
                status=STATUS_EVALUATED,
                included=True,
                reason=evaluation.rationale or "оценка подтверждена сохранёнными доказательствами",
            )
        )

    completeness = round(covered_weight, 6)
    total: int | None = None
    verdict: str | None = None

    if completeness < rules.completeness_threshold:
        limitations.append(
            "Полнота данных ниже порога правил "
            f"({completeness:.2f} < {rules.completeness_threshold:.2f}): "
            "общий балл не рассчитывается."
        )
    else:
        weighted_sum = sum(
            r.weight * float(r.value) for r in results if r.included and r.value is not None
        )
        total = int(round(weighted_sum / covered_weight))
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
