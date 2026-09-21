from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def calculate_position_weight(position: int, total: int) -> float:
    if total <= 1:
        return 1.0
    normalized = position / max(total, 1)
    return clamp(1.2 - normalized * 0.7)


def score_product_against_profile(
    ingredients: List[str],
    knowledge: Dict[str, Dict[str, Dict[str, float]]],
    user_profile: Dict[str, Any],
    priority_weights: Dict[str, float],
    interaction_knowledge: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    valid_ingredients = [ingredient for ingredient in ingredients if ingredient and str(ingredient).strip()]
    if not valid_ingredients:
        return {
            'score': 0,
            'dimensions': {key: 0.0 for key in priority_weights},
            'positive_factors': [],
            'negative_factors': [],
            'unknown_factors': [],
            'confidence': 0.0,
            'hard_flags': [],
        }

    dimensions = {key: 0.0 for key in priority_weights}
    positive_factors: List[Dict[str, Any]] = []
    negative_factors: List[Dict[str, Any]] = []
    unknown_factors: List[Dict[str, Any]] = []
    hard_flags: List[Dict[str, Any]] = []

    allergies = {str(item).strip().lower() for item in user_profile.get('allergies', [])}
    concerns = {str(item).strip().lower() for item in user_profile.get('concerns', [])}

    for index, ingredient in enumerate(valid_ingredients, start=1):
        ingredient_key = str(ingredient).strip().lower()

        # Непереносимость/аллергия — жёсткий сигнал, проверяется ДО знания базы:
        # ингредиент с аллергией должен флагироваться, даже если движок о нём ещё не знает.
        if ingredient_key in allergies:
            hard_flags.append({
                'type': 'allergy',
                'ingredient': ingredient,
                'severity': 'high',
                'message': f'Ingredient {ingredient} matches a reported allergy.',
            })

        ingredient_claims = knowledge.get(ingredient_key, {})
        if not ingredient_claims:
            unknown_factors.append({'ingredient': ingredient, 'position': index, 'reason': 'unknown_ingredient'})
            continue

        position_weight = calculate_position_weight(index, len(valid_ingredients))
        for property_name, claim in ingredient_claims.items():
            direction = str(claim.get('direction', 'neutral')).lower()
            strength = float(claim.get('strength', 0.0) or 0.0)
            confidence = float(claim.get('confidence', 0.0) or 0.0)
            if direction == 'neutral':
                continue

            weighted_value = strength * confidence * position_weight
            if direction == 'positive':
                dimensions[property_name] = dimensions.get(property_name, 0.0) + weighted_value
                positive_factors.append({
                    'ingredient': ingredient,
                    'property': property_name,
                    'direction': direction,
                    'strength': strength,
                    'confidence': confidence,
                    'position_weight': round(position_weight, 3),
                })
            elif direction == 'negative':
                dimensions[property_name] = dimensions.get(property_name, 0.0) - weighted_value
                negative_factors.append({
                    'ingredient': ingredient,
                    'property': property_name,
                    'direction': direction,
                    'strength': strength,
                    'confidence': confidence,
                    'position_weight': round(position_weight, 3),
                })

    if interaction_knowledge:
        for key, interaction in interaction_knowledge.items():
            if interaction.get('direction') == 'negative':
                negative_factors.append({
                    'ingredient': key,
                    'property': interaction.get('property', 'interaction'),
                    'direction': 'negative',
                    'strength': interaction.get('strength', 0.5),
                    'confidence': interaction.get('confidence', 0.5),
                    'position_weight': 1.0,
                })

    for concern in concerns:
        if concern in dimensions:
            dimensions[concern] = dimensions.get(concern, 0.0)

    weighted_total = 0.0
    for property_name, weight in priority_weights.items():
        if property_name not in dimensions:
            dimensions[property_name] = 0.0
        # Каждое измерение насыщается на уровне 1.0 (diminishing returns):
        # иначе сумма вкладов по ингредиентам растёт неограниченно и любой
        # насыщенный состав показывает «100%». Это НЕ меняет направление
        # оценки, а лишь ограничивает верхнюю границу.
        contribution = max(0.0, min(dimensions[property_name], 1.0))
        weighted_total += contribution * float(weight)

    safe_score = clamp(weighted_total / max(sum(priority_weights.values()), 1e-9), 0.0, 1.0)
    final_score = int(round(safe_score * 100))

    if unknown_factors and not positive_factors and not negative_factors and not hard_flags:
        final_score = max(final_score, 40)

    if hard_flags:
        final_score = min(final_score, 35)

    return {
        'score': int(final_score),
        'dimensions': {key: round(value, 3) for key, value in dimensions.items()},
        'positive_factors': positive_factors,
        'negative_factors': negative_factors,
        'unknown_factors': unknown_factors,
        'confidence': round(clamp((sum(1 for _ in positive_factors) + sum(1 for _ in negative_factors)) / max(len(valid_ingredients), 1), 0.0, 1.0), 3),
        'hard_flags': hard_flags,
    }
