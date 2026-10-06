from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .ingredient_normalizer import normalize_ingredient_name
from .scoring_config import (
    CLAMP_MAX,
    CLAMP_MIN,
    HARD_FLAG_SCORE_CAP,
    INTOLERANCE_PENALTY,
    POSITION_WEIGHT_DECAY,
    POSITION_WEIGHT_MAX,
    POSITION_WEIGHT_SINGLE,
    SATURATION_SCALE,
    UNKNOWN_SCORE_FLOOR,
)


def clamp(value: float, minimum: float = CLAMP_MIN, maximum: float = CLAMP_MAX) -> float:
    return max(minimum, min(maximum, value))


def calculate_position_weight(position: int, total: int) -> float:
    if total <= 1:
        return POSITION_WEIGHT_SINGLE
    normalized = position / max(total, 1)
    return clamp(POSITION_WEIGHT_MAX - normalized * POSITION_WEIGHT_DECAY)


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
    from .profile_resolver import normalize_scoring_profile

    user_profile = normalize_scoring_profile(user_profile)
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


def _profile_axis_multiplier(axis: str, profile: Dict[str, Any]) -> float:
    context = profile.get("structured") if isinstance(profile.get("structured"), dict) else profile
    multipliers = context.get("axis_multipliers") or {}
    return clamp(float(multipliers.get(axis, 1.0)), 0.5, 1.5)


PROFILE_CONFLICT_SCALE = 1.5
PROFILE_CONFLICT_DECAY = 2.0


def _profile_negative_multiplier(axis: str, profile: Dict[str, Any]) -> float:
    """Saturating risk modifier from matching concerns, active therapy, and procedures."""
    from .profile_matrix import PROFILE_MATRIX
    from .profile_resolver import (
        _canonical_matrix_id,
        _element_id,
        _procedure_factor,
        _severity_factor,
        _therapy_factor,
    )

    context = profile.get("structured") if isinstance(profile.get("structured"), dict) else profile
    risk_items: Dict[str, Tuple[Dict[str, Any], float]] = {}
    for key in ("concerns", "imperfections", "states", "selected"):
        for item in context.get(key) or []:
            sid = _canonical_matrix_id(_element_id(item))
            node = PROFILE_MATRIX.get(sid) if sid else None
            if node and node.get("mode") == "score":
                risk_items[sid] = (node, _severity_factor(item) if isinstance(item, dict) else 1.0)
    for item in context.get("therapy") or []:
        sid = _canonical_matrix_id(_element_id(item))
        node = PROFILE_MATRIX.get(sid) if sid else None
        if node and node.get("mode") == "score":
            risk_items[sid] = (node, _therapy_factor(item) if isinstance(item, dict) else 0.0)
    for item in context.get("procedures") or []:
        sid = _canonical_matrix_id(_element_id(item))
        node = PROFILE_MATRIX.get(sid) if sid else None
        if node and node.get("mode") == "score":
            risk_items[sid] = (node, _procedure_factor(item) if isinstance(item, dict) else 0.0)

    load = sum(float(node.get("axes", {}).get(axis, 0.0)) * factor
               for node, factor in risk_items.values())
    sensitivity = str(context.get("sensitivity") or "").strip().lower()
    if axis in {"irritation", "sensitization"}:
        load += {"medium": 0.25, "moderate": 0.25, "high": 0.75,
                 "very_high": 1.0, "severe": 1.0}.get(sensitivity, 0.0)
    if load <= 0.0:
        return 1.0
    return round(1.0 + PROFILE_CONFLICT_SCALE * (1.0 - math.exp(-load / PROFILE_CONFLICT_DECAY)), 3)


