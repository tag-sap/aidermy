import asyncio
import copy
import ipaddress
import logging
import os
import socket
import sys
import threading
import time
from urllib.parse import urlparse

import httpx

from .extractors import ProductPageBlocked, UnsupportedPageFormat, extract_product
from .models import ProductImportResult

logger = logging.getLogger(__name__)

# Возможные пути к системному Chromium-браузеру для Patchright (если env не задан).
_BROWSER_CANDIDATES = [
    # Windows
    os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
]


def resolve_browser_executable() -> str | None:
    """Возвращает путь к браузеру для headless-фетчеров.

    Явный env имеет приоритет; иначе ищем системный Chrome/Edge, чтобы
    DynamicFetcher/StealthyFetcher работали без ручной установки Patchright.
    """
    env_path = os.getenv("SCRAPLING_BROWSER_EXECUTABLE")
    if env_path and os.path.exists(env_path):
        return env_path
    for candidate in _BROWSER_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


# Общий таймаут на ОДИН fetcher (basic/dynamic/stealth). Гарантирует, что scraper
# никогда не зависнет бесконечно на внешнем сайте (например, headless-браузер).
SCRAPER_FETCH_TIMEOUT = 90.0

# A short process-local cache prevents repeated URL imports from launching the
# browser again. It is disabled by default; production can opt in with a small
# TTL (e.g. 300 seconds). Only successful results are cached.
_IMPORT_CACHE: dict[str, tuple[float, ProductImportResult]] = {}
_IMPORT_CACHE_LOCK = threading.Lock()


def _cache_ttl() -> float:
    try:
        return max(0.0, float((os.getenv("SCRAPER_IMPORT_CACHE_TTL") or "0").strip() or "0"))
    except ValueError:
        return 0.0


def _cache_get(url: str) -> ProductImportResult | None:
    ttl = _cache_ttl()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _IMPORT_CACHE_LOCK:
        entry = _IMPORT_CACHE.get(url)
        if not entry:
            return None
        timestamp, result = entry
        if now - timestamp > ttl:
            _IMPORT_CACHE.pop(url, None)
            return None
        return copy.copy(result)


def _cache_put(url: str, result: ProductImportResult) -> None:
    if _cache_ttl() <= 0:
        return
    with _IMPORT_CACHE_LOCK:
        _IMPORT_CACHE[url] = (time.monotonic(), copy.copy(result))


def clear_import_cache() -> None:
    with _IMPORT_CACHE_LOCK:
        _IMPORT_CACHE.clear()


def _domain_matches(host: str, rules: str) -> bool:
    host = (host or "").lower().rstrip(".")
    for item in (rules or "").replace(";", ",").split(","):
        domain = item.strip().lower().rstrip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return True
    return False


def _scrapper_enabled_for(host: str) -> bool:
    from .scrapper_provider import configured

    if not configured():
        return False
    if os.getenv("SCRAPPER_ALL_DOMAINS", "0").strip().lower() in {"1", "true", "yes"}:
        return True
    return _domain_matches(host, os.getenv("SCRAPPER_DOMAINS", "goldapple.ru"))

# Ярлыки раскрывающихся блоков состава (таб/аккордеон/button/summary).
_INGREDIENTS_ACCORDION_LABELS = (
    "Ingredients", "Full Ingredients", "Ingredients & Benefits",
    "Ingredients and Benefits", "Ingredient List", "What's inside",
    "Состав", "Ингредиенты",
)


def _dismiss_cookie_banner(page: object) -> None:
    """Закрывает cookie-баннер (best-effort), который перехватывает клики."""
    try:
        for text in ("Accept All", "Accept", "Согласиться", "Принять", "Allow All"):
            btn = page.get_by_role("button", name=text)
            if btn.count() > 0:
                btn.first.click(force=True, timeout=3000)
                page.wait_for_timeout(500)
                return
    except Exception:  # noqa: BLE001
        pass


def _expand_ingredients(page: object) -> None:
    """JS-interaction (page_action): раскрывает блок Ingredients после загрузки.

    Ищет именно КЛИКАБЕЛЬНУЮ кнопку аккордеона/таба состава. Приоритет: кнопка с
    aria-label (надёжный признак раскрывающегося блока), затем элемент с
    aria-expanded. Если INCI уже был в HTML — extraction вернёт его и без клика.
    """
    try:
        _dismiss_cookie_banner(page)
        for label in _INGREDIENTS_ACCORDION_LABELS:
            # Кнопка аккордеона с aria-label="Ingredients" (не текстовый бейдж).
            loc = page.locator(f"button[aria-label='{label}']")
            if loc.count() == 0:
                loc = page.locator(f"[aria-expanded][aria-label='{label}']")
            if loc.count() == 0:
                continue
            loc.first.click(force=True, timeout=5000)
            try:
                # INCI часто грузится лениво (AJAX) после раскрытия аккордеона.
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:  # noqa: BLE001
                page.wait_for_timeout(3000)
            logger.info("[SCRAPER] expanded Ingredients via aria-label %r", label)
            return
    except Exception as exc:  # noqa: BLE001
        logger.info("[SCRAPER] expand ingredients skipped: %s", exc)


