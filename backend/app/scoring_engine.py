from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .ingredient_normalizer import normalize_ingredient_name


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def calculate_position_weight(position: int, total: int) -> float:
    if total <= 1:
        return 1.0
    normalized = position / max(total, 1)
    return clamp(1.2 - normalized * 0.7)


def _ingredient_matches(item: str, ingredients: List[str]) -> bool:
    """Проверяет, входит ли ограничение item в состав (по нормализованному имени).

    Точное вхождение или подстрока — чтобы «niacinamide» ловил «Niacinamide 10%».
    """
    key = normalize_ingredient_name(item)
    if not key:
        return False
    for ingredient in ingredients:
        ni = normalize_ingredient_name(ingredient)
        if not ni:
            continue
        if key == ni or key in ni or ni in key:
            return True
    return False


def apply_hard_filters(user_profile: Dict[str, Any], ingredients: List[str]) -> List[Dict[str, Any]]:
    """Жёсткие фильтры: выполняются ДО расчёта обычного процента.

    Проверяет:
      - restrictions — жёсткие исключения (товар исключается);
      - allergies — заявленные аллергии (товар исключается).

    Возвращает список нарушений. Пустой список = товар проходит hard filters.
    """
    violations: List[Dict[str, Any]] = []
    valid = [i for i in ingredients if i and str(i).strip()]

    for item in user_profile.get('restrictions') or []:
        if _ingredient_matches(item, valid):
            violations.append({
                'type': 'restriction',
                'ingredient': item,
                'severity': 'exclude',
                'message': f'Ingredient {item} is a hard exclusion for this user.',
            })

    for item in user_profile.get('allergies') or []:
        if _ingredient_matches(item, valid):
            violations.append({
                'type': 'allergy',
                'ingredient': item,
                'severity': 'exclude',
                'message': f'Ingredient {item} matches a reported allergy.',
            })

    return violations


def _canonical_direction_sign(axis: str, direction: str) -> float:
    """±1: benefit-oriented знак для canonical direction (endpoint-oriented).

    benefit-ось (hydration/barrier): positive = хорошо → +1.
    harm-ось (irritation/sensitization/sebum/pigmentation): positive = плохо → -1.
    """
    from .axes import AXIS_HARM

    d = str(direction or "").strip().lower()
    if d in ("positive", "+", "increase", "increases"):
        positive = True
    elif d in ("negative", "-", "decrease", "decreases"):
        positive = False
    else:
        return 0.0
    harm = axis in AXIS_HARM
    return -1.0 if (positive == harm) else 1.0


