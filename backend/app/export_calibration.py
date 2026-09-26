# export_calibration.py
# CLI для выгрузки calibration dataset — снимок работы deterministic scoring engine.
#
# НЕ меняет production scoring. Просто прогоняет РЕАЛЬНЫЙ движок
# (scoring_engine.score_product_against_profile_canonical через AnalysisService)
# на выборке продуктов × синтетических профилей и сохраняет ПОЛНЫЙ breakdown,
# чтобы внешний анализатор мог восстановить, ПОЧЕМУ получен конкретный score.
#
# Запуск:
#   python -m app.export_calibration --count 500 --seed 12345 --out calibration
#   python -m app.export_calibration --count 500 --format jsonl
#
# Выход:
#   <out>/dataset.json        — записи анализа (или dataset.jsonl при --format jsonl)
#   <out>/scoring_config.json — snapshot scoring_config (versioned)
#   <out>/metadata.json       — версии, seed, git_commit, статистика БД

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analysis_service import AnalysisService
from .axes import canonicalize_weights
from .database import AIDERMY_DB, PRODUCTS_DB, get_connection
from .decision_engine import priorities_for_profile
from .ingredient_normalizer import normalize_ingredient_name
from .scoring_config import (
    AXES,
    AXIS_LABELS,
    HARD_FLAG_SCORE_CAP,
    INTOLERANCE_PENALTY,
    SCORING_CONFIG,
    SCORING_CONFIG_VERSION,
    UNKNOWN_SCORE_FLOOR,
)
from .scoring_engine import apply_hard_filters, score_product_against_profile_canonical

