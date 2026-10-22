"""Integration tests for evaluation v2 against a REAL PostgreSQL.

Safety contract:
  * runs only when ``EVALUATION_TEST_DSN`` is set;
  * refuses any host except localhost and any database whose name does not
    start with ``aidermy_eval_test``;
  * explicitly refuses known production hosts (Supabase / the Aidermy server);
  * recreates the ``evaluation`` schema from the migration file on every run,
    so the test proves the current migration, not a leftover schema.

Nothing here is imported by the application; production is never touched.
"""
from __future__ import annotations

import os
import threading
import unittest
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg import conninfo
from psycopg.rows import dict_row

from app.evaluation import (
    ParameterEvaluation,
    build_snapshot,
    evaluate,
    get_rules,
    verify_snapshot,
)
from app.evaluation.postgres_store import PostgresStore
from app.evaluation.service import DEFAULT_METHOD_VERSION, EvaluationService
from app.evaluation.store import StoreError

DSN_ENV = "EVALUATION_TEST_DSN"
TEST_DB_PREFIX = "aidermy_eval_test"
FORBIDDEN_HOST_PARTS = ("supabase.co", "supabase.com", "138.124.231.42", "eclectusgames.ru")
MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "migrations",
    "20261023_evaluation_v2.sql",
)
COMPOSITION = "e" * 64
OTHER_COMPOSITION = "f" * 64
PRODUCT = {"id": 7, "name": "Integration Serum"}
PROFILE = {"skin_type": "dry"}

SUPABASE_STUB = """
create schema if not exists auth;
create or replace function auth.uid() returns text
language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::text;
$$;
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end $$;
alter role service_role bypassrls;
"""


def _guard_dsn() -> str:
    dsn = os.environ.get(DSN_ENV, "").strip()
    if not dsn:
        raise unittest.SkipTest(f"{DSN_ENV} is not set — integration tests skipped")
    info = conninfo.conninfo_to_dict(dsn)
    host = str(info.get("host") or "")
    dbname = str(info.get("dbname") or "")
    for part in FORBIDDEN_HOST_PARTS:
        if part in host:
            raise RuntimeError(f"refusing production host: {host}")
    if host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError(f"only local test databases are allowed, got host={host!r}")
    if not dbname.startswith(TEST_DB_PREFIX):
        raise RuntimeError(f"only {TEST_DB_PREFIX}* databases are allowed, got {dbname!r}")
    return dsn


DSN = _guard_dsn()


def connect(**kwargs):
    return psycopg.connect(DSN, row_factory=dict_row, **kwargs)


def make_store() -> PostgresStore:
    return PostgresStore(lambda: connect())


def ev(parameter_id: str, value: float | None, status: str = "evaluated", **kwargs):
    return ParameterEvaluation(
        parameter_id=parameter_id,
        status=status,
        value=value,
        composition_hash=kwargs.pop("composition_hash", COMPOSITION),
        method_version=kwargs.pop("method_version", DEFAULT_METHOD_VERSION),
        **kwargs,
    )


def sql(statement: str, params: tuple = ()) -> list:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params)
            if cur.description:
                return cur.fetchall()
            conn.commit()
            return []


class SchemaTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SUPABASE_STUB)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute("drop schema if exists evaluation cascade")
            conn.commit()
            with open(MIGRATION_PATH, encoding="utf-8") as fh:
                migration = fh.read()
            with conn.cursor() as cur:
                cur.execute(migration)
            conn.commit()

    def setUp(self):
        sql(
            "truncate evaluation.snapshots, evaluation.parameter_evaluations, "
            "evaluation.research_jobs, evaluation.product_compositions "
            "restart identity cascade"
        )
        self.store = make_store()
        self.store.seed_rule(get_rules())

    def make_composition(self, store=None, comp_hash: str = COMPOSITION) -> dict:
        return (store or self.store).upsert_composition(
            {
                "product_id": PRODUCT["id"],
                "composition_hash": comp_hash,
                "inci_raw": "Aqua, Glycerin",
                "source": "integration-test",
                "verified_at": "2026-10-23T00:00:00+00:00",
            }
        )


