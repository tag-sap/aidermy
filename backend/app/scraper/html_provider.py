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
from urllib.parse import urljoin, urlparse

import httpx

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None  # type: ignore[assignment]

from .extractors import (
    UnsupportedPageFormat,
    _brand_from_domain,
    _ingredients_from_jsonld,
    is_blocked_page,
)
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
_NAME_NOISE = re.compile(
    r"^(?:главная(?:\s+страница)?|каталог|корзина|избранное|сравнение|"
    r"личный\s+кабинет|войти|войдите|зарегистрир|ваша\s+учетная|выход|"
    r"регистрация|поиск|меню|доставка|оплата|о\s+компании|контакты|"
    r"home|shop|cart|account|login|search|menu)\b",
    re.I,
)
_PRODUCT_HINT = re.compile(
    r"(?:маск|крем|сыворот|тонер|тоник|эмульс|гель|пенк|бальзам|лосьон|"
    r"шампун|кондиционер|патч|пэд|скраб|пилинг|spf|масло|эссенц|ампул|"
    r"cream|serum|toner|mask|gel|cleanser|balm|lotion|shampoo|conditioner|"
    r"patch|pad|scrub|peel|oil|essence|ampoule)",
    re.I,
)
_CATEGORY_TITLES = re.compile(
    r"^(?:маски|патчи|пэды|кремы|сыворотки|очищение|тонизирование|"
    r"уход\s+для\s+лица|уход\s+за\s+лицом|специальный\s+уход)$",
    re.I,
)
_IMAGE_EXT = re.compile(r"\.(?:jpe?g|png|webp|avif)(?:[?#][^\s\"'<>]*)?$", re.I)
_IMAGE_SKIP = re.compile(
    r"(?:logo|sprite|favicon|icon|placeholder|loader|spinner|pixel|"
    r"tracking|payment|visa|mastercard|telegram|vk|chat-bubble|yandex|"
    r"mail\.ru)",
    re.I,
)


def _name_from_slug(url: str) -> str | None:
    """Human-readable fallback from a product URL path, not a confirmed fact."""
    try:
        path = urlparse(url).path
    except ValueError:
        return None
    segment = next(
        (part for part in reversed([p for p in path.split("/") if p]) if not part.isdigit()),
        "",
    )
    if not segment:
        return None
    from urllib.parse import unquote

    text = unquote(segment)
    text = re.sub(r"^\d+[\-_]+", "", text)  # technical ID prefix: 896-
    text = re.sub(r"\.(?:html?|php|aspx)$", "", text, flags=re.I)
    text = re.sub(r"[\-_]+", " ", text)
    text = _text(text)
    if not text or len(text) < 3 or len(text) > 180:
        return None
    # A slug is lowercase/latin-transliterated; keep it recognizable but do not
    # pretend it is the exact brand capitalization from the page.
    words = [word[:1].upper() + word[1:] if word.islower() else word for word in text.split()]
    return " ".join(words)


def _name_candidate(value: str | None) -> str | None:
    text = _clean_title(value)
    if not text or len(text) < 3 or len(text) > 220:
        return None
    if _NAME_NOISE.search(text) or _CATEGORY_TITLES.fullmatch(text):
        return None
    if text.lower() in {"все товары", "подробнее", "купить", "добавить в корзину"}:
        return None
    return text


def _heading_name(soup: Any) -> tuple[str | None, str | None]:
    candidates: list[tuple[int, int, str]] = []
    for index, node in enumerate(soup.select("h1, h2")):
        text = _name_candidate(node.get_text(" ", strip=True))
        if not text:
            continue
        score = 0
        if _PRODUCT_HINT.search(text):
            score += 4
        if len(text) >= 8:
            score += 2
        if _CATEGORY_TITLES.fullmatch(text):
            score -= 3
        if text.count(" ") >= 1:
            score += 1
        candidates.append((score, -index, text))
    if not candidates:
        return None, None
    candidates.sort(reverse=True)
    return candidates[0][2], "heading"


def _embedded_name(normalized_html: str) -> str | None:
    patterns = (
        r'"(?:productName|product_name|productTitle)"\s*:\s*"([^"\\]{3,220})"',
        r'"product"\s*:\s*\{[^{}]{0,2500}?"name"\s*:\s*"([^"\\]{3,220})"',
        r'"(?:name|title)"\s*:\s*"([^"\\]{3,220})"',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized_html, re.I | re.S):
            value = _name_candidate(match.group(1))
            if value and (
                _PRODUCT_HINT.search(value)
                or "productName" in pattern
                or "product_name" in pattern
            ):
                return value
    return None


