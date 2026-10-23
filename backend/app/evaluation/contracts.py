"""Evaluation v2 — contracts.

Pure domain layer: no database, no network, no AI. Everything is immutable so a
result can be reproduced from its inputs and versions.

Score scale (chosen by the research model, validated here):

    0   — product conflicts with the parameter's requirement
    25  — mostly conflicts
    50  — the requirement is partly met / mixed, explicitly justified
    75  — mostly corresponds
    100 — fully corresponds

Only these five values are accepted. The deterministic layer never derives a
score from the amount or balance of quotes: it validates the model's result
(allowed value, mandatory explanation, references to confirmed evidence) and
stores it. A parameter without a score has a non-scoring status
(``pending`` / ``not_applicable`` / ``insufficient_evidence``) and is excluded
from the average — never replaced by 0 or 50.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Tuple

ENGINE_VERSION = "3.0.0-draft"

# Scores the research model may choose. Nothing else is accepted.
SCORE_LEVELS: Tuple[int, ...] = (0, 25, 50, 75, 100)

# Unified meaning of each level (provisional wording, not clinically validated).
# ``50`` means "partly corresponds / mixed and explicitly justified", never
# "unknown": an unknown outcome must be stored without a score.
SCORE_LEVEL_CRITERIA: dict[int, str] = {
    0: "подтверждённые данные по пункту прямо противоречат требованию пользователя",
    25: "подтверждённые данные в основном не соответствуют требованию, есть отдельные совпадения",
    50: "данные частично соответствуют и частично противоречат требованию; уровень выбран "
        "осознанно и обоснован, а не как «неизвестно»",
    75: "подтверждённые данные в основном соответствуют требованию, есть второстепенные ограничения",
    100: "подтверждённые данные прямо соответствуют требованию, существенных возражений нет",
}

STATUS_PENDING = "pending"                     # not researched yet
STATUS_ASSESSED = "assessed"                   # allowed score + explanation + evidence
STATUS_NOT_APPLICABLE = "not_applicable"       # parameter does not apply to the product
STATUS_INSUFFICIENT = "insufficient_evidence"  # applicable, but evidence is not enough
STATUS_STALE = "stale"                         # valid for another composition/method

# Values written by earlier drafts. They are readable for audit/history but are
# never scored by the engine and never migrated as authoritative results.
LEGACY_STATUS_EVALUATED = "evaluated"
LEGACY_STATUS_NOT_RESEARCHED = "not_researched"
LEGACY_STATUS_CONTRADICTORY = "contradictory_evidence"

SCORING_STATUSES = (STATUS_ASSESSED,)
STATUSES = (
    STATUS_PENDING,
    STATUS_ASSESSED,
    STATUS_NOT_APPLICABLE,
    STATUS_INSUFFICIENT,
    STATUS_STALE,
    LEGACY_STATUS_EVALUATED,
    LEGACY_STATUS_NOT_RESEARCHED,
    LEGACY_STATUS_CONTRADICTORY,
)


def canonical_json(payload: Any) -> str:
    """Stable JSON: sorted keys, no whitespace."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_of(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class ContractError(ValueError):
    """Raised when an input violates the evaluation contract."""


@dataclass(frozen=True)
class Parameter:
    """One evaluated questionnaire parameter (never a universal product axis)."""

    id: str
    label: str
    definition: str
    anchors: Tuple[Tuple[int, str], ...]
    direction: str = "benefit"  # benefit | risk (risk is already inverted into 0..100)
    section: str = ""           # questionnaire section: skin_type|problem|therapy|...
    option_id: str = ""         # selected option inside that section
    modifier: str = ""          # e.g. procedure period
    question: str = ""          # the user-facing question this parameter answers
    product_axes: Tuple[str, ...] = ()  # research hints only, never a stored axis

    def __post_init__(self) -> None:
        if self.direction not in {"benefit", "risk"}:
            raise ContractError(f"unknown direction for {self.id}: {self.direction}")
        if not self.anchors:
            raise ContractError(f"parameter {self.id} needs at least one scale anchor")
        if self.section and not self.id.startswith(f"{self.section}:"):
            raise ContractError(
                f"parameter {self.id} is not bound to questionnaire section {self.section!r}"
            )
        for value, text in self.anchors:
            try:
                numeric = int(value)
            except (TypeError, ValueError) as exc:
                raise ContractError(f"anchor value must be an integer for {self.id}") from exc
            if not 0 <= numeric <= 100:
                raise ContractError(f"anchor out of 0..100 for {self.id}: {value}")
            if not str(text).strip():
                raise ContractError(f"empty anchor text for {self.id}")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "definition": self.definition,
            "anchors": [[int(v), t] for v, t in self.anchors],
            "direction": self.direction,
            "section": self.section,
            "option_id": self.option_id,
            "modifier": self.modifier,
            "question": self.question,
            "product_axes": list(self.product_axes),
        }


