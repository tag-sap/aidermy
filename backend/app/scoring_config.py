# scoring_config.py
# Единый versioned конфиг scoring engine (продукт × профиль пользователя).
#
# Это ЕДИНСТВЕННЫЙ источник истины для всех числовых параметров deterministic
# scoring: веса, штрафы, бонусы, пороги, нормализация, clamping, правила
# взаимодействий ингредиентов. Production-модули импортируют значения отсюда
# (axes.py, decision_engine.py, interaction_scoring.py, scoring_engine.py,
# ingredient_graph.py), чтобы правила не «расползались» по кодовой базе.
#
# НЕ содержит знание об ингредиентах: сами эффекты ингредиентов и взаимодействия
# хранятся в БД (ingredients_catalog / ingredient_claims / ingredient_interactions).
# Здесь только ПРАВИЛА, по которым это знание превращается в score.
#
# ВАЖНО (архитектурный инвариант Фазы 9-fix):
#   comedogenicity, oiliness/sebum и irritation — РАЗНЫЕ параметры и не смешиваются:
#     - oiliness/sebum      -> ось "sebum" (только изменение выработки/уровня себума);
#     - irritation          -> ось "irritation" (раздражение/воспаление);
#     - comedogenicity      -> НЕ ось (механизм/формульное свойство), хранится в
#                             DATA_MODEL_PARAMETERS, но НЕ участвует в scoring.
#   comedogenicity / pore_clogging / breakout_potential / acneogenicity сознательно
#   НЕ маппятся в "sebum" и не подменяют его.

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Версия конфига. Меняется при ЛЮБОМ изменении числовых правил скоринга.
# Входит в snapshot calibration-экспорта и в идентичность результата скоринга.
# ---------------------------------------------------------------------------
SCORING_CONFIG_VERSION = "1.1.0"

# ===========================================================================
# 1. КАНОНИЧЕСКИЕ ПАРАМЕТРЫ (оси индивидуальных эффектов ингредиента)
# ===========================================================================
# Подписанные биологические endpoint'ы: «+» усиливает свойство, «-» ослабляет.
AXES: Tuple[str, ...] = (
    "hydration",      # гидратация рогового слоя
    "barrier",        # целостность/функция барьера
    "irritation",     # раздражение/воспаление
    "sensitization",  # аллергенный/сенсибилизирующий потенциал
    "sebum",          # продукция/уровень себума (oiliness)
    "pigmentation",   # пигментация/меланин
)

# Оси-«вред»: direction=positive означает УСИЛЕНИЕ вреда → негативный вклад в score.
# Оси-«польза» (hydration, barrier): direction=positive = положительный вклад.
AXIS_HARM = frozenset({"irritation", "sensitization", "sebum", "pigmentation"})
AXIS_BENEFIT = frozenset({"hydration", "barrier"})

# legacy property_name -> (canonical_axis, direction_flip).
# direction_flip=True: legacy direction инвертируется при переводе.
#   Пример: legacy "brightening" + "positive" (осветляет) -> "pigmentation" + "negative".
# Значение None у оси = не ось (механизм/формульное свойство): comedogenicity и т.п.
AXIS_ALIASES: Dict[str, Tuple[Optional[str], bool]] = {
    # --- hydration ---
    "hydration": ("hydration", False),
    "moisturizing": ("hydration", False),
    "humectant": ("hydration", False),
    # --- barrier ---
    "barrier": ("barrier", False),
    "barrier_support": ("barrier", False),
    "barrier_strengthening": ("barrier", False),
    # --- irritation (flip для «успокаивающих» legacy-имён) ---
    "irritation": ("irritation", False),
    "irritation_risk": ("irritation", False),
    "irritating": ("irritation", False),
    "soothing": ("irritation", True),
    "calming": ("irritation", True),
    "anti_irritation": ("irritation", True),
    "anti_inflammatory": ("irritation", True),
    "sensitivity": ("irritation", True),
    # --- sensitization ---
    "sensitization": ("sensitization", False),
    "sensitizer": ("sensitization", False),
    "allergen": ("sensitization", False),
    # --- sebum (flip для «контроль себума») ---
    # sebum = ТОЛЬКО изменение выработки/уровня себума.
    # НЕ маппим сюда comedogenicity / pore_clogging / breakout / acneogenicity.
    "sebum": ("sebum", False),
    "sebum_production": ("sebum", False),
    "oil_control": ("sebum", True),
    "sebum_control": ("sebum", True),
    "sebum_regulating": ("sebum", True),
    "mattifying": ("sebum", True),
    # --- pigmentation (flip для «осветляющих») ---
    "pigmentation": ("pigmentation", False),
    "hyperpigmentation": ("pigmentation", False),
    "brightening": ("pigmentation", True),
    "whitening": ("pigmentation", True),
    "lightening": ("pigmentation", True),
    # --- НЕ ось (механизм/формульное свойство) ---
    "comedogenicity": (None, False),
    "comedogenic": (None, False),
    "pore_clogging": (None, False),
    "breakout_potential": (None, False),
    "acneogenicity": (None, False),
    "acneogenic": (None, False),
    "acne_control": (None, False),
    "exfoliation": (None, False),
    "active_load": (None, False),
    "occlusive": (None, False),
}

