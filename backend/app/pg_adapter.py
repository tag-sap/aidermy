"""PostgreSQL adapter mimicking the sqlite3.Connection/Cursor surface.

The app was written against SQLite. The schema already lives in Supabase
PostgreSQL; this module lets existing SQLite-style code (``?`` placeholders,
``INSERT OR ...``, ``PRAGMA table_info``, ``sqlite_master``, ``lastrowid``)
run against Postgres without rewriting every caller.
"""
from __future__ import annotations

import os
import re
from datetime import datetime

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row


class _DictRow(dict):
    """dict that also supports integer index access like sqlite3.Row."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._keys = list(self.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


# INSERT OR REPLACE conflict targets keyed by lowercase table name.
_REPLACE_CONFLICT = {
    "product_models": ("product_id",),
    "product_ppms": ("product_id",),
    "product_vectors": ("product_id",),
    "calibration_references": ("cache_key",),
    "calibration_cases": ("run_key", "product_id", "profile_id"),
}


def _translate(sql: str) -> str:
    s = sql
    had_ignore = re.search(r"INSERT\s+OR\s+IGNORE", s, flags=re.IGNORECASE) is not None
    had_replace = re.search(r"INSERT\s+OR\s+REPLACE", s, flags=re.IGNORECASE) is not None
    s = re.sub(
        r"INSERT\s+OR\s+(IGNORE|REPLACE|ABORT|FAIL|ROLLBACK)\s+INTO",
        "INSERT INTO", s, flags=re.IGNORECASE)
    s = re.sub(r"lower_ru\s*\(", "lower(", s, flags=re.IGNORECASE)
    s = s.replace("NOCASE_RU", '"C"')
    s = s.replace("?", "%s")
    if had_ignore:
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    elif had_replace:
        s = _add_replace_conflict(s)
    return s


def _add_replace_conflict(s: str) -> str:
    m = re.search(r"INSERT\s+INTO\s+(\w+)\s*\(([^)]+)\)", s, flags=re.IGNORECASE)
    if not m:
        return s
    table = m.group(1).lower()
    target = _REPLACE_CONFLICT.get(table)
    if not target:
        return s
    cols = [c.strip() for c in m.group(2).split(",") if c.strip()]
    excluded = {t.lower() for t in target}
    updates = [f"{c}=EXCLUDED.{c}" for c in cols if c.lower() not in excluded]
    if not updates:
        return s
    clause = "ON CONFLICT (" + ", ".join(target) + ") DO UPDATE SET " + ", ".join(updates)
    return s.rstrip().rstrip(";") + " " + clause


class _PgCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None
        self._buffer = None

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def execute(self, sql, params=()):
        self._buffer = None
        if sql.lstrip().upper().startswith("PRAGMA"):
            self._buffer = self._handle_pragma(sql)
            self.lastrowid = None
            return self
        if "sqlite_master" in sql.lower():
            self._buffer = self._handle_sqlite_master(sql)
            self.lastrowid = None
            return self
        if re.match(r"\s*(CREATE|ALTER|DROP)\s", sql, flags=re.IGNORECASE):
            self.lastrowid = None
            return self
        statement = _translate(sql)
        is_insert = re.match(r"\s*INSERT\s+INTO\s+\w+", statement, flags=re.IGNORECASE) is not None
        if is_insert and "RETURNING" not in statement.upper():
            statement = statement.rstrip().rstrip(";") + " RETURNING id"
        self._cursor.execute(statement, params or ())
        self.lastrowid = None
        if is_insert:
            try:
                row = self._cursor.fetchone()
                if row is not None and "id" in row:
                    self.lastrowid = row["id"]
            except Exception:
                self.lastrowid = None
        return self

    def _handle_pragma(self, sql):
        m = re.search(r"table_info\(([\"\w]+)\)", sql, flags=re.IGNORECASE)
        if m:
            table = m.group(1).strip('"')
            self._cursor.execute(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
                (table,),
            )
            rows = self._cursor.fetchall()
            return [
                _DictRow({
                    "cid": i,
                    "name": r["column_name"],
                    "type": r["data_type"],
                    "notnull": 0 if r["is_nullable"] == "YES" else 1,
                    "dflt_value": r["column_default"],
                    "pk": 0,
                })
                for i, r in enumerate(rows)
            ]
        return []

    def _handle_sqlite_master(self, sql):
        m = re.search(r"name\s*=\s*'([^']+)'", sql, flags=re.IGNORECASE)
        if not m:
            return []
        table = m.group(1)
        self._cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        return [_DictRow({"name": r["table_name"]}) for r in self._cursor.fetchall()]

    @staticmethod
    def _normalise(row):
        if not row:
            return row
        return _DictRow({
            k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v)
            for k, v in row.items()
        })

    def fetchone(self):
        if self._buffer is not None:
            return self._buffer[0] if self._buffer else None
        return self._normalise(self._cursor.fetchone())

    def fetchall(self):
        if self._buffer is not None:
            return self._buffer
        return [self._normalise(r) for r in self._cursor.fetchall()]


class _PgConnection:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return _PgCursor(self._connection.cursor())

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        try:
            self._connection.rollback()
        except Exception:
            pass
        _get_pool().putconn(self._connection)


_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        url = os.getenv("SUPABASE_DATABASE_URL")
        if not url:
            raise RuntimeError("SUPABASE_DATABASE_URL не настроен")
        _pool = ConnectionPool(url, min_size=1, max_size=10, open=True, timeout=30, kwargs={"row_factory": dict_row})
    return _pool


def connect():
    """Return a Postgres connection adapter from the shared pool."""
    return _PgConnection(_get_pool().getconn())