class FullCycleTests(SchemaTestBase):
    def test_full_cycle_build_read_verify(self):
        composition = self.make_composition()
        self.store.save_evaluation(composition["id"], ev("hydration", 80))
        self.store.save_evaluation(composition["id"], ev("barrier", 60))

        service = EvaluationService(self.store)
        built = service.build(
            product=PRODUCT, composition=composition, profile=PROFILE, user_id=1
        )
        snapshot = built.snapshot
        self.assertEqual(snapshot["total"], 70)
        self.assertAlmostEqual(snapshot["completeness"], 1.0, places=6)
        self.assertEqual(built.pending_parameters, ())
        self.assertTrue(verify_snapshot(snapshot))

        read_back = service.snapshot(snapshot["snapshot_id"])
        self.assertEqual(read_back["snapshot_id"], snapshot["snapshot_id"])
        self.assertTrue(verify_snapshot(read_back))
        self.assertEqual(read_back["product"]["name"], PRODUCT["name"])
        self.assertEqual(read_back["composition"]["hash"], COMPOSITION)

    def test_repeated_build_reuses_one_snapshot(self):
        composition = self.make_composition()
        self.store.save_evaluation(composition["id"], ev("hydration", 80))
        self.store.save_evaluation(composition["id"], ev("barrier", 60))
        service = EvaluationService(self.store)

        first = service.build(product=PRODUCT, composition=composition, profile=PROFILE, user_id=1)
        second = service.build(product=PRODUCT, composition=composition, profile=PROFILE, user_id=1)

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.snapshot["snapshot_id"], second.snapshot["snapshot_id"])
        self.assertEqual(sql("select count(*) as n from evaluation.snapshots")[0]["n"], 1)

    def test_snapshot_is_immutable_in_database(self):
        composition = self.make_composition()
        service = EvaluationService(self.store)
        snapshot_id = service.build(
            product=PRODUCT, composition=composition, profile=PROFILE, user_id=1
        ).snapshot["snapshot_id"]

        with self.assertRaises(psycopg.errors.RaiseException):
            sql("update evaluation.snapshots set total = 99 where snapshot_id = %s", (snapshot_id,))
        with self.assertRaises(psycopg.errors.RaiseException):
            sql("delete from evaluation.snapshots where snapshot_id = %s", (snapshot_id,))

    def test_tampering_is_detected_when_trigger_is_bypassed(self):
        composition = self.make_composition()
        service = EvaluationService(self.store)
        snapshot_id = service.build(
            product=PRODUCT, composition=composition, profile=PROFILE, user_id=1
        ).snapshot["snapshot_id"]

        sql("alter table evaluation.snapshots disable trigger trg_snapshots_immutable")
        try:
            sql(
                "update evaluation.snapshots set document = jsonb_set(document, '{total}', '99') "
                "where snapshot_id = %s",
                (snapshot_id,),
            )
        finally:
            sql("alter table evaluation.snapshots enable trigger trg_snapshots_immutable")

        self.assertFalse(verify_snapshot(self.store.get_snapshot(snapshot_id)))


class CompositionTests(SchemaTestBase):
    def test_upsert_is_idempotent_and_enriches_metadata(self):
        first = self.make_composition()
        second = self.store.upsert_composition(
            {
                "product_id": PRODUCT["id"],
                "composition_hash": COMPOSITION,
                "source": "",
                "verified_at": "2026-10-24T00:00:00+00:00",
            }
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["source"], "integration-test")  # empty value did not overwrite
        self.assertEqual(sql("select count(*) as n from evaluation.product_compositions")[0]["n"], 1)

    def test_duplicate_composition_hash_is_rejected(self):
        self.make_composition()
        with self.assertRaises(psycopg.errors.UniqueViolation):
            sql(
                "insert into evaluation.product_compositions "
                "(product_id, composition_hash, inci_raw) values (%s, %s, %s)",
                (PRODUCT["id"], COMPOSITION, "Aqua"),
            )

    def test_build_registers_a_new_composition(self):
        service = EvaluationService(self.store)
        built = service.build(
            product={"id": 999, "name": "Unknown"},
            composition={"composition_hash": OTHER_COMPOSITION},
            profile=PROFILE,
        )
        self.assertEqual(built.snapshot["composition"]["hash"], OTHER_COMPOSITION)
        self.assertEqual(
            sql("select count(*) as n from evaluation.product_compositions")[0]["n"], 1
        )

    def test_save_snapshot_requires_registered_composition(self):
        snapshot = build_snapshot(
            product=PRODUCT,
            composition={"composition_hash": OTHER_COMPOSITION},
            profile=PROFILE,
            evaluations=[],
            result=evaluate(PROFILE, []),
            rules=get_rules(),
            user_id=1,
        )
        with self.assertRaises(StoreError):
            self.store.save_snapshot(snapshot)


