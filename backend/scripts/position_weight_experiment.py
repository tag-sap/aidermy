"""Офлайн-эксперимент: позиционный вес INCI (не влияет на production).

Baseline — текущий production Score Engine без override.
Кандидаты — position_config (power / two_phase / none) через run_score_engine.

Дизайн:
  * выборка: calibration_references (AI reference: estimate/range) × products;
  * split по product_id (один продукт встречается в 30 профилях → делим по продуктам);
  * параметры подбираются только на train (60%), holdout (20%) — финальная проверка;
  * метрики: MAE, median AE, signed error, coverage, over/under, распределение;
  * bootstrap по продуктам (кластер) для ΔMAE на holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Tuple

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

from dotenv import load_dotenv, dotenv_values  # noqa: E402

load_dotenv(".env")

import psycopg  # noqa: E402

from app.calibration_profiles import CALIBRATION_PROFILES  # noqa: E402
from app.calibration_service import run_score_engine  # noqa: E402
from app.ingredient_repository import IngredientRepository  # noqa: E402
from app.scoring_config_store import get_production_saturation_scale  # noqa: E402

# Production Score Engine читает saturation_scale из scoring_config_store (сейчас 1.2),
# а run_score_engine по умолчанию берёт константу 1.5. Для корректного baseline
# фиксируем реальное production-значение и НЕ меняем его ни у одного кандидата.
PRODUCTION_SATURATION_SCALE = get_production_saturation_scale()


def _install_goal_evidence_cache() -> None:
    """Кэш goal-evidence по составу: ускоряет эксперимент, НЕ влияет на score.

    get_goal_evidence_map не зависит от профиля и в scoring не участвует —
    результат только добавляется в payload. В проде это один запрос на проверку,
    в офлайн-эксперименте (300 продуктов × 30 профилей) — 8879 запросов.
    """
    original = IngredientRepository.get_goal_evidence_map
    cache: Dict[Tuple[str, ...], Dict[str, Dict[str, Dict[str, Any]]]] = {}

    def cached(self, ingredients=None):
        key = tuple(sorted(str(i) for i in (ingredients or [])))
        if key not in cache:
            cache[key] = original(self, ingredients)
        return cache[key]

    IngredientRepository.get_goal_evidence_map = cached


_install_goal_evidence_cache()

CACHE_DIR = "/tmp/position_exp"
SPLIT_SEED = 20261019
TRAIN_FRACTION = 0.60
HOLDOUT_FRACTION = 0.20

# Кандидаты зафиксированы ДО просмотра результатов эксперимента.
CANDIDATES: Dict[str, Dict[str, Any]] = {
    "none": {"mode": "none"},
    "power_e1_m20_both": {"mode": "power", "exponent": 1.0, "min_weight": 0.20, "apply_to": "both"},
    "power_e15_m20_both": {"mode": "power", "exponent": 1.5, "min_weight": 0.20, "apply_to": "both"},
    "power_e1_m30_both": {"mode": "power", "exponent": 1.0, "min_weight": 0.30, "apply_to": "both"},
    "power_e1_m20_negative": {"mode": "power", "exponent": 1.0, "min_weight": 0.20, "apply_to": "negative"},
    "power_e15_m30_both": {"mode": "power", "exponent": 1.5, "min_weight": 0.30, "apply_to": "both"},
    "two_phase_e30_m20_both": {"mode": "two_phase", "early_fraction": 0.30, "min_weight": 0.20, "apply_to": "both"},
}

LATE_IRRITANTS = (
    "fragrance", "parfum", "alcohol denat", "limonene", "linalool", "citral",
    "geraniol", "eugenol", "citronellol", "hexyl cinnamal", "benzyl alcohol",
    "benzyl salicylate", "coumarin", "isoeugenol", "amyl cinnamal",
)


def _key(product_id: int, profile_id: str) -> str:
    return f"{product_id}:{profile_id}"


def _json_load(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _json_dump(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)



def load_dataset() -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """Все calibration cases + references + метаданные продуктов."""
    dsn = dotenv_values(".env")["SUPABASE_DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cr.product_id, cr.profile_id, cr.reference,
                       p.name, p.ingredients, p.catalog_category
                FROM public.calibration_references cr
                JOIN public.products p ON p.id = cr.product_id
                WHERE p.ingredients IS NOT NULL
                  AND btrim(p.ingredients) <> ''
                  AND (p.catalog_category IS NULL OR p.catalog_category <> 'Уход за губами')
                """
            )
            rows = cur.fetchall()
    profiles = {p["id"]: p for p in CALIBRATION_PROFILES}
    cases: List[Dict[str, Any]] = []
    ref_map: Dict[str, Dict[str, Any]] = {}
    products: Dict[int, Dict[str, Any]] = {}
    for pid, prid, ref, name, ingredients, category in rows:
        profile = profiles.get(prid)
        if not profile:
            continue
        try:
            parsed = json.loads(ref) if isinstance(ref, str) else dict(ref)
        except Exception:
            continue
        if parsed.get("estimate") is None:
            continue
        product = {
            "id": int(pid),
            "name": (name or "").replace("\n", " ").strip(),
            "category": category or "",
            "ingredients": ingredients or "",
        }
        products[int(pid)] = product
        cases.append({"product": product, "profile": profile})
        ref_map[_key(int(pid), prid)] = parsed
    return cases, ref_map, products


