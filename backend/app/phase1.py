# phase1.py
# Phase 1 — детерминированная проверка ДОПУСКА продукта к рекомендации.
#
# Отвечает на вопрос: допустимо ли рекомендовать продукт этому пользователю?
# Это ОТДЕЛЬНОЕ решение, принимаемое ДО Phase 2 (обычный Score Engine).
# Положительные свойства НЕ компенсируют превышение порога негативной нагрузки.
#
# Phase 1 использует уже вычисленные факторы Score Engine (negative_factors,
# interaction_breakdown, hard_flags), поэтому НЕ дублирует per-ingredient цикл
# и НЕ расходится с Phase 2. Непереносимость и негативные взаимодействия
# учитываются ровно один раз (тестами закреплено).

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .scoring_config import AXES, INTOLERANCE_PENALTY, SATURATION_SCALE
from .ingredient_normalizer import normalize_ingredient_name

PHASE1_VERSION = "2.0.0"
# Все оси рассматриваются; блокирующими становятся только оси с multiplier > 1.
TRACKED_BRANCHES: Tuple[str, ...] = tuple(AXES)
BLOCKING_BRANCHES: Tuple[str, ...] = tuple(AXES)
PHASE1_LAMBDA = 1.0


def _detect_intolerance(user_profile: Dict[str, Any], ingredients: List[str]) -> Optional[str]:
    """Детекция непереносимости 1-в-1 с scoring engine (первое совпадение).

    Возвращает название совпавшего ингредиента или None.
    """
    from .profile_resolver import intolerance_ingredient_aliases

    valid = [i for i in ingredients if i and str(i).strip()]
    for item in user_profile.get('intolerances') or []:
        aliases = intolerance_ingredient_aliases(item) or [str(item)]
        matched: Optional[str] = None
        for ing in valid:
            ni = normalize_ingredient_name(ing)
            for alias in aliases:
                key = normalize_ingredient_name(alias)
                if ni and key and (key == ni or key in ni or ni in key):
                    matched = ing
                    break
            if matched:
                break
        if matched:
            return matched
    return None


def compute_negative_loads(
    scoring_result: Dict[str, Any],
    user_profile: Dict[str, Any],
    ingredients: List[str],
) -> Tuple[Dict[str, float], Dict[str, List[float]]]:
    """Вычисляет негативную нагрузку (negative_dimension) по каждой оси.

    Возвращает (negative_dim, neg_weights).
      negative_dim[axis] <= 0 — негативная часть измерения Score Engine
      (та же убывающая отдача 1/rank, что и в scoring_engine), БЕЗ положительной
      части. neg_weights[axis] — сырые weighted_value факторов.
    """
    negative_factors = scoring_result.get("negative_factors") or []
    neg_weights: Dict[str, List[float]] = {axis: [] for axis in AXES}
    for f in negative_factors:
        wv = f.get("weighted_value")
        if wv is None:
            # «Голая» запись непереносимости (без weighted_value) — учитывается ниже один раз.
            continue
        axis = f.get("property")
        if axis in neg_weights:
            neg_weights[axis].append(float(wv))

    negative_dim: Dict[str, float] = {axis: 0.0 for axis in AXES}
    for axis in AXES:
        vals = sorted(neg_weights[axis], reverse=True)
        negative_dim[axis] = -sum(v / rank for rank, v in enumerate(vals, start=1))

    # Непереносимость — один раз (тот же источник, что scoring engine).
    if _detect_intolerance(user_profile, ingredients):
        negative_dim[INTOLERANCE_PENALTY["axis"]] -= float(INTOLERANCE_PENALTY["dimension_delta"])

    # Негативные взаимодействия учитываются один раз через weighted_contribution.
    # Профильный риск отдельно определяет блокирующие оси и пороги Phase 1.
    for item in scoring_result.get("interaction_breakdown") or []:
        wc = item.get("weighted_contribution")
        if wc is not None and float(wc) < 0:
            axis = item.get("axis")
            if axis in negative_dim:
                negative_dim[axis] += float(wc)

    return negative_dim, neg_weights



