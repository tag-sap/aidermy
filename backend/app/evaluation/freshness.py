"""Freshness rules: is a stored evaluation still usable?

An evaluation is current only when ALL of the following hold:
  * it belongs to the same composition version (composition_hash);
  * it was produced by the same method version;
  * it has not passed valid_until (when set);
  * it is not superseded (superseded rows are never passed to the engine).

Nothing here mutates data; the caller decides whether to re-research.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .contracts import ParameterEvaluation


def _parse(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def stale_reason(
    evaluation: ParameterEvaluation,
    *,
    composition_hash: str,
    method_version: str,
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> str | None:
    """Return a human-readable reason why the evaluation is stale, or None."""
    if evaluation.composition_hash != composition_hash:
        return "состав продукта изменился (другой composition_hash)"
    if evaluation.method_version != method_version:
        return "изменилась версия методики оценки"
    if evaluation.valid_until:
        valid_until = _parse(evaluation.valid_until)
        current = now or datetime.now(timezone.utc)
        if valid_until is None:
            return "некорректный формат valid_until — актуальность не подтверждена"
        if current > valid_until:
            return "истёк срок действия оценки (valid_until)"
    if max_age_days is not None and evaluation.evaluated_at:
        evaluated_at = _parse(evaluation.evaluated_at)
        current = now or datetime.now(timezone.utc)
        if evaluated_at is None:
            return "некорректная дата оценки — возраст не подтверждён"
        if current - evaluated_at > timedelta(days=max_age_days):
            return f"оценка старше {max_age_days} дн."
    return None


def is_current(
    evaluation: ParameterEvaluation,
    *,
    composition_hash: str,
    method_version: str,
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> bool:
    return (
        stale_reason(
            evaluation,
            composition_hash=composition_hash,
            method_version=method_version,
            now=now,
            max_age_days=max_age_days,
        )
        is None
    )


def select_current(
    evaluations: list[ParameterEvaluation],
    *,
    composition_hash: str,
    method_version: str,
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> tuple[list[ParameterEvaluation], dict[str, str]]:
    """Split evaluations into current ones and a map parameter_id -> stale reason."""
    current: list[ParameterEvaluation] = []
    stale: dict[str, str] = {}
    for evaluation in evaluations:
        reason = stale_reason(
            evaluation,
            composition_hash=composition_hash,
            method_version=method_version,
            now=now,
            max_age_days=max_age_days,
        )
        if reason is None:
            current.append(evaluation)
        else:
            stale[evaluation.parameter_id] = reason
    return current, stale
