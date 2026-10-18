"""Гостевой сценарий айдерми: одна проверка одного средства за сеанс.

Сессия хранится на сервере и идентифицируется криптографически стойким
непрозрачным токеном (в БД — только SHA-256 от него). Токен живёт в памяти
фронтенда и не попадает в браузерное хранилище, поэтому после перезагрузки
или нового визита гостевой прогресс не восстанавливается.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .database import AIDERMY_DB, get_connection

GUEST_SESSION_TTL_MINUTES = 60


class GuestSessionError(Exception):
    """Ожидаемая ошибка гостевого сценария (преобразуется в HTTP в роутере)."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def ensure_guest_sessions_table() -> None:
    """Идемпотентно создаёт таблицу гостевых сессий."""
    if os.getenv("SUPABASE_DATABASE_URL"):
        from .postgres_connection import get_postgres_connection

        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public.guest_sessions (
                        id BIGSERIAL PRIMARY KEY,
                        token_hash TEXT NOT NULL UNIQUE,
                        profile_json TEXT NOT NULL,
                        check_used_at TIMESTAMPTZ,
                        result_json TEXT,
                        report_json TEXT,
                        claimed_by BIGINT,
                        claimed_at TIMESTAMPTZ,
                        claimed_analysis_id BIGINT,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        expires_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_guest_sessions_expires "
                    "ON public.guest_sessions (expires_at)"
                )
            conn.commit()
        return

    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS guest_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            profile_json TEXT NOT NULL,
            check_used_at TIMESTAMP,
            result_json TEXT,
            report_json TEXT,
            claimed_by INTEGER,
            claimed_at TIMESTAMP,
            claimed_analysis_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def normalize_guest_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Приводит профиль анкеты к виду, пригодному для Score Engine и отчёта."""
    normalized = dict(profile or {})
    structured = normalized.get("structured")
    if isinstance(structured, dict) and not str(normalized.get("skin_type") or "").strip():
        normalized["skin_type"] = str(structured.get("skin_type") or "").strip()
    return normalized


def validate_guest_profile(profile: Dict[str, Any]) -> None:
    """Профиль должен быть результатом заполненной анкеты, а не пустышкой.

    Анкета формирует `structured` (тип кожи, проблемы, лечение, процедуры) —
    именно он обязателен: без него проверка была бы «по умолчанию», а не по
    реально заполненному профилю.
    """
    profile = profile or {}
    structured = profile.get("structured")
    if not isinstance(structured, dict):
        raise GuestSessionError("Сначала заполните профиль кожи", 400)
    skin = str(profile.get("skin_type") or "").strip()
    structured_skin = str(structured.get("skin_type") or "").strip()
    if not skin and not structured_skin:
        raise GuestSessionError("Сначала заполните профиль кожи", 400)
    if not isinstance(structured.get("concerns", []), list):
        raise GuestSessionError("Некорректный профиль кожи", 400)


def create_guest_session(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Создаёт гостевой сеанс. Возвращает непрозрачный токен и срок действия."""
    profile = normalize_guest_profile(profile)
    validate_guest_profile(profile)
    ensure_guest_sessions_table()

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=GUEST_SESSION_TTL_MINUTES)

    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO guest_sessions (token_hash, profile_json, expires_at) VALUES (?, ?, ?)",
        (_hash_token(token), json.dumps(profile, ensure_ascii=False), expires_at),
    )
    conn.commit()
    conn.close()

    return {
        "guest_token": token,
        "expires_at": expires_at.isoformat(),
        "ttl_minutes": GUEST_SESSION_TTL_MINUTES,
    }


def _load_row(token: str) -> Optional[Dict[str, Any]]:
    token = (token or "").strip()
    if not token:
        return None
    ensure_guest_sessions_table()
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM guest_sessions WHERE token_hash = ?", (_hash_token(token),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _is_expired(row: Dict[str, Any]) -> bool:
    expires_at = row.get("expires_at")
    if expires_at is None:
        return True
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def load_guest_session(token: str) -> Dict[str, Any]:
    """Возвращает активную сессию или бросает GuestSessionError."""
    row = _load_row(token)
    if not row:
        raise GuestSessionError("Гостевой сеанс не найден. Начните заново.", 401)
    if _is_expired(row):
        raise GuestSessionError("Гостевой сеанс истёк. Начните заново.", 410)
    return row


def consume_guest_check(token: str) -> Dict[str, Any]:
    """Атомарно расходует единственную гостевую проверку.

    Параллельные запросы не могут оба пройти: UPDATE с условием
    `check_used_at IS NULL` затрагивает ровно одну строку.
    """
    session = load_guest_session(token)
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE guest_sessions SET check_used_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND check_used_at IS NULL AND expires_at > CURRENT_TIMESTAMP",
        (session["id"],),
    )
    conn.commit()
    updated = cursor.rowcount
    conn.close()
    if not updated:
        raise GuestSessionError(
            "Гостевая проверка уже использована. Зарегистрируйтесь, чтобы продолжить.",
            409,
        )
    session["profile"] = json.loads(session.get("profile_json") or "{}")
    return session