# Каноническая ось -> legacy scoring dimension (COMPATIBILITY LAYER, НЕ источник истины).
# None = нет legacy-эквивалента (sensitization появилась только в канонической модели).
CANONICAL_TO_LEGACY_DIMENSION: Dict[str, Optional[str]] = {
    "hydration": "hydration",
    "barrier": "barrier_support",
    "irritation": "sensitivity",
    "sensitization": None,
    "sebum": "acne_control",
    "pigmentation": "brightening",
}

# Обратный маппинг legacy dimension -> canonical axis (для границы ввода).
LEGACY_TO_CANONICAL_DIMENSION: Dict[str, str] = {
    "hydration": "hydration",
    "barrier_support": "barrier",
    "sensitivity": "irritation",
    "acne_control": "sebum",
    "brightening": "pigmentation",
}

# Классификация legacy->canonical mapping (аудит Фазы 8).
#   exact          — тождественное значение (rename без потери смысла).
#   approximate    — приблизительный (flip + сужение смысла). НЕ доказательство KG.
#   canonical-only — оси нет в legacy (появилась только в канонической модели).
LEGACY_MAPPING_KIND: Dict[str, str] = {
    "hydration": "exact",
    "barrier_support": "exact",
    "sensitivity": "approximate",
    "acne_control": "approximate",
    "brightening": "approximate",
    "sensitization": "canonical-only",
}

# Человекочитаемые названия осей для summary (совпадает с decision_engine.DIMENSION_LABELS).
AXIS_LABELS: Dict[str, str] = {
    "hydration": "увлажнение",
    "barrier": "поддержку барьера кожи",
    "irritation": "снижение раздражения",
    "sensitization": "снижение сенсибилизации",
    "sebum": "контроль себума",
    "pigmentation": "выравнивание тона",
}

# ===========================================================================
# 2. ВЕСА ПАРАМЕТРОВ ПРОФИЛЯ ПОЛЬЗОВАТЕЛЯ
# ===========================================================================
# Legacy-измерения, которые понимает движок (для приоритетов).
DIMENSIONS: Tuple[str, ...] = (
    "hydration",
    "barrier_support",
    "sensitivity",
    "acne_control",
    "brightening",
)

# Базовые приоритеты (совпадают с прежним фолбэком).
DEFAULT_PRIORITIES: Dict[str, float] = {
    "hydration": 0.35,
    "barrier_support": 0.25,
    "sensitivity": 0.2,
    "acne_control": 0.1,
    "brightening": 0.1,
}

# Вклад типа кожи в веса измерений (детерминированно, без LLM).
# Это «modifiers для разных типов кожи».
#
# v1.1.0: снижен вес acne_control (→ sebum) для жирной кожи, т.к. ось sebum
# заполнена лишь в ~16% случаев (production calibration). Часть веса перенесена
# на sensitivity (→ irritation) и barrier_support (заполнены ~95-98%).
SKIN_TYPE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "сухая": {"hydration": 0.5, "barrier_support": 0.3},
    "жирная": {"acne_control": 0.25, "sensitivity": 0.2},
    "комбинирован": {"hydration": 0.3, "acne_control": 0.3},
    "чувствительн": {"sensitivity": 0.5, "barrier_support": 0.25},
    "нормальн": {"hydration": 0.3, "barrier_support": 0.3},
    "обезвожен": {"hydration": 0.55},
}

