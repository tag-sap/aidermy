# ppm.py — Pre Product Model (PPM): дешёвое частичное представление товара.
#
# PPM НЕ является scoring-моделью. Он нужен только для vector retrieval,
# понимания known/unknown ингредиентов и lazy enrichment. Пользователь его не видит.
#
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .ingredient_normalizer import normalize_ingredient_name
from .catalog_taxonomy import classify_product
from .product_model import KNOWLEDGE_VERSION, TAXONOMY_VERSION, composition_hash
from .product_vector import build_product_vector
from .scoring_config import SCORING_CONFIG_VERSION


def build_ppm(
    product: Dict[str, Any],
    normalized_ingredients: List[str],
    unknown_ingredients: List[str],
    canonical_knowledge: Dict[str, Any],
) -> Dict[str, Any]:
    """Строит PPM без LLM, из существующей knowledge map.

    Unknown ingredient НЕ получает отрицательный contribution: он просто не вносит
    вклад в vector (contribution = 0) и попадает в unknown_ingredients, снижая coverage.
    """
    raw = product.get("ingredients") or ""
    unknown_norm = sorted({
        normalize_ingredient_name(u) for u in unknown_ingredients if normalize_ingredient_name(u)
    })
    vector = build_product_vector(normalized_ingredients, canonical_knowledge)
    total = len(normalized_ingredients)
    known = max(0, total - len(unknown_norm))
    coverage = (known / total) if total else 0.0

    classification = classify_product(product)
    cabinet = classification["body_area"]
    category = classification["canonical_category"]

    return {
        "product_id": product.get("id"),
        "composition_hash": composition_hash(raw),
        "vector": vector,
        "coverage": coverage,
        "known_count": known,
        "unknown_count": len(unknown_norm),
        "unknown_ingredients": unknown_norm,
        "cabinet": cabinet,
        "category": category,
        "body_area": classification["body_area"],
        "body_area_title": classification["body_area_title"],
        "product_type": classification["product_type"],
        "primary_function": classification["primary_function"],
        "secondary_functions": classification["secondary_functions"],
        "canonical_category": classification["canonical_category"],
        "category_confidence": classification["category_confidence"],
        "category_source": classification["category_source"],
        "knowledge_version": KNOWLEDGE_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
    }


def _cabinet_category(product: Dict[str, Any]) -> Tuple[str, str]:
    try:
        c = classify_product(product)
        return c["body_area"], c["canonical_category"]
    except Exception:
        return "", (product.get("category") or "")