class ConstraintTests(SchemaTestBase):
    def test_value_out_of_range_is_rejected_by_check(self):
        composition = self.make_composition()
        with self.assertRaises(psycopg.errors.CheckViolation):
            sql(
                "insert into evaluation.parameter_evaluations "
                "(composition_id, parameter_id, method_version, status, value, input_hash) "
                "values (%s, 'hydration', %s, 'evaluated', 150, 'x')",
                (composition["id"], DEFAULT_METHOD_VERSION),
            )

    def test_evaluated_requires_value(self):
        composition = self.make_composition()
        with self.assertRaises(psycopg.errors.CheckViolation):
            sql(
                "insert into evaluation.parameter_evaluations "
                "(composition_id, parameter_id, method_version, status, value, input_hash) "
                "values (%s, 'hydration', %s, 'evaluated', null, 'x')",
                (composition["id"], DEFAULT_METHOD_VERSION),
            )

    def test_confidence_range_is_enforced(self):
        composition = self.make_composition()
        with self.assertRaises(psycopg.errors.CheckViolation):
            sql(
                "insert into evaluation.parameter_evaluations "
                "(composition_id, parameter_id, method_version, status, value, confidence, input_hash) "
                "values (%s, 'hydration', %s, 'evaluated', 50, 1.5, 'x')",
                (composition["id"], DEFAULT_METHOD_VERSION),
            )

    def test_unknown_status_is_rejected(self):
        composition = self.make_composition()
        with self.assertRaises(psycopg.errors.CheckViolation):
            sql(
                "insert into evaluation.parameter_evaluations "
                "(composition_id, parameter_id, method_version, status, input_hash) "
                "values (%s, 'hydration', %s, 'maybe', 'x')",
                (composition["id"], DEFAULT_METHOD_VERSION),
            )

    def test_foreign_key_rejects_unknown_composition(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.store.save_evaluation(999_999, ev("hydration", 70))

    def test_snapshot_requires_registered_rule_version(self):
        composition = self.make_composition()
        snapshot = build_snapshot(
            product=PRODUCT,
            composition=composition,
            profile=PROFILE,
            evaluations=[],
            result=evaluate(PROFILE, []),
            rules=get_rules(),
            user_id=1,
        )
        with self.assertRaises(StoreError):
            self.store.save_snapshot({**snapshot, "rule_version": "does-not-exist"})


class SupersedeAndConcurrencyTests(SchemaTestBase):
    def test_history_keeps_previous_versions(self):
        composition = self.make_composition()
        self.store.save_evaluation(composition["id"], ev("hydration", 40))
        self.store.save_evaluation(composition["id"], ev("hydration", 90))

        current = self.store.current_evaluations(composition["id"], DEFAULT_METHOD_VERSION)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].value, 90.0)

        history = self.store.evaluation_history(composition["id"], "hydration")
        self.assertEqual([item.value for item in history], [40.0, 90.0])

        rows = sql("select id, superseded_by from evaluation.parameter_evaluations order by id")
        self.assertEqual(rows[0]["superseded_by"], rows[1]["id"])
        self.assertIsNone(rows[1]["superseded_by"])

    def test_concurrent_first_writes_are_serialised(self):
        composition = self.make_composition()
        barrier = threading.Barrier(2)
        results: list = []

        def worker(value: float) -> None:
            barrier.wait()
            try:
                make_store().save_evaluation(composition["id"], ev("hydration", value))
                results.append(("ok", value))
            except Exception as exc:  # noqa: BLE001
                results.append((type(exc).__name__, str(exc)[:100]))

        threads = [threading.Thread(target=worker, args=(value,)) for value in (60, 80)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual([item[0] for item in results], ["ok", "ok"], results)
        current = self.store.current_evaluations(composition["id"], DEFAULT_METHOD_VERSION)
        self.assertEqual(len(current), 1)
        self.assertIn(current[0].value, (60.0, 80.0))
        self.assertEqual(len(self.store.evaluation_history(composition["id"], "hydration")), 2)

    def test_rollback_leaves_no_partial_supersede(self):
        composition = self.make_composition()
        self.store.save_evaluation(composition["id"], ev("hydration", 50))

        with self.assertRaises(RuntimeError):
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "select id from evaluation.parameter_evaluations "
                        "where superseded_by is null for update"
                    )
                    old_id = cur.fetchone()["id"]
                    # Same order as the store: mark old first, then insert the new row
                    # (the partial unique index forbids two current rows).
                    cur.execute(
                        "select nextval(pg_get_serial_sequence("
                        "'evaluation.parameter_evaluations', 'id')) as id"
                    )
                    new_id = cur.fetchone()["id"]
                    cur.execute(
                        "update evaluation.parameter_evaluations set superseded_by = %s where id = %s",
                        (new_id, old_id),
                    )
                    cur.execute(
                        "insert into evaluation.parameter_evaluations "
                        "(id, composition_id, parameter_id, method_version, status, value, input_hash) "
                        "values (%s, %s, 'hydration', %s, 'evaluated', 90, 'rollback-test')",
                        (new_id, composition["id"], DEFAULT_METHOD_VERSION),
                    )
                    raise RuntimeError("forced rollback")

        current = self.store.current_evaluations(composition["id"], DEFAULT_METHOD_VERSION)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].value, 50.0)
        self.assertEqual(len(self.store.evaluation_history(composition["id"], "hydration")), 1)


