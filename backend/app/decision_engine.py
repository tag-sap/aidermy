# decision_engine.py
# Явное «дерево решений» / Decision Engine для анализа и подбора косметики.
#
# Это СТРУКТУРИРОВАННЫЙ слой поверх существующего deterministic scoring engine
# (scoring_engine.score_product_against_profile + AnalysisService), а НЕ новый
# независимый движок:
#
#   User Skin Profile -> Cabinet -> Category -> Product Type ->
#   Ingredient Analysis (существующий scoring engine) -> Priorities ->
#   Benefits / Risks / Compatibility -> Verdict + Summary -> Recommendation
#
# Финальный compatibility score всегда считается существующим движком.
# AI может обогащать знания ингредиентов, но НЕ выставляет итоговый процент.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .analysis_service import AnalysisService
from .scoring_engine import score_product_against_profile  # noqa: F401  (явная зависимость)

# Измерения и веса вынесены в scoring_config.py — единственный versioned источник истины.
from .scoring_config import (
    CONCERN_WEIGHTS,
    DEFAULT_PRIORITIES,
    SKIN_TYPE_WEIGHTS,
    VERDICT_CAUTION,
    VERDICT_GOOD,
    AXIS_LABELS as DIMENSION_LABELS,
    DIMENSIONS,
)


def _effective_skin_type(profile: Dict[str, Any], skin_type: str = "") -> str:
    """Определяет фактический тип кожи из доступных полей профиля."""
    value = (
        (profile or {}).get("skin_type")
        or skin_type
        or (profile or {}).get("skin_type_determined")
        or ""
    )
    return str(value or "").strip()


def _skin_phrase(profile: Dict[str, Any], skin_type: str = "") -> str:
    """Натуральная формулировка типа кожи для персонализированного summary.

    Никогда не подставляет абстрактный «средний тип кожи» — только реальные
    данные профиля пользователя.
    """
    st = _effective_skin_type(profile, skin_type).lower()
    if not st:
        return "ваш профиль"
    if "чувствительн" in st:
        return "вашему профилю чувствительной кожи"
    if "сухая" in st:
        return "вашему профилю сухой кожи"
    if "жирн" in st:
        return "вашему профилю жирной кожи"
    if "комбинирован" in st:
        return "вашему профилю комбинированной кожи"
    if "нормальн" in st:
        return "вашему профилю нормальной кожи"
    return f"вашему профилю ({st})"


def priorities_for_profile(profile: Dict[str, Any], skin_type: str = "") -> Dict[str, float]:
    """Выводит веса измерений из Skin Profile.

    Использует существующую weight-систему движка: усиливает те измерения,
    которые важны для конкретного профиля, затем нормализует.
    """
    weights: Dict[str, float] = dict(DEFAULT_PRIORITIES)

    st = _effective_skin_type(profile, skin_type).lower()
    for key, dims in SKIN_TYPE_WEIGHTS.items():
        if key in st:
            for dim, w in dims.items():
                weights[dim] = weights.get(dim, 0.0) + w

    concerns = (profile or {}).get("concerns") or []
    if isinstance(concerns, str):
        concerns = [c.strip() for c in concerns.split(",") if c.strip()]
    for concern in concerns:
        c = str(concern).strip().lower()
        for key, dims in CONCERN_WEIGHTS.items():
            if key in c or (c and c in key):
                for dim, w in dims.items():
                    weights[dim] = weights.get(dim, 0.0) + w

    total = sum(weights.values()) or 1.0
    return {k: round(v / total, 4) for k, v in weights.items()}


