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

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol, Sequence

from .contracts import ParameterEvaluation
from .evidence import Evidence


class StoreError(RuntimeError):
    """Raised on a storage contract violation."""


COMPOSITION_ACTIVE = "active"
COMPOSITION_UNVERIFIED = "unverified"
COMPOSITION_STATUSES = (COMPOSITION_ACTIVE, COMPOSITION_UNVERIFIED, "superseded")


def composition_status(composition: Mapping[str, Any]) -> str:
    """A composition is only ``active`` when it was explicitly verified.

    ``verified_at`` (or an explicit ``status``) must be supplied by the caller who
    imported/checked the INCI: an unknown formula is never trusted by default.
    """
    status = str(composition.get("status") or "").strip()
    if status:
        if status not in COMPOSITION_STATUSES:
            raise StoreError(f"unknown composition status: {status}")
        return status
    if str(composition.get("verified_at") or "").strip():
        return COMPOSITION_ACTIVE
    return COMPOSITION_UNVERIFIED


class EvaluationStore(Protocol):
    def get_composition(self, product_id: int, composition_hash: str) -> dict | None: ...
    def upsert_composition(self, composition: dict) -> dict: ...
    def verify_composition(self, composition_id: int, verified_at: str, source: str = "") -> dict: ...
    def current_evaluations(self, composition_id: int, method_version: str) -> list[ParameterEvaluation]: ...
    def save_evaluation(self, composition_id: int, evaluation: ParameterEvaluation) -> ParameterEvaluation: ...
    def evaluation_history(self, composition_id: int, parameter_id: str) -> list[ParameterEvaluation]: ...
    def save_snapshot(self, snapshot: dict) -> dict: ...
    def get_snapshot(self, snapshot_id: str) -> dict | None: ...
    def latest_snapshot(
        self,
        *,
        product_id: int,
        composition_hash: str,
        user_id: int | None,
        profile_fingerprint: Mapping[str, Any],
    ) -> dict | None: ...
    def enqueue_research(self, composition_id: int, parameter_id: str, method_version: str) -> bool: ...
    def pending_parameters(self, composition_id: int, method_version: str) -> list[str]: ...
    def save_evidence(self, composition_id: int, evidence: Sequence[Evidence]) -> list[int]: ...
    def evidence_for(self, composition_id: int, parameter_id: str) -> list[dict]: ...
    def evidence_for_many(
        self, composition_id: int, parameter_ids: Sequence[str]
    ) -> dict[str, list[dict]]: ...
    def evidence_ref(self, evidence_id: int) -> dict | None: ...
    def save_documents(self, composition_id: int, documents: Sequence[Any]) -> list[str]: ...
    def documents_for(self, composition_id: int) -> list[dict]: ...
    def document_for(self, composition_id: int, url: str) -> dict | None: ...
    def claim_job(
        self, worker_id: str, *, composition_id: int | None = None, lock_seconds: int = 120
    ) -> dict | None: ...
    def complete_job(
        self, job_id: int, *, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0
    ) -> None: ...
    def fail_job(
        self, job_id: int, error: str, *, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0
    ) -> None: ...
    def release_job(self, job_id: int) -> None: ...
    def job(self, job_id: int) -> dict | None: ...
    def jobs_for(self, composition_id: int, parameter_id: str, method_version: str) -> list[dict]: ...