def refund_guest_check(session_id: int) -> None:
    """Возвращает попытку, если проверка завершилась технической ошибкой."""
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE guest_sessions SET check_used_at = NULL "
        "WHERE id = ? AND result_json IS NULL AND claimed_by IS NULL",
        (session_id,),
    )
    conn.commit()
    conn.close()


def store_guest_result(session_id: int, payload: Dict[str, Any]) -> None:
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE guest_sessions SET result_json = ? WHERE id = ?",
        (json.dumps(payload, ensure_ascii=False), session_id),
    )
    conn.commit()
    conn.close()


def get_guest_result(token: str) -> Dict[str, Any]:
    session = load_guest_session(token)
    payload = json.loads(session.get("result_json") or "{}")
    if not payload:
        raise GuestSessionError("Результат гостевой проверки не найден", 404)
    payload["_session"] = session
    return payload


def save_guest_report(token: str, report: Dict[str, Any]) -> None:
    session = load_guest_session(token)
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE guest_sessions SET report_json = ? WHERE id = ?",
        (json.dumps(report, ensure_ascii=False), session["id"]),
    )
    conn.commit()
    conn.close()


def get_cached_guest_report(token: str) -> Optional[Dict[str, Any]]:
    session = load_guest_session(token)
    cached = json.loads(session.get("report_json") or "{}")
    return cached or None


def claim_guest_result(token: str, user_id: int) -> Dict[str, Any]:
    """Привязывает единственный гостевой результат к вошедшему пользователю.

    Захват атомарный (`claimed_by IS NULL`): один результат нельзя присоединить
    к двум аккаунтам. Повторный вызов тем же пользователем идемпотентен.
    """
    session = load_guest_session(token)
    payload = json.loads(session.get("result_json") or "{}")
    if not payload:
        raise GuestSessionError("Результат гостевой проверки не найден", 404)

    if session.get("claimed_by") is not None:
        if int(session["claimed_by"]) == int(user_id):
            return {
                "already_claimed": True,
                "analysis_id": session.get("claimed_analysis_id"),
                "session_id": session["id"],
                "payload": payload,
            }
        raise GuestSessionError("Этот результат уже сохранён в другом аккаунте", 409)

    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE guest_sessions SET claimed_by = ?, claimed_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND claimed_by IS NULL AND expires_at > CURRENT_TIMESTAMP",
        (user_id, session["id"]),
    )
    conn.commit()
    updated = cursor.rowcount
    conn.close()

    if not updated:
        fresh = _load_row(token)
        if fresh and fresh.get("claimed_by") is not None:
            if int(fresh["claimed_by"]) == int(user_id):
                return {
                    "already_claimed": True,
                    "analysis_id": fresh.get("claimed_analysis_id"),
                    "session_id": fresh["id"],
                    "payload": payload,
                }
            raise GuestSessionError("Этот результат уже сохранён в другом аккаунте", 409)
        raise GuestSessionError("Не удалось сохранить результат", 409)

    return {
        "already_claimed": False,
        "analysis_id": None,
        "session_id": session["id"],
        "payload": payload,
    }


def finalize_guest_claim(session_id: int, analysis_id: Optional[int]) -> None:
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE guest_sessions SET claimed_analysis_id = ? WHERE id = ?",
        (analysis_id, session_id),
    )
    conn.commit()
    conn.close()


def release_guest_claim(session_id: int) -> None:
    """Откатывает захват, если сохранить анализ не удалось."""
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE guest_sessions SET claimed_by = NULL, claimed_at = NULL "
        "WHERE id = ? AND claimed_analysis_id IS NULL",
        (session_id,),
    )
    conn.commit()
    conn.close()


# Ограничение создания гостевых сеансов: защита от автоматического перебора
# и безлимитного расхода AI-ресурсов через /api/guest/session.
_SESSION_RATE: Dict[str, list] = {}
GUEST_SESSION_RATE_LIMIT = 5
GUEST_SESSION_RATE_WINDOW_SECONDS = 3600


def rate_limit_sessions(ip: str) -> bool:
    import time as _time

    now = _time.time()
    key = (ip or "unknown").strip() or "unknown"
    bucket = _SESSION_RATE.setdefault(key, [])
    bucket[:] = [t for t in bucket if now - t < GUEST_SESSION_RATE_WINDOW_SECONDS]
    if len(bucket) >= GUEST_SESSION_RATE_LIMIT:
        return False
    bucket.append(now)
    return True
