# product_identification.py
# Оркестрация: фото продукта -> идентификация -> поиск в БД -> автоматический Web Search.
# Это orchestration/navigation layer: использует существующие scraper/vision_service/database.
from __future__ import annotations

import asyncio
import re
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from . import database
from .product_dedup import _MATCH_THRESHOLD, match_score

logger = logging.getLogger(__name__)

# Реалистичный User-Agent: DuckDuckGo возвращает 202 (антибот) для ботоподобных UA.
_WEBSEARCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# Маркеры рекламных результатов DuckDuckGo — их пропускаем (нужен органический URL).
_AD_MARKERS = ("ad_domain", "ad_provider", "doubleclick", "bing.com/aclick", "aclick")


def _normalize(s: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", (s or "").lower()).strip()


def find_product_candidates(brand: str, name: str, limit: int = 5) -> list[Dict[str, Any]]:
    """Возвращает ранжированные совпадения из Product DB.

    Один и тот же матчер (`product_dedup.match_score`), что и у каталога.
    Нужен, чтобы не выбирать случайный товар при нескольких похожих карточках.
    """
    if not brand and not name:
        return []

    query = {"brand": brand or "", "name": name or ""}
    conn = database.get_connection(database.PRODUCTS_DB)
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT id, name, slug, brand, image_url, category, ingredients, barcode, variant "
        "FROM products WHERE is_canonical = 1"
    ).fetchall()
    conn.close()

    scored: list[tuple[float, Dict[str, Any]]] = []
    for row in rows:
        row_dict = dict(row)
        score = match_score(query, row_dict)
        if score is None or score < _MATCH_THRESHOLD:
            continue
        scored.append((float(score), row_dict))

    scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
    brand_key = _normalize(str(brand or ""))
    if brand_key:
        # Общий токен вроде «calming» не должен вытаскивать чужие бренды.
        # Если бренда нет ни в одной строке, оставляем исходный рейтинг:
        # в старых записях бренд может храниться только внутри name.
        brand_matched = [
            item for item in scored
            if brand_key in _normalize(str(item[1].get("brand") or ""))
            or _normalize(str(item[1].get("name") or "")).startswith(brand_key)
        ]
        if brand_matched:
            scored = brand_matched

    result: list[Dict[str, Any]] = []
    for score, row in scored[: max(1, int(limit))]:
        raw_name = str(row.get("name") or "")
        parts = [part.strip() for part in raw_name.split("\n") if part.strip()]
        if len(parts) >= 2:
            display_brand = str(row.get("brand") or parts[0]).strip()
            display_name = " ".join(parts[1:])
        else:
            display_brand = str(row.get("brand") or "").strip()
            display_name = " ".join(raw_name.split())
        product = {
            "id": row.get("id"),
            "slug": row.get("slug") or "",
            "name": display_name,
            "brand": display_brand,
            "image_url": row.get("image_url") or "",
            "category": row.get("category") or "",
            "ingredients": row.get("ingredients") or "",
            "barcode": row.get("barcode") or "",
            "variant": row.get("variant") or "",
            "source_url": "",
            "match_score": round(score, 4),
        }
        product["has_inci"] = has_reliable_inci(product)
        result.append(product)
    return result


def find_product_in_db(brand: str, name: str) -> Optional[Dict[str, Any]]:
    """Ищет продукт в Product DB тем же механизмом, что и каталог (product_dedup.match_score).

    Переиспользует нормализацию каталога (normalize_name/normalize_brand внутри
    match_score): регистр, пробелы, дефисы, пунктуацию, транслитерацию, бренд + название.
    Не создаёт отдельный независимый алгоритм поиска.
    """
    candidates = find_product_candidates(brand, name, limit=1)
    return candidates[0] if candidates else None


def has_reliable_inci(product: Optional[Dict[str, Any]]) -> bool:
    """Достоверный INCI = непустая строка с несколькими ингредиентами."""
    if not product:
        return False
    ings = [x.strip() for x in (product.get("ingredients") or "").split(",") if x.strip()]
    return len(ings) >= 2


