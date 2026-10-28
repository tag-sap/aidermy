"""Поиск минимальной достоверной цены продукта.

Источники — только уже существующий стек проекта: органический поиск
(``product_identification.search_web_urls``: локальный SearXNG → DuckDuckGo HTML)
и обычные страницы магазинов с микроразметкой Product/Offer. Никаких новых
сервисов и API-ключей.

Правила:
* цена берётся только из структурированных данных страницы (JSON-LD Offer,
  ``itemprop=price``, ``product:price:amount``) — не из «примерно 1000 ₽» в тексте;
* страница должна относиться к тому же бренду и названию, а объём — совпадать
  с объёмом продукта; пробники, миниатюры и наборы отбрасываются;
* если достоверной цены нет — возвращается ``found=False`` (никаких выдуманных
  значений);
* результат кэшируется в ``product_prices`` вместе с источником и датой проверки.
"""
from __future__ import annotations

import asyncio
import json
import time as _time
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

import httpx

from .database import AIDERMY_DB, get_connection

logger = logging.getLogger(__name__)

PRICE_CACHE_TTL_HOURS = int(os.getenv("PRICE_CACHE_TTL_HOURS", "168"))
# Отрицательный результат («цена не найдена») кэшируем меньше: цена могла просто
# не найтись из-за таймаута конкретной страницы.
PRICE_NEGATIVE_TTL_HOURS = int(os.getenv("PRICE_NEGATIVE_TTL_HOURS", "24"))
PRICE_FETCH_TIMEOUT = float(os.getenv("PRICE_FETCH_TIMEOUT", "7"))
PRICE_MAX_PAGES = int(os.getenv("PRICE_MAX_PAGES", "4"))
# Общий бюджет одного поиска: карточка в колоде не должна ждать минуту.
PRICE_LOOKUP_BUDGET = float(os.getenv("PRICE_LOOKUP_BUDGET", "10"))
PRICE_SEARCH_LIMIT = int(os.getenv("PRICE_SEARCH_LIMIT", "6"))

# Магазины, где цена обычно лежит в микроразметке. Порядок — приоритет обхода.
SHOP_HOSTS = (
    "goldapple.ru",
    "letu.ru",
    "podrygka.ru",
    "rivezire.ru",
    "ozon.ru",
    "wildberries.ru",
    "apteka.ru",
    "sephora.ru",
)

_SAMPLE_MARKERS = (
    "пробник", "миниатюр", "мини ", "mini ", "miniature", "sample", "sachet", "саше",
    "travel size", "дорожн", "тестер", "tester", "deluxe", "подарочный набор",
    "travel set", "набор из", "set of",
)

_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|мл|g|гр|г|oz|fl\.?\s*oz)\b", re.I)
_PRICE_CLEAN_RE = re.compile(r"[^\d,.]")
_CURRENCY_RUB = {"rub", "rur", "₽", "руб", "руб.", "russian ruble"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _parse_iso(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_volume(text: str) -> Optional[Dict[str, Any]]:
    """Возвращает объём в миллилитрах (для граммов принята плотность 1)."""
    raw = str(text or "")
    match = _VOLUME_RE.search(raw)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    unit = match.group(2).lower().replace(" ", "")
    if unit in {"ml", "мл"}:
        ml = value
    elif unit in {"g", "гр", "г"}:
        ml = value
    elif unit in {"oz", "fl.oz", "floz"}:
        ml = value * 29.5735
    else:
        return None
    if ml <= 0:
        return None
    return {"label": match.group(0).strip(), "ml": round(ml, 2)}


def _looks_like_sample(text: str, volume_ml: Optional[float]) -> bool:
    low = f" {str(text or '').lower()} "
    if any(marker in low for marker in _SAMPLE_MARKERS):
        return True
    # Полноразмерные средства для лица начинаются примерно с 15 мл/г.
    if volume_ml is not None and volume_ml < 15:
        return True
    return False


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^0-9a-zа-яё]+", str(value or "").lower())
        if len(token) > 2
    }


def _clean_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        price = float(value)
    else:
        text = _PRICE_CLEAN_RE.sub("", str(value)).replace(",", ".")
        try:
            price = float(text)
        except ValueError:
            return None
    if price <= 0 or price > 1_000_000:
        return None
    return round(price, 2)


