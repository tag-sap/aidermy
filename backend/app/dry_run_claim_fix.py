# dry_run_claim_fix.py
# Dry-run исправления direction: прогоняет ВСЕ claims через новый validation
# (claim_direction.validate_claim) и делит на HIGH/MEDIUM/LOW.
#
# НИЧЕГО не применяет к БД. Только пишет отчёт.

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from .claim_direction import validate_claim
from .correct_ingredient_claims import _affected_products, _load_claims
from .database import AIDERMY_DB, get_connection
from .scoring_config import SCORING_CONFIG_VERSION


def _run() -> Dict[str, Any]:
    conn = get_connection(AIDERMY_DB)
    claims = _load_claims(conn)
    conn.close()
    affected = _affected_products()

    flips: List[Dict[str, Any]] = []      # HIGH_CONFIDENCE (можно авто-исправить)
    rejects: List[Dict[str, Any]] = []    # MEDIUM_CONFIDENCE (ручная проверка)

    for c in claims:
        verdict, corrected, reason = validate_claim(
            c["property_name"], c["direction"], c["evidence_level"], c["confidence"]
        )
        rec = {
            "ingredient": c["normalized_name"],
            "axis": c["property_name"],
            "old_direction": c["direction"],
            "new_direction": corrected,
            "evidence": c["evidence_level"],
            "reason": reason,
            "confidence": c["confidence"],
            "affected_products": affected.get(c["normalized_name"], 0),
        }
        if verdict == "flip":
            rec["tier"] = "HIGH_CONFIDENCE"
            flips.append(rec)
        elif verdict == "reject":
            rec["tier"] = "MEDIUM_CONFIDENCE"
            rejects.append(rec)

    flip_by_axis = Counter(f["axis"] for f in flips)
    reject_by_axis = Counter(r["axis"] for r in rejects)
    flips.sort(key=lambda x: (-x["affected_products"], -(x["confidence"] or 0)))
    rejects.sort(key=lambda x: (-x["affected_products"], -(x["confidence"] or 0)))

    return {
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "total_claims": len(claims),
        "flip_count": len(flips),
        "reject_count": len(rejects),
        "ok_count": len(claims) - len(flips) - len(rejects),
        "flip_by_axis": dict(flip_by_axis),
        "reject_by_axis": dict(reject_by_axis),
        "high_confidence": flips,
        "medium_confidence": rejects,
    }


def _md(r: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("# Enrichment Direction Fix — Dry Run\n")
    L.append(f"- config: {r['scoring_config_version']} (НЕ меняется)")
    L.append(f"- total claims: {r['total_claims']}")
    L.append(f"- HIGH_CONFIDENCE (авто-flip): **{r['flip_count']}**")
    L.append(f"- MEDIUM_CONFIDENCE (ручная проверка/reject): **{r['reject_count']}**")
    L.append(f"- LOW (ok, без изменений): {r['ok_count']}\n")
    L.append("flip by axis: " + json.dumps(r["flip_by_axis"], ensure_ascii=False))
    L.append("reject by axis: " + json.dumps(r["reject_by_axis"], ensure_ascii=False))
    L.append("")

    L.append("## HIGH_CONFIDENCE (предлагается авто-исправить, примеры)\n")
    L.append("| ingredient | axis | old | new | conf | products | evidence |\n|---|---|---|---|---|---|---|")
    for s in r["high_confidence"][:30]:
        L.append(f"| {s['ingredient'][:32]} | {s['axis']} | {s['old_direction']} | {s['new_direction']} "
                 f"| {s['confidence']} | {s['affected_products']} | {s['evidence'][:60]} |")
    L.append("")

    L.append("## MEDIUM_CONFIDENCE (оставить на проверку, примеры)\n")
    L.append("| ingredient | axis | old | new | conf | products | evidence |\n|---|---|---|---|---|---|---|")
    for s in r["medium_confidence"][:15]:
        L.append(f"| {s['ingredient'][:32]} | {s['axis']} | {s['old_direction']} | {s['new_direction']} "
                 f"| {s['confidence']} | {s['affected_products']} | {s['evidence'][:60]} |")
    return "\n".join(L)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/var/www/aidermy/calibration")
    args = p.parse_args()
    report = _run()
    out = Path(args.out)
    (out / "enrichment_direction_fix_dry_run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "enrichment_direction_fix_dry_run.md").write_text(_md(report), encoding="utf-8")
    print(f"total claims: {report['total_claims']}")
    print(f"flip (HIGH): {report['flip_count']}  reject (MEDIUM): {report['reject_count']}  ok (LOW): {report['ok_count']}")
    print(f"flip by axis: {report['flip_by_axis']}")
    print(f"reject by axis: {report['reject_by_axis']}")
    print(f"wrote: {out / 'enrichment_direction_fix_dry_run.json'}")
    print(f"wrote: {out / 'enrichment_direction_fix_dry_run.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
