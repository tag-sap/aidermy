"""PostgreSQL/Supabase implementation of the evaluation storage port.

Code is complete but NOT executed against a database yet: the `evaluation`
schema migration is still pending approval. Every SQL statement is parameterized;
writes are transactional; identity/idempotency rules live in unique indexes
(see backend/migrations/20261023_evaluation_v2.sql).

Usage (after the migration is applied):
    store = PostgresStore()
    store.seed_rule(get_rules())          # register the rule version (FK target)
    store.seed_registry(METHOD_VERSION)   # mirror the parameter registry
    service = EvaluationService(store)
"""
from __future__ import annotations

import hashlib
import json
from contextlib import closing
from typing import Any, Callable, Iterable, Mapping, Sequence

from .contracts import ParameterEvaluation, RuleSet, sha256_of
from .evidence import Evidence
from .parameters import PARAMETERS
from .store import StoreError, composition_status

SCHEMA = "evaluation"

_COMPOSITION_FIELDS = "id, product_id, composition_hash, inci_raw, source, verified_at, status"


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        return parsed if isinstance(parsed, list) else [parsed]
    return list(value)


def row_to_evaluation(row: Mapping[str, Any]) -> ParameterEvaluation:
    """Map a joined evaluation row to the domain object."""
    limitations = tuple(str(item) for item in _as_list(row.get("limitations")))
    evidence = tuple(str(item) for item in _as_list(row.get("evidence_ids")))
    value = row.get("value")
    return ParameterEvaluation(
        parameter_id=str(row["parameter_id"]),
        status=str(row["status"]),
        value=float(value) if value is not None else None,
        confidence=(
            float(row["confidence"]) if row.get("confidence") is not None else None
        ),
        composition_hash=str(row.get("composition_hash") or ""),
        method_version=str(row["method_version"]),
        evidence_ids=evidence,
        rationale=str(row.get("rationale") or ""),
        limitations=limitations,
        evaluated_at=str(row.get("evaluated_at") or ""),
        valid_until=str(row["valid_until"]) if row.get("valid_until") else None,
    )


def _advisory_key(*parts: Any) -> int:
    """Stable signed 64-bit key for pg_advisory_xact_lock."""
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)