def _currency_is_rub(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return not text or text in _CURRENCY_RUB


def _json_ld_products(html: str) -> list[dict[str, Any]]:
    """Достаёт Product/ProductGroup из JSON-LD без новых зависимостей."""
    found: list[dict[str, Any]] = []
    for raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html or "",
        re.S | re.I,
    ):
        payload = raw.strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except Exception:  # noqa: BLE001 - битая разметка не должна ломать поиск
            continue
        stack: list[Any] = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
            types = node.get("@type")
            type_list = types if isinstance(types, list) else [types]
            if any(str(item).lower() in {"product", "productgroup"} for item in type_list if item):
                found.append(node)
    return found


def _offer_price(record: dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    offers = record.get("offers")
    candidates: Iterable[Any] = offers if isinstance(offers, list) else [offers]
    for offer in candidates:
        if not isinstance(offer, dict):
            continue
        for key in ("price", "lowPrice", "highPrice"):
            price = _clean_price(offer.get(key))
            if price:
                return price, str(offer.get("priceCurrency") or "")
    return None, None


def _meta_price(html: str) -> tuple[Optional[float], Optional[str]]:
    patterns = (
        r'<meta[^>]+property=["\']product:price:amount["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:price:amount["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+itemprop=["\']price["\'][^>]+content=["\']([^"\']+)',
        r'<[^>]+itemprop=["\']price["\'][^>]+content=["\']([^"\']+)',
    )
    currency_match = re.search(
        r'<meta[^>]+(?:property|itemprop)=["\'](?:product:price:currency|priceCurrency)["\'][^>]+content=["\']([^"\']+)',
        html or "",
        re.I,
    )
    currency = currency_match.group(1) if currency_match else None
    for pattern in patterns:
        match = re.search(pattern, html or "", re.I)
        if match:
            price = _clean_price(match.group(1))
            if price:
                return price, currency
    return None, currency


def _page_title(html: str) -> str:
    for pattern in (
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r"<title[^>]*>(.*?)</title>",
    ):
        match = re.search(pattern, html or "", re.S | re.I)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return ""


def _page_brand(records: Iterable[dict[str, Any]], html: str) -> str:
    for record in records:
        brand = record.get("brand")
        value = brand.get("name") if isinstance(brand, dict) else brand
        if value and str(value).strip():
            return str(value).strip()
    match = re.search(
        r'<meta[^>]+(?:property|itemprop)=["\'](?:product:brand|og:brand)["\'][^>]+content=["\']([^"\']+)',
        html or "",
        re.I,
    )
    return match.group(1).strip() if match else ""


def extract_price_from_html(html: str, url: str) -> Optional[dict[str, Any]]:
    """Возвращает найденную цену с провенансом или None (без догадок)."""
    records = _json_ld_products(html)
    price: Optional[float] = None
    currency: Optional[str] = None
    for record in records:
        price, currency = _offer_price(record)
        if price:
            break
    if not price:
        price, currency = _meta_price(html)
    if not price or not _currency_is_rub(currency):
        return None

    title = _page_title(html)
    description = ""
    match = re.search(
        r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']+)',
        html or "",
        re.I,
    )
    if match:
        description = match.group(1)
    volume = parse_volume(f"{title} {description}")
    return {
        "price": price,
        "currency": "RUB",
        "volume": volume["label"] if volume else "",
        "volume_ml": volume["ml"] if volume else None,
        "title": title,
        "brand": _page_brand(records, html),
        "source_url": url,
    }


_GENERIC_TOKENS = {
    "cream", "serum", "toner", "tonic", "lotion", "mask", "gel", "foam", "shampoo",
    "cleanser", "cleansing", "balm", "spray", "oil", "essence", "ampoule", "fluid",
    "emulsion", "professional", "laboratories", "laboratory", "cosmetics", "care",
    "the", "and", "for", "with", "spf", "plus", "new",
    "крем", "сыворотка", "тоник", "тонер", "лосьон", "маска", "гель", "пенка",
    "шампунь", "бальзам", "спрей", "масло", "эссенция", "ампула", "флюид", "эмульсия",
    "профессиональный", "профессиональная", "лаборатория", "косметика", "уход", "для",
}


def _matches_product(
    product: Dict[str, Any],
    candidate: dict[str, Any],
    *,
    brand: str,
    name: str,
) -> bool:
    """Отсекает чужие товары, пробники, миниатюры и наборы."""
    title = f"{candidate.get('title') or ''} {candidate.get('brand') or ''}".strip()
    haystack = title.lower()
    if not haystack:
        return False

    # Бренд сверяем по отличительным словам: «Professional»/«Laboratories» —
    # служебные и в заголовках магазинов часто опускаются.
    if brand:
        brand_tokens = _tokens(brand) - _GENERIC_TOKENS
        if brand_tokens and not any(token in haystack for token in brand_tokens):
            return False
    name_tokens = _tokens(name)
    if name_tokens:
        matched = sum(1 for token in name_tokens if token in haystack)
        distinctive = name_tokens - _GENERIC_TOKENS
        # Название может быть переведено («Couperose Intensive Cream» →
        # «Интенсивный крем с куперозом»), поэтому достаточно либо 60% слов,
        # либо одного отличительного слова (модель/линейка).
        if matched / len(name_tokens) < 0.6 and not any(token in haystack for token in distinctive):
            return False

    page_volume_ml = candidate.get("volume_ml")
    if _looks_like_sample(title, page_volume_ml):
        return False

    product_volume = parse_volume(str(product.get("volume") or ""))
    if product_volume and page_volume_ml:
        # Объём страницы должен совпадать с объёмом продукта (±15%).
        if abs(page_volume_ml - product_volume["ml"]) / product_volume["ml"] > 0.15:
            return False
    return True


def _shop_priority(url: str) -> int:
    host = (urlparse(url).hostname or "").lower()
    for index, shop in enumerate(SHOP_HOSTS):
        if host == shop or host.endswith("." + shop):
            return index
    return len(SHOP_HOSTS)


async def _fetch_html(url: str) -> str:
    from .product_identification import _WEBSEARCH_UA

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(PRICE_FETCH_TIMEOUT, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": _WEBSEARCH_UA, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.6"},
    ) as client:
        response = await client.get(url)
    if response.status_code != 200:
        return ""
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return ""
    return response.text[:400_000]


