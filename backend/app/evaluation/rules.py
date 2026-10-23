"""Versioned rule sets for the deterministic Score Engine.

Active default: ``3.0.0-draft`` — plain arithmetic mean of the *assessed*
questionnaire parameters. There is no completeness gate: a missing or
non-scoring parameter is excluded, never replaced by 0/50, and never penalised.
The research model chooses one of the five allowed scores; the engine only
averages validated results.

``2.0.0-draft`` (evidence bands) and ``1.0.0-draft`` (weighted mean) are kept
only so earlier experiments stay reproducible.

All three are ``calibrated=False``: the engine returns per-parameter results and
a total, but NO verdict, because verdict thresholds have not been validated
against independent reference labels yet.
"""
from __future__ import annotations

from .contracts import SCORE_LEVELS, ContractError, RuleSet

# Draft thresholds: they exist so the pipeline can be exercised end-to-end and
# so calibration can measure their behaviour. They are NOT validated values.
_COMPLETENESS_THRESHOLD = 0.5
_VERDICT_BANDS = ((75, "high"), (50, "medium"), (25, "low"), (0, "very_low"))

RULE_SETS: dict[str, RuleSet] = {
    "3.0.0-draft": RuleSet(
        version="3.0.0-draft",
        aggregation="arithmetic_mean",
        completeness_threshold=0.0,   # no gate: every assessed parameter counts
        verdict_bands=_VERDICT_BANDS,
        calibrated=False,
        missing_policy="exclude_and_reduce_completeness",
        min_confidence=0.0,
        score_levels=SCORE_LEVELS,
    ),
    "2.0.0-draft": RuleSet(
        version="2.0.0-draft",
        aggregation="arithmetic_mean",
        completeness_threshold=_COMPLETENESS_THRESHOLD,
        verdict_bands=_VERDICT_BANDS,
        calibrated=False,
        missing_policy="exclude_and_reduce_completeness",
        min_confidence=0.0,
        score_levels=SCORE_LEVELS,
    ),
    "1.0.0-draft": RuleSet(
        version="1.0.0-draft",
        aggregation="weighted_mean",
        completeness_threshold=0.6,
        verdict_bands=_VERDICT_BANDS,
        calibrated=False,
        missing_policy="exclude_and_reduce_completeness",
        min_confidence=0.0,
        score_levels=SCORE_LEVELS,
    ),
}

DEFAULT_RULE_VERSION = "3.0.0-draft"


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
            "арифметическое среднее оценённых параметров "
            "(веса важности не используются)"
        )
    else:
        aggregation_text = "взвешенное среднее по релевантным параметрам (устаревшая версия)"
    return {
        "version": rules.version,
        "aggregation": aggregation_text,
        "included_statuses": ["assessed"],
        "excluded_statuses": ["pending", "not_applicable", "insufficient_evidence"],
        "score_levels": list(rules.score_levels),
        "completeness_threshold": rules.completeness_threshold,
        "missing_policy": (
            "параметр без оценки исключается из числителя и знаменателя; "
            "значение 0/50 не подставляется; порога покрытия нет"
        ),
        "verdict_bands": list(rules.verdict_bands),
        "calibrated": rules.calibrated,
        "verdict_enabled": rules.calibrated,
        "rules_hash": rules.hash,
    }

