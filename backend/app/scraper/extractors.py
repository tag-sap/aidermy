import json
import re
from typing import Any
from urllib.parse import urljoin

from .models import ProductImportResult

_INGREDIENT_LABELS = re.compile(
    r"(?:ingredients?|inci|состав|ингредиенты)\s*[:\-]?\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
_INCI_VALUE = re.compile(r"\b(?:aqua|water)\b\s*,\s*[^.]{8,}", re.IGNORECASE)
_INCI_START = re.compile(r"\b(?:deionized\s+water|aqua|water)\s*,", re.IGNORECASE)
_VOLUME = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:ml|мл|g|гр|г|oz|fl\.?\s*oz)\b", re.IGNORECASE)
# Next.js/SPA: состав часто лежит в JSON-объекте {"name":"Состав","value":"Water, ..."}.
# value экранируется как \"value\":\"...\", поэтому допускаем необязательный бэкслэш.
_JSON_INCI = re.compile(
    r'\\?"?value\\?"?\s*:\s*\\?"((?:Deionized Water|Aqua|Water)[^"\\]{8,})',
    re.IGNORECASE,
)


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


# Типичные заголовки UI входа/регистрации, которые иногда попадают в название товара.
_ACCOUNT_NOISE = re.compile(
    r"(?:войдите или создайте учетную запись|создание учетной записи|зарегистрировать учетную запись|ваша учетная запись создана!?|вход|выход)",
    re.IGNORECASE,
)


def _strip_leading_symbols(value: str) -> str:
    """Убирает знаки/скобки/кавычки/невидимые символы в начале названия."""
    t = (value or "").strip()
    # невидимые и служебные символы (object replacement, BOM, zero-width space)
    t = re.sub(r"^[\s\uFFFC\uFEFF\u200B]+", "", t)
    # скобочный префикс целиком: (Renewal), [BR], {X}
    t = re.sub(r"^[\[\(\{][^\]\)\}]{0,60}[\]\)\}]\s*", "", t)
    # кавычки/решётка/дефисы/тире/маркеры в начале
    t = re.sub(r"^[\"'\u2018\u2019\u201C\u201D\u201E\u00AB\u00BB#\-\u2014\u2013\u00B7\u2022]+", "", t)
    # любые оставшиеся не-буквенно-цифровые символы в начале
    t = re.sub(r"^[^\w]+", "", t, flags=re.UNICODE)
    return t.strip()


def _clean_product_name(value: str | None) -> str | None:
    if not value:
        return None
    value = _text(re.sub(r"^в наличии:\s*", "", value, flags=re.IGNORECASE))
    # Отрезаем «шум» из шапки аккаунта, если он слипся с названием.
    value = _text(_ACCOUNT_NOISE.sub(" ", value))
    # Убираем знаки/скобки/кавычки/невидимые символы в начале названия.
    value = _strip_leading_symbols(value)
    # Хвостовая цена (… 1 116 ₽) и дублированное название («X X») — типичный мусор карточек.
    while True:
        stripped = re.sub(r"\s+\d[\d\s\u00A0\u202F]*[₽$€£]\s*$", "", value)
        if stripped == value:
            break
        value = stripped
    value = value.strip()
    half = len(value) // 2
    if half > 0:
        left, right = value[:half].strip(), value[half:].strip()
        if left and left == right:
            value = left
    return value or None


def _clean_brand(value: str | None) -> str | None:
    cleaned = _text(value)
    if not cleaned:
        return None
    cleaned = re.split(r"\s+перейти в каталог бренда", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    words = cleaned.split()
    if len(words) > 1 and words[0].casefold() == words[1].casefold():
        cleaned = words[0]
    return cleaned


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group().replace(",", "."))
    except ValueError:
        return None