def calculate_dynamic_threshold(
    axis: str,
    user_profile: Dict[str, Any],
) -> Optional[float]:
    """Возвращает None при multiplier <= 1, иначе порог 2 - multiplier."""
    from .scoring_engine import _profile_negative_multiplier

    multiplier = float(_profile_negative_multiplier(axis, user_profile) or 1.0)
    multiplier = min(2.0, max(1.0, multiplier))
    if multiplier <= 1.0:
        return None
    return round(2.0 - multiplier, 4)


def evaluate_phase1(
    scoring_result: Dict[str, Any],
    user_profile: Dict[str, Any],
    ingredients: List[str],
) -> Dict[str, Any]:
    """Запускает Phase 1 и возвращает структурированный результат допуска.

    Вход:
      scoring_result — результат score_product_against_profile_canonical;
      user_profile    — нормализованный scoring-профиль;
      ingredients     — нормализованный список ингредиентов.

    Возвращает:
      status            — passed | blocked | insufficient_data;
      branches          — результат каждой отслеживаемой ветви;
      violations        — нарушенные количественные ветви;
      hard_violations   — жёсткие ограничения (аллергия/restriction);
      negative_dimensions — негативная часть измерений (диагностика).
    """
    hard_flags = scoring_result.get("hard_flags") or []
    unknown_factors = scoring_result.get("unknown_factors") or []
    positive_factors = scoring_result.get("positive_factors") or []

    negative_dim, neg_weights = compute_negative_loads(scoring_result, user_profile, ingredients)

    from .scoring_engine import _profile_negative_multiplier
    branches: Dict[str, Any] = {}
    for axis in TRACKED_BRANCHES:
        load = max(0.0, -negative_dim.get(axis, 0.0))
        multiplier = min(
            2.0, max(1.0, float(_profile_negative_multiplier(axis, user_profile) or 1.0))
        )
        # Ось участвует в допуске только при коэффициенте строго больше 1.
        blocking = multiplier > 1.0
        threshold = round(2.0 - multiplier, 4) if blocking else None
        violated = bool(
            blocking and threshold is not None and load >= threshold
        )

        branches[axis] = {
            "axis": axis,
            "load": round(load, 4),
            "profile_negative_multiplier": round(multiplier, 3),
            "blocking": blocking,
            "threshold": threshold,
            "violated": violated,
            "factor_count": len(neg_weights.get(axis, [])),
        }
    violations = [b for b in branches.values() if b.get("violated")]
    hard_violations = [
        {
            "type": f.get("type"),
            "ingredient": f.get("ingredient"),
            "severity": f.get("severity"),
            "message": f.get("message"),
        }
        for f in hard_flags
    ]

    valid = [i for i in ingredients if i and str(i).strip()]
    unknown_ingredient_names = {
        normalize_ingredient_name(str(item.get("ingredient") or ""))
        for item in unknown_factors
        if item.get("ingredient")
    }
    all_ingredients_unknown = bool(valid) and all(
        normalize_ingredient_name(str(ingredient)) in unknown_ingredient_names
        for ingredient in valid
    )

    if not valid:
        status = "insufficient_data"
    elif hard_flags:
        status = "blocked"
    elif violations:
        status = "blocked"
    elif unknown_factors and all_ingredients_unknown and not any(neg_weights.values()):
        # Недостаточность определяется покрытием знаний, а не наличием позитивных эффектов.
        status = "insufficient_data"
    else:
        status = "passed"

    return {
        "status": status,
        "branches": branches,
        "violations": violations,
        "hard_violations": hard_violations,
        "negative_dimensions": {k: round(v, 4) for k, v in negative_dim.items()},
        "version": PHASE1_VERSION,
    }




def recommendation_status(phase1_result: Dict[str, Any], score: Optional[int]) -> str:
    """Независимый статус рекомендации.

    Не смешивается с числовым баллом: «Не рекомендовано» не отменяется высоким score.
    """
    status = phase1_result.get("status")
    if status == "blocked":
        return "Не рекомендовано"
    if status == "insufficient_data":
        return "Недостаточно данных"
    if score is None:
        return "Недостаточно данных"
    if score >= 60:
        return "Рекомендовано"
    return "Требует внимания"
