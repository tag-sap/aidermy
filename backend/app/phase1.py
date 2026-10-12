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

PHASE1_VERSION = "1.0.0"

# Блокирующие ветви допуска (по итогам аудита).
BLOCKING_BRANCHES: Tuple[str, ...] = ("irritation", "sensitization")

# Оси, по которым считается негативная нагрузка (для диагностики).
# barrier/sebum/pigmentation не блокируют: их негативные сигналы редки и/или
# слабо подтверждены — см. отчёт. Нагрузка всё равно попадает в trace.
TRACKED_BRANCHES: Tuple[str, ...] = ("irritation", "sensitization", "barrier", "sebum", "pigmentation")

# Пороги негативной нагрузки. ПРЕДВАРИТЕЛЬНЫЕ значения, НЕ откалиброваны по
# независимым эталонным меткам (их нет в репозитории). Обоснование:
#   irritation    — нагрузка ~0.7 = один сильный подтверждённый ирритант
#                   (strength 0.8 * confidence 0.9 * position_weight 1.0 ≈ 0.72)
#                   при отсутствии профильных множителей;
#   sensitization — нагрузка ~0.5 = известный сенсибилизатор из allergen_sensitizer
#                   (potential 0.7 * confidence 0.8 ≈ 0.56).
PHASE1_THRESHOLDS: Dict[str, float] = {
    "irritation": 0.7,
    "sensitization": 0.5,
}

# Коэффициент повышения веса нарушенной ветви в negative_only_score.
# ПРЕДВАРИТЕЛЬНЫЙ (lambda=1.0 => вес нарушенной ветви удваивается до нормализации).
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

    # Негативные взаимодействия — один раз (weighted_contribution уже содержит
    # профильные множители; НЕ складываем с исходным contribution повторно).
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
    """Индивидуальный порог: профиль меняет допустимую нагрузку,
    а не силу отдельных вкладов ингредиентов.
    """
    base = PHASE1_THRESHOLDS.get(axis)
    if base is None:
        return None

    # Используем уже существующую оценку профильного риска:
    # чувствительность, состояния, терапия и процедуры.
    # Импорт локальный, чтобы избежать циклического импорта модулей.
    from .scoring_engine import _profile_negative_multiplier

    multiplier = _profile_negative_multiplier(axis, user_profile)
    multiplier = max(1.0, float(multiplier or 1.0))
    return round(base / multiplier, 4)


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

    branches: Dict[str, Any] = {}
    for axis in TRACKED_BRANCHES:
        load = max(0.0, -negative_dim.get(axis, 0.0))
        blocking = axis in BLOCKING_BRANCHES
        threshold = calculate_dynamic_threshold(axis, user_profile) if blocking else None
        violated = bool(blocking and threshold is not None and load > threshold)
        branches[axis] = {
            "axis": axis,
            "load": round(load, 4),
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
    if not valid:
        status = "insufficient_data"
    elif hard_flags:
        status = "blocked"
    elif violations:
        status = "blocked"
    elif unknown_factors and not positive_factors and not any(neg_weights.values()):
        # Состав целиком неизвестен — не можем ни подтвердить риск, ни безопасность.
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


def compute_negative_only_score(
    phase1_result: Dict[str, Any],
    scoring_result: Dict[str, Any],
    user_profile: Dict[str, Any],
    ingredients: List[str],
    canonical_weights: Dict[str, float],
) -> Optional[int]:
    """Негативный результат (negative_only_score) при отказе в допуске.

    Строится ТОЛЬКО из негативных вкладов; положительные факторы не участвуют.
    Вес нарушенной ветви повышается: adjusted = base * (1 + lambda * violation),
    затем все веса нормализуются до суммы 1. Итог ограничен 0..100.

    Возвращает None, если негативный вклад отсутствует (нельзя достоверно рассчитать).
    """
    negative_dim, _ = compute_negative_loads(scoring_result, user_profile, ingredients)
    branches = phase1_result.get("branches") or {}

    # Только оси с фактическим негативным сигналом.
    active = {axis: negative_dim[axis] for axis in AXES if negative_dim.get(axis, 0.0) < 0.0}
    if not active:
        return None

    base_weights = {axis: float(canonical_weights.get(axis, 0.0)) for axis in active}
    total = sum(base_weights.values())
    if total <= 0:
        base_weights = {axis: 1.0 for axis in active}
        total = sum(base_weights.values())

    adjusted: Dict[str, float] = {}
    for axis in active:
        w = base_weights[axis] / total
        violated = bool((branches.get(axis) or {}).get("violated"))
        adjusted[axis] = w * (1.0 + PHASE1_LAMBDA * (1.0 if violated else 0.0))

    adj_total = sum(adjusted.values()) or 1.0

    weighted = 0.0
    for axis in active:
        w = adjusted[axis] / adj_total
        weighted += w * math.tanh(negative_dim[axis] / SATURATION_SCALE)

    raw = 50.0 + 50.0 * weighted
    return int(round(max(0.0, min(100.0, raw))))


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
