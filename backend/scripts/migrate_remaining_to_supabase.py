#!/usr/bin/env python3
"""Идемпотентный перенос остатков пользовательских данных SQLite -> Supabase.

Переносит из резервной SQLite-базы недостающие строки shelf_products и
balance_transactions (по натуральному ключу / id). Повторный запуск безопасен.

Запуск (из backend/):
  python scripts/migrate_remaining_to_supabase.py <path-to-sqlite-backup>
"""
import sqlite3
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> int:
    backup = sys.argv[1] if len(sys.argv) > 1 else "aidermy.db.bak-analysis-pg-20261010-124204"
    sq = sqlite3.connect(backup)
    sq.row_factory = sqlite3.Row
    scur = sq.cursor()

    pg = psycopg.connect(os.environ["SUPABASE_DATABASE_URL"])
    pcur = pg.cursor()

    # shelf_products (натуральный ключ user_id + product_id)
    scur.execute("SELECT user_id, product_id, category, notes, routine_id, cabinet, score, added_at FROM shelf_products")
    pcur.execute("SELECT user_id, product_id FROM shelf_products")
    p_keys = {(r[0], r[1]) for r in pcur.fetchall()}
    n = 0
    for r in scur.fetchall():
        if (r["user_id"], r["product_id"]) in p_keys:
            continue
        pcur.execute(
            "INSERT INTO shelf_products (user_id, product_id, category, notes, routine_id, cabinet, score, added_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id, product_id) DO NOTHING",
            (r["user_id"], r["product_id"], r["category"], r["notes"], r["routine_id"], r["cabinet"], r["score"], r["added_at"]),
        )
        n += 1
    print(f"shelf_products перенесено: {n}")

    # balance_transactions (по id)
    scur.execute("SELECT id, user_id, type, amount, note, created_at FROM balance_transactions")
    pcur.execute("SELECT id FROM balance_transactions")
    p_ids = {r[0] for r in pcur.fetchall()}
    n = 0
    for r in scur.fetchall():
        if r["id"] in p_ids:
            continue
        pcur.execute(
            "INSERT INTO balance_transactions (id, user_id, type, amount, note, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (r["id"], r["user_id"], r["type"], r["amount"], r["note"], r["created_at"]),
        )
        n += 1
    print(f"balance_transactions перенесено: {n}")

    pg.commit()
    for table in ("shelf_products", "balance_transactions"):
        pcur.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'), (SELECT MAX(id) FROM {table}))")
    pg.commit()
    sq.close()
    pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
