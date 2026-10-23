"""Production wiring for the analysis mechanic (env-driven, no hidden fallbacks).

`/analyze` works without any of this: it only scans knowledge and builds the
report. `/analyze/research` needs a provider and a fetcher, so they are explicit:

    configure_evaluation(app, store=PostgresStore())

Without ``DEEPSEEK_API_KEY`` the provider is absent and the research endpoint
returns 503 instead of pretending that research happened.
"""
from __future__ import annotations

import os

from .documents import HttpDocumentFetcher
from .llm_research import LlmResearchProvider


def build_document_fetcher(*, enabled: bool = True) -> HttpDocumentFetcher | None:
    if not enabled:
        return None
    return HttpDocumentFetcher(timeout=float(os.getenv("AIDERMY_FETCH_TIMEOUT", "15")))


def build_research_provider(api_key: str | None = None) -> LlmResearchProvider | None:
    key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        return None
    return LlmResearchProvider(
        api_key=key,
        price_per_1k_tokens=float(os.getenv("AIDERMY_LLM_PRICE_PER_1K", "0") or 0),
    )


def configure_evaluation(
    app,
    *,
    store=None,
    method_version: str | None = None,
    rule_version: str | None = None,
    provider=None,
    fetcher=None,
) -> None:
    """Attach storage and research dependencies to the FastAPI application."""
    from .api import setup_evaluation_routes

    if provider is None:
        provider = build_research_provider()
    if fetcher is None:
        fetcher = build_document_fetcher()
    setup_evaluation_routes(
        app,
        store=store,
        method_version=method_version,
        rule_version=rule_version,
        provider=provider,
        fetcher=fetcher,
    )
