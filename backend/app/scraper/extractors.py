import json
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from .models import ProductImportResult

_BLOCKED_PAGE_MARKERS = (
    "checking device",
    "just a moment",
    "access denied",
    "enable javascript",
    "включите javascript",
    "проверка устройства",
    "captcha",
)


class ProductPageBlocked(Exception):
    """Страница вернула антибот/JS-заглушку вместо карточки товара."""


class UnsupportedPageFormat(Exception):
    """URL отдал не HTML-документ (JSON/PDF/картинку и т.п.)."""


def is_blocked_page(text: str | None) -> bool:
    haystack = (text or "").lower()
    return any(marker in haystack for marker in _BLOCKED_PAGE_MARKERS)


_INGREDIENT_LABELS = re.compile(
    r"(?:ingredients?|inci|состав|ингредиенты)\s*[:\-]?\s*(.{0,8000})",
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
# Next.js/SPA: {"name":"Product Ingredients","value":["Snail Secretion Filtrate"," Betaine", ...]}.
_JSON_LIST_INCI = re.compile(
    r'"name"\s*:\s*"(?:product\s+)?(?:ingredients?|состав|ингредиенты)"\s*,\s*"value"\s*:\s*\[(.*?)\]',
    re.IGNORECASE | re.DOTALL,
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


# Известные официальные домены брендов → canonical brand name.
# Fallback для определения brand, когда страница (например, официальный сайт бренда)
# не содержит brand в JSON-LD/meta/title. НЕ считаем любой домен автоматически брендом.
_BRAND_DOMAINS: dict[str, str] = {
    "theordinary.com": "The Ordinary",
    "deciem.com": "The Ordinary",
    "cosrx.com": "COSRX",
    "laroche-posay.com": "La Roche-Posay",
    "larocheposay.com": "La Roche-Posay",
    "cerave.com": "CeraVe",
    "paulaschoice.com": "Paula's Choice",
    "clinique.com": "Clinique",
    "kiehls.com": "Kiehl's",
    "lorealparis.com": "L'Oréal Paris",
    "loreal.com": "L'Oréal",
    "vichy.com": "Vichy",
    "bioderma.com": "Bioderma",
    "avene.com": "Avène",
    "eucerin.com": "Eucerin",
    "neutrogena.com": "Neutrogena",
    "olaplex.com": "Olaplex",
    "skinceuticals.com": "SkinCeuticals",
    "angiopharm.com": "AngioPharm",
    "angiofarm.ru": "AngioPharm",
}


def _brand_from_domain(source_url: str) -> str | None:
    """Возвращает brand по известному официальному домену (иначе None — не выдумываем)."""
    try:
        host = (urlparse(source_url).hostname or "").rstrip(".").lower()
    except Exception:
        return None
    if not host:
        return None
    if host in _BRAND_DOMAINS:
        return _BRAND_DOMAINS[host]
    for domain, brand in _BRAND_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return brand
    return None


def _name_from_slug(source_url: str) -> str | None:
    """Readable, explicitly-unconfirmed fallback from the product URL path."""
    try:
        path = urlparse(source_url).path
    except ValueError:
        return None
    segment = next(
        (part for part in reversed([p for p in path.split("/") if p]) if not part.isdigit()),
        "",
    )
    if not segment:
        return None
    text = unquote(segment)
    text = re.sub(r"^\d+[\-_]+", "", text)
    text = re.sub(r"\.(?:html?|php|aspx)$", "", text, flags=re.I)
    text = re.sub(r"[\-_]+", " ", text)
    text = _text(text)
    if not text or len(text) < 3 or len(text) > 180:
        return None
    return " ".join(
        word[:1].upper() + word[1:] if word.islower() else word
        for word in text.split()
    )


def _dom_image(page: Any, source_url: str, product_name: str | None) -> str | None:
    """Best product-context <img>, including relative OpenCart paths."""
    name_words = {
        word.lower()
        for word in re.findall(r"[a-zA-Zа-яА-Я0-9]{4,}", product_name or "")
    }
    candidates: list[tuple[int, str]] = []
    for raw in page.css("img::attr(src)").getall() + page.css("img::attr(data-src)").getall():
        value = _text(raw)
        if not value or value.startswith("data:"):
            continue
        absolute = urljoin(source_url, value)
        lowered = absolute.lower()
        if any(
            marker in lowered
            for marker in ("logo", "sprite", "icon", "favicon", "placeholder", "loader", "yandex", "mail.ru")
        ):
            continue
        score = 0
        if any(word in lowered for word in name_words):
            score += 3
        if "/product" in lowered or "product/" in lowered:
            score += 2
        if re.search(r"\.(?:jpe?g|png|webp)(?:[?#]|$)", lowered):
            score += 1
        candidates.append((score, absolute))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1] if candidates[0][0] > 0 else None


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


def _extract_inci_candidate(raw: str) -> str | None:
    """Превращает текст после «Ingredients»-метки в список INCI.

    INCI не всегда начинается с Water/Aqua (например, «Snail Secretion Filtrate, ...»),
    поэтому признак — список через запятую из КОРОТКИХ ингредиентов (≤4 слов), а не
    стартовое слово. Маркетинговый текст/описание отсекается по длинным элементам.
    """
    if not raw:
        return None
    candidate = re.split(r"\.\s*[^.]{0,80}?перейти в каталог бренда", raw, maxsplit=1, flags=re.IGNORECASE)[0]
    # Конец секции состава — пустая строка (следующая секция описания/применения).
    candidate = re.split(r"\n\s*\n", candidate, maxsplit=1)[0]
    candidate = _text(candidate)
    if not candidate:
        return None
    parts = [p.strip() for p in candidate.split(",") if p.strip()]
    if len(parts) < 3:
        return None
    if not (20 <= len(candidate) <= 8000):
        return None
    # JSON/JS-бандл — не состав (кавычки/скобки/escape).
    if any(ch in candidate for ch in ('"', '{', '}', '\\')):
        return None
    # Ингредиент — короткое название (до 4 слов); длинные элементы = это предложение.
    if any(len(p.split()) > 4 for p in parts):
        return None
    return candidate


def _jsonld_ingredients_value(value: Any) -> str | None:
    """Превращает JSON-LD значение (str/list/dict) в INCI-строку."""
    if isinstance(value, str):
        return _extract_inci_candidate(value)
    if isinstance(value, list):
        parts = [p for p in (_text(x) for x in value) if p]
        if len(parts) >= 3:
            joined = ", ".join(parts)
            return _extract_inci_candidate(joined) or joined
        return None
    if isinstance(value, dict):
        return _jsonld_ingredients_value(value.get("value"))
    return None


def _ingredients_from_jsonld(record: dict[str, Any]) -> str | None:
    """Извлекает INCI из JSON-LD: поле ingredients или additionalProperty (Product Ingredients)."""
    ingredients = record.get("ingredients")
    if ingredients is not None:
        found = _jsonld_ingredients_value(ingredients)
        if found:
            return found

    for prop in record.get("additionalProperty") or []:
        if not isinstance(prop, dict):
            continue
        name = _text(prop.get("name")) or ""
        if re.search(r"(?:ingredients?|состав|ингредиенты)", name, re.IGNORECASE):
            found = _jsonld_ingredients_value(prop.get("value"))
            if found:
                return found
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
            candidate = _extract_inci_candidate(match.group(1) if match else value)
            if candidate:
                return candidate

    # Состав в JSON-структуре (Next.js/SPA): {"name":"Состав","value":"Water, ..."}.
    for m in _JSON_INCI.finditer(body_text):
        candidate = _text(m.group(1))
        if candidate and "," in candidate and len(candidate) >= 20:
            return candidate

    # Состав массивом строк: {"name":"Ingredients","value":["Snail Secretion Filtrate"," Betaine", ...]}.
    for m in _JSON_LIST_INCI.finditer(body_text):
        parts = [p.strip() for p in re.findall(r'"([^"]+)"', m.group(1)) if p.strip()]
        if len(parts) >= 3:
            candidate = _extract_inci_candidate(", ".join(parts))
            if candidate:
                return candidate

    for match in _INGREDIENT_LABELS.finditer(body_text):
        candidate = _extract_inci_candidate(match.group(1))
        if candidate:
            return candidate

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
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    source_image = urljoin(source_url, image) if image else None
    body_text = _text(" ".join(page.xpath("//body//text()").getall())) or ""
    if is_blocked_page(body_text) or is_blocked_page(_meta(page, "og:title")):
        raise ProductPageBlocked("Страница вернула проверку устройства/антибот-заглушку")

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
    name_source = "structured" if name else None
    if not name:
        name = _name_from_slug(source_url)
        name_source = "slug" if name else None
    description = _text(record.get("description")) or _meta(page, "og:description") or _dom_text(page, ['[itemprop="description"]', '[class*="description"]'])
    source_image = source_image or _meta(page, "og:image")
    if source_image:
        source_image = urljoin(source_url, source_image)
    image_source = "json_ld" if source_image else None
    if not source_image:
        source_image = _dom_image(page, source_url, name)
        image_source = "dom" if source_image else None
    ingredients = _ingredients_from_jsonld(record) or _ingredient_text(page, body_text)
    volume_match = _VOLUME.search(body_text)
    brand_value = (
        _clean_brand(
            _text(brand)
            or _meta(page, "product:brand")
            or _meta(page, "og:site_name")
            or _dom_text(page, ['[text="Бренд"] [class*="__title"]', '[class*="brand"] [class*="__title"]', '[itemprop="brand"]', '[class*="brand"]', '[class*="бренд"]'])
        )
        or _brand_from_domain(source_url)
    )

    return ProductImportResult(
        name=_clean_product_name(name),
        brand=brand_value,
        manufacturer=_text(record.get("manufacturer")),
        image_url=source_image,
        price=_safe_float(offers.get("price") if isinstance(offers, dict) else None) or _safe_float(_meta(page, "product:price")),
        currency=_text(offers.get("priceCurrency") if isinstance(offers, dict) else None) or _meta(page, "product:price:currency"),
        volume=volume_match.group(0) if volume_match else None,
        category=_text(record.get("category")) or _dom_text(page, ['[itemprop="category"]', '[class*="category"]']),
        description=description,
        ingredients_raw=ingredients,
        source_url=source_url,
        name_source=name_source,
        brand_source="structured" if brand_value else None,
        image_source=image_source,
    )
