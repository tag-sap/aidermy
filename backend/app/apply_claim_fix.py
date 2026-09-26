# apply_claim_fix.py
# Применяет ТОЛЬКО HIGH_CONFIDENCE flips (verdict='flip' из validate_claim).
# НЕ трогает MEDIUM (reject), LOW (ok), scoring config, weights, formula, floor.
#
# Перед изменением делает backup aidermy.db + копию dry-run JSON.

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .claim_direction import validate_claim
from .correct_ingredient_claims import _load_claims
from .database import AIDERMY_DB, get_connection


def run(apply: bool, out_dir: str) -> int:
    conn = get_connection(AIDERMY_DB)
    claims = _load_claims(conn)
    conn.close()

    flips: List[Dict[str, Any]] = []
    rejects: List[Dict[str, Any]] = []
    for c in claims:
        verdict, corrected, reason = validate_claim(
            c["property_name"], c["direction"], c["evidence_level"], c["confidence"]
        )
        if verdict == "flip":
            flips.append({
                "claim_id": c["id"], "ingredient": c["normalized_name"],
                "axis": c["property_name"], "old_direction": c["direction"],
                "new_direction": corrected, "evidence": c["evidence_level"],
                "confidence": c["confidence"],
            })
        elif verdict == "reject":
            rejects.append({
                "ingredient": c["normalized_name"], "axis": c["property_name"],
                "direction": c["direction"], "evidence": c["evidence_level"],
                "reason": reason, "confidence": c["confidence"],
                "why_not_auto_fix": "low confidence — нужна внешняя/ручная проверка",
            })

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"/root/aidermy_backups/{ts}_claimfix")
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(AIDERMY_DB, backup_dir / "aidermy.db.before.db")
    dry_src = Path(out_dir) / "enrichment_direction_fix_dry_run.json"
    if dry_src.exists():
        shutil.copy(dry_src, backup_dir / "enrichment_direction_fix_dry_run.json")

    if apply:
        conn = get_connection(AIDERMY_DB)
        try:
            conn.execute("BEGIN")
            for f in flips:
                conn.execute(
                    "UPDATE ingredient_claims SET direction = ? WHERE id = ?",
                    (f["new_direction"], f["claim_id"]),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    flip_by_axis = Counter(f["axis"] for f in flips)
    report = {
        "mode": "APPLY" if apply else "DRY-RUN",
        "timestamp": ts,
        "backup_dir": str(backup_dir),
        "flip_count": len(flips),
        "reject_count": len(rejects),
        "flip_by_axis": dict(flip_by_axis),
        "applied_flips": flips,
        "medium_claims": rejects,
    }

    out = Path(out_dir)
    (out / "claim_fix_apply_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "medium_claims_review.json").write_text(
        json.dumps(rejects, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"mode: {report['mode']}")
    print(f"flips (HIGH): {len(flips)}  rejects (MEDIUM): {len(rejects)}")
    print(f"flip by axis: {report['flip_by_axis']}")
    print(f"backup: {backup_dir}")
    print("representative BEFORE -> AFTER:")
    for f in flips[:8]:
        print(f"  [{f['ingredient'][:32]}] {f['axis']}: {f['old_direction']}->{f['new_direction']}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Apply HIGH_CONFIDENCE claim direction flips")
    p.add_argument("--apply", action="store_true", help="Apply (default dry-run)")
    p.add_argument("--out", default="/var/www/aidermy/calibration")
    return run(apply=p.parse_args().apply, out_dir=p.parse_args().out)


if __name__ == "__main__":
    raise SystemExit(main())
