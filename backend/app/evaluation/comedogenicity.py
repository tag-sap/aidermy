"""Conservative, separate assessment of a formula's comedogenic potential.

This is deliberately not a personal-compatibility parameter and is never added
to the compatibility average. The available ingredient records contain a 0..5
comedogenicity field without concentration data, so this module:

  * reports every confirmed ingredient rating in 1..5, even when overall INCI
    coverage is low;
  * never turns one flagged ingredient into a product-level diagnosis;
  * never invents a numeric score or a safe/unsafe claim for unknown tokens;
  * hides the user-facing block when no confirmed rating in 1..5 exists;
  * returns ``not_applicable`` only for products for which the property has no
    meaningful interpretation (for example fragrance).

A rating of 0 is not used as proof of safety. It is retained only in the
diagnostic counts. The 1..5 scale is the catalog's existing comedogenicity
field; values outside it are ignored rather than rescaled or mixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .inci import split_inci

COMEDOGENICITY_VERSION = "2.0.0"


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
    ingredients: tuple[dict[str, Any], ...] = ()
    max_rating: float | None = None
    risk_label: str = ""
    # Diagnostics: resolved in the catalog vs. actually carrying a confirmed
    # comedogenicity record. ``known_count < resolved_count < total_count`` is
    # normal and is never interpreted as evidence of safety or harm.
    total_count: int = 0
    resolved_count: int = 0
    known_count: int = 0
    flagged_count: int = 0
    coverage: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        verdict = (
            "not_applicable" if not self.applicable
            else "unknown" if self.status != "assessed"
            else "caution" if self.flagged_count
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
            "ingredients": list(self.ingredients),
            "max_rating": self.max_rating,
            "risk_label": self.risk_label,
            "total_count": self.total_count,
            "resolved_count": self.resolved_count,
            "known_count": self.known_count,
            "flagged_count": self.flagged_count,
            "coverage": self.coverage,
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
    ingredients: Sequence[Mapping[str, Any]] = (),
    max_rating: float | None = None,
    risk_label: str = "",
    total_count: int = 0,
    resolved_count: int = 0,
    known_count: int = 0,
    flagged_count: int = 0,
    coverage: float = 0.0,
) -> ComedogenicityAssessment:
    return ComedogenicityAssessment(
        status=status,
        applicable=applicable,
        level=level,
        reason=reason,
        risk=risk,
        recommendation=recommendation,
        basis=tuple(dict(item) for item in basis),
        ingredients=tuple(dict(item) for item in ingredients),
        max_rating=max_rating,
        risk_label=risk_label,
        total_count=total_count,
        resolved_count=resolved_count,
        known_count=known_count,
        flagged_count=flagged_count,
        coverage=coverage,
    )


def _rating_text(value: float) -> str:
    """Stable 1..5 display without a trailing .0."""
    rounded = round(float(value), 1)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:g}"


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
            total_count=len(ingredients),
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
            total_count=len(ingredients),
        ).as_dict()

    records: list[tuple[str, float, Mapping[str, Any]]] = []
    confirmed_values: list[float] = []
    resolved = 0
    for ingredient in ingredients:
        try:
            row = ingredient_lookup(ingredient)
        except Exception:
            row = None
        if not row:
            continue
        resolved += 1
        try:
            rating = float(row.get("comedogenicity"))
        except (TypeError, ValueError):
            continue
        evidence = str(row.get("evidence_level") or "").casefold()
        # A default 0 without evidence is not a confirmed “not comedogenic”.
        # Only the catalog's existing 0..5 scale is accepted; values from a
        # different scale are not rescaled or mixed into this result.
        if evidence not in {"high", "strong", "moderate"}:
            continue
        if rating < 0 or rating > 5:
            continue
        if rating == 0:
            try:
                confidence = float(row.get("knowledge_confidence") or 0)
            except (TypeError, ValueError):
                confidence = 0.0
            if evidence in {"", "missing", "unknown"} or confidence <= 0:
                continue
            confirmed_values.append(rating)
            continue
        confirmed_values.append(rating)
        records.append((str(ingredient), rating, row))

    total = len(ingredients)
    known = len(confirmed_values)
    flagged = len(records)
    coverage = known / total if total else 0.0
    max_rating = max((rating for _, rating, _ in records), default=None)
    counts = dict(
        total_count=total,
        resolved_count=resolved,
        known_count=known,
        flagged_count=flagged,
        coverage=round(coverage, 4),
    )

    if not records:
        # No confirmed rating in 1..5 means there is nothing to show. A safe-
        # looking zero-only record set is still not presented as a pseudo-
        # verdict, and unknown tokens never become evidence of safety.
        if known:
            return _result(
                "assessed",
                level="low",
                reason=(
                    "Подтверждённых рейтингов комедогенности 1–5 среди "
                    "сопоставленных компонентов нет. Это не доказывает "
                    "безопасность неизвестных компонентов."
                ),
                basis=[
                    {"label": "Проверено компонентов", "value": f"{known} из {total}"},
                    {"label": "Покрытие", "value": f"{coverage:.0%}"},
                ],
                **counts,
            ).as_dict()
        return _result(
            "insufficient_evidence",
            reason=(
                "Нет подтверждённых записей о комедогенности с известной "
                f"шкалой 0–5: сопоставлено {resolved} из {total} компонентов. "
                "Неизвестные компоненты не считаются ни безопасными, ни "
                "комедогенными."
            ),
            basis=[
                {"label": "Сопоставлено с каталогом", "value": f"{resolved} из {total}"},
                {"label": "Покрытие", "value": f"{coverage:.0%}"},
            ],
            **counts,
        ).as_dict()

    if max_rating is not None and max_rating >= 4:
        level = "high"
        risk_label = "Высокий потенциальный риск"
        risk_context = (
            "Максимальный подтверждённый рейтинг — 5-балльная шкала, "
            f"{_rating_text(max_rating)} из 5. Это серьёзный потенциальный "
            "сигнал, но не доказательство появления высыпаний у конкретного "
            "человека."
        )
    elif max_rating is not None and max_rating >= 3:
        level = "medium"
        risk_label = "Средний потенциальный риск"
        risk_context = (
            "Максимальный подтверждённый рейтинг — "
            f"{_rating_text(max_rating)} из 5. Это повод учесть контекст "
            "формулы, но не диагноз."
        )
    else:
        level = "low"
        risk_label = "Низкий потенциальный риск"
        risk_context = (
            "Максимальный подтверждённый рейтинг — "
            f"{_rating_text(max_rating or 0)} из 5. Это минимальный "
            "потенциальный сигнал, а не доказательство вреда."
        )

    listed = [
        {
            "name": name,
            "rating": round(rating, 1),
            "rating_label": f"{_rating_text(rating)}/5",
        }
        for name, rating, _ in sorted(records, key=lambda item: (-item[1], item[0].casefold()))
    ]
    rating_summary = "; ".join(
        f"{item['name']} — {item['rating_label']}" for item in listed
    )
    return _result(
        "assessed",
        level=level,
        reason=(
            "В составе подтверждены рейтинги комедогенности 1–5 у "
            f"{len(listed)} компонент(ов). Низкое покрытие состава не скрывает "
            "эти известные сведения; неизвестные компоненты не считаются ни "
            "безопасными, ни комедогенными."
        ),
        risk=(
            f"{risk_context} Рейтинг отдельного компонента не доказывает, что "
            "вся формула закупорит поры: концентрации и готовая формула не "
            "оценивались."
        ),
        recommendation=(
            "При склонности к закупорке пор учитывайте этот потенциальный риск "
            "и следите за реакцией кожи; при появлении высыпаний прекратите "
            "использование."
        ),
        basis=[
            {"label": "Подтверждённые рейтинги", "value": rating_summary},
            {"label": "Максимальный рейтинг", "value": f"{_rating_text(max_rating or 0)}/5"},
            {"label": "Шкала", "value": "0–5, поле комедогенности каталога"},
            {"label": "Проверено компонентов", "value": f"{known} из {total}"},
            {"label": "Покрытие", "value": f"{coverage:.0%}"},
        ],
        ingredients=listed,
        max_rating=round(max_rating, 1) if max_rating is not None else None,
        risk_label=risk_label,
        **counts,
    ).as_dict()

