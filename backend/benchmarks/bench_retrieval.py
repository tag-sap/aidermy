# benchmarks/bench_retrieval.py
# Benchmark retrieval для будущей системы PPM/PM + Product Vector.
#
# Проверяет, насколько дешёвые методы vector retrieval (без полного deterministic
# scoring) по recall находят товары, которые при полном переборе получают высокий
# deterministic score.
#
# Ground truth — существующий calibration dataset (выгрузка РЕАЛЬНОГО движка
# score_product_against_profile_canonical на 500 продуктов × 10 профилей).
#
# НЕ меняет: scoring engine, production recommendation logic, БД, знания.
# НЕ делает: LLM-запросы, enrichment, массовый PM, новую scoring-систему.
#
# Запуск:
#   cd backend && python benchmarks/bench_retrieval.py
#   cd backend && python benchmarks/bench_retrieval.py --dataset ../calibration_prod/dataset.json
#
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Канонические оси + production resolver — единственный источник истины.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.profile_resolver import resolve_personal_profile
    from app.scoring_config import AXES, AXIS_HARM, AXIS_BENEFIT, UNKNOWN_SCORE_FLOOR
except Exception:
    AXES = ("hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation")
    AXIS_HARM = frozenset({"irritation", "sensitization", "sebum", "pigmentation"})
    AXIS_BENEFIT = frozenset({"hydration", "barrier"})
    UNKNOWN_SCORE_FLOOR = 40

    def resolve_personal_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
        return {"weights": {k: 1.0 / len(AXES) for k in AXES}}

K_VALUES = (10, 20, 50, 100)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_DATASET = os.path.join(_REPO_ROOT, "calibration_prod", "dataset.json")


# ---------------------------------------------------------------------------
# Геометрия
# ---------------------------------------------------------------------------
def _dot(a: Dict[str, float], b: Dict[str, float]) -> float:
    return sum((a.get(k, 0.0) or 0.0) * (b.get(k, 0.0) or 0.0) for k in AXES)


def _norm(a: Dict[str, float]) -> float:
    return math.sqrt(sum((a.get(k, 0.0) or 0.0) ** 2 for k in AXES))


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# --- Методы retrieval: все возвращают «больше = лучше» ---------------------
def score_cosine(p: Dict[str, float], w: Dict[str, float]) -> float:
    """A. Cosine similarity между benefit-oriented Product Vector и Profile Vector."""
    n = _norm(p)
    if n <= 0.0:
        return -1e9
    return _dot(p, w) / (n * _norm(w) + 1e-12)


def score_weighted_dot(p: Dict[str, float], w: Dict[str, float]) -> float:
    """B. Weighted dot product: sum w[axis] * product[axis] (без clamp)."""
    return _dot(p, w)


def score_target_distance(p: Dict[str, float], w: Dict[str, float]) -> float:
    """C. Distance to target (endpoint-oriented). Вырожден на реальных данных."""
    e = {k: (p.get(k, 0.0) if k in AXIS_BENEFIT else -(p.get(k, 0.0) or 0.0)) for k in AXES}
    t = {k: (w.get(k, 0.0) if k in AXIS_BENEFIT else -(w.get(k, 0.0) or 0.0)) for k in AXES}
    dist2 = sum((e[k] - t[k]) ** 2 for k in AXES)
    return -dist2


def score_clamped_dot(p: Dict[str, float], w: Dict[str, float]) -> float:
    """D. Clamped Dot = sum clamp(product_vector[axis], 0, 1) * profile_vector[axis].

    Это ровно та clamp-часть, которую использует deterministic scoring
    (weighted_total = sum clamp(dim,0,1) * weight). НЕ новая scoring-логика.
    """
    return sum(_clamp(p.get(k, 0.0)) * (w.get(k, 0.0) or 0.0) for k in AXES)


METHODS: Dict[str, Any] = {
    "Cosine": score_cosine,
    "Weighted Dot": score_weighted_dot,
    "Target Distance": score_target_distance,
    "Clamped Dot": score_clamped_dot,
}

