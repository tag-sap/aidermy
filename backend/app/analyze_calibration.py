# analyze_calibration.py
# Анализатор calibration dataset → компактная аналитическая выжимка (не весь dataset).
#
# Считает распределения, оси, профили, влиятельные ингредиенты/взаимодействия,
# sensitivity, аномалии и системные проблемы. Пишет:
#   calibration/analysis_report.json
#   calibration/analysis_report.md

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .scoring_config import AXES, SCORING_CONFIG_VERSION

# Группы ингредиентов для системных проверок.
_UV_FILTERS = {
    "octocrylene", "avobenzone", "oxybenzone", "homosalate", "octinoxate",
    "octisalate", "ensulizole", "ecamsule", "padimate o", "amiloxate",
    "titanium dioxide", "zinc oxide", "tinosorb", "benzophenone",
    "ethylhexyl salicylate", "diethylamino hydroxybenzoyl",
    "methylene bis-benzotriazolyl", "bis-ethylhexyloxyphenol",
    "ethylhexyl triazone", "phenylbenzimidazole", "disodium phenyl dibenzimidazole",
}
_HUMECTANTS = {
    "hyaluronic acid", "sodium hyaluronate", "glycerin", "glycerine",
    "butylene glycol", "propanediol", "panthenol", "betaine", "trehalose",
    "sodium pca", "urea", "polyglutamic acid", "beta-glucan",
}


