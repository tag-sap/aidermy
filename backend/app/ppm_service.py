# ppm_service.py — сервис построения/обновления PPM и единого Product Vector.
#
# Единственный источник построения Product Vector: для каждого canonical продукта
# хранится РОВНО одна representation (PM, если есть актуальный PM, иначе PPM).
#
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .ingredient_normalizer import canonicalize_ingredient_name, normalize_ingredient_name


def _prepare(raw: Any) -> List[str]:
    """Зеркалит AnalysisService.prepare_product_ingredients без открытия соединения."""
    if isinstance(raw, str):
        cleaned = raw.split(",") if "," in raw else raw.split("\n")
        items = [canonicalize_ingredient_name(item) for item in cleaned]
    else:
        items = [canonicalize_ingredient_name(item) for item in (raw or [])]
    return [i for i in items if i]


def build_or_refresh_ppm(
    product: Dict[str, Any],
    repo=None,
    canonical_knowledge: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Строит/обновляет PPM + product_vector для одного продукта (без LLM).

    - есть актуальный PM -> vector с representation_type='PM' (PPM не сохраняется);
    - иначе -> PPM (product_ppms + product_vectors с representation_type='PPM').

    force=True — пересчитать, игнорируя актуальность PPM (для targeted invalidation).
    """
    from .ingredient_enrichment import find_unknown_ingredients
    from .ingredient_repository import IngredientRepository
    from .ppm import build_ppm
    from .product_model import composition_hash

    repo = repo or IngredientRepository()
    knowledge = (
        canonical_knowledge if canonical_knowledge is not None else repo.get_canonical_knowledge_map()
    )

    raw = product.get("ingredients") or ""
    normalized = _prepare(raw)
    if not normalized:
        return {"skipped": True, "representation_type": None, "reason": "no_ingredients"}

    h = composition_hash(raw)

    if repo.has_current_product_model(product["id"], h):
        unknown_raw = find_unknown_ingredients(normalized, repo)
        ppm = build_ppm(product, normalized, unknown_raw, knowledge)
        repo.save_product_vector(
            product["id"], "PM", ppm["vector"], h, ppm["coverage"], ppm["unknown_count"]
        )
        return {"skipped": False, "representation_type": "PM", "reason": ""}

    if not force and repo.has_current_ppm(product["id"], h):
        return {"skipped": True, "representation_type": "PPM", "reason": "current_ppm"}

    unknown_raw = find_unknown_ingredients(normalized, repo)
    ppm = build_ppm(product, normalized, unknown_raw, knowledge)
    repo.save_ppm(ppm)
    repo.save_product_vector(
        product["id"], "PPM", ppm["vector"], h, ppm["coverage"], ppm["unknown_count"]
    )
    return {"skipped": False, "representation_type": "PPM", "reason": ""}


def build_all_ppms(
    products: Optional[List[Dict[str, Any]]] = None,
    progress_cb: Optional[Callable[[int, int, Dict[str, int]], None]] = None,
) -> Dict[str, int]:
    """Batch-построение PPM/vector для каталога. Без LLM, idempotent."""
    from .database import get_all_canonical_products
    from .ingredient_repository import IngredientRepository
    from .vector_index import load_vector_index

    repo = IngredientRepository()
    knowledge = repo.get_canonical_knowledge_map()
    products = products if products is not None else get_all_canonical_products()

    stats = {
        "total": 0, "pm": 0, "ppm": 0,
        "skipped_current": 0, "skipped_no_ingredients": 0, "failed": 0,
    }
    for i, p in enumerate(products):
        stats["total"] += 1
        try:
            r = build_or_refresh_ppm(p, repo=repo, canonical_knowledge=knowledge)
            if r["skipped"]:
                if r["reason"] == "no_ingredients":
                    stats["skipped_no_ingredients"] += 1
                else:
                    stats["skipped_current"] += 1
            elif r["representation_type"] == "PM":
                stats["pm"] += 1
            else:
                stats["ppm"] += 1
        except Exception:
            stats["failed"] += 1
        if progress_cb and (i + 1) % 100 == 0:
            progress_cb(i + 1, len(products), stats)

    load_vector_index(repo)
    return stats


def refresh_ppms_for_ingredients(ingredients: List[str], repo=None) -> int:
    """Targeted invalidation после enrichment: force rebuild затронутых PPM + reload index."""
    from .database import get_product_by_id
    from .ingredient_repository import IngredientRepository
    from .vector_index import load_vector_index

    repo = repo or IngredientRepository()
    knowledge = repo.get_canonical_knowledge_map()
    refreshed = 0

    for ing in (ingredients or []):
        key = normalize_ingredient_name(ing)
        if not key:
            continue
        for pid in repo.get_ppms_by_unknown_ingredient(key):
            p = get_product_by_id(pid)
            if not p:
                continue
            try:
                r = build_or_refresh_ppm(p, repo=repo, canonical_knowledge=knowledge, force=True)
                if not r["skipped"]:
                    refreshed += 1
            except Exception:
                continue

    load_vector_index(repo)
    return refreshed
