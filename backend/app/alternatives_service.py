"""Подбор альтернатив выбранному продукту.

Подбор опирается на уже существующие механизмы Aidermy:

* категория и назначение — ``catalog_taxonomy.classify_product``;
* состав — нормализованные INCI (``ingredient_normalizer``) и knowledge map
  (``ingredient_repository``);
* совместимость с кожей — детерминированный Score Engine через
  ``shelf_service._deterministic_analysis`` (тот же вход, что у рекомендаций
  и полки).

Цены здесь не считаются: их отдаёт ``price_service`` отдельным запросом, чтобы
колода карточек открывалась мгновенно, а внешний поиск шёл по мере показа карточки.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .database import PRODUCTS_DB, get_connection, get_product_by_id

logger = logging.getLogger(__name__)

# Доля общих «значимых» ингредиентов, ниже которой продукт не считается похожим.
MIN_SIMILARITY = 0.30
CANDIDATE_LIMIT = 400
MAX_ALTERNATIVES = 12

_ACTIVE_HINTS = (
    "niacinamide", "retinol", "retinal", "salicylic", "glycolic", "lactic", "mandelic",
    "hyaluronic", "ceramide", "ascorbic", "azelaic", "panthenol", "allantoin",
    "centella", "madecassoside", "peptide", "zinc pca", "squalane", "urea",
    "adenosine", "tranexamic", "arbutin", "bakuchiol", "caffeine", "collagen",
    "tocopherol", "tocopheryl", "bisabolol", "ectoin", "glycerin",
)


def _split_name(name: str) -> Tuple[str, str]:
    from .shelf_service import _split_name as split

    return split(name or "")


def _clean_name(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _ingredient_set(text: str) -> set[str]:
    from .ingredient_normalizer import canonicalize_ingredient_name

    result: set[str] = set()
    for raw in str(text or "").split(","):
        item = raw.strip()
        if not item:
            continue
        canonical = canonicalize_ingredient_name(item) or item.lower()
        if canonical:
            result.add(canonical)
    return result


def _is_notable(name: str, knowledge: Optional[Dict[str, Any]]) -> bool:
    if any(hint in name for hint in _ACTIVE_HINTS):
        return True
    if knowledge:
        entry = knowledge.get(name)
        if isinstance(entry, dict) and entry.get("effects"):
            return True
    return False


def _notable_ingredients(ingredients: set[str], knowledge: Optional[Dict[str, Any]]) -> set[str]:
    return {name for name in ingredients if _is_notable(name, knowledge)}


def _pretty(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return text
    return text[:1].upper() + text[1:]


def _load_candidates(product: Dict[str, Any], category: str, subcategory: str) -> List[Dict[str, Any]]:
    """Кандидаты той же категории каталога (с мягким fallback по таксономии)."""
    if not category or category == "Другое":
        return []
    select = (
        "SELECT id, name, slug, brand, image_url, volume, price, currency, ingredients, "
        "category, subcategory, catalog_category, catalog_subcategory, taxonomy_category "
        "FROM products WHERE is_canonical = 1 AND id <> ? "
        "AND ingredients IS NOT NULL AND trim(ingredients) <> ''"
    )
    rows: List[Dict[str, Any]] = []
    seen: set[int] = set()
    conn = get_connection(PRODUCTS_DB)
    try:
        for where, params in (
            (" AND catalog_category = ?", [category]),
            (" AND catalog_subcategory = ?", [subcategory] if subcategory else []),
            (" AND taxonomy_category = ?", [product.get("taxonomy_category") or ""]),
        ):
            if not params or not params[0]:
                continue
            try:
                fetched = conn.execute(
                    select + where + f" LIMIT {CANDIDATE_LIMIT}",
                    (int(product.get("id") or 0), *params),
                ).fetchall()
            except Exception as exc:  # noqa: BLE001 - один фильтр не должен ломать подбор
                logger.info("[ALTERNATIVES] candidate query failed (%s): %s", where, exc)
                continue
            for row in fetched:
                data = dict(row)
                pid = int(data.get("id") or 0)
                if pid and pid not in seen:
                    seen.add(pid)
                    rows.append(data)
            if len(rows) >= 40:
                break
    finally:
        conn.close()
    return rows


def _reasons(
    *,
    source: Dict[str, Any],
    candidate: Dict[str, Any],
    shared: set[str],
    shared_notable: set[str],
    jaccard: float,
    same_function: bool,
    category: str,
) -> List[str]:
    reasons: List[str] = []
    if category and category != "Другое":
        reasons.append(f"Та же категория каталога: {category.lower()}")
    if same_function:
        reasons.append("Совпадает назначение средства")
    if shared_notable:
        names = ", ".join(_pretty(item) for item in sorted(shared_notable)[:3])
        reasons.append(f"Общие ключевые компоненты: {names}")
    if jaccard >= 0.2:
        reasons.append(f"Похожий состав: {round(jaccard * 100)}% общих ингредиентов")
    if not reasons:
        reasons.append("Близкий по типу и назначению вариант")
    return reasons[:3]


def _differences(
    *,
    source: Dict[str, Any],
    candidate: Dict[str, Any],
    source_set: set[str],
    candidate_set: set[str],
    source_notable: set[str],
    candidate_notable: set[str],
    category: str,
) -> List[str]:
    differences: List[str] = []
    only_here = candidate_set - source_set
    only_source = source_set - candidate_set
    notable_here = sorted((candidate_notable - source_notable))[:3]
    notable_source = sorted((source_notable - candidate_notable))[:3]
    if notable_here:
        differences.append("Дополнительно содержит: " + ", ".join(_pretty(item) for item in notable_here))
    if notable_source:
        differences.append("Без компонентов исходного: " + ", ".join(_pretty(item) for item in notable_source))
    if not notable_here and not notable_source:
        if only_here:
            differences.append("Другие вспомогательные ингредиенты: " + ", ".join(_pretty(item) for item in sorted(only_here)[:3]))
        elif not only_source:
            differences.append("Состав практически совпадает")
    source_brand = (source.get("brand") or _split_name(source.get("name") or "")[0] or "").strip()
    candidate_brand = (candidate.get("brand") or _split_name(candidate.get("name") or "")[0] or "").strip()
    if source_brand and candidate_brand and source_brand.lower() != candidate_brand.lower():
        differences.append(f"Другой бренд: {candidate_brand}")
    return differences[:3]


def find_alternatives(
    user: Dict[str, Any],
    product_id: int,
    *,
    limit: int = MAX_ALTERNATIVES,
) -> Dict[str, Any]:
    """Возвращает наиболее похожие средства той же категории (без исходного)."""
    from .catalog_taxonomy import classify_product
    from .shelf_service import _build_user_profile, _deterministic_analysis

    product = get_product_by_id(int(product_id))
    if not product:
        return {"source": None, "items": [], "reason": "product_not_found"}

    classification = {}
    try:
        classification = classify_product(product) or {}
    except Exception as exc:  # noqa: BLE001 - классификация не должна ломать подбор
        logger.info("[ALTERNATIVES] classify failed: %s", exc)

    category = str(classification.get("canonical_category") or product.get("catalog_category") or "")
    subcategory = str(classification.get("catalog_subcategory") or product.get("catalog_subcategory") or "")
    function_key = str(classification.get("function_key") or "")

    source_brand, source_name = _split_name(product.get("name") or "")
    source_name = _clean_name(source_name or product.get("name") or "")
    source_brand = (product.get("brand") or source_brand or "").strip()
    source_set = _ingredient_set(product.get("ingredients") or "")

    knowledge = None
    try:
        from .ingredient_repository import IngredientRepository

        knowledge = IngredientRepository().get_canonical_knowledge_map()
    except Exception as exc:  # noqa: BLE001
        logger.info("[ALTERNATIVES] knowledge map unavailable: %s", exc)

    profile = _build_user_profile(user)
    source_notable = _notable_ingredients(source_set, knowledge)

    scored: List[Dict[str, Any]] = []
    seen_names: set[str] = {(source_name or "").lower()}
    for candidate in _load_candidates(product, category, subcategory):
        candidate_name = _clean_name(_split_name(candidate.get("name") or "")[1] or candidate.get("name") or "")
        if not candidate_name or candidate_name.lower() in seen_names:
            continue
        candidate_set = _ingredient_set(candidate.get("ingredients") or "")
        if len(candidate_set) < 2 or not source_set:
            continue
        shared = source_set & candidate_set
        union = source_set | candidate_set
        jaccard = len(shared) / len(union) if union else 0.0
        shared_notable = shared & source_notable
        candidate_notable = _notable_ingredients(candidate_set, knowledge)
        notable_ratio = len(shared_notable) / max(1, len(source_notable)) if source_notable else 0.0

        analysis = _deterministic_analysis(
            profile, candidate.get("ingredients") or "", knowledge=knowledge
        )
        compatibility: Dict[str, Any] = {"score": None, "verdict": None, "status": None}
        if isinstance(analysis, dict):
            compatibility = {
                "score": analysis.get("score"),
                "verdict": analysis.get("verdict"),
                "status": analysis.get("phase1_status"),
                "recommendation_status": analysis.get("recommendation_status"),
            }
        if str(compatibility.get("recommendation_status") or "").lower().startswith("не рекоменд"):
            # Средство заведомо не подходит профилю (аллергии/непереносимости).
            continue

        candidate_function = ""
        try:
            candidate_function = str((classify_product(candidate) or {}).get("function_key") or "")
        except Exception:  # noqa: BLE001
            candidate_function = ""
        same_function = bool(function_key and candidate_function == function_key)

        compat_score = compatibility.get("score")
        compat_norm = (float(compat_score) / 100.0) if isinstance(compat_score, (int, float)) else 0.5
        similarity = (
            0.5 * jaccard
            + 0.3 * notable_ratio
            + 0.2 * compat_norm
            + (0.05 if same_function else 0.0)
        )
        if similarity < MIN_SIMILARITY:
            continue

        candidate_brand = (candidate.get("brand") or _split_name(candidate.get("name") or "")[0] or "").strip()
        scored.append(
            {
                "id": int(candidate.get("id") or 0),
                "slug": candidate.get("slug") or "",
                "brand": candidate_brand,
                "name": candidate_name,
                "image_url": candidate.get("image_url") or "",
                "volume": candidate.get("volume") or "",
                "category": candidate.get("category") or "",
                "catalog_category": candidate.get("catalog_category") or category,
                "similarity": round(min(1.0, similarity), 3),
                "reasons": _reasons(
                    source=product,
                    candidate=candidate,
                    shared=shared,
                    shared_notable=shared_notable,
                    jaccard=jaccard,
                    same_function=same_function,
                    category=category,
                ),
                "differences": _differences(
                    source=product,
                    candidate=candidate,
                    source_set=source_set,
                    candidate_set=candidate_set,
                    source_notable=source_notable,
                    candidate_notable=candidate_notable,
                    category=category,
                ),
                "compatibility": compatibility,
            }
        )
        seen_names.add(candidate_name.lower())

    scored.sort(key=lambda item: (-item["similarity"], -(item["compatibility"].get("score") or 0)))
    items = scored[: max(1, int(limit))]
    return {
        "source": {
            "id": int(product.get("id") or 0),
            "slug": product.get("slug") or "",
            "brand": source_brand,
            "name": source_name,
            "image_url": product.get("image_url") or "",
            "volume": product.get("volume") or "",
            "catalog_category": category,
        },
        "items": items,
        "reason": "ok" if items else "no_alternatives",
    }
