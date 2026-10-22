"""Versioned rule sets for the deterministic Score Engine.

Only one rule set exists so far: v1.0.0-draft. It is deliberately marked
``calibrated=False``: the engine will then return per-parameter results and a
total, but NO verdict, because verdict thresholds have not been validated
against independent reference labels yet. Enabling a verdict requires a new
rule version with `calibrated=True` and documented calibration results.
"""
from __future__ import annotations

from .contracts import ContractError, RuleSet

# Draft thresholds: they exist so the pipeline can be exercised end-to-end and
# so calibration can measure their behaviour. They are NOT validated values.
_COMPLETENESS_THRESHOLD = 0.6
_VERDICT_BANDS = ((75, "high"), (50, "medium"), (25, "low"), (0, "very_low"))

RULE_SETS: dict[str, RuleSet] = {
    "1.0.0-draft": RuleSet(
        version="1.0.0-draft",
        aggregation="weighted_mean",
        completeness_threshold=_COMPLETENESS_THRESHOLD,
        verdict_bands=_VERDICT_BANDS,
        calibrated=False,
        missing_policy="exclude_and_reduce_completeness",
        min_confidence=0.0,
    ),
}

DEFAULT_RULE_VERSION = "1.0.0-draft"


def get_rules(version: str | None = None) -> RuleSet:
    key = version or DEFAULT_RULE_VERSION
    try:
        return RULE_SETS[key]
    except KeyError as exc:
        raise ContractError(f"unknown rule version: {key}") from exc


def describe_rules(rules: RuleSet) -> dict:
    """Human-readable summary used by API/docs (no hidden numbers)."""
    return {
        "version": rules.version,
        "aggregation": "взвешенное среднее по релевантным параметрам",
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
