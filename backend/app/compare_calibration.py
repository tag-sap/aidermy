# compare_calibration.py
# BEFORE (v1.0.0) vs AFTER (v1.1.0) сравнение на одном calibration dataset.

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _stats(scores: List[float]) -> Dict[str, Any]:
    s = sorted(scores)
    n = len(s)
    if n == 0:
        return {"count": 0}
    return {
        "count": n,
        "mean": round(sum(s) / n, 2),
        "median": s[n // 2],
        "p25": s[int(n * 0.25)],
        "p75": s[int(n * 0.75)],
        "min": s[0],
        "max": s[-1],
    }


def _hist(scores: List[float]) -> List[Dict[str, Any]]:
    if not scores:
        return []
    bins = [0] * 10
    for s in scores:
        i = min(9, int(s / 10))
        bins[i] += 1
    return [{"range": f"{i*10}-{i*10+9}", "count": c} for i, c in enumerate(bins)]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--before", default="calibration/dataset_before_v1.0.0.json")
    p.add_argument("--after", default="calibration/dataset.json")
    p.add_argument("--out", default="calibration")
    args = p.parse_args()

    with open(args.before, encoding="utf-8") as f:
        before = json.load(f)
    with open(args.after, encoding="utf-8") as f:
        after = json.load(f)

    before_map = {r["analysis_id"]: r for r in before}
    after_map = {r["analysis_id"]: r for r in after}

    common = [k for k in before_map if k in after_map]
    b_scores = [before_map[k]["scoring"]["final_score"] for k in common]
    a_scores = [after_map[k]["scoring"]["final_score"] for k in common]

    by_skin = defaultdict(lambda: {"before": [], "after": []})
    by_id = defaultdict(lambda: {"before": [], "after": []})
    for k in common:
        skin = after_map[k]["profile"]["skin_type"]
        pid = after_map[k]["profile"]["id"]
        by_skin[skin]["before"].append(before_map[k]["scoring"]["final_score"])
        by_skin[skin]["after"].append(after_map[k]["scoring"]["final_score"])
        by_id[pid]["before"].append(before_map[k]["scoring"]["final_score"])
        by_id[pid]["after"].append(after_map[k]["scoring"]["final_score"])

    # most changed products
    deltas = []
    for k in common:
        b = before_map[k]["scoring"]["final_score"]
        a = after_map[k]["scoring"]["final_score"]
        if a != b:
            deltas.append((abs(a - b), a - b, after_map[k]["product"]["name"],
                           after_map[k]["profile"]["label"], b, a))
    deltas.sort(key=lambda x: -x[0])

    report = {
        "matched_records": len(common),
        "overall": {"before": _stats(b_scores), "after": _stats(a_scores)},
        "histogram": {"before": _hist(b_scores), "after": _hist(a_scores)},
        "by_skin_type": {
            k: {"before": _stats(v["before"]), "after": _stats(v["after"])}
            for k, v in sorted(by_skin.items())
        },
        "by_profile_id": {
            k: {"before": _stats(v["before"]), "after": _stats(v["after"])}
            for k, v in sorted(by_id.items())
        },
        "most_changed_products": [
            {"delta": d[1], "before": d[4], "after": d[5],
             "product": d[2][:50], "profile": d[3]}
            for d in deltas[:20]
        ],
    }

    out = Path(args.out)
    (out / "comparison_before_after.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"matched records: {len(common)}")
    print(f"overall: before mean/median {report['overall']['before']['mean']}/{report['overall']['before']['median']} "
          f"-> after {report['overall']['after']['mean']}/{report['overall']['after']['median']}")
    print("by skin type (mean before -> after):")
    for k, v in report["by_skin_type"].items():
        print(f"  {k}: {v['before']['mean']} -> {v['after']['mean']}")
    print("by profile id (mean before -> after):")
    for k, v in report["by_profile_id"].items():
        print(f"  {k}: {v['before']['mean']} -> {v['after']['mean']}")
    print(f"wrote: {out / 'comparison_before_after.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