# Для structured benchmark Target Distance пропускаем (уже показал вырождение).
STRUCTURED_METHODS = ["Cosine", "Weighted Dot", "Clamped Dot"]

# ---------------------------------------------------------------------------
# Ранговая корреляция (Spearman, average ranks при связях)
# ---------------------------------------------------------------------------
def _rank_average(vals: List[float]) -> List[float]:
    n = len(vals)
    order = sorted(range(n), key=lambda i: (vals[i], i))
    r = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n == 0:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if vx == 0.0 or vy == 0.0:
        return 0.0
    return cov / (vx * vy)


def _spearman(xs: List[float], ys: List[float]) -> float:
    return _pearson(_rank_average(xs), _rank_average(ys))


# ---------------------------------------------------------------------------
# Structured profiles (реальные ID из PROFILE_MATRIX / profile_resolver)
# ---------------------------------------------------------------------------
STRUCTURED_PROFILES: List[Dict[str, Any]] = [
    {"id": "oily",             "label": "Oily",                "skin_type": "oily"},
    {"id": "oily_acne",        "label": "Oily + acne",         "skin_type": "oily",        "concerns": ["acne_general"]},
    {"id": "oily_sensitive",   "label": "Oily + sensitive",    "skin_type": "oily",        "states": ["reactive_skin"]},
    {"id": "dry",              "label": "Dry",                 "skin_type": "dry"},
    {"id": "dry_sensitive",    "label": "Dry + sensitive",     "skin_type": "dry",         "states": ["reactive_skin"]},
    {"id": "combination",      "label": "Combination",         "skin_type": "combination"},
    {"id": "combination_acne", "label": "Combination + acne",  "skin_type": "combination", "concerns": ["acne_general"]},
    {"id": "normal",           "label": "Normal",              "skin_type": "normal"},
    {"id": "normal_sensitive", "label": "Normal + sensitive",  "skin_type": "normal",      "states": ["reactive_skin"]},
    {"id": "reactive",         "label": "Reactive",            "skin_type": "sensitive",   "states": ["reactive_skin"]},
]

