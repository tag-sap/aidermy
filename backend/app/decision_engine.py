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

# Измерения, которые понимает существующий scoring engine.
DIMENSIONS: Tuple[str, ...] = (
    "hydration",
    "barrier_support",
    "sensitivity",
    "acne_control",
    "brightening",
)

# Базовые приоритеты (совпадают с прежним фолбэком в services.py).
DEFAULT_PRIORITIES: Dict[str, float] = {
    "hydration": 0.35,
    "barrier_support": 0.25,
    "sensitivity": 0.2,
    "acne_control": 0.1,
    "brightening": 0.1,
}

# Вклад типа кожи в веса измерений (детерминированно, без LLM).
SKIN_TYPE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "сухая": {"hydration": 0.5, "barrier_support": 0.3},
    "жирная": {"acne_control": 0.4, "sensitivity": 0.15},
    "комбинирован": {"hydration": 0.3, "acne_control": 0.3},
    "чувствительн": {"sensitivity": 0.5, "barrier_support": 0.25},
    "нормальн": {"hydration": 0.3, "barrier_support": 0.3},
    "обезвожен": {"hydration": 0.55},
}

# Вклад concern'а в веса измерений.
CONCERN_WEIGHTS: Dict[str, Dict[str, float]] = {
    "акне": {"acne_control": 0.4, "sensitivity": 0.15},
    "пигментаци": {"brightening": 0.4},
    "морщин": {"barrier_support": 0.3, "brightening": 0.2},
    "покраснен": {"sensitivity": 0.4, "barrier_support": 0.2},
    "пор": {"acne_control": 0.3},
    "тускл": {"brightening": 0.3},
    "обезвожен": {"hydration": 0.5},
    "купероз": {"sensitivity": 0.4, "barrier_support": 0.2},
}

# Человекочитаемые названия измерений для summary.
DIMENSION_LABELS: Dict[str, str] = {
    "hydration": "увлажнение",
    "barrier_support": "поддержку барьера кожи",
    "sensitivity": "снижение раздражения",
    "acne_control": "контроль акне",
    "brightening": "выравнивание тона",
}

VERDICT_GOOD = 70
VERDICT_CAUTION = 40


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


def build_verdict(score: int) -> str:
    """Детерминированный verdict, согласованный со score."""
    if score >= VERDICT_GOOD:
        return "Подходит"
    if score >= VERDICT_CAUTION:
        return "Требует внимания"
    return "Не рекомендуется"


def _top_property(factors: List[Dict[str, Any]], direction: str) -> Optional[str]:
    """Возвращает свойство с наибольшим вкладом (strength*confidence)."""
    best: Optional[str] = None
    best_weight = -1.0
    for f in factors:
        if str(f.get("direction", "")).lower() != direction:
            continue
        w = float(f.get("strength", 0.0) or 0.0) * float(f.get("confidence", 0.0) or 0.0)
        if w > best_weight:
            best_weight = w
            best = str(f.get("property", "") or "")
    return best


def build_summary(
    analysis: Dict[str, Any],
    profile: Dict[str, Any],
    skin_type: str = "",
    score: Optional[int] = None,
) -> str:
    """Детерминированное, персонализированное резюме, согласованное с анализом.

    Строится ТОЛЬКО из фактических результатов scoring engine (dimensions,
    positive/negative factors, hard_flags) и реального профиля пользователя.
    Не генерирует фразы вида «подходит для нормальной кожи», если в профиле
    не указан нормальный тип.
    """
    if score is None:
        score = int(analysis.get("score") or 0)

    phrase = _skin_phrase(profile, skin_type)

    hard_flags = analysis.get("hard_flags") or []
    if hard_flags:
        ing = str(hard_flags[0].get("ingredient") or "ингредиент")
        return (
            f"<bad>В составе есть ингредиент, на который у вас отмечена аллергия — {ing}.</bad> "
            f"Оценка совместимости снижена до {score}%."
        )

    positive = analysis.get("positive_factors") or []
    negative = analysis.get("negative_factors") or []
    confidence = float(analysis.get("confidence") or 0.0)

    if confidence <= 0 and not positive and not negative:
        return (
            "Недостаточно данных об ингредиентах, чтобы дать уверенную оценку совместимости. "
            "Попробуйте проверить состав повторно."
        )

    top_pos = _top_property(positive, "positive")
    top_neg = _top_property(negative, "negative")

    if score >= VERDICT_GOOD:
        core = f"Формула в целом соответствует {phrase}"
        if top_pos:
            core += f" и поддерживает {DIMENSION_LABELS.get(top_pos, top_pos)}"
        core += "."
        if top_neg:
            core += f" <warning>Обратите внимание на фактор «{DIMENSION_LABELS.get(top_neg, top_neg)}».</warning>"
        return core

    if score >= VERDICT_CAUTION:
        core = f"Формула требует внимания применительно к {phrase}"
        if top_neg:
            core += f" из-за фактора «{DIMENSION_LABELS.get(top_neg, top_neg)}»"
        core += "."
        if top_pos:
            core += f" <good>При этом она поддерживает {DIMENSION_LABELS.get(top_pos, top_pos)}.</good>"
        return core

    core = f"Формула, скорее всего, не подходит {phrase}"
    if top_neg:
        core += f" из-за значимого конфликта по фактору «{DIMENSION_LABELS.get(top_neg, top_neg)}»"
    core += "."
    return core


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
    ) -> Dict[str, Any]:
        priorities = priorities_for_profile(profile, skin_type)
        result = self.analysis_service.analyze(
            product_name,
            ingredients,
            profile,
            priorities,
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