# Версия формата dataset (не зависит от версии scoring config).
DATASET_VERSION = "1.0.0"


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Синтетические профили пользователей (детерминированные, фиксированный список).
#
# Используются ТОЛЬКО те параметры, которые реально поддерживает система профилей:
#   - skin_type  — матчится по подстроке в SKIN_TYPE_WEIGHTS (decision_engine);
#   - concerns   — матчится по подстроке в CONCERN_WEIGHTS (decision_engine);
#   - allergies / intolerances / restrictions / preferences — читаются scoring engine.
# Значения подобраны так, чтобы реально менять веса (см. _CONCERN_TO_GOALS и
# SKIN_TYPE_WEIGHTS). Ничего не выдумано — все ключи существуют в движке.
# ---------------------------------------------------------------------------
SYNTHETIC_PROFILES: List[Dict[str, Any]] = [
    {"id": "oily",             "label": "Oily",
     "skin_type": "Жирная",          "concerns": ["Акне", "Поры"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "dry",              "label": "Dry",
     "skin_type": "Сухая",           "concerns": ["Обезвоженность"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "combination",      "label": "Combination",
     "skin_type": "Комбинированная", "concerns": ["Акне"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "normal",           "label": "Normal",
     "skin_type": "Нормальная",      "concerns": [],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "sensitive",        "label": "Sensitive",
     "skin_type": "Чувствительная",  "concerns": ["Покраснения", "Купероз"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "acne_prone",       "label": "Acne-prone",
     "skin_type": "Жирная",          "concerns": ["Акне", "Поры", "Покраснения"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "oily_sensitive",   "label": "Oily + sensitive",
     "skin_type": "Жирная",          "concerns": ["Акне", "Покраснения"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "dry_sensitive",    "label": "Dry + sensitive",
     "skin_type": "Сухая",           "concerns": ["Покраснения", "Обезвоженность"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "combination_acne", "label": "Combination + acne-prone",
     "skin_type": "Комбинированная", "concerns": ["Акне", "Поры"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
    {"id": "normal_sensitive", "label": "Normal + sensitive",
     "skin_type": "Нормальная",      "concerns": ["Покраснения"],
     "allergies": [], "intolerances": [], "restrictions": [], "preferences": []},
]


def _split_ingredients(raw: Any) -> List[str]:
    """Разбивает INCI-строку на список ингредиентов (как в БД хранится)."""
    if not raw:
        return []
    out: List[str] = []
    for part in str(raw).replace("\r", "\n").replace(";", ",").split(","):
        for piece in part.split("\n"):
            piece = piece.strip()
            if piece and piece not in out:
                out.append(piece)
    return out


def _ingredient_count(raw: Any) -> int:
    return len(_split_ingredients(raw))


# ---------------------------------------------------------------------------
# Загрузка продуктов
# ---------------------------------------------------------------------------
def load_canonical_products() -> List[Dict[str, Any]]:
    """Все canonical продукты из products.db."""
    conn = get_connection(PRODUCTS_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM products WHERE is_canonical = 1"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _allocate_quotas(group_sizes: Dict[str, int], total: int) -> Dict[str, int]:
    """Распределяет `total` квот пропорционально размерам групп (метод Гамильтона).

    Гарантирует: сумма квот == total, маленькие группы не обнуляются (если total
    достаточно), доминирующая категория не «съедает» всю выборку.
    """
    if not group_sizes:
        return {}

    n = len(group_sizes)
    # Каждая непустая группа получает минимум 1, если total позволяет.
    floor = {g: 1 for g, size in group_sizes.items() if size > 0}
    remaining = total - sum(floor.values())

    if remaining <= 0:
        # Слишком мало квот на все группы — отдаём приоритет самым крупным.
        result: Dict[str, int] = {}
        for g in sorted(group_sizes, key=lambda g: -group_sizes[g]):
            if len(result) >= total:
                break
            result[g] = 1
        return result

    total_size = sum(group_sizes.values())
    exact = {g: (size * remaining) / total_size for g, size in group_sizes.items()}
    base = {g: int(exact[g]) for g in group_sizes}
    result = {g: floor[g] + base[g] for g in group_sizes}

    # Добор остатка по наибольшей дробной части (детерминированно, по (дробь, имя)).
    leftover = total - sum(result.values())
    order = sorted(group_sizes, key=lambda g: (-(exact[g] - base[g]), g))
    for i in range(leftover):
        result[order[i % n]] += 1
    return result


def _sample_group(group: List[Dict[str, Any]], quota: int, rng: random.Random) -> List[Dict[str, Any]]:
    """Выбирает `quota` продуктов из группы, равномерно распределяя по количеству
    ингредиентов (систематическая выборка по отсортированному списку + seed)."""
    if quota <= 0:
        return []
    if quota >= len(group):
        return list(group)

    ordered = sorted(group, key=lambda p: (p.get("_ing_count", 0), p.get("id", 0)))
    step = len(ordered) / quota
    start = rng.uniform(0.0, step)
    picked: List[Dict[str, Any]] = []
    seen = set()
    for i in range(quota):
        idx = min(len(ordered) - 1, int(start + i * step))
        if idx not in seen:
            seen.add(idx)
            picked.append(ordered[idx])
    # Добрать недостающих (при дублях индексов) — начиная с несобранных позиций.
    if len(picked) < quota:
        for p in ordered:
            if len(picked) >= quota:
                break
            if p not in picked:
                picked.append(p)
    return picked


def sample_products(products: List[Dict[str, Any]], count: int, seed: int) -> List[Dict[str, Any]]:
    """Разнообразная репрезентативная выборка (не «первые N из БД»).

    Стратификация по категории + равномерное покрытие диапазона количества
    ингредиентов внутри категории. Детерминированно через seed.
    """
    rng = random.Random(seed)
    for p in products:
        p["_ing_count"] = _ingredient_count(p.get("ingredients"))

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for p in products:
        key = p.get("category") or p.get("taxonomy_category") or "Неизвестно"
        groups.setdefault(key, []).append(p)

    if count >= len(products):
        return list(products)

    quotas = _allocate_quotas({g: len(v) for g, v in groups.items()}, count)
    selected: List[Dict[str, Any]] = []
    for g, quota in sorted(quotas.items()):
        selected.extend(_sample_group(groups[g], quota, rng))

    # Дедупликация по id и добор до count (на случай коллизий).
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for p in selected:
        pid = p.get("id")
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        deduped.append(p)

    if len(deduped) < count:
        for p in products:
            if len(deduped) >= count:
                break
            if p.get("id") not in seen_ids:
                deduped.append(p)
                seen_ids.add(p.get("id"))

    return deduped[:count]


def _git_commit() -> Optional[str]:
    """Текущий git-commit (если доступен)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _knowledge_base_stats() -> Dict[str, Any]:
    """Статистика базы знаний (для metadata — помогает понять полноту scoring)."""
    stats: Dict[str, Any] = {}
    try:
        conn = get_connection(AIDERMY_DB)
        conn.row_factory = sqlite3.Row
        try:
            for table in ("ingredients_catalog", "ingredient_claims", "ingredient_interactions"):
                try:
                    stats[table] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
                except Exception:
                    stats[table] = None
        finally:
            conn.close()
    except Exception:
        stats["error"] = "unable to read aidermy.db"
    return stats


# ---------------------------------------------------------------------------
# Скоринг + построение explainable breakdown
# ---------------------------------------------------------------------------
def _matched_intolerances(profile: Dict[str, Any], ingredients: List[str]) -> set:
    """Возвращает нормализованные имена intolerances, реально найденных в составе.

    Зеркалит логику scoring_engine (независимо от knowledge base): мягкий
    негативный вклад за непереносимость.
    """
    matched = set()
    for item in profile.get("intolerances") or []:
        key = normalize_ingredient_name(item)
        if not key:
            continue
        for ingredient in ingredients:
            ni = normalize_ingredient_name(ingredient)
            if ni and (key == ni or key in ni or ni in key):
                matched.add(key)
                break
    return matched


def _scoring_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Профиль в том виде, в котором его читает scoring engine."""
    return {
        "skin_type": profile.get("skin_type", ""),
        "concerns": list(profile.get("concerns") or []),
        "allergies": list(profile.get("allergies") or []),
        "intolerances": list(profile.get("intolerances") or []),
        "restrictions": list(profile.get("restrictions") or []),
    }


def _ingredient_contributions(
    positive_factors: List[Dict[str, Any]],
    negative_factors: List[Dict[str, Any]],
    matched_intolerances: set,
) -> List[Dict[str, Any]]:
    """Группирует factors по ингредиенту → per-axis signed contribution.

    contribution(фактора) = sign × strength × confidence × position_weight.
    Непереносимости (intolerance) выносятся отдельно в penalties и не попадают
    сюда, чтобы не задваиваться с dimension_delta (их вычет в движке — плоский).
    """
    aggregated: Dict[str, Dict[str, float]] = {}
    seen_order: List[str] = []

    def _add(ingredient: str, axis: str, value: float) -> None:
        if ingredient not in aggregated:
            aggregated[ingredient] = {}
            seen_order.append(ingredient)
        aggregated[ingredient][axis] = aggregated[ingredient].get(axis, 0.0) + value

    for sign, factors in ((1.0, positive_factors), (-1.0, negative_factors)):
        for f in factors:
            ingredient = str(f.get("ingredient") or "")
            key = normalize_ingredient_name(ingredient)
            if not ingredient:
                continue
            if key and key in matched_intolerances and f.get("property") == INTOLERANCE_PENALTY["axis"]:
                continue  # intolerance → penalties
            axis = str(f.get("property") or "")
            if axis not in AXES:
                continue
            value = (
                sign
                * float(f.get("strength") or 0.0)
                * float(f.get("confidence") or 0.0)
                * float(f.get("position_weight") or 1.0)
            )
            _add(ingredient, axis, value)

    out: List[Dict[str, Any]] = []
    for ingredient in seen_order:
        per_axis = aggregated[ingredient]
        total = sum(per_axis.values())
        out.append({
            "ingredient_name": ingredient,
            "parameters": {axis: round(per_axis.get(axis, 0.0), 6) for axis in AXES},
            "total_contribution": round(total, 6),
        })
    return out


def score_one(
    product: Dict[str, Any],
    profile: Dict[str, Any],
    service: AnalysisService,
    knowledge: Dict[str, Any],
) -> Dict[str, Any]:
    """Полный breakdown анализа (product × profile) реальным scoring engine."""
    normalized = service.prepare_product_ingredients(product.get("ingredients") or "")
    scoring_profile = _scoring_profile(profile)

    hard_filters = apply_hard_filters(scoring_profile, normalized)
    weights = canonicalize_weights(
        priorities_for_profile(scoring_profile, scoring_profile.get("skin_type", ""))
    )
    result = score_product_against_profile_canonical(
        ingredients=normalized,
        canonical_knowledge=knowledge,
        user_profile=scoring_profile,
        canonical_weights=weights,
        interactions=None,
    )

    dimensions = result["dimensions"]
    positive = result["positive_factors"]
    negative = result["negative_factors"]
    unknown = result["unknown_factors"]
    hard_flags = result["hard_flags"]

    matched = _matched_intolerances(scoring_profile, normalized)

    # Реконструкция raw/normalized из dimensions (движок округляет dimensions до 3 знаков).
    weighted_total = sum(
        _clamp(dimensions.get(axis, 0.0), 0.0, 1.0) * weight
        for axis, weight in weights.items()
    )
    normalized_score = _clamp(weighted_total / max(sum(weights.values()), 1e-9), 0.0, 1.0)

    # Бонусы / штрафы (объяснение «почему именно такой score»).
    bonuses: List[Dict[str, Any]] = []
    penalties: List[Dict[str, Any]] = []

    unknown_floor_applied = bool(unknown) and not positive and not negative and not hard_flags
    if unknown_floor_applied:
        bonuses.append({
            "type": "unknown_score_floor",
            "applied": True,
            "floor": UNKNOWN_SCORE_FLOOR,
            "note": "Все ингредиенты неизвестны — score поднят до порога.",
        })

    if hard_flags:
        penalties.append({
            "type": "hard_flag_cap",
            "applied": True,
            "cap": HARD_FLAG_SCORE_CAP,
            "flags": hard_flags,
            "note": "Найден жёсткий флаг (аллергия/restriction) — score ограничен сверху.",
        })

    for item in profile.get("intolerances") or []:
        key = normalize_ingredient_name(item)
        if key and key in matched:
            penalties.append({
                "type": "intolerance",
                "ingredient": item,
                "axis": INTOLERANCE_PENALTY["axis"],
                "delta": -float(INTOLERANCE_PENALTY["dimension_delta"]),
                "note": "Непереносимость найдена в составе — мягкий негативный вклад.",
            })

    return {
        "analysis_id": f"{product.get('id')}:{profile.get('id')}",
        "product": {
            "id": product.get("id"),
            "name": " ".join((product.get("name") or "").split()),
            "brand": product.get("brand") or None,
            "category": product.get("category") or None,
            "subcategory": product.get("subcategory") or None,
            "taxonomy_category": product.get("taxonomy_category") or None,
            "ingredients": normalized,
            "ingredient_count": len(normalized),
        },
        "profile": {
            "id": profile.get("id"),
            "label": profile.get("label"),
            "skin_type": profile.get("skin_type"),
            "concerns": list(profile.get("concerns") or []),
            "allergies": list(profile.get("allergies") or []),
            "intolerances": list(profile.get("intolerances") or []),
            "restrictions": list(profile.get("restrictions") or []),
            "preferences": list(profile.get("preferences") or []),
        },
        "scoring": {
            "final_score": int(result["score"]),
            "raw_score": round(weighted_total, 6),
            "normalized_score": round(normalized_score, 6),
            "confidence": result["confidence"],
            "excluded": bool(hard_filters),
            "parameter_scores": {axis: dimensions.get(axis, 0.0) for axis in AXES},
            "weights": {axis: weights.get(axis, 0.0) for axis in AXES},
            "ingredient_contributions": _ingredient_contributions(positive, negative, matched),
            "interaction_contributions": result["interaction_breakdown"],
            "bonuses": bonuses,
            "penalties": penalties,
            "unknown_ingredients": [u.get("ingredient") for u in unknown],
            "hard_flags": hard_flags,
            "hard_filters": hard_filters,
        },
    }


# ---------------------------------------------------------------------------
# Оркестрация экспорта + статистика
# ---------------------------------------------------------------------------
def _unavailable_data_notes() -> List[Dict[str, str]]:
    """Честный список данных, которых нет в текущей архитектуре/БД."""
    return [
        {
            "field": "product.brand",
            "where": "products.db (products.brand)",
            "reason": "Колонка brand пуста во всех строках — экспорт ставит null.",
        },
        {
            "field": "parameter_scores.comedogenicity",
            "where": "scoring_config.DATA_MODEL_PARAMETERS / ingredients_catalog.comedogenicity",
            "reason": "comedogenicity хранится в модели данных, но НЕ является scoring-осью "
                     "(сознательно не смешивается с sebum/irritation) — фиктивное значение не подставляется.",
        },
        {
            "field": "ingredient_contributions[].ingredient_id",
            "where": "products.ingredients (INCI-строки)",
            "reason": "Продукт хранит ингредиенты строками INCI, а не id из ingredients_catalog — "
                     "используется ingredient_name, а не ingredient_id.",
        },
        {
            "field": "product_type_modifiers",
            "where": "scoring_config.PRODUCT_TYPE_MODIFIERS",
            "reason": "modifiers для типов продуктов в текущем scoring engine отсутствуют.",
        },
    ]


def _export_stats(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    from collections import Counter

    categories = Counter(
        (r["product"].get("category") or r["product"].get("taxonomy_category") or "Неизвестно")
        for r in records
    )
    skin_types = Counter(r["profile"].get("skin_type") or "" for r in records)

    empty_breakdown = 0
    for r in records:
        s = r["scoring"]
        if not s["ingredient_contributions"] and not s["interaction_contributions"] \
                and not s["penalties"] and not s["hard_flags"]:
            empty_breakdown += 1

    return {
        "categories": dict(sorted(categories.items(), key=lambda kv: -kv[1])),
        "skin_types": dict(sorted(skin_types.items(), key=lambda kv: -kv[1])),
        "empty_breakdown_count": empty_breakdown,
    }


def run_export(count: int, seed: int, out_dir: str, fmt: str) -> int:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    products = load_canonical_products()
    sample = sample_products(products, count, seed)

    # Анализ реальным движком (AnalysisService реплицирует production-путь).
    service = AnalysisService()
    knowledge = service.repository.get_canonical_knowledge_map()

    records: List[Dict[str, Any]] = []
    for product in sample:
        for profile in SYNTHETIC_PROFILES:
            records.append(score_one(product, profile, service, knowledge))

    stats = _export_stats(records)

    dataset_path = out_path / ("dataset.json" if fmt == "json" else "dataset.jsonl")
    config_path = out_path / "scoring_config.json"
    metadata_path = out_path / "metadata.json"

    if fmt == "json":
        dataset_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    elif fmt == "jsonl":
        with dataset_path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        raise ValueError(f"Unknown format: {fmt}")

    config_path.write_text(
        json.dumps(SCORING_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    metadata = {
        "dataset_version": DATASET_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_count": len(sample),
        "profile_count": len(SYNTHETIC_PROFILES),
        "analysis_count": len(records),
        "random_seed": seed,
        "git_commit": _git_commit(),
        "knowledge_base": _knowledge_base_stats(),
        "axis_labels": AXIS_LABELS,
        "unavailable_data": _unavailable_data_notes(),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _print_stats(len(sample), len(SYNTHETIC_PROFILES), len(records), stats,
                 dataset_path, config_path, metadata_path)
    return 0


def _print_stats(product_count, profile_count, analysis_count, stats,
                 dataset_path, config_path, metadata_path):
    print("Calibration export completed")
    print()
    print(f"Products: {product_count}")
    print(f"Profiles per product: {profile_count}")
    print(f"Total analyses: {analysis_count}")
    print()
    print("Categories:")
    for name, n in stats["categories"].items():
        print(f"  {name}: {n}")
    print()
    print("Skin types:")
    for name, n in stats["skin_types"].items():
        print(f"  {name}: {n}")
    print()
    print("Output:")
    print(f"  {dataset_path}")
    print(f"  {config_path}")
    print(f"  {metadata_path}")

    if stats["empty_breakdown_count"]:
        print()
        print(
            f"WARNING: {stats['empty_breakdown_count']} analyses have empty scoring breakdown "
            f"(no ingredient knowledge in DB)."
        )
        print(
            "  Ingredient knowledge (ingredients_catalog/ingredient_claims) is empty — "
            "populated at runtime by AI enrichment (DEEPSEEK_API_KEY)."
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export calibration dataset for scoring engine audit"
    )
    parser.add_argument("--count", type=int, default=500,
                        help="Number of products to sample (default 500)")
    parser.add_argument("--seed", type=int, default=12345,
                        help="Random seed for reproducible sampling (default 12345)")
    parser.add_argument("--out", default="calibration",
                        help="Output directory (default calibration)")
    parser.add_argument("--format", choices=["json", "jsonl"], default="json",
                        help="Dataset format (default json)")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return run_export(args.count, args.seed, args.out, args.format)


if __name__ == "__main__":
    raise SystemExit(main())