class PostgresStore:
    """Storage adapter over the `evaluation` schema."""

    def __init__(
        self,
        connection_factory: Callable[[], Any] | None = None,
        *,
        schema: str = SCHEMA,
    ) -> None:
        if connection_factory is None:
            from ..postgres_connection import get_postgres_connection

            connection_factory = get_postgres_connection
        self._connect = connection_factory
        self.schema = schema

    # -- helpers ------------------------------------------------------------
    def _table(self, name: str) -> str:
        return f"{self.schema}.{name}"

    def _fetchone(self, sql: str, params: Iterable[Any] = ()) -> Mapping[str, Any] | None:
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                return cur.fetchone()

    def _fetchone_write(self, sql: str, params: Iterable[Any] = ()) -> Mapping[str, Any] | None:
        """Same as _fetchone but commits: required for INSERT/UPDATE ... RETURNING."""
        with closing(self._connect()) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))
                    return cur.fetchone()

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with closing(self._connect()) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))

    # -- compositions -------------------------------------------------------
    def get_composition(self, product_id: int, composition_hash: str) -> dict | None:
        row = self._fetchone(
            f"select {_COMPOSITION_FIELDS} from {self._table('product_compositions')} "
            "where product_id = %s and composition_hash = %s",
            (product_id, composition_hash),
        )
        return dict(row) if row else None

    def upsert_composition(self, composition: Mapping[str, Any]) -> dict:
        status = composition_status(composition)
        row = self._fetchone_write(
            f"""
            insert into {self._table('product_compositions')}
                (product_id, composition_hash, inci_raw, source, verified_at, status)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (product_id, composition_hash) do update
                set source = coalesce(nullif(excluded.source, ''),
                                      {self._table('product_compositions')}.source),
                    verified_at = coalesce(excluded.verified_at,
                                           {self._table('product_compositions')}.verified_at),
                    status = case
                        when excluded.status = 'active' then 'active'
                        when {self._table('product_compositions')}.status = 'active' then 'active'
                        else excluded.status
                    end
            returning {_COMPOSITION_FIELDS}
            """,
            (
                int(composition["product_id"]),
                str(composition["composition_hash"]),
                composition.get("inci_raw") or "",
                composition.get("source") or "",
                composition.get("verified_at") or None,
                status,
            ),
        )
        if row is None:
            raise StoreError("composition upsert returned no row")
        return dict(row)

    def verify_composition(
        self, composition_id: int, verified_at: str, source: str = ""
    ) -> dict:
        """Mark a composition as verified: only then is it usable for research."""
        if not str(verified_at or "").strip():
            raise StoreError("verified_at is required to verify a composition")
        row = self._fetchone_write(
            f"""
            update {self._table('product_compositions')}
               set status = 'active',
                   verified_at = %s,
                   source = coalesce(nullif(%s, ''), source)
             where id = %s
            returning {_COMPOSITION_FIELDS}
            """,
            (verified_at, source or "", int(composition_id)),
        )
        if row is None:
            raise StoreError(f"unknown composition_id: {composition_id}")
        return dict(row)

    # -- evaluations --------------------------------------------------------
    def current_evaluations(
        self, composition_id: int, method_version: str
    ) -> list[ParameterEvaluation]:
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select e.id, e.parameter_id, e.status, e.value, e.confidence,
                           e.rationale, e.limitations, e.evidence_ids,
                           e.evaluated_at, e.valid_until, e.method_version,
                           c.composition_hash
                    from {self._table('parameter_evaluations')} e
                    join {self._table('product_compositions')} c on c.id = e.composition_id
                    where e.composition_id = %s and e.method_version = %s
                      and e.superseded_by is null
                    order by e.parameter_id
                    """,
                    (composition_id, method_version),
                )
                return [row_to_evaluation(row) for row in cur.fetchall()]

    def save_evaluation(
        self, composition_id: int, evaluation: ParameterEvaluation
    ) -> ParameterEvaluation:
        with closing(self._connect()) as conn:
            with conn:
                with conn.cursor() as cur:
                    # Serialise concurrent writers for the same natural key:
                    # SELECT ... FOR UPDATE cannot lock a row that does not exist yet,
                    # so two first-time inserts would race on the partial unique index.
                    cur.execute(
                        "select pg_advisory_xact_lock(%s)",
                        (
                            _advisory_key(
                                composition_id,
                                evaluation.parameter_id,
                                evaluation.method_version,
                            ),
                        ),
                    )
                    cur.execute(
                        f"""
                        select id from {self._table('parameter_evaluations')}
                        where composition_id = %s and parameter_id = %s
                          and method_version = %s and superseded_by is null
                        for update
                        """,
                        (composition_id, evaluation.parameter_id, evaluation.method_version),
                    )
                    previous = cur.fetchone()
                    if previous is not None:
                        # Mark the old row superseded BEFORE inserting the new one:
                        # the partial unique index forbids two current rows even
                        # inside one transaction. The FK is deferred, so pointing
                        # to the id that is inserted next is checked at COMMIT.
                        cur.execute(
                            "select nextval(pg_get_serial_sequence(%s, 'id')) as id",
                            (f"{self.schema}.parameter_evaluations",),
                        )
                        new_id = int(cur.fetchone()["id"])
                        cur.execute(
                            f"update {self._table('parameter_evaluations')} "
                            "set superseded_by = %s where id = %s",
                            (new_id, previous["id"]),
                        )
                        cur.execute(
                            f"""
                            insert into {self._table('parameter_evaluations')}
                                (id, composition_id, parameter_id, status, value, confidence,
                                 rationale, limitations, evidence_ids, input_hash,
                                 method_version, valid_until)
                            values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                            returning id
                            """,
                            (
                                new_id,
                                composition_id,
                                evaluation.parameter_id,
                                evaluation.status,
                                evaluation.value,
                                evaluation.confidence,
                                evaluation.rationale,
                                _as_json(list(evaluation.limitations)),
                                _as_json(list(evaluation.evidence_ids)),
                                sha256_of(evaluation.as_dict()),
                                evaluation.method_version,
                                evaluation.valid_until,
                            ),
                        )
                        inserted = cur.fetchone()
                        if inserted is None:
                            raise StoreError("evaluation insert returned no id")
                        return evaluation
                    cur.execute(
                        f"""
                        insert into {self._table('parameter_evaluations')}
                            (composition_id, parameter_id, status, value, confidence,
                             rationale, limitations, evidence_ids, input_hash,
                             method_version, valid_until)
                        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                        returning id
                        """,
                        (
                            composition_id,
                            evaluation.parameter_id,
                            evaluation.status,
                            evaluation.value,
                            evaluation.confidence,
                            evaluation.rationale,
                            _as_json(list(evaluation.limitations)),
                            _as_json(list(evaluation.evidence_ids)),
                            sha256_of(evaluation.as_dict()),
                            evaluation.method_version,
                            evaluation.valid_until,
                        ),
                    )
                    inserted = cur.fetchone()
                    if inserted is None:
                        raise StoreError("evaluation insert returned no id")
        return evaluation

    def evaluation_history(
        self, composition_id: int, parameter_id: str
    ) -> list[ParameterEvaluation]:
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select e.id, e.parameter_id, e.status, e.value, e.confidence,
                           e.rationale, e.limitations, e.evidence_ids,
                           e.evaluated_at, e.valid_until, e.method_version,
                           c.composition_hash
                    from {self._table('parameter_evaluations')} e
                    join {self._table('product_compositions')} c on c.id = e.composition_id
                    where e.composition_id = %s and e.parameter_id = %s
                    order by e.id
                    """,
                    (composition_id, parameter_id),
                )
                return [row_to_evaluation(row) for row in cur.fetchall()]

    # -- evidence -----------------------------------------------------------
    def save_evidence(self, composition_id: int, evidence: Sequence[Evidence]) -> list[int]:
        ids: list[int] = []
        for item in evidence:
            source = item.source
            source_row = self._fetchone_write(
                f"""
                insert into {self._table('sources')}
                    (url, title, publisher, source_type, retrieved_at, content_hash)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (url, content_hash) do update
                    set title = excluded.title,
                        publisher = excluded.publisher,
                        source_type = excluded.source_type,
                        retrieved_at = coalesce(excluded.retrieved_at,
                                                {self._table('sources')}.retrieved_at)
                returning id
                """,
                (
                    source.url,
                    source.title,
                    source.publisher,
                    source.source_type,
                    source.retrieved_at or None,
                    source.content_hash,
                ),
            )
            if source_row is None:
                raise StoreError("source upsert returned no id")
            evidence_row = self._fetchone_write(
                f"""
                insert into {self._table('evidence')}
                    (source_id, composition_id, parameter_id, claim, quote, direction,
                     strength, confidence, extraction_method, verification,
                     rejection_reason, retrieved_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (composition_id, parameter_id, source_id, md5(quote)) do update
                    set verification = excluded.verification,
                        rejection_reason = excluded.rejection_reason,
                        confidence = excluded.confidence
                returning id
                """,
                (
                    source_row["id"],
                    composition_id,
                    item.parameter_id,
                    item.claim,
                    item.quote,
                    item.direction,
                    item.strength,
                    item.confidence,
                    item.extraction_method,
                    item.verification,
                    item.rejection_reason,
                    item.retrieved_at or None,
                ),
            )
            if evidence_row is None:
                raise StoreError("evidence insert returned no id")
            ids.append(int(evidence_row["id"]))
        return ids

    def evidence_for(self, composition_id: int, parameter_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select e.id, e.composition_id, e.parameter_id, e.claim, e.quote,
                           e.direction, e.strength, e.confidence, e.extraction_method,
                           e.verification, e.rejection_reason, e.retrieved_at,
                           s.url, s.title, s.publisher, s.source_type,
                           s.retrieved_at as source_retrieved_at, s.content_hash
                    from {self._table('evidence')} e
                    join {self._table('sources')} s on s.id = e.source_id
                    where e.composition_id = %s and e.parameter_id = %s
                    order by e.id
                    """,
                    (composition_id, parameter_id),
                )
                rows = cur.fetchall()
        return [
            {
                "id": row["id"],
                "composition_id": row["composition_id"],
                "parameter_id": row["parameter_id"],
                "claim": row["claim"],
                "quote": row["quote"],
                "direction": row["direction"],
                "strength": row["strength"],
                "confidence": float(row["confidence"]),
                "verification": row["verification"],
                "rejection_reason": row["rejection_reason"],
                "extraction_method": row["extraction_method"],
                "retrieved_at": str(row["retrieved_at"] or ""),
                "source": {
                    "url": row["url"],
                    "title": row["title"],
                    "publisher": row["publisher"],
                    "source_type": row["source_type"],
                    "retrieved_at": str(row["source_retrieved_at"] or ""),
                    "content_hash": row["content_hash"],
                },
            }
            for row in rows
        ]

    # -- research job claiming ---------------------------------------------
    def claim_job(
        self, worker_id: str, *, composition_id: int | None = None, lock_seconds: int = 120
    ) -> dict | None:
        row = self._fetchone_write(
            f"""
            with picked as (
                select id from {self._table('research_jobs')}
                where status = 'pending'
                  and (%s is null or composition_id = %s)
                order by id
                for update skip locked
                limit 1
            )
            update {self._table('research_jobs')} j
               set status = 'processing',
                   worker_id = %s,
                   locked_until = now() + make_interval(secs => %s),
                   attempts = j.attempts + 1,
                   updated_at = now()
              from picked
             where j.id = picked.id
            returning j.id, j.composition_id, j.parameter_id, j.method_version,
                      j.status, j.attempts, j.worker_id, j.locked_until,
                      j.tokens_in, j.tokens_out, j.cost_usd, j.last_error
            """,
            (composition_id, composition_id, worker_id, lock_seconds),
        )
        return dict(row) if row else None

    def complete_job(
        self, job_id: int, *, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0
    ) -> None:
        self._execute(
            f"""
            update {self._table('research_jobs')}
               set status = 'completed', tokens_in = %s, tokens_out = %s,
                   cost_usd = %s, locked_until = null, updated_at = now()
             where id = %s
            """,
            (tokens_in, tokens_out, cost_usd, job_id),
        )

    def fail_job(
        self, job_id: int, error: str, *, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0
    ) -> None:
        self._execute(
            f"""
            update {self._table('research_jobs')}
               set status = 'failed', last_error = %s, locked_until = null,
                   tokens_in = %s, tokens_out = %s, cost_usd = %s, updated_at = now()
             where id = %s
            """,
            (str(error)[:500], tokens_in, tokens_out, cost_usd, job_id),
        )

    def release_job(self, job_id: int) -> None:
        self._execute(
            f"""
            update {self._table('research_jobs')}
               set status = 'pending', worker_id = '', locked_until = null,
                   updated_at = now()
             where id = %s
            """,
            (job_id,),
        )

    def job(self, job_id: int) -> dict | None:
        row = self._fetchone(
            f"""
            select id, composition_id, parameter_id, method_version, status, attempts,
                   worker_id, locked_until, tokens_in, tokens_out, cost_usd, last_error
            from {self._table('research_jobs')} where id = %s
            """,
            (job_id,),
        )
        return dict(row) if row else None

    def jobs_for(self, composition_id: int, parameter_id: str, method_version: str) -> list[dict]:
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select id, composition_id, parameter_id, method_version, status,
                           attempts, worker_id, locked_until, tokens_in, tokens_out,
                           cost_usd, last_error
                    from {self._table('research_jobs')}
                    where composition_id = %s and parameter_id = %s and method_version = %s
                    order by id
                    """,
                    (composition_id, parameter_id, method_version),
                )
                return [dict(row) for row in cur.fetchall()]

    def pending_parameters(self, composition_id: int, method_version: str) -> list[str]:
        with closing(self._connect()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select distinct parameter_id
                    from {self._table('research_jobs')}
                    where composition_id = %s and method_version = %s and status = 'pending'
                    order by parameter_id
                    """,
                    (composition_id, method_version),
                )
                return [str(row["parameter_id"]) for row in cur.fetchall()]

    # -- snapshots ----------------------------------------------------------
    def save_snapshot(self, snapshot: Mapping[str, Any]) -> dict:
        snapshot_id = str(snapshot.get("snapshot_id") or "")
        if not snapshot_id:
            raise StoreError("snapshot_id is required")

        existing = self.get_snapshot(snapshot_id)
        if existing is not None:
            return existing

        product = snapshot.get("product") or {}
        composition = snapshot.get("composition") or {}
        product_id = product.get("id")
        composition_hash = str(composition.get("hash") or "")
        if product_id is None or not composition_hash:
            raise StoreError("snapshot requires product.id and composition.hash")

        record = self.get_composition(int(product_id), composition_hash)
        if record is None:
            raise StoreError(
                "composition is not registered in evaluation.product_compositions; "
                "call ensure_composition first"
            )

        rule_version = str(snapshot.get("rule_version") or "")
        if not self._fetchone(
            f"select 1 as ok from {self._table('rule_versions')} where version = %s",
            (rule_version,),
        ):
            raise StoreError(
                f"rule version {rule_version} is not registered; call seed_rule() first"
            )

        self._execute(
            f"""
            insert into {self._table('snapshots')} (
                snapshot_id, snapshot_hash, schema_version, user_id,
                product_id, product_name, composition_id, profile_fingerprint,
                rule_version, engine_version, engine_input_hash, document, parameters,
                total, verdict, completeness, limitations
            ) values (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s::jsonb
            )
            on conflict (snapshot_id) do nothing
            """,
            (
                snapshot_id,
                str(snapshot.get("snapshot_hash") or ""),
                str(snapshot.get("schema_version") or ""),
                snapshot.get("user_id"),
                int(product_id),
                str(product.get("name") or ""),
                int(record["id"]),
                _as_json(snapshot.get("profile") or {}),
                rule_version,
                str(snapshot.get("engine_version") or ""),
                str(snapshot.get("engine_input_hash") or ""),
                _as_json(dict(snapshot)),
                _as_json(snapshot.get("parameters") or []),
                snapshot.get("total"),
                snapshot.get("verdict"),
                snapshot.get("completeness"),
                _as_json(snapshot.get("limitations") or []),
            ),
        )
        stored = self.get_snapshot(snapshot_id)
        if stored is None:
            raise StoreError("snapshot was not persisted")
        return stored

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        row = self._fetchone(
            f"""
            select s.snapshot_id, s.snapshot_hash, s.schema_version, s.user_id,
                   s.product_id, s.product_name, s.profile_fingerprint,
                   s.rule_version, s.engine_version, s.engine_input_hash,
                   s.document, s.parameters, s.total, s.verdict, s.completeness,
                   s.limitations, s.created_at,
                   c.composition_hash, c.source, c.verified_at, c.status, r.rules_hash
            from {self._table('snapshots')} s
            join {self._table('product_compositions')} c on c.id = s.composition_id
            join {self._table('rule_versions')} r on r.version = s.rule_version
            where s.snapshot_id = %s
            """,
            (snapshot_id,),
        )
        if not row:
            return None
        document = row.get("document")
        if isinstance(document, Mapping) and document.get("snapshot_hash"):
            # Canonical copy: byte-for-byte identical to what was hashed at build
            # time, so verify_snapshot() stays valid after a database round-trip.
            return dict(document)
        return {
            "schema_version": row["schema_version"],
            "engine_version": row["engine_version"],
            "rule_version": row["rule_version"],
            "rules_hash": row["rules_hash"],
            "engine_input_hash": row["engine_input_hash"],
            "product": {"id": row["product_id"], "name": row["product_name"]},
            "composition": {
                "hash": row["composition_hash"],
                "source": row["source"] or "",
                "verified_at": str(row["verified_at"] or ""),
                "status": row.get("status") or "unverified",
            },
            "profile": row["profile_fingerprint"] or {},
            "parameters": _as_list(row["parameters"]),
            "total": row["total"],
            "verdict": row["verdict"],
            "completeness": float(row["completeness"]),
            "limitations": _as_list(row["limitations"]),
            "created_at": str(row["created_at"]),
            "snapshot_hash": row["snapshot_hash"],
            "snapshot_id": row["snapshot_id"],
        }

    # -- research jobs ------------------------------------------------------
    def enqueue_research(
        self, composition_id: int, parameter_id: str, method_version: str
    ) -> bool:
        row = self._fetchone_write(
            f"""
            insert into {self._table('research_jobs')}
                (composition_id, parameter_id, method_version)
            values (%s, %s, %s)
            on conflict do nothing
            returning id
            """,
            (composition_id, parameter_id, method_version),
        )
        return row is not None

    # -- seeds --------------------------------------------------------------
    def seed_rule(self, rules: RuleSet) -> str:
        """Register (or refresh) a rule version so snapshots can reference it."""
        self._execute(
            f"""
            insert into {self._table('rule_versions')}
                (version, aggregation, rules, rules_hash, calibrated, status, notes)
            values (%s, %s, %s::jsonb, %s, %s, %s, %s)
            on conflict (version) do update
                set rules = excluded.rules,
                    rules_hash = excluded.rules_hash,
                    calibrated = excluded.calibrated
            """,
            (
                rules.version,
                rules.aggregation,
                _as_json(rules.as_dict()),
                rules.hash,
                rules.calibrated,
                "draft" if not rules.calibrated else "approved",
                "seeded from code",
            ),
        )
        return rules.version

    def seed_registry(self, method_version: str) -> int:
        """Mirror the code parameter registry into the database for audit."""
        count = 0
        for parameter in PARAMETERS.values():
            self._execute(
                f"""
                insert into {self._table('parameter_registry')}
                    (parameter_id, method_version, label, definition, anchors, direction)
                values (%s, %s, %s, %s, %s::jsonb, %s)
                on conflict (parameter_id, method_version) do update
                    set label = excluded.label,
                        definition = excluded.definition,
                        anchors = excluded.anchors,
                        direction = excluded.direction
                """,
                (
                    parameter.id,
                    method_version,
                    parameter.label,
                    parameter.definition,
                    _as_json([[int(v), t] for v, t in parameter.anchors]),
                    parameter.direction,
                ),
            )
            count += 1
        return count


