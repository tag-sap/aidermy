# product_identification.py
# Оркестрация: фото продукта -> идентификация -> поиск в БД -> автоматический Web Search.
# Это orchestration/navigation layer: использует существующие scraper/vision_service/database.
from __future__ import annotations

import re
from typing import Any, Dict, Optional

import httpx

from . import database


def _normalize(s: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", (s or "").lower()).strip()


def find_product_in_db(brand: str, name: str) -> Optional[Dict[str, Any]]:
    """Ищет продукт в Product DB по нормализованному бренду + названию.

    Не считает продукт найденным только по совпадению названия: проверяет
    соответствие бренда и названия.
    """
    if not brand and not name:
        return None
    b = _normalize(brand)
    n = _normalize(name)
    conn = database.get_connection(database.PRODUCTS_DB)
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT id, name, slug, brand, image_url, category, ingredients "
        "FROM products WHERE is_canonical = 1"
    ).fetchall()
    conn.close()

    for row in rows:
        row_brand = _normalize(str(row["brand"] or ""))
        row_name = _normalize(str(row["name"] or "").replace("\n", " "))
        brand_ok = (not b) or (b and b in row_brand) or (b and row_brand and row_brand in b)
        name_ok = n and (n in row_name or row_name in n)
        if brand_ok and name_ok:
            return {
                "id": row["id"],
                "slug": row["slug"] or "",
                "name": row["name"] or "",
                "brand": row["brand"] or "",
                "image_url": row["image_url"] or "",
                "category": row["category"] or "",
                "ingredients": row["ingredients"] or "",
                "source_url": "",
            }
    return None


def has_reliable_inci(product: Optional[Dict[str, Any]]) -> bool:
    """Достоверный INCI = непустая строка с несколькими ингредиентами."""
    if not product:
        return False
    ings = [x.strip() for x in (product.get("ingredients") or "").split(",") if x.strip()]
    return len(ings) >= 2


async def _search_product_url(brand: str, name: str, variant: Optional[str] = None) -> Optional[str]:
    """Ищет ссылку на страницу продукта (best-effort, без API-ключа).

    Использует публичный HTML-эндпоинт DuckDuckGo ТОЛЬКО как способ получить URL.
    INCI из поисковой выдачи не извлекается. Если поиск недоступен или ничего
    не нашлось — возвращает None (оркестратор перейдёт к fallback).
    """
    query = " ".join(x for x in (brand, name, variant) if x and x.strip()).strip()
    if not query:
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0), follow_redirects=True) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AidermyBot/1.0)"},
            )
        if resp.status_code != 200:
            return None
        html = resp.text
        # Первый внешний результат: ссылка вида <a rel="nofollow" class="result__a" href="...">
        m = re.search(r'class="result__a"[^>]*href="([^"]+)"', html)
        if not m:
            return None
        # DDG оборачивает ссылку в свой редирект — извлекаем реальный URL из uddg.
        url = m.group(1)
        uddg = re.search(r"uddg=([^&]+)", url)
        return _unquote(uddg.group(1)) if uddg else None
    except Exception:  # noqa: BLE001
        return None


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


async def web_search_product(brand: str, name: str, variant: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Автоматический Web Search: search -> URL -> существующий scraper.import_product(url).

    INCI получаем только через существующий scraper (не из поисковой выдачи).
    Возвращает product-dict или None (страница не найдена / не совпала / нет INCI).
    """
    from .scraper import import_product

    url = await _search_product_url(brand, name, variant)
    if not url:
        return None
    try:
        imported = await import_product(url)
    except Exception:  # noqa: BLE001
        return None

    if not imported.name:
        return None
    if not _is_matching_product(imported.brand or "", imported.name, brand, name, variant):
        return None

    ingredients = (imported.ingredients_raw or "").strip()
    result: Dict[str, Any] = {
        "name": imported.name,
        "brand": imported.brand or brand,
        "ingredients": ingredients,
        "source_url": url,
        "image_url": imported.image_url or "",
        "category": imported.category or "",
        "volume": imported.volume or "",
        "description": imported.description or "",
    }
    # INCI должен быть надёжным (несколько ингредиентов), иначе fallback.
    if not has_reliable_inci(result):
        return None
    return result