# Вклад concern'а в веса измерений.
CONCERN_WEIGHTS: Dict[str, Dict[str, float]] = {
    "акне": {"acne_control": 0.25, "sensitivity": 0.15, "barrier_support": 0.1},
    "пигментаци": {"brightening": 0.4},
    "морщин": {"barrier_support": 0.3, "brightening": 0.2},
    "покраснен": {"sensitivity": 0.4, "barrier_support": 0.2},
    "пор": {"acne_control": 0.15, "sensitivity": 0.05},
    "тускл": {"brightening": 0.3},
    "обезвожен": {"hydration": 0.5},
    "купероз": {"sensitivity": 0.4, "barrier_support": 0.2},
}

# ===========================================================================
# 3. ВЛИЯНИЕ ИНГРЕДИЕНТА НА ПАРАМЕТР (individual effect → contribution)
# ===========================================================================
# Взвешивание позиции ингредиента в INCI-списке:
#   position_weight = clamp(position_weight_max - normalized * position_weight_decay)
# где normalized = position / max(total, 1). Ближе к началу списка = выше концентрация.
POSITION_WEIGHT_MAX = 1.2
POSITION_WEIGHT_DECAY = 0.7
POSITION_WEIGHT_SINGLE = 1.0  # для списка из одного ингредиента

# Мягкий штраф за непереносимость (intolerance), найденную в составе.
# Идёт в ось irritation: dimensions["irritation"] -= dimension_delta.
# (dimension_delta — фактическая величина вычета; strength/confidence — метаданные
#  фактора, сохраняемые в negative_factors. В текущей реализации delta = strength.)
INTOLERANCE_PENALTY = {
    "axis": "irritation",
    "strength": 0.7,
    "confidence": 0.7,
    "position_weight": 1.0,
    "dimension_delta": 0.7,
}

# ===========================================================================
# 4. NORMALIZATION / CLAMPING
# ===========================================================================
# Общий clamp для промежуточных значений (position weight, per-axis contribution).
CLAMP_MIN = 0.0
CLAMP_MAX = 1.0

# ===========================================================================
# 5. ФИНАЛЬНЫЙ SCORE: штрафы / бонусы / пороги
# ===========================================================================
# «Бонус» неизвестности: если все ингредиенты неизвестны и нет ни положительных,
# ни отрицательных факторов, ни hard-флагов — score не опускается ниже порога.
UNKNOWN_SCORE_FLOOR = 40
# «Штраф» за жёсткие флаги (аллергия/restriction): score ограничивается сверху.
HARD_FLAG_SCORE_CAP = 35

# Пороги вердикта (decision_engine).
VERDICT_GOOD = 70
VERDICT_CAUTION = 40

# ===========================================================================
# 6. ПРАВИЛА ВЗАИМОДЕЙСТВИЯ ИНГРЕДИЕНТОВ (interaction contribution model)
# ===========================================================================
# Знание о конкретных взаимодействиях — в БД (ingredient_interactions).
# Здесь — ПРАВИЛА перевода interaction-записи в числовой contribution.
# Модель (v1): contribution = sign × strength_weight(strength) × confidence(confidence).
INTERACTION_SCORING_VERSION = "v1"

# Полный 4-layer Match включён в production: interaction contribution (Layer 2 internal
# + Layer 3 cross/shelf) реально влияет на финальный score наряду с Layer 1 (прямые
# эффекты) и Layer 4 (профиль). Не feature-flag для «потом» — целевая архитектура.
INTERACTION_SCORING_ENABLED_DEFAULT = True

# Строковый strength → вес (детерминированно). Числовой strength проходит clamp(0,1).
INTERACTION_STRENGTH_MAP: Dict[str, float] = {
    "strong": 1.0, "high": 1.0,
    "moderate": 0.6, "medium": 0.6,
    "weak": 0.3, "low": 0.3,
}
INTERACTION_STRENGTH_UNKNOWN_DEFAULT = 0.5  # для неизвестного строкового strength
INTERACTION_CONFIDENCE_DEFAULT = 0.0        # для отсутствующей/невалидной confidence

# Направления, распознаваемые при парсинге direction.
POSITIVE_DIRECTIONS = frozenset({"positive", "+", "increase", "increases"})
NEGATIVE_DIRECTIONS = frozenset({"negative", "-", "decrease", "decreases"})