class SnapshotConcurrencyTests(SchemaTestBase):
    def test_concurrent_builds_create_single_snapshot(self):
        composition = self.make_composition()
        service = EvaluationService(self.store)
        barrier = threading.Barrier(2)
        results: list = []

        def worker() -> None:
            barrier.wait()
            try:
                built = service.build(
                    product=PRODUCT, composition=composition, profile=PROFILE, user_id=1
                )
                results.append(("ok", built.snapshot["snapshot_id"]))
            except Exception as exc:  # noqa: BLE001
                results.append((type(exc).__name__, str(exc)[:100]))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual([item[0] for item in results], ["ok", "ok"], results)
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(sql("select count(*) as n from evaluation.snapshots")[0]["n"], 1)


class ResearchJobTests(SchemaTestBase):
    def test_active_jobs_are_deduplicated(self):
        composition = self.make_composition()
        self.assertTrue(
            self.store.enqueue_research(composition["id"], "hydration", DEFAULT_METHOD_VERSION)
        )
        self.assertFalse(
            self.store.enqueue_research(composition["id"], "hydration", DEFAULT_METHOD_VERSION)
        )
        self.assertEqual(sql("select count(*) as n from evaluation.research_jobs")[0]["n"], 1)

    def test_completed_job_allows_a_new_attempt(self):
        composition = self.make_composition()
        self.store.enqueue_research(composition["id"], "hydration", DEFAULT_METHOD_VERSION)
        sql("update evaluation.research_jobs set status = 'completed'")
        self.assertTrue(
            self.store.enqueue_research(composition["id"], "hydration", DEFAULT_METHOD_VERSION)
        )
        self.assertEqual(sql("select count(*) as n from evaluation.research_jobs")[0]["n"], 2)

    def test_two_active_jobs_are_impossible(self):
        composition = self.make_composition()
        self.store.enqueue_research(composition["id"], "hydration", DEFAULT_METHOD_VERSION)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            sql(
                "insert into evaluation.research_jobs "
                "(composition_id, parameter_id, method_version) values (%s, 'hydration', %s)",
                (composition["id"], DEFAULT_METHOD_VERSION),
            )


