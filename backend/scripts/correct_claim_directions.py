#!/usr/bin/env python3
"""Коррекция подтверждённых ошибок направления в ingredient_claims (идемпотентно).

Добавляет корректирующие claims (source_type='curated_correction', provenance в
source_title), не удаляя исторические записи. Медианная агрегация выбирает
направление с высшей confidence, поэтому корректирующий claim перекрывает
ошибочный. Запуск: python scripts/correct_claim_directions.py [--dry-run]
"""
import hashlib, sys, os
from pathlib import Path
from datetime import datetime, timezone
import psycopg
from dotenv import load_dotenv

# (normalized_name, property_name, direction, strength, confidence, rationale)
CORRECTIONS = [
    ("niacinamide", "brightening", "positive", 0.7, 0.9,
     "Niacinamide reduces hyperpigmentation (brightens), not increases it"),
    ("sodium hydroxide", "barrier_support", "positive", 0.0, 0.9,
     "pH adjuster used in trace amounts; no barrier harm"),
    ("triethanolamine", "barrier_support", "positive", 0.0, 0.8,
     "pH adjuster; no barrier harm"),
    ("dimethicone", "barrier_support", "positive", 0.5, 0.85,
     "Occlusive silicone supports barrier function"),
]

SOURCE_TYPE = "curated_correction"
RESEARCH_VERSION = "correction-2026-10-18"


def main() -> int:
    dry = "--dry-run" in sys.argv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    conn = psycopg.connect(os.environ["SUPABASE_DATABASE_URL"])
    cur = conn.cursor()
    added = 0
    for name, prop, direction, strength, confidence, rationale in CORRECTIONS:
        cur.execute("SELECT id FROM ingredients_catalog WHERE normalized_name=%s", (name,))
        r = cur.fetchone()
        if not r:
            print(f"  {name}: not found, skip"); continue
        iid = r[0]
        cur.execute(
            "SELECT id FROM ingredient_claims WHERE ingredient_id=%s AND property_name=%s "
            "AND direction=%s AND source_type='curated_correction'", (iid, prop, direction))
        if cur.fetchone():
            print(f"  {name}/{prop}: already corrected, skip"); continue
        if dry:
            print(f"  [dry] {name}/{prop} -> {direction}"); added += 1; continue
        h = hashlib.sha256(f"{iid}|{prop}|{direction}|correction".encode()).hexdigest()[:32]
        cur.execute(
            "INSERT INTO ingredient_claims (ingredient_id, property_name, direction, strength, "
            "confidence, evidence_level, source_type, source_title, researched_at, research_version, source_hash) "
            "VALUES (%s,%s,%s,%s,%s,moderate,curated_correction,%s,%s,%s,%s)",
            (iid, prop, direction, strength, confidence, rationale, datetime.now(timezone.utc), RESEARCH_VERSION, h))
        added += 1
        print(f"  {name}/{prop} -> {direction} (s={strength}, c={confidence})")
    conn.commit()
    cur.execute("SELECT count(*) FROM ingredient_claims WHERE source_type='curated_correction'")
    print(("[dry] " if dry else "") + "corrections added=%d; total curated_correction=%d" % (added, cur.fetchone()[0]))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
