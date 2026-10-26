"""API for durable shelf compatibility checks, saved sets and notifications."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import compat_store
from .auth import get_current_user
from .compat_worker import ensure_worker
from .database import (
    get_balance,
    get_product_by_id,
    get_user_profile_updated_at,
    get_user_shelf,
)
from .compat_service import compatibility_cost
from .plans import compatibility_set_limit
from .evaluation.snapshot import profile_fingerprint

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/compatibility", tags=["compatibility"])
notifications_router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class ProfileRequest(BaseModel):
    profile: dict[str, Any] = {}


class IndividualRequest(ProfileRequest):
    product_id: int


class CompatibilityRequest(ProfileRequest):
    product_ids: list[int]
    name: str = ""


def _context_key(kind: str, profile: dict, product_ids: list[int]) -> str:
    material = {
        "kind": kind,
        "profile": profile_fingerprint(profile),
        "products": sorted(int(pid) for pid in product_ids),
    }
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _active_key(user_id: int, kind: str, context_key: str) -> str:
    return f"{kind}:{user_id}:{context_key}"


def _public_task(task: dict | None) -> dict | None:
    if not task:
        return None
    fields = (
        "id", "kind", "status", "product_ids", "set_id", "error",
        "attempts", "created_at", "updated_at", "started_at", "finished_at",
        "result_snapshot_id", "cost",
    )
    return {key: task.get(key) for key in fields}


def _load_report(set_row: dict | None) -> dict | None:
    if not set_row:
        return None
    raw = set_row.get("report_json")
    if isinstance(raw, dict):
        return raw
    if not raw:
        return None
    try:
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _public_set(set_row: dict, *, detail: bool = False) -> dict:
    report = _load_report(set_row)
    out = {
        "id": int(set_row["id"]),
        "name": set_row.get("name") or "Набор",
        "product_ids": [int(x) for x in (set_row.get("product_ids") or [])],
        "status": set_row.get("status") or "queued",
        "created_at": set_row.get("created_at") or "",
        "updated_at": set_row.get("updated_at") or "",
        "checked_at": set_row.get("checked_at") or "",
        "task_id": set_row.get("task_id"),
        "cost": int(set_row.get("cost") or 0),
        "error": set_row.get("error") or "",
        "report": report if detail else None,
        "report_summary": (
            {
                "score": report.get("score"),
                "overall": report.get("overall") or {},
                "product_count": len(report.get("products") or []),
                "products": report.get("products") or [],
            }
            if report
            else None
        ),
    }
    return out


def _shelf_product_map(user_id: int) -> dict[int, dict]:
    return {
        int(row["product_id"]): row
        for row in get_user_shelf(int(user_id))
        if row.get("product_id") is not None
    }


def _validate_products(user_id: int, product_ids: list[int]) -> list[int]:
    ids = [int(pid) for pid in product_ids]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="В наборе не должно быть повторяющихся продуктов.")
    if len(ids) < 2:
        raise HTTPException(status_code=422, detail="Для проверки совместимости выберите минимум два продукта.")
    if len(ids) > 15:
        raise HTTPException(status_code=422, detail="В одном наборе можно проверить не более 15 продуктов.")
    shelf = _shelf_product_map(user_id)
    missing = [pid for pid in ids if pid not in shelf]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Выбранные продукты должны находиться на вашей полке.",
        )
    for pid in ids:
        product = get_product_by_id(pid)
        if not product:
            raise HTTPException(status_code=422, detail="Один из продуктов больше недоступен.")
        cabinet = str(shelf[pid].get("cabinet") or "face").lower()
        if cabinet and cabinet not in {"face", "уход для лица", "лицо"}:
            raise HTTPException(
                status_code=422,
                detail="Проверка совместимости доступна для средств ухода за лицом.",
            )
    return ids


def _default_set_name(product_ids: list[int]) -> str:
    names = []
    for pid in product_ids[:2]:
        product = get_product_by_id(int(pid)) or {}
        name = str(product.get("name") or "").replace("\n", " ").strip()
        if name:
            names.append(name[:42])
    return " + ".join(names) if names else "Набор для проверки"


def _require_balance(user_id: int, cost: int) -> None:
    """Fail before creating a task when the fixed set price cannot be paid."""
    try:
        balance = int((get_balance(int(user_id)) or {}).get("balance") or 0)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[COMPAT] balance lookup failed")
        raise HTTPException(status_code=503, detail="Не удалось проверить баланс.") from exc
    if balance < int(cost):
        raise HTTPException(
            status_code=402,
            detail=(
                f"Для проверки нужно {int(cost)} балл(ов), на балансе {balance}. "
                "Пополните баланс и повторите проверку."
            ),
        )


@router.get("/pricing")
async def compatibility_pricing(
    product_count: int = 2,
    user: dict = Depends(get_current_user),
) -> dict:
    if product_count < 1 or product_count > 15:
        raise HTTPException(
            status_code=422,
            detail="Количество продуктов должно быть от 1 до 15.",
        )
    return {
        "product_count": int(product_count),
        "cost": compatibility_cost(int(product_count)),
        "unit": "points",
    }


@router.post("/tasks/individual")
async def start_individual_task(
    payload: IndividualRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    product = get_product_by_id(int(payload.product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден.")
    profile = payload.profile or {}
    context = _context_key("individual", profile, [int(payload.product_id)])
    active_key = _active_key(int(user["id"]), "individual", context)
    existing = compat_store.find_active_task_by_key(active_key)
    if existing:
        return {"task": _public_task(existing), "reused": True}
    try:
        task = compat_store.create_task(
            user_id=int(user["id"]),
            kind="individual",
            product_ids=[int(payload.product_id)],
            profile=profile,
            profile_updated_at=str(get_user_profile_updated_at(int(user["id"])) or ""),
            context_key=context,
            active_key=active_key,
        )
    except Exception:
        existing = compat_store.find_active_task_by_key(active_key)
        if existing:
            return {"task": _public_task(existing), "reused": True}
        logger.exception("[COMPAT] individual task creation failed")
        raise HTTPException(status_code=503, detail="Не удалось создать проверку продукта.")
    return {"task": _public_task(task), "reused": False}


@router.post("/tasks/compatibility")
async def start_compatibility_task(
    payload: CompatibilityRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    product_ids = _validate_products(int(user["id"]), payload.product_ids)
    profile = payload.profile or {}
    context = _context_key("compatibility", profile, product_ids)
    existing = compat_store.find_set_by_context(int(user["id"]), context)
    if existing:
        task = compat_store.get_task(int(user["id"]), int(existing["task_id"])) if existing.get("task_id") else None
        if task and task.get("status") in compat_store.ACTIVE_TASK_STATUSES:
            return {"set": _public_set(existing), "task": _public_task(task), "reused": True}
        if existing.get("status") == "completed":
            return {"set": _public_set(existing), "task": _public_task(task), "reused": True}
    active_key = _active_key(int(user["id"]), "compatibility", context)
    active = compat_store.find_active_task_by_key(active_key)
    if active:
        set_row = compat_store.get_set(int(user["id"]), int(active["set_id"])) if active.get("set_id") else None
        return {"set": _public_set(set_row) if set_row else None, "task": _public_task(active), "reused": True}

    set_limit = compatibility_set_limit(user.get("plan"))
    if len(compat_store.list_sets(int(user["id"]))) >= set_limit:
        raise HTTPException(
            status_code=422,
            detail=(
                f"На тарифе {str(user.get('plan') or 'free').capitalize()} можно хранить "
                f"до {set_limit} наборов. Удалите старый набор и повторите проверку."
            ),
        )
    cost = compatibility_cost(len(product_ids))
    _require_balance(int(user["id"]), cost)
    name = (payload.name or "").strip()[:120] or _default_set_name(product_ids)
    set_row: dict | None = None
    try:
        set_row = compat_store.create_set(
            user_id=int(user["id"]),
            name=name,
            product_ids=product_ids,
            profile=profile,
            profile_updated_at=str(get_user_profile_updated_at(int(user["id"])) or ""),
            context_key=context,
            cost=cost,
        )
        task = compat_store.create_task(
            user_id=int(user["id"]),
            kind="compatibility",
            product_ids=product_ids,
            profile=profile,
            profile_updated_at=str(get_user_profile_updated_at(int(user["id"])) or ""),
            context_key=context,
            set_id=int(set_row["id"]),
            active_key=active_key,
            cost=cost,
        )
        compat_store.update_set(int(set_row["id"]), task_id=int(task["id"]))
        set_row = compat_store.get_set(int(user["id"]), int(set_row["id"])) or set_row
    except Exception:
        # A concurrent tab may win the unique active-key race.
        active = compat_store.find_active_task_by_key(active_key)
        if active:
            try:
                if set_row:
                    compat_store.soft_delete_set(int(user["id"]), int(set_row["id"]))
            except Exception:
                pass
            set_row = compat_store.get_set(int(user["id"]), int(active["set_id"])) if active.get("set_id") else None
            return {"set": _public_set(set_row) if set_row else None, "task": _public_task(active), "reused": True}
        logger.exception("[COMPAT] failed to create set task")
        raise HTTPException(status_code=503, detail="Не удалось создать проверку набора.")
    return {"set": _public_set(set_row), "task": _public_task(task), "reused": False, "cost": cost}


@router.get("/sets")
async def list_compatibility_sets(user: dict = Depends(get_current_user)) -> dict:
    rows = compat_store.list_sets(int(user["id"]))
    return {"sets": [_public_set(row) for row in rows]}


@router.get("/sets/{set_id}")
async def get_compatibility_set(
    set_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    row = compat_store.get_set(int(user["id"]), int(set_id))
    if not row:
        raise HTTPException(status_code=404, detail="Набор не найден.")
    return {"set": _public_set(row, detail=True)}


@router.delete("/sets/{set_id}")
async def delete_compatibility_set(
    set_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    if not compat_store.soft_delete_set(int(user["id"]), int(set_id)):
        raise HTTPException(status_code=404, detail="Набор не найден.")
    return {"status": "ok", "deleted": 1}


@router.post("/sets/{set_id}/retry")
async def retry_compatibility_set(
    set_id: int,
    payload: ProfileRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    row = compat_store.get_set(int(user["id"]), int(set_id))
    if not row:
        raise HTTPException(status_code=404, detail="Набор не найден.")
    product_ids = [int(pid) for pid in (row.get("product_ids") or [])]
    _validate_products(int(user["id"]), product_ids)
    profile = payload.profile or {}
    context = _context_key("compatibility", profile, product_ids)
    active_key = _active_key(int(user["id"]), "compatibility", context)
    active = compat_store.find_active_task_by_key(active_key)
    if active:
        return {"task": _public_task(active), "set": _public_set(row), "reused": True}
    cost = compatibility_cost(len(product_ids))
    _require_balance(int(user["id"]), cost)
    now = datetime.now(timezone.utc).isoformat()
    compat_store.update_set(
        int(set_id),
        status="queued",
        cost=cost,
        report_json=None,
        error="",
        checked_at=None,
        profile_json=profile,
        context_key=context,
        updated_at=now,
    )
    task = compat_store.create_task(
        user_id=int(user["id"]),
        kind="compatibility",
        product_ids=product_ids,
        profile=profile,
        profile_updated_at=str(get_user_profile_updated_at(int(user["id"])) or ""),
        context_key=context,
        set_id=int(set_id),
        active_key=active_key,
        cost=cost,
    )
    compat_store.update_set(int(set_id), task_id=int(task["id"]))
    return {
        "task": _public_task(task),
        "set": _public_set(compat_store.get_set(int(user["id"]), int(set_id)) or row),
        "reused": False,
        "cost": cost,
    }


@router.get("/tasks/individual/{product_id}")
async def get_individual_task(
    product_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    task = compat_store.find_individual_task(int(user["id"]), int(product_id))
    return {"task": _public_task(task)}


@router.get("/tasks/{task_id}")
async def get_compatibility_task(
    task_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    task = compat_store.get_task(int(user["id"]), int(task_id))
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    return {"task": _public_task(task)}


@notifications_router.get("")
async def get_notifications(
    limit: int = 30,
    user: dict = Depends(get_current_user),
) -> dict:
    rows = compat_store.list_notifications(int(user["id"]), limit=limit)
    return {
        "notifications": rows,
        "unread": sum(1 for row in rows if not row.get("read_at")),
    }


@notifications_router.post("/{notification_id}/read")
async def read_notification(
    notification_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    if not compat_store.mark_notification_read(int(user["id"]), int(notification_id)):
        raise HTTPException(status_code=404, detail="Уведомление не найдено.")
    return {"status": "ok"}


@notifications_router.post("/read-all")
async def read_all_notifications(user: dict = Depends(get_current_user)) -> dict:
    return {"updated": compat_store.mark_all_notifications_read(int(user["id"]))}


@notifications_router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    if not compat_store.delete_notification(int(user["id"]), int(notification_id)):
        raise HTTPException(status_code=404, detail="Уведомление не найдено.")
    return {"status": "ok", "deleted": 1}


@notifications_router.delete("")
async def delete_all_notifications(user: dict = Depends(get_current_user)) -> dict:
    return {"status": "ok", "deleted": compat_store.delete_all_notifications(int(user["id"]))}


def setup_compat_routes(app) -> None:
    """Register routes, initialize local tables and start the durable worker."""
    try:
        compat_store.ensure_schema()
    except Exception:  # noqa: BLE001 - missing production migration is reported on use
        logger.exception("[COMPAT] schema initialization failed")
    app.include_router(router)
    app.include_router(notifications_router)
    app.router.on_startup.append(lambda: ensure_worker(app))
