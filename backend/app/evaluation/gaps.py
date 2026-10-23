"""Knowledge scan and report completeness.

Two questions are answered here, deterministically and without I/O:

  * which questionnaire parameters are already backed by usable knowledge, and
    exactly why the others are not (``scan_parameters``);
  * may the assembled result be presented as a finished report
    (``analysis_state``).

A parameter is *usable knowledge* only when it has a current evaluation with a
non-zero-information outcome: ``assessed`` (a validated score) or
``not_applicable`` (a grounded decision). ``insufficient_evidence`` is a gap by
definition: "we do not know" is not knowledge to reuse. Legacy statuses are gaps
too — they belong to an earlier method and are never scored here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Sequence

from .contracts import (
    STATUS_ASSESSED,
    STATUS_INSUFFICIENT,
    STATUS_NOT_APPLICABLE,
    ParameterEvaluation,
)
from .freshness import DEFAULT_REVIEW_AFTER_DAYS, select_current
from .parameters import resolve_parameters

GAP_MISSING = "missing"              # no evaluation for this composition/method
GAP_STALE = "stale"                  # evaluation exists but is out of date
GAP_INSUFFICIENT = "insufficient"    # applicable, evidence was not enough
GAP_UNSUPPORTED = "unsupported"      # pending/legacy status, not reusable

GAP_REASONS = (GAP_MISSING, GAP_STALE, GAP_INSUFFICIENT, GAP_UNSUPPORTED)

GAP_LABELS = {
    GAP_MISSING: "результата ещё нет",
    GAP_STALE: "результат устарел",
    GAP_INSUFFICIENT: "недостаточно доказательств",
    GAP_UNSUPPORTED: "статус не пригоден для повторного использования",
}

ANALYSIS_COMPLETE = "complete"
ANALYSIS_INCOMPLETE = "incomplete"
ANALYSIS_FAILED = "failed"
ANALYSIS_BLOCKED = "blocked"
ANALYSIS_STATUSES = (
    ANALYSIS_COMPLETE,
    ANALYSIS_INCOMPLETE,
    ANALYSIS_FAILED,
    ANALYSIS_BLOCKED,
)


@dataclass(frozen=True)
class ParameterGap:
    """One parameter that still needs research, with a machine-readable reason."""

    parameter_id: str
    reason: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.reason not in GAP_REASONS:
            raise ValueError(f"unknown gap reason: {self.reason}")

    def as_dict(self) -> dict:
        return {
            "parameter_id": self.parameter_id,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class KnowledgeScan:
    """Result of checking EVERY parameter before any research begins."""

    current: tuple[ParameterEvaluation, ...] = ()
    gaps: tuple[ParameterGap, ...] = ()
    stale: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def needed(self) -> tuple[str, ...]:
        return tuple(sorted(gap.parameter_id for gap in self.gaps))

    @property
    def assessed(self) -> tuple[ParameterEvaluation, ...]:
        return tuple(item for item in self.current if item.status == STATUS_ASSESSED)

    @property
    def not_applicable(self) -> tuple[ParameterEvaluation, ...]:
        return tuple(item for item in self.current if item.status == STATUS_NOT_APPLICABLE)

    def gap_for(self, parameter_id: str) -> ParameterGap | None:
        return next((gap for gap in self.gaps if gap.parameter_id == parameter_id), None)


def scan_parameters(
    *,
    evaluations: Sequence[ParameterEvaluation],
    profile: Mapping | None,
    composition_hash: str,
    method_version: str,
    now: datetime | None = None,
    max_age_days: int | None = None,
    review_after_days: int | None = DEFAULT_REVIEW_AFTER_DAYS,
) -> KnowledgeScan:
    """Check all parameters of the questionnaire for this product version.

    The scan is complete before the caller may start research: it returns the
    whole gap set, not the first missing parameter.
    """
    resolved = resolve_parameters(profile)
    by_id = {item.parameter_id: item for item in evaluations}
    relevant_ids = {parameter.id for parameter in resolved.parameters}
    relevant = [item for item in evaluations if item.parameter_id in relevant_ids]

    current, stale_reasons = select_current(
        relevant,
        composition_hash=composition_hash,
        method_version=method_version,
        now=now,
        max_age_days=max_age_days,
        review_after_days=review_after_days,
    )
    current_ids = {item.parameter_id for item in current}

    gaps: list[ParameterGap] = []
    for parameter in resolved.parameters:
        evaluation = by_id.get(parameter.id)
        if evaluation is None:
            gaps.append(ParameterGap(parameter.id, GAP_MISSING, "оценки нет"))
            continue
        if parameter.id in stale_reasons:
            gaps.append(
                ParameterGap(parameter.id, GAP_STALE, stale_reasons[parameter.id])
            )
            continue
        # "Not enough evidence" is a gap even while it is still "fresh": unknown is
        # not knowledge to reuse. Re-research is bounded by max_attempts, and each
        # shared-research run may bring new documents.
        if evaluation.status == STATUS_INSUFFICIENT:
            gaps.append(
                ParameterGap(
                    parameter.id,
                    GAP_INSUFFICIENT,
                    evaluation.rationale or "доказательств недостаточно",
                )
            )
            continue
        if parameter.id in current_ids:
            continue
        gaps.append(
            ParameterGap(
                parameter.id,
                GAP_UNSUPPORTED,
                f"status={evaluation.status} нельзя использовать как результат",
            )
        )

    stale = tuple(sorted(pid for pid in stale_reasons if pid in relevant_ids))
    return KnowledgeScan(
        current=tuple(current),
        gaps=tuple(gaps),
        stale=stale,
        notes=tuple(resolved.notes),
    )


@dataclass(frozen=True)
class AnalysisState:
    """Whether an assembled result is a finished report, and why."""

    status: str
    is_final: bool
    assessed_parameters: tuple[str, ...] = ()
    not_applicable_parameters: tuple[str, ...] = ()
    gaps: tuple[ParameterGap, ...] = ()
    failed_parameters: tuple[str, ...] = ()
    deferred_parameters: tuple[str, ...] = ()
    exhausted_parameters: tuple[str, ...] = ()
    documents_fetched: int = 0
    documents_reused: int = 0
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in ANALYSIS_STATUSES:
            raise ValueError(f"unknown analysis status: {self.status}")

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "is_final": self.is_final,
            "assessed_parameters": list(self.assessed_parameters),
            "not_applicable_parameters": list(self.not_applicable_parameters),
            "gaps": [gap.as_dict() for gap in self.gaps],
            "failed_parameters": list(self.failed_parameters),
            "deferred_parameters": list(self.deferred_parameters),
            "exhausted_parameters": list(self.exhausted_parameters),
            "documents_fetched": self.documents_fetched,
            "documents_reused": self.documents_reused,
            "notes": list(self.notes),
        }



def analysis_state(
    *,
    scan: KnowledgeScan,
    research: Mapping | None = None,
    blocked: bool = False,
    extra_notes: Iterable[str] = (),
) -> AnalysisState:
    """Derive report completeness from the scan and (optional) research result.

    ``is_final`` is true only when every relevant parameter has usable, current
    knowledge and no research step failed. An unfinished or failed analysis is
    never presented as a complete report, even if some parameters already have
    scores.
    """
    failed = tuple(str(item) for item in (research or {}).get("failed") or ())
    deferred = tuple(str(item) for item in (research or {}).get("deferred") or ())
    exhausted = tuple(str(item) for item in (research or {}).get("exhausted") or ())
    notes = list(scan.notes)
    notes.extend(
        str(text) for text in (research or {}).get("notes") or () if str(text).strip()
    )
    notes.extend(str(text) for text in extra_notes if str(text).strip())

    assessed = tuple(sorted(item.parameter_id for item in scan.assessed))
    not_applicable = tuple(sorted(item.parameter_id for item in scan.not_applicable))
    gaps = scan.gaps

    if blocked:
        status = ANALYSIS_BLOCKED
    elif failed and not (assessed or not_applicable):
        status = ANALYSIS_FAILED
    elif gaps:
        status = ANALYSIS_INCOMPLETE
    else:
        status = ANALYSIS_COMPLETE

    if status == ANALYSIS_INCOMPLETE and not research:
        notes.append(
            "Исследование недостающих параметров не запускалось: результат неполный "
            "и не является готовым отчётом."
        )
    elif status == ANALYSIS_INCOMPLETE:
        notes.append(
            "Часть параметров осталась без подтверждённого результата: отчёт помечен "
            "как неполный."
        )

    return AnalysisState(
        status=status,
        is_final=status == ANALYSIS_COMPLETE,
        assessed_parameters=assessed,
        not_applicable_parameters=not_applicable,
        gaps=tuple(gaps),
        failed_parameters=failed,
        deferred_parameters=deferred,
        exhausted_parameters=exhausted,
        documents_fetched=int((research or {}).get("documents_fetched") or 0),
        documents_reused=int((research or {}).get("documents_reused") or 0),
        notes=tuple(dict.fromkeys(notes)),
    )

