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
        "signals": list(signals.ids),
        "therapy": list(signals.active_therapy),
        "procedures": list(signals.recent_procedures),
        "allergy_count": len(signals.allergies),
        "intolerance_count": len(signals.intolerances),
    }


def build_snapshot(
    *,
    product: Mapping[str, Any],
    composition: Mapping[str, Any],
    profile: Mapping | None,
    evaluations: Sequence[ParameterEvaluation],
    result: EngineResult,
    rules: RuleSet,
    created_at: datetime | None = None,
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
    body = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
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
            "verified_at": composition.get("verified_at") or "",
        },
        "profile": profile_fingerprint(profile),
        "parameters": [
            {
                "parameter_id": item.parameter_id,
                "value": item.value,
                "status": item.status,
                "included": item.included,
                "weight": round(item.weight, 6),
                "reason": item.reason,
            }
            for item in result.parameters
        ],
        "total": result.total,
        "verdict": result.verdict,
        "completeness": round(result.completeness, 6),
        "limitations": list(result.limitations),
        "created_at": created,
    }
    body["snapshot_hash"] = sha256_of({k: v for k, v in body.items() if k != "snapshot_hash"})
    body["snapshot_id"] = body["snapshot_hash"][:32]
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
        "rule_version": snapshot.get("rule_version"),
        "created_at": snapshot.get("created_at"),
    }
