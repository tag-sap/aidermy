import os

import pytest


def test_connection_requires_database_url(monkeypatch):
    from app.postgres_connection import get_postgres_connection

    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="SUPABASE_DATABASE_URL"):
        get_postgres_connection()


@pytest.mark.skipif(
    not os.getenv("SUPABASE_DATABASE_URL"),
    reason="SUPABASE_DATABASE_URL is not configured",
)
def test_supabase_connection_read_only():
    from app.postgres_connection import get_postgres_connection

    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("""
                SELECT
                    current_setting('transaction_read_only') AS read_only,
                    (SELECT count(*) FROM public.products) AS products_count,
                    (SELECT count(*) FROM public.analysis) AS analysis_count
            """)
            row = cur.fetchone()

        assert row["read_only"] == "on"
        assert row["products_count"] == 4481
        assert row["analysis_count"] == 67
        conn.rollback()
