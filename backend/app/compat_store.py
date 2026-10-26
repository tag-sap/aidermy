"""Durable storage for shelf compatibility checks and in-app notifications.

The module lives next to the existing shelf tables instead of introducing a
second analysis database. SQLite is used locally and in tests; PostgreSQL gets
the same tables through the SQL migration in ``backend/migrations``.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .database import AIDERMY_DB, get_connection

_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()

TASK_STATUSES = (
    "queued",
    "running",
    "waiting_for_products",
    "analyzing_compatibility",
    "completed",
    "failed",
    "cancelled",
)
ACTIVE_TASK_STATUSES = (
    "queued",
    "running",
    "waiting_for_products",
    "analyzing_compatibility",
)


def _load(value: Any, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _row_dict(row) -> dict | None:
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def _json_fields(row: dict | None, fields: Iterable[str]) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for field in fields:
        fallback = {} if field == "profile_json" else []
        out[field] = _load(out.get(field), fallback)
    return out


def ensure_schema() -> None:
    """Create local tables once. Production uses the SQL migration."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        conn = get_connection(AIDERMY_DB)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS compatibility_sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT DEFAULT '',
                    product_ids TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'queued',
                    report_json TEXT,
                    profile_json TEXT DEFAULT '{}',
                    profile_updated_at TEXT DEFAULT '',
                    context_key TEXT DEFAULT '',
                    task_id INTEGER,
                    cost INTEGER NOT NULL DEFAULT 0,
                    error TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    checked_at TIMESTAMP,
                    deleted_at TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS compatibility_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT DEFAULT 'queued',
                    product_ids TEXT DEFAULT '[]',
                    set_id INTEGER,
                    profile_json TEXT DEFAULT '{}',
                    profile_updated_at TEXT DEFAULT '',
                    context_key TEXT DEFAULT '',
                    active_key TEXT,
                    result_snapshot_id TEXT,
                    cost INTEGER NOT NULL DEFAULT 0,
                    error TEXT DEFAULT '',
                    attempts INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_key TEXT NOT NULL,
                    kind TEXT DEFAULT '',
                    title TEXT DEFAULT '',
                    body TEXT DEFAULT '',
                    target_type TEXT DEFAULT '',
                    target_id INTEGER,
                    read_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_compat_tasks_active_key "
                "ON compatibility_tasks (active_key)"
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_notifications_event "
                "ON user_notifications (user_id, event_key)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_compat_tasks_status "
                "ON compatibility_tasks (status, id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_compat_sets_user "
                "ON compatibility_sets (user_id, created_at)"
            )
            # Keep local SQLite databases created by the previous release
            # compatible without running a destructive rebuild.
            for table in ("compatibility_sets", "compatibility_tasks"):
                columns = {
                    str(row["name"])
                    for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if "cost" not in columns:
                    cursor.execute(
                        f"ALTER TABLE {table} ADD COLUMN cost INTEGER NOT NULL DEFAULT 0"
                    )
            conn.commit()
            _SCHEMA_READY = True
        finally:
            conn.close()


# -- sets ------------------------------------------------------------------
def create_set(
    *,
    user_id: int,
    name: str,
    product_ids: list[int],
    profile: dict,
    profile_updated_at: str,
    context_key: str,
    status: str = "queued",
    cost: int = 0,
) -> dict:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO compatibility_sets
                (user_id, name, product_ids, status, profile_json,
                 profile_updated_at, context_key, cost, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                int(user_id),
                name,
                _dump(product_ids),
                status,
                _dump(profile),
                profile_updated_at,
                context_key,
                max(0, int(cost)),
            ),
        )
        set_id = int(cursor.lastrowid)
        conn.commit()
        return get_set(user_id, set_id) or {}
    finally:
        conn.close()


def get_set(user_id: int, set_id: int) -> dict | None:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        row = conn.execute(
            "SELECT * FROM compatibility_sets "
            "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (int(set_id), int(user_id)),
        ).fetchone()
        return _json_fields(_row_dict(row), ("product_ids",))
    finally:
        conn.close()


def get_set_any(set_id: int) -> dict | None:
    """Worker-only access. Never expose without an owner check."""
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        row = conn.execute(
            "SELECT * FROM compatibility_sets WHERE id = ?", (int(set_id),)
        ).fetchone()
        return _json_fields(_row_dict(row), ("product_ids",))
    finally:
        conn.close()


def list_sets(user_id: int) -> list[dict]:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        rows = conn.execute(
            "SELECT * FROM compatibility_sets "
            "WHERE user_id = ? AND deleted_at IS NULL "
            "ORDER BY updated_at DESC, id DESC",
            (int(user_id),),
        ).fetchall()
        return [_json_fields(_row_dict(row), ("product_ids",)) for row in rows]
    finally:
        conn.close()


