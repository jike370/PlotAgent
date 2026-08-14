"""Stable tombstones for chart types removed from the public product."""

from __future__ import annotations

REMOVED_CHART_TYPE_ERROR_CODE = "CHART_TYPE_REMOVED"
REMOVED_CHART_TYPE_IDS = frozenset(
    {"K05", "K16", "K17", "K25", "S01", "S05", "S07", "S21", "S25", "S31", "X01"}
)
