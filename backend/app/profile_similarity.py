# profile_similarity.py
# Детерминированное сравнение Skin Profile для Community Intelligence.
# НЕ использует LLM. Работает только с параметрами профиля.

from __future__ import annotations

from typing import Any, Dict

# Настраиваемые константы Community Intelligence.
COMMUNITY_SIMILARITY_THRESHOLD = 70  # порог похожести (0..100)
COMMUNITY_MIN_PERSONALIZED_REVIEWS = 5  # минимальная выборка для персонального рейтинга

AGE_ORDER = ["до 25", "25–35", "35–45", "45+"]


def _as_set(value: Any) -> set:
    if isinstance(value, list):
        return {str(x).strip().lower() for x in value if str(x).strip()}
    if isinstance(value, str):
        return {x.strip().lower() for x in value.split(",") if x.strip()}
    return set()


def _jaccard(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 0.5  # оба пустые — нейтрально
    return len(a & b) / len(union)


def _skin_similarity(a: str, b: str) -> float:
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a and not b:
        return 0.5
    if a == b:
        return 1.0
    if a and b and (a in b or b in a):
        return 0.6
    return 0.0


def _age_similarity(a: str, b: str) -> float:
    a = (a or "").strip()
    b = (b or "").strip()
    if not a and not b:
        return 0.5
    if a == b:
        return 1.0
    if a in AGE_ORDER and b in AGE_ORDER:
        distance = abs(AGE_ORDER.index(a) - AGE_ORDER.index(b))
        return max(0.0, 1.0 - distance / (len(AGE_ORDER) - 1))
    return 0.0


class ProfileSimilarityService:
    """Возвращает similarityScore 0..100 между двумя Skin Profile."""

    def similarity(self, profile_a: Dict[str, Any], profile_b: Dict[str, Any]) -> int:
        a = profile_a or {}
        b = profile_b or {}

        skin = _skin_similarity(
            a.get("skin_type") or a.get("skinType"),
            b.get("skin_type") or b.get("skinType"),
        )
        concerns = _jaccard(_as_set(a.get("concerns")), _as_set(b.get("concerns")))
        allergies = _jaccard(_as_set(a.get("allergies")), _as_set(b.get("allergies")))
        age = _age_similarity(a.get("age"), b.get("age"))

        score = 0.35 * skin + 0.35 * concerns + 0.15 * age + 0.15 * allergies
        return int(round(score * 100))
