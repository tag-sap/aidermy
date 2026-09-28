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


def retrieve_candidates(
    profile: Dict[str, Any],
    cabinet: str,
    category: str,
    exclude_slugs: set,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Возвращает TOP K кандидатов (PM + PPM) по Clamped Dot, после hard filters.

    Возвращает обычные product-dict'ы (как _query_candidates) — БЕЗ внутренних
    полей (vector / retrieval score / coverage / PPM). Они не должны попасть в API.
    """
    from .decision_engine import profile_weights
    from .database import get_all_canonical_products
    from .shelf_service import _hard_filter_exclusion, is_product_compatible

    # Тот же источник весов, что и у deterministic scoring (profile_weights),
    # чтобы retrieval находил именно то, что scoring оценит высоко. Для legacy
    # RU-профилей profile_weights делает legacy→structured mapping (не равномерные).
    weights = profile_weights(profile)

    if not VECTOR_INDEX.is_loaded():
        load_vector_index()

    products = get_all_canonical_products()
    products_map = {p["id"]: p for p in products}

    def predicate(pid: int) -> bool:
        p = products_map.get(pid)
        if not p:
            return False
        if (p.get("slug") or "") in exclude_slugs:
            return False
        ok, _reason = is_product_compatible(p, cabinet, category)
        if not ok:
            return False
        if _hard_filter_exclusion(profile, p.get("ingredients") or ""):
            return False
        return True

    k = top_k or VECTOR_TOP_K
    hits = VECTOR_INDEX.search(weights, k, predicate)
    return [dict(products_map[pid]) for pid, _score in hits]
