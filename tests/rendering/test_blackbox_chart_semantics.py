from __future__ import annotations

import math

import pytest

from plotagent.contracts.plots import CalculatedSeriesData, PreparedSeriesData
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer, safe_text
from tests.rendering.fixture_factory import build_plot_and_store, resolve_chart


def _with_fields(chart_id: str, field_ids: tuple[str, ...]) -> tuple[object, RenderDataStore]:
    plot, store = build_plot_and_store(chart_id)
    series = plot.series[0]
    assert isinstance(series.data, PreparedSeriesData)
    old_table = store.get(series.data.prepared_dataset_ref.content_hash)
    table = RenderTable.from_columns(dict(zip(field_ids, old_table.columns.values(), strict=True)))
    new_ref = series.data.prepared_dataset_ref.model_copy(
        update={"content_hash": table.object_hash}
    )
    new_data = series.data.model_copy(
        update={"prepared_dataset_ref": new_ref, "role_fields": field_ids}
    )
    new_series = series.model_copy(update={"data": new_data})
    new_plot = plot.model_copy(
        update={
            "series": (new_series,),
            "prepared_data_refs": (new_ref,),
        }
    )
    return new_plot, RenderDataStore({table.object_hash: table})


@pytest.mark.parametrize("chart_id", ("X03", "X39", "X40"))
def test_opaque_field_ids_never_enter_series_labels_or_category_ticks(chart_id: str) -> None:
    plot, _store = build_plot_and_store(chart_id)
    field_count = len(plot.series[0].data.role_fields)
    opaque_fields = tuple(f"field:{index:024x}" for index in range(1, field_count + 1))
    updated, store = _with_fields(chart_id, opaque_fields)
    resolved = PlotResolver().resolve(updated, store)

    labels = tuple(
        text for layer in resolved.plan.layers if (text := safe_text(layer.label)) is not None
    )
    ticks = tuple(
        safe_text(tick.label)
        for axis in resolved.plan.axes
        if axis.orientation == "x"
        for tick in axis.ticks
    )

    assert all(opaque.removeprefix("field:") not in labels for opaque in opaque_fields)
    assert all(opaque.removeprefix("field:") not in ticks for opaque in opaque_fields)
    series_count = field_count - 1 if chart_id == "X03" else field_count
    assert {label for label in labels if label.startswith("Series ")} == {
        f"Series {index}" for index in range(1, series_count + 1)
    }


@pytest.mark.parametrize(
    ("chart_id", "expected"),
    (
        ("K20", ("Column", "Row")),
        ("S61", ("Predicted", "Actual")),
        ("S07", ("log2FC", "-log10(p)")),
    ),
)
def test_v1_default_axes_follow_chart_scientific_semantics(
    chart_id: str, expected: tuple[str, str]
) -> None:
    resolved = resolve_chart(chart_id)
    by_orientation = {axis.orientation: safe_text(axis.label) for axis in resolved.plan.axes}

    assert (by_orientation["x"], by_orientation["y"]) == expected


def test_later_axis_edit_is_not_overwritten_by_default_semantics() -> None:
    plot, store = build_plot_and_store("S07")
    edited = plot.model_copy(update={"plot_version": 2})
    resolved = PlotResolver().resolve(edited, store)
    by_orientation = {axis.orientation: safe_text(axis.label) for axis in resolved.plan.axes}

    assert (by_orientation["x"], by_orientation["y"]) == ("X", "Y")


def test_volcano_uses_supplied_q_value_for_significance_axis() -> None:
    plot, store = build_plot_and_store("S07")
    series = plot.series[0]
    assert isinstance(series.data, PreparedSeriesData)
    old_table = store.get(series.data.prepared_dataset_ref.content_hash)
    old_fields = series.data.role_fields
    q_field = "field:s07.0.qvalue"
    qvalues = (0.02, 0.2, 0.8, 0.9, 0.3, 0.01)
    table = RenderTable.from_columns(
        {
            **dict(old_table.columns),
            q_field: qvalues,
        }
    )
    new_ref = series.data.prepared_dataset_ref.model_copy(
        update={"content_hash": table.object_hash}
    )
    new_data = series.data.model_copy(
        update={
            "prepared_dataset_ref": new_ref,
            "role_fields": (*old_fields, q_field),
        }
    )
    updated = plot.model_copy(
        update={
            "series": (series.model_copy(update={"data": new_data}),),
            "prepared_data_refs": (new_ref,),
        }
    )
    resolved = PlotResolver().resolve(updated, RenderDataStore({table.object_hash: table}))
    observed = sorted(
        value
        for layer in resolved.plan.layers
        if layer.geometry == "xy.symbol"
        for value in resolved.table_for(layer).column(layer.field_bindings[1].field_id)
    )
    y_axis = next(axis for axis in resolved.plan.axes if axis.orientation == "y")

    assert observed == pytest.approx(sorted(-math.log10(value) for value in qvalues))
    assert safe_text(y_axis.label) == "-log10(q)"


def test_long_bar_categories_wrap_and_remain_inside_fixed_canvas() -> None:
    plot, store = build_plot_and_store("K08")
    series = plot.series[0]
    fields = series.data.role_fields
    table = RenderTable.from_columns(
        {
            fields[0]: (
                "Short",
                "A much longer than usual scientific category label",
                "Another long treatment condition for layout testing",
            ),
            fields[1]: (1.0, 2.0, 3.0),
            fields[2]: (0.8, 1.8, 2.8),
            fields[3]: (1.2, 2.2, 3.2),
        }
    )
    assert isinstance(series.data, CalculatedSeriesData)
    content_hash = series.data.calculation_result_ref.content_hash
    resolved = PlotResolver().resolve(
        plot,
        RenderDataStore({**store.tables, content_hash: table}),
    )
    x_axis = next(axis for axis in resolved.plan.axes if axis.orientation == "x")

    assert all("\n" not in (safe_text(tick.label) or "") for tick in x_axis.ticks)

    figure = MatplotlibRenderer().build_figure(resolved)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    labels = figure.axes[0].get_xticklabels()
    assert any("\n" in label.get_text() for label in labels)
    assert min(label.get_window_extent(renderer).x0 for label in labels) >= 7.5
    assert max(label.get_window_extent(renderer).x1 for label in labels) <= figure.bbox.x1 - 7.5
    assert min(label.get_window_extent(renderer).y0 for label in labels) >= 7.5