def _site_brand(soup: Any, url: str, title_values: list[str]) -> str | None:
    for selector, attr in (
        ('meta[property="og:site_name"]', "content"),
        ('meta[name="application-name"]', "content"),
        ('meta[name="product:brand"]', "content"),
        ('meta[property="product:brand"]', "content"),
    ):
        node = soup.select_one(selector)
        value = _brand(node.get(attr) if node else None)
        if value:
            return value
    for title in title_values:
        parts = re.split(r"\s+[|—–-]\s+", title, maxsplit=1)
        if len(parts) == 2:
            candidate = _brand(parts[0])
            if candidate and len(candidate) <= 60 and not _PRODUCT_HINT.search(candidate):
                return candidate
    return _brand_from_domain(url)


def _absolute_image(
    value: str | None, url: str, *, require_extension: bool = True
) -> str | None:
    text = _text(value)
    if not text or text.startswith("data:"):
        return None
    absolute = urljoin(url, text)
    try:
        parsed = urlparse(absolute)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if _IMAGE_SKIP.search(absolute):
        return None
    if require_extension and not _IMAGE_EXT.search(parsed.path):
        return None
    return absolute


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
    # Product pages often put a JavaScript/HTML fragment immediately after the
    # INCI text (OpenCart/Angiopharm did: ``... <!-- $('#product-product'``).
    # It is not an ingredient and must not become part of the composition hash.
    candidate = re.split(r"<!--|<script\b|</?[a-z][^>]*>", candidate, maxsplit=1, flags=re.I)[0]
    candidate = re.split(
        r"\b(?:window\.|document\.|jQuery|\$\(|var\s+[A-Za-z_$]|function\s*\()",
        candidate,
        maxsplit=1,
        flags=re.I,
    )[0]
    candidate = re.split(
        r"\b(?:регион\s+доставки|доставка|оплата|каталог\s+товаров|"
        r"личный\s+кабинет|о\s+компании|контакты|способы\s+оплаты)\b",
        candidate,
        maxsplit=1,
        flags=re.I,
    )[0]
    candidate = _text(candidate)
    if not candidate:
        return None
    # The label may be a section heading followed by marketing copy before the
    # actual list ("Состав ... АКМЕЛЛА ... AQUA, ..."). Start at the first INCI
    # token instead of discarding the whole section.
    start = _INCI_START.search(candidate)
    if start:
        candidate = candidate[start.start():]
    parts = [part.strip(" .;•") for part in candidate.split(",") if part.strip(" .;•")]
    valid: list[str] = []
    for part in parts:
        if len(part) > 120 or any(
            marker in part for marker in ("{", "}", '"', "\\", "<!--", "<")
        ):
            # A page footer/JS fragment starts here; keep the INCI prefix that
            # was already recognised instead of dropping the whole composition.
            break
        valid.append(part)
    if len(valid) < 2:
        return None
    # OpenCart often leaves a close-button/quantity glyph after the last
    # ingredient ("SODIUM PHOSPHATE X"). Strip a trailing standalone glyph.
    valid[-1] = re.sub(r"\s+[A-Za-zА-Яа-я×x]$", "", valid[-1]).strip(" .;•")
    if len(valid[-1]) < 2:
        valid.pop()
    if len(valid) < 2:
        return None
    return ", ".join(valid[:160])


def _clean_title(value: str | None) -> str | None:
    title = _text(value)
    if not title:
        return None
    title = title.replace("`", "").replace('"', "")
    title = _SITE_TITLE_SUFFIX.sub("", title).strip(" -—–|")
    # OpenCart/retailer titles often read "Brand - купить Product in City".
    title = re.sub(
        r"^.{0,60}?\s[-—–]\s*(?:купить|заказать)\s+",
        "",
        title,
        flags=re.I,
    )
    title = re.sub(r"^(?:купить|заказать)\s+", "", title, flags=re.I)
    title = re.sub(r"\s+в\s+(?:москве|новосибирске|россии)\s*$", "", title, flags=re.I)
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


