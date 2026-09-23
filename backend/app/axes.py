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
    "sebum": ("sebum", False),
    "sebum_production": ("sebum", False),
    "oil_control": ("sebum", True),
    "sebum_control": ("sebum", True),
    "sebum_regulating": ("sebum", True),
    "mattifying": ("sebum", True),
    "acne_control": ("sebum", True),
    # --- pigmentation (flip для «осветляющих») ---
    "pigmentation": ("pigmentation", False),
    "hyperpigmentation": ("pigmentation", False),
    "brightening": ("pigmentation", True),
    "whitening": ("pigmentation", True),
    "lightening": ("pigmentation", True),
    # --- НЕ ось (механизм/формульное свойство) ---
    "comedogenicity": (None, False),
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
