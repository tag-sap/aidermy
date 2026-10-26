"""Free HTML extraction providers for product pages.

HTTPX + Beautiful Soup is the cheap first pass. Crawl4AI is an optional
browser-backed fallback for pages whose product/INCI data is rendered by JS.
Neither provider invents a product or ingredients: if the page has no reliable
product name, the caller simply tries the next provider.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from .models import ProductImportResult

logger = logging.getLogger(__name__)

_VOLUME = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:ml|мл|g|гр|г|oz)\b", re.I)
_INCI_LABEL = re.compile(
    r"(?:ingredients?|inci|состав|ингредиенты)\s*[:\-]?\s*(.{0,12000})",
    re.I | re.S,
)
_INCI_START = re.compile(r"\b(?:aqua|water|deionized\s+water|snail\s+secretion)\b", re.I)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
    return value or None


def _json_ld_records(soup: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            parsed = json.loads(node.get_text() or "")
        except Exception:
            continue
        values = parsed if isinstance(parsed, list) else (
            parsed.get("@graph", [parsed]) if isinstance(parsed, dict) else []
        )
        records.extend(item for item in values if isinstance(item, dict))
    return records


def _product_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in records:
        types = record.get("@type", [])
        types = types if isinstance(types, list) else [types]
        if "Product" in types or (record.get("name") and ("offers" in record or "brand" in record)):
            return record
    return {}


def _brand(value: Any) -> str | None:
    if isinstance(value, dict):
        return _text(value.get("name"))
    return _text(value)


def _inci_from_text(text: str) -> str | None:
    match = _INCI_LABEL.search(text)
    if not match:
        return None
    candidate = match.group(1)
    candidate = re.split(
        r"\b(?:details|how to use|benefits|highlights|read more|"
        r"описание|применение|отзывы)\b",
        candidate,
        maxsplit=1,
        flags=re.I,
    )[0]
    candidate = _text(candidate)
    if not candidate or not _INCI_START.search(candidate):
        return None
    parts = [part.strip(" .;•") for part in candidate.split(",") if part.strip(" .;•")]
    if len(parts) < 2 or any(len(part) > 120 for part in parts):
        return None
    return ", ".join(parts[:120])


def extract_html_product(html: str, url: str) -> ProductImportResult:
    """Extract only fields present in the document; never synthesize INCI."""
    if not html:
        return ProductImportResult(source_url=url)
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        return ProductImportResult(source_url=url)

    soup = BeautifulSoup(html, "html.parser")
    records = _json_ld_records(soup)
    record = _product_record(records)
    offers = record.get("offers") if isinstance(record.get("offers"), dict) else {}
    og_title = soup.select_one('meta[property="og:title"]')
    og_image = soup.select_one('meta[property="og:image"]')
    og_site = soup.select_one('meta[property="og:site_name"]')
    name = _text(record.get("name")) or _text(og_title.get("content") if og_title else "")
    image = record.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    image = _text(image) or _text(og_image.get("content") if og_image else "")
    if image and not str(image).startswith(("http://", "https://")):
        image = urljoin(url, str(image))
    page_text = " ".join(
        filter(None, [
            _text(soup.get_text(" ", strip=True)),
            _text(record.get("description")),
        ])
    )
    inci = _inci_from_text(page_text)
    volume = _VOLUME.search(page_text)
    return ProductImportResult(
        name=name,
        brand=_brand(record.get("brand")) or _text(og_site.get("content") if og_site else ""),
        manufacturer=_text(record.get("manufacturer")),
        image_url=image,
        price=offers.get("price") if isinstance(offers.get("price"), (int, float)) else None,
        currency=_text(offers.get("priceCurrency")),
        volume=volume.group(0) if volume else None,
        category=_text(record.get("category")),
        description=_text(record.get("description")),
        ingredients_raw=inci,
        source_url=url,
    )


async def fetch_http(url: str) -> ProductImportResult:
    """Fast HTTPX pass for server-rendered pages."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=8.0),
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Aidermy/1.0)"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        from .extractors import ProductPageBlocked, is_blocked_page

        if is_blocked_page(response.text):
            raise ProductPageBlocked("blocked page")
        return extract_html_product(response.text, url)


async def fetch_crawl4ai(url: str) -> ProductImportResult:
    """Optional JS-rendering pass. Import is lazy so the app still works without it."""
    try:
        from crawl4ai import AsyncWebCrawler  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Crawl4AI is not installed") from exc
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
    html = getattr(result, "html", None) or ""
    if not html:
        raise RuntimeError("Crawl4AI returned no HTML")
    return extract_html_product(html, url)
