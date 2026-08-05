"""Closed execution boundary for a typed OriginExportPlan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from plotagent.contracts.rendering import (
    OriginDataObject,
    OriginExportPlan,
    OriginGraphObject,
    OriginPlotPlan,
)

from .validation import expected_validation_report

PROJECT_FOLDERS = ("Data", "Analysis", "Graphs", "Metadata")


@dataclass(frozen=True, slots=True)
class NativePrimitive:
    """One fixed editable primitive; role names can only come from the typed plan."""

    plot_type: str
    x_role: str | None
    y_role: str | None
    error_role: str | None = None


_LINE_KINDS = {
    "line",
    "area",
    "density",
    "step",
    "survival_step",
    "survival_band",
    "spectrum",
    "nyquist",
    "facet_line",
}
_SYMBOL_KINDS = {"scatter", "bubble", "strip", "forest_symbol", "risk_table"}
_BAR_KINDS = {"bar", "grouped_bar", "stacked_bar", "percent_bar", "histogram"}


def _first_role(plot: OriginPlotPlan, candidates: tuple[str, ...]) -> str | None:
    roles = {item.role for item in plot.role_columns}
    return next((role for role in candidates if role in roles), None)


def native_primitives(plot: OriginPlotPlan) -> tuple[NativePrimitive, ...]:
    """Normalize every semantic plot into an allowlisted native Origin primitive set."""

    x_role = _first_role(
        plot,
        (
            "x",
            "time",
            "dose",
            "grid",
            "spectral_axis",
            "angle",
            "z_real",
            "left",
            "group",
            "label",
        ),
    )
    y_role = _first_role(
        plot,
        (
            "y",
            "center",
            "value",
            "response",
            "intensity",
            "z_imaginary",
            "height",
            "density",
            "probability",
            "survival",
            "effect",
            "median",
        ),
    )
    if plot.native_kind in _LINE_KINDS:
        return (NativePrimitive("line", x_role, y_role),)
    if plot.native_kind == "line_symbol":
        return (NativePrimitive("line_symbol", x_role, y_role),)
    if plot.native_kind in _SYMBOL_KINDS:
        return (NativePrimitive("scatter", x_role, y_role),)
    if plot.native_kind in _BAR_KINDS:
        return (NativePrimitive("column", x_role, y_role),)
    if plot.native_kind == "error_bar":
        return (NativePrimitive("line_symbol", x_role, y_role, "lower"),)
    if plot.native_kind == "band":
        return (
            NativePrimitive("line", x_role, "lower"),
            NativePrimitive("line", x_role, "upper"),
        )
    if plot.native_kind == "box":
        return tuple(
            NativePrimitive("line_symbol", "group", role)
            for role in ("whisker_low", "q1", "median", "q3", "whisker_high")
        )
    if plot.native_kind == "violin":
        return (NativePrimitive("line", x_role, y_role),)
    if plot.native_kind == "forest_interval":
        return tuple(
            NativePrimitive("scatter", "label", role)
            for role in ("lower", "effect", "upper")
        )
    if plot.native_kind in {"heatmap", "contour"}:
        return (NativePrimitive(plot.native_kind, None, None),)
    raise ValueError(f"unsupported typed Origin native kind: {plot.native_kind}")


class NativeOriginBackend(Protocol):
    """Minimal backend surface; it intentionally has no script or property-string method."""

    def ensure_blank(self) -> None: ...

    def create_folder(self, name: str) -> None: ...

    def write_data_object(self, data: OriginDataObject) -> None: ...

    def write_graph_object(self, graph: OriginGraphObject) -> None: ...

    def write_manifest(self, plan: OriginExportPlan) -> None: ...

    def inspect(self, plan: OriginExportPlan) -> dict[str, object]: ...

    def save(self, path: str) -> None: ...


def build_native_project(
    backend: NativeOriginBackend,
    plan: OriginExportPlan,
    temporary_path: str,
) -> dict[str, object]:
    """Build, inspect, then save one project through the closed backend protocol."""

    backend.ensure_blank()
    for folder in PROJECT_FOLDERS:
        backend.create_folder(folder)
    for data in plan.data_objects:
        backend.write_data_object(data)
    for graph in plan.graph_objects:
        backend.write_graph_object(graph)
    backend.write_manifest(plan)
    report = backend.inspect(plan)
    if report != expected_validation_report(plan):
        raise ValueError("live native Origin report differs from the typed execution plan")
    backend.save(temporary_path)
    return report


def inspect_native_project(
    backend: NativeOriginBackend,
    plan: OriginExportPlan,
) -> dict[str, object]:
    report = backend.inspect(plan)
    if report != expected_validation_report(plan):
        raise ValueError("fresh native Origin report differs from the typed execution plan")
    return report
