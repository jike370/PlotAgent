"""Version-independent deterministic jitter for plot geometry."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from plotagent.plot_calculations.errors import PlotCalculationError


def deterministic_jitter(
    row_ids: Sequence[str],
    *,
    seed: int,
    half_width: float,
) -> tuple[float, ...]:
    """Map stable row ids to uniform offsets without depending on an RNG implementation."""

    if seed < 0 or not math.isfinite(half_width) or half_width < 0:
        raise PlotCalculationError(
            "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
            "jitter seed and half_width must be non-negative and finite",
        )
    denominator = float((1 << 64) - 1)
    offsets: list[float] = []
    for row_id in row_ids:
        digest = hashlib.sha256(f"plotagent-jitter-v1\0{seed}\0{row_id}".encode()).digest()
        unit = int.from_bytes(digest[:8], "big") / denominator
        offsets.append((2.0 * unit - 1.0) * half_width)
    return tuple(offsets)