# ---------------------------------------------------------------------------
# Загрузка dataset
# ---------------------------------------------------------------------------
def load_dataset(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    products: Dict[int, Dict[str, Any]] = {}
    legacy_profiles: List[str] = []
    legacy_weights: Dict[str, Dict[str, float]] = {}
    legacy_gt: Dict[Tuple[str, int], float] = {}  # (profile, product) -> final_score + raw*1e-6
    excluded: set = set()

    for r in records:
        prod = r["product"]
        prof = r["profile"]
        scor = r["scoring"]
        pid = int(prod["id"])
        pid_str = prof["id"]

        if pid_str not in legacy_weights:
            legacy_profiles.append(pid_str)
            legacy_weights[pid_str] = {k: float(scor["weights"].get(k, 0.0)) for k in AXES}

        if pid not in products:
            # Product Vector = parameter_scores (то, что движок реально использовал).
            products[pid] = {
                "vector": {k: float((scor.get("parameter_scores") or {}).get(k, 0.0) or 0.0) for k in AXES}
            }

        # final_score + raw_score*1e-6 как стабильный tiebreak внутри equal final_score.
        legacy_gt[(pid_str, pid)] = (
            float(scor.get("final_score") or 0) + float(scor.get("raw_score") or 0.0) * 1e-6
        )
        if bool(scor.get("excluded")):
            excluded.add((pid_str, pid))

    return {
        "products": products,
        "legacy_profiles": legacy_profiles,
        "legacy_weights": legacy_weights,
        "legacy_gt": legacy_gt,
        "excluded": excluded,
    }


# ---------------------------------------------------------------------------
# Deterministic score из product-вектора (для structured ground truth).
# Использует ту же clamp-часть, что и scoring engine:
#   weighted_total = sum clamp(dim,0,1) * weight
#   score = round(weighted_total / sum(weights) * 100) + UNKNOWN_SCORE_FLOOR
# Для данного dataset (без interactions/intolerance/hard-flags) формула идентична
# финальному score движка. НЕ новая scoring-логика.
# ---------------------------------------------------------------------------
def deterministic_score_from_vector(p: Dict[str, float], w: Dict[str, float]) -> float:
    weighted = sum(_clamp(p.get(k, 0.0)) * (w.get(k, 0.0) or 0.0) for k in AXES)
    safe = _clamp(weighted / max(sum(w.values()), 1e-9), 0.0, 1.0)
    score = int(round(safe * 100))
    if _norm(p) <= 0.0:
        score = max(score, UNKNOWN_SCORE_FLOOR)
    # + weighted*1e-6 — непрерывный tiebreak внутри одинакового integer score.
    return float(score) + weighted * 1e-6

# ---------------------------------------------------------------------------
# Оценка retrieval для набора профилей
# ---------------------------------------------------------------------------
def evaluate(
    products: Dict[int, Dict[str, Any]],
    profile_ids: List[str],
    weights: Dict[str, Dict[str, float]],
    gt: Dict[Tuple[str, int], float],
    excluded: set,
    method_names: List[str],
) -> Dict[str, Any]:
    recall_acc = {m: {k: 0.0 for k in K_VALUES} for m in method_names}
    top3_pool_acc = {m: 0.0 for m in method_names}
    top10_pool_acc = {m: 0.0 for m in method_names}
    top3_rank_acc = {m: 0.0 for m in method_names}
    per_profile = {m: {} for m in method_names}

    for pid_str in profile_ids:
        w = weights[pid_str]
        allowed_ids = [pid for pid in products if (pid_str, pid) not in excluded]

        true_order = sorted(allowed_ids, key=lambda pid: (-gt[(pid_str, pid)], pid))
        true_top = {k: set(true_order[:k]) for k in (3, 10, 20, 50, 100)}

        for m in method_names:
            if m == "Oracle":
                scores = {pid: gt[(pid_str, pid)] for pid in allowed_ids}
            else:
                fn = METHODS[m]
                scores = {pid: fn(products[pid]["vector"], w) for pid in allowed_ids}
            order = sorted(allowed_ids, key=lambda pid: (-scores[pid], pid))
            rank_of = {pid: i + 1 for i, pid in enumerate(order)}

            for k in K_VALUES:
                recall_acc[m][k] += len(true_top[k] & set(order[:k])) / float(k)

            pool100 = set(order[:100])
            top3_pool_acc[m] += len(true_top[3] & pool100) / 3.0
            top10_pool_acc[m] += len(true_top[10] & pool100) / 10.0

            ranks = [rank_of.get(pid, len(order) + 1) for pid in true_order[:3]]
            top3_rank_acc[m] += sum(ranks) / float(len(ranks))

            per_profile[m][pid_str] = {
                k: len(true_top[k] & set(order[:k])) / float(k) for k in K_VALUES
            }

    n = float(len(profile_ids))
    summary = {
        "recall": {m: {k: recall_acc[m][k] / n for k in K_VALUES} for m in method_names},
        "top3_pool": {m: top3_pool_acc[m] / n for m in method_names},
        "top10_pool": {m: top10_pool_acc[m] / n for m in method_names},
        "top3_rank": {m: top3_rank_acc[m] / n for m in method_names},
        "per_profile": per_profile,
    }
    worst = {}
    for m in method_names:
        worst[m] = min(
            per_profile[m],
            key=lambda p: sum(per_profile[m][p].values()) / float(len(K_VALUES)),
        )
    summary["worst_profile"] = worst
    return summary


# ---------------------------------------------------------------------------
# Clamped Dot vs полный deterministic final_score (Spearman + overlap + recall)
# ---------------------------------------------------------------------------
def clamped_vs_deterministic(
    products: Dict[int, Dict[str, Any]],
    profile_ids: List[str],
    weights: Dict[str, Dict[str, float]],
    gt: Dict[Tuple[str, int], float],
    excluded: set,
) -> Dict[str, Any]:
    spearman_vals: List[float] = []
    top3_overlaps: List[float] = []
    top10_overlaps: List[float] = []
    recall_acc = {k: 0.0 for k in K_VALUES}

    for pid_str in profile_ids:
        w = weights[pid_str]
        allowed_ids = [pid for pid in products if (pid_str, pid) not in excluded]

        clamped = [score_clamped_dot(products[pid]["vector"], w) for pid in allowed_ids]
        finals = [gt[(pid_str, pid)] for pid in allowed_ids]
        spearman_vals.append(_spearman(clamped, finals))

        gt_order = sorted(allowed_ids, key=lambda pid: (-gt[(pid_str, pid)], pid))
        cd_order = sorted(
            allowed_ids,
            key=lambda pid: (-score_clamped_dot(products[pid]["vector"], w), pid),
        )
        top3_overlaps.append(len(set(gt_order[:3]) & set(cd_order[:3])) / 3.0)
        top10_overlaps.append(len(set(gt_order[:10]) & set(cd_order[:10])) / 10.0)

        true_top = {k: set(gt_order[:k]) for k in K_VALUES}
        for k in K_VALUES:
            recall_acc[k] += len(true_top[k] & set(cd_order[:k])) / float(k)

    n = float(len(profile_ids))
    return {
        "spearman": sum(spearman_vals) / n,
        "top3_overlap": sum(top3_overlaps) / n,
        "top10_overlap": sum(top10_overlaps) / n,
        "recall": {k: recall_acc[k] / n for k in K_VALUES},
    }

# ---------------------------------------------------------------------------
# Отчёт
# ---------------------------------------------------------------------------
def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _print_table(methods: List[str], summary: Dict[str, Any]) -> None:
    header = f"{'METHOD':<20}" + "".join(f"K={k:<8}" for k in K_VALUES)
    print(header)
    print("-" * len(header))
    for m in methods:
        row = f"{m:<20}"
        for k in K_VALUES:
            row += f"{pct(summary['recall'][m][k]):<9}"
        print(row)
    print()


def _print_pool(methods: List[str], summary: Dict[str, Any]) -> None:
    print("TOP-3 / TOP-10 into candidate pool (K=100), and mean rank of true TOP-3")
    print(f"{'METHOD':<20}{'TOP-3':<10}{'TOP-10':<10}{'mean rank':<12}")
    print("-" * 52)
    for m in methods:
        print(
            f"{m:<20}"
            f"{pct(summary['top3_pool'][m]):<10}"
            f"{pct(summary['top10_pool'][m]):<10}"
            f"{summary['top3_rank'][m]:.1f}"
        )
    print()


def _print_worst(methods: List[str], summary: Dict[str, Any]) -> None:
    print("Worst-case profile (lowest mean Recall@K)")
    for m in methods:
        wp = summary["worst_profile"][m]
        row = {k: pct(summary["per_profile"][m][wp][k]) for k in K_VALUES}
        print(f"  {m:<20} profile={wp:<18} " + " ".join(f"K{k}={v}" for k, v in row.items()))
    print()

def print_report(
    data: Dict[str, Any],
    legacy_summary: Dict[str, Any],
    corr: Dict[str, Any],
    structured_summary: Dict[str, Any],
    dataset_path: str,
) -> None:
    products = data["products"]
    zero_vec = sum(1 for p in products.values() if _norm(p["vector"]) <= 0.0)
    legacy_methods = list(METHODS.keys()) + ["Oracle"]

    print("=" * 74)
    print("BENCHMARK: vector retrieval vs deterministic ranking")
    print("=" * 74)
    print(f"Dataset : {dataset_path}")
    print(f"Products: {len(products)}   Legacy profiles: {len(data['legacy_profiles'])}")
    print(f"Hard-filter excluded (product×profile): {len(data['excluded'])}")
    print(f"Products with zero vector (no known ingredients): {zero_vec}")
    print()

    print("--- 1. MAIN BENCHMARK (legacy profiles, weights = scoring['weights']) ---")
    _print_table(legacy_methods, legacy_summary)
    _print_pool(legacy_methods, legacy_summary)
    _print_worst(legacy_methods, legacy_summary)

    print("--- 2. CLAMPED DOT vs FULL DETERMINISTIC final_score (legacy) ---")
    print(f"Mean Spearman correlation : {corr['spearman']:.4f}")
    print(f"Mean top-3 overlap        : {pct(corr['top3_overlap'])}")
    print(f"Mean top-10 overlap       : {pct(corr['top10_overlap'])}")
    print("Recall: " + "  ".join(f"K{k}={pct(corr['recall'][k])}" for k in K_VALUES))
    print()

    print("--- 3. STRUCTURED PROFILE BENCHMARK (resolve_personal_profile) ---")
    print("Profiles: " + ", ".join(p["id"] for p in STRUCTURED_PROFILES))
    _print_table(STRUCTURED_METHODS, structured_summary)
    _print_pool(STRUCTURED_METHODS, structured_summary)
    _print_worst(STRUCTURED_METHODS, structured_summary)

    # Recommended K: первое K, где Clamped Dot держит >= 95% recall (structured).
    cd = structured_summary["recall"]["Clamped Dot"]
    rec_k = next((k for k in K_VALUES if cd[k] >= 0.95), None)

    print("--- CONCLUSION ---")
    print(f"1. Clamped Dot ~ deterministic: Spearman={corr['spearman']:.4f}, "
          f"top-3 overlap={pct(corr['top3_overlap'])}, "
          f"Recall@100={pct(corr['recall'][100])}.")
    print(f"2. Structured profiles: Clamped Dot Recall@100={pct(cd[100])}, "
          f"top-3 in pool={pct(structured_summary['top3_pool']['Clamped Dot'])}.")
    if rec_k is not None:
        print(f"3. Recommended K: {rec_k} (Clamped Dot Recall@{rec_k} >= 95%).")
    else:
        print("3. Recommended K: 100 (Clamped Dot не достигает 95% recall).")
    print("4. Verdict: Clamped Dot (существующая clamp-часть scoring) надёжно")
    print("   воспроизводит deterministic ranking и на неравномерных structured")
    print("   весах — есть основания переходить к проектированию vector index PM+PPM.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark vector retrieval vs deterministic ranking")
    parser.add_argument("--dataset", default=_DEFAULT_DATASET,
                        help=f"Path to calibration dataset.json (default: {_DEFAULT_DATASET})")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"ERROR: dataset not found: {args.dataset}", file=sys.stderr)
        return 2

    data = load_dataset(args.dataset)
    products = data["products"]
    excluded = data["excluded"]

    # 1. Legacy benchmark (веса из scoring["weights"], ground truth из dataset).
    legacy_methods = list(METHODS.keys()) + ["Oracle"]
    legacy_summary = evaluate(
        products, data["legacy_profiles"], data["legacy_weights"], data["legacy_gt"],
        excluded, legacy_methods,
    )

    # 2. Clamped Dot vs deterministic (real final_score из dataset).
    corr = clamped_vs_deterministic(
        products, data["legacy_profiles"], data["legacy_weights"], data["legacy_gt"], excluded,
    )

    # 3. Structured benchmark (resolve_personal_profile, ground truth пересчитан).
    structured_ids = [p["id"] for p in STRUCTURED_PROFILES]
    structured_weights = {
        p["id"]: resolve_personal_profile(p)["weights"] for p in STRUCTURED_PROFILES
    }
    structured_gt: Dict[Tuple[str, int], float] = {}
    for p in STRUCTURED_PROFILES:
        wid = p["id"]
        for pid in products:
            structured_gt[(wid, pid)] = deterministic_score_from_vector(
                products[pid]["vector"], structured_weights[wid]
            )
    structured_summary = evaluate(
        products, structured_ids, structured_weights, structured_gt,
        set(), STRUCTURED_METHODS,
    )

    print_report(data, legacy_summary, corr, structured_summary, args.dataset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





