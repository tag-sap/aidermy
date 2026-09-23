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


def get_current_versions() -> Dict[str, str]:
    """Единый источник текущих версий (инвалидация Static Product Model)."""
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "interaction_version": INTERACTION_VERSION,
        "model_version": MODEL_VERSION,
    }


def build_product_context(ingredient_names: List[str], graph=None) -> Dict[str, Any]:
    """Контекст продукта: классы резолвятся ОДИН раз на ингредиент (O(n), не O(n²)).

    Возвращает: ingredient_to_classes, class_to_ingredients, classes,
    relevant_internal_pairs (только пары из релевантных классовых маршрутов).
    """
    from .ingredient_graph import GRAPH

    g = graph or GRAPH
    ingredient_to_classes = {ing: list(g.lookup_classes(ing)) for ing in ingredient_names}
    class_to_ingredients: Dict[str, List[str]] = {}
    for ing, classes in ingredient_to_classes.items():
        for c in classes:
            class_to_ingredients.setdefault(c, []).append(ing)

    routes = g._repo.get_class_routes()
    relevant_pairs: List[tuple] = []
    seen = set()
    for route_a, route_b in routes:
        for ca in route_a:
            for cb in route_b:
                for a in class_to_ingredients.get(ca, []):
                    for b in class_to_ingredients.get(cb, []):
                        if a == b:
                            continue
                        p = tuple(sorted([a, b]))
                        if p not in seen:
                            seen.add(p)
                            relevant_pairs.append(p)

    return {
        "ingredient_names": ingredient_names,
        "ingredient_to_classes": ingredient_to_classes,
        "class_to_ingredients": class_to_ingredients,
        "classes": list(class_to_ingredients.keys()),
        "relevant_internal_pairs": relevant_pairs,
    }


# ProductContext — промежуточный ВЫЧИСЛИТЕЛЬНЫЙ кэш контекста продукта (Фаза 6).
# НЕ является системой знаний: чистая функция от состава + версий. Инвалидируется
# сменой composition_hash или любой версии (taxonomy/knowledge/interaction/model).
_context_cache: Dict[str, Dict[str, Any]] = {}
_context_cache_lock = threading.Lock()


def get_or_build_product_context(ingredient_names: List[str], graph=None) -> Dict[str, Any]:
    """Cache-first ProductContext: классы резолвятся один раз на ингредиент и переиспользуются."""
    versions = get_current_versions()
    key = composition_hash(",".join(ingredient_names)) + "|" + "|".join(versions.values())
    with _context_cache_lock:
        cached = _context_cache.get(key)
        if cached:
            METRICS.increment("product_context_cache_hit")
            return cached
    METRICS.increment("product_context_cache_miss")
    ctx = build_product_context(ingredient_names, graph=graph)
    with _context_cache_lock:
        _context_cache[key] = ctx
    return ctx


def build_static_product_model(product: Dict[str, Any], graph=None) -> Dict[str, Any]:
    """Строит объективную модель продукта из глобального knowledge graph."""
    from .ingredient_graph import GRAPH

    g = graph or GRAPH
    ingredient_names = _split_ingredients(product.get("ingredients") or "")
    context = get_or_build_product_context(ingredient_names, graph=g)

    effects: Dict[str, Dict[str, Any]] = {}
    for ing in ingredient_names:
        for axis, eff in g.lookup_effects(ing).items():
            if eff["state"] in ("known", "insufficient"):
                effects.setdefault(ing, {})[axis] = {
                    "direction": eff.get("direction"),
                    "strength": eff.get("strength"),
                    "confidence": eff.get("confidence"),
                    "state": eff["state"],
                }

    internal_ids = _detect_internal_interaction_ids(context, g)

    return {
        "product_id": product.get("id"),
        "composition_hash": composition_hash(product.get("ingredients") or ""),
        "ingredient_names": ingredient_names,
        "classes": context["classes"],
        "individual_effects": effects,
        "internal_interaction_ids": internal_ids,
        "taxonomy_version": TAXONOMY_VERSION,
        "knowledge_version": KNOWLEDGE_VERSION,
        "interaction_version": INTERACTION_VERSION,
        "model_version": MODEL_VERSION,
    }


def _detect_internal_interaction_ids(context: Dict[str, Any], g) -> List[int]:
    """Exact lookup только для relevant_internal_pairs (классовый routing).

    Классы уже резолвены в context (O(n) lookup'ов), здесь — только пары из
    релевантных маршрутов, без повторного class lookup.
    """
    ids: List[int] = []
    for a, b in context["relevant_internal_pairs"]:
        r = g.lookup_interaction(a, b)
        for rec in r.get("records", []):
            if rec.get("interaction_id") is not None and rec["interaction_id"] not in ids:
                ids.append(rec["interaction_id"])
    return ids


def get_internal_interactions(product: Dict[str, Any], graph=None) -> List[Dict[str, Any]]:
    """Подготовленные internal interaction-записи продукта (для Scoring Engine, Фаза 7).

    Использует кэшированный ProductContext (классы резолвены один раз) + cached
    interaction map. Возвращает плоские записи с ingredient_a/ingredient_b/type="internal"
    и полями lookup (axis/direction/strength/confidence/state). Без повторных class lookups.
    """
    from .ingredient_graph import GRAPH

    g = graph or GRAPH
    ingredient_names = _split_ingredients(product.get("ingredients") or "")
    context = get_or_build_product_context(ingredient_names, graph=g)
    records: List[Dict[str, Any]] = []
    for a, b in context["relevant_internal_pairs"]:
        r = g.lookup_interaction(a, b)
        for rec in r.get("records", []):
            rec = dict(rec)
            rec["ingredient_a"] = a
            rec["ingredient_b"] = b
            rec["type"] = "internal"
            records.append(rec)
    return records


# ---------------------------------------------------------------------------
# In-memory per-process кэш + DB persistence.
# ---------------------------------------------------------------------------
_cache: Dict[int, Dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _is_current(model: Dict[str, Any]) -> bool:
    versions = get_current_versions()
    return all(model.get(k) == v for k, v in versions.items())


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
    if product_id is not None:
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
    if product_id is not None:
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
