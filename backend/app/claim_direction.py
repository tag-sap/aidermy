# claim_direction.py
# Единая семантика direction для enrichment claims + safety validation.
#
# Проблема (root cause): enrichment-LLM трактовал direction как «хорошо/плохо»
# (benefit-oriented), тогда как scoring engine ждёт «усилить/ослабить endpoint»
# (endpoint-oriented). Это давало перепутанные направления на harm-осях.
#
# Здесь:
#   1) DIRECTION_SEMANTICS / DIRECTION_EXAMPLES — текст для промптов;
#   2) validate_claim() — safety net, проверяющий evidence vs direction
#      перед сохранением claim.

from __future__ import annotations

from typing import Optional, Tuple

from .axes import canonicalize_axis, _flip_direction

# ---------------------------------------------------------------------------
# Текст семантики (включается в оба enrichment-промпта).
# ---------------------------------------------------------------------------
DIRECTION_SEMANTICS = (
    "Семантика direction (ВАЖНО): direction означает НАПРАВЛЕНИЕ ИЗМЕНЕНИЯ endpoint, "
    "а НЕ «хорошо/плохо».\n"
    "harm-оси (irritation, sensitization, sebum, pigmentation):\n"
    "  positive = усиливает вред; negative = ослабляет вред / soothing.\n"
    "benefit-оси (hydration, barrier):\n"
    "  positive = усиливает пользу; negative = ослабляет пользу.\n"
)

DIRECTION_EXAMPLES = (
    "Примеры:\n"
    "  anti-inflammatory / soothing -> irritation negative\n"
    "  contact dermatitis risk -> sensitization positive\n"
    "  sebum absorbing / mattifying -> sebum negative\n"
    "  inhibits tyrosinase / reduces pigmentation -> pigmentation negative\n"
    "  hydration benefit -> hydration positive\n"
    "  barrier repair -> barrier positive"
)


def prompt_instruction() -> str:
    return DIRECTION_SEMANTICS + "\n" + DIRECTION_EXAMPLES


# ---------------------------------------------------------------------------
# Safety validation: evidence -> expected endpoint direction.
# ---------------------------------------------------------------------------
# (ось, ожидаемый direction) по ключевым словам evidence.
# Ключевые слова подобраны так, чтобы не путать benefit/harm и учитывать отрицание:
#   "non-irritating" -> benefit (не harm), "reduces X" -> benefit, "increase X" -> harm.
_HARM_BENEFIT = {
    "irritation": (
        ("anti-inflammatory", "anti inflammatory", "sooth", "calm", "anti-irritat",
         "reduce irritation", "reduce erythema", "reduce redness", "reduce inflammation",
         "non-irritating", "non irritating"),
        ("irritating", "irritant", "irritates", "sting", "burn",
         "may irritate", "can irritate", "increase irritation", "increases irritation",
         "irritation potential", "causes irritation"),
    ),
    "sensitization": (
        ("hypoallergenic", "non-sensitizing", "non sensitizing", "low sensitization"),
        ("contact dermatitis", "sensitizing", "sensitizer", "allergen", "allergic",
         "potential sensitizer", "eugenol", "linalool", "can cause sensitization",
         "increase sensitization"),
    ),
    "sebum": (
        ("mattif", "absorb", "sebum control", "reduce sebum", "oil control",
         "oil-control", "regulat sebum", "anti-acne", "sebum regulat", "sebum absorb"),
        ("increase sebum", "sebum production", "stimulat sebum"),
    ),
    "pigmentation": (
        ("tyrosinase", "melanogenesis", "brighten", "whiten", "lighten",
         "reduce pigmentation", "reduce hyperpigmentation", "melanin synthesis",
         "inhibit melanin"),
        ("increase pigmentation", "stimulat melanin", "darken"),
    ),
}
_BENEFIT_BENEFIT = {
    "hydration": (
        ("moisturiz", "humectant", "hydrat", "water-binding", "water binding"),
        ("dehydrat", "drying", "reduce hydration", "decreases hydration"),
    ),
    "barrier": (
        ("barrier repair", "strengthen barrier", "restore barrier", "support barrier",
         "improve barrier", "barrier function", "repair barrier"),
        ("disrupt barrier", "weaken barrier", "impair barrier"),
    ),
}


def _expected_direction(axis: str, evidence: str) -> Optional[str]:
    """Возвращает ожидаемый direction по evidence, или None если сигнал неясен."""
    ev = (evidence or "").lower()
    table = _HARM_BENEFIT.get(axis) or _BENEFIT_BENEFIT.get(axis)
    if not table:
        return None
    benefit_hints, harm_hints = table
    has_benefit = any(h in ev for h in benefit_hints)
    has_harm = any(h in ev for h in harm_hints)
    if has_benefit and not has_harm:
        # benefit-ось: benefit = positive; harm-ось: benefit = negative (ослабить вред).
        return "positive" if axis in ("hydration", "barrier") else "negative"
    if has_harm and not has_benefit:
        return "negative" if axis in ("hydration", "barrier") else "positive"
    return None  # оба/ни одного -> неоднозначно


def validate_claim(
    property_name: str,
    direction: str,
    evidence: str = "",
    confidence: float = 0.0,
) -> Tuple[str, Optional[str], str]:
    """Проверяет claim перед сохранением.

    Возвращает (verdict, corrected_direction, reason):
      verdict:
        'ok'     — нет противоречия (или не axis/neutral) -> сохранять как есть;
        'flip'   — явное противоречие -> исправить direction на corrected_direction;
        'reject' — противоречие, но слишком неоднозначно/низкая confidence -> не сохранять.

    Работает с canonical axis: property_name канонизируется, direction приводится
    к canonical (с учётом flip legacy-имён). Возвращает corrected_direction в RAW
    (исходной) форме для сохранения.
    """
    axis, flip_dir = canonicalize_axis(property_name)
    if axis is None:
        return ("ok", None, "non-axis")
    d = (direction or "").strip().lower()
    if d not in ("positive", "negative"):
        return ("ok", None, "neutral")

    canonical_direction = _flip_direction(d) if flip_dir else d
    expected = _expected_direction(axis, evidence)
    if expected is None:
        return ("ok", None, "no-clear-signal")

    if expected == canonical_direction:
        return ("ok", None, "consistent")

    # Противоречие. Исправляем только если confidence достаточно высокая.
    opposite = "negative" if canonical_direction == "positive" else "positive"
    raw_opposite = _flip_direction(opposite) if flip_dir else opposite
    if (confidence or 0.0) >= 0.4:
        return ("flip", raw_opposite, f"evidence contradicts direction ({axis} {d} -> {raw_opposite})")
    return ("reject", None, f"contradiction but low confidence ({confidence})")