def _json_ld(page: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in page.css('script[type="application/ld+json"]::text').getall():
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        values = parsed if isinstance(parsed, list) else parsed.get("@graph", [parsed]) if isinstance(parsed, dict) else []
        records.extend(item for item in values if isinstance(item, dict))
    return records


def _product_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in records:
        types = record.get("@type", [])
        types = types if isinstance(types, list) else [types]
        if "Product" in types or record.get("name") and ("offers" in record or "brand" in record):
            return record
    return {}


def _meta(page: Any, name: str, attribute: str = "property") -> str | None:
    values = page.css(f'meta[{attribute}="{name}"]::attr(content)').getall()
    return _text(values[0] if values else None)


def _dom_text(page: Any, selectors: list[str]) -> str | None:
    for selector in selectors:
        values = page.css(selector).xpath(".//text()").getall()
        value = _text(" ".join(values))
        if value:
            return value
    return None


def _ingredient_text(page: Any, body_text: str) -> str | None:
    selectors = [
        '[text="Состав"]', '[value="Text_2"]',
        '[class*="ingredient"]', '[id*="ingredient"]', '[class*="inci"]', '[id*="inci"]',
        '[class*="состав"]', '[id*="состав"]',
    ]
    for selector in selectors:
        value = _dom_text(page, [selector])
        if value:
            match = _INGREDIENT_LABELS.search(value)
            candidate = match.group(1) if match else value
            inci_start = _INCI_START.search(candidate)
            if inci_start:
                candidate = candidate[inci_start.start():]
            candidate = re.split(r"\.\s*[^.]{0,80}?перейти в каталог бренда", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
            if "," in candidate and len(candidate) >= 20:
                return _text(candidate)

    # Состав в JSON-структуре (Next.js/SPA): {"name":"Состав","value":"Water, ..."}.
    for m in _JSON_INCI.finditer(body_text):
        candidate = _text(m.group(1))
        if candidate and "," in candidate and len(candidate) >= 20:
            return candidate

    match = _INGREDIENT_LABELS.search(body_text)
    if match:
        candidate = match.group(1).split("description", 1)[0]
        inci_start = _INCI_START.search(candidate)
        if inci_start:
            candidate = candidate[inci_start.start():]
        candidate = re.split(r"\.\s*[^.]{0,80}?перейти в каталог бренда", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
        if "," in candidate and len(candidate) >= 20:
            return _text(candidate)

    match = _INCI_VALUE.search(body_text)
    return _text(match.group(0)) if match else None


def extract_product(page: Any, source_url: str) -> ProductImportResult:
    records = _json_ld(page)
    record = _product_record(records)
    offers = record.get("offers") or {}
    offers = _first(offers) if isinstance(offers, list) else offers
    brand = record.get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else brand
    image = _first(record.get("image"))
    image = urljoin(source_url, image) if image else None
    body_text = _text(" ".join(page.xpath("//body//text()").getall())) or ""

    name = (
        _text(record.get("name"))
        or _meta(page, "og:title")
        or _dom_text(
            page,
            [
                '[class*="product-name"]',
                '[class*="product_name"]',
                'h1[itemprop="name"]',
                '[itemprop="name"]',
                '[class*="product"][class*="title"]',
                '[class*="product"][class*="name"]',
                "h1",
            ],
        )
    )
    description = _text(record.get("description")) or _meta(page, "og:description") or _dom_text(page, ['[itemprop="description"]', '[class*="description"]'])
    image = image or _meta(page, "og:image")
    if image:
        image = urljoin(source_url, image)
    ingredients = _text(record.get("ingredients")) or _ingredient_text(page, body_text)
    volume_match = _VOLUME.search(body_text)

    return ProductImportResult(
        name=_clean_product_name(name),
        brand=_clean_brand(_text(brand) or _meta(page, "product:brand") or _dom_text(page, ['[text="Бренд"] [class*="__title"]', '[class*="brand"] [class*="__title"]', '[itemprop="brand"]', '[class*="brand"]', '[class*="бренд"]'])),
        image_url=image,
        price=_safe_float(offers.get("price") if isinstance(offers, dict) else None) or _safe_float(_meta(page, "product:price")),
        currency=_text(offers.get("priceCurrency") if isinstance(offers, dict) else None) or _meta(page, "product:price:currency"),
        volume=volume_match.group(0) if volume_match else None,
        category=_text(record.get("category")) or _dom_text(page, ['[itemprop="category"]', '[class*="category"]']),
        description=description,
        ingredients_raw=ingredients,
        source_url=source_url,
    )
