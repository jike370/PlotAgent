from __future__ import annotations

from plotagent.contracts.plots import CalculatedSeriesData
from plotagent.contracts.rendering import ResolvedAnnotation
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from tests.rendering.fixture_factory import build_plot_and_store, resolve_chart


def _text(annotation: ResolvedAnnotation) -> str:
    rich_text = annotation.text
    assert rich_text is not None
    return "".join(node.text for node in rich_text.nodes)


def test_s61_resolver_materializes_count_labels_at_matrix_cell_centers() -> None:
    resolved = resolve_chart("S61")

    assert [
        (_text(item), item.x, item.y, item.color.value if item.color else None)
        for item in resolved.plan.annotations
    ] == [
        ("12", 0.0, 0.0, "#000000"),
        ("2", 1.0, 0.0, "#FFFFFF"),
        ("1", 0.0, 1.0, "#FFFFFF"),
        ("10", 1.0, 1.0, "#000000"),
    ]
    assert all(
        item.kind == "text" and item.affect_range is False
        for item in resolved.plan.annotations
    )


def test_regular_k20_heatmap_does_not_gain_automatic_cell_labels() -> None:
    assert resolve_chart("K20").plan.annotations == ()


def test_s61_cell_labels_follow_dynamic_class_count_and_include_zero() -> None:
    plot, store = build_plot_and_store("S61")
    series = plot.series[0]
    fields = series.data.role_fields
    classes = ("A", "B", "C")
    rows = tuple(actual for actual in classes for _predicted in classes)
    columns = classes * len(classes)
    values = tuple(float(value) for value in range(len(rows)))
    table = RenderTable.from_columns(dict(zip(fields, (rows, columns, values), strict=True)))
    assert isinstance(series.data, CalculatedSeriesData)
    content_hash = series.data.calculation_result_ref.content_hash
    resolved = PlotResolver().resolve(
        plot,
        RenderDataStore({**store.tables, content_hash: table}),
    )

    assert len(resolved.plan.annotations) == 9
    assert [_text(item) for item in resolved.plan.annotations] == [str(value) for value in range(9)]
    assert {(item.x, item.y) for item in resolved.plan.annotations} == {
        (float(x), float(y)) for y in range(3) for x in range(3)
    }


def test_s61_annotations_are_shared_by_matplotlib_and_origin_plans() -> None:
    resolved = resolve_chart("S61")

    figure = MatplotlibRenderer().build_figure(resolved)
    rendered = {(item.get_text(), *item.get_position()) for item in figure.axes[0].texts}
    assert rendered == {
        ("12", 0.0, 0.0),
        ("2", 1.0, 0.0),
        ("1", 0.0, 1.0),
        ("10", 1.0, 1.0),
    }

    export = build_origin_export_spec((resolved,), export_id="export:s61-cell-labels")
    origin_plan = compile_origin_plan((resolved,), export)
    assert origin_plan.graph_objects[0].annotations == resolved.plan.annotations
    colors = [
        item.color.value if item.color else None
        for item in origin_plan.graph_objects[0].annotations
    ]
    assert colors == [
        "#000000",
        "#FFFFFF",
        "#FFFFFF",
        "#000000",
    ]