@dataclass(frozen=True)
class ParameterEvaluation:
    """A stored, versioned evaluation of one product parameter."""

    parameter_id: str
    status: str
    composition_hash: str
    method_version: str
    value: float | None = None
    confidence: float | None = None
    evidence_ids: Tuple[str, ...] = ()
    rationale: str = ""
    limitations: Tuple[str, ...] = ()
    evaluated_at: str = ""
    valid_until: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ContractError(f"unknown status: {self.status}")
        if self.status == STATUS_ASSESSED:
            if self.value is None:
                raise ContractError(f"{self.parameter_id}: status=assessed requires a value")
            if int(float(self.value)) not in SCORE_LEVELS or float(self.value) != int(float(self.value)):
                raise ContractError(
                    f"{self.parameter_id}: score {self.value!r} is not one of {SCORE_LEVELS}"
                )
            if not str(self.rationale).strip():
                raise ContractError(
                    f"{self.parameter_id}: status=assessed requires an explanation"
                )
            if not self.evidence_ids:
                raise ContractError(
                    f"{self.parameter_id}: status=assessed requires references to stored evidence"
                )
        elif self.value is not None:
            # Only the legacy "evaluated" rows keep a historical number; they are
            # readable for audit but are never scored.
            if self.status != LEGACY_STATUS_EVALUATED:
                raise ContractError(
                    f"{self.parameter_id}: value is only allowed with status={STATUS_ASSESSED}"
                )
            if not 0 <= float(self.value) <= 100:
                raise ContractError(f"value out of 0..100 for {self.parameter_id}: {self.value}")
        if self.confidence is not None and not 0 <= float(self.confidence) <= 1:
            raise ContractError(f"confidence out of 0..1 for {self.parameter_id}")
        if not self.composition_hash:
            raise ContractError(f"{self.parameter_id}: composition_hash is required")
        if not self.method_version:
            raise ContractError(f"{self.parameter_id}: method_version is required")

    @property
    def usable(self) -> bool:
        """Only an ``assessed`` result may enter the average."""
        return self.status == STATUS_ASSESSED and self.value is not None

    def as_dict(self) -> dict:
        return {
            "parameter_id": self.parameter_id,
            "status": self.status,
            "composition_hash": self.composition_hash,
            "method_version": self.method_version,
            "value": self.value,
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
            "rationale": self.rationale,
            "limitations": list(self.limitations),
            "evaluated_at": self.evaluated_at,
            "valid_until": self.valid_until,
        }
@dataclass(frozen=True)
class RuleSet:
    """Versioned, immutable calculation rules. Weights are never invented here."""

    version: str
    aggregation: str
    completeness_threshold: float      # legacy field; the engine no longer gates on it
    verdict_bands: Tuple[Tuple[int, str], ...]
    calibrated: bool
    missing_policy: str = "exclude_and_reduce_completeness"
    min_confidence: float = 0.0
    score_levels: Tuple[int, ...] = SCORE_LEVELS

    def __post_init__(self) -> None:
        if self.aggregation not in {"weighted_mean", "arithmetic_mean"}:
            raise ContractError(f"unsupported aggregation: {self.aggregation}")
        if not 0 <= self.completeness_threshold <= 1:
            raise ContractError("completeness_threshold must be within 0..1")
        if not self.version:
            raise ContractError("rule version is required")
        if self.missing_policy != "exclude_and_reduce_completeness":
            raise ContractError(f"unsupported missing policy: {self.missing_policy}")
        if self.calibrated and not self.verdict_bands:
            raise ContractError("calibrated rules require verdict bands")
        levels = tuple(int(level) for level in self.score_levels)
        if not levels:
            raise ContractError("score_levels must not be empty")
        if list(levels) != sorted(set(levels)):
            raise ContractError("score_levels must be unique and sorted ascending")
        for level in levels:
            if not 0 <= level <= 100:
                raise ContractError(f"score level out of 0..100: {level}")
        thresholds = []
        for threshold, label in self.verdict_bands:
            if not 0 <= int(threshold) <= 100:
                raise ContractError(f"verdict threshold out of 0..100: {threshold}")
            if not str(label).strip():
                raise ContractError("verdict label must not be empty")
            thresholds.append(int(threshold))
        if thresholds != sorted(set(thresholds), reverse=True):
            raise ContractError(
                "verdict bands must be unique and sorted from high to low"
            )

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "aggregation": self.aggregation,
            "completeness_threshold": self.completeness_threshold,
            "verdict_bands": [list(b) for b in self.verdict_bands],
            "calibrated": self.calibrated,
            "missing_policy": self.missing_policy,
            "min_confidence": self.min_confidence,
            "score_levels": list(self.score_levels),
        }

    @property
    def hash(self) -> str:
        return sha256_of(self.as_dict())


@dataclass(frozen=True)
class ParameterResult:
    parameter_id: str
    label: str
    weight: float           # normalized weight inside the relevant set
    value: float | None
    status: str
    included: bool
    reason: str
    summary: str = ""       # short user-facing answer; full reason stays in diagnostics


@dataclass(frozen=True)
class EngineResult:
    parameters: Tuple[ParameterResult, ...]
    total: float | None
    verdict: str | None
    completeness: float
    limitations: Tuple[str, ...]
    rule_version: str
    engine_version: str = ENGINE_VERSION
    input_hash: str = field(default="")

    def as_dict(self) -> dict:
        return {
            "parameters": [
                {
                    "parameter_id": p.parameter_id,
                    "label": p.label,
                    "weight": round(p.weight, 6),
                    "value": p.value,
                    "status": p.status,
                    "included": p.included,
                    "reason": p.reason,
                    "summary": p.summary,
                }
                for p in self.parameters
            ],
            "total": self.total,
            "verdict": self.verdict,
            "completeness": round(self.completeness, 6),
            "limitations": list(self.limitations),
            "rule_version": self.rule_version,
            "engine_version": self.engine_version,
            "input_hash": self.input_hash,
        }


def assert_unique(evaluations: Sequence[ParameterEvaluation]) -> None:
    """Exactly one current evaluation per parameter is required for determinism."""
    seen: dict = {}
    for item in evaluations:
        if item.parameter_id in seen:
            raise ContractError(f"duplicate evaluation for parameter {item.parameter_id}")
        seen[item.parameter_id] = item


def normalized_weights(weights: Mapping[str, float]) -> dict:
    positive = {k: float(v) for k, v in weights.items() if float(v) > 0}
    total = sum(positive.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in positive.items()}
