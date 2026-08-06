from __future__ import annotations

from plotagent.contracts.base import PhysicalLength
from plotagent.contracts.plots import AnnotationSpec, AxisRange, AxisTickSpec
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.rendering import PlotResolver
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from tests.contracts.helpers import rich_text
from tests.rendering.fixture_factory import build_plot_and_store


def test_general_edits_resolve_identically_for_matplotlib_and_origin() -> None:
    plot, store = build_plot_and_store("K01")
    scales = tuple(
        scale.model_copy(
            update={
                "axis_range": AxisRange(minimum=0, maximum=20, reverse=True),
                "ticks": AxisTickSpec(
                    major_interval=5,
                    number_format="fixed",
                    decimal_places=1,
                ),
            }
        )
        if scale.scale_id == "scale:y"
        else scale
        for scale in plot.scales
    )
    edited = plot.model_copy(
        update={
            "title": rich_text("Qualified title"),
            "scales": scales,
            "resolved_style": plot.resolved_style.model_copy(
                update={"font_size": PhysicalLength(value=11, unit="pt")}
            ),
            "annotations": (
                AnnotationSpec(
                    annotation_id="annotation:test.text",
                    kind="text",
                    text=rich_text("Peak"),
                    x=1,
                    y=10,
                ),
                AnnotationSpec(
                    annotation_id="annotation:test.line",
                    kind="reference_line",
                    y=8,
                ),
                AnnotationSpec(
                    annotation_id="annotation:test.band",
                    kind="reference_band",
                    y=12,
                    y2=16,
                ),
            ),
        }
    )

    resolved = PlotResolver().resolve(edited, store)
    y_axis = next(axis for axis in resolved.plan.axes if axis.axis_id == "axis:y")
    assert y_axis.reverse is True
    assert tuple(tick.value for tick in y_axis.ticks) == (0, 5, 10, 15, 20)
    assert tuple(tick.label.nodes[0].text for tick in y_axis.ticks) == (
        "0.0",
        "5.0",
        "10.0",
        "15.0",
        "20.0",
    )
    assert resolved.plan.fonts[0].size == PhysicalLength(value=11, unit="pt")

    figure = MatplotlibRenderer().build_figure(resolved)
    axis = figure.axes[0]
    assert axis.get_title() == "Qualified title"
    assert axis.get_ylim() == (20, 0)
    assert "Peak" in {text.get_text() for text in axis.texts}
    assert axis.patches

    origin = compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))
    graph = origin.graph_objects[0]
    origin_y = next(axis for axis in graph.layers[0].axes if axis.axis_id == "axis:y")
    assert graph.title == "Qualified title"
    assert graph.font_size_pt == 11
    assert graph.annotations == resolved.plan.annotations
    assert origin_y.reverse is True
    assert tuple(tick.label for tick in origin_y.ticks) == (
        "0.0",
        "5.0",
        "10.0",
        "15.0",
        "20.0",
    )


def test_explicit_tick_interval_larger_than_span_remains_renderable() -> None:
    plot, store = build_plot_and_store("K01")
    scales = tuple(
        scale.model_copy(update={"ticks": AxisTickSpec(major_interval=100)})
        if scale.scale_id == "scale:y"
        else scale
        for scale in plot.scales
    )
    resolved = PlotResolver().resolve(plot.model_copy(update={"scales": scales}), store)
    y_axis = next(axis for axis in resolved.plan.axes if axis.axis_id == "axis:y")

    assert len(y_axis.ticks) >= 1
    MatplotlibRenderer().build_figure(resolved)
