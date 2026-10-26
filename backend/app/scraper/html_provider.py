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

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None  # type: ignore[assignment]

from .extractors import UnsupportedPageFormat, _ingredients_from_jsonld, is_blocked_page
from .models import ProductImportResult

logger = logging.getLogger(__name__)

_VOLUME = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:ml|мл|g|гр|г|oz)\b", re.I)
_INCI_LABEL = re.compile(
    r"(?:ingredients?|inci|состав|ингредиенты)\s*[:\-]?\s*(.{0,12000})",
    re.I | re.S,
)
_INCI_START = re.compile(r"\b(?:aqua|water|deionized\s+water|snail\s+secretion)\b", re.I)
_IMAGE_URL = re.compile(r"https?://[^\"'\\\s]+?\.(?:jpe?g|png|webp)(?:\?[^\"'\\\s]*)?", re.I)
_SITE_TITLE_SUFFIX = re.compile(
    r"\s*(?:\||—|–|\s-\s)\s*(?:official|home|shop|store|online|магазин|"
    r"купить|каталог|gold apple|podrygka|wildberries|ozon)\s*$",
    re.I,
)


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
        value = value.get("name")
    text = _text(value)
    if not text:
        return None
    # Retailer metadata often appends the site role: "COSRX official".
    return _text(re.sub(r"\s+(?:official(?:\s+(?:site|store|shop))?|site|store|shop)\s*$", "", text, flags=re.I))


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


def _clean_title(value: str | None) -> str | None:
    title = _text(value)
    if not title:
        return None
    title = title.replace("`", "").replace('"', "")
    title = _SITE_TITLE_SUFFIX.sub("", title).strip(" -—–|")
    return _text(title)


def _visible_text(soup: Any) -> str:
    """Body text without scripts/styles/noscript (anti-bot words live there)."""
    visible = BeautifulSoup(str(soup), "html.parser")
    for tag in visible(["script", "style", "noscript", "template"]):
        tag.decompose()
    return _text(visible.get_text(" ", strip=True)) or ""


def is_blocked_html(html: str) -> bool:
    """Detect a challenge page without scanning bundled JavaScript.

    Shopify/Next.js bundles routinely contain words like ``captcha`` or
    ``access denied`` in analytics and error handlers. Scanning the raw HTML
    produced false positives and forced every healthy page into a slow browser
    fallback. Only the title and visible text are authoritative here.
    """
    if not html or BeautifulSoup is None:
        return False
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    visible = _visible_text(soup)
    probe = f"{title} {visible[:5000]}"
    return is_blocked_page(probe)


def _flatten_embedded_json(html: str) -> str:
    """Expose Next.js/RSC escaped JSON as normal quoted JSON for regexes.

    The page is used read-only. We only normalize quote escaping; we never
    execute scripts or construct data.
    """
    return html.replace('\\\\"', '"').replace('\\"', '"')


def _embedded_inci(normalized_html: str) -> str | None:
    """Read INCI from JSON-like ``{"name":"Состав","value":"Water, ..."}``."""
    patterns = (
        r'"name"\s*:\s*"(?:состав|ingredients?|ингредиенты)"\s*,\s*'
        r'(?:"description"\s*:\s*[^,}]{0,80}\s*,\s*)?'
        r'(?:"filterValue"\s*:\s*[^,}]{0,80}\s*,\s*)?'
        r'"value"\s*:\s*"([^"]{10,12000})"',
        r'"composition"\s*:\s*\{[^{}]{0,800}?"value"\s*:\s*"([^"]{10,12000})"',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized_html, re.I | re.S):
            candidate = _text(match.group(1))
            if not candidate:
                continue
            cleaned = _clean_embedded_inci(candidate)
            if cleaned:
                return cleaned
    return None


def _clean_embedded_inci(value: str) -> str | None:
    """Validate a composition value from page JSON without guessing.

    Botanical INCI names can legitimately contain more than four words, so the
    stricter marketing-text heuristic from ``extractors`` is not suitable for
    an explicit ``composition.value`` field. We still require a comma-separated
    list, a reasonable length and no JSON/markup fragments.
    """
    candidate = _text(value)
    if not candidate or not (20 <= len(candidate) <= 8000):
        return None
    if any(char in candidate for char in ('"', "{", "}", "\\")):
        return None
    parts = [part.strip(" .;•") for part in candidate.split(",") if part.strip(" .;•")]
    if len(parts) < 3 or any(len(part) > 140 or len(part.split()) > 10 for part in parts):
        return None
    starts_like_inci = bool(_INCI_START.search(" ".join(parts[:3])))
    if not starts_like_inci and len(parts) < 5:
        return None
    return ", ".join(parts[:160])