class InMemoryStore:
    """Reference implementation used by tests (no persistence)."""

    def __init__(self) -> None:
        self._compositions: dict[int, dict] = {}
        self._next_composition_id = 1
        self._evaluations: list[tuple[int, ParameterEvaluation]] = []
        self._snapshots: dict[str, dict] = {}
        self._jobs: dict[int, dict] = {}
        self._next_job_id = 1
        self._evidence: list[dict] = []
        self._next_evidence_id = 1
        self._documents: dict[int, dict[str, dict]] = {}
        self._lock = threading.RLock()

    # -- compositions -------------------------------------------------------
    def upsert_composition(self, composition: dict) -> dict:
        product_id = int(composition["product_id"])
        composition_hash = str(composition["composition_hash"])
        status = composition_status(composition)
        for existing in self._compositions.values():
            if existing["product_id"] == product_id and existing["composition_hash"] == composition_hash:
                # mirror the Postgres upsert: enrich, never overwrite with empty values
                if composition.get("source"):
                    existing["source"] = composition["source"]
                if composition.get("verified_at"):
                    existing["verified_at"] = composition["verified_at"]
                # a verified composition never becomes unverified again
                if status == COMPOSITION_ACTIVE:
                    existing["status"] = COMPOSITION_ACTIVE
                elif not existing.get("status"):
                    existing["status"] = status
                return existing
        record = {
            "id": self._next_composition_id,
            "product_id": product_id,
            "composition_hash": composition_hash,
            "inci_raw": composition.get("inci_raw") or "",
            "source": composition.get("source") or "",
            "verified_at": composition.get("verified_at") or "",
            "status": status,
        }
        self._compositions[record["id"]] = record
        self._next_composition_id += 1
        return record

    def verify_composition(self, composition_id: int, verified_at: str, source: str = "") -> dict:
        """Mark a composition as verified: only then is it usable for research."""
        record = self.get_composition_by_id(composition_id)
        if record is None:
            raise StoreError(f"unknown composition_id: {composition_id}")
        if not str(verified_at or "").strip():
            raise StoreError("verified_at is required to verify a composition")
        record["verified_at"] = str(verified_at)
        if source:
            record["source"] = str(source)
        record["status"] = COMPOSITION_ACTIVE
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

    def latest_snapshot(
        self,
        *,
        product_id: int,
        composition_hash: str,
        user_id: int | None,
        profile_fingerprint: Mapping[str, Any],
    ) -> dict | None:
        candidates = [
            snapshot
            for snapshot in self._snapshots.values()
            if int((snapshot.get("product") or {}).get("id") or 0) == int(product_id)
            and str((snapshot.get("composition") or {}).get("hash") or "")
            == str(composition_hash)
            and snapshot.get("user_id") == user_id
            and snapshot.get("profile") == dict(profile_fingerprint)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: str(item.get("created_at") or ""))

    def snapshot_count(self) -> int:
        return len(self._snapshots)

    # -- evidence -----------------------------------------------------------
    def save_evidence(self, composition_id: int, evidence: Sequence[Evidence]) -> list[int]:
        if self.get_composition_by_id(composition_id) is None:
            raise StoreError(f"unknown composition_id: {composition_id}")
        ids: list[int] = []
        for item in evidence:
            existing = next(
                (
                    row
                    for row in self._evidence
                    if row["composition_id"] == composition_id
                    and row["parameter_id"] == item.parameter_id
                    and row["source"]["url"] == item.source.url
                    and row["quote"] == item.quote
                ),
                None,
            )
            if existing is not None:
                ids.append(existing["id"])
                continue
            record = {
                "id": self._next_evidence_id,
                "composition_id": composition_id,
                **item.as_dict(),
            }
            self._evidence.append(record)
            ids.append(record["id"])
            self._next_evidence_id += 1
        return ids

    def evidence_for(self, composition_id: int, parameter_id: str) -> list[dict]:
        return [
            dict(row)
            for row in self._evidence
            if row["composition_id"] == composition_id and row["parameter_id"] == parameter_id
        ]

    def evidence_for_many(
        self, composition_id: int, parameter_ids: Sequence[str]
    ) -> dict[str, list[dict]]:
        wanted = {str(item) for item in parameter_ids}
        grouped: dict[str, list[dict]] = {item: [] for item in wanted}
        for row in self._evidence:
            if row["composition_id"] != composition_id:
                continue
            parameter_id = str(row.get("parameter_id") or "")
            if parameter_id in wanted:
                grouped.setdefault(parameter_id, []).append(dict(row))
        return {key: value for key, value in grouped.items() if value}

    def evidence_ref(self, evidence_id: int) -> dict | None:
        record = next(
            (row for row in self._evidence if int(row["id"]) == int(evidence_id)), None
        )
        if record is None:
            return None
        composition = self.get_composition_by_id(record["composition_id"]) or {}
        return {
            **dict(record),
            "composition_hash": str(composition.get("composition_hash") or ""),
        }

    # -- shared product knowledge (documents) -------------------------------
    def save_documents(self, composition_id: int, documents: Sequence[Any]) -> list[str]:
        if self.get_composition_by_id(composition_id) is None:
            raise StoreError(f"unknown composition_id: {composition_id}")
        with self._lock:
            bucket = self._documents.setdefault(composition_id, {})
            stored: list[str] = []
            for document in documents:
                record = document.as_dict() if hasattr(document, "as_dict") else dict(document)
                url = str(record.get("url") or "")
                if not url:
                    raise StoreError("documents require a url")
                bucket[url] = record
                stored.append(url)
            return stored

    def documents_for(self, composition_id: int) -> list[dict]:
        return [dict(row) for row in self._documents.get(composition_id, {}).values()]

    def document_for(self, composition_id: int, url: str) -> dict | None:
        record = self._documents.get(composition_id, {}).get(str(url))
        return dict(record) if record else None

    # -- research jobs ------------------------------------------------------
    def enqueue_research(self, composition_id: int, parameter_id: str, method_version: str) -> bool:
        with self._lock:
            for job in self._jobs.values():
                if (
                    job["composition_id"] == composition_id
                    and job["parameter_id"] == parameter_id
                    and job["method_version"] == method_version
                    and job["status"] in ("pending", "processing")
                ):
                    return False
            job = {
                "id": self._next_job_id,
                "composition_id": composition_id,
                "parameter_id": parameter_id,
                "method_version": method_version,
                "status": "pending",
                "attempts": 0,
                "worker_id": "",
                "locked_until": None,
                "last_error": "",
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
            }
            self._jobs[job["id"]] = job
            self._next_job_id += 1
            return True

    def claim_job(
        self, worker_id: str, *, composition_id: int | None = None, lock_seconds: int = 120
    ) -> dict | None:
        with self._lock:
            now = datetime.now(timezone.utc)
            for job in self._jobs.values():
                if job["status"] != "pending":
                    continue
                if composition_id is not None and job["composition_id"] != composition_id:
                    continue
                job["status"] = "processing"
                job["worker_id"] = worker_id
                job["attempts"] += 1
                job["locked_until"] = (now + timedelta(seconds=lock_seconds)).isoformat()
                return dict(job)
            return None

    def complete_job(
        self, job_id: int, *, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            raise StoreError(f"unknown job: {job_id}")
        job.update(
            status="completed",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            locked_until=None,
        )

    def fail_job(
        self, job_id: int, error: str, *, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            raise StoreError(f"unknown job: {job_id}")
        job.update(
            status="failed",
            last_error=str(error)[:500],
            locked_until=None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )

    def release_job(self, job_id: int) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            raise StoreError(f"unknown job: {job_id}")
        job.update(status="pending", worker_id="", locked_until=None)

    def job(self, job_id: int) -> dict | None:
        job = self._jobs.get(job_id)
        return dict(job) if job else None

    def jobs_for(self, composition_id: int, parameter_id: str, method_version: str) -> list[dict]:
        return [
            dict(job)
            for job in self._jobs.values()
            if job["composition_id"] == composition_id
            and job["parameter_id"] == parameter_id
            and job["method_version"] == method_version
        ]

    def pending_parameters(self, composition_id: int, method_version: str) -> list[str]:
        return sorted(
            {
                job["parameter_id"]
                for job in self._jobs.values()
                if job["composition_id"] == composition_id
                and job["method_version"] == method_version
                and job["status"] == "pending"
            }
        )

    def job_count(self) -> int:
        return len(self._jobs)