class JsonAndDateTests(SchemaTestBase):
    def test_jsonb_roundtrip_with_special_characters(self):
        composition = self.make_composition()
        limitations = (
            'кавычки "double" и \'single\'',
            "перевод\nстроки",
            "таб\tсимвол",
            "emoji 🧪",
            "обратный слеш \\ и {json}",
        )
        self.store.save_evaluation(
            composition["id"],
            ev(
                "hydration",
                70,
                limitations=limitations,
                evidence_ids=("ev-1", "ev-2"),
                rationale='строка с "кавычками"',
            ),
        )
        current = self.store.current_evaluations(composition["id"], DEFAULT_METHOD_VERSION)[0]
        self.assertEqual(current.limitations, limitations)
        self.assertEqual(current.evidence_ids, ("ev-1", "ev-2"))
        self.assertEqual(current.rationale, 'строка с "кавычками"')

    def test_valid_until_roundtrip_and_freshness(self):
        from app.evaluation import is_current, stale_reason

        composition = self.make_composition()
        future = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
        self.store.save_evaluation(
            composition["id"], ev("hydration", 70, valid_until=future.isoformat())
        )
        stored = self.store.current_evaluations(composition["id"], DEFAULT_METHOD_VERSION)[0]
        self.assertTrue(stored.valid_until)
        self.assertTrue(
            is_current(stored, composition_hash=COMPOSITION, method_version=DEFAULT_METHOD_VERSION)
        )

        past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0)
        self.store.save_evaluation(
            composition["id"], ev("hydration", 75, valid_until=past.isoformat())
        )
        stored = self.store.current_evaluations(composition["id"], DEFAULT_METHOD_VERSION)[0]
        reason = stale_reason(
            stored, composition_hash=COMPOSITION, method_version=DEFAULT_METHOD_VERSION
        )
        self.assertIn("valid_until", reason)

    def test_evaluated_at_is_set_by_database(self):
        composition = self.make_composition()
        self.store.save_evaluation(composition["id"], ev("hydration", 70))
        stored = self.store.current_evaluations(composition["id"], DEFAULT_METHOD_VERSION)[0]
        self.assertTrue(stored.evaluated_at)


class RlsTests(SchemaTestBase):
    """Real role-based tests. Supabase roles are emulated with NOLOGIN roles."""

    def _seed_two_users(self) -> dict:
        composition = self.make_composition()
        service = EvaluationService(self.store)
        ids = {}
        for user_id in (1, 2):
            ids[user_id] = service.build(
                product=PRODUCT, composition=composition, profile=PROFILE, user_id=user_id
            ).snapshot["snapshot_id"]
        return ids

    def _as(self, role: str, claim: str | None = None):
        conn = connect()
        cur = conn.cursor()
        cur.execute(f"set role {role}")
        if claim is not None:
            cur.execute("select set_config('request.jwt.claim.sub', %s, false)", (claim,))
        return conn, cur

    def test_without_grants_even_select_is_denied(self):
        self._seed_two_users()
        sql("revoke all on evaluation.snapshots from authenticated")
        sql("revoke all on schema evaluation from authenticated")
        conn, cur = self._as("authenticated", "1")
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                cur.execute("select count(*) from evaluation.snapshots")
        finally:
            conn.close()

    def test_owner_sees_only_own_snapshots(self):
        ids = self._seed_two_users()
        sql("grant usage on schema evaluation to authenticated")
        sql("grant select on evaluation.snapshots to authenticated")

        for user_id in (1, 2):
            conn, cur = self._as("authenticated", str(user_id))
            try:
                cur.execute("select snapshot_id, user_id from evaluation.snapshots")
                rows = cur.fetchall()
                self.assertEqual(len(rows), 1, f"user {user_id} sees {rows}")
                self.assertEqual(int(rows[0]["user_id"]), user_id)
                self.assertEqual(rows[0]["snapshot_id"], ids[user_id])
            finally:
                conn.close()

    def test_foreign_snapshot_is_invisible_by_id(self):
        ids = self._seed_two_users()
        sql("grant usage on schema evaluation to authenticated")
        sql("grant select on evaluation.snapshots to authenticated")
        conn, cur = self._as("authenticated", "2")
        try:
            cur.execute(
                "select count(*) as n from evaluation.snapshots where snapshot_id = %s",
                (ids[1],),
            )
            self.assertEqual(cur.fetchone()["n"], 0)
        finally:
            conn.close()

    def test_authenticated_cannot_insert_even_with_grant(self):
        self._seed_two_users()
        sql("grant usage on schema evaluation to authenticated")
        sql("grant insert on evaluation.snapshots to authenticated")
        conn, cur = self._as("authenticated", "1")
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    "insert into evaluation.snapshots (snapshot_id, snapshot_hash, schema_version, "
                    "product_id, composition_id, profile_fingerprint, rule_version, engine_version, "
                    "engine_input_hash, parameters, completeness) values "
                    "('forged', 'h', '1', 1, 1, '{}', %s, 'v', 'i', '[]', 0)",
                    (get_rules().version,),
                )
        finally:
            conn.close()

    def test_anon_is_denied(self):
        self._seed_two_users()
        conn, cur = self._as("anon", "1")
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                cur.execute("select count(*) from evaluation.snapshots")
        finally:
            conn.close()

    def test_service_role_bypasses_rls(self):
        self._seed_two_users()
        sql("grant usage on schema evaluation to service_role")
        sql("grant select on evaluation.snapshots to service_role")
        conn, cur = self._as("service_role")
        try:
            cur.execute("select count(*) as n from evaluation.snapshots")
            self.assertEqual(cur.fetchone()["n"], 2)
        finally:
            conn.close()


