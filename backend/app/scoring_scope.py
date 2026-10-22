"""Deterministic applicability of skin-compatibility scoring by product category."""

from __future__ import annotations

from typing import Any, Dict

from .catalog_taxonomy import classify_product

_UNSCORED_BODY_AREAS = {"makeup", "fragrance"}
_UNSCORED_REASON = (
    "Для макияжа и парфюмерии процент совместимости с профилем кожи не рассчитывается: "
    "эти категории не предназначены для оценки по кожному INCI-скорингу."
)
# Для области вокруг глаз и губ себум/пигментация не являются основной целью
# оценки; релевантны увлажнение, барьер и риск раздражения/реакции.
_SPECIAL_RELEVANT_AXES = {
    "eyes": ("hydration", "barrier", "irritation", "sensitization"),
    "lips": ("hydration", "barrier", "irritation", "sensitization"),
}


def filter_weights_for_scope(weights: Dict[str, float], scope: Dict[str, Any]) -> Dict[str, float]:
    relevant = scope.get("relevant_axes") or ()
    if not relevant:
        return weights
    filtered = {axis: (value if axis in relevant else 0.0) for axis, value in weights.items()}
    total = sum(filtered.values())
    if total <= 0:
        return weights
    return {axis: value / total for axis, value in filtered.items()}


def resolve_scoring_scope(
    product: Dict[str, Any] | None = None,
    product_name: str = "",
    category: str = "",
) -> Dict[str, Any]:
    """Возвращает, применим ли skin-scoring к продукту.

    Это не штраф и не «декоративная» категория: для категорий, где кожный
    процент вводил бы пользователя в заблуждение, Score Engine не выдаёт score.
    """
    payload = dict(product or {})
    if product_name and not payload.get("name"):
        payload["name"] = product_name
    if category and not payload.get("category"):
        payload["category"] = category
    try:
        classified = classify_product(payload)
    except Exception:
        classified = {}
    body_area = str(classified.get("body_area") or "").lower()
    product_type = str(classified.get("product_type") or "").lower()
    applies = body_area not in _UNSCORED_BODY_AREAS
    relevant_axes = _SPECIAL_RELEVANT_AXES.get(product_type, ())
    return {
        "applies": applies,
        "body_area": body_area,
        "product_type": product_type,
        "relevant_axes": list(relevant_axes),
        "canonical_category": classified.get("canonical_category") or "",
        "reason": "" if applies else _UNSCORED_REASON,
    }
