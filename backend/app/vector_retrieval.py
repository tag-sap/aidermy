# vector_retrieval.py — retrieval service (candidate discovery layer).
#
# Profile -> resolve_personal_profile -> hard filters -> Clamped Dot -> TOP K.
# НИКОГДА не заменяет deterministic scoring: возвращает только candidate pool.
#
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .vector_index import VECTOR_INDEX, load_vector_index

# Feature flag: позволяет мгновенно вернуться к старому candidate discovery.
VECTOR_RETRIEVAL_ENABLED = os.getenv("VECTOR_RETRIEVAL_ENABLED", "0") == "1"
VECTOR_TOP_K = int(os.getenv("VECTOR_TOP_K", "20"))

# Минимум продуктов курируемой категории витрины, при котором имеет смысл
# сужать candidate pool. Если их меньше — оставляем внутреннюю категорию.
CATALOG_POOL_MIN = 3


def _catalog_slugs(catalog_category: str) -> set:
    """Slug'и продуктов с точной курируемой категорией витрины (Postgres).

    Внутренняя таксономия (classify_product) шире витринной: например,
    «Увлажнение» и «Восстановление кожного барьера» попадают в «Увлажнение и
    питание»/«Кремы», из-за чего солнцезащита и обычные кремы смешивались с
    увлажнением. Витринная категория в public.products.catalog_category —
    точный источник для ограничения candidate pool.
    """
    from .postgres_connection import get_postgres_connection

    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT slug FROM products "
                "WHERE catalog_category = %s AND is_canonical = 1 AND slug IS NOT NULL",
                (catalog_category,),
            )
            slugs = {row["slug"] for row in cur.fetchall() if row.get("slug")}
        conn.rollback()
    return slugs


def retrieve_candidates(
    profile: Dict[str, Any],
    cabinet: str,
    category: str,
    exclude_slugs: set,
    top_k: Optional[int] = None,
    catalog_category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Возвращает TOP K кандидатов (PM + PPM) по Clamped Dot, после hard filters.

    Возвращает обычные product-dict'ы (как _query_candidates) — БЕЗ внутренних
    полей (vector / retrieval score / coverage / PPM). Они не должны попасть в API.
    """
    from .decision_engine import profile_weights
    from .database import get_all_canonical_products
    from .shelf_service import _hard_filter_exclusion, _is_other_category
    from .catalog_taxonomy import classify_product, canonical_subcategory

    # Тот же источник весов, что и у deterministic scoring (profile_weights),
    # чтобы retrieval находил именно то, что scoring оценит высоко. Для legacy
    # RU-профилей profile_weights делает legacy→structured mapping (не равномерные).
    weights = profile_weights(profile)

    if not VECTOR_INDEX.is_loaded():
        load_vector_index()

    products = get_all_canonical_products()

    # Category hard filter ДО retrieval: candidate pool ограничивается выбранной
    # категорией (canonical_category == category) и шкафом. Vector retrieval затем
    # ранжирует ТОЛЬКО эти продукты — другие категории и «Другое» в Top-K не попадают.
    norm_category = canonical_subcategory(cabinet, category)
    products_map: Dict[int, Dict[str, Any]] = {}
    allowed_ids: List[int] = []
    for p in products:
        c = classify_product(p)
        if c["canonical_category"] != norm_category:
            continue
        if c["body_area"] and c["body_area"] != cabinet:
            continue
        products_map[p["id"]] = p
        allowed_ids.append(p["id"])

    # Курируемая категория витрины сужает пул ДО vector ranking: релевантные
    # продукты должны попадать в TOP K, а не просто существовать в индексе.
    # Возврат к внутренней категории — если курируемых продуктов слишком мало
    # (или витринная категория не задана). Скоринг и ранжирование не меняются.
    if catalog_category:
        try:
            wanted = _catalog_slugs(catalog_category)
            if wanted:
                narrowed = [
                    pid for pid in allowed_ids
                    if (products_map.get(pid) or {}).get("slug") in wanted
                ]
                if len(narrowed) >= CATALOG_POOL_MIN:
                    allowed_ids = narrowed
        except Exception as exc:  # витрина недоступна — работаем как раньше
            print(f"[RETRIEVAL] catalog_category filter failed: {exc!r}")

    def predicate(pid: int) -> bool:
        p = products_map.get(pid)
        if not p:
            return False
        if (p.get("slug") or "") in exclude_slugs:
            return False
        if _hard_filter_exclusion(profile, p.get("ingredients") or ""):
            return False
        if _is_other_category(p):
            return False
        return True

    k = top_k or VECTOR_TOP_K
    hits = VECTOR_INDEX.search(weights, k, predicate, allowed_ids=allowed_ids)
    return [dict(products_map[pid]) for pid, _score in hits]