class ProductImportError(Exception):
    """A user-facing product import failure with safe technical logging.

    ``code`` and ``status_code`` let the API distinguish an invalid link, a
    site that blocks automation, a timeout, no product data and an upstream
    failure without exposing provider internals to the client.
    """

    def __init__(
        self,
        message: str,
        technical: str | None = None,
        *,
        code: str = "import_failed",
        status_code: int = 422,
        provider: str | None = None,
    ):
        super().__init__(message)
        self.technical = technical or message
        self.code = code
        self.status_code = int(status_code)
        self.provider = provider


def validate_public_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ProductImportError(
            "Введите корректную ссылку на товар.",
            code="invalid_url",
            status_code=400,
        )
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
        raise ProductImportError(
            "Ссылка на этот адрес недоступна.",
            code="invalid_url",
            status_code=400,
        )
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ProductImportError(
            "Не удалось открыть сайт по этой ссылке.",
            str(exc),
            code="network_error",
            status_code=502,
        ) from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            raise ProductImportError(
                "Ссылка на этот адрес недоступна.",
                code="invalid_url",
                status_code=400,
            )
    return parsed.geturl()


def _error_for_status(status: int, provider: str) -> ProductImportError:
    """Map an upstream HTTP status to a user-facing, non-retrying result."""
    if status in {401, 403}:
        return ProductImportError(
            "Сайт запретил автоматическое получение карточки (нужен вход или доступ ограничен). "
            "Используйте фото состава или ручной ввод.",
            f"HTTP {status}",
            code="access_denied",
            status_code=422,
            provider=provider,
        )
    if status == 429:
        return ProductImportError(
            "Сайт ограничил частоту запросов. Попробуйте позже или используйте фото/ручной ввод.",
            f"HTTP {status}",
            code="rate_limited",
            status_code=429,
            provider=provider,
        )
    if status == 422:
        return ProductImportError(
            "Сайт вернул страницу проверки устройства вместо карточки товара. "
            "Автоматический импорт остановлен; используйте распознавание по фото или ручной ввод.",
            f"HTTP {status}",
            code="anti_bot",
            status_code=422,
            provider=provider,
        )
    if status in {404, 410}:
        return ProductImportError(
            "Страница товара не найдена. Проверьте ссылку.",
            f"HTTP {status}",
            code="not_found",
            status_code=404,
            provider=provider,
        )
    if status >= 500:
        return ProductImportError(
            "Сайт временно вернул ошибку. Попробуйте позже или используйте фото/ручной ввод.",
            f"HTTP {status}",
            code="upstream_error",
            status_code=502,
            provider=provider,
        )
    return ProductImportError(
        "Сайт не отдал страницу товара.",
        f"HTTP {status}",
        code="upstream_error",
        status_code=422,
        provider=provider,
    )


def _fetch(fetcher: str, url: str) -> object:
    executable_path = resolve_browser_executable()
    if fetcher == "basic":
        from scrapling.fetchers import Fetcher
        return Fetcher.get(url, timeout=20, impersonate="chrome")
    if fetcher == "dynamic":
        from scrapling.fetchers import DynamicFetcher
        options = {"headless": True, "network_idle": False, "timeout": 30000, "page_action": _expand_ingredients}
        if executable_path:
            options["executable_path"] = executable_path
        return DynamicFetcher.fetch(url, **options)
    from scrapling.fetchers import StealthyFetcher
    options = {"headless": True, "network_idle": True, "timeout": 60000, "page_action": _expand_ingredients}
    if executable_path:
        options["executable_path"] = executable_path
    return StealthyFetcher.fetch(url, **options)


def _try_extract(fetcher: str, url: str) -> ProductImportResult:
    logger.info("[SCRAPER] %s fetch", fetcher.capitalize())
    page = _fetch(fetcher, url)
    status = getattr(page, "status", None)
    if status is not None and int(status) >= 400:
        raise _error_for_status(int(status), fetcher)
    return extract_product(page, url)


