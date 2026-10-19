"""Хранение согласий пользователя с юридическими документами.

Согласие фиксируется только на сервере: клиент не может «нарисовать» факт
согласия, он лишь передаёт тип согласия, контекст и версию документа.
Версия всегда сверяется с серверным значением — старую версию подставить нельзя.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .database import AIDERMY_DB, get_connection
from .legal_documents import CONSENT_TYPES, require_document_version


class ConsentError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def ensure_user_consents_table() -> None:
    if os.getenv("SUPABASE_DATABASE_URL"):
        from .postgres_connection import get_postgres_connection

        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public.user_consents (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        consent_type TEXT NOT NULL,
                        document_version TEXT NOT NULL,
                        context TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_consents_user "
                    "ON public.user_consents (user_id, consent_type)"
                )
            conn.commit()
        return

    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_consents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            consent_type TEXT NOT NULL,
            document_version TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def record_consent(
    user_id: int,
    consent_type: str,
    context: str = "",
    client_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Записывает согласие. Версия берётся с сервера, а не от клиента."""
    ctype = (consent_type or "").strip()
    if ctype not in CONSENT_TYPES:
        raise ConsentError("Неизвестный тип согласия", 422)

    # Для payment_terms действует версия оферты, для privacy — версия политики.
    version = require_document_version("privacy" if ctype == "privacy" else "offer")

    if client_version and client_version != version:
        raise ConsentError("Версия документа устарела. Обновите страницу и повторите.", 409)

    ensure_user_consents_table()
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_consents (user_id, consent_type, document_version, context) "
        "VALUES (?, ?, ?, ?)",
        (user_id, ctype, version, (context or "").strip()[:64]),
    )
    conn.commit()
    row = cursor.execute(
        "SELECT * FROM user_consents WHERE id = (SELECT MAX(id) FROM user_consents WHERE user_id = ?)",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_user_consents(user_id: int) -> Dict[str, str]:
    """Последняя версия принятого документа по каждому типу согласия."""
    ensure_user_consents_table()
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT consent_type, document_version, context, created_at FROM user_consents "
        "WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    result: Dict[str, str] = {}
    for row in rows:
        result[row["consent_type"]] = row["document_version"]
    return result


def consent_history(user_id: int) -> List[Dict[str, Any]]:
    ensure_user_consents_table()
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT consent_type, document_version, context, created_at FROM user_consents "
        "WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_current_consent(user_id: int, consent_type: str) -> bool:
    """Принята ли АКТУАЛЬНАЯ версия документа."""
    current = require_document_version("privacy" if consent_type == "privacy" else "offer")
    return get_user_consents(user_id).get(consent_type) == current
