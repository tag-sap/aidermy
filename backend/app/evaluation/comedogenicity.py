"""Conservative, separate assessment of a formula's comedogenic potential.

This is deliberately not a personal-compatibility parameter and is never added
to the compatibility average. The available ingredient records contain a 0..5
comedogenicity field without concentration data, so this module:

  * never turns one flagged ingredient into a product-level negative verdict;
  * never invents a numeric score;
  * returns ``insufficient_evidence`` when formula coverage is too low;
  * returns ``not_applicable`` only for products for which the property has no
    meaningful interpretation (for example fragrance).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .inci import split_inci

COMEDOGENICITY_VERSION = "1.0.0"
MIN_KNOWN_COVERAGE = 0.5


@dataclass(frozen=True)
class ComedogenicityAssessment:
    status: str
    applicable: bool
    level: str = "unknown"
    score: None = None
    reason: str = ""
    risk: str = ""
    recommendation: str = ""
    basis: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        verdict = (
            "not_applicable" if not self.applicable
            else "unknown" if self.status != "assessed"
            else "caution" if self.level in {"medium", "high"}
            else "positive"
        )
        return {
            "version": COMEDOGENICITY_VERSION,
            "status": self.status,
            "verdict": verdict,
            "applicable": self.applicable,
            "level": self.level,
            "score": self.score,
            "reason": self.reason,
            "risk": self.risk,
            "recommendation": self.recommendation,
            "basis": list(self.basis),
        }


def _result(
    status: str,
    *,
    applicable: bool = True,
    level: str = "unknown",
    reason: str,
    risk: str = "",
    recommendation: str = "",
    basis: Sequence[Mapping[str, Any]] = (),
) -> ComedogenicityAssessment:
    return ComedogenicityAssessment(
        status=status,
        applicable=applicable,
        level=level,
        reason=reason,
        risk=risk,
        recommendation=recommendation,
        basis=tuple(dict(item) for item in basis),
    )


def _is_fragrance(product: Mapping[str, Any]) -> bool:
    text = " ".join(
        str(product.get(key) or "") for key in ("name", "category", "subcategory")
    ).casefold()
    return any(
        marker in text
        for marker in ("парфюм", "parfum", "туалетная вода", "духи", "cologne", "perfume")
    )
def assess_comedogenicity(
    product: Mapping[str, Any] | None,
    composition: Mapping[str, Any] | None,
    *,
    ingredient_lookup: Callable[[str], Mapping[str, Any] | None] | None = None,
    composition_status: str = "active",
) -> dict[str, Any]:
    """Return a separate product-level assessment (never a personal score)."""
    product = product or {}
    composition = composition or {}
    if _is_fragrance(product):
        return _result(
            "not_applicable",
            applicable=False,
            reason="Комедогенность не оценивается для парфюмерной продукции.",
        ).as_dict()

    if str(composition_status or "") != "active":
        return _result(
            "insufficient_evidence",
            reason="Состав не подтверждён, поэтому комедогенный потенциал не оценивается.",
        ).as_dict()

    inci = str(composition.get("inci_raw") or product.get("ingredients") or "").strip()
    ingredients = split_inci(inci)
    if len(ingredients) < 2:
        return _result(
            "insufficient_evidence",
            reason="Недостаточно подтверждённого состава для оценки комедогенности.",
        ).as_dict()

    if ingredient_lookup is None:
        try:
            from ..ingredient_repository import IngredientRepository

            ingredient_lookup = IngredientRepository().resolve_ingredient
        except Exception:
            ingredient_lookup = None

    if ingredient_lookup is None:
        return _result(
            "insufficient_evidence",
            reason="Справочник ингредиентов недоступен; оценка комедогенности не построена.",
        ).as_dict()

    records: list[tuple[str, float, Mapping[str, Any]]] = []
    for ingredient in ingredients:
        try:
            row = ingredient_lookup(ingredient)
        except Exception:
            row = None
        if not row:
            continue
        try:
            rating = float(row.get("comedogenicity"))
        except (TypeError, ValueError):
            continue
        evidence = str(row.get("evidence_level") or "").casefold()
        confidence = float(row.get("knowledge_confidence") or 0)
        # A default 0 without evidence is not a confirmed “not comedogenic”.
        if rating <= 0 and (evidence in {"", "missing", "unknown"} or confidence <= 0):
            continue
        if evidence in {"missing", "unknown"}:
            continue
        records.append((str(ingredient), rating, row))

    known = len(records)
    coverage = known / len(ingredients)
    if known == 0 or coverage < MIN_KNOWN_COVERAGE:
        return _result(
            "insufficient_evidence",
            reason=(
                "Недостаточно проверенных данных о комедогенности компонентов "
                f"(подтверждено {known} из {len(ingredients)})."
            ),
        ).as_dict()

    high = [name for name, rating, _ in records if rating >= 4]
    medium = [name for name, rating, _ in records if 2 <= rating < 4]
    if not high and not medium:
        return _result(
            "assessed",
            level="low",
            reason=(
                "Среди проверенных компонентов формулы нет подтверждённых "
                "высоких или средних показателей комедогенности."
            ),
            basis=[
                {"label": "Проверено компонентов", "value": f"{known} из {len(ingredients)}"},
            ],
        ).as_dict()

    # One marked ingredient is not enough to call the whole formula comedogenic.
    if len(high) + len(medium) < 2:
        return _result(
            "insufficient_evidence",
            reason=(
                "В формуле есть отдельный компонент с потенциальной комедогенностью, "
                "но без концентрации и второго подтверждающего компонента нельзя "
                "обоснованно оценить всю формулу."
            ),
            basis=[
                {"label": "Компонент требует контекста", "value": (high + medium)[0]},
            ],
        ).as_dict()

    flagged = (high + medium)[:6]
    return _result(
        "assessed",
        level="medium" if len(high) + len(medium) >= 2 else "unknown",
        reason=(
            "В проверенной части формулы есть несколько компонентов с потенциальной "
            "комедогенностью. Это предупреждение о формуле, а не диагноз и не "
            "доказательство появления высыпаний у конкретного пользователя."
        ),
        risk=(
            "При склонности к закупорке пор теоретически возможна дополнительная "
            "нагрузка; концентрации компонентов в составе не указаны."
        ),
        recommendation=(
            "Если решите использовать продукт, проверьте переносимость на небольшом "
            "участке и следите за реакцией; при появлении высыпаний прекратите использование."
        ),
        basis=[
            {"label": "Проверено компонентов", "value": f"{known} из {len(ingredients)}"},
            {"label": "Компоненты для контекста", "value": ", ".join(flagged)},
        ],
    ).as_dict()