def profile_weights(profile: Dict[str, Any], skin_type: str = "") -> Dict[str, float]:
    """6 canonical weights (нормализованы) для scoring engine.

    Принимает НОВЫЙ structured profile (English IDs) либо legacy RU-поля —
    в этом случае сначала прогоняет legacy -> structured mapper.
    """
    from .profile_matrix import PROFILE_MATRIX
    from .profile_resolver import legacy_profile_to_structured, resolve_personal_profile

    profile = profile or {}

    # Явный structured-профиль (новый формат) — используем напрямую.
    if isinstance(profile.get("structured"), dict):
        return resolve_personal_profile(profile["structured"])["weights"]

    st = _effective_skin_type(profile, skin_type).lower()

    concerns = profile.get("concerns") or []
    if isinstance(concerns, str):
        concerns = [c.strip() for c in concerns.split(",") if c.strip()]

    is_structured = (
        st in PROFILE_MATRIX
        or any((str(c).strip().lower() in PROFILE_MATRIX) for c in concerns)
        or any(k in profile for k in ("imperfections", "states", "therapy", "procedures", "selected"))
    )

    if is_structured:
        p = dict(profile)
        if not p.get("skin_type") and st:
            p["skin_type"] = st
        return resolve_personal_profile(p)["weights"]

    structured = legacy_profile_to_structured(profile)
    if st and not structured["skin_type"]:
        structured["skin_type"] = st
    return resolve_personal_profile(structured)["weights"]


def build_verdict(score: int) -> str:
    """Детерминированный verdict, согласованный со score."""
    if score >= VERDICT_GOOD:
        return "Подходит"
    if score >= VERDICT_CAUTION:
        return "Требует внимания"
    return "Не рекомендуется"


def build_summary(
    analysis: Dict[str, Any],
    profile: Dict[str, Any],
    skin_type: str = "",
    score: Optional[int] = None,
) -> str:
    """Нейтральное детерминированное резюме (fallback, без причин).

    Содержит ТОЛЬКО общий вердикт-парафраз, согласованный со score. НЕ содержит
    названий ингредиентов и hardcoded-описаний эффектов — человеческое объяснение
    причин полностью генерирует AI Report (generate_ai_report).
    """
    if score is None:
        score = int(analysis.get("score") or 0)

    phrase = _skin_phrase(profile, skin_type)

    hard_flags = analysis.get("hard_flags") or []
    if hard_flags:
        return f"Оценка совместимости снижена до {score}% из-за выявленного ограничения в составе."

    positive = analysis.get("positive_factors") or []
    negative = analysis.get("negative_factors") or []
    confidence = float(analysis.get("confidence") or 0.0)

    if confidence <= 0 and not positive and not negative:
        return "Недостаточно данных об ингредиентах, чтобы дать уверенную оценку совместимости."

    if score >= VERDICT_GOOD:
        return f"Формула в целом подходит {phrase}."
    if score >= VERDICT_CAUTION:
        return f"Формула требует внимания применительно к {phrase}."
    return f"Формула, скорее всего, не подходит {phrase}."


def ingredient_lists(analysis: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Извлекает safe/caution ингредиенты из факторов scoring engine."""
    safe: List[str] = []
    caution: List[str] = []
    for f in analysis.get("positive_factors") or []:
        name = str(f.get("ingredient") or "").strip()
        if name and name not in safe:
            safe.append(name)
    for f in analysis.get("negative_factors") or []:
        name = str(f.get("ingredient") or "").strip()
        if name and name not in caution:
            caution.append(name)
    return safe[:8], caution[:8]


class DecisionEngine:
    """Обёртка над существующим AnalysisService, добавляющая verdict/summary.

    НЕ дублирует scoring engine — вызывает его напрямую.
    """

    def __init__(self, analysis_service: Optional[AnalysisService] = None):
        self.analysis_service = analysis_service or AnalysisService()

    def analyze(
        self,
        product_name: str,
        ingredients: str | List[str],
        profile: Dict[str, Any],
        skin_type: str = "",
        knowledge: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
        interactions: Optional[List[Dict[str, Any]]] = None,
        saturation_scale: float | None = None,
    ) -> Dict[str, Any]:
        priorities = profile_weights(profile, skin_type)
        result = self.analysis_service.analyze(
            product_name,
            ingredients,
            profile,
            priorities,
            knowledge=knowledge,
            interactions=interactions,
            priorities_are_canonical=True,
            saturation_scale=saturation_scale,
        )
        score = int(result.get("score") or 0)
        safe, caution = ingredient_lists(result)
        result["score"] = score
        result["verdict"] = build_verdict(score)
        result["summary"] = build_summary(result, profile, skin_type, score)
        result["safe_ingredients"] = safe
        result["caution_ingredients"] = caution
        result["priorities"] = priorities
        return result

