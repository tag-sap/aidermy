"""Single source of truth for plan capacity.

Keep shelf limits here, not in frontend copy. The backend enforces the same
values for every shelf mutation path.
"""
from __future__ import annotations

SHELF_LIMITS = {"free": 5, "plus": 10, "pro": 15}
PLAN_SHELF_LIMITS = SHELF_LIMITS


def normalize_plan(plan: str | None) -> str:
    value = (plan or "free").strip().lower()
    return value if value in SHELF_LIMITS else "free"


def shelf_limit(plan: str | None) -> int:
    return SHELF_LIMITS[normalize_plan(plan)]
