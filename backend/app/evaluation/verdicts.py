"""Single source of truth for user-facing compatibility verdicts.

The Score Engine's numeric thresholds are unchanged. This module only maps an
already calculated 0..100 compatibility score to the five user-facing labels,
and maps semantic per-parameter verdicts to an icon. It never calculates or
weights a compatibility score.
"""
from __future__ import annotations

from typing import Mapping

# Thresholds are deliberately identical to the existing Score Engine bands:
# 0–19, 20–39, 40–59, 60–79, 80–100. A score of exactly 20 belongs to the
# second band, exactly 40 to the third, and so on.
VERDICT_BANDS: tuple[tuple[int, str, str, str], ...] = (
    (80, "Отлично подходит", "good", "happy"),
    (60, "Хорошо подходит", "good", "happy"),
    (40, "Подходит частично", "neutral", "neutral"),
    (20, "Слабо подходит", "warn", "alert"),
    (0, "Не подходит", "bad", "dead"),
)

VERDICT_ICON_BY_STATUS: dict[str, str] = {
    "positive": "happy",
    "negative": "dead",
    "caution": "alert",
    "neutral": "neutral",
    "unknown": "neutral",
}

ICON_IDS: frozenset[str] = frozenset({"dead", "happy", "neutral", "alert"})


def verdict_band(score: float | int | None) -> Mapping[str, str] | None:
    """Return the label/tone/icon for a deterministic compatibility score.

    ``None`` means there is no score: the caller must not invent a 0, 50 or an
    arbitrary band. Non-finite values are treated as absent as well.
    """
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value != value or value in {float("inf"), float("-inf")}:
        return None
    value = max(0.0, min(100.0, value))
    for threshold, label, tone, icon in VERDICT_BANDS:
        if value >= threshold:
            return {
                "label": label,
                "tone": tone,
                "icon": icon,
                "min": str(threshold),
            }
    return None


def verdict_text(score: float | int | None) -> str:
    band = verdict_band(score)
    return str(band["label"]) if band else "Недостаточно данных"


def icon_for_status(status: str | None) -> str:
    """Map any per-parameter status (including old payloads) to a sprite id."""
    legacy = {
        "check": "happy",
        "cross": "dead",
        "dash": "neutral",
    }
    value = str(status or "unknown")
    value = legacy.get(value, value)
    if value in ICON_IDS:
        return value
    return VERDICT_ICON_BY_STATUS.get(value, "neutral")
