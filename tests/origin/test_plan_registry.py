from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from plotagent.contracts.rendering import OriginExportPlan
from plotagent.origin.planner import (
    OriginPlanError,
    build_origin_export_spec,
    compile_origin_plan,
)
from plotagent.origin.registry import (
    ORIGIN_ADAPTERS,
    OriginAdapterNotFoundError,
    get_origin_adapter,
)
from plotagent.rendering import PlotResolver
from tests.rendering.fixture_factory import build_plot_and_store, resolve_chart

EXPECTED_CHART_IDS = {
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
    "X01",
    "X02",
    "X03",
    "X05",
    "X07",
    "X09",
    "X11",
    "X12",
    "X13",
    "X15",
    "X16",
    "X17",
    "X18",
    "X19",
    "X23",
    "X24",
    "X35",
    "X36",
    "X37",
    "X38",
    "X39",
    "X40",
    "S07",
}
FIXTURE_MANIFEST = Path(__file__).parents[1] / "fixtures" / "rendering" / "chart-fixtures.json"


def _compile(chart_id: str) -> OriginExportPlan:
    resolved = resolve_chart(chart_id)
    export = build_origin_export_spec((resolved,), export_id=f"export:{chart_id.lower()}")
    return compile_origin_plan((resolved,), export)


def test_origin_registry_is_exactly_the_frozen_54_o1_surface() -> None:
    assert len(ORIGIN_ADAPTERS) == 54
    assert {entry.chart_type_id for entry in ORIGIN_ADAPTERS} == EXPECTED_CHART_IDS
    assert all(
        entry.capability == "O1" and not entry.known_differences for entry in ORIGIN_ADAPTERS
    )
    for rejected in ("K23", "S45", "K26", "unknown"):
        with pytest.raises(OriginAdapterNotFoundError, match="no qualified"):
            get_origin_adapter(rejected)


@pytest.mark.parametrize("chart_id", sorted(EXPECTED_CHART_IDS))
def test_every_chart_compiles_to_a_strict_roundtrip_plan(chart_id: str) -> None:
    plan = _compile(chart_id)
    payload = plan.model_dump(mode="json")

    assert OriginExportPlan.model_validate_json(plan.model_dump_json()) == plan
    assert plan.manifest.chart_type_ids == (chart_id,)
    assert plan.manifest.render_plan_hashes == (plan.render_plan_hash,)
    assert plan.capability == "O1"
    assert not plan.manifest.known_differences
    assert all(graph.layers for graph in plan.graph_objects)
    assert all(data.columns or data.matrix is not None for data in plan.data_objects)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    for forbidden in (
        "property_assignments",
        "labtalk",
        "worksheet.formula",
        "raster",
        "svg",
        "template_path",
    ):
        assert forbidden not in text


def test_frozen_minimal_representative_edge_matrix_all_compiles_without_origin() -> None:
    manifest = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
    compiled: list[str] = []
    for chart in manifest["charts"]:
        chart_id = chart["chart_type_id"]
        for case in chart["cases"]:
            plan = _compile(chart_id)
            assert plan.manifest.chart_type_ids == (chart_id,)
            compiled.append(case["case_id"])
    assert len(compiled) == len(set(compiled)) == 162


def test_matrix_and_explicit_panel_plans_remain_native_structures() -> None:
    for chart_id in ("K20", "K21", "K22", "S61"):
        plan = _compile(chart_id)
        assert {item.object_kind for item in plan.data_objects} == {"matrixbook"}
        assert all(item.matrix is not None for item in plan.data_objects)

    k25 = _compile("K25")
    graph = k25.graph_objects[0]
    assert tuple(layer.panel_id for layer in graph.layers) == ("panel:a", "panel:b")
    assert len(graph.layers) == 2


def test_supplied_survival_risk_table_has_native_panel_axes() -> None:
    plot, store = build_plot_and_store("S01")
    step = plot.series[0]
    risk = step.model_copy(
        update={
            "series_id": "series:s01.risk",
            "geometry": "risk_table",
        }
    )
    resolved = PlotResolver().resolve(plot.model_copy(update={"series": (step, risk)}), store)

    risk_axes = tuple(axis for axis in resolved.plan.axes if axis.panel_id == "panel:risk")
    assert len(risk_axes) == 2
    assert {axis.orientation for axis in risk_axes} == {"x", "y"}
    plan = compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))
    risk_layer = next(
        layer for layer in plan.graph_objects[0].layers if layer.panel_id == "panel:risk"
    )
    assert len(risk_layer.axes) == 2
    assert risk_layer.plots


def test_plan_rejects_hash_drift_unknown_fields_and_nonformal_input() -> None:
    resolved = resolve_chart("K01")
    export = build_origin_export_spec((resolved,))
    with pytest.raises(OriginPlanError, match="hash does not match"):
        compile_origin_plan((resolved,), export.model_copy(update={"render_plan_hash": "0" * 64}))

    plan = compile_origin_plan((resolved,), export)
    with pytest.raises(ValidationError):
        OriginExportPlan.model_validate({**plan.model_dump(), "script": "run anything"})

    interactive = resolved.__class__.create(
        resolved.plan.model_copy(update={"quality_tier": "interactive"}), resolved.tables
    )
    interactive_export = build_origin_export_spec((interactive,))
    with pytest.raises(OriginPlanError, match="formal"):
        compile_origin_plan((interactive,), interactive_export)