# -- cache ------------------------------------------------------------------
def ensure_price_table() -> None:
    conn = get_connection(AIDERMY_DB)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS product_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL UNIQUE,
                price REAL,
                currency TEXT DEFAULT '',
                volume TEXT DEFAULT '',
                volume_ml REAL,
                source_url TEXT DEFAULT '',
                source_title TEXT DEFAULT '',
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _read_cache(product_id: int) -> Optional[dict[str, Any]]:
    try:
        ensure_price_table()
        conn = get_connection(AIDERMY_DB)
        try:
            row = conn.execute(
                "SELECT * FROM product_prices WHERE product_id = ?", (int(product_id),)
            ).fetchone()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - кэш не должен ломать выдачу
        return None
    if not row:
        return None
    data = dict(row)
    checked = _parse_iso(data.get("checked_at"))
    ttl = PRICE_CACHE_TTL_HOURS if data.get("price") is not None else PRICE_NEGATIVE_TTL_HOURS
    if checked and _now() - checked > timedelta(hours=ttl):
        return None
    return data


def _write_cache(product_id: int, price: Optional[dict[str, Any]]) -> None:
    try:
        ensure_price_table()
        conn = get_connection(AIDERMY_DB)
        try:
            conn.execute("DELETE FROM product_prices WHERE product_id = ?", (int(product_id),))
            conn.execute(
                "INSERT INTO product_prices "
                "(product_id, price, currency, volume, volume_ml, source_url, source_title, checked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(product_id),
                    (price or {}).get("price"),
                    (price or {}).get("currency", ""),
                    (price or {}).get("volume", ""),
                    (price or {}).get("volume_ml"),
                    (price or {}).get("source_url", ""),
                    (price or {}).get("title", ""),
                    _cache_iso(_now()),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PRICE] cache write failed: %s", exc)