def _legacyize_factor(factor: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility: canonical factor.property → legacy dimension name."""
    from .axes import CANONICAL_TO_LEGACY_DIMENSION

    legacy = CANONICAL_TO_LEGACY_DIMENSION.get(factor.get('property'))
    if legacy:
        factor = dict(factor)
        factor['property'] = legacy
    return factor


def score_product_against_profile_canonical(
    ingredients: List[str],
    canonical_knowledge: Dict[str, Dict[str, Dict[str, Any]]],
    user_profile: Dict[str, Any],
    canonical_weights: Dict[str, float],
    interactions: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Канонический Scoring Vector на 6 осях (axes.AXES), benefit-oriented.

    Individual Effects и Interaction Effects попадают НАПРЯМУЮ в canonical dimensions
    (без canonical→legacy→canonical). Возвращает canonical result (dimensions на 6 осях,
    factors с property=canonical axis, direction=benefit-oriented).
    """
    from .axes import AXES

    valid_ingredients = [ingredient for ingredient in ingredients if ingredient and str(ingredient).strip()]
    empty_dims = {axis: 0.0 for axis in AXES}
    if not valid_ingredients:
        return {
            'score': 0,
            'dimensions': empty_dims,
            'positive_factors': [],
            'negative_factors': [],
            'unknown_factors': [],
            'confidence': 0.0,
            'hard_flags': [],
            'interaction_breakdown': [],
            'interaction_scoring_version': _interaction_scoring_version(),
        }

    dimensions = {axis: 0.0 for axis in AXES}
    positive_factors: List[Dict[str, Any]] = []
    negative_factors: List[Dict[str, Any]] = []
    unknown_factors: List[Dict[str, Any]] = []
    hard_flags: List[Dict[str, Any]] = []

    allergies = {str(item).strip().lower() for item in user_profile.get('allergies', [])}

    for index, ingredient in enumerate(valid_ingredients, start=1):
        ingredient_key = str(ingredient).strip().lower()
        if ingredient_key in allergies:
            hard_flags.append({
                'type': 'allergy',
                'ingredient': ingredient,
                'severity': 'high',
                'message': f'Ingredient {ingredient} matches a reported allergy.',
            })

        ingredient_claims = canonical_knowledge.get(ingredient_key, {})
        if not ingredient_claims:
            unknown_factors.append({'ingredient': ingredient, 'position': index, 'reason': 'unknown_ingredient'})
            continue

        position_weight = calculate_position_weight(index, len(valid_ingredients))
        for axis, claim in ingredient_claims.items():
            axis_direction = str(claim.get('direction', 'neutral')).lower()
            strength = float(claim.get('strength', 0.0) or 0.0)
            confidence = float(claim.get('confidence', 0.0) or 0.0)
            sign = _canonical_direction_sign(axis, axis_direction)
            if sign == 0.0:
                continue
            weighted_value = sign * strength * confidence * position_weight
            dimensions[axis] += weighted_value
            factor = {
                'ingredient': ingredient,
                'property': axis,
                'direction': 'positive' if sign > 0 else 'negative',
                'strength': strength,
                'confidence': confidence,
                'position_weight': round(position_weight, 3),
            }
            if sign > 0:
                positive_factors.append(factor)
            else:
                negative_factors.append(factor)

    for item in user_profile.get('intolerances') or []:
        key = normalize_ingredient_name(item)
        if not key:
            continue
        matched = False
        for ingredient in valid_ingredients:
            ni = normalize_ingredient_name(ingredient)
            if ni and (key == ni or key in ni or ni in key):
                matched = True
                break
        if matched:
            negative_factors.append({
                'ingredient': item,
                'property': 'irritation',
                'direction': 'negative',
                'strength': 0.7,
                'confidence': 0.7,
                'position_weight': 1.0,
            })
            dimensions['irritation'] -= 0.7

    interaction_breakdown: List[Dict[str, Any]] = []
    if interactions:
        from . import interaction_scoring
        if interaction_scoring.INTERACTION_SCORING_ENABLED:
            agg, interaction_breakdown = interaction_scoring.aggregate_interactions(interactions)
            for axis, contrib in agg.items():
                dimensions[axis] += contrib

    weighted_total = 0.0
    for axis, weight in canonical_weights.items():
        contribution = max(0.0, min(dimensions.get(axis, 0.0), 1.0))
        weighted_total += contribution * float(weight)

    safe_score = clamp(weighted_total / max(sum(canonical_weights.values()), 1e-9), 0.0, 1.0)
    final_score = int(round(safe_score * 100))

    if unknown_factors and not positive_factors and not negative_factors and not hard_flags:
        final_score = max(final_score, 40)
    if hard_flags:
        final_score = min(final_score, 35)

    return {
        'score': int(final_score),
        'dimensions': {axis: round(value, 3) for axis, value in dimensions.items()},
        'positive_factors': positive_factors,
        'negative_factors': negative_factors,
        'unknown_factors': unknown_factors,
        'confidence': round(clamp((sum(1 for _ in positive_factors) + sum(1 for _ in negative_factors)) / max(len(valid_ingredients), 1), 0.0, 1.0), 3),
        'hard_flags': hard_flags,
        'interaction_breakdown': interaction_breakdown,
        'interaction_scoring_version': _interaction_scoring_version(),
    }


def score_product_against_profile(
    ingredients: List[str],
    knowledge: Dict[str, Dict[str, Dict[str, float]]],
    user_profile: Dict[str, Any],
    priority_weights: Dict[str, float],
    interaction_knowledge: Dict[str, Dict[str, Any]] | None = None,
    interactions: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """LEGACY compatibility wrapper: legacy → canonical → scoring → legacy.

    Канонический scoring выполняется в score_product_against_profile_canonical;
    legacy-вход канонизируется НА ГРАНИЦЕ, legacy-выход восстанавливается на границе.
    При interaction disabled результат бит-в-бит совпадает с прежним legacy scoring.
    """
    from .axes import canonicalize_knowledge_map, canonicalize_weights, legacyize_dimensions

    canonical_knowledge = canonicalize_knowledge_map(knowledge)
    canonical_weights = canonicalize_weights(priority_weights)
    result = score_product_against_profile_canonical(
        ingredients, canonical_knowledge, user_profile, canonical_weights, interactions=interactions
    )
    result['dimensions'] = legacyize_dimensions(result['dimensions'])
    result['positive_factors'] = [_legacyize_factor(f) for f in result['positive_factors']]
    result['negative_factors'] = [_legacyize_factor(f) for f in result['negative_factors']]

    if interaction_knowledge:
        for key, interaction in interaction_knowledge.items():
            if interaction.get('direction') == 'negative':
                result['negative_factors'].append({
                    'ingredient': key,
                    'property': interaction.get('property', 'interaction'),
                    'direction': 'negative',
                    'strength': interaction.get('strength', 0.5),
                    'confidence': interaction.get('confidence', 0.5),
                    'position_weight': 1.0,
                })
    return result


def _interaction_scoring_version() -> str:
    """Текущая версия правил interaction contribution (часть идентичности score)."""
    from . import interaction_scoring
    return interaction_scoring.INTERACTION_SCORING_VERSION
