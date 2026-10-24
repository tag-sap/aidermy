"""Pricing and helpers for a user-approved shelf refresh.

The regular full check costs one point. A refresh is a deterministic
recalculation of several stale products, so it uses the same point unit and a
configurable bundle discount. The measured provider cost per check is not
available in this repository; the discount below is therefore an explicit
business parameter, not a claim about provider cost. Confirm it with the real
provider invoices before changing production prices.
"""
from __future__ import annotations

import math
import os

INDIVIDUAL_CHECK_POINTS = 1
# Set AIDERMY_SHELF_REFRESH_DISCOUNT in deployment after confirming margins.
DEFAULT_REFRESH_DISCOUNT = 0.8


def refresh_quote(count: int) -> int:
    """Return the fixed package price for ``count`` stale products."""
    if count <= 0:
        return 0
    try:
        discount = float(os.getenv("AIDERMY_SHELF_REFRESH_DISCOUNT", DEFAULT_REFRESH_DISCOUNT))
    except (TypeError, ValueError):
        discount = DEFAULT_REFRESH_DISCOUNT
    discount = min(1.0, max(0.0, discount))
    return max(1, math.ceil(count * INDIVIDUAL_CHECK_POINTS * discount))
