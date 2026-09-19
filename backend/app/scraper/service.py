import asyncio
import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

from .extractors import extract_product
from .models import ProductImportResult

logger = logging.getLogger(__name__)


class ProductImportError(Exception):
    """A user-facing product import failure with safe technical logging."""

    def __init__(self, message: str, technical: str | None = None):
        super().__init__(message)
        self.technical = technical or message


def validate_public_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ProductImportError("Введите корректную ссылку на товар.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
        raise ProductImportError("Ссылка на этот адрес недоступна.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ProductImportError("Не удалось открыть сайт по этой ссылке.", str(exc)) from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            raise ProductImportError("Ссылка на этот адрес недоступна.")
    return parsed.geturl()


def _fetch(fetcher: str, url: str) -> object:
    executable_path = os.getenv("SCRAPLING_BROWSER_EXECUTABLE")
    if fetcher == "basic":
        from scrapling.fetchers import Fetcher
        return Fetcher.get(url, timeout=20, impersonate="chrome")
    if fetcher == "dynamic":
        from scrapling.fetchers import DynamicFetcher
        options = {"headless": True, "network_idle": False, "timeout": 30000}
        if executable_path:
            options["executable_path"] = executable_path
        return DynamicFetcher.fetch(url, **options)
    from scrapling.fetchers import StealthyFetcher
    options = {"headless": True, "network_idle": True, "timeout": 60000}
    if executable_path:
        options["executable_path"] = executable_path
    return StealthyFetcher.fetch(url, **options)


def _try_extract(fetcher: str, url: str) -> ProductImportResult:
    logger.info("[SCRAPER] %s fetch", fetcher.capitalize())
    page = _fetch(fetcher, url)
    status = getattr(page, "status", None)
    if status is not None and int(status) >= 400:
        raise ProductImportError("Сайт недоступен.", f"HTTP status {status}")
    return extract_product(page, url)


async def import_product(url: str) -> ProductImportResult:
    source_url = validate_public_url(url)
    logger.info("[SCRAPER] Import started")
    last_error: Exception | None = None
    for fetcher in ("basic", "dynamic", "stealth"):
        try:
            result = await asyncio.to_thread(_try_extract, fetcher, source_url)
            if result.has_product_data():
                if result.ingredients_raw:
                    logger.info("[SCRAPER] Ingredients found")
                logger.info("[SCRAPER] Product normalized")
                return result
        except ProductImportError as exc:
            last_error = exc
            logger.info("[SCRAPER] %s rejected: %s", fetcher.capitalize(), exc.technical)
        except Exception as exc:
            last_error = exc
            logger.exception("[SCRAPER] %s fetch failed", fetcher.capitalize())
    if isinstance(last_error, ProductImportError):
        raise ProductImportError(
            "Не удалось автоматически получить данные товара: сайт отклонил автоматический запрос (антибот или ограничение доступа). Проверьте ссылку или добавьте состав вручную.",
            repr(last_error),
        )
    raise ProductImportError(
        "Не удалось автоматически получить данные товара. Проверьте ссылку или добавьте состав вручную.",
        repr(last_error),
    )
