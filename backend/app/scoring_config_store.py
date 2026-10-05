# scoring_config_store.py
# Версионированное DB-хранилище production-конфигурации Score Engine.
# Позволяет применить/откатить candidate config без перезапуска сервиса,
# с audit log и историей версий. Не меняет формулы scoring — только
# runtime-значения реально параметризованных параметров (saturation_scale).
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import AIDERMY_DB, get_connection

DEFAULT_SATURATION_SCALE = 1.5
BASE_VERSION = "1.4.0"

# Разрешённые к изменению runtime-параметры (sandbox candidate / production apply).
ALLOWED_PARAM_KEYS = {"saturation_scale"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bump_version(version: str) -> str:
    parts = version.split(".")
    try:
        nums = [int(p) for p in parts]
        nums[-1] += 1
        return ".".join(str(n) for n in nums)
    except Exception:
        return version + ".1"


def ensure_config_tables() -> None:
    conn = get_connection(AIDERMY_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scoring_config_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT UNIQUE,
            config TEXT,
            note TEXT,
            applied_by TEXT,
            applied_at TEXT,
            previous_version TEXT,
            event TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scoring_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT,
            version TEXT,
            detail TEXT,
            author TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _seed() -> None:
    ensure_config_tables()
    conn = get_connection(AIDERMY_DB)
    conn.execute("PRAGMA busy_timeout = 30000")
    n = conn.execute("SELECT COUNT(*) FROM scoring_config_versions").fetchone()[0]
    if n == 0:
        conn.execute(
            "INSERT INTO scoring_config_versions "
            "(version, config, note, applied_by, applied_at, previous_version, event) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (BASE_VERSION, json.dumps({"saturation_scale": DEFAULT_SATURATION_SCALE}),
             "initial production config", "system", _now(), None, "seed"),
        )
        conn.commit()
    conn.close()


def get_production_config() -> Dict[str, Any]:
    _seed()
    conn = get_connection(AIDERMY_DB)
    row = conn.execute("SELECT * FROM scoring_config_versions ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row is None:
        return {"version": BASE_VERSION, "saturation_scale": DEFAULT_SATURATION_SCALE,
                "config": {"saturation_scale": DEFAULT_SATURATION_SCALE}}
    cfg = json.loads(row["config"]) if row["config"] else {"saturation_scale": DEFAULT_SATURATION_SCALE}
    return {
        "version": row["version"],
        "saturation_scale": cfg.get("saturation_scale", DEFAULT_SATURATION_SCALE),
        "config": cfg,
        "note": row["note"],
        "applied_by": row["applied_by"],
        "applied_at": row["applied_at"],
        "event": row["event"],
    }


def get_production_saturation_scale() -> float:
    try:
        return float(get_production_config().get("saturation_scale", DEFAULT_SATURATION_SCALE))
    except Exception:
        return DEFAULT_SATURATION_SCALE


def get_production_history() -> List[Dict[str, Any]]:
    _seed()
    conn = get_connection(AIDERMY_DB)
    rows = conn.execute("SELECT * FROM scoring_config_versions ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return [{k: row[k] for k in row.keys()} for row in rows]


def get_audit_log(limit: int = 100) -> List[Dict[str, Any]]:
    ensure_config_tables()
    conn = get_connection(AIDERMY_DB)
    rows = conn.execute("SELECT * FROM scoring_audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [{k: row[k] for k in row.keys()} for row in rows]


def validate_production_config(config: Dict[str, Any]) -> Optional[str]:
    """Возвращает строку с ошибкой или None, если конфиг валиден."""
    if not isinstance(config, dict):
        return "config должен быть объектом"
    for k in config.keys():
        if k not in ALLOWED_PARAM_KEYS:
            return f"неизвестный параметр: {k} (разрешены: {sorted(ALLOWED_PARAM_KEYS)})"
    if "saturation_scale" in config:
        try:
            s = float(config["saturation_scale"])
        except (TypeError, ValueError):
            return "saturation_scale должен быть числом"
        if not (0.1 <= s <= 20.0):
            return "saturation_scale должен быть в диапазоне 0.1..20.0"
    return None


def apply_production_config(config: Dict[str, Any], note: str, applied_by: str) -> Dict[str, Any]:
    _seed()
    current = get_production_config()
    new_version = _bump_version(current["version"])
    conn = get_connection(AIDERMY_DB)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute(
        "INSERT INTO scoring_config_versions "
        "(version, config, note, applied_by, applied_at, previous_version, event) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_version, json.dumps(config, ensure_ascii=False), note, applied_by, _now(),
         current["version"], "apply"),
    )
    conn.execute(
        "INSERT INTO scoring_audit_log (event, version, detail, author, created_at) VALUES (?, ?, ?, ?, ?)",
        ("apply_config", new_version,
         json.dumps({"from": current["version"], "to": new_version, "config": config}, ensure_ascii=False),
         applied_by, _now()),
    )
    conn.commit()
    conn.close()
    return get_production_config()


def rollback_production_config(note: str, applied_by: str) -> Dict[str, Any]:
    _seed()
    conn = get_connection(AIDERMY_DB)
    conn.execute("PRAGMA busy_timeout = 30000")
    rows = conn.execute("SELECT * FROM scoring_config_versions ORDER BY id DESC LIMIT 2").fetchall()
    if len(rows) < 2:
        conn.close()
        return get_production_config()
    current, prev = rows[0], rows[1]
    new_version = _bump_version(current["version"])
    conn.execute(
        "INSERT INTO scoring_config_versions "
        "(version, config, note, applied_by, applied_at, previous_version, event) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_version, prev["config"], note or f"rollback to {prev['version']}", applied_by, _now(),
         current["version"], "rollback"),
    )
    conn.execute(
        "INSERT INTO scoring_audit_log (event, version, detail, author, created_at) VALUES (?, ?, ?, ?, ?)",
        ("rollback_config", new_version,
         json.dumps({"from": current["version"], "to": prev["version"]}, ensure_ascii=False),
         applied_by, _now()),
    )
    conn.commit()
    conn.close()
    return get_production_config()

