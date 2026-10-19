"""Удаление аккаунта и связанных персональных данных.

Удаление выполняется на сервере по идентификатору из токена: клиент не может
передать чужой user_id. Все связанные записи удаляются в одной транзакции
PostgreSQL, чтобы ошибка не оставила «половину» данных.

Платёжные/фискальные записи: сейчас реальных платежей в проекте нет. При
подключении ЮKassa чеки и платежи нужно будет сохранять в сроки, установленные
законодательством, и удалять только персональные данные, а не фискальные записи.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from .database import AIDERMY_DB, get_connection

# Таблицы, где user_id — персональная привязка.
ACCOUNT_TABLES = (
    "analysis",
    "shelf_products",
    "routines",
    "user_profiles",
    "user_product_images",
    "oauth_accounts",
    "recommendation_feedback",
    "shelf_removal_feedback",
    "review_helpful_votes",
    "reviews",
    "check_history",
    "balance_transactions",
    "pending_products",
    "user_consents",
)


def _ensure_consents_table() -> None:
    try:
        from .consents import ensure_user_consents_table

        ensure_user_consents_table()
    except Exception:
        pass


def delete_user_account(user_id: int) -> Dict[str, Any]:
    """Удаляет аккаунт и связанные данные. Возвращает статистику удаления."""
    if not user_id:
        raise ValueError("user_id обязателен")

    _ensure_consents_table()

    deleted: Dict[str, int] = {}

    if os.getenv("SUPABASE_DATABASE_URL"):
        from .postgres_connection import get_postgres_connection

        with get_postgres_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    for table in ACCOUNT_TABLES:
                        cur.execute(
                            f"DELETE FROM public.{table} WHERE user_id = %s", (user_id,)
                        )
                        deleted[table] = cur.rowcount
                    # Гостевые сессии: убираем ссылку на удалённый аккаунт.
                    cur.execute(
                        "UPDATE public.guest_sessions SET claimed_by = NULL "
                        "WHERE claimed_by = %s",
                        (user_id,),
                    )
                    cur.execute("DELETE FROM public.users WHERE id = %s", (user_id,))
                    deleted["users"] = cur.rowcount
        return {"deleted": deleted, "total": sum(deleted.values())}

    # SQLite-фолбэк (локальная разработка).
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    try:
        for table in ACCOUNT_TABLES:
            try:
                cursor.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
                deleted[table] = cursor.rowcount
            except Exception:
                deleted[table] = 0
        try:
            cursor.execute(
                "UPDATE guest_sessions SET claimed_by = NULL WHERE claimed_by = ?", (user_id,)
            )
        except Exception:
            pass
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        deleted["users"] = cursor.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return {"deleted": deleted, "total": sum(deleted.values())}
