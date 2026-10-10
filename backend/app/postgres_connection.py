"""Изолированное подключение к PostgreSQL/Supabase."""
import os

import psycopg
from psycopg.rows import dict_row


def get_postgres_connection() -> psycopg.Connection:
    """Открывает соединение с PostgreSQL; не меняет SQLite-подключение."""
    database_url = os.getenv("SUPABASE_DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Не задана переменная окружения SUPABASE_DATABASE_URL"
        )

    return psycopg.connect(
        database_url,
        connect_timeout=10,
        row_factory=dict_row,
    )