def find_set_by_context(user_id: int, context_key: str) -> dict | None:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        row = conn.execute(
            "SELECT * FROM compatibility_sets "
            "WHERE user_id = ? AND context_key = ? AND deleted_at IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (int(user_id), context_key),
        ).fetchone()
        return _json_fields(_row_dict(row), ("product_ids",))
    finally:
        conn.close()


def update_set(set_id: int, **fields: Any) -> None:
    allowed = {
        "name", "status", "report_json", "profile_json", "task_id", "error",
        "checked_at", "updated_at", "deleted_at", "product_ids", "cost",
    }
    values = []
    assignments = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        assignments.append(f"{key} = ?")
        if key in {"report_json", "profile_json", "product_ids"} and value is not None:
            value = _dump(value)
        values.append(value)
    if not assignments:
        return
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        conn.execute(
            f"UPDATE compatibility_sets SET {', '.join(assignments)} WHERE id = ?",
            (*values, int(set_id)),
        )
        conn.commit()
    finally:
        conn.close()


def soft_delete_set(user_id: int, set_id: int) -> bool:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        row = conn.execute(
            "SELECT id FROM compatibility_sets "
            "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (int(set_id), int(user_id)),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE compatibility_sets SET deleted_at = CURRENT_TIMESTAMP, "
            "status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(set_id),),
        )
        conn.execute(
            "UPDATE compatibility_tasks SET status = 'cancelled', active_key = NULL, "
            "updated_at = CURRENT_TIMESTAMP, finished_at = CURRENT_TIMESTAMP "
            "WHERE set_id = ? AND status IN "
            "('queued','running','waiting_for_products','analyzing_compatibility')",
            (int(set_id),),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# -- tasks -----------------------------------------------------------------
def create_task(
    *,
    user_id: int,
    kind: str,
    product_ids: list[int],
    profile: dict,
    profile_updated_at: str,
    context_key: str,
    set_id: int | None = None,
    active_key: str | None = None,
    cost: int = 0,
) -> dict:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO compatibility_tasks
                (user_id, kind, status, product_ids, set_id, profile_json,
                 profile_updated_at, context_key, active_key, cost, created_at, updated_at)
            VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                int(user_id),
                kind,
                _dump(product_ids),
                set_id,
                _dump(profile),
                profile_updated_at,
                context_key,
                active_key,
                max(0, int(cost)),
            ),
        )
        task_id = int(cursor.lastrowid)
        conn.commit()
        return get_task_any(task_id) or {}
    finally:
        conn.close()


def get_task_any(task_id: int) -> dict | None:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        row = conn.execute(
            "SELECT * FROM compatibility_tasks WHERE id = ?", (int(task_id),)
        ).fetchone()
        return _json_fields(_row_dict(row), ("product_ids", "profile_json"))
    finally:
        conn.close()


def get_task(user_id: int, task_id: int) -> dict | None:
    task = get_task_any(task_id)
    if not task or int(task["user_id"]) != int(user_id):
        return None
    return task


def find_individual_task(user_id: int, product_id: int) -> dict | None:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        rows = conn.execute(
            "SELECT * FROM compatibility_tasks WHERE user_id = ? AND kind = 'individual' "
            "ORDER BY id DESC LIMIT 100",
            (int(user_id),),
        ).fetchall()
        for row in rows:
            task = _json_fields(_row_dict(row), ("product_ids", "profile_json"))
            if int(product_id) in [int(pid) for pid in (task.get("product_ids") or [])]:
                return task
        return None
    finally:
        conn.close()


def find_active_individual_task(user_id: int, product_id: int) -> dict | None:
    """Return a queued/running individual check for this user's product.

    The compatibility worker must wait for this task instead of launching a
    duplicate analysis. Completed/failed tasks are intentionally ignored.
    """
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        rows = conn.execute(
            "SELECT * FROM compatibility_tasks "
            "WHERE user_id = ? AND kind = 'individual' "
            "AND status IN ('queued','running','waiting_for_products','analyzing_compatibility') "
            "ORDER BY id DESC LIMIT 50",
            (int(user_id),),
        ).fetchall()
        for row in rows:
            task = _json_fields(_row_dict(row), ("product_ids", "profile_json"))
            if int(product_id) in [int(pid) for pid in (task.get("product_ids") or [])]:
                return task
        return None
    finally:
        conn.close()


def find_task_by_context(user_id: int, kind: str, context_key: str) -> dict | None:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        row = conn.execute(
            "SELECT * FROM compatibility_tasks "
            "WHERE user_id = ? AND kind = ? AND context_key = ? "
            "ORDER BY id DESC LIMIT 1",
            (int(user_id), kind, context_key),
        ).fetchone()
        return _json_fields(_row_dict(row), ("product_ids", "profile_json"))
    finally:
        conn.close()