def _public(payload: dict[str, Any]) -> dict[str, Any]:
    price = payload.get("price")
    volume_ml = payload.get("volume_ml")
    found = price is not None
    return {
        "product_id": int(payload.get("product_id") or 0),
        "found": found,
        "price": price,
        "currency": payload.get("currency") or "RUB",
        "volume": payload.get("volume") or "",
        "volume_ml": volume_ml,
        "price_per_ml": round(float(price) / float(volume_ml), 2) if found and volume_ml else None,
        "source_url": payload.get("source_url") or "",
        "source_title": payload.get("source_title") or "",
        "checked_at": payload.get("checked_at") or _cache_iso(_now()),
    }


def product_search_names(product: Dict[str, Any]) -> tuple[str, str]:
    """Бренд и название без служебных переносов строк."""
    from .shelf_service import _split_name

    brand, name = _split_name(product.get("name") or "")
    brand = (product.get("brand") or brand or "").strip()
    return brand, (name or "").strip()


async def lookup_price(product: Dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Ищет минимальную достоверную цену и кэширует её вместе с источником."""
    product_id = int(product.get("id") or 0)
    if not product_id:
        return _public({"product_id": 0, "price": None})

    if not force:
        cached = _read_cache(product_id)
        if cached:
            return _public({**cached, "product_id": product_id})

    from .product_identification import search_web_urls

    brand, name = product_search_names(product)
    if not name:
        _write_cache(product_id, None)
        return _public({"product_id": product_id, "price": None})

    volume_label = str(product.get("volume") or "").strip()
    query = " ".join(part for part in (brand, name, volume_label, "цена купить") if part)
    urls = await search_web_urls(query, limit=PRICE_SEARCH_LIMIT)
    # Сначала крупные магазины, но если их страницы без разметки (SPA/антибот),
    # продолжаем обход остальных результатов — иначе цена теряется.
    ordered = sorted(urls, key=_shop_priority)

    best: Optional[dict[str, Any]] = None
    deadline = _time.monotonic() + PRICE_LOOKUP_BUDGET
    for index, url in enumerate(ordered):
        remaining = deadline - _time.monotonic()
        if remaining <= 0.5:
            logger.info("[PRICE] lookup budget exceeded (product=%s)", product_id)
            break
        if index >= PRICE_MAX_PAGES:
            if best is not None:
                break
            if index >= PRICE_MAX_PAGES + 3:
                break
        try:
            html = await asyncio.wait_for(
                _fetch_html(url), timeout=min(PRICE_FETCH_TIMEOUT, max(1.0, remaining))
            )
        except Exception as exc:  # noqa: BLE001 - одна страница не должна ломать поиск
            logger.info("[PRICE] fetch failed %s: %s", url, exc)
            continue
        if not html:
            continue
        candidate = extract_price_from_html(html, url)
        if not candidate:
            continue
        if not _matches_product(product, candidate, brand=brand, name=name):
            continue
        if best is None or candidate["price"] < best["price"]:
            best = candidate

    if best is None:
        _write_cache(product_id, None)
        logger.info("[PRICE] product=%s not found", product_id)
        return _public({"product_id": product_id, "price": None})

    payload = {
        "product_id": product_id,
        "price": best["price"],
        "currency": "RUB",
        "volume": best.get("volume") or "",
        "volume_ml": best.get("volume_ml"),
        "source_url": best.get("source_url", ""),
        "source_title": best.get("title", ""),
        "checked_at": _cache_iso(_now()),
    }
    _write_cache(product_id, best)
    logger.info("[PRICE] product=%s price=%s source=%s", product_id, best["price"], best.get("source_url"))
    return _public(payload)


_locks: Dict[int, asyncio.Lock] = {}
# Колода запрашивает цены пачкой; ограничиваем число одновременных поисков,
# чтобы один worker не выстраивал длинную очередь.
_search_semaphore = asyncio.Semaphore(2)


async def lookup_price_locked(product: Dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Один сетевой поиск на продукт одновременно."""
    product_id = int(product.get("id") or 0)
    lock = _locks.setdefault(product_id, asyncio.Lock())
    async with lock:
        async with _search_semaphore:
            return await lookup_price(product, force=force)
