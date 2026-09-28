# product_vector.py
# Единый 6-мерный Product Vector для retrieval (используется и PM, и PPM).
#
# Product Vector строится из СУЩЕСТВУЮЩЕЙ формулы scoring engine:
#   contribution(ingredient, axis) = sign × strength × confidence × position_weight
#   vector[axis] = Σ contributions
# Это ровно `dimensions` из score_product_against_profile_canonical (до clamp и до
# профильных весов). Новой формулы влияния ингредиентов здесь НЕТ — вызывается
# существующий deterministic scoring engine с нейтральным профилем.
#
from __future__ import annotations

from typing import Any, Dict, List

from .scoring_config import AXES


def build_product_vector(
    ingredients: List[str],
    canonical_knowledge: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, float]:
    """6-мерный benefit-oriented Product Vector (pre-clamp) из существующей формулы.

    `ingredients` — нормализованный список INCI-имён (см. AnalysisService.
    prepare_product_ingredients). `canonical_knowledge` — get_canonical_knowledge_map().
    Нейтральный профиль (без allergies/intolerances/restrictions) и равные веса
    гарантируют, что dimensions = чистый individual-effect вектор продукта.
    """
    from .scoring_engine import score_product_against_profile_canonical

    neutral = {"allergies": [], "intolerances": [], "restrictions": []}
    uniform = {axis: 1.0 / len(AXES) for axis in AXES}
    result = score_product_against_profile_canonical(
        ingredients=ingredients,
        canonical_knowledge=canonical_knowledge,
        user_profile=neutral,
        canonical_weights=uniform,
        interactions=None,
    )
    return {axis: float(result["dimensions"].get(axis, 0.0)) for axis in AXES}


def clamped_dot(vector: Dict[str, float], weights: Dict[str, float]) -> float:
    """Retrieval metric (НЕ пользовательский score):

        retrieval_score = Σ clamp(vector[axis], 0, 1) × weight[axis]

    Финальный compatibility score всегда считается отдельно deterministic Score Engine.
    """
    return sum(
        max(0.0, min(float(vector.get(k, 0.0) or 0.0), 1.0)) * float(weights.get(k, 0.0) or 0.0)
        for k in AXES
    )