# ===========================================================================
# 7. ПОРОГ ДОСТАТОЧНОСТИ ЗНАНИЯ (ingredient graph lookup)
# ===========================================================================
# confidence >= порога → state=known (участвует в score), иначе insufficient.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# ===========================================================================
# 8. ПАРАМЕТРЫ, ХРАНЯЩИЕСЯ В МОДЕЛИ ДАННЫХ, НО НЕ ЯВЛЯЮЩИЕСЯ SCORING-ОСЯМИ
# ===========================================================================
# Структурные поля ingredients_catalog. Часть маппится в оси (через AXIS_ALIASES),
# часть — механизм/формульное свойство, НЕ участвующее в score.
DATA_MODEL_PARAMETERS: Dict[str, Dict[str, Any]] = {
    "hydration":         {"scored_axis": "hydration",     "note": "гидратация"},
    "barrier_support":   {"scored_axis": "barrier",       "note": "поддержка барьера"},
    "soothing":          {"scored_axis": "irritation",    "note": "успокаивающее (flip)"},
    "oil_control":       {"scored_axis": "sebum",         "note": "контроль себума (flip)"},
    "brightening":       {"scored_axis": "pigmentation",  "note": "осветление (flip)"},
    "irritation_risk":   {"scored_axis": "irritation",    "note": "риск раздражения"},
    "sensitization":     {"scored_axis": "sensitization", "note": "сенсибилизация"},
    # comedogenicity — ОТДЕЛЬНЫЙ параметр формулы, сознательно НЕ является осью:
    "comedogenicity":    {"scored_axis": None,            "note": "комедогенность 0..5; НЕ участвует в score"},
}

# modifiers для разных типов продуктов.
# В текущей архитектуре product-type/category modifiers для scoring ОТСУТСТВУЮТ:
# категория/тип продукта (category/subcategory) используется только в каталоге и
# на полке, но НЕ влияет на по-ингредиентный scoring.
PRODUCT_TYPE_MODIFIERS: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Итоговая машиночитаемая структура (используется snapshot'ом calibration-экспорта).
# ---------------------------------------------------------------------------
def build_scoring_config_snapshot() -> Dict[str, Any]:
    """Собирает полный словарь конфига для calibration/export и аудита."""
    return {
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "axes": {
            "list": list(AXES),
            "labels": AXIS_LABELS,
            "harm": sorted(AXIS_HARM),
            "benefit": sorted(AXIS_BENEFIT),
            "aliases": {k: [v0, v1] for k, (v0, v1) in AXIS_ALIASES.items()},
            "canonical_to_legacy_dimension": CANONICAL_TO_LEGACY_DIMENSION,
            "legacy_to_canonical_dimension": LEGACY_TO_CANONICAL_DIMENSION,
            "legacy_mapping_kind": LEGACY_MAPPING_KIND,
        },
        "profile_parameter_weights": {
            "dimensions": list(DIMENSIONS),
            "default_priorities": DEFAULT_PRIORITIES,
            "skin_type_weights": SKIN_TYPE_WEIGHTS,
            "concern_weights": CONCERN_WEIGHTS,
        },
        "ingredient_effect": {
            "position_weight": {
                "max": POSITION_WEIGHT_MAX,
                "decay": POSITION_WEIGHT_DECAY,
                "single": POSITION_WEIGHT_SINGLE,
            },
            "intolerance_penalty": INTOLERANCE_PENALTY,
        },
        "normalization": {
            "clamp": {"min": CLAMP_MIN, "max": CLAMP_MAX},
        },
        "final_score": {
            "unknown_score_floor": UNKNOWN_SCORE_FLOOR,
            "hard_flag_score_cap": HARD_FLAG_SCORE_CAP,
            "verdict_good": VERDICT_GOOD,
            "verdict_caution": VERDICT_CAUTION,
        },
        "interaction_scoring": {
            "version": INTERACTION_SCORING_VERSION,
            "enabled_default": INTERACTION_SCORING_ENABLED_DEFAULT,
            "strength_map": INTERACTION_STRENGTH_MAP,
            "strength_unknown_default": INTERACTION_STRENGTH_UNKNOWN_DEFAULT,
            "confidence_default": INTERACTION_CONFIDENCE_DEFAULT,
            "positive_directions": sorted(POSITIVE_DIRECTIONS),
            "negative_directions": sorted(NEGATIVE_DIRECTIONS),
        },
        "knowledge": {
            "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
        },
        "data_model_parameters": DATA_MODEL_PARAMETERS,
        "product_type_modifiers": PRODUCT_TYPE_MODIFIERS,
    }


# Единый словарь-константа (для прямого импорта и для snapshot'а).
SCORING_CONFIG = build_scoring_config_snapshot()
