"""Search adapter for V2 research.

The search itself is NOT reimplemented here: it delegates to Aidermy's existing
DuckDuckGo organic search (``app.product_identification.search_web_urls``), which
already handles the user agent, retries/backoff and ad filtering. This module only
adapts it to the synchronous research loop and builds queries for a product and
its missing parameters.

The search returns candidate URLs, never evidence. Fetching, text extraction and
quote validation stay in ``documents.py`` / ``evidence.py``.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Iterable, Mapping, Protocol, Sequence

logger = logging.getLogger(__name__)

MAX_QUERIES = 4
RESULTS_PER_QUERY = 5


class SourceSearch(Protocol):
    """Finds candidate page URLs for a natural-language query."""

    name: str

    def search(self, query: str, *, limit: int = RESULTS_PER_QUERY) -> tuple[str, ...]: ...


def run_async(factory):
    """Run an async callable from synchronous code (also inside a worker thread).

    The analysis endpoints execute the service in a threadpool, so there is no
    running loop there; if a loop does exist, the coroutine is executed in a fresh
    thread with its own loop instead of failing.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    result: dict = {}

    def worker() -> None:
        try:
            result["value"] = asyncio.run(factory())
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller
            result["error"] = exc

    thread = threading.Thread(target=worker, name="evaluation-search", daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


class DuckDuckGoSourceSearch:
    """Thin synchronous adapter over the existing project search."""

    name = "duckduckgo"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def search(self, query: str, *, limit: int = RESULTS_PER_QUERY) -> tuple[str, ...]:
        from ..product_identification import search_web_urls

        cleaned = " ".join(str(query or "").split())
        if not cleaned:
            return ()
        try:
            urls = run_async(lambda: search_web_urls(cleaned, limit=limit))
        except Exception as exc:  # noqa: BLE001 - search failures are data
            logger.warning("[EVAL SEARCH] query=%r failed: %s", cleaned, exc)
            return ()
        return tuple(str(url) for url in urls or () if str(url).strip())


def build_research_queries(
    *,
    product: Mapping | None,
    composition: Mapping | None,
    parameter_labels: Sequence[str] = (),
    limit: int = MAX_QUERIES,
) -> tuple[str, ...]:
    """Build a small, bounded set of queries for one product.

    Product/INCI queries come first (they serve every parameter through shared
    documents), then one query per missing parameter for extra coverage.
    """
    product = product or {}
    composition = composition or {}
    brand = str(product.get("brand") or "").strip()
    name = str(product.get("name") or "").strip()
    base = " ".join(part for part in (brand, name) if part).strip()

    queries: list[str] = []

    def add(value: str) -> None:
        text = " ".join(str(value or "").split())
        if text and text.casefold() not in {item.casefold() for item in queries}:
            queries.append(text)

    if base:
        add(f"{base} ingredients INCI")
        add(f"{base} incidecoder")
    inci = str(composition.get("inci_raw") or "")
    tokens = [token.strip() for token in inci.replace(";", ",").split(",") if token.strip()]
    if tokens:
        add(f"{' '.join(tokens[:5])} ingredients")
    for label in parameter_labels:
        if len(queries) >= limit:
            break
        if base:
            add(f"{base} {label}")
    return tuple(queries[:limit])


def prioritize_candidates(urls: Iterable[str], product: Mapping | None) -> tuple[str, ...]:
    """Brand/INCIDecoder/retail first, keeping the project's existing ranking."""
    ordered = [str(url) for url in urls if str(url or "").strip()]
    if not ordered:
        return ()
    brand = str((product or {}).get("brand") or "").strip()
    try:
        from ..product_identification import prioritize_urls

        if brand:
            ordered = prioritize_urls(ordered, brand)
    except Exception:  # noqa: BLE001 - ranking is best effort
        pass
    seen: list[str] = []
    for url in ordered:
        if url not in seen:
            seen.append(url)
    return tuple(seen)
