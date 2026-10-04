# calibration_worker.py
# Отдельный процесс выполнения calibration run ВНЕ HTTP/Gunicorn worker.
# Запуск: python -m app.calibration_worker --run-key <run_key>
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict

from .calibration_profiles import CALIBRATION_PROFILES
from .calibration_service import (
    DEFAULT_MODEL,
    audit,
    build_cases,
    compare,
    find_drift,
    generate_ai_reference_batched,
    get_run,
    load_products,
    run_score_engine,
    update_run,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_progress(run_key: str, stats: Dict[str, Any]) -> None:
    update_run(
        run_key,
        current_batch=stats.get("current_batch", 0),
        total_batches=stats.get("total_batches", 0),
        processed_cases=stats.get("processed_cases", 0),
        total_cases=stats.get("total_cases", 0),
        ai_request_count=stats.get("ai_requests", 0),
        cache_hits=stats.get("cache_hits", 0),
        cache_misses=stats.get("cache_misses", 0),
        ai_references_generated=stats.get("references_generated", 0),
        errors=stats.get("errors", 0),
        updated_at=_now(),
    )


async def _run_async(run_key: str) -> None:
    run = get_run(run_key)
    if run is None:
        return
    if run.get("status") == "completed":
        return  # idempotent resume: уже завершён

    params = json.loads(run["params"]) if run.get("params") else {}
    product_limit = int(params.get("product_limit", 500))
    profile_ids = params.get("profile_ids") or []
    use_cache = bool(params.get("use_cache", True))
    force_refresh = bool(params.get("force_refresh", False))
    candidate = params.get("candidate")

    profiles = [p for p in CALIBRATION_PROFILES if not profile_ids or p["id"] in profile_ids]
    products = load_products(limit=product_limit)
    cases = build_cases(products, profiles)

    update_run(
        run_key, status="running", started_at=_now(), updated_at=_now(),
        product_count=len(products), profile_count=len(profiles),
        case_count=len(cases), total_cases=len(cases),
        processed_cases=0, current_batch=0, total_batches=0,
        ai_request_count=0, cache_hits=0, cache_misses=0,
        ai_references_generated=0, errors=0,
        error=None,
    )

    async def on_batch(stats: Dict[str, Any]) -> None:
        _persist_progress(run_key, stats)

    references, stats = await generate_ai_reference_batched(
        products, profiles, model=DEFAULT_MODEL, use_cache=use_cache,
        force_refresh=force_refresh, on_batch=on_batch,
    )

    # Score Engine phase (вся тяжёлая работа с AI уже закэширована).
    prod_results = run_score_engine(cases)
    metrics = audit(prod_results, references)
    drift = find_drift(prod_results, references)
    comparison = None
    if candidate:
        cand_results = run_score_engine(cases, candidate)
        comparison = compare(prod_results, cand_results, references)

    result_payload = {"audit": metrics, "drift": drift, "comparison": comparison}
    update_run(
        run_key, status="completed", completed_at=_now(), updated_at=_now(),
        processed_cases=len(cases),
        ai_request_count=stats.get("ai_requests", 0),
        cache_hits=stats.get("cache_hits", 0),
        cache_misses=stats.get("cache_misses", 0),
        ai_references_generated=stats.get("references_generated", 0),
        errors=stats.get("errors", 0),
        metrics=json.dumps(result_payload, ensure_ascii=False),
        error=None,
    )


def run_calibration_job(run_key: str) -> None:
    try:
        asyncio.run(_run_async(run_key))
    except Exception as e:
        err = (str(e)[:2000] + "\n" + traceback.format_exc())[:4000]
        try:
            update_run(run_key, status="failed", completed_at=_now(), updated_at=_now(), error=err)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-key", required=True)
    args = parser.parse_args()
    print(f"[{_now()}] worker start {args.run_key}", flush=True)
    run_calibration_job(args.run_key)
    print(f"[{_now()}] worker done {args.run_key}", flush=True)


if __name__ == "__main__":
    main()