def _embedded_image(normalized_html: str, url: str) -> str | None:
    """Read a product image from Next.js/RSC-like escaped JSON."""
    patterns = (
        r'"(?:imageUrl|image_url|imageURL)"\s*:\s*"([^"\\]{8,500})"',
        r'"image"\s*:\s*"((?:https?:)?//[^"\\]{8,500})"',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized_html, re.I):
            value = _absolute_image(match.group(1), url, require_extension=False)
            if value:
                return value
    return None


def _image_from_html(
    soup: Any, normalized_html: str, url: str, product_name: str | None = None
) -> tuple[str | None, str | None]:
    """Choose a product image, preferring metadata and product-context DOM.

    Relative OpenCart/retailer paths such as ``/image/catalog/products/AG20.jpg``
    are valid product images. The old absolute-URL-only regex dropped them and
    the UI then displayed a mock image.
    """
    candidates: list[tuple[int, str, str]] = []
    for meta in soup.select(
        'meta[property="og:image"], meta[property="og:image:url"], '
        'meta[name="twitter:image"], meta[name="twitter:image:src"]'
    ):
        value = _absolute_image(meta.get("content"), url, require_extension=False)
        if value:
            candidates.append((10, value, "metadata"))

    name_words = {
        word.lower()
        for word in re.findall(r"[a-zA-Zа-яА-Я0-9]{4,}", product_name or "")
    }
    for image in soup.select("img"):
        attrs = " ".join(
            str(image.get(key) or "")
            for key in ("src", "data-src", "data-large_image", "data-original", "srcset", "alt", "title", "class")
        )
        raw = (
            image.get("data-large_image")
            or image.get("data-src")
            or image.get("data-original")
            or image.get("src")
            or (str(image.get("srcset") or "").split(",")[0].strip().split(" ")[0])
        )
        value = _absolute_image(raw, url)
        if not value:
            continue
        lowered = attrs.lower()
        score = 0
        if _PRODUCT_HINT.search(lowered):
            score += 3
        if any(word in lowered for word in name_words):
            score += 3
        if "product" in lowered:
            score += 2
        if any(marker in lowered for marker in ("logo", "sprite", "icon", "favicon", "placeholder")):
            score -= 8
        candidates.append((score, value, "dom"))

    for match in _IMAGE_URL.finditer(normalized_html):
        value = _absolute_image(match.group(0), url)
        if value:
            candidates.append((1, value, "html"))

    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates and candidates[0][0] > 0:
        return candidates[0][1], candidates[0][2]
    return None, None


def _title_candidates(soup: Any) -> list[str]:
    values: list[str] = []
    for selector in ('meta[property="og:title"]', 'meta[name="twitter:title"]', "title", "h1"):
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
    # Name provenance, in priority order. A slug is only a last-resort label and
    # is explicitly marked as such in the result.
    title_values = _title_candidates(soup)
    heading_name, _ = _heading_name(soup)
    name = _clean_title(_text(record.get("name")))
    name_source = "json_ld" if name else None
    if not name:
        name = _embedded_name(normalized_html)
        name_source = "embedded_json" if name else None
    if not name:
        name = heading_name or next(
            (candidate for candidate in title_values if _name_candidate(candidate)),
            None,
        )
        name_source = "heading" if name == heading_name else ("metadata" if name else None)
    if not name:
        name = _name_from_slug(url)
        name_source = "slug" if name else None

    image = record.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    image = _absolute_image(str(image) if image else None, url, require_extension=False)
    image_source = "json_ld" if image else None
    if not image:
        image = _embedded_image(normalized_html, url)
        image_source = "embedded_json" if image else None
    if not image:
        image, image_source = _image_from_html(soup, normalized_html, url, name)

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
    brand = _brand(record.get("brand"))
    brand_source = "json_ld" if brand else None
    if not brand:
        brand = _embedded_brand(normalized_html)
        brand_source = "embedded_json" if brand else None
    if not brand:
        brand = _text(record.get("brandName"))
        brand_source = "json_ld" if brand else None
    if not brand:
        brand = _site_brand(soup, url, title_values)
        brand_source = "metadata" if brand else None
    return ProductImportResult(
        name=name,
        brand=brand,
        manufacturer=_text(record.get("manufacturer")),
        image_url=image,
        price=offers.get("price") if isinstance(offers.get("price"), (int, float)) else None,
        currency=_text(offers.get("priceCurrency")),
        volume=volume.group(0) if volume else None,
        category=_text(record.get("category")),
        description=description,
        ingredients_raw=inci,
        source_url=url,
        name_source=name_source,
        brand_source=brand_source,
        image_source=image_source,
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
