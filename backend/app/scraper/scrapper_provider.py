"""Optional client for amerkurev/scrapper (Playwright + Readability).

Scrapper is an external Docker service, not a Python dependency. The provider
is disabled unless ``SCRAPPER_URL`` is configured, so ordinary deployments do
not require a 2 GB browser image. The caller still uses the same deterministic
HTML extractor and never invents INCI.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .html_provider import extract_html_product
from .models import ProductImportResult


def configured() -> bool:
    return bool((os.getenv("SCRAPPER_URL") or "").strip())


async def fetch_scrapper(url: str) -> ProductImportResult:
    """Fetch full page HTML through a configured Scrapper instance."""
    base = (os.getenv("SCRAPPER_URL") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("Scrapper is not configured")
    timeout = float((os.getenv("SCRAPPER_TIMEOUT") or "60").strip() or "60")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(
            f"{base}/api/article",
            params={"url": url},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload: Any = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Scrapper returned an invalid payload")
    html = payload.get("fullContent") or payload.get("content") or ""
    if not isinstance(html, str) or not html.strip():
        raise RuntimeError("Scrapper returned no HTML")
    return extract_html_product(html, url)
