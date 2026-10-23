"""Existing Aidermy product data as the starting knowledge of an analysis.

Nothing here is invented: the product record, its INCI and its links come from the
catalog database, and seed URLs for research also come from the ingredient
knowledge base (claims that already carry a `source_url`). The module never marks
a composition as verified on its own — verification is an explicit decision of the
caller, because an unverified INCI may not be the real formula.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from .contracts import sha256_of
from .documents import collect_source_urls

_WS_RE = re.compile(r"\s+")


class KnowledgeUnavailable(RuntimeError):
    """The product cannot be loaded from the Aidermy catalog."""


class ProductNotFound(KnowledgeUnavailable):
    """The requested product does not exist in the catalog."""


@dataclass(frozen=True)
class ProductKnowledge:
    """Product + composition + the URLs worth checking for this product."""

    product: dict
    composition: dict
    source_urls: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def composition_hash(self) -> str:
        return str(self.composition.get("composition_hash") or "")

    def as_dict(self) -> dict:
        return {
            "product": dict(self.product),
            "composition": dict(self.composition),
            "source_urls": list(self.source_urls),
            "notes": list(self.notes),
        }


def normalize_inci(inci_raw: str) -> str:
    """Canonical INCI string used for the composition hash."""
    text = str(inci_raw or "").replace(";", ",")
    parts = [_WS_RE.sub(" ", part).strip() for part in text.split(",")]
    return ", ".join(part for part in parts if part)


def composition_hash_for(inci_raw: str) -> str:
    """Stable identity of one formula version (same INCI -> same hash)."""
    return sha256_of({"inci": normalize_inci(inci_raw).casefold()})


def _inci_tokens(inci_raw: str) -> tuple[str, ...]:
    normalized = normalize_inci(inci_raw)
    if not normalized:
        return ()
    return tuple(part.strip().casefold() for part in normalized.split(",") if part.strip())


def ingredient_source_urls(
    inci_raw: str,
    *,
    repository=None,
    limit: int = 6,
) -> tuple[str, ...]:
    """Seed URLs from Aidermy's ingredient claims (already researched earlier).

    Failures are not fatal: a missing knowledge base simply means there are fewer
    starting points for research, not that the analysis may fabricate sources.
    """
    tokens = _inci_tokens(inci_raw)
    if not tokens:
        return ()
    try:
        if repository is None:
            from ..ingredient_repository import IngredientRepository

            repository = IngredientRepository()
        evidence = repository.get_goal_evidence_map(ingredients=list(tokens))
    except Exception:  # noqa: BLE001 - optional knowledge, never a hard dependency
        return ()
    urls: list[str] = []
    for claims in (evidence or {}).values():
        for claim in (claims or {}).values():
            url = str((claim or {}).get("source_url") or "").strip()
            if url and url not in urls:
                urls.append(url)
            if len(urls) >= limit:
                return tuple(urls)
    return tuple(urls)


def load_product_knowledge(
    product_id: int,
    *,
    product_loader: Callable[[int], Mapping | None] | None = None,
    repository=None,
    verified_at: str | None = None,
    composition_source: str | None = None,
    extra_sources: Iterable[str] = (),
    include_ingredient_sources: bool = True,
) -> ProductKnowledge:
    """Load a product from the Aidermy catalog and derive its composition record.

    ``verified_at`` is required to treat the INCI as confirmed; without it the
    composition stays unverified and research will refuse to run.
    """
    if product_loader is None:
        from ..database import get_product_by_id as product_loader  # type: ignore[no-redef]

    try:
        product = product_loader(int(product_id))
    except Exception as exc:  # noqa: BLE001 - catalog driver errors are data
        raise KnowledgeUnavailable(f"каталог недоступен: {exc}") from exc
    if not product:
        raise ProductNotFound(f"продукт {product_id} не найден в каталоге")

    notes: list[str] = []
    inci_raw = str(product.get("ingredients") or "").strip()
    if not inci_raw:
        notes.append(
            "У продукта нет сохранённого состава: анализ невозможен, пока состав не "
            "подтверждён."
        )
    source = str(
        composition_source
        or product.get("url")
        or product.get("incidecoder_url")
        or "catalog"
    )
    composition = {
        "composition_hash": composition_hash_for(inci_raw),
        "inci_raw": inci_raw,
        "source": source,
        "verified_at": str(verified_at or ""),
    }

    seeds: list[str] = []
    if include_ingredient_sources:
        seeds.extend(ingredient_source_urls(inci_raw, repository=repository))
    source_urls = collect_source_urls(
        product, {"source": source}, extra=tuple(seeds) + tuple(extra_sources)
    )
    return ProductKnowledge(
        product={
            "id": int(product.get("id") or product_id),
            "name": str(product.get("name") or ""),
        },
        composition=composition,
        source_urls=source_urls,
        notes=tuple(notes),
    )
