"""Shared data-driven representative values for variable-size plot keys."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SizeKeyEntry:
    value: float
    marker_area: float


def representative_size_key(
    pairs: Sequence[tuple[float, float]],
    *,
    maximum_entries: int = 4,
) -> tuple[SizeKeyEntry, ...]:
    """Return evenly spaced values with interpolated marker areas.

    The key describes the continuous size mapping rather than selecting a few
    convenient observations. Duplicate size values are averaged before the
    interpolation so input row order and group count cannot affect the result.
    """

    if maximum_entries < 1:
        raise ValueError("size key requires at least one representative entry")
    finite = sorted(
        (size, area)
        for size, area in pairs
        if math.isfinite(size) and math.isfinite(area) and area > 0
    )
    if not finite:
        return ()
    areas_by_size: dict[float, list[float]] = {}
    for size, area in finite:
        areas_by_size.setdefault(size, []).append(area)
    unique = tuple((size, float(np.mean(areas))) for size, areas in sorted(areas_by_size.items()))
    if len(unique) <= maximum_entries:
        return tuple(SizeKeyEntry(value=size, marker_area=area) for size, area in unique)
    targets = np.linspace(unique[0][0], unique[-1][0], maximum_entries)
    source_values = np.asarray([item[0] for item in unique], dtype=np.float64)
    source_areas = np.asarray([item[1] for item in unique], dtype=np.float64)
    target_areas = np.interp(targets, source_values, source_areas)
    return tuple(
        SizeKeyEntry(value=float(value), marker_area=float(area))
        for value, area in zip(targets, target_areas, strict=True)
    )
