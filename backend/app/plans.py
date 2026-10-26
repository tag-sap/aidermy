"""Single source of truth for plan capacity.

Keep shelf limits here, not in frontend copy. The backend enforces the same
values for every shelf mutation path.
"""
from __future__ import annotations

SHELF_LIMITS = {"free": 5, "plus": 10, "pro": 15}
PLAN_SHELF_LIMITS = SHELF_LIMITS
# Saved compatibility sets are a lighter resource than shelf products. Keep the
# same plan tiers visible in the UI and enforce the cap on task creation.
COMPAT_SET_LIMITS = {"free": 2, "plus": 5, "pro": 10}
# Public names. The internal free key is kept for billing compatibility.
PLAN_TITLES = {"free": "Basic", "plus": "Plus", "pro": "Pro"}


def normalize_plan(plan: str | None) -> str:
    value = (plan or "free").strip().lower()
    return value if value in SHELF_LIMITS else "free"


def shelf_limit(plan: str | None) -> int:
    return SHELF_LIMITS[normalize_plan(plan)]


def compatibility_set_limit(plan: str | None) -> int:
    return COMPAT_SET_LIMITS[normalize_plan(plan)]
