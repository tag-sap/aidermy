"""Print a safe summary of the evaluation-v2 test environment.

Never prints credentials. Refuses to describe a non-local database, so it cannot
be used by accident against production.

Usage:
    EVALUATION_TEST_DSN=... python backend/scripts/evaluation_test_env.py
"""
from __future__ import annotations

import os
import sys

import psycopg
from psycopg import conninfo
from psycopg.rows import dict_row

TEST_DB_PREFIX = "aidermy_eval_test"
FORBIDDEN_HOST_PARTS = ("supabase.co", "supabase.com", "138.124.231.42", "eclectusgames.ru")


def main() -> int:
    dsn = os.environ.get("EVALUATION_TEST_DSN", "").strip()
    if not dsn:
        print("EVALUATION_TEST_DSN is not set")
        return 2
    info = conninfo.conninfo_to_dict(dsn)
    host = str(info.get("host") or "")
    port = str(info.get("port") or "")
    dbname = str(info.get("dbname") or "")
    user = str(info.get("user") or "")

    for part in FORBIDDEN_HOST_PARTS:
        if part in host:
            print(f"REFUSED: production host detected ({host})")
            return 3
    if host not in {"127.0.0.1", "localhost"} or not dbname.startswith(TEST_DB_PREFIX):
        print(f"REFUSED: not a local test database (host={host!r}, db={dbname!r})")
        return 3

    print("environment : isolated local PostgreSQL")
    print("host        :", host)
    print("port        :", port)
    print("database    :", dbname)
    print("user        :", user)
    print("password    :", "<not printed>")
    print("production  : NOT used (guard passed)")

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("select version() as v, current_database() as db, current_user as usr")
            row = cur.fetchone()
            print("server      :", row["v"].split(" on ")[0])
            print("connected   :", row["db"], "as", row["usr"])
            cur.execute("select coalesce(ssl, false) as ssl from pg_stat_ssl where pid = pg_backend_pid()")
            ssl_row = cur.fetchone()
            print("ssl         :", bool(ssl_row and ssl_row["ssl"]))
            cur.execute(
                "select table_name from information_schema.tables "
                "where table_schema = 'evaluation' order by 1"
            )
            tables = [r["table_name"] for r in cur.fetchall()]
            print("evaluation tables:", len(tables), tables)
            cur.execute("select count(*) as n from pg_policies where schemaname = 'evaluation'")
            print("rls policies:", cur.fetchone()["n"])
            cur.execute(
                "select rolname, rolbypassrls from pg_roles "
                "where rolname in ('anon','authenticated','service_role') order by 1"
            )
            print("roles:", [(r["rolname"], r["rolbypassrls"]) for r in cur.fetchall()])
    return 0


if __name__ == "__main__":
    sys.exit(main())