def _q(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Базовые квантили/статистика по числовому списку final_score."""
    scores = sorted(r["scoring"]["final_score"] for r in records)
    n = len(scores)
    if n == 0:
        return {"count": 0}
    return {
        "count": n,
        "mean": round(sum(scores) / n, 2),
        "median": scores[n // 2],
        "p10": scores[int(n * 0.10)],
        "p25": scores[int(n * 0.25)],
        "p75": scores[int(n * 0.75)],
        "p90": scores[int(n * 0.90)],
        "min": scores[0],
        "max": scores[-1],
    }


def _hist(scores: List[float], bins: int = 10) -> List[Dict[str, Any]]:
    if not scores:
        return []
    lo, hi = 0, 100
    w = (hi - lo) / bins
    counts = [0] * bins
    for s in scores:
        i = min(bins - 1, int(s / w))
        counts[i] += 1
    return [
        {"range": f"{int(lo + i * w)}-{int(lo + (i + 1) * w)}", "count": c}
        for i, c in enumerate(counts)
    ]


def _axis_nonzero(records: List[Dict[str, Any]], axis: str) -> int:
    return sum(1 for r in records if abs(r["scoring"]["parameter_scores"].get(axis, 0.0)) > 1e-9)


def _analyze_axes(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(records)
    out: Dict[str, Any] = {}
    for axis in AXES:
        nz = _axis_nonzero(records, axis)
        vals = [r["scoring"]["parameter_scores"].get(axis, 0.0) for r in records]
        mean = sum(vals) / n if n else 0.0
        mean_contrib = sum(
            max(0.0, min(r["scoring"]["parameter_scores"].get(axis, 0.0), 1.0))
            * r["scoring"]["weights"].get(axis, 0.0)
            for r in records
        ) / n if n else 0.0
        out[axis] = {
            "nonzero_fraction": round(nz / n, 4) if n else 0.0,
            "nonzero_count": nz,
            "mean_value": round(mean, 4),
            "mean_contribution_to_weighted_total": round(mean_contrib, 4),
        }
    return out


def _analyze_profiles(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_skin: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_id: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_skin[r["profile"]["skin_type"]].append(r)
        by_id[r["profile"]["id"]].append(r)
    return {
        "by_skin_type": {k: _q(v) for k, v in sorted(by_skin.items())},
        "by_profile_id": {k: _q(v) for k, v in sorted(by_id.items())},
    }


def _analyze_ingredients(records: List[Dict[str, Any]], top_n: int = 25) -> Dict[str, Any]:
    freq: Counter = Counter()
    total: Counter = Counter()
    pos: Counter = Counter()
    neg: Counter = Counter()
    for r in records:
        for c in r["scoring"]["ingredient_contributions"]:
            name = c["ingredient_name"]
            freq[name] += 1
            tc = c["total_contribution"]
            total[name] += abs(tc)
            (pos if tc > 0 else neg)[name] += tc

    def top(counter: Counter, key_desc: str):
        return [
            {"ingredient": k, key_desc: round(v, 4)}
            for k, v in counter.most_common(top_n)
        ]

    return {
        "top_by_frequency": top(freq, "frequency"),
        "top_by_abs_contribution": top(total, "abs_contribution"),
        "top_positive": top(pos, "positive_contribution"),
        "top_negative": top(neg, "negative_contribution"),
    }


def _q_from_scores(scores: List[float]) -> Dict[str, Any]:
    s = sorted(scores)
    n = len(s)
    if n == 0:
        return {"count": 0}
    return {
        "count": n,
        "mean": round(sum(s) / n, 2),
        "median": s[n // 2],
        "min": s[0],
        "max": s[-1],
    }


def _analyze_unknown(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(records)
    unk_fracs = []
    products_mostly_unknown = 0
    score_by_unknown: Dict[str, List[float]] = defaultdict(list)
    for r in records:
        ing = r["product"]["ingredients"]
        unknown = r["scoring"]["unknown_ingredients"]
        frac = (len(unknown) / len(ing)) if ing else 0.0
        unk_fracs.append(frac)
        if frac > 0.5:
            products_mostly_unknown += 1
        bucket = "0" if frac == 0 else ("0-25%" if frac <= 0.25 else ("25-50%" if frac <= 0.5 else ">50%"))
        score_by_unknown[bucket].append(r["scoring"]["final_score"])

    return {
        "mean_unknown_fraction": round(sum(unk_fracs) / n, 4) if n else 0.0,
        "records_with_mostly_unknown": products_mostly_unknown,
        "records_with_mostly_unknown_fraction": round(products_mostly_unknown / n, 4) if n else 0.0,
        "score_by_unknown_bucket": {k: _q_from_scores(v) for k, v in sorted(score_by_unknown.items())},
    }


def _analyze_dominance(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Случаи, где один фактор непропорционально доминирует."""
    dominated = 0
    examples = []
    for r in records:
        contribs = r["scoring"]["ingredient_contributions"]
        if len(contribs) < 3:
            continue
        total_abs = sum(abs(c["total_contribution"]) for c in contribs)
        if total_abs <= 0:
            continue
        top = max(contribs, key=lambda c: abs(c["total_contribution"]))
        share = abs(top["total_contribution"]) / total_abs
        if share > 0.6:
            dominated += 1
            if len(examples) < 8:
                examples.append({
                    "product": r["product"]["name"],
                    "profile": r["profile"]["label"],
                    "dominant_ingredient": top["ingredient_name"],
                    "share": round(share, 3),
                    "total_contribution": round(top["total_contribution"], 4),
                })
    return {"dominated_count": dominated, "examples": examples}


def _analyze_systemic(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    axes = _analyze_axes(records)

    oily = [
        r for r in records
        if "жирн" in (r["profile"]["skin_type"] or "").lower()
        or "акне" in " ".join(r["profile"]["concerns"] or []).lower()
    ]
    oily_sebum_zero = sum(
        1 for r in oily if abs(r["scoring"]["parameter_scores"].get("sebum", 0.0)) <= 1e-9
    )
    oily_mean = round(sum(r["scoring"]["final_score"] for r in oily) / len(oily), 2) if oily else None

    uv_n = 0
    uv_contrib = 0.0
    ha_n = 0
    ha_contrib = 0.0
    for r in records:
        for c in r["scoring"]["ingredient_contributions"]:
            key = re.sub(r"[^a-z0-9 ]", " ", c["ingredient_name"].lower())
            key = re.sub(r"\s+", " ", key).strip()
            if any(u in key for u in _UV_FILTERS):
                uv_n += 1
                uv_contrib += abs(c["total_contribution"])
            if any(h in key for h in _HUMECTANTS):
                ha_n += 1
                ha_contrib += abs(c["total_contribution"])

    return {
        "oily_acne": {
            "count": len(oily),
            "sebum_zero_count": oily_sebum_zero,
            "sebum_zero_fraction": round(oily_sebum_zero / len(oily), 4) if oily else None,
            "mean_score": oily_mean,
        },
        "sensitization": axes.get("sensitization"),
        "sebum": axes.get("sebum"),
        "uv_filters": {"occurrences": uv_n, "abs_contribution": round(uv_contrib, 3)},
        "humectants": {"occurrences": ha_n, "abs_contribution": round(ha_contrib, 3)},
    }


def _anomalies(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    scores = sorted(records, key=lambda r: r["scoring"]["final_score"])
    top = scores[-5:] if scores else []
    bottom = scores[:5] if scores else []
    return {
        "highest": [
            {"product": r["product"]["name"], "profile": r["profile"]["label"],
             "score": r["scoring"]["final_score"]} for r in reversed(top)
        ],
        "lowest": [
            {"product": r["product"]["name"], "profile": r["profile"]["label"],
             "score": r["scoring"]["final_score"]} for r in bottom
        ],
    }


def build_report(records: List[Dict[str, Any]], dataset_path: str) -> Dict[str, Any]:
    n = len(records)
    products = len({r["analysis_id"].split(":")[0] for r in records})
    profiles = len({r["profile"]["id"] for r in records})
    interactions_n = sum(len(r["scoring"]["interaction_contributions"]) for r in records)

    return {
        "meta": {
            "dataset": dataset_path,
            "records": n,
            "products": products,
            "profiles": profiles,
            "scoring_config_version": SCORING_CONFIG_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "score_distribution": {
            "summary": _q(records),
            "histogram_10bins": _hist([r["scoring"]["final_score"] for r in records]),
        },
        "confidence": {
            "mean": round(sum(r["scoring"]["confidence"] for r in records) / n, 4) if n else 0.0,
        },
        "unknown_ingredients": _analyze_unknown(records),
        "profiles": _analyze_profiles(records),
        "axes": _analyze_axes(records),
        "ingredients": _analyze_ingredients(records),
        "interactions": {"total_contribution_count": interactions_n},
        "dominance": _analyze_dominance(records),
        "systemic": _analyze_systemic(records),
        "anomalies": _anomalies(records),
    }


def _md_report(report: Dict[str, Any]) -> str:
    m = report["meta"]
    L: List[str] = []
    L.append("# Calibration Analysis Report\n")
    L.append(f"- dataset: `{m['dataset']}`")
    L.append(f"- records: {m['records']} | products: {m['products']} | profiles: {m['profiles']}")
    L.append(f"- scoring_config_version: {m['scoring_config_version']}")
    L.append(f"- generated_at: {m['generated_at']}\n")

    s = report["score_distribution"]["summary"]
    L.append("## Score distribution\n")
    L.append(f"mean={s.get('mean')} median={s.get('median')} "
             f"p10={s.get('p10')} p25={s.get('p25')} p75={s.get('p75')} p90={s.get('p90')} "
             f"min={s.get('min')} max={s.get('max')}\n")
    L.append("| range | count |\n|---|---|")
    for h in report["score_distribution"]["histogram_10bins"]:
        L.append(f"| {h['range']} | {h['count']} |")
    L.append("")

    L.append("## Confidence\n")
    L.append(f"mean confidence = {report['confidence']['mean']}\n")

    L.append("## Unknown ingredients\n")
    u = report["unknown_ingredients"]
    L.append(f"- mean unknown fraction: {u['mean_unknown_fraction']}")
    L.append(f"- records with >50% unknown: {u['records_with_mostly_unknown']} "
             f"({u['records_with_mostly_unknown_fraction']})\n")
    L.append("| unknown bucket | mean score | median |")
    L.append("|---|---|---|")
    for k, v in u["score_by_unknown_bucket"].items():
        if v.get("count"):
            L.append(f"| {k} | {v.get('mean')} | {v.get('median')} |")
    L.append("")

    L.append("## Profiles\n")
    L.append("### by skin type\n")
    L.append("| skin_type | count | mean | median |\n|---|---|---|---|")
    for k, v in report["profiles"]["by_skin_type"].items():
        if v.get("count"):
            L.append(f"| {k} | {v['count']} | {v['mean']} | {v['median']} |")
    L.append("\n### by profile id\n")
    L.append("| profile | count | mean | median |\n|---|---|---|---|")
    for k, v in report["profiles"]["by_profile_id"].items():
        if v.get("count"):
            L.append(f"| {k} | {v['count']} | {v['mean']} | {v['median']} |")
    L.append("")

    L.append("## Axes\n")
    L.append("| axis | nonzero_fraction | mean_value | mean_contrib |\n|---|---|---|---|")
    for axis, v in report["axes"].items():
        L.append(f"| {axis} | {v['nonzero_fraction']} | {v['mean_value']} | {v['mean_contribution_to_weighted_total']} |")
    L.append("")

    L.append("## Top ingredients (abs contribution)\n")
    for it in report["ingredients"]["top_by_abs_contribution"][:15]:
        L.append(f"- {it['ingredient']}: {it['abs_contribution']}")
    L.append("\n### top negative\n")
    for it in report["ingredients"]["top_negative"][:10]:
        L.append(f"- {it['ingredient']}: {it['negative_contribution']}")
    L.append("")

    L.append("## Systemic\n")
    sy = report["systemic"]
    L.append(f"- oily/acne: count={sy['oily_acne']['count']} sebum_zero={sy['oily_acne']['sebum_zero_count']} "
             f"({sy['oily_acne']['sebum_zero_fraction']}) mean_score={sy['oily_acne']['mean_score']}")
    L.append(f"- sensitization nonzero_fraction: {sy['sensitization']['nonzero_fraction']}")
    L.append(f"- sebum nonzero_fraction: {sy['sebum']['nonzero_fraction']}")
    L.append(f"- UV filters: occurrences={sy['uv_filters']['occurrences']} abs_contrib={sy['uv_filters']['abs_contribution']}")
    L.append(f"- humectants: occurrences={sy['humectants']['occurrences']} abs_contrib={sy['humectants']['abs_contribution']}")
    L.append("")

    L.append("## Dominance (single factor >60% of product contribution)\n")
    L.append(f"dominated records: {report['dominance']['dominated_count']}")
    for e in report["dominance"]["examples"]:
        L.append(f"- {e['product'][:40]} ({e['profile']}): {e['dominant_ingredient']} share={e['share']}")
    L.append("")

    L.append("## Anomalies\n")
    L.append("### highest scores")
    for e in report["anomalies"]["highest"]:
        L.append(f"- {e['score']} — {e['product'][:40]} ({e['profile']})")
    L.append("### lowest scores")
    for e in report["anomalies"]["lowest"]:
        L.append(f"- {e['score']} — {e['product'][:40]} ({e['profile']})")

    return "\n".join(L)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze calibration dataset")
    parser.add_argument("--dataset", default="calibration/dataset.json")
    parser.add_argument("--out", default="calibration")
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        records = json.load(f)

    report = build_report(records, args.dataset)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / "analysis_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "analysis_report.md").write_text(_md_report(report), encoding="utf-8")

    print(f"records: {report['meta']['records']}")
    print(f"score mean/median: {report['score_distribution']['summary'].get('mean')} / "
          f"{report['score_distribution']['summary'].get('median')}")
    print(f"axes nonzero: " + ", ".join(
        f"{a}={v['nonzero_fraction']}" for a, v in report["axes"].items()
    ))
    print(f"wrote: {out / 'analysis_report.json'}")
    print(f"wrote: {out / 'analysis_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



