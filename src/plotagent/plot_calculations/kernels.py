"""Small deterministic numeric kernels shared by calculations and render profiles.

These functions do not know about PlotSpec, PlotDocument, renderers or storage.
They are the single numeric authority for data-derived chart geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

_SQRT_TWO_PI = math.sqrt(2.0 * math.pi)


@dataclass(frozen=True, slots=True)
class HistogramGeometry:
    left: tuple[float, ...]
    right: tuple[float, ...]
    center: tuple[float, ...]
    count: tuple[int, ...]
    height: tuple[int | float, ...]
    rule: Literal["freedman_diaconis", "sturges", "constant"]


@dataclass(frozen=True, slots=True)
class KDEGeometry:
    grid: tuple[float, ...]
    density: tuple[float, ...]
    bandwidth: float


def histogram_geometry(
    values: tuple[float, ...],
    *,
    normalization: Literal["count", "density"] = "count",
) -> HistogramGeometry:
    """Apply the frozen Freedman-Diaconis/Sturges rule once for every backend."""

    if not values:
        raise ValueError("histogram calculation requires finite observations")
    observed = np.asarray(values, dtype=np.float64)
    if not np.isfinite(observed).all():
        raise ValueError("histogram observations must be finite")
    minimum = float(np.min(observed))
    maximum = float(np.max(observed))
    if minimum == maximum:
        edges = np.asarray((minimum - 0.5, maximum + 0.5), dtype=np.float64)
        rule: Literal["freedman_diaconis", "sturges", "constant"] = "constant"
    else:
        q1, q3 = np.quantile(observed, (0.25, 0.75), method="linear")
        iqr = float(q3 - q1)
        if iqr > 0:
            width = 2.0 * iqr * observed.size ** (-1.0 / 3.0)
            bin_count = max(1, math.ceil((maximum - minimum) / width))
            rule = "freedman_diaconis"
        else:
            bin_count = max(1, math.ceil(math.log2(observed.size) + 1.0))
            rule = "sturges"
        edges = np.linspace(minimum, maximum, bin_count + 1, dtype=np.float64)
    counts, _ = np.histogram(observed, bins=edges)
    widths = np.diff(edges)
    densities = counts.astype(np.float64) / (float(observed.size) * widths)
    heights: tuple[int | float, ...]
    if normalization == "count":
        heights = tuple(int(value) for value in counts)
    else:
        heights = tuple(float(value) for value in densities)
    return HistogramGeometry(
        left=tuple(float(value) for value in edges[:-1]),
        right=tuple(float(value) for value in edges[1:]),
        center=tuple(float(value) for value in (edges[:-1] + edges[1:]) / 2.0),
        count=tuple(int(value) for value in counts),
        height=heights,
        rule=rule,
    )


def scott_kde_geometry(
    values: tuple[float, ...],
    *,
    grid_points: int = 256,
    extend_bandwidths: float = 3.0,
) -> KDEGeometry:
    """Return the frozen Gaussian Scott KDE geometry used by density profiles."""

    if len(values) < 2:
        raise ValueError("Scott KDE requires at least two finite observations")
    observed = np.asarray(values, dtype=np.float64)
    if not np.isfinite(observed).all():
        raise ValueError("Scott KDE observations must be finite")
    standard_deviation = float(np.std(observed, ddof=1))
    bandwidth = standard_deviation * observed.size ** (-1.0 / 5.0)
    if not math.isfinite(bandwidth) or bandwidth <= 0:
        raise ValueError("Scott KDE requires positive sample variance")
    start = float(np.min(observed)) - extend_bandwidths * bandwidth
    end = float(np.max(observed)) + extend_bandwidths * bandwidth
    grid = np.linspace(start, end, grid_points, dtype=np.float64)
    density_sum = np.zeros(grid.size, dtype=np.float64)
    for offset in range(0, observed.size, 4096):
        chunk = observed[offset : offset + 4096]
        scaled = (grid[:, None] - chunk[None, :]) / bandwidth
        density_sum += np.exp(-0.5 * scaled * scaled).sum(axis=1)
    density = density_sum / (float(observed.size) * bandwidth * _SQRT_TWO_PI)
    return KDEGeometry(
        grid=tuple(float(value) for value in grid),
        density=tuple(float(value) for value in density),
        bandwidth=bandwidth,
    )
