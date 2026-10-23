"""Production wiring for the analysis mechanic (env-driven, no hidden fallbacks).

`configure_evaluation(app)` is called once from ``app.main``:

  * storage      — ``PostgresStore`` over ``SUPABASE_DATABASE_URL`` (no DSN -> None);
  * page fetch   — ``HttpDocumentFetcher`` (real HTTP + SSRF protection);
  * search       — the project's existing DuckDuckGo organic search;
  * LLM          — ``LlmResearchProvider`` over the configured DeepSeek endpoint.

Missing pieces do not crash the app: ``/analyze`` still scans knowledge and
reports gaps, while ``/analyze/research`` returns 503 with an explicit reason.
Migrations are never applied automatically; readiness is logged at startup.
"""
from __future__ import annotations

import logging
import os

from .documents import MAX_DOCUMENTS_PER_SESSION, HttpDocumentFetcher
from .llm_research import DEFAULT_MODELS, LlmResearchProvider
from .websearch import DuckDuckGoSourceSearch

logger = logging.getLogger(__name__)

REQUIRED_TABLES = (
    "product_compositions",
    "parameter_registry",
    "research_jobs",
    "sources",
    "evidence",
    "source_documents",
    "parameter_evaluations",
    "rule_versions",
    "snapshots",
)


def _env_flag(name: str, *, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def build_document_fetcher(*, enabled: bool = True) -> HttpDocumentFetcher | None:
    if not enabled:
        return None
    return HttpDocumentFetcher(timeout=float(os.getenv("AIDERMY_FETCH_TIMEOUT", "15")))


def build_research_provider(api_key: str | None = None) -> LlmResearchProvider | None:
    key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        return None
    override = [
        name.strip()
        for name in os.getenv("AIDERMY_LLM_MODELS", "").split(",")
        if name.strip()
    ]
    return LlmResearchProvider(
        api_key=key,
        models=tuple(override) if override else DEFAULT_MODELS,
        price_per_1k_tokens=float(os.getenv("AIDERMY_LLM_PRICE_PER_1K", "0") or 0),
    )


def build_source_search(*, enabled: bool | None = None) -> DuckDuckGoSourceSearch | None:
    if enabled is None:
        enabled = _env_flag("AIDERMY_SEARCH_ENABLED", default=True)
    return DuckDuckGoSourceSearch() if enabled else None


def build_store_from_env():
    """PostgresStore when SUPABASE_DATABASE_URL is configured, else None."""
    if not os.getenv("SUPABASE_DATABASE_URL"):
        logger.warning(
            "[EVALUATION] SUPABASE_DATABASE_URL is not set: /api/v1/evaluation will "
            "answer 503 until storage is configured"
        )
        return None
    from .postgres_store import PostgresStore

    return PostgresStore()


def evaluation_schema_status() -> dict:
    """Read-only readiness of the `evaluation` schema (never migrates)."""
    if not os.getenv("SUPABASE_DATABASE_URL"):
        return {
            "configured": False,
            "reason": "SUPABASE_DATABASE_URL is not set",
            "missing_tables": list(REQUIRED_TABLES),
        }
    try:
        from ..postgres_connection import get_postgres_connection

        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select table_name from information_schema.tables "
                    "where table_schema = 'evaluation'"
                )
                existing = {str(row["table_name"]) for row in cur.fetchall()}
    except Exception as exc:  # noqa: BLE001 - readiness must not crash the app
        return {"configured": False, "reason": f"database unreachable: {exc}"}
    missing = [name for name in REQUIRED_TABLES if name not in existing]
    return {
        "configured": True,
        "ready": not missing,
        "missing_tables": missing,
        "tables": sorted(existing),
    }


def _env_number(name: str, default, cast):
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    try:
        return cast(str(value).strip())
    except (TypeError, ValueError):
        logger.warning("[EVALUATION] invalid %s=%r, using %r", name, value, default)
        return default


def analysis_limits_from_env() -> dict:
    """Budget and volume limits for one analysis run (all overridable)."""
    return {
        "max_documents": _env_number(
            "AIDERMY_MAX_DOCUMENTS", MAX_DOCUMENTS_PER_SESSION, int
        ),
        "max_cost_per_job": _env_number("AIDERMY_MAX_COST_PER_JOB", 0.50, float),
        "max_cost_per_run": _env_number("AIDERMY_MAX_COST_PER_RUN", 5.00, float),
        "max_attempts": _env_number("AIDERMY_MAX_ATTEMPTS", 3, int),
    }


def configure_evaluation(
    app,
    *,
    store=None,
    method_version: str | None = None,
    rule_version: str | None = None,
    provider=None,
    fetcher=None,
    search=None,
    allow_synthetic_evidence: bool = False,
) -> None:
    """Attach storage and research dependencies to the FastAPI application."""
    from .api import setup_evaluation_routes

    if store is None:
        store = build_store_from_env()
    if provider is None:
        provider = build_research_provider()
    if fetcher is None:
        fetcher = build_document_fetcher(enabled=_env_flag("AIDERMY_FETCH_ENABLED"))
    if search is None:
        search = build_source_search()

    setup_evaluation_routes(
        app,
        store=store,
        method_version=method_version,
        rule_version=rule_version,
        provider=provider,
        fetcher=fetcher,
        search=search,
        allow_synthetic_evidence=allow_synthetic_evidence,
    )
    logger.info(
        "[EVALUATION] routes registered: store=%s provider=%s fetcher=%s search=%s",
        bool(store),
        getattr(provider, "name", None) or "missing",
        getattr(fetcher, "name", None) or "missing",
        getattr(search, "name", None) or "missing",
    )
