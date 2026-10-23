"""Deterministic INCI check for intolerance parameters.

What this module can and cannot prove (deliberate scope):

  * only a **verified** composition (``status == "active"``) with a non-empty,
    non-truncated INCI list is checked. An unverified composition, an empty list,
    a dangling separator or a single-token list is ``unverifiable``;
  * a *present* ingredient is a fact about the declared composition. It is **not**
    a medical conclusion about an individual reaction or its severity;
  * absence is decisive only for "closed" categories whose INCI naming is
    standardised (fragrance, niacinamide, ethanol). For "open" categories
    (essential oils, retinoids, acids) the dictionary below is partial, so
    absence yields ``unverifiable`` instead of a false "safe" claim;
  * even for closed categories the INCI list may be incomplete: absence means
    "not declared", never "no risk at all".

The dictionary is an explicit, reviewable subset of INCI names — not a clinical
knowledge base and not an invented synonym engine. Anything not listed here is
reported as unverifiable rather than guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .contracts import Parameter

PRESENT = "present"
NOT_LISTED = "not_listed"
UNVERIFIABLE = "unverifiable"

COVERAGE_CLOSED = "closed"
COVERAGE_OPEN = "open"
COVERAGE_UNKNOWN = "unknown"

# INCI names for each questionnaire intolerance category.
CATEGORY_INGREDIENTS: dict[str, tuple[str, ...]] = {
    # INCI requires Parfum/Fragrance/Aroma for an added fragrance.
    "fragrance_intolerance": ("parfum", "fragrance", "aroma"),
    # Ethanol and denatured alcohols. Fatty alcohols (cetyl/stearyl/...) are
    # different substances and are intentionally NOT matched.
    "alcohol_intolerance": (
        "alcohol denat",
        "alcohol denat.",
        "denatured alcohol",
        "ethanol",
        "ethyl alcohol",
        "isopropyl alcohol",
        "isopropanol",
        "sd alcohol 40",
        "sd alcohol 40-b",
    ),
    # Plant oils are an open list: absence is not provable with a partial list.
    "essential_oil_intolerance": (
        "lavandula angustifolia oil",
        "citrus limon peel oil",
        "citrus aurantium dulcis peel oil",
        "citrus bergamia peel oil",
        "mentha piperita oil",
        "eucalyptus globulus leaf oil",
        "rosmarinus officinalis leaf oil",
        "melaleuca alternifolia leaf oil",
        "pelargonium graveolens oil",
        "cananga odorata flower oil",
    ),
    # Retinoid INCI names are a growing family: absence is not provable.
    "retinoid_intolerance": (
        "retinol",
        "retinal",
        "retinaldehyde",
        "retinyl palmitate",
        "retinyl acetate",
        "retinyl retinoate",
        "tretinoin",
        "adapalene",
        "tazarotene",
        "isotretinoin",
        "hydroxypinacolone retinoate",
    ),
    # Exfoliating acids only; hyaluronic/ascorbic acid are not this category.
    "acid_intolerance": (
        "glycolic acid",
        "lactic acid",
        "salicylic acid",
        "malic acid",
        "tartaric acid",
        "mandelic acid",
        "citric acid",
        "gluconolactone",
        "lactobionic acid",
        "azelaic acid",
    ),
    "niacinamide_intolerance": ("niacinamide", "nicotinamide"),
}

# Categories whose INCI naming is standardised enough to treat absence as a fact.
CLOSED_CATEGORIES = frozenset(
    {"fragrance_intolerance", "alcohol_intolerance", "niacinamide_intolerance"}
)

_BRACKETS = re.compile(r"\([^)]*\)")
_NON_WORD = re.compile(r"[^0-9a-z]+")
_CYRILLIC = re.compile(r"[а-яё]")
_TRUNCATED_ENDINGS = ("...", "…", ",", ";", ":", " and", " &", " и", " +")


def normalize_inci_name(value: str) -> str:
    """Lowercase INCI token without parenthetical synonyms or punctuation."""
    text = _BRACKETS.sub(" ", str(value or "").casefold())
    text = text.replace("·", " ")
    text = _NON_WORD.sub(" ", text)
    return " ".join(text.split())


def split_inci(raw: str) -> list[str]:
    """Split INCI into ingredient tokens, keeping bracketed synonyms intact."""
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if char in ",;\n" and depth == 0:
            parts.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
    parts.append("".join(buffer))
    return [part.strip() for part in parts if part.strip()]


def looks_truncated(raw: str) -> bool:
    text = " ".join(str(raw or "").split()).casefold()
    return bool(text) and text.endswith(_TRUNCATED_ENDINGS)


@dataclass(frozen=True)
class InciCheck:
    parameter_id: str
    composition_hash: str
    status: str
    coverage: str = COVERAGE_UNKNOWN
    matched: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in (PRESENT, NOT_LISTED, UNVERIFIABLE):
            raise ValueError(f"unknown INCI check status: {self.status}")
        if self.coverage not in (COVERAGE_CLOSED, COVERAGE_OPEN, COVERAGE_UNKNOWN):
            raise ValueError(f"unknown INCI coverage: {self.coverage}")

    @property
    def verified(self) -> bool:
        return self.status in (PRESENT, NOT_LISTED)

    def as_dict(self) -> dict:
        return {
            "parameter_id": self.parameter_id,
            "composition_hash": self.composition_hash,
            "status": self.status,
            "coverage": self.coverage,
            "matched": list(self.matched),
            "reason": self.reason,
        }


def _target(parameter: Parameter) -> tuple[str, tuple[str, ...], str] | None:
    """Return (label, INCI names, coverage) for an intolerance parameter."""
    option_id = str(parameter.option_id or "")
    if option_id.startswith("ingredient:"):
        name = option_id.split(":", 1)[1].replace("_", " ").strip()
        if not name:
            return None
        if _CYRILLIC.search(name):
            # No Latin-script dictionary for a free-form Russian ingredient name.
            return (name, (), COVERAGE_UNKNOWN)
        return (name, (name,), COVERAGE_CLOSED)
    names = CATEGORY_INGREDIENTS.get(option_id)
    if not names:
        return None
    coverage = COVERAGE_CLOSED if option_id in CLOSED_CATEGORIES else COVERAGE_OPEN
    return (option_id, names, coverage)



def check_intolerance(
    parameter: Parameter,
    composition: Mapping | None,
) -> InciCheck | None:
    """Check an intolerance parameter against a verified composition.

    Returns ``None`` for parameters outside the ``intolerance`` section.
    """
    if parameter.section != "intolerance":
        return None

    composition_hash = str((composition or {}).get("composition_hash") or "")
    base = dict(
        parameter_id=parameter.id,
        composition_hash=composition_hash,
        coverage=COVERAGE_UNKNOWN,
    )
    target = _target(parameter)
    if target is None:
        return InciCheck(
            status=UNVERIFIABLE,
            reason="для этой категории нет проверяемого словаря INCI",
            **base,
        )
    label, names, coverage = target
    base["coverage"] = coverage

    if composition is None or not composition_hash:
        return InciCheck(
            status=UNVERIFIABLE,
            reason="состав не передан для проверки",
            **base,
        )
    status = str(composition.get("status") or "unverified")
    if status != "active":
        return InciCheck(
            status=UNVERIFIABLE,
            reason=f"состав не подтверждён (status={status})",
            **base,
        )
    raw = str(composition.get("inci_raw") or "")
    tokens = split_inci(raw)
    if not tokens:
        return InciCheck(
            status=UNVERIFIABLE,
            reason="INCI пуст: проверить наличие компонента невозможно",
            **base,
        )
    if looks_truncated(raw) or len(tokens) < 2:
        return InciCheck(
            status=UNVERIFIABLE,
            reason="INCI выглядит неполным: отсутствие компонента недоказуемо",
            **base,
        )
    if not names:
        return InciCheck(
            status=UNVERIFIABLE,
            reason=f"нет словаря INCI для «{label}»",
            **base,
        )

    aliases = {normalize_inci_name(name) for name in names}
    matched = tuple(
        dict.fromkeys(
            token
            for token in (normalize_inci_name(item) for item in tokens)
            if token in aliases
        )
    )
    if matched:
        return InciCheck(
            status=PRESENT,
            matched=matched,
            reason="компонент найден в подтверждённом составе",
            **base,
        )
    if coverage == COVERAGE_CLOSED:
        return InciCheck(
            status=NOT_LISTED,
            reason="компонент не заявлен в подтверждённом составе (INCI может быть неполным)",
            **base,
        )
    return InciCheck(
        status=UNVERIFIABLE,
        reason=(
            "словарь категории неполон: отсутствие компонента в составе не доказывает "
            "его отсутствие"
        ),
        **base,
    )