def _embedded_brand(normalized_html: str) -> str | None:
    patterns = (
        r'"brand"\s*:\s*\{[^{}]{0,800}?"value"\s*:\s*"([^"]{1,80})"',
        r'"brand"\s*:\s*\{[^{}]{0,800}?"name"\s*:\s*"([^"]{1,80})"',
        r'"brand(?:Name)?"\s*:\s*"([^"]{1,80})"',
    )
    for pattern in patterns:
        match = re.search(pattern, normalized_html, re.I | re.S)
        if not match:
            continue
        value = _text(match.group(1))
        if value and value.lower() not in {"brand", "бренд"}:
            return _brand(value)
    return None


def _embedded_description(normalized_html: str) -> str | None:
    match = re.search(r'"description"\s*:\s*"([^"]{10,2000})"', normalized_html, re.I)
    if not match:
        return None
    value = match.group(1).replace("\\\\n", " ").replace("\\n", " ")
    return _text(value)


def _image_from_html(soup: Any, normalized_html: str, url: str) -> str | None:
    candidates = [
        _text(meta.get("content"))
        for meta in soup.select('meta[property="og:image"], meta[name="twitter:image"]')
    ]
    candidates.extend(
        _text(match.group(0)) for match in _IMAGE_URL.finditer(normalized_html)
    )
    for value in candidates:
        if not value:
            continue
        lowered = value.lower()
        if any(marker in lowered for marker in ("logo", "sprite", "icon", "favicon", "placeholder")):
            continue
        return urljoin(url, value)
    return None


def _title_candidates(soup: Any) -> list[str]:
    values: list[str] = []
    for selector in ("h1", 'meta[property="og:title"]', "title"):
        if selector.startswith("meta"):
            node = soup.select_one(selector)
            value = node.get("content") if node else None
        else:
            node = soup.select_one(selector)
            value = node.get_text(" ", strip=True) if node else None
        value = _clean_title(value)
        if value and value not in values:
            values.append(value)
    return values


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
    normalized_html = _flatten_embedded_json(html)

    page_text = " ".join(
        filter(None, [
            _visible_text(soup),
            _text(record.get("description")),
            _embedded_description(normalized_html),
        ])
    )
    # A <title>/<h1> is often the only product name on a server-rendered page
    # (many retailers do not emit JSON-LD). Prefer JSON-LD, then h1/title.
    title_values = _title_candidates(soup)
    name = _text(record.get("name")) or (title_values[0] if title_values else None)
    name = _clean_title(name)

    image = record.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    image = _text(image)
    if image and not str(image).startswith(("http://", "https://")):
        image = urljoin(url, str(image))
    image = image or _image_from_html(soup, normalized_html, url)

    inci = (
        _ingredients_from_jsonld(record)
        or _embedded_inci(normalized_html)
        or _inci_from_text(page_text)
    )
    volume = _VOLUME.search(page_text)
    description = (
        _text(record.get("description"))
        or _embedded_description(normalized_html)
    )
    return ProductImportResult(
        name=name,
        brand=(
            _brand(record.get("brand"))
            or _embedded_brand(normalized_html)
            or _text(record.get("brandName"))
        ),
        manufacturer=_text(record.get("manufacturer")),
        image_url=image,
        price=offers.get("price") if isinstance(offers.get("price"), (int, float)) else None,
        currency=_text(offers.get("priceCurrency")),
        volume=volume.group(0) if volume else None,
        category=_text(record.get("category")),
        description=description,
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
        content_type = (response.headers.get("content-type") or "").lower()
        if content_type and not any(
            marker in content_type for marker in ("text/html", "application/xhtml+xml")
        ):
            raise UnsupportedPageFormat(content_type)
        from .extractors import ProductPageBlocked

        if is_blocked_html(response.text):
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