def find_active_task_by_key(active_key: str) -> dict | None:
    if not active_key:
        return None
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        row = conn.execute(
            "SELECT * FROM compatibility_tasks WHERE active_key = ? LIMIT 1",
            (active_key,),
        ).fetchone()
        return _json_fields(_row_dict(row), ("product_ids", "profile_json"))
    finally:
        conn.close()


def update_task(task_id: int, **fields: Any) -> None:
    allowed = {
        "status", "active_key", "result_snapshot_id", "error", "attempts",
        "updated_at", "started_at", "finished_at", "set_id", "cost",
    }
    values = []
    assignments = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        assignments.append(f"{key} = ?")
        values.append(value)
    if not assignments:
        return
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        conn.execute(
            f"UPDATE compatibility_tasks SET {', '.join(assignments)} WHERE id = ?",
            (*values, int(task_id)),
        )
        conn.commit()
    finally:
        conn.close()


def claim_next_task(kind: str | None = None) -> dict | None:
    """Atomically claim one queued task from any application worker."""
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        if kind:
            row = conn.execute(
                "SELECT id FROM compatibility_tasks WHERE status = 'queued' AND kind = ? "
                "ORDER BY id ASC LIMIT 1",
                (str(kind),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM compatibility_tasks WHERE status = 'queued' "
                "ORDER BY id ASC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        task_id = int(row["id"])
        if kind:
            updated = conn.execute(
                "UPDATE compatibility_tasks SET status = 'running', "
                "started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, "
                "attempts = attempts + 1 WHERE id = ? AND status = 'queued' AND kind = ?",
                (task_id, str(kind)),
            )
        else:
            updated = conn.execute(
                "UPDATE compatibility_tasks SET status = 'running', "
                "started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, "
                "attempts = attempts + 1 WHERE id = ? AND status = 'queued'",
                (task_id,),
            )
        conn.commit()
        if not updated.rowcount:
            return None
        return get_task_any(task_id)
    finally:
        conn.close()


def recover_stale_tasks(max_age_minutes: int = 45) -> int:
    """Return a crashed worker's task to the queue instead of hanging forever."""
    ensure_schema()
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=max_age_minutes)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = get_connection(AIDERMY_DB)
    try:
        cursor = conn.execute(
            "UPDATE compatibility_tasks SET status = 'queued', "
            "started_at = NULL, updated_at = CURRENT_TIMESTAMP, "
            "error = 'Предыдущий исполнитель был прерван; задача поставлена повторно.' "
            "WHERE status IN ('running','waiting_for_products','analyzing_compatibility') "
            "AND started_at IS NOT NULL AND started_at < ?",
            (cutoff,),
        )
        conn.commit()
        return int(cursor.rowcount or 0)
    finally:
        conn.close()


def active_task_count() -> int:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM compatibility_tasks WHERE active_key IS NOT NULL"
        ).fetchone()
        return int(row["n"] if row else 0)
    finally:
        conn.close()


# -- notifications ---------------------------------------------------------
def create_notification(
    *,
    user_id: int,
    event_key: str,
    kind: str,
    title: str,
    body: str,
    target_type: str,
    target_id: int | None,
) -> dict | None:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_notifications "
            "(user_id, event_key, kind, title, body, target_type, target_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (int(user_id), event_key, kind, title, body, target_type, target_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_notifications WHERE user_id = ? AND event_key = ?",
            (int(user_id), event_key),
        ).fetchone()
        return _row_dict(row)
    finally:
        conn.close()


def list_notifications(user_id: int, limit: int = 30) -> list[dict]:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        rows = conn.execute(
            "SELECT * FROM user_notifications WHERE user_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(user_id), max(1, min(int(limit), 100))),
        ).fetchall()
        return [_row_dict(row) for row in rows]
    finally:
        conn.close()


def mark_notification_read(user_id: int, notification_id: int) -> bool:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        cursor = conn.execute(
            "UPDATE user_notifications SET read_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND user_id = ? AND read_at IS NULL",
            (int(notification_id), int(user_id)),
        )
        conn.commit()
        return bool(cursor.rowcount)
    finally:
        conn.close()


def mark_all_notifications_read(user_id: int) -> int:
    ensure_schema()
    conn = get_connection(AIDERMY_DB)
    try:
        cursor = conn.execute(
            "UPDATE user_notifications SET read_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND read_at IS NULL",
            (int(user_id),),
        )
        conn.commit()
        return int(cursor.rowcount or 0)
    finally:
        conn.close()


