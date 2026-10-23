"""Orchestration for evaluation v2.

Ties together: profile relevance → stored evaluations → freshness → engine →
snapshot. It never calls AI itself; instead it returns the list of parameters
that need research, so a worker can enqueue exactly those (and only those).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from .contracts import (
    ParameterEvaluation,
    RuleSet,
    sha256_of,
)
from .engine import evaluate
from .freshness import DEFAULT_REVIEW_AFTER_DAYS
from .gaps import AnalysisState, KnowledgeScan, analysis_state, scan_parameters
from .parameters import resolve_relevance
from .rules import get_rules
from .snapshot import build_snapshot, verify_snapshot
from .store import EvaluationStore, StoreError

DEFAULT_METHOD_VERSION = "research-1.0.0-draft"


@dataclass(frozen=True)
class BuildResult:
    snapshot: dict
    pending_parameters: tuple[str, ...]
    stale_parameters: tuple[str, ...]
    reused: bool
    analysis: AnalysisState
    scan: KnowledgeScan


class EvaluationService:
    def __init__(
        self,
        store: EvaluationStore,
        *,
        rules: RuleSet | None = None,
        method_version: str = DEFAULT_METHOD_VERSION,
        max_age_days: int | None = None,
        review_after_days: int | None = DEFAULT_REVIEW_AFTER_DAYS,
    ) -> None:
        self.store = store
        self.rules = rules or get_rules()
        self.method_version = method_version
        self.max_age_days = max_age_days
        self.review_after_days = review_after_days

    # -- composition --------------------------------------------------------
    def ensure_composition(self, product_id: int, composition: Mapping[str, Any]) -> dict:
        composition_hash = str(composition.get("composition_hash") or "")
        if not composition_hash:
            raise StoreError("composition_hash is required")
        existing = self.store.get_composition(product_id, composition_hash)
        if existing is not None:
            return existing
        return self.store.upsert_composition(
            {
                "product_id": product_id,
                "composition_hash": composition_hash,
                "inci_raw": composition.get("inci_raw") or "",
                "source": composition.get("source") or "",
                "verified_at": composition.get("verified_at") or "",
            }
        )

    # -- build --------------------------------------------------------------
    def build(
        self,
        *,
        product: Mapping[str, Any],
        composition: Mapping[str, Any],
        profile: Mapping[str, Any] | None,
        now: datetime | None = None,
        user_id: int | None = None,
        research_summary: Mapping[str, Any] | None = None,
        blocked: bool = False,
    ) -> BuildResult:
        product_id = product.get("id")
        if product_id is None:
            raise StoreError("product.id is required")
        record = self.ensure_composition(int(product_id), composition)
        composition_hash = str(record["composition_hash"])

        stored = self.store.current_evaluations(record["id"], self.method_version)
        scan = scan_parameters(
            evaluations=stored,
            profile=profile,
            composition_hash=composition_hash,
            method_version=self.method_version,
            now=now,
            max_age_days=self.max_age_days,
            review_after_days=self.review_after_days,
        )
        result = evaluate(profile, scan.current, self.rules)
        blocked = blocked or str(record.get("status") or "") != "active"
        state = analysis_state(scan=scan, research=research_summary, blocked=blocked)
        snapshot = build_snapshot(
            product=product,
            composition=record,
            profile=profile,
            evaluations=scan.current,
            result=result,
            rules=self.rules,
            created_at=now,
            user_id=user_id,
            analysis=state.as_dict(),
        )
        existing = self.store.get_snapshot(str(snapshot.get("snapshot_id") or ""))
        if existing is not None:
            saved, reused = existing, True
        else:
            saved, reused = self.store.save_snapshot(snapshot), False

        return BuildResult(
            snapshot=saved,
            pending_parameters=scan.needed,
            stale_parameters=scan.stale,
            reused=reused,
            analysis=state,
            scan=scan,
        )

    # -- research bookkeeping ----------------------------------------------
    def enqueue_research(self, composition_id: int, parameters: Sequence[str]) -> list[str]:
        created: list[str] = []
        for parameter_id in parameters:
            if self.store.enqueue_research(composition_id, parameter_id, self.method_version):
                created.append(parameter_id)
        return created

    def record_evaluation(self, composition_id: int, evaluation: ParameterEvaluation) -> dict:
        if evaluation.method_version != self.method_version:
            raise StoreError(
                "evaluation.method_version does not match the service method version"
            )
        saved = self.store.save_evaluation(composition_id, evaluation)
        return saved.as_dict()

    def verify_composition(
        self, composition_id: int, verified_at: str, source: str = ""
    ) -> dict:
        """Explicitly mark an INCI as checked (required before research)."""
        return self.store.verify_composition(composition_id, verified_at, source)

    # -- read ---------------------------------------------------------------
    def snapshot(self, snapshot_id: str) -> dict:
        stored = self.store.get_snapshot(snapshot_id)
        if stored is None:
            raise StoreError(f"snapshot not found: {snapshot_id}")
        if not verify_snapshot(stored):
            raise StoreError(f"snapshot integrity check failed: {snapshot_id}")
        return stored

    # -- diagnostics --------------------------------------------------------
    def relevance_fingerprint(self, profile: Mapping[str, Any] | None) -> dict:
        relevance = resolve_relevance(profile)
        return {
            "weights": {k: round(v, 6) for k, v in sorted(relevance.weights.items())},
            "parameters": [item.id for item in relevance.parameters],
            "notes": list(relevance.notes),
            "hash": sha256_of({k: round(v, 6) for k, v in sorted(relevance.weights.items())}),
        }