class EvidenceStorageTests(SchemaTestBase):
    def _evidence(self, *, parameter_id: str = "hydration", verification: str = "confirmed", **kwargs):
        from app.evaluation import Evidence, Source

        return Evidence(
            parameter_id=parameter_id,
            claim=kwargs.get("claim", "Glycerin удерживает влагу"),
            quote=kwargs.get("quote", "Glycerin helps keep the skin hydrated"),
            direction=kwargs.get("direction", "supports"),
            strength=kwargs.get("strength", "moderate"),
            confidence=kwargs.get("confidence", 0.8),
            source=Source(
                url=kwargs.get("url", "https://brand.example/serum"),
                title="Brand page",
                source_type="official",
                retrieved_at="2026-10-01T00:00:00+00:00",
            ),
            verification=verification,
            product_id=PRODUCT["id"],
            composition_hash=COMPOSITION,
            extraction_method="quote_extraction_v1",
            retrieved_at="2026-10-01T00:00:00+00:00",
            rejection_reason=kwargs.get("rejection_reason", ""),
        )

    def test_evidence_roundtrip_is_bound_to_composition_and_parameter(self):
        composition = self.make_composition()
        ids = self.store.save_evidence(
            composition["id"],
            [self._evidence(), self._evidence(parameter_id="barrier")],
        )
        self.assertEqual(len(ids), 2)
        rows = self.store.evidence_for(composition["id"], "hydration")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["composition_id"], composition["id"])
        self.assertEqual(rows[0]["parameter_id"], "hydration")
        self.assertEqual(rows[0]["verification"], "confirmed")
        self.assertEqual(rows[0]["source"]["url"], "https://brand.example/serum")
        self.assertEqual(rows[0]["source"]["source_type"], "official")
        self.assertTrue(rows[0]["retrieved_at"])

    def test_same_quote_from_same_source_is_stored_once(self):
        composition = self.make_composition()
        first = self.store.save_evidence(composition["id"], [self._evidence()])
        second = self.store.save_evidence(composition["id"], [self._evidence()])
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.evidence_for(composition["id"], "hydration")), 1)
        self.assertEqual(sql("select count(*) as n from evaluation.sources")[0]["n"], 1)

    def test_rejected_evidence_is_kept_for_audit(self):
        composition = self.make_composition()
        self.store.save_evidence(
            composition["id"],
            [self._evidence(verification="rejected", rejection_reason="цитата не найдена")],
        )
        rows = self.store.evidence_for(composition["id"], "hydration")
        self.assertEqual(rows[0]["verification"], "rejected")
        self.assertEqual(rows[0]["rejection_reason"], "цитата не найдена")

    def test_evidence_requires_known_composition(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.store.save_evidence(999_999, [self._evidence()])


class JobClaimTests(SchemaTestBase):
    def _enqueue(self, parameter_id: str = "hydration") -> dict:
        composition = self.make_composition()
        self.store.enqueue_research(composition["id"], parameter_id, DEFAULT_METHOD_VERSION)
        return composition

    def test_claim_marks_processing_and_counts_attempt(self):
        composition = self._enqueue()
        job = self.store.claim_job("worker-a", composition_id=composition["id"])
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "processing")
        self.assertEqual(job["attempts"], 1)
        self.assertEqual(job["worker_id"], "worker-a")
        self.assertIsNone(self.store.claim_job("worker-b", composition_id=composition["id"]))

    def test_release_returns_job_to_queue(self):
        composition = self._enqueue()
        job = self.store.claim_job("worker-a", composition_id=composition["id"])
        self.store.release_job(job["id"])
        again = self.store.claim_job("worker-b", composition_id=composition["id"])
        self.assertEqual(again["id"], job["id"])
        self.assertEqual(again["attempts"], 2)

    def test_failed_job_records_cost_and_error(self):
        composition = self._enqueue()
        job = self.store.claim_job("worker-a", composition_id=composition["id"])
        self.store.fail_job(
            job["id"], "провайдер недоступен", tokens_in=10, tokens_out=20, cost_usd=0.12
        )
        stored = self.store.job(job["id"])
        self.assertEqual(stored["status"], "failed")
        self.assertIn("недоступен", stored["last_error"])
        self.assertEqual(float(stored["cost_usd"]), 0.12)
        self.assertEqual(stored["tokens_in"], 10)
        self.assertEqual(stored["tokens_out"], 20)

    def test_parallel_workers_claim_different_jobs(self):
        composition = self.make_composition()
        for parameter_id in ("hydration", "barrier"):
            self.store.enqueue_research(composition["id"], parameter_id, DEFAULT_METHOD_VERSION)
        claimed: list = []
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        def worker(name: str) -> None:
            store = make_store()
            barrier.wait()
            job = store.claim_job(name, composition_id=composition["id"])
            if job:
                with lock:
                    claimed.append(job["id"])

        threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(claimed), 2)
        self.assertEqual(len(set(claimed)), 2)


