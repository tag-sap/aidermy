#!/usr/bin/env python3
"""Эксперимент: влияние Phase 1 на калибровку Score Engine.

Сравнивает два режима на ОДНИХ И ТЕХ ЖЕ данных и одном сплите:
  baseline  — Phase 1 влияет на итоговый score (текущее production-поведение);
  no_phase1 — Phase 1 только диагностируется, score считает чистый Phase 2.

Production не меняется: режим включается флагом PHASE1_AFFECTS_SCORE
(по умолчанию 1). Скрипт переключает его только в памяти процесса.

Usage: python scripts/phase1_experiment.py [--seed N] [--phase test]
"""
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/var/www/aidermy/backend")
os.chdir("/var/www/aidermy/backend")

from dotenv import load_dotenv, dotenv_values  # noqa: E402
load_dotenv(".env")
import psycopg  # noqa: E402

import app.scoring_engine as SE  # noqa: E402
from app.calibration_profiles import CALIBRATION_PROFILES  # noqa: E402
from app.calibration_service import run_score_engine  # noqa: E402


def load_cases():
    conn = psycopg.connect(dotenv_values(".env")["SUPABASE_DATABASE_URL"])
    rows = conn.execute(
        """
        SELECT cr.product_id, cr.profile_id, cr.reference, p.name, p.ingredients, p.catalog_category
        FROM calibration_references cr JOIN products p ON p.id = cr.product_id
        WHERE p.catalog_category IS NOT NULL AND p.catalog_category <> 'Уход за губами'
          AND p.ingredients IS NOT NULL AND btrim(p.ingredients) <> ''
        """
    ).fetchall()
    conn.close()
    profiles = {p["id"]: p for p in CALIBRATION_PROFILES}
    cases, ref_map = [], {}
    for pid, prid, ref, name, ing, cat in rows:
        pr = profiles.get(prid)
        if not pr:
            continue
        cases.append({
            "product": {"id": pid, "name": (name or "").replace("\n", " ").strip(),
                        "category": cat or "", "ingredients": ing or ""},
            "profile": pr,
        })
        ref_map[f"{pid}:{prid}"] = json.loads(ref)
    return cases, ref_map


def split(cases, seed, ratios):
    by_product = defaultdict(list)
    for case in cases:
        by_product[case["product"]["id"]].append(case)
    products = list(by_product.keys())
    random.seed(seed)
    random.shuffle(products)
    n = len(products)
    a = int(n * ratios[0])
    b = int(n * (ratios[0] + ratios[1]))
    train, val, test = set(products[:a]), set(products[a:b]), set(products[b:])
    pick = lambda ids: [c for c in cases if c["product"]["id"] in ids]  # noqa: E731
    return pick(train), pick(val), pick(test)


def metrics(results, ref_map):
    deltas, abs_errors = [], []
    by_profile, by_category = defaultdict(list), defaultdict(list)
    blocks, coverage_hits, coverage_total = 0, 0, 0
    for r in results:
        key = f'{r["product"]["id"]}:{r["profile"]["id"]}'
        ref = ref_map.get(key)
        if not ref or ref.get("estimate") is None:
            continue
        d = r["score"] - ref["estimate"]
        deltas.append(d)
        abs_errors.append(abs(d))
        skin = ((r["profile"].get("structured") or {}).get("skin_type")) or "?"
        by_profile[skin].append(d)
        by_category[r["product"].get("category") or "?"].append(d)
        if (r.get("phase1_status") or "") == "blocked":
            blocks += 1
        lo, hi = ref.get("range_low"), ref.get("range_high")
        if lo is not None and hi is not None:
            coverage_total += 1
            if lo <= r["score"] <= hi:
                coverage_hits += 1
    n = len(deltas) or 1
    return {
        "n": len(deltas),
        "mae": round(sum(abs_errors) / n, 3),
        "median_abs_error": round(statistics.median(abs_errors), 3) if abs_errors else None,
        "signed": round(statistics.mean(deltas), 3) if deltas else None,
        "rmse": round(math.sqrt(sum(d * d for d in deltas) / n), 3),
        "over_rate": round(sum(1 for d in deltas if d > 0) / n, 3),
        "under_rate": round(sum(1 for d in deltas if d < 0) / n, 3),
        "coverage": round(coverage_hits / coverage_total, 3) if coverage_total else None,
        "blocked": blocks,
        "blocked_share": round(blocks / n, 3),
        "by_profile": {k: round(statistics.mean(v), 2) for k, v in sorted(by_profile.items(), key=lambda kv: -len(kv[1]))},
        "by_category": {k: round(statistics.mean(v), 2) for k, v in sorted(by_category.items(), key=lambda kv: -len(kv[1]))[:8]},
    }



def run_mode(cases, flag):
    SE.PHASE1_AFFECTS_SCORE = flag
    return run_score_engine(cases, config_override={"saturation_scale": 1.2})


def main():
    args = sys.argv[1:]
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 20261019
    phase = args[args.index("--phase") + 1] if "--phase" in args else "test"

    cases, ref_map = load_cases()
    train, val, test = split(cases, seed, [0.6, 0.2, 0.2])
    chosen = {"train": train, "val": val, "test": test}.get(phase, test)

    from app.score_version import SCORE_ENGINE_VERSION
    print(f"cases={len(chosen)} phase={phase} seed={seed} saturation=1.2 version={SCORE_ENGINE_VERSION}", flush=True)

    baseline = metrics(run_mode(chosen, True), ref_map)
    experimental = metrics(run_mode(chosen, False), ref_map)
    SE.PHASE1_AFFECTS_SCORE = True  # вернуть процесс в production-режим

    print("\n=== BASELINE (Phase 1 влияет) ===", flush=True)
    print(json.dumps(baseline, ensure_ascii=False, indent=1), flush=True)
    print("\n=== NO PHASE 1 (только диагностика) ===", flush=True)
    print(json.dumps(experimental, ensure_ascii=False, indent=1), flush=True)

    print("\n=== DIFF (no_phase1 - baseline) ===", flush=True)
    diff = {}
    for key in ("mae", "median_abs_error", "signed", "rmse", "over_rate", "under_rate", "coverage", "blocked", "blocked_share"):
        b, e = baseline.get(key), experimental.get(key)
        diff[key] = round((e - b), 3) if isinstance(b, (int, float)) and isinstance(e, (int, float)) else None
    print(json.dumps(diff, ensure_ascii=False, indent=1), flush=True)
    print("\nDONE", flush=True)


if __name__ == "__main__":
    main()
