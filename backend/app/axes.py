# axes.py
# Фаза 1 — канонические 6 осей индивидуальных эффектов ингредиента.
#
# Устраняет рассинхрон трёх наборов (catalog columns / claims property_name /
# decision_engine.DIMENSIONS). Единый словарь осей и неразрушающий маппинг
# legacy-имён на канонические оси.
#
# НЕ меняет scoring: это только словарь + функции перевода. Scoring продолжает
# читать старые property_name; каноническая карта понадобится на Фазе 2.

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# Канонические нейтральные оси (подписанные биологические endpoint'ы).
#   + = усиливает свойство, - = ослабляет свойство.
AXES: Tuple[str, ...] = (
    "hydration",      # гидратация рогового слоя
    "barrier",        # целостность/функция барьера
    "irritation",     # раздражение/воспаление
    "sensitization",  # аллергенный/сенсибилизирующий потенциал
    "sebum",          # продукция/уровень себума
    "pigmentation",   # пигментация/меланин
)

# Маппинг legacy property_name -> (canonical_axis, direction_flip).
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
    # Фаза 9-fix: sebum = ТОЛЬКО изменение выработки/уровня себума.
    # НЕ маппим сюда comedogenicity / pore clogging / breakout / acneogenicity.
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

# legacy-направления для инверсии.
def _flip_direction(direction: str) -> str:
    d = (direction or "").strip().lower()
    if d in ("positive", "+", "increase", "increases"):
        return "negative"
    if d in ("negative", "-", "decrease", "decreases"):
        return "positive"
    return d


def canonicalize_axis(property_name: str) -> Tuple[Optional[str], bool]:
    """(canonical_axis, direction_flip) для legacy property_name.

    Возвращает (None, False), если имя не соответствует ни одной оси.
    """
    key = (property_name or "").strip().lower().replace(" ", "_")
    return AXIS_ALIASES.get(key, (None, False))


def canonicalize_effect(property_name: str, direction: str) -> Tuple[Optional[str], str]:
    """Переводит legacy effect (property_name, direction) в (axis, canonical_direction)."""
    axis, flip_dir = canonicalize_axis(property_name)
    if axis is None:
        return None, direction
    return axis, (_flip_direction(direction) if flip_dir else (direction or "").strip().lower())


def canonicalize_knowledge_map(knowledge: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Переводит knowledge map {ingredient: {property: {direction, strength, confidence}}}
    в канонические оси {ingredient: {axis: {...}}}.

    Неизвестные оси отбрасываются; в поле '_legacy_property' сохраняется исходное имя
    для трассировки (non-destructive).
    """
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for ingredient, props in (knowledge or {}).items():
        canon: Dict[str, Dict[str, Any]] = {}
        for prop, val in (props or {}).items():
            if not isinstance(val, dict):
                continue
            axis, direction = canonicalize_effect(prop, val.get("direction"))
            if axis is None:
                continue
            canon[axis] = {
                "direction": direction,
                "strength": val.get("strength"),
                "confidence": val.get("confidence"),
                "_legacy_property": prop,
            }
        if canon:
            out[ingredient] = canon
    return out


# ---------------------------------------------------------------------------
# Фаза 8 — Canonical scoring metadata + legacy compatibility layer.
# ---------------------------------------------------------------------------
# Оси-«вред»: direction=positive означает УСИЛЕНИЕ вреда → негативный вклад.
# benefit-оси (hydration, barrier): direction=positive = положительный вклад.
AXIS_HARM = frozenset({"irritation", "sensitization", "sebum", "pigmentation"})

# Каноническая ось → legacy scoring dimension (COMPATIBILITY LAYER, НЕ источник истины).
# None = нет legacy-эквивалента (sensitization появилась только в канонической модели).
CANONICAL_TO_LEGACY_DIMENSION: Dict[str, Optional[str]] = {
    "hydration": "hydration",
    "barrier": "barrier_support",
    "irritation": "sensitivity",
    "sensitization": None,
    "sebum": "acne_control",
    "pigmentation": "brightening",
}

# Обратный маппинг legacy dimension → canonical axis (для границы ввода).
LEGACY_TO_CANONICAL_DIMENSION: Dict[str, str] = {
    "hydration": "hydration",
    "barrier_support": "barrier",
    "sensitivity": "irritation",
    "acne_control": "sebum",
    "brightening": "pigmentation",
}

# Классификация legacy→canonical mapping (аудит Фазы 8).
#   exact         — тождественное значение (rename без потери смысла).
#   approximate   — приблизительный (flip + сужение смысла). НЕ доказательство KG.
#   canonical-only — оси нет в legacy (появилась только в канонической модели).
LEGACY_MAPPING_KIND: Dict[str, str] = {
    "hydration": "exact",
    "barrier_support": "exact",
    "sensitivity": "approximate",
    "acne_control": "approximate",
    "brightening": "approximate",
    "sensitization": "canonical-only",
}


def canonicalize_weights(legacy_weights: Dict[str, Any]) -> Dict[str, float]:
    """Legacy benefit-oriented weights → canonical benefit-oriented weights.

    Только переименование ключей (sensitivity→irritation, acne_control→sebum,
    brightening→pigmentation); значения не меняются. Оси без legacy-веса = 0.0.
    """
    out = {axis: 0.0 for axis in AXES}
    for legacy, weight in (legacy_weights or {}).items():
        axis = LEGACY_TO_CANONICAL_DIMENSION.get(legacy)
        if axis:
            out[axis] = float(weight)
    return out


def legacyize_dimensions(canonical_dimensions: Dict[str, Any]) -> Dict[str, float]:
    """Canonical dimensions → legacy dimensions (compatibility, для API/tests)."""
    out: Dict[str, float] = {}
    for axis, value in (canonical_dimensions or {}).items():
        legacy = CANONICAL_TO_LEGACY_DIMENSION.get(axis)
        if legacy:
            out[legacy] = value
    return out
