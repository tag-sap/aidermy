"""Versioned rule sets for the deterministic Score Engine.

Active default: ``2.0.0-draft`` — plain arithmetic mean of the available
evaluations of relevant parameters. Questionnaire relevance still selects WHICH
parameters matter; it no longer carries importance weights, so no hidden
weighting, no blockers and no penalties.

``1.0.0-draft`` is kept only so earlier experiments stay reproducible.

Both are ``calibrated=False``: the engine returns per-parameter results and a
total, but NO verdict, because verdict thresholds have not been validated
against independent reference labels yet.
"""
from __future__ import annotations

from .contracts import ContractError, RuleSet

# Draft thresholds: they exist so the pipeline can be exercised end-to-end and
# so calibration can measure their behaviour. They are NOT validated values.
_COMPLETENESS_THRESHOLD = 0.5
_VERDICT_BANDS = ((75, "high"), (50, "medium"), (25, "low"), (0, "very_low"))

RULE_SETS: dict[str, RuleSet] = {
    "2.0.0-draft": RuleSet(
        version="2.0.0-draft",
        aggregation="arithmetic_mean",
        completeness_threshold=_COMPLETENESS_THRESHOLD,
        verdict_bands=_VERDICT_BANDS,
        calibrated=False,
        missing_policy="exclude_and_reduce_completeness",
        min_confidence=0.0,
    ),
    "1.0.0-draft": RuleSet(
        version="1.0.0-draft",
        aggregation="weighted_mean",
        completeness_threshold=0.6,
        verdict_bands=_VERDICT_BANDS,
        calibrated=False,
        missing_policy="exclude_and_reduce_completeness",
        min_confidence=0.0,
    ),
}

DEFAULT_RULE_VERSION = "2.0.0-draft"


def get_rules(version: str | None = None) -> RuleSet:
    key = version or DEFAULT_RULE_VERSION
    try:
        return RULE_SETS[key]
    except KeyError as exc:
        raise ContractError(f"unknown rule version: {key}") from exc


def describe_rules(rules: RuleSet) -> dict:
    """Human-readable summary used by API/docs (no hidden numbers)."""
    if rules.aggregation == "arithmetic_mean":
        aggregation_text = (
            "арифметическое среднее доступных оценок релевантных параметров "
            "(веса важности не используются)"
        )
    else:
        aggregation_text = "взвешенное среднее по релевантным параметрам (устаревшая версия)"
    return {
        "version": rules.version,
        "aggregation": aggregation_text,
        "completeness_threshold": rules.completeness_threshold,
        "missing_policy": (
            "отсутствующая оценка исключается из числителя и знаменателя и снижает полноту; "
            "значение 0/50 не подставляется"
        ),
        "verdict_bands": list(rules.verdict_bands),
        "calibrated": rules.calibrated,
        "verdict_enabled": rules.calibrated,
        "rules_hash": rules.hash,
    }