def split_products(products: Dict[int, Dict[str, Any]]) -> Dict[str, List[int]]:
    ids = sorted(products)
    random.Random(SPLIT_SEED).shuffle(ids)
    n = len(ids)
    n_train = int(n * TRAIN_FRACTION)
    n_holdout = int(n * HOLDOUT_FRACTION)
    return {
        "train": ids[:n_train],
        "holdout": ids[n_train:n_train + n_holdout],
        "unused": ids[n_train + n_holdout:],
        "all": ids,
    }


def _ingredients_hash(product: Dict[str, Any]) -> str:
    text = " ".join(str(product.get("ingredients") or "").lower().split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def leakage_report(cases: List[Dict[str, Any]], splits: Dict[str, List[int]]) -> Dict[str, Any]:
    train_ids, holdout_ids = set(splits["train"]), set(splits["holdout"])
    train_hashes = {_ingredients_hash(c["product"]) for c in cases if c["product"]["id"] in train_ids}
    holdout_hashes = {_ingredients_hash(c["product"]) for c in cases if c["product"]["id"] in holdout_ids}
    overlap_ids = train_ids & holdout_ids
    dup_hashes = train_hashes & holdout_hashes
    return {
        "train_products": len(train_ids),
        "holdout_products": len(holdout_ids),
        "product_id_overlap": len(overlap_ids),
        "identical_inci_overlap": len(dup_hashes),
        "identical_inci_overlap_examples": sorted(dup_hashes)[:5],
    }


def run_cases(cases: List[Dict[str, Any]], config: Dict[str, Any] | None) -> Dict[str, int]:
    payload: Dict[str, Any] = {"saturation_scale": PRODUCTION_SATURATION_SCALE}
    if config:
        payload["position_config"] = config
    results = run_score_engine(cases, payload)
    return {
        _key(r["product"]["id"], r["profile"]["id"]): int(r["score"])
        for r in results
    }


def _is_late_irritant(product: Dict[str, Any]) -> bool:
    parts = [p.strip().lower() for p in str(product.get("ingredients") or "").split(",") if p.strip()]
    if not parts:
        return False
    tail_start = int(len(parts) * 0.66)
    return any(any(irr in part for irr in LATE_IRRITANTS) for part in parts[tail_start:])


def _has_ingredient(product: Dict[str, Any], needle: str) -> bool:
    return needle in str(product.get("ingredients") or "").lower()


def metrics(
    scores: Dict[str, int],
    cases: List[Dict[str, Any]],
    ref_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    deltas: List[int] = []
    abs_deltas: List[int] = []
    inside = over = under = 0
    values: List[int] = []
    for case in cases:
        key = _key(case["product"]["id"], case["profile"]["id"])
        if key not in scores:
            continue
        ref = ref_map.get(key)
        if not ref:
            continue
        score = int(scores[key])
        estimate = int(ref["estimate"])
        lo, hi = int(ref.get("range_min", estimate)), int(ref.get("range_max", estimate))
        delta = score - estimate
        deltas.append(delta)
        abs_deltas.append(abs(delta))
        values.append(score)
        if lo <= score <= hi:
            inside += 1
        elif score > hi:
            over += 1
        else:
            under += 1
    n = len(deltas)
    if n == 0:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": n,
        "mae": round(sum(abs_deltas) / n, 3),
        "median_abs_error": round(statistics.median(abs_deltas), 3),
        "signed_error": round(sum(deltas) / n, 3),
        "coverage": round(inside / n, 4),
        "overestimation_rate": round(over / n, 4),
        "underestimation_rate": round(under / n, 4),
        "score_mean": round(sum(values) / n, 2),
        "score_p10": ordered[int(n * 0.10)],
        "score_p50": ordered[n // 2],
        "score_p90": ordered[min(n - 1, int(n * 0.90))],
        "neutral_share_45_55": round(sum(1 for v in values if 45 <= v <= 55) / n, 4),
        "within_5_points": round(sum(1 for d in abs_deltas if d <= 5) / n, 4),
    }


def grouped_metrics(
    scores: Dict[str, int],
    cases: List[Dict[str, Any]],
    ref_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    buckets: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for case in cases:
        product = case["product"]
        profile = case["profile"]
        groups = {
            "skin_type": str(profile.get("structured", {}).get("skin_type") or "?"),
            "category": product.get("category") or "?",
            "citric_acid": "yes" if _has_ingredient(product, "citric acid") else "no",
            "late_irritant": "yes" if _is_late_irritant(product) else "no",
            "application": (
                "rinse_off" if product.get("category") == "Очищение" else "leave_on"
            ),
        }
        for name, value in groups.items():
            buckets[name][value].append(case)
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for group, values in buckets.items():
        out[group] = {}
        for value, subset in values.items():
            if len(subset) < 60:
                continue
            out[group][value] = metrics(scores, subset, ref_map)
    return out


def bootstrap_delta_mae(
    base_scores: Dict[str, int],
    cand_scores: Dict[str, int],
    cases: List[Dict[str, Any]],
    ref_map: Dict[str, Dict[str, Any]],
    iterations: int = 1000,
    seed: int = 7,
) -> Dict[str, Any]:
    """Кластерный bootstrap по product_id: 95% CI для ΔMAE (cand - base)."""
    by_product: Dict[int, List[float]] = defaultdict(list)
    for case in cases:
        key = _key(case["product"]["id"], case["profile"]["id"])
        ref = ref_map.get(key)
        if not ref or key not in base_scores or key not in cand_scores:
            continue
        estimate = int(ref["estimate"])
        by_product[case["product"]["id"]].append(
            abs(cand_scores[key] - estimate) - abs(base_scores[key] - estimate)
        )
    products = [pid for pid, values in by_product.items() if values]
    if len(products) < 10:
        return {"products": len(products), "note": "too_few_products"}
    rng = random.Random(seed)
    deltas: List[float] = []
    for _ in range(iterations):
        sample = [by_product[rng.choice(products)] for _ in products]
        flat = [value for values in sample for value in values]
        deltas.append(sum(flat) / len(flat))
    deltas.sort()
    observed = sum(v for values in by_product.values() for v in values) / sum(
        len(values) for values in by_product.values()
    )
    return {
        "products": len(products),
        "delta_mae": round(observed, 3),
        "ci_low": round(deltas[int(iterations * 0.025)], 3),
        "ci_high": round(deltas[int(iterations * 0.975)], 3),
        "p_better": round(sum(1 for d in deltas if d < 0) / len(deltas), 3),
    }


def subset_cases(cases: List[Dict[str, Any]], product_ids: List[int]) -> List[Dict[str, Any]]:
    allowed = set(product_ids)
    return [c for c in cases if c["product"]["id"] in allowed]



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True,
                        choices=["baseline", "candidates", "holdout", "report", "prepare"])
    parser.add_argument("--candidate", default="")
    parser.add_argument("--out", default="/tmp/position_experiment.json")
    args = parser.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)
    cases, ref_map, products = load_dataset()
    splits = split_products(products)

    if args.stage == "prepare":
        report = {
            "cases": len(cases),
            "products": len(products),
            "splits": {name: len(ids) for name, ids in splits.items()},
            "leakage": leakage_report(cases, splits),
            "citric_products": sum(1 for p in products.values() if _has_ingredient(p, "citric acid")),
            "production_saturation_scale": PRODUCTION_SATURATION_SCALE,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        _json_dump(os.path.join(CACHE_DIR, "dataset.json"), report)
        return

    train_cases = subset_cases(cases, splits["train"])
    holdout_cases = subset_cases(cases, splits["holdout"])

    if args.stage == "baseline":
        started = time.time()
        scores = run_cases(cases, None)
        _json_dump(os.path.join(CACHE_DIR, "baseline_all.json"), scores)
        print(json.dumps({
            "baseline_cases": len(scores),
            "seconds": round(time.time() - started, 1),
            "train": metrics(scores, train_cases, ref_map),
            "holdout": metrics(scores, holdout_cases, ref_map),
            "all": metrics(scores, cases, ref_map),
        }, ensure_ascii=False, indent=2))
        return

    if args.stage == "candidates":
        baseline = _json_load(os.path.join(CACHE_DIR, "baseline_all.json")) or {}
        base_train = metrics(baseline, train_cases, ref_map)
        results: Dict[str, Any] = {}
        for name, config in CANDIDATES.items():
            path = os.path.join(CACHE_DIR, f"cand_{name}_train.json")
            started = time.time()
            scores = run_cases(train_cases, config)
            _json_dump(path, scores)
            train_metrics = metrics(scores, train_cases, ref_map)
            results[name] = {
                "config": config,
                "seconds": round(time.time() - started, 1),
                "train": train_metrics,
                "delta_mae_train": round(train_metrics["mae"] - base_train["mae"], 3),
            }
            print(name, json.dumps(train_metrics, ensure_ascii=False))
        _json_dump(os.path.join(CACHE_DIR, "candidates_train.json"), results)
        return

    if args.stage == "holdout":
        if not args.candidate:
            raise SystemExit("--candidate required")
        baseline = _json_load(os.path.join(CACHE_DIR, "baseline_all.json")) or {}
        config = CANDIDATES[args.candidate]
        scores = run_cases(holdout_cases, config)
        _json_dump(os.path.join(CACHE_DIR, f"cand_{args.candidate}_holdout.json"), scores)
        payload = {
            "candidate": args.candidate,
            "config": config,
            "baseline_holdout": metrics(baseline, holdout_cases, ref_map),
            "candidate_holdout": metrics(scores, holdout_cases, ref_map),
            "bootstrap": bootstrap_delta_mae(baseline, scores, holdout_cases, ref_map),
            "groups": grouped_metrics(scores, holdout_cases, ref_map),
            "baseline_groups": grouped_metrics(baseline, holdout_cases, ref_map),
        }
        _json_dump(os.path.join(CACHE_DIR, f"holdout_{args.candidate}.json"), payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.stage == "report":
        baseline = _json_load(os.path.join(CACHE_DIR, "baseline_all.json")) or {}
        candidates = _json_load(os.path.join(CACHE_DIR, "candidates_train.json")) or {}
        holdouts = {}
        for name in CANDIDATES:
            payload = _json_load(os.path.join(CACHE_DIR, f"holdout_{name}.json"))
            if payload:
                holdouts[name] = payload
        payload = {
            "dataset": _json_load(os.path.join(CACHE_DIR, "dataset.json")),
            "baseline": {
                "train": metrics(baseline, train_cases, ref_map),
                "holdout": metrics(baseline, holdout_cases, ref_map),
            },
            "candidates_train": candidates,
            "holdout": holdouts,
        }
        _json_dump(args.out, payload)
        print(json.dumps({
            "out": args.out,
            "baseline_holdout": payload["baseline"]["holdout"],
            "holdouts": {k: v["candidate_holdout"] for k, v in holdouts.items()},
        }, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
