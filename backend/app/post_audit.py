# post_audit.py
# Post-calibration audit: почему реальные продукты получают подозрительно низкие/высокие оценки.
# Читает calibration dataset (v1.1.0) и выдаёт компактный отчёт по продуктам и профилям.

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List

from .scoring_config import AXES, SCORING_CONFIG_VERSION


def _by_product(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    d: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        d[r["product"]["id"]].append(r)
    return d


def _prod_summary(pid: Any, recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    scores = [r["scoring"]["final_score"] for r in recs]
    unk_fracs = [
        len(r["scoring"]["unknown_ingredients"]) / len(r["product"]["ingredients"])
        if r["product"]["ingredients"] else 0.0
        for r in recs
    ]
    return {
        "id": pid,
        "name": (recs[0]["product"]["name"] or "").replace("\n", " ")[:60],
        "category": recs[0]["product"].get("category"),
        "n_profiles": len(recs),
        "score_min": min(scores),
        "score_max": max(scores),
        "score_mean": round(mean(scores), 2),
        "score_std": round(pstdev(scores), 2) if len(scores) > 1 else 0.0,
        "mean_unknown_fraction": round(mean(unk_fracs), 3),
        "per_profile": {r["profile"]["id"]: r["scoring"]["final_score"] for r in recs},
    }


def _axis_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for axis in AXES:
        vals = [r["scoring"]["parameter_scores"].get(axis, 0.0) for r in records]
        nz = sum(1 for v in vals if abs(v) > 1e-9)
        out[axis] = {
            "nonzero_fraction": round(nz / len(records), 4) if records else 0.0,
            "mean_value": round(mean(vals), 4) if vals else 0.0,
            "mean_weight": round(mean(r["scoring"]["weights"].get(axis, 0.0) for r in records), 4) if records else 0.0,
        }
    return out


def _dominance(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for r in records:
        pid = r["product"]["id"]
        if pid in seen:
            continue
        contribs = r["scoring"]["ingredient_contributions"]
        if len(contribs) < 3:
            continue
        total_abs = sum(abs(c["total_contribution"]) for c in contribs)
        if total_abs <= 0:
            continue
        top = max(contribs, key=lambda c: abs(c["total_contribution"]))
        share = abs(top["total_contribution"]) / total_abs
        if share > 0.6:
            seen.add(pid)
            out.append({
                "id": pid,
                "name": (r["product"]["name"] or "").replace("\n", " ")[:50],
                "dominant_ingredient": top["ingredient_name"],
                "share": round(share, 3),
                "total": round(top["total_contribution"], 3),
            })
    return out


def build_report(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    byp = _by_product(records)
    summaries = [_prod_summary(pid, recs) for pid, recs in byp.items()]

    low_020 = [s for s in summaries if s["score_max"] <= 20]
    low_2040 = [s for s in summaries if 20 < s["score_min"] <= 40 and s["score_max"] < 45]
    high_80100 = [s for s in summaries if s["score_min"] >= 80]

    high_var = sorted(summaries, key=lambda s: -s["score_std"])[:20]
    low_var = sorted(summaries, key=lambda s: s["score_std"])[:20]
    high_unknown = sorted(summaries, key=lambda s: -s["mean_unknown_fraction"])[:20]

    neg_irrit_by_prod = {}
    for r in records:
        if r["scoring"]["parameter_scores"].get("irritation", 0.0) < -0.3:
            neg_irrit_by_prod.setdefault(r["product"]["id"], r)
    neg_irrit_list = [
        {"id": r["product"]["id"], "name": r["product"]["name"].replace("\n", " ")[:50],
         "irritation": round(r["scoring"]["parameter_scores"]["irritation"], 3),
         "score": r["scoring"]["final_score"], "profile": r["profile"]["id"]}
        for r in list(neg_irrit_by_prod.values())[:15]
    ]

    profile_breakdown: Dict[str, Any] = defaultdict(lambda: {"scores": []})
    for r in records:
        profile_breakdown[r["profile"]["id"]]["scores"].append(r["scoring"]["final_score"])
    profile_stats = {
        pid: {
            "count": len(v["scores"]),
            "mean": round(mean(v["scores"]), 2),
            "min": min(v["scores"]),
            "max": max(v["scores"]),
            "std": round(pstdev(v["scores"]), 2) if len(v["scores"]) > 1 else 0.0,
        }
        for pid, v in sorted(profile_breakdown.items())
    }

    return {
        "meta": {
            "records": len(records),
            "products": len(byp),
            "scoring_config_version": SCORING_CONFIG_VERSION,
        },
        "axes": _axis_summary(records),
        "products_score_0_20": low_020[:25],
        "products_score_20_40": low_2040[:25],
        "products_score_80_100": high_80100[:25],
        "products_high_profile_variance": high_var,
        "products_near_constant_score": low_var,
        "products_high_unknown": high_unknown,
        "products_dominance": _dominance(records)[:25],
        "products_negative_irritation": neg_irrit_list,
        "profiles": profile_stats,
    }


def _md(report: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("# Post-Calibration Audit\n")
    L.append(f"- records: {report['meta']['records']} | products: {report['meta']['products']} | config: {report['meta']['scoring_config_version']}\n")

    L.append("## Axes\n| axis | nonzero_fraction | mean_value | mean_weight |\n|---|---|---|---|")
    for a, v in report["axes"].items():
        L.append(f"| {a} | {v['nonzero_fraction']} | {v['mean_value']} | {v['mean_weight']} |")
    L.append("")

    L.append("## Profiles\n| profile | count | mean | min | max | std |\n|---|---|---|---|---|---|")
    for p, v in report["profiles"].items():
        L.append(f"| {p} | {v['count']} | {v['mean']} | {v['min']} | {v['max']} | {v['std']} |")
    L.append("")

    def _tbl(title, items):
        L.append(f"## {title}\n")
        L.append("| name | min | max | mean | std | unk_frac |\n|---|---|---|---|---|---|")
        for s in items:
            L.append(f"| {s['name'][:45]} | {s['score_min']} | {s['score_max']} | {s['score_mean']} | {s['score_std']} | {s['mean_unknown_fraction']} |")
        L.append("")

    _tbl("Score 0-20", report["products_score_0_20"])
    _tbl("Score 20-40", report["products_score_20_40"])
    _tbl("Score 80-100", report["products_score_80_100"])

    L.append("## High profile variance\n| name | std | min | max |\n|---|---|---|---|")
    for s in report["products_high_profile_variance"]:
        L.append(f"| {s['name'][:45]} | {s['score_std']} | {s['score_min']} | {s['score_max']} |")
    L.append("")

    L.append("## Near-constant score\n| name | std | score |\n|---|---|---|")
    for s in report["products_near_constant_score"]:
        L.append(f"| {s['name'][:45]} | {s['score_std']} | {s['score_mean']} |")
    L.append("")

    L.append("## High unknown fraction\n| name | unk_frac | mean score |\n|---|---|---|")
    for s in report["products_high_unknown"]:
        L.append(f"| {s['name'][:45]} | {s['mean_unknown_fraction']} | {s['score_mean']} |")
    L.append("")

    L.append("## Dominance (single ingredient >60%)\n| name | ingredient | share | total |\n|---|---|---|---|")
    for s in report["products_dominance"]:
        L.append(f"| {s['name'][:40]} | {s['dominant_ingredient'][:30]} | {s['share']} | {s['total']} |")
    L.append("")

    L.append("## Negative irritation impact\n| name | irritation | score | profile |\n|---|---|---|---|")
    for s in report["products_negative_irritation"]:
        L.append(f"| {s['name'][:40]} | {s['irritation']} | {s['score']} | {s['profile']} |")

    return "\n".join(L)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="calibration/dataset.json")
    p.add_argument("--out", default="calibration")
    args = p.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        records = json.load(f)
    report = build_report(records)
    out = Path(args.out)
    (out / "post_audit_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "post_audit_report.md").write_text(_md(report), encoding="utf-8")
    print(f"wrote: {out / 'post_audit_report.json'}")
    print(f"wrote: {out / 'post_audit_report.md'}")
    print("axes nonzero: " + ", ".join(f"{a}={v['nonzero_fraction']}" for a, v in report["axes"].items()))
    print("profiles mean: " + ", ".join(f"{p}={v['mean']}" for p, v in report["profiles"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
