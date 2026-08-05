from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from plotagent.contracts.rendering import OriginDataObject, OriginExportPlan, OriginGraphObject
from plotagent.origin.native import (
    PROJECT_FOLDERS,
    build_native_project,
    inspect_native_project,
    native_primitives,
)
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.origin.validation import expected_validation_report
from tests.rendering.fixture_factory import resolve_chart


def _plan(chart_id: str) -> OriginExportPlan:
    resolved = resolve_chart(chart_id)
    return compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))


@dataclass
class _RecordingBackend:
    plan: OriginExportPlan
    calls: list[tuple[str, str]] = field(default_factory=list)

    def set_plan(self, plan: OriginExportPlan) -> None:
        self.calls.append(("plan", plan.origin_plan_id))

    def ensure_blank(self) -> None:
        self.calls.append(("blank", ""))

    def create_folder(self, name: str) -> None:
        self.calls.append(("folder", name))

    def write_data_object(self, data: OriginDataObject) -> None:
        self.calls.append(("data", data.object_id))

    def write_graph_object(self, graph: OriginGraphObject) -> None:
        self.calls.append(("graph", graph.graph_id))

    def write_manifest(self, plan: OriginExportPlan) -> None:
        self.calls.append(("manifest", plan.origin_plan_id))

    def inspect(self, plan: OriginExportPlan) -> dict[str, object]:
        self.calls.append(("inspect", plan.origin_plan_id))
        return expected_validation_report(plan)

    def save(self, path: str) -> None:
        self.calls.append(("save", path))


@pytest.mark.parametrize(
    "chart_id",
    [
        *(f"K{index:02d}" for index in range(1, 23)),
        "K24",
        "K25",
        "S01",
        "S05",
        "S21",
        "S25",
        "S31",
        "S34",
        "S61",
    ],
)
def test_all_31_plans_normalize_to_fixed_native_primitives(chart_id: str) -> None:
    plan = _plan(chart_id)
    primitives = [
        primitive
        for graph in plan.graph_objects
        for layer in graph.layers
        for plot in layer.plots
        for primitive in native_primitives(plot)
    ]

    assert primitives
    assert {item.plot_type for item in primitives} <= {
        "line",
        "line_symbol",
        "scatter",
        "column",
        "area",
        "fill_area",
        "floating_column",
        "bubble",
        "bubble_color",
        "heatmap",
        "contour",
    }


def test_closed_executor_orders_native_objects_before_validation_and_save() -> None:
    plan = _plan("K25")
    backend = _RecordingBackend(plan)

    report = build_native_project(backend, plan, "temporary.opju")

    assert report == expected_validation_report(plan)
    assert backend.calls[:6] == [
        ("plan", plan.origin_plan_id),
        ("blank", ""),
        *(("folder", folder) for folder in PROJECT_FOLDERS),
    ]
    assert backend.calls[-2:] == [
        ("inspect", plan.origin_plan_id),
        ("save", "temporary.opju"),
    ]


def test_fresh_inspection_rejects_report_drift() -> None:
    plan = _plan("K20")
    backend = _RecordingBackend(plan)
    expected = expected_validation_report(plan)
    expected["raster_objects"] = True
    backend.inspect = lambda unused: expected  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="fresh native Origin report differs"):
        inspect_native_project(backend, plan)


@pytest.mark.parametrize(
    ("chart_id", "transforms", "plot_count"),
    [
        ("K06", {"interval_connector", "direct"}, 4),
        ("K07", {"direct", "band"}, 2),
        ("K13", {"box_outline", "direct"}, 2),
        ("K14", {"violin_polygon"}, 1),
        ("S21", {"forest_interval", "forest_symbol"}, 2),
    ],
)
def test_interval_distribution_and_band_geometry_is_not_collapsed(
    chart_id: str,
    transforms: set[str],
    plot_count: int,
) -> None:
    plan = _plan(chart_id)
    primitives = [
        primitive
        for graph in plan.graph_objects
        for layer in graph.layers
        for plot in layer.plots
        for primitive in native_primitives(plot)
    ]

    assert {item.transform for item in primitives} == transforms
    assert len(primitives) == plot_count
    if chart_id == "K07":
        assert any(item.plot_type == "fill_area" for item in primitives)
