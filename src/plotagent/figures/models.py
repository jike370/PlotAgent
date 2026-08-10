"""Immutable request and result types for Figure orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from plotagent.contracts.base import PhysicalSize, PlotSpecRef
from plotagent.contracts.plots import FigureSpec, PublicationProfileSnapshot, SafeRichText

type FigureLayout = Literal["1x2", "1x3", "1x4", "2x1", "2x2", "2x3", "3x1"]
type FigureAlignment = Literal["independent", "align_x", "align_y", "align_both"]
type FigureAxisPolicy = Literal["independent", "shared_x", "shared_y", "shared_both"]


@dataclass(frozen=True, slots=True)
class AxisCompatibilitySignature:
    scale: Literal["linear", "log10", "datetime", "categorical"]
    unit_hash: str


@dataclass(frozen=True, slots=True)
class FigureSourceSnapshot:
    plot_ref: PlotSpecRef
    numeric_only: bool
    x_axis: AxisCompatibilitySignature | None
    y_axis: AxisCompatibilitySignature | None


@dataclass(frozen=True, slots=True)
class FigureCreateRequest:
    project_id: str
    figure_id: str
    idempotency_key: str
    layout: FigureLayout
    plot_refs: tuple[PlotSpecRef, ...]
    physical_size: PhysicalSize
    publication_profile: PublicationProfileSnapshot
    alignment: FigureAlignment = "align_both"
    axis_policy: FigureAxisPolicy = "independent"
    common_legend: bool = False
    panel_labels: tuple[SafeRichText, ...] = ()


@dataclass(frozen=True, slots=True)
class PanelReplacement:
    panel_id: str
    plot_ref: PlotSpecRef


@dataclass(frozen=True, slots=True)
class FigureUpgradeRequest:
    project_id: str
    figure_id: str
    expected_figure_version: int
    idempotency_key: str
    replacements: tuple[PanelReplacement, ...]


@dataclass(frozen=True, slots=True)
class FigureUpdate:
    panel_id: str
    pinned_ref: PlotSpecRef
    latest_ref: PlotSpecRef


@dataclass(frozen=True, slots=True)
class FigureResult:
    figure: FigureSpec
    replayed: bool = False
