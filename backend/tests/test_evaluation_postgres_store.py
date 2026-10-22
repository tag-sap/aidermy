"""PostgresStore tests using a scripted fake connection (no real database)."""
from __future__ import annotations

import unittest

from app.evaluation import ParameterEvaluation, get_rules
from app.evaluation.parameters import PARAMETERS
from app.evaluation.postgres_store import PostgresStore, row_to_evaluation
from app.evaluation.store import StoreError

COMPOSITION = "a" * 64


class FakeCursor:
    def __init__(self, db: "FakeDB"):
        self.db = db
        self._rows = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.db.executed.append((" ".join(sql.split()), params))
        self._rows = self.db.dispatch(" ".join(sql.split()), params)

    def fetchone(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows

    def fetchall(self):
        if self._rows is None:
            return []
        return self._rows if isinstance(self._rows, list) else [self._rows]


class FakeConnection:
    def __init__(self, db: "FakeDB"):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.db.commits += 1
        return False

    def close(self):
        self.db.closed += 1


class FakeDB:
    def __init__(self):
        self.executed: list = []
        self.commits = 0
        self.closed = 0
        self.handlers: list = []

    def on(self, marker, result):
        self.handlers.append((marker, result))

    def connect(self):
        return FakeConnection(self)

    def dispatch(self, sql, params):
        for marker, result in self.handlers:
            if marker in sql:
                return result(params) if callable(result) else result
        return None


def store_for(db: FakeDB) -> PostgresStore:
    return PostgresStore(connection_factory=db.connect)


def sql_text(db: FakeDB) -> str:
    return " || ".join(statement for statement, _ in db.executed)


class RowMappingTests(unittest.TestCase):
    def test_row_is_mapped_to_domain_object(self):
        evaluation = row_to_evaluation(
            {
                "parameter_id": "hydration",
                "status": "evaluated",
                "value": "72.5",
                "confidence": "0.8",
                "method_version": "research-1.0.0-draft",
                "composition_hash": COMPOSITION,
                "rationale": "подтверждено источником",
                "limitations": '["нет данных о концентрации"]',
                "evidence_ids": '["ev-1"]',
                "evaluated_at": "2026-10-23T10:00:00+00:00",
                "valid_until": None,
            }
        )
        self.assertEqual(evaluation.value, 72.5)
        self.assertEqual(evaluation.confidence, 0.8)
        self.assertEqual(evaluation.limitations, ("нет данных о концентрации",))
        self.assertEqual(evaluation.evidence_ids, ("ev-1",))
        self.assertIsNone(evaluation.valid_until)

    def test_invalid_scale_is_rejected_by_contract(self):
        with self.assertRaises(Exception):
            row_to_evaluation(
                {
                    "parameter_id": "hydration",
                    "status": "evaluated",
                    "value": "150",
                    "method_version": "m",
                    "composition_hash": COMPOSITION,
                }
            )


class CompositionTests(unittest.TestCase):
    def test_missing_composition_returns_none(self):
        db = FakeDB()
        self.assertIsNone(store_for(db).get_composition(1, COMPOSITION))

    def test_upsert_is_idempotent_by_conflict_target(self):
        db = FakeDB()
        db.on("insert into", lambda params: {
            "id": 5,
            "product_id": params[0],
            "composition_hash": params[1],
            "inci_raw": params[2],
            "source": params[3],
            "verified_at": params[4],
        })
        record = store_for(db).upsert_composition(
            {
                "product_id": 7,
                "composition_hash": COMPOSITION,
                "inci_raw": "Aqua",
                "source": "catalog",
            }
        )
        self.assertEqual(record["id"], 5)
        self.assertIn("on conflict (product_id, composition_hash)", sql_text(db))

    def test_upsert_failure_is_reported(self):
        db = FakeDB()
        with self.assertRaises(StoreError):
            store_for(db).upsert_composition({"product_id": 1, "composition_hash": COMPOSITION})

    def test_upsert_is_committed(self):
        db = FakeDB()
        db.on("insert into", {"id": 1, "product_id": 1, "composition_hash": COMPOSITION})
        store_for(db).upsert_composition({"product_id": 1, "composition_hash": COMPOSITION})
        self.assertGreaterEqual(db.commits, 1, "INSERT ... RETURNING must be committed")


class EvaluationTests(unittest.TestCase):
    def test_current_evaluations_exclude_superseded_rows(self):
        db = FakeDB()
        db.on("from evaluation.parameter_evaluations e", [])
        result = store_for(db).current_evaluations(3, "m")
        self.assertEqual(result, [])
        self.assertIn("superseded_by is null", sql_text(db))

    def test_save_evaluation_supersedes_previous_row(self):
        db = FakeDB()
        db.on("for update", {"id": 10})
        db.on("insert into", {"id": 11})
        evaluation = ParameterEvaluation(
            parameter_id="hydration",
            status="evaluated",
            value=70,
            composition_hash=COMPOSITION,
            method_version="m",
        )
        store_for(db).save_evaluation(3, evaluation)
        text = sql_text(db)
        self.assertIn("for update", text)
        self.assertIn("set superseded_by = %s", text)

    def test_first_evaluation_does_not_supersede(self):
        db = FakeDB()
        db.on("for update", None)
        db.on("insert into", {"id": 11})
        evaluation = ParameterEvaluation(
            parameter_id="barrier",
            status="evaluated",
            value=60,
            composition_hash=COMPOSITION,
            method_version="m",
        )
        store_for(db).save_evaluation(3, evaluation)
        self.assertNotIn("set superseded_by", sql_text(db))

class SnapshotTests(unittest.TestCase):
    def _snapshot(self):
        return {
            "snapshot_id": "abc123",
            "snapshot_hash": "hash",
            "schema_version": "1.0.0",
            "engine_version": "2.0.0-draft",
            "rule_version": get_rules().version,
            "rules_hash": get_rules().hash,
            "engine_input_hash": "input",
            "user_id": 1,
            "product": {"id": 7, "name": "Test"},
            "composition": {"hash": COMPOSITION, "source": "catalog"},
            "profile": {"signals": ["dry"]},
            "parameters": [{"parameter_id": "hydration", "value": 70}],
            "total": 70,
            "verdict": None,
            "completeness": 1.0,
            "limitations": [],
            "created_at": "2026-10-23T10:00:00+00:00",
        }

    def test_snapshot_requires_registered_rule_version(self):
        db = FakeDB()
        db.on("from evaluation.product_compositions", {"id": 3})
        db.on("from evaluation.rule_versions", None)
        with self.assertRaises(StoreError):
            store_for(db).save_snapshot(self._snapshot())

    def test_snapshot_requires_registered_composition(self):
        db = FakeDB()
        db.on("from evaluation.product_compositions", None)
        with self.assertRaises(StoreError):
            store_for(db).save_snapshot(self._snapshot())

    def test_snapshot_insert_is_idempotent(self):
        db = FakeDB()
        db.on("from evaluation.product_compositions", {"id": 3})
        db.on("from evaluation.rule_versions", {"ok": 1})
        db.on("insert into", None)
        stored_row = {
            "snapshot_id": "abc123",
            "snapshot_hash": "hash",
            "schema_version": "1.0.0",
            "user_id": 1,
            "product_id": 7,
            "product_name": "Test",
            "profile_fingerprint": {"signals": ["dry"]},
            "rule_version": get_rules().version,
            "engine_version": "2.0.0-draft",
            "engine_input_hash": "input",
            "parameters": [{"parameter_id": "hydration", "value": 70}],
            "total": 70,
            "verdict": None,
            "completeness": 1.0,
            "limitations": [],
            "created_at": "2026-10-23T10:00:00+00:00",
            "composition_hash": COMPOSITION,
            "source": "catalog",
            "verified_at": None,
            "rules_hash": get_rules().hash,
        }
        calls = {"selects": 0}

        def snapshots_handler(_params):
            calls["selects"] += 1
            return None if calls["selects"] == 1 else stored_row

        db.on("from evaluation.snapshots s", snapshots_handler)

        stored = store_for(db).save_snapshot(self._snapshot())
        self.assertEqual(stored["snapshot_id"], "abc123")
        self.assertEqual(stored["product"]["name"], "Test")
        self.assertIn("on conflict (snapshot_id) do nothing", sql_text(db))
        self.assertEqual(calls["selects"], 2)

    def test_existing_snapshot_is_returned_without_insert(self):
        db = FakeDB()
        db.on("from evaluation.snapshots s", {"document": {"snapshot_id": "abc123", "snapshot_hash": "h"}})
        store_for(db).save_snapshot(self._snapshot())
        self.assertNotIn("insert into evaluation.snapshots", sql_text(db))

    def test_document_is_returned_verbatim(self):
        db = FakeDB()
        document = {
            "snapshot_id": "abc123",
            "snapshot_hash": "hash",
            "total": 70,
            "created_at": "2026-10-23T10:00:00.123456+00:00",
        }
        db.on("from evaluation.snapshots s", {"document": document})
        self.assertEqual(store_for(db).get_snapshot("abc123"), document)


class ResearchAndSeedTests(unittest.TestCase):
    def test_enqueue_returns_false_on_conflict(self):
        db = FakeDB()
        self.assertFalse(store_for(db).enqueue_research(3, "hydration", "m"))
        self.assertIn("on conflict do nothing", sql_text(db))

    def test_enqueue_returns_true_when_row_is_created(self):
        db = FakeDB()
        db.on("insert into", {"id": 1})
        self.assertTrue(store_for(db).enqueue_research(3, "hydration", "m"))
        self.assertGreaterEqual(db.commits, 1, "research job insert must be committed")

    def test_seed_rule_upserts_version(self):
        db = FakeDB()
        version = store_for(db).seed_rule(get_rules())
        self.assertEqual(version, get_rules().version)
        self.assertIn("on conflict (version) do update", sql_text(db))

    def test_seed_registry_writes_every_parameter(self):
        db = FakeDB()
        count = store_for(db).seed_registry("m")
        self.assertEqual(count, len(PARAMETERS))
        self.assertEqual(len(db.executed), len(PARAMETERS))


if __name__ == "__main__":
    unittest.main()
