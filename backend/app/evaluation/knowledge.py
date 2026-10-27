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
from urllib.parse import urlparse

from .contracts import sha256_of
from .documents import collect_source_urls
from .inci import looks_truncated, split_inci

_WS_RE = re.compile(r"\s+")

# Provenance that is strong enough to use an existing catalog INCI without asking
# an administrator to re-type it. This is deliberately narrow: a dedicated INCI
# database is a different class of source from an arbitrary product page.
TRUSTED_INCI_HOSTS = ("incidecoder.com",)


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


@dataclass(frozen=True)
class CompositionReadiness:
    """Whether the catalog INCI may be used, and what the user must do next.

    ``usable`` describes the data, not the status of a previous evaluation:
    a complete INCI from a trusted provenance can be used immediately even when
    the composition row has not been explicitly verified yet (``auto_verify``).
    """

    usable: bool
    reason: str
    action: str
    trust: str
    message: str
    source_host: str = ""
    auto_verify: bool = False

    def as_dict(self) -> dict:
        return {
            "usable": self.usable,
            "reason": self.reason,
            "action": self.action,
            "trust": self.trust,
            "message": self.message,
            "source_host": self.source_host,
            "auto_verify": self.auto_verify,
        }


def _trusted_inci_host(source: str) -> str:
    try:
        host = (urlparse(str(source or "").strip()).hostname or "").lower()
    except ValueError:
        return ""
    if not host:
        return ""
    for trusted in TRUSTED_INCI_HOSTS:
        if host == trusted or host.endswith("." + trusted):
            return host
    return ""


def assess_composition(
    product: Mapping | None,
    composition: Mapping | None,
    *,
    status: str = "",
) -> CompositionReadiness:
    """Split "INCI exists" from "INCI is trustworthy enough to analyse".

    Rules:
      * empty or single-token INCI is never usable;
      * truncated lists are not usable;
      * an already ``active`` composition is usable (it was explicitly verified);
      * a complete INCI from a trusted INCI database is usable automatically and
        should be recorded as verified;
      * a complete INCI from any other source stays unverified until its source
        is checked — a non-empty string alone never proves the formula.
    """
    product = product or {}
    composition = composition or {}
    inci_raw = str(composition.get("inci_raw") or product.get("ingredients") or "").strip()
    tokens = split_inci(inci_raw)
    source = str(composition.get("source") or product.get("url") or "").strip()
    host = _trusted_inci_host(source)

    if not inci_raw:
        return CompositionReadiness(
            usable=False,
            reason="missing",
            action="provide_inci",
            trust="none",
            message=(
                "В карточке нет состава, поэтому оценка невозможна. "
                "Добавьте INCI или укажите источник состава."
            ),
        )
    if len(tokens) < 2 or looks_truncated(inci_raw):
        return CompositionReadiness(
            usable=False,
            reason="incomplete",
            action="provide_inci",
            trust="incomplete",
            source_host=host,
            message=(
                f"Состав в карточке неполный: найдено {len(tokens)} ингредиент(а). "
                "Нужен полный INCI, иначе оценка будет недостоверной."
            ),
        )
    if str(status or "") == "active":
        return CompositionReadiness(
            usable=True,
            reason="confirmed",
            action="none",
            trust="confirmed",
            source_host=host,
            message="Состав подтверждён и пригоден для оценки.",
        )
    if str(status or "") == "superseded":
        return CompositionReadiness(
            usable=False,
            reason="superseded",
            action="check_source",
            trust="unverified",
            source_host=host,
            message=(
                "Эта версия состава помечена как устаревшая. Проверьте актуальный состав "
                "по источнику, прежде чем оценивать продукт."
            ),
        )
    # A user who scans or manually enters a product explicitly confirms the
    # composition when pressing "save and check". Such a card may have no URL
    # (the normal case for a newly added product), so requiring a retailer
    # source would make the check impossible. This is a user confirmation, not
    # an automatically trusted third-party source: the label stays visible in
    # the report and the composition record is stamped accordingly.
    if str(product.get("source_type") or "").strip().lower() in {
        "scan",
        "manual",
        "ocr",
        "user",
    }:
        return CompositionReadiness(
            usable=True,
            reason="user_confirmed",
            action="none",
            trust="user_confirmed",
            source_host=host,
            auto_verify=True,
            message=(
                "Состав введён или подтверждён пользователем. Он используется для "
                "персональной проверки; при сомнении сверьте его с упаковкой."
            ),
        )
    if host:
        return CompositionReadiness(
            usable=True,
            reason="trusted_catalog",
            action="none",
            trust="trusted_catalog",
            source_host=host,
            auto_verify=True,
            message=(
                f"Состав взят из карточки каталога, источник — доверенная база INCI "
                f"{host}. Его можно использовать без повторного подтверждения."
            ),
        )
    return CompositionReadiness(
        usable=False,
        reason="untrusted_source" if source else "source_missing",
        action="check_source",
        trust="unverified",
        source_host=host,
        message=(
            "Состав есть, но его происхождение не подтверждено. "
            "Проверьте состав по источнику; если источник недоступен, подтверждение выполняет администратор."
            if source
            else "Состав есть, но у карточки нет источника. Укажите источник и проверьте состав; при недоступном источнике нужен администратор."
        ),
    )


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
    raw_name = str(product.get("name") or "")
    name_parts = [part.strip() for part in raw_name.split("\n") if part.strip()]
    display_name = " ".join(name_parts[1:]) if len(name_parts) >= 2 else raw_name.strip()
    brand = str(product.get("brand") or "").strip()
    if not brand and len(name_parts) >= 2:
        brand = name_parts[0]
    return ProductKnowledge(
        product={
            "id": int(product.get("id") or product_id),
            "name": display_name,
            "brand": brand,
            "url": str(product.get("url") or product.get("incidecoder_url") or ""),
            # Functional classification must use the catalog category/type as
            # evidence. Keeping only the display name discarded the reliable
            # "Очищение" signal for products such as Bioderma Créaline.
            "category": str(product.get("category") or "").strip(),
            "subcategory": str(product.get("subcategory") or "").strip(),
            "taxonomy_category": str(product.get("taxonomy_category") or "").strip(),
            # The catalog pair is the trusted purpose classification. Keep it
            # in the analysis payload instead of reducing the product to its
            # display name and legacy category.
            "catalog_category": str(product.get("catalog_category") or "").strip(),
            "catalog_subcategory": str(product.get("catalog_subcategory") or "").strip(),
            "description": str(product.get("description") or "").strip(),
            "source_type": str(product.get("source_type") or "").strip().lower(),
            "has_reliable_inci": len(_inci_tokens(inci_raw)) >= 2,
        },
        composition=composition,
        source_urls=source_urls,
        notes=tuple(notes),
    )
