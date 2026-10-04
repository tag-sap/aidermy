#!/usr/bin/env python3
"""Phase 3 — clear legacy user check state from production DB.

Idempotent, transactional cleanup of the two tables that are *exclusively*
user check/report state:

  * `analysis`      — score/verdict/deterministic_json/report/what_good/
                      what_caution/how_to_use/expectations/profile_snapshot.
  * `check_history` — legacy check history (summary/ai_report/score/...).

Everything else is preserved untouched: users, user_profiles, shelf_products,
products, ingredients_catalog, ingredient_claims, allergen_sensitizer,
ingredient_interactions, ingredient_classes, and the static product model
(product_models / product_ppms / product_vectors).

Usage:
    cd /var/www/aidermy/backend
    ./venv/bin/python3 scripts/clear_legacy_check_data.py
"""
import sqlite3

DB = "/var/www/aidermy/backend/aidermy.db"

PRESERVE = [
    "users", "user_profiles", "shelf_products",
    "ingredients_catalog", "ingredient_claims", "allergen_sensitizer",
    "ingredient_interactions", "ingredient_classes",
]
CLEAR = ["analysis", "check_history"]


def _count(cur, table):
    return cur.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    before_clear = {t: _count(cur, t) for t in CLEAR}
    before_preserve = {t: _count(cur, t) for t in PRESERVE}

    cur.execute("BEGIN")
    try:
        for t in CLEAR:
            cur.execute(f'DELETE FROM "{t}"')
    except Exception:
        conn.rollback()
        raise

    ok = True
    for t in CLEAR:
        if _count(cur, t) != 0:
            ok = False
            print(f"MISMATCH {t}: {_count(cur, t)} != 0")
    for t in PRESERVE:
        if _count(cur, t) != before_preserve[t]:
            ok = False
            print(f"MISMATCH {t}: before={before_preserve[t]} after={_count(cur, t)}")

    if not ok:
        conn.rollback()
        raise SystemExit("ROLLBACK — preserved table changed; nothing deleted")

    conn.commit()

    print("CLEANUP OK")
    for t, n in before_clear.items():
        print(f"  deleted {t}: {n} rows")
    print("preserved (unchanged):")
    for t in PRESERVE:
        print(f"  {t}: {_count(cur, t)}")
    conn.close()


if __name__ == "__main__":
    main()
