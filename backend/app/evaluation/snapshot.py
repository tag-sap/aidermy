"""Result snapshots: the single source of truth for UI and report.

A snapshot stores everything needed to reproduce and explain a result:
product + composition version, profile signals (never raw personal data),
parameter results with their statuses, total, verdict, completeness,
limitations, engine/rule versions and hashes.

`verify_snapshot` detects any modification of a stored snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .contracts import (
    ENGINE_VERSION,
    ContractError,
    EngineResult,
    ParameterEvaluation,
    RuleSet,
    sha256_of,
)
from .parameters import collect_signals

SNAPSHOT_SCHEMA_VERSION = "1.0.0"


def profile_fingerprint(profile: Mapping | None) -> dict:
    """Non-identifying profile representation used in snapshots and hashes."""
    signals = collect_signals(profile)
    return {
        "skin_type": signals.skin_type,
        "age": signals.age,
        "problems": list(signals.problems),
        "therapy": list(signals.therapy),
        "procedures": list(signals.procedures),
        "goals": list(signals.goals),
        # Intolerances are the most sensitive answers: only the count is stored.
        "intolerance_count": len(signals.intolerances),
        "unresolved_count": len(signals.unresolved),
    }


def _fingerprint_text(value: Any) -> str:
    return " ".join(str(value or "").replace("_", "-").replace("–", "-").replace("—", "-").split()).casefold()


def _fingerprint_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    normalised: set[str] = set()
    for item in values:
        if isinstance(item, Mapping):
            item = item.get("id") or item.get("type") or item.get("label") or ""
        text = _fingerprint_text(item)
        if text:
            normalised.add(text)
    return tuple(sorted(normalised))


def profile_compatible(stored: Mapping | None, current: Mapping | None) -> bool:
    """Compare saved and current profile signals without exact JSON quirks.

    Fingerprints written by older releases may omit optional fields such as
    ``goals`` or use a different age separator. Those differences alone must
    not invalidate a report. Core fit signals (skin type, problems, therapy,
    procedures) are required; optional signals are compared only when present
    on both sides.
    """
    if not isinstance(stored, Mapping) or not isinstance(current, Mapping):
        return False
    for key in ("skin_type",):
        if _fingerprint_text(stored.get(key)) != _fingerprint_text(current.get(key)):
            return False
    for key in ("problems", "therapy", "procedures"):
        if _fingerprint_list(stored.get(key)) != _fingerprint_list(current.get(key)):
            return False
    for key in ("age",):
        left, right = _fingerprint_text(stored.get(key)), _fingerprint_text(current.get(key))
        if left and right and left != right:
            return False
    for key in ("goals",):
        if key in stored and key in current:
            if _fingerprint_list(stored.get(key)) != _fingerprint_list(current.get(key)):
                return False
    for key in ("intolerance_count", "unresolved_count"):
        if key in stored and key in current:
            try:
                if int(stored.get(key) or 0) != int(current.get(key) or 0):
                    return False
            except (TypeError, ValueError):
                return False
    return True


def _iso(value: Any) -> str:
    """Normalise DB datetimes and strings to one canonical ISO representation."""
    if value is None or value == "":
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_snapshot(
    *,
    product: Mapping[str, Any],
    composition: Mapping[str, Any],
    profile: Mapping | None,
    evaluations: Sequence[ParameterEvaluation],
    result: EngineResult,
    rules: RuleSet,
    created_at: datetime | None = None,
    user_id: int | None = None,
    analysis: Mapping[str, Any] | None = None,
) -> dict:
    composition_hash = str(composition.get("composition_hash") or "")
    if not composition_hash:
        raise ContractError("composition_hash is required for a snapshot")
    for evaluation in evaluations:
        if evaluation.composition_hash != composition_hash:
            raise ContractError(
                f"evaluation {evaluation.parameter_id} belongs to another composition"
            )

    created = (created_at or datetime.now(timezone.utc)).isoformat()
    status = str(composition.get("status") or "unverified")
    limitations = list(result.limitations)
    if status != "active":
        limitations.append(
            f"Состав не подтверждён (status={status}): результат справочный и не должен "
            "рассматриваться как проверенный."
        )
    body = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "user_id": user_id,
        "rule_version": rules.version,
        "rules_hash": rules.hash,
        "engine_input_hash": result.input_hash,
        "product": {
            "id": product.get("id"),
            "name": str(product.get("name") or "").strip(),
        },
        "composition": {
            "hash": composition_hash,
            "source": composition.get("source") or "",
            "verified_at": _iso(composition.get("verified_at")),
            "status": status,
        },
        "profile": profile_fingerprint(profile),
        # User-facing list: only parameters with an actual, validated score.
        # pending / not_applicable / insufficient_evidence stay in storage
        # (evaluation.parameter_evaluations) and never enter this list or the average.
        "parameters": [
            {
                "parameter_id": item.parameter_id,
                "label": item.label,
                "value": item.value,
                "status": item.status,
                "included": item.included,
                "weight": item.weight,
                "reason": item.reason,
                "summary": item.summary,
            }
            for item in result.parameters
            if item.included and item.value is not None
        ],
        "total": result.total,
        "verdict": result.verdict,
        "completeness": round(result.completeness, 6),
        # Report completeness is part of the document and of its hash: an
        # unfinished analysis cannot be mistaken for a finished report, and a
        # later completed run produces a NEW snapshot instead of rewriting this one.
        "analysis": dict(analysis or {}),
        "limitations": limitations,
        "created_at": created,
    }
    body["snapshot_hash"] = sha256_of({k: v for k, v in body.items() if k != "snapshot_hash"})
    identity = {k: v for k, v in body.items() if k not in {"snapshot_hash", "created_at"}}
    body["snapshot_id"] = sha256_of(identity)[:32]
    return body


def verify_snapshot(snapshot: Mapping[str, Any]) -> bool:
    """True when the stored snapshot_hash matches its content."""
    stored = snapshot.get("snapshot_hash")
    if not stored:
        return False
    content = {k: v for k, v in snapshot.items() if k not in {"snapshot_hash", "snapshot_id"}}
    return sha256_of(content) == stored


def snapshot_summary(snapshot: Mapping[str, Any]) -> dict:
    """Compact view for API listings."""
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "product": snapshot.get("product"),
        "total": snapshot.get("total"),
        "verdict": snapshot.get("verdict"),
        "completeness": snapshot.get("completeness"),
        "analysis_status": (snapshot.get("analysis") or {}).get("status"),
        "is_final": (snapshot.get("analysis") or {}).get("is_final"),
        "rule_version": snapshot.get("rule_version"),
        "created_at": snapshot.get("created_at"),
    }
