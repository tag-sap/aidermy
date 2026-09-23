# product_model.py
# Фаза 5 — Static Product Model: кэшируемое ОБЪЕКТИВНОЕ представление продукта.
#
# НЕ содержит user profile / personalized score / shelf compatibility / hard constraints.
# Кэш-first: composition_hash + версии решают актуальность (не product_id сам по себе).
# Источник истины — глобальные таблицы; модель хранит ССЫЛКИ на interaction ids.

from __future__ import annotations

import hashlib
import re
import threading
from typing import Any, Dict, List

from .ingredient_normalizer import normalize_ingredient_name
from .instrumentation import METRICS

TAXONOMY_VERSION = "v1"
KNOWLEDGE_VERSION = "v1"
INTERACTION_VERSION = "seed-v1"
MODEL_VERSION = "v1"


def composition_hash(ingredients: str) -> str:
    parts = sorted({
        normalize_ingredient_name(p)
        for p in re.split(r"[,;\n]+", str(ingredients or ""))
        if normalize_ingredient_name(p)
    })
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _split_ingredients(raw: str) -> List[str]:
    out: List[str] = []
    for p in re.split(r"[,;\n]+", str(raw or "")):
        n = normalize_ingredient_name(p)
        if n and n not in out:
            out.append(n)
    return out


def build_static_product_model(product: Dict[str, Any], graph=None) -> Dict[str, Any]:
    """Строит объективную модель продукта из глобального knowledge graph."""
    from .ingredient_graph import GRAPH

    g = graph or GRAPH
    ingredient_names = _split_ingredients(product.get("ingredients") or "")

    classes: List[str] = []
    effects: Dict[str, Dict[str, Any]] = {}
    for ing in ingredient_names:
        for c in g.lookup_classes(ing):
            if c not in classes:
                classes.append(c)
        for axis, eff in g.lookup_effects(ing).items():
            if eff["state"] in ("known", "insufficient"):
                effects.setdefault(ing, {})[axis] = {
                    "direction": eff.get("direction"),
                    "strength": eff.get("strength"),
                    "confidence": eff.get("confidence"),
                    "state": eff["state"],
                }

    internal_ids = _detect_internal_interaction_ids(ingredient_names, g)

    return {
        "product_id": product.get("id"),
        "composition_hash": composition_hash(product.get("ingredients") or ""),
        "ingredient_names": ingredient_names,
        "classes": classes,
        "individual_effects": effects,
        "internal_interaction_ids": internal_ids,
        "taxonomy_version": TAXONOMY_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "interaction_version": INTERACTION_VERSION,
        "model_version": MODEL_VERSION,
    }


def _detect_internal_interaction_ids(ingredient_names: List[str], g) -> List[int]:
    routes = g._repo.get_class_routes()
    ids: List[int] = []
    for i in range(len(ingredient_names)):
        for j in range(i + 1, len(ingredient_names)):
            a, b = ingredient_names[i], ingredient_names[j]
            ca = set(g.lookup_classes(a))
            cb = set(g.lookup_classes(b))
            if not ca or not cb:
                continue
            if g._classes_relevant(ca, cb, routes):
                r = g.lookup_interaction(a, b)
                for rec in r.get("records", []):
                    if rec.get("interaction_id") is not None and rec["interaction_id"] not in ids:
                        ids.append(rec["interaction_id"])
    return ids


# ---------------------------------------------------------------------------
# In-memory per-process кэш + DB persistence.
# ---------------------------------------------------------------------------
_cache: Dict[int, Dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _is_current(model: Dict[str, Any]) -> bool:
    return (
        model.get("taxonomy_version") == TAXONOMY_VERSION
        and model.get("knowledge_version") == KNOWLEDGE_VERSION
        and model.get("interaction_version") == INTERACTION_VERSION
        and model.get("model_version") == MODEL_VERSION
    )


def get_or_build_product_model(product: Dict[str, Any], graph=None, repository=None) -> Dict[str, Any]:
    """Cache-first: актуальная модель → использовать; иначе построить и сохранить."""
    from .ingredient_graph import GRAPH
    from .ingredient_repository import IngredientRepository

    g = graph or GRAPH
    repo = repository or IngredientRepository()
    product_id = product.get("id")
    h = composition_hash(product.get("ingredients") or "")

    with _cache_lock:
        cached = _cache.get(product_id)
        if cached and cached.get("composition_hash") == h and _is_current(cached):
            METRICS.increment("product_model_cache_hit")
            return cached

    stored = None
    try:
        repo.ensure_product_model_tables()
        stored = repo.get_product_model(product_id)
    except Exception:
        stored = None
    if stored:
        data = stored.get("data") or {}
        if data.get("composition_hash") == h and _is_current(data):
            METRICS.increment("product_model_cache_hit")
            with _cache_lock:
                _cache[product_id] = data
            return data

    METRICS.increment("product_model_cache_miss")
    METRICS.increment("static_model_build_count")
    model = build_static_product_model(product, graph=g)
    try:
        repo.ensure_product_model_tables()
        repo.save_product_model(product_id, model)
    except Exception:
        pass
    with _cache_lock:
        _cache[product_id] = model
    return model


def invalidate_product_model(product_id: int) -> None:
    with _cache_lock:
        _cache.pop(product_id, None)