async def import_product(url: str) -> ProductImportResult:
    source_url = validate_public_url(url)
    cached = _cache_get(source_url)
    if cached is not None:
        logger.info("[SCRAPER] cache hit domain=%s", urlparse(source_url).hostname or "")
        return cached
    host = (urlparse(source_url).hostname or "").lower()
    logger.info("[SCRAPER] Import started domain=%s", host)
    last_error: Exception | None = None
    best_result: ProductImportResult | None = None
    best_provider: str | None = None
    blocked_error: ProductImportError | None = None
    observed_errors: list[ProductImportError] = []

    # Optional Scrapper (Playwright + Readability) is preferred only for the
    # explicitly configured domains. It is a separate Docker service and is
    # never required for the fast path.
    if _scrapper_enabled_for(host):
        try:
            from .scrapper_provider import fetch_scrapper

            result = await asyncio.wait_for(
                fetch_scrapper(source_url),
                timeout=float(os.getenv("SCRAPPER_TIMEOUT", "60")),
            )
            if result.has_product_data():
                if result.ingredients_raw:
                    logger.info("[SCRAPER] Ingredients found via scrapper")
                    _cache_put(source_url, result)
                    return result
                best_result = result
                best_provider = "scrapper"
                logger.info("[SCRAPER] scrapper: no ingredients, trying next provider")
        except asyncio.TimeoutError:
            last_error = ProductImportError(
                "Scrapper не успел загрузить страницу. Попробуйте позже.",
                "scrapper timeout",
                code="timeout",
                status_code=504,
                provider="scrapper",
            )
            observed_errors.append(last_error)
        except httpx.HTTPStatusError as exc:
            last_error = _error_for_status(exc.response.status_code, "scrapper")
            observed_errors.append(last_error)
        except Exception as exc:  # noqa: BLE001 - optional external service
            last_error = ProductImportError(
                "Scrapper недоступен, используется встроенный fallback.",
                f"{type(exc).__name__}: {exc}",
                code="provider_unavailable",
                status_code=502,
                provider="scrapper",
            )
            observed_errors.append(last_error)
            logger.info("[SCRAPER] scrapper unavailable: %s", exc)

    # Free fast path: plain HTML first. It is opt-in so existing deployments
    # can keep the proven Scrapling order until the provider is enabled.
    # Domains known to serve a challenge to plain HTTP clients skip this pass.
    httpx_skip = os.getenv("SCRAPER_HTTPX_SKIP_DOMAINS", "goldapple.ru")
    if (
        os.getenv("SCRAPER_HTTPX_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
        and not _domain_matches(host, httpx_skip)
    ):
        try:
            from .html_provider import fetch_http

            result = await asyncio.wait_for(
                fetch_http(source_url),
                timeout=float(os.getenv("SCRAPER_HTTPX_TIMEOUT", "20")),
            )
            if result.has_product_data():
                if result.ingredients_raw:
                    logger.info("[SCRAPER] Ingredients found via httpx")
                    _cache_put(source_url, result)
                    return result
                best_result = result
                best_provider = "httpx"
                logger.info("[SCRAPER] httpx: no ingredients, trying browser fallback")
        except asyncio.TimeoutError:
            last_error = ProductImportError(
                "Сайт слишком долго отвечает. Попробуйте позже или используйте фото/ручной ввод.",
                "httpx timeout",
                code="timeout",
                status_code=504,
                provider="httpx",
            )
            observed_errors.append(last_error)
            logger.info("[SCRAPER] httpx timed out")
        except httpx.HTTPStatusError as exc:
            last_error = _error_for_status(exc.response.status_code, "httpx")
            observed_errors.append(last_error)
            logger.info("[SCRAPER] httpx rejected: %s", last_error.technical)
        except UnsupportedPageFormat as exc:
            last_error = ProductImportError(
                "Ссылка ведёт не на HTML-страницу товара (например, PDF или изображение). "
                "Укажите страницу товара или используйте фото/ручной ввод.",
                repr(exc),
                code="unsupported_format",
                status_code=422,
                provider="httpx",
            )
            observed_errors.append(last_error)
            logger.info("[SCRAPER] httpx unsupported format: %s", exc)
        except ProductPageBlocked as exc:
            last_error = ProductImportError(
                "Сайт вернул страницу проверки устройства вместо карточки товара. "
                "Автоматический импорт остановлен; используйте распознавание по фото или ручной ввод.",
                repr(exc),
                code="anti_bot",
                status_code=422,
                provider="httpx",
            )
            observed_errors.append(last_error)
            logger.info("[SCRAPER] httpx blocked by challenge page")
        except Exception as exc:  # noqa: BLE001 - fallback remains available
            last_error = ProductImportError(
                "Не удалось загрузить страницу товара.",
                f"{type(exc).__name__}: {exc}",
                code="network_error",
                status_code=502,
                provider="httpx",
            )
            observed_errors.append(last_error)
            logger.info("[SCRAPER] httpx rejected: %s", exc)

    # Optional Crawl4AI browser pass for JavaScript-rendered product pages.
    if os.getenv("CRAWL4AI_ENABLED", "0").strip().lower() in {"1", "true", "yes"}:
        try:
            from .html_provider import fetch_crawl4ai

            result = await asyncio.wait_for(
                fetch_crawl4ai(source_url),
                timeout=float(os.getenv("CRAWL4AI_TIMEOUT", "90")),
            )
            if result.has_product_data():
                if result.ingredients_raw:
                    logger.info("[SCRAPER] Ingredients found via Crawl4AI")
                    _cache_put(source_url, result)
                    return result
                if best_result is None:
                    best_result = result
                    best_provider = "crawl4ai"
        except asyncio.TimeoutError:
            logger.info("[SCRAPER] Crawl4AI timed out")
        except Exception as exc:  # noqa: BLE001 - optional dependency
            logger.info("[SCRAPER] Crawl4AI unavailable/rejected: %s", exc)

    for fetcher in ("basic", "dynamic", "stealth"):
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_try_extract, fetcher, source_url),
                timeout=SCRAPER_FETCH_TIMEOUT,
            )
            if result.has_product_data():
                if best_result is None:
                    best_result = result
                    best_provider = fetcher
                if result.ingredients_raw:
                    logger.info("[SCRAPER] Ingredients found via %s", fetcher)
                    logger.info("[SCRAPER] Product normalized provider=%s", fetcher)
                    _cache_put(source_url, result)
                    return result
                logger.info("[SCRAPER] %s: no ingredients, trying next fetcher", fetcher)
        except asyncio.TimeoutError:
            last_error = ProductImportError(
                "Сайт слишком долго отвечает. Попробуйте позже или используйте фото/ручной ввод.",
                f"{fetcher} timeout",
                code="timeout",
                status_code=504,
                provider=fetcher,
            )
            observed_errors.append(last_error)
            logger.info("[SCRAPER] %s timed out after %.0fs", fetcher.capitalize(), SCRAPER_FETCH_TIMEOUT)
        except ProductPageBlocked as exc:
            logger.warning("[SCRAPER] %s blocked by site challenge", fetcher.capitalize())
            blocked_error = ProductImportError(
                "Сайт вернул страницу проверки устройства вместо карточки товара. "
                "Автоматический импорт остановлен; используйте распознавание по фото или ручной ввод.",
                repr(exc),
                code="anti_bot",
                status_code=422,
                provider=fetcher,
            )
            # Do not try to bypass or repeat an explicit challenge.
            break
        except ProductImportError as exc:
            last_error = exc
            observed_errors.append(last_error)
            logger.info("[SCRAPER] %s rejected: %s", fetcher.capitalize(), exc.technical)
        except Exception as exc:
            last_error = ProductImportError(
                "Не удалось запустить браузерный fallback для этой страницы.",
                f"{fetcher}: {type(exc).__name__}: {exc}",
                code="provider_unavailable",
                status_code=502,
                provider=fetcher,
            )
            observed_errors.append(last_error)
            logger.info("[SCRAPER] %s unavailable: %s", fetcher.capitalize(), exc)
    if best_result is not None:
        logger.info("[SCRAPER] Product normalized provider=%s (no ingredients)", best_provider or "unknown")
        _cache_put(source_url, best_result)
        return best_result
    candidates = ([blocked_error] if blocked_error is not None else []) + observed_errors
    # Prefer the most actionable classification. A missing headless browser
    # must not hide an upstream 403/422/timeout from the user.
    for code in (
        "anti_bot",
        "access_denied",
        "rate_limited",
        "unsupported_format",
        "timeout",
        "not_found",
        "upstream_error",
        "network_error",
    ):
        for error in candidates:
            if error.code == code:
                raise error
    if isinstance(last_error, ProductImportError):
        # Preserve the useful classification (timeout/403/404) instead of
        # collapsing every failure into a generic anti-bot message.
        if last_error.code == "provider_unavailable":
            raise ProductImportError(
                "Страница загрузилась, но не удалось найти карточку товара или состав. "
                "Проверьте ссылку, сфотографируйте состав или введите его вручную.",
                last_error.technical,
                code="no_product_data",
                status_code=422,
                provider=last_error.provider,
            ) from last_error
        raise last_error
    raise ProductImportError(
        "Страница загрузилась, но не удалось найти карточку товара или состав. "
        "Проверьте ссылку, сфотографируйте состав или введите его вручную.",
        repr(last_error),
        code="no_product_data",
        status_code=422,
    )