class ResearchIntegrationTests(SchemaTestBase):
    def test_fake_provider_research_persists_evidence_and_evaluation(self):
        from app.evaluation import FakeResearchProvider, ResearchService, candidate, ok

        provider = FakeResearchProvider(
            {
                "hydration": ok(
                    candidate(
                        parameter_id="hydration",
                        claim="Glycerin удерживает влагу",
                        quote="Glycerin helps keep the skin hydrated",
                        source_text="Formula. Glycerin helps keep the skin hydrated.",
                        strength="strong",
                        confidence=1.0,
                    )
                ),
                "barrier": ok(
                    candidate(
                        parameter_id="barrier",
                        claim="Ceramides поддерживают барьер",
                        quote="Ceramides support the skin barrier",
                        source_text="Formula. Ceramides support the skin barrier.",
                        strength="moderate",
                        confidence=1.0,
                    )
                ),
            }
        )
        service = ResearchService(self.store, provider)
        report = service.research_missing(
            product=PRODUCT, composition=self.make_composition(), profile=PROFILE
        )
        self.assertEqual(report.researched, ("barrier", "hydration"))
        composition = self.store.get_composition(PRODUCT["id"], COMPOSITION)

        rows = self.store.evidence_for(composition["id"], "hydration")
        self.assertEqual(rows[0]["verification"], "confirmed")
        self.assertEqual(rows[0]["composition_id"], composition["id"])

        evaluations = self.store.current_evaluations(composition["id"], DEFAULT_METHOD_VERSION)
        values = {item.parameter_id: item.value for item in evaluations}
        self.assertEqual(values, {"barrier": 70.0, "hydration": 80.0})
        self.assertTrue(
            next(item for item in evaluations if item.parameter_id == "hydration").evidence_ids
        )

        built = EvaluationService(self.store).build(
            product=PRODUCT, composition=self.make_composition(), profile=PROFILE, user_id=1
        )
        self.assertEqual(built.snapshot["total"], 75)
        self.assertIsNone(built.snapshot["verdict"])

        calls = provider.call_count()
        service.research_missing(
            product=PRODUCT, composition=self.make_composition(), profile=PROFILE
        )
        self.assertEqual(provider.call_count(), calls, "second run must not call the provider")


class MigrationIdempotencyTests(SchemaTestBase):
    def test_migration_can_be_reapplied(self):
        with open(MIGRATION_PATH, encoding="utf-8") as fh:
            migration = fh.read()
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(migration)
            conn.commit()
        rows = sql("select count(*) as n from information_schema.tables where table_schema = 'evaluation'")
        self.assertEqual(rows[0]["n"], 8)


if __name__ == "__main__":
    unittest.main()