def score_product_against_profile_canonical(
    ingredients: List[str],
    canonical_knowledge: Dict[str, Dict[str, Dict[str, Any]]],
    user_profile: Dict[str, Any],
    canonical_weights: Dict[str, float],
    interactions: List[Dict[str, Any]] | None = None,
    saturation_scale: float | None = None,
) -> Dict[str, Any]:
    """Канонический Scoring Vector на 6 осях (axes.AXES), benefit-oriented.

    Individual Effects и Interaction Effects попадают НАПРЯМУЮ в canonical dimensions
    (без canonical→legacy→canonical). Возвращает canonical result (dimensions на 6 осях,
    factors с property=canonical axis, direction=benefit-oriented).
    """
    from .axes import AXES
    from .profile_resolver import normalize_scoring_profile, resolve_personal_profile

    user_profile = normalize_scoring_profile(user_profile)
    structured_profile = user_profile.get("structured")
    if isinstance(structured_profile, dict):
        structured_profile["axis_multipliers"] = resolve_personal_profile(
            structured_profile
        )["axis_multipliers"]
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
    axis_positive: Dict[str, List[float]] = {axis: [] for axis in AXES}
    axis_negative: Dict[str, List[float]] = {axis: [] for axis in AXES}
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
            weighted_value = strength * confidence * position_weight

            axis_multiplier = (
                _profile_axis_multiplier(axis, user_profile) if sign < 0 else 1.0
            )
            weighted_value *= axis_multiplier
            profile_multiplier = 1.0
            if sign < 0:
                profile_multiplier = _profile_negative_multiplier(axis, user_profile)
                weighted_value *= profile_multiplier

            if sign > 0:
                axis_positive[axis].append(weighted_value)
            else:
                axis_negative[axis].append(weighted_value)
            factor = {
                'ingredient': ingredient,
                'property': axis,
                'direction': 'positive' if sign > 0 else 'negative',
                'strength': strength,
                'confidence': confidence,
                'position_weight': round(position_weight, 3),
                'profile_multiplier': profile_multiplier,
                'axis_multiplier': axis_multiplier,
                'weighted_value': round(weighted_value, 6),
            }
            if sign > 0:
                positive_factors.append(factor)
            else:
                negative_factors.append(factor)

    # Diminishing returns для однотипных ingredient claims.
    # Сильнейший claim получает полный вес, последующие — 1/rank.
    for axis in AXES:
        positive_values = sorted(axis_positive[axis], reverse=True)
        negative_values = sorted(axis_negative[axis], reverse=True)

        if axis in {"hydration", "barrier"}:
            dimensions[axis] += positive_values[0] if positive_values else 0.0
        else:
            dimensions[axis] += sum(
                value / rank
                for rank, value in enumerate(positive_values, start=1)
            )

        dimensions[axis] -= sum(
            value / rank
            for rank, value in enumerate(negative_values, start=1)
        )

    from .profile_resolver import intolerance_ingredient_aliases

    for item in user_profile.get('intolerances') or []:
        aliases = intolerance_ingredient_aliases(item) or [str(item)]
        matched_ingredient = None
        for ingredient in valid_ingredients:
            ni = normalize_ingredient_name(ingredient)
            for alias in aliases:
                key = normalize_ingredient_name(alias)
                if ni and key and (key == ni or key in ni or ni in key):
                    matched_ingredient = ingredient
                    break
            if matched_ingredient:
                break
        if matched_ingredient:
            penalty_axis = INTOLERANCE_PENALTY["axis"]
            negative_factors.append({
                'ingredient': normalize_ingredient_name(matched_ingredient),
                'property': penalty_axis,
                'direction': 'negative',
                'strength': INTOLERANCE_PENALTY["strength"],
                'confidence': INTOLERANCE_PENALTY["confidence"],
                'position_weight': INTOLERANCE_PENALTY["position_weight"],
            })
            dimensions[penalty_axis] -= INTOLERANCE_PENALTY["dimension_delta"]

    interaction_breakdown: List[Dict[str, Any]] = []
    if interactions:
        from . import interaction_scoring
        if interaction_scoring.INTERACTION_SCORING_ENABLED:
            _, interaction_breakdown = interaction_scoring.aggregate_interactions(interactions)
            adjusted_agg: Dict[str, float] = {}
            for item in interaction_breakdown:
                axis = item["axis"]
                contribution = float(item["contribution"])
                axis_multiplier = (
                    _profile_axis_multiplier(axis, user_profile)
                    if contribution < 0 else 1.0
                )
                profile_multiplier = (
                    _profile_negative_multiplier(axis, user_profile)
                    if contribution < 0
                    else 1.0
                )
                item["axis_multiplier"] = axis_multiplier
                item["profile_multiplier"] = profile_multiplier
                item["weighted_contribution"] = round(
                    contribution * axis_multiplier * profile_multiplier, 6
                )
                adjusted_agg[axis] = adjusted_agg.get(axis, 0.0) + item["weighted_contribution"]
            for axis, contrib in adjusted_agg.items():
                dimensions[axis] += contrib

    weighted_total = 0.0
    if saturation_scale is None:
        from .scoring_config_store import get_production_saturation_scale
        saturation_scale = get_production_saturation_scale()
    for axis, weight in canonical_weights.items():
        # Плавное знакопеременное насыщение вместо жёсткого clamp(0..1):
        # отрицательные raw реально штрафуют, положительные насыщаются мягко.
        contribution = math.tanh(dimensions.get(axis, 0.0) / saturation_scale)
        weighted_total += contribution * float(weight)

    # 50% = нейтральная совместимость с профилем (НЕ «50% ингредиентов хорошие»).
    # Взвешенное среднее tanh(raw/S) лежит в [-1, 1], поэтому центрируем вокруг 50:
    #   raw=0          -> 50% (отсутствие эффекта — НЕ штраф и НЕ бонус);
    #   raw>0          -> >50% (положительный вклад);
    #   raw<0          -> <50% (отрицательный вклад).
    # Раньше clamp(avg, 0, 1) * 100 превращал raw=0 в 0% и обнулял отрицательные значения.
    avg = weighted_total / max(sum(canonical_weights.values()), 1e-9)
    final_score = int(round(clamp(50.0 + 50.0 * avg, 0.0, 100.0)))

    if unknown_factors and not positive_factors and not negative_factors and not hard_flags:
        final_score = max(final_score, UNKNOWN_SCORE_FLOOR)
    if hard_flags:
        final_score = min(final_score, HARD_FLAG_SCORE_CAP)

    ingredient_confidence: Dict[str, float] = {}
    for factor in positive_factors + negative_factors:
        key = normalize_ingredient_name(str(factor.get('ingredient') or ''))
        if key:
            ingredient_confidence[key] = max(
                ingredient_confidence.get(key, 0.0),
                float(factor.get('confidence') or 0.0),
            )
    for factor in interaction_breakdown:
        evidence_confidence = float(factor.get('confidence') or 0.0)
        for key in (factor.get('ingredient_a'), factor.get('ingredient_b')):
            normalized_key = normalize_ingredient_name(str(key or ''))
            if normalized_key:
                ingredient_confidence[normalized_key] = max(
                    ingredient_confidence.get(normalized_key, 0.0), evidence_confidence
                )
    for flag in hard_flags:
        key = normalize_ingredient_name(str(flag.get('ingredient') or ''))
        if key:
            ingredient_confidence[key] = max(ingredient_confidence.get(key, 0.0), 1.0)
    ingredient_confidence_denominator = {
        normalize_ingredient_name(str(ingredient))
        for ingredient in valid_ingredients
        if normalize_ingredient_name(str(ingredient))
    }

    return {
        'score': int(final_score),
        'dimensions': {axis: round(value, 3) for axis, value in dimensions.items()},
        'positive_factors': positive_factors,
        'negative_factors': negative_factors,
        'unknown_factors': unknown_factors,
        'confidence': round(clamp(
            sum(ingredient_confidence.values()) / max(len(ingredient_confidence_denominator), 1),
            0.0,
            1.0,
        ), 3),
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