async def search_web_urls(query: str, *, limit: int = 10) -> list[str]:
    """Публичный органический поиск: возвращает только URL, без разбора INCI.

    Использует тот же DuckDuckGo HTML-механизм (UA, retry/backoff, фильтр
    рекламы), что и поиск карточки продукта. Нужен слою исследования Evaluation
    V2, чтобы находить дополнительные страницы, а не только известные ссылки.
    """
    query = " ".join(str(query or "").split())
    if not query:
        return []
    found: list[str] = []
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0), follow_redirects=True) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": _WEBSEARCH_UA},
                )
            if resp.status_code != 200:
                logger.warning("[WEBSEARCH] DuckDuckGo status=%s (attempt %d) query=%r", resp.status_code, attempt + 1, query)
                continue
            html = resp.text
            for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"', html):
                uddg = re.search(r"uddg=([^&]+)", m.group(1))
                if not uddg:
                    continue
                url = _unquote(uddg.group(1))
                low = url.lower()
                if any(marker in low for marker in _AD_MARKERS):
                    continue  # пропускаем рекламу
                if url not in found:
                    found.append(url)
                if len(found) >= limit:
                    break
            if found:
                break
            logger.warning("[WEBSEARCH] no organic URLs (attempt %d) query=%r", attempt + 1, query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[WEBSEARCH] search failed (attempt %d) query=%r: %s", attempt + 1, query, exc)
        if attempt < 2:
            await asyncio.sleep(1.5 * (attempt + 1))
    logger.info("[WEBSEARCH] query=%r -> %d urls", query, len(found))
    return found[: max(0, int(limit))]


async def _search_product_urls(brand: str, name: str, variant: Optional[str] = None) -> list[str]:
    """Ищет URL-кандидаты страницы продукта (best-effort, без API-ключа).

    Возвращает список органических URL в порядке релевантности. INCI из поисковой
    выдачи не извлекается — только URL. Пропускает рекламные результаты.
    """
    query = " ".join(x for x in (brand, name, variant) if x and x.strip()).strip()
    if not query:
        return []
    return await search_web_urls(query, limit=10)


async def _search_product_url(brand: str, name: str, variant: Optional[str] = None) -> Optional[str]:
    """Первый URL-кандидат (обратная совместимость с существующими тестами)."""
    urls = await _search_product_urls(brand, name, variant)
    return urls[0] if urls else None


def _unquote(s: str) -> str:
    try:
        from urllib.parse import unquote
        return unquote(s)
    except Exception:  # noqa: BLE001
        return s


def _is_matching_product(
    imported_brand: str,
    imported_name: str,
    brand: str,
    name: str,
    variant: Optional[str] = None,
) -> bool:
    """Проверяет, что найденная страница соответствует исходному Vision brand/name/variant.

    Не принимает первый попавшийся похожий товар и не смешивает INCI разных вариантов.
    """
    b = _normalize(brand)
    n = _normalize(name)
    ib = _normalize(imported_brand or "")
    inm = _normalize((imported_name or "").replace("\n", " "))

    if not n:
        return False
    # Название обязано пересекаться.
    if n not in inm and inm not in n:
        return False
    # Бренд, если он известен, обязан пересекаться.
    if b and (not ib or (b not in ib and ib not in b)):
        return False
    # Вариант: если Vision выделил отдельный вариант, он должен встречаться в названии
    # страницы (иначе рискуем взять INCI другого варианта).
    v = _normalize(variant or "")
    if v and v not in inm and v not in n:
        return False
    return True


_RETAIL_DOMAINS = (
    "goldapple.ru",
    "ozon.ru",
    "wildberries.ru",
    "letu.ru",
    "sephora",
    "iherb.",
    "amazon.",
    "notino.",
    "lookfantastic.",
)


def _prioritize_product_urls(urls: list[str], brand: str) -> list[str]:
    """Официальный сайт бренда → профильный каталог/продавец → остальные."""
    brand_key = _normalize(brand).replace(" ", "")

    def rank(url: str) -> int:
        host = (urlparse(url).hostname or "").lower()
        compact_host = host.replace("-", "").replace(".", "")
        if brand_key and brand_key in compact_host:
            return 0
        if "incidecoder." in host:
            return 1
        if any(domain in host for domain in _RETAIL_DOMAINS):
            return 2
        return 3

    return sorted(urls, key=rank)


def prioritize_urls(urls: list[str], brand: str) -> list[str]:
    """Public alias for the existing product-URL ranking (brand → INCIDecoder → retail)."""
    return _prioritize_product_urls(urls, brand)


async def web_search_product(
    brand: str,
    name: str,
    variant: Optional[str] = None,
    *,
    allow_unreliable_inci: bool = False,
) -> Optional[Dict[str, Any]]:
    """Автоматический Web Search: search -> URL -> существующий scraper.import_product(url).

    INCI получаем только через существующий scraper (не из поисковой выдачи).
    Возвращает product-dict или None (страница не найдена / не совпала / нет INCI).

    allow_unreliable_inci=True используется единым сканированием: если scraper
    нашёл правильную карточку, но INCI неполный, вызывающий код может дополнить
    его распознанным составом с задней фотографии и пометить как непроверенный.
    """
    from .scraper import import_product

    urls = await _search_product_urls(brand, name, variant)
    if not urls:
        return None
    urls = _prioritize_product_urls(urls, brand)
    for url in urls:
        try:
            logger.info("[WEBSEARCH] SCRAPER_START url=%s", url)
            imported = await import_product(url)
            logger.info("[WEBSEARCH] SCRAPER_DONE name=%r has_inci=%s", imported.name, bool((imported.ingredients_raw or "").strip()))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[WEBSEARCH] SCRAPER_ERROR url=%s: %s", url, exc)
            continue

        if not imported.name:
            logger.warning("[WEBSEARCH] import_product returned empty name for url=%s", url)
            continue
        if not _is_matching_product(imported.brand or "", imported.name, brand, name, variant):
            logger.warning(
                "[WEBSEARCH] product mismatch: vision=%r %r vs imported=%r %r url=%s",
                brand, name, imported.brand, imported.name, url,
            )
            continue

        ingredients = (imported.ingredients_raw or "").strip()
        result: Dict[str, Any] = {
            "name": imported.name,
            "brand": imported.brand or brand,
            "manufacturer": imported.manufacturer or "",
            "ingredients": ingredients,
            "inci_reliable": False,
            "source_url": url,
            "image_url": imported.image_url or "",
            "category": imported.category or "",
            "volume": imported.volume or "",
            "description": imported.description or "",
        }
        result["inci_reliable"] = has_reliable_inci(result)
        # INCI должен быть надёжным (несколько ингредиентов), иначе пробуем следующий URL.
        if not result["inci_reliable"] and not allow_unreliable_inci:
            logger.warning("[WEBSEARCH] unreliable INCI for url=%s (%d chars)", url, len(ingredients))
            continue
        logger.info("[WEBSEARCH] saved product %r (%d INCI chars) url=%s", imported.name, len(ingredients), url)
        return result
    return None
