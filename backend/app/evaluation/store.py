"""Storage port for evaluation v2.

The engine and service depend on this protocol only, so they can be tested
without a database. Two implementations are planned:

  * InMemoryStore  — used by unit tests and local experiments (this module);
  * PostgresStore  — Supabase implementation, added after the migration is
                     approved and tested on a staging schema.

Contract notes:
  * exactly one *current* evaluation per (composition, parameter, method);
    replacing an evaluation appends a new row and marks the old one superseded;
  * snapshots are append-only and idempotent by snapshot_id;
  * research jobs are deduplicated by an active unique key.
"""
from __future__ import annotations

from typing import Protocol

from .contracts import ParameterEvaluation


class StoreError(RuntimeError):
    """Raised on a storage contract violation."""


class EvaluationStore(Protocol):
    def get_composition(self, product_id: int, composition_hash: str) -> dict | None: ...
    def upsert_composition(self, composition: dict) -> dict: ...
    def current_evaluations(self, composition_id: int, method_version: str) -> list[ParameterEvaluation]: ...
    def save_evaluation(self, composition_id: int, evaluation: ParameterEvaluation) -> ParameterEvaluation: ...
    def evaluation_history(self, composition_id: int, parameter_id: str) -> list[ParameterEvaluation]: ...
    def save_snapshot(self, snapshot: dict) -> dict: ...
    def get_snapshot(self, snapshot_id: str) -> dict | None: ...
    def enqueue_research(self, composition_id: int, parameter_id: str, method_version: str) -> bool: ...


class InMemoryStore:
    """Reference implementation used by tests (no persistence)."""

    def __init__(self) -> None:
        self._compositions: dict[int, dict] = {}
        self._next_composition_id = 1
        self._evaluations: list[tuple[int, ParameterEvaluation]] = []
        self._snapshots: dict[str, dict] = {}
        self._jobs: set[tuple[int, str, str]] = set()

    # -- compositions -------------------------------------------------------
    def upsert_composition(self, composition: dict) -> dict:
        product_id = int(composition["product_id"])
        composition_hash = str(composition["composition_hash"])
        for existing in self._compositions.values():
            if existing["product_id"] == product_id and existing["composition_hash"] == composition_hash:
                return existing
        record = {
            "id": self._next_composition_id,
            "product_id": product_id,
            "composition_hash": composition_hash,
            "inci_raw": composition.get("inci_raw") or "",
            "source": composition.get("source") or "",
            "verified_at": composition.get("verified_at") or "",
        }
        self._compositions[record["id"]] = record
        self._next_composition_id += 1
        return record

    def get_composition(self, product_id: int, composition_hash: str) -> dict | None:
        for record in self._compositions.values():
            if record["product_id"] == product_id and record["composition_hash"] == composition_hash:
                return record
        return None

    # -- evaluations --------------------------------------------------------
    def current_evaluations(self, composition_id: int, method_version: str) -> list[ParameterEvaluation]:
        current: dict[str, ParameterEvaluation] = {}
        for comp_id, evaluation in self._evaluations:
            if comp_id != composition_id or evaluation.method_version != method_version:
                continue
            current[evaluation.parameter_id] = evaluation  # later rows win (append-only history)
        return list(current.values())

    def save_evaluation(self, composition_id: int, evaluation: ParameterEvaluation) -> ParameterEvaluation:
        if self.get_composition_by_id(composition_id) is None:
            raise StoreError(f"unknown composition_id: {composition_id}")
        previous = [
            item
            for comp_id, item in self._evaluations
            if comp_id == composition_id
            and item.parameter_id == evaluation.parameter_id
            and item.method_version == evaluation.method_version
        ]
        if previous and previous[-1] == evaluation:
            return evaluation  # idempotent write, nothing to append
        self._evaluations.append((composition_id, evaluation))
        return evaluation

    def evaluation_history(self, composition_id: int, parameter_id: str) -> list[ParameterEvaluation]:
        return [
            item
            for comp_id, item in self._evaluations
            if comp_id == composition_id and item.parameter_id == parameter_id
        ]

    def get_composition_by_id(self, composition_id: int) -> dict | None:
        return self._compositions.get(composition_id)

    # -- snapshots ----------------------------------------------------------
    def save_snapshot(self, snapshot: dict) -> dict:
        snapshot_id = str(snapshot.get("snapshot_id") or "")
        if not snapshot_id:
            raise StoreError("snapshot_id is required")
        stored = self._snapshots.get(snapshot_id)
        if stored is not None:
            return stored
        self._snapshots[snapshot_id] = dict(snapshot)
        return self._snapshots[snapshot_id]

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        return self._snapshots.get(snapshot_id)

    def snapshot_count(self) -> int:
        return len(self._snapshots)

    # -- research -----------------------------------------------------------
    def enqueue_research(self, composition_id: int, parameter_id: str, method_version: str) -> bool:
        key = (composition_id, parameter_id, method_version)
        if key in self._jobs:
            return False
        self._jobs.add(key)
        return True

    def job_count(self) -> int:
        return len(self._jobs)
