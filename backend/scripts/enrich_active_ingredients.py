#!/usr/bin/env python3
"""Целевое обогащение пропущенных активных ингредиентов (без LLM).

Идемпотентно добавляет устоявшиеся эффекты часто встречающихся активов,
отсутствующих в ingredients_catalog (пептиды, центелла, ретиноиды, керамиды,
производные витаминов C/E). Силы/уверенности консервативны, т.к. концентрация
в каждом продукте неизвестна. Происхождение: source_type='curated_science',
без выдуманных URL. Запуск: python scripts/enrich_active_ingredients.py [--dry-run]
"""
import hashlib, sys
from pathlib import Path
from datetime import datetime, timezone
import psycopg
from dotenv import load_dotenv

# (canonical_key, inci_name, [(property, direction, strength, confidence), ...])
ENRICH = [
    ("palmitoyl tripeptide-5", "Palmitoyl Tripeptide-5", [("barrier", "positive", 0.5, 0.5)]),
    ("centella asiatica extract", "Centella Asiatica Extract", [("irritation", "negative", 0.5, 0.6)]),
    ("centella asiatica", "Centella Asiatica", [("irritation", "negative", 0.5, 0.6)]),
    ("centella asiatica root extract", "Centella Asiatica Root Extract", [("irritation", "negative", 0.5, 0.6)]),
    ("centella asiatica leaf water", "Centella Asiatica Leaf Water", [("irritation", "negative", 0.4, 0.5)]),
    ("centella asiatica leaf vesicles", "Centella Asiatica Leaf Vesicles", [("irritation", "negative", 0.4, 0.5)]),
    ("sh-oligopeptide-1", "sh-Oligopeptide-1", [("barrier", "positive", 0.5, 0.5)]),
    ("acetyl octapeptide-3", "Acetyl Octapeptide-3", [("barrier", "positive", 0.4, 0.5)]),
    ("retinal", "Retinal", [("pigmentation", "negative", 0.5, 0.5), ("irritation", "positive", 0.3, 0.4)]),
    ("ceramide 6 ii", "Ceramide 6 II", [("barrier", "positive", 0.6, 0.7)]),
    ("hexapeptide-11", "Hexapeptide-11", [("barrier", "positive", 0.4, 0.4)]),
    ("hexapeptide-2", "Hexapeptide-2", [("barrier", "positive", 0.4, 0.4)]),
    ("palmitoyl tripeptide-8", "Palmitoyl Tripeptide-8", [("barrier", "positive", 0.4, 0.4)]),
    ("palmitoyl dipeptide-10", "Palmitoyl Dipeptide-10", [("barrier", "positive", 0.4, 0.4)]),
    ("sh-oligopeptide-2", "sh-Oligopeptide-2", [("barrier", "positive", 0.4, 0.4)]),
    ("sh-polypeptide-1", "sh-Polypeptide-1", [("barrier", "positive", 0.4, 0.4)]),
    ("sh-polypeptide-11", "sh-Polypeptide-11", [("barrier", "positive", 0.4, 0.4)]),
    ("ethyl ascorbic acid", "Ethyl Ascorbic Acid", [("pigmentation", "negative", 0.5, 0.5)]),
    ("ascorbyl propyl hyaluronate", "Ascorbyl Propyl Hyaluronate", [("pigmentation", "negative", 0.4, 0.4)]),
    ("ascorbic acid polypeptide", "Ascorbic Acid Polypeptide", [("pigmentation", "negative", 0.4, 0.4)]),
    ("tocopherol acetate", "Tocopherol Acetate", [("barrier", "positive", 0.4, 0.5)]),
    ("phloretin", "Phloretin", [("pigmentation", "negative", 0.4, 0.5)]),
    ("hydroxydecyl ubiquinone", "Hydroxydecyl Ubiquinone", [("barrier", "positive", 0.4, 0.4)]),
    ("copper palmitoyl heptapeptide-14", "Copper Palmitoyl Heptapeptide-14", [("barrier", "positive", 0.4, 0.4)]),
]

SOURCE_TYPE = "curated_science"
SOURCE_TITLE = "Established cosmetic ingredient effect (curated, conservative; no specific citation)"
RESEARCH_VERSION = "curated-2026-10-18"


def main() -> int:
    dry = "--dry-run" in sys.argv
    import os
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    conn = psycopg.connect(os.environ["SUPABASE_DATABASE_URL"])
    cur = conn.cursor()
    added_ing = 0
    added_claim = 0
    for key, inci, claims in ENRICH:
        cur.execute("SELECT id FROM ingredients_catalog WHERE normalized_name=%s", (key,))
        row = cur.fetchone()
        if row is None:
            added_ing += 1
            if dry:
                print(f"[dry] add ingredient: {key}")
                continue
            cur.execute(
                "INSERT INTO ingredients_catalog (inci_name, canonical_name, normalized_name, evidence_level, knowledge_confidence) "
                "VALUES (%s,%s,%s,'moderate',0.5) ON CONFLICT (normalized_name) DO NOTHING",
                (inci, inci, key),
            )
            cur.execute("SELECT id FROM ingredients_catalog WHERE normalized_name=%s", (key,))
            row = cur.fetchone()
        iid = row[0]
        for prop, direction, strength, confidence in claims:
            cur.execute(
                "SELECT id FROM ingredient_claims WHERE ingredient_id=%s AND property_name=%s AND direction=%s",
                (iid, prop, direction),
            )
            if cur.fetchone() is None:
                added_claim += 1
                if not dry:
                    h = hashlib.sha256(f"{iid}|{prop}|{direction}|{RESEARCH_VERSION}".encode()).hexdigest()[:32]
                    cur.execute(
                        "INSERT INTO ingredient_claims (ingredient_id, property_name, direction, strength, confidence, evidence_level, source_type, source_title, researched_at, research_version, source_hash) "
                        "VALUES (%s,%s,%s,%s,%s,'moderate',%s,%s,%s,%s,%s)",
                        (iid, prop, direction, strength, confidence, SOURCE_TYPE, SOURCE_TITLE, datetime.now(timezone.utc), RESEARCH_VERSION, h),
                    )
    conn.commit()
    cur.execute("SELECT count(*) FROM ingredients_catalog")
    n_ing = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM ingredient_claims")
    n_claim = cur.fetchone()[0]
    print(f"{'[dry] ' if dry else ''}ingredients added={added_ing} claims added={added_claim}; catalog={n_ing} claims={n_claim}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
