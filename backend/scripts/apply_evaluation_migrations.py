"""Apply the Evaluation V2 migrations to an isolated test database.

Safety model (deliberate):
  * by default only a local test database is accepted (host 127.0.0.1/localhost,
    db name starting with ``aidermy_eval_test``);
  * remote DSNs require BOTH ``--allow-remote --yes`` AND the environment flag
    ``AIDERMY_ALLOW_REMOTE_MIGRATIONS=1``;
  * ``--dry-run`` prints the SQL order without touching the database;
  * each file runs in its own transaction; the migrations themselves are
    idempotent (``create table if not exists`` / ``not valid`` checks).

Usage:
    EVALUATION_TEST_DSN=postgresql://... python backend/scripts/apply_evaluation_migrations.py
    ... --dry-run
    ... --allow-remote --yes   # staging only, with the env flag set
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from evaluation_test_env import guard_local_test_dsn  # noqa: E402

BACKEND = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = BACKEND / "migrations"


def migration_files() -> list[pathlib.Path]:
    """Evaluation V2 migrations in filename (date) order."""
    return sorted(MIGRATIONS.glob("*evaluation_v2*.sql"))


def apply(dsn: str, *, dry_run: bool = False) -> dict:
    files = migration_files()
    if dry_run:
        return {"files": [path.name for path in files], "applied": [], "dry_run": True}
    applied: list[str] = []
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        for path in files:
            with conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
            conn.commit()
            applied.append(path.name)
        with conn.cursor() as cur:
            cur.execute(
                "select table_name from information_schema.tables "
                "where table_schema = 'evaluation' order by 1"
            )
            tables = [row["table_name"] for row in cur.fetchall()]
    return {"files": [path.name for path in files], "applied": applied, "tables": tables}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("EVALUATION_TEST_DSN", ""))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if args.allow_remote:
        if not args.yes or os.getenv("AIDERMY_ALLOW_REMOTE_MIGRATIONS") != "1":
            raise SystemExit(
                "REFUSED: remote migrations need --yes and AIDERMY_ALLOW_REMOTE_MIGRATIONS=1"
            )
    else:
        guard_local_test_dsn(args.dsn)
        print("target      : isolated local test database (guard passed)")

    if args.dry_run:
        print("dry-run     : yes")
        for name in [path.name for path in migration_files()]:
            print("  would apply:", name)
        return 0

    result = apply(args.dsn)
    for name in result["applied"]:
        print("applied     :", name)
    print("tables      :", len(result.get("tables") or []), result.get("tables"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
