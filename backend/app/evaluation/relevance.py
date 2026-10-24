"""Deterministic relevance of a user goal to a product category.

This module does not judge efficacy. It only answers a narrower question:

    "Is this goal the product's direct purpose, a supportive part of care,
     or outside what this product is designed to do?"

Keeping that decision deterministic prevents an LLM from turning "this
cleanser has no brightening actives" into a user-facing warning. A confirmed
contradiction/risk is handled separately by the evidence layer and is never
suppressed here.
"""
from __future__ import annotations

from typing import Mapping

from ..catalog_taxonomy import classify_product

GOAL_SCOPE_DIRECT = "direct"
GOAL_SCOPE_SUPPORTIVE = "supportive"
GOAL_SCOPE_NOT_INTENDED = "not_intended"
GOAL_SCOPE_UNKNOWN = "unknown"

# Direct = the category is designed to deliver this goal as a primary effect.
# Supportive = the product may help the routine, but is not a standalone
# treatment for the goal. Anything else is not_intended.
_GOAL_RELEVANCE: dict[str, tuple[set[str], set[str]]] = {
    "acne": (
        {"face:acne", "face:special", "face:serums"},
        {
            "face:cleansing", "face:toning", "face:pads", "face:masks",
            "face:creams", "face:moisturizing",
        },
    ),
    "brightening": (
        {"face:brightening", "face:serums", "face:special", "face:pads"},
        {"face:toning", "face:creams", "face:masks", "face:antiage"},
    ),
    "hydration": (
        {
            "face:creams",
            "face:moisturizing",
            "face:serums",
            "face:toning",
            "face:lips",
            "face:eyes",
            "face:hydration",
            "body:basic",
        },
        {"face:cleansing", "face:masks", "face:pads", "body:shower"},
    ),
    "calm": (
        {
            "face:serums",
            "face:toning",
            "face:creams",
            "face:masks",
            "face:patches",
            "face:eyes",
        },
        {"face:cleansing", "face:pads"},
    ),
    "barrier": (
        {
            "face:barrier",
            "face:creams",
            "face:moisturizing",
            "face:serums",
            "face:lips",
            "body:basic",
        },
        {"face:toning", "face:cleansing"},
    ),
    "sebum": (
        {"face:cleansing", "face:pads", "face:special", "face:serums"},
        {"face:masks", "face:creams"},
    ),
    "anti_age": (
        {"face:antiage", "face:serums", "face:creams"},
        {"face:masks", "face:eyes", "face:special"},
    ),
}


def product_category_key(product: Mapping | None) -> str:
    """Return the catalog purpose key (e.g. ``face:acne``).

    ``function_key`` is preferred over the broad form key so an anti-acne serum
    is not reduced to the generic ``face:serums`` category.
    """
    classification = classify_product(dict(product or {}))
    function_key = str(classification.get("function_key") or "").strip()
    if function_key:
        return function_key
    body_area = str(classification.get("body_area") or "").strip()
    product_type = str(classification.get("product_type") or "").strip()
    if body_area and product_type:
        return f"{body_area}:{product_type}"
    return ""


def product_category_label(product: Mapping | None) -> str:
    classification = classify_product(dict(product or {}))
    return str(classification.get("canonical_category") or "").strip()


def goal_scope(parameter_id: str, product: Mapping | None) -> str:
    """Classify a ``goal:<option>`` parameter, never an efficacy judgement."""
    if not str(parameter_id or "").startswith("goal:"):
        return ""
    goal = str(parameter_id).split(":", 1)[1].strip()
    rules = _GOAL_RELEVANCE.get(goal)
    if rules is None:
        return GOAL_SCOPE_UNKNOWN
    key = product_category_key(product)
    if not key:
        return GOAL_SCOPE_UNKNOWN
    direct, supportive = rules
    if key in direct:
        return GOAL_SCOPE_DIRECT
    if key in supportive:
        return GOAL_SCOPE_SUPPORTIVE
    return GOAL_SCOPE_NOT_INTENDED


def goal_scope_note(scope: str, product: Mapping | None = None) -> str:
    """A short, user-facing explanation of the product's role for the goal."""
    if scope == GOAL_SCOPE_NOT_INTENDED:
        category = product_category_label(product)
        category_text = f" «{category}»" if category else ""
        return (
            f"Категория{category_text} не предназначена для самостоятельного "
            "достижения этой цели; отсутствие профильных активов не является риском."
        )
    if scope == GOAL_SCOPE_SUPPORTIVE:
        return (
            "Продукт может поддерживать уход в рамках этой цели, но не заменяет "
            "средство, предназначенное для её самостоятельного достижения."
        )
    return ""
