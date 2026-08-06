"""Closed, explicit parameters for fixed visual calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VolcanoThresholds:
    """One parameter set shared by volcano classification and threshold geometry."""

    absolute_log2_fold_change: float
    pvalue: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.absolute_log2_fold_change)
            or self.absolute_log2_fold_change <= 0
        ):
            raise ValueError("volcano fold-change threshold must be finite and positive")
        if not math.isfinite(self.pvalue) or not 0 < self.pvalue <= 1:
            raise ValueError("volcano p-value threshold must be in (0, 1]")


VOLCANO_THRESHOLDS = VolcanoThresholds(
    absolute_log2_fold_change=1.0,
    pvalue=0.05,
)
