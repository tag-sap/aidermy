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

import json
from contextlib import closing
from typing import Any, Callable, Iterable, Mapping

from .contracts import ParameterEvaluation, RuleSet, sha256_of
from .parameters import PARAMETERS
from .store import StoreError

SCHEMA = "evaluation"

_COMPOSITION_FIELDS = "id, product_id, composition_hash, inci_raw, source, verified_at"


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


def evaluation_to_params(evaluation: ParameterEvaluation) -> tuple:
    return (
        evaluation.parameter_id,
        evaluation.status,
        evaluation.value,
        evaluation.confidence,
        evaluation.rationale,
        _as_json(list(evaluation.limitations)),
        _as_json(list(evaluation.evidence_ids)),
        evaluation.composition_hash,  # used only by the input hash, not stored here
        evaluation.method_version,
        evaluation.valid_until,
    )


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
        row = self._fetchone(
            f"""
            insert into {self._table('product_compositions')}
                (product_id, composition_hash, inci_raw, source, verified_at)
            values (%s, %s, %s, %s, %s)
            on conflict (product_id, composition_hash) do update
                set source = coalesce(nullif(excluded.source, ''),
                                      {self._table('product_compositions')}.source),
                    verified_at = coalesce(excluded.verified_at,
                                           {self._table('product_compositions')}.verified_at)
            returning {_COMPOSITION_FIELDS}
            """,
            (
                int(composition["product_id"]),
                str(composition["composition_hash"]),
                composition.get("inci_raw") or "",
                composition.get("source") or "",
                composition.get("verified_at") or None,
            ),
        )
        if row is None:
            raise StoreError("composition upsert returned no row")
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
                    if previous is not None:
                        cur.execute(
                            f"update {self._table('parameter_evaluations')} "
                            "set superseded_by = %s where id = %s",
                            (inserted["id"], previous["id"]),
                        )
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
                rule_version, engine_version, engine_input_hash, parameters,
                total, verdict, completeness, limitations
            ) values (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb
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
                   s.parameters, s.total, s.verdict, s.completeness,
                   s.limitations, s.created_at,
                   c.composition_hash, c.source, c.verified_at, r.rules_hash
            from {self._table('snapshots')} s
            join {self._table('product_compositions')} c on c.id = s.composition_id
            join {self._table('rule_versions')} r on r.version = s.rule_version
            where s.snapshot_id = %s
            """,
            (snapshot_id,),
        )
        if not row:
            return None
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
        row = self._fetchone(
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


