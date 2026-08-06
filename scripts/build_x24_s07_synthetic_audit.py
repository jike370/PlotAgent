"""Build the X24/S07 synthetic generalized visual-regression audit.

This suite is deliberately separate from Origin same-source visual admission. It has
no reference-image column: one frozen CSV feeds one PlotSpec/ResolvedRenderPlan, and
that exact resolved plan feeds both the formal Matplotlib and native Origin exporters.
"""

# ruff: noqa: E402, E501 -- repo bootstrap and contiguous generated HTML.

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pandas as pd
from matplotlib.text import Text

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.contracts.base import PreparedDatasetRef
from plotagent.contracts.plots import PlotSpec, PreparedSeriesData, SafeRichText, SafeTextNode
from plotagent.contracts.rendering import OriginExportPlan, ResolvedAxis, ResolvedLayer
from plotagent.exports import export_png
from plotagent.origin import build_origin_export_spec, compile_origin_plan, export_origin
from plotagent.origin.models import OriginExportSuccess
from plotagent.origin.native import native_primitives, physical_plot_count
from plotagent.origin.validation import origin_canonical_hash
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable, ResolvedPlot
from plotagent.rendering.matplotlib import MatplotlibRenderer
from plotagent.rendering.policies import VOLCANO_THRESHOLDS
from tests.rendering.fixture_factory import build_plot_and_store

FIXTURE_DIR = (
    REPOSITORY / "tests" / "fixtures" / "visual_regression" / "x24_s07_synthetic"
)
DEFAULT_OUTPUT = REPOSITORY / "build" / "visual-audit" / "x24-s07-synthetic"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _plain(value: SafeRichText | None) -> str:
    return "" if value is None else "".join(node.text for node in value.nodes)


def _load_manifest() -> dict[str, Any]:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    if manifest["admission_class"] != "synthetic_generalized_visual_regression":
        raise RuntimeError("synthetic audit manifest has the wrong admission class")
    if manifest["origin_official_same_source_admission"] is not False:
        raise RuntimeError("synthetic fixtures must not enter Origin official admission")
    if not isinstance(manifest["generator"]["seed"], int):
        raise RuntimeError("synthetic audit seed must be frozen as an integer")
    return cast(dict[str, Any], manifest)


def _load_case(case: Mapping[str, Any]) -> pd.DataFrame:
    path = FIXTURE_DIR / str(case["data_file"])
    actual_hash = _sha256(path)
    if actual_hash != case["data_sha256"]:
        raise RuntimeError(
            f"frozen synthetic data hash differs for {case['case_id']}: {actual_hash}"
        )
    frame = pd.read_csv(path)
    expected_rows = int(case["expected"]["row_count"])
    if len(frame) != expected_rows:
        raise RuntimeError(f"row count differs for {case['case_id']}")
    return frame


def _resolved(case: Mapping[str, Any], frame: pd.DataFrame) -> tuple[PlotSpec, ResolvedPlot]:
    chart_id = str(case["chart_type_id"])
    case_id = str(case["case_id"])
    base, _ = build_plot_and_store(chart_id)
    field_ids = tuple(
        f"field:synthetic.{case_id.lower()}.{role}" for role in frame.columns
    )
    table = RenderTable.from_columns(
        {
            field_id: tuple(frame[role].tolist())
            for role, field_id in zip(frame.columns, field_ids, strict=True)
        }
    )
    prepared = PreparedDatasetRef(
        prepared_dataset_id=f"prepared:synthetic.{case_id.lower()}",
        prepared_version=1,
        content_hash=table.object_hash,
    )
    data = PreparedSeriesData(prepared_dataset_ref=prepared, role_fields=field_ids)
    series = base.series[0].model_copy(update={"data": data})
    labels = (
        {
            "axis:x": "Cause",
            "axis:y": "Count",
            "axis:y_right": "Cumulative (%)",
        }
        if chart_id == "X24"
        else {"axis:x": "log2 fold change", "axis:y": "-log10(p-value)"}
    )
    axes = tuple(
        axis.model_copy(update={"label": _text(labels[axis.axis_id])}) for axis in base.axes
    )
    plot = base.model_copy(
        update={
            "plot_id": f"plot:synthetic.{case_id.lower()}",
            "prepared_data_refs": (prepared,),
            "series": (series,),
            "axes": axes,
        }
    )
    resolved = PlotResolver().resolve(plot, RenderDataStore({table.object_hash: table}))
    return plot, resolved


def _axis(resolved: ResolvedPlot, panel_id: str, orientation: str) -> ResolvedAxis:
    return next(
        item
        for item in resolved.plan.axes
        if item.panel_id == panel_id and item.orientation == orientation
    )


def _roles(resolved: ResolvedPlot, layer: ResolvedLayer) -> dict[str, tuple[Any, ...]]:
    table = resolved.table_for(layer)
    return {binding.role: table.column(binding.field_id) for binding in layer.field_bindings}


def _assert_finite_geometry(resolved: ResolvedPlot) -> None:
    for layer in resolved.plan.layers:
        for role, values in _roles(resolved, layer).items():
            for value in values:
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and not math.isfinite(float(value))
                ):
                    raise RuntimeError(f"non-finite {layer.layer_id}/{role}")


def _assert_axis_coverage(resolved: ResolvedPlot) -> None:
    for layer in resolved.plan.layers:
        axes = {
            orientation: _axis(resolved, layer.panel_id, orientation)
            for orientation in ("x", "y")
        }
        roles = _roles(resolved, layer)
        candidates = {
            "x": tuple(roles.get("x", ())),
            "y": tuple(
                value
                for role in ("y", "height", "bottom", "top")
                for value in roles.get(role, ())
            ),
        }
        for orientation, values in candidates.items():
            axis = axes[orientation]
            assert axis.minimum is not None and axis.maximum is not None
            for value in values:
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric = float(value)
                    if not axis.minimum - 1e-10 <= numeric <= axis.maximum + 1e-10:
                        raise RuntimeError(
                            f"{layer.layer_id}/{orientation} geometry is outside axis"
                        )


def _assert_chart_semantics(
    case: Mapping[str, Any], frame: pd.DataFrame, resolved: ResolvedPlot
) -> dict[str, Any]:
    chart_id = str(case["chart_type_id"])
    if chart_id == "X24":
        bar = next(layer for layer in resolved.plan.layers if layer.geometry == "bar.single")
        line = next(layer for layer in resolved.plan.layers if layer.geometry == "xy.line")
        bar_roles = _roles(resolved, bar)
        line_roles = _roles(resolved, line)
        heights = tuple(float(value) for value in bar_roles["height"])
        widths = tuple(float(value) for value in bar_roles["width"])
        x_values = tuple(float(value) for value in bar_roles["x"])
        cumulative = tuple(float(value) for value in line_roles["y"])
        if heights != tuple(sorted(heights, reverse=True)):
            raise RuntimeError("Pareto bars did not sort descending")
        if not all(
            left < right
            for left, right in zip(cumulative[:-1], cumulative[1:], strict=True)
        ):
            raise RuntimeError("Pareto cumulative percentage is not increasing")
        if not math.isclose(cumulative[-1], 100.0, abs_tol=1e-12):
            raise RuntimeError("Pareto cumulative percentage does not end at 100")
        for left_x, left_width, right_x, right_width in zip(
            x_values[:-1], widths[:-1], x_values[1:], widths[1:], strict=True
        ):
            if left_x + left_width / 2 >= right_x - right_width / 2:
                raise RuntimeError("Pareto bars overlap")
        left_axis = _axis(resolved, "panel:left", "y")
        right_axis = _axis(resolved, "panel:right", "y")
        if left_axis.minimum is None or left_axis.minimum > 0:
            raise RuntimeError("Pareto count axis does not include zero")
        if right_axis.minimum is None or right_axis.maximum is None:
            raise RuntimeError("Pareto cumulative axis is unresolved")
        return {
            "input_rows": len(frame),
            "resolved_order": [
                str(item[0])
                for item in sorted(
                    zip(frame["category"], frame["value"], strict=True),
                    key=lambda item: float(item[1]),
                    reverse=True,
                )
            ],
            "bar_width": widths[0],
            "bar_gap": min(
                right_x - right_width / 2 - (left_x + left_width / 2)
                for left_x, left_width, right_x, right_width in zip(
                    x_values[:-1], widths[:-1], x_values[1:], widths[1:], strict=True
                )
            ),
            "cumulative_last": cumulative[-1],
            "left_y_range": [left_axis.minimum, left_axis.maximum],
            "right_y_range": [right_axis.minimum, right_axis.maximum],
        }

    class_layers = {
        _plain(layer.label): layer
        for layer in resolved.plan.layers
        if layer.geometry == "xy.symbol"
    }
    expected_classes = set(case["expected"]["classes"])
    if set(class_layers) != expected_classes:
        raise RuntimeError(f"volcano classes differ: {sorted(class_layers)}")
    class_colors = {
        label: layer.color.value if layer.color is not None else None
        for label, layer in class_layers.items()
    }
    if len(set(class_colors.values())) != len(class_colors):
        raise RuntimeError("volcano classes do not have distinct colors")
    plotted_points = [
        (float(x), float(y))
        for layer in class_layers.values()
        for x, y in zip(_roles(resolved, layer)["x"], _roles(resolved, layer)["y"], strict=True)
    ]
    if len(plotted_points) != len(frame) or len(set(plotted_points)) != len(plotted_points):
        raise RuntimeError("volcano point identity was lost or duplicated")
    x_axis = _axis(resolved, "panel:main", "x")
    if x_axis.minimum is None or x_axis.maximum is None or not math.isclose(
        abs(x_axis.minimum), abs(x_axis.maximum), rel_tol=0.0, abs_tol=1e-12
    ):
        raise RuntimeError("volcano X axis is not symmetric around zero")
    expected_pvalue = float(case["expected"]["threshold_pvalue"])
    expected_effect = float(case["expected"]["absolute_log2_fold_change_threshold"])
    if not math.isclose(expected_pvalue, VOLCANO_THRESHOLDS.pvalue, abs_tol=1e-12) or not math.isclose(
        expected_effect,
        VOLCANO_THRESHOLDS.absolute_log2_fold_change,
        abs_tol=1e-12,
    ):
        raise RuntimeError("synthetic manifest thresholds differ from the resolver policy")
    line_layers = {
        layer.layer_id.removeprefix("layer.0."): layer
        for layer in resolved.plan.layers
        if layer.geometry == "xy.line"
    }
    expected_line_ids = {
        "threshold.pvalue",
        "threshold.fold_change.negative",
        "threshold.fold_change.positive",
    }
    if set(line_layers) != expected_line_ids:
        raise RuntimeError(f"volcano threshold layers differ: {sorted(line_layers)}")
    pvalue_roles = _roles(resolved, line_layers["threshold.pvalue"])
    threshold_y = tuple(float(value) for value in pvalue_roles["y"])
    expected_threshold_y = -math.log10(expected_pvalue)
    if any(
        not math.isclose(value, expected_threshold_y, abs_tol=1e-12)
        for value in threshold_y
    ):
        raise RuntimeError("volcano significance threshold differs")
    fold_change_lines: dict[str, dict[str, tuple[Any, ...]]] = {}
    for direction, expected_x in (
        ("negative", -expected_effect),
        ("positive", expected_effect),
    ):
        roles = _roles(resolved, line_layers[f"threshold.fold_change.{direction}"])
        x_values = tuple(float(value) for value in roles["x"])
        y_values = tuple(float(value) for value in roles["y"])
        if any(not math.isclose(value, expected_x, abs_tol=1e-12) for value in x_values):
            raise RuntimeError(f"volcano {direction} fold-change threshold differs")
        if not math.isclose(y_values[0], 0.0, abs_tol=1e-12) or y_values[-1] < max(
            point[1] for point in plotted_points
        ):
            raise RuntimeError(f"volcano {direction} threshold does not span visible data")
        fold_change_lines[direction] = {"x": x_values, "y": y_values}
    return {
        "input_rows": len(frame),
        "class_counts": {
            label: len(_roles(resolved, layer)["x"]) for label, layer in class_layers.items()
        },
        "class_colors": class_colors,
        "x_range": [x_axis.minimum, x_axis.maximum],
        "threshold_y": threshold_y[0],
        "threshold_parameters": {
            "absolute_log2_fold_change": expected_effect,
            "pvalue": expected_pvalue,
        },
        "fold_change_lines": fold_change_lines,
    }


def _matplotlib_checks(resolved: ResolvedPlot) -> dict[str, Any]:
    figure = MatplotlibRenderer().build_figure(resolved)
    try:
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        page = figure.bbox
        hidden_axis_labels = {
            id(axis.xaxis.label) for axis in figure.axes if not axis.xaxis.get_visible()
        } | {id(axis.yaxis.label) for axis in figure.axes if not axis.yaxis.get_visible()}
        clipped: list[str] = []
        for text_object in figure.findobj(match=Text):
            if (
                not text_object.get_visible()
                or not text_object.get_text()
                or id(text_object) in hidden_axis_labels
            ):
                continue
            bounds = text_object.get_window_extent(renderer=renderer)
            if (
                bounds.x0 < page.x0 - 1
                or bounds.y0 < page.y0 - 1
                or bounds.x1 > page.x1 + 1
                or bounds.y1 > page.y1 + 1
            ):
                clipped.append(text_object.get_text())
        if clipped:
            raise RuntimeError(f"Matplotlib visible text is clipped: {clipped}")
        x_tick_overlap: list[tuple[str, str]] = []
        for axis in figure.axes:
            labels = [
                item
                for item in axis.get_xticklabels()
                if item.get_visible() and item.get_text()
            ]
            boxes = [item.get_window_extent(renderer=renderer) for item in labels]
            for index, left in enumerate(boxes):
                for right_index, right in enumerate(boxes[index + 1 :], start=index + 1):
                    if left.overlaps(right):
                        x_tick_overlap.append(
                            (labels[index].get_text(), labels[right_index].get_text())
                        )
        if x_tick_overlap:
            raise RuntimeError(f"Matplotlib X tick labels overlap: {x_tick_overlap}")
        legend_labels = sorted(
            {
                label
                for axis in figure.axes
                for label in axis.get_legend_handles_labels()[1]
                if label
            }
        )
        expected_labels = sorted(
            {
                _plain(layer.label)
                for layer in resolved.plan.layers
                if layer.label is not None
            }
        )
        if resolved.plan.legend.visible and legend_labels != expected_labels:
            raise RuntimeError("Matplotlib legend labels differ from resolved layers")
        return {
            "visible_text_clipped": False,
            "x_tick_overlap": False,
            "legend_labels": legend_labels,
        }
    finally:
        figure.clear()


def _rgb(value: str) -> tuple[int, int, int]:
    token = value.removeprefix("#")
    return tuple(int(token[index : index + 2], 16) for index in (0, 2, 4))


def _fresh_origin_readback(
    target: Path, output_png: Path, plan: OriginExportPlan
) -> dict[str, Any]:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        op.open(str(target), readonly=True)
        graphs = {graph.name: graph for graph in op.pages("g")}
        graph_reports: list[dict[str, Any]] = []
        for graph_plan in plan.graph_objects:
            graph = graphs.get(graph_plan.internal_name)
            if graph is None:
                raise RuntimeError(f"fresh Origin reopen lost {graph_plan.internal_name}")
            graph.save_fig(str(output_png), type="png", replace=True, width=1600)
            layer_reports: list[dict[str, Any]] = []
            expected_labels = [
                plot.label
                for layer in graph_plan.layers
                for plot in layer.plots
                if plot.label
            ]
            for layer_index, (layer_plan, layer) in enumerate(
                zip(graph_plan.layers, graph, strict=True)
            ):
                native_plots = layer.plot_list()
                expected_plot_count = sum(
                    physical_plot_count(primitive)
                    for plot in layer_plan.plots
                    for primitive in native_primitives(plot)
                )
                if len(native_plots) != expected_plot_count:
                    raise RuntimeError("fresh Origin native plot count differs")
                if any(not plot.obj.GetDatasetName() for plot in native_plots):
                    raise RuntimeError("fresh Origin plot lost its editable dataset link")
                expected_colors = [
                    _rgb(plot.color.value)
                    for plot in layer_plan.plots
                    if plot.color is not None
                    for _ in range(
                        sum(
                            physical_plot_count(primitive)
                            for primitive in native_primitives(plot)
                        )
                    )
                ]
                actual_colors = [tuple(int(value) for value in plot.color) for plot in native_plots]
                if actual_colors != expected_colors:
                    raise RuntimeError(
                        f"fresh Origin colors differ in {layer_plan.layer_id}: "
                        f"{actual_colors} != {expected_colors}"
                    )
                legend = layer.label("legend")
                legend_text = "" if legend is None else legend.text.replace("\r\n", "\n")
                if graph_plan.legend_visible and layer_index == 0:
                    if graph_plan.graph_id.startswith("graph.S07."):
                        expected_native_text = "\n".join(
                            f"\\l({index}) {label}"
                            for index, label in enumerate(expected_labels, 1)
                        )
                    else:
                        expected_native_text = "\n".join(expected_labels)
                    if legend_text != expected_native_text:
                        raise RuntimeError(
                            f"fresh Origin legend differs: {legend_text!r} != "
                            f"{expected_native_text!r}"
                        )
                layer_reports.append(
                    {
                        "layer_id": layer_plan.layer_id,
                        "native_plot_count": len(native_plots),
                        "dataset_links": [plot.obj.GetDatasetName() for plot in native_plots],
                        "colors_rgb": actual_colors,
                        "legend_text": legend_text,
                    }
                )
            graph_reports.append(
                {
                    "graph_name": graph.name,
                    "native_layer_count": len(graph),
                    "layers": layer_reports,
                }
            )
        return {
            "fresh_reopen": True,
            "native_graphs": True,
            "native_data_links": True,
            "raster_objects": False,
            "graph_reports": graph_reports,
        }
    finally:
        op.exit()


def _render_case(case: Mapping[str, Any], output: Path) -> dict[str, Any]:
    case_id = str(case["case_id"])
    chart_id = str(case["chart_type_id"])
    case_dir = output / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    frame = _load_case(case)
    plot, resolved = _resolved(case, frame)
    _, repeated = _resolved(case, frame)
    if resolved.render_plan_hash != repeated.render_plan_hash:
        raise RuntimeError(f"resolved plan is not deterministic for {case_id}")
    _assert_finite_geometry(resolved)
    _assert_axis_coverage(resolved)
    chart_checks = _assert_chart_semantics(case, frame, resolved)
    matplotlib_checks = _matplotlib_checks(resolved)

    (case_dir / "plot-spec.json").write_text(
        plot.model_dump_json(indent=2), encoding="utf-8"
    )
    (case_dir / "resolved-render-plan.json").write_text(
        resolved.plan.model_dump_json(indent=2), encoding="utf-8"
    )
    export_png(case_dir / "matplotlib-formal.png", resolved)
    export_spec = build_origin_export_spec(
        (resolved,),
        export_id=f"export:synthetic.{case_id.lower()}",
        output_name=f"{case_id}.opju",
    )
    origin_plan = compile_origin_plan((resolved,), export_spec)
    (case_dir / "origin-export-plan.json").write_text(
        origin_plan.model_dump_json(indent=2), encoding="utf-8"
    )
    target = case_dir / f"{case_id}.opju"
    result = export_origin(
        origin_plan,
        target,
        expected_existing_sha256=_sha256(target) if target.is_file() else None,
        timeout_seconds=120.0,
    )
    if not isinstance(result, OriginExportSuccess):
        raise RuntimeError(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    origin_readback = _fresh_origin_readback(
        target, case_dir / "origin-fresh-reopen.png", origin_plan
    )
    if result.build_validation != result.reopen_validation:
        raise RuntimeError(f"Origin fresh-reopen validation drift for {case_id}")
    readback = {
        "case_id": case_id,
        "chart_type_id": chart_id,
        "admission_class": "synthetic_generalized_visual_regression",
        "origin_official_same_source_admission": False,
        "data_sha256": case["data_sha256"],
        "plot_spec_sha256": _sha256(case_dir / "plot-spec.json"),
        "resolved_render_plan_sha256": resolved.render_plan_hash,
        "origin_plan_sha256": origin_canonical_hash(origin_plan),
        "origin_render_plan_sha256": result.render_plan_sha256,
        "matplotlib_png_sha256": _sha256(case_dir / "matplotlib-formal.png"),
        "opju_sha256": result.file_sha256,
        "origin_fresh_png_sha256": _sha256(case_dir / "origin-fresh-reopen.png"),
        "build_reopen_identical": True,
        "origin_validation_report_sha256": result.validation_report_sha256,
        "chart_checks": chart_checks,
        "matplotlib_checks": matplotlib_checks,
        "origin_readback": origin_readback,
    }
    (case_dir / "readback.json").write_text(
        json.dumps(readback, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return readback


def _assert_dynamic_pairs(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {str(item["case_id"]): item for item in results}
    x24_base = by_id["X24_baseline"]["chart_checks"]
    x24_expanded = by_id["X24_expanded"]["chart_checks"]
    if x24_expanded["input_rows"] <= x24_base["input_rows"]:
        raise RuntimeError("X24 expanded case did not grow the category count")
    if not math.isclose(x24_expanded["bar_width"], x24_base["bar_width"], abs_tol=1e-12):
        raise RuntimeError("X24 bar width changed unexpectedly with category count")
    if x24_expanded["bar_gap"] <= 0 or x24_base["bar_gap"] <= 0:
        raise RuntimeError("X24 bar gap is not positive")
    s07_base = by_id["S07_baseline"]["chart_checks"]
    s07_expanded = by_id["S07_expanded"]["chart_checks"]
    if s07_expanded["input_rows"] <= s07_base["input_rows"]:
        raise RuntimeError("S07 expanded case did not grow the point count")
    if abs(s07_expanded["x_range"][1]) <= abs(s07_base["x_range"][1]):
        raise RuntimeError("S07 expanded case did not expand the symmetric X range")
    return {
        "X24": "6 to 10 categories; positive non-overlapping bar gaps in both cases",
        "S07": "24 to 40 points; symmetric X range expands with effect range",
    }


def _data_table(frame: pd.DataFrame, limit: int = 12) -> str:
    head = frame.head(limit)
    headers = "".join(f"<th>{html.escape(str(column))}</th>" for column in head.columns)
    rows = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
        + "</tr>"
        for row in head.itertuples(index=False, name=None)
    )
    suffix = (
        f'<tr><td colspan="{len(head.columns)}">… {len(frame) - limit} more rows</td></tr>'
        if len(frame) > limit
        else ""
    )
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{rows}{suffix}</tbody></table>"


def _write_index(
    manifest: Mapping[str, Any], results: Sequence[Mapping[str, Any]], output: Path
) -> None:
    results_by_id = {str(item["case_id"]): item for item in results}
    cards: list[str] = []
    for case in manifest["cases"]:
        case_id = str(case["case_id"])
        frame = _load_case(case)
        result = results_by_id[case_id]
        cards.append(
            f"""<section class="card"><div class="card-head"><div><h2>{html.escape(case_id)}</h2>
<p><strong>{html.escape(str(case['chart_type_id']))}</strong> · {html.escape(str(case['risk']))}</p></div>
<span class="badge">synthetic generalized visual regression</span></div>
<div class="data"><h3>同一冻结合成数据</h3>{_data_table(frame)}
<p><code>SHA-256 {html.escape(str(case['data_sha256']))}</code></p></div>
<div class="images"><figure><figcaption>Matplotlib · formal</figcaption><a href="{case_id}/matplotlib-formal.png"><img src="{case_id}/matplotlib-formal.png" alt="{case_id} Matplotlib"></a></figure>
<figure><figcaption>Origin · O1 native · fresh reopen</figcaption><a href="{case_id}/origin-fresh-reopen.png"><img src="{case_id}/origin-fresh-reopen.png" alt="{case_id} Origin fresh reopen"></a></figure></div>
<p class="links"><a href="../../../tests/fixtures/visual_regression/x24_s07_synthetic/{html.escape(str(case['data_file']))}">CSV</a><a href="{case_id}/plot-spec.json">PlotSpec</a><a href="{case_id}/resolved-render-plan.json">ResolvedRenderPlan</a><a href="{case_id}/origin-export-plan.json">Origin plan</a><a href="{case_id}/{case_id}.opju">OPJU</a><a href="{case_id}/readback.json">readback</a></p>
<p class="pass">PASS · finite geometry · axis coverage · no bar/tick overlap · no visible-text clipping · native editable data links · build/fresh-reopen identical</p>
<details><summary>关键读回摘要</summary><pre>{html.escape(json.dumps(result['chart_checks'], ensure_ascii=False, indent=2))}</pre></details></section>"""
        )
    document = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>X24 / S07 合成泛化视觉回归</title>
<style>:root{{font-family:Inter,"Microsoft YaHei",system-ui,sans-serif;color:#18212f;background:#edf1f6}}body{{margin:0}}main{{max-width:1500px;margin:auto;padding:32px}}h1{{margin-bottom:8px}}.notice{{background:#fff2cf;border:1px solid #e4b84b;border-radius:12px;padding:14px 18px;line-height:1.6}}.card{{background:#fff;border-radius:16px;margin:24px 0;padding:22px;box-shadow:0 5px 24px #1b2b4314}}.card-head{{display:flex;gap:18px;justify-content:space-between;align-items:start}}h2{{margin:0}}.badge{{background:#e8f1ff;color:#1859ae;padding:7px 10px;border-radius:999px;font-size:12px;white-space:nowrap}}.images{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}}figure{{margin:0;border:1px solid #dce2ea;border-radius:10px;overflow:hidden;background:#f7f9fc}}figcaption{{padding:10px 12px;font-weight:650;background:#f0f4f9}}img{{display:block;width:100%;height:430px;object-fit:contain;background:#fff}}table{{border-collapse:collapse;font-size:12px;max-width:100%}}th,td{{padding:5px 9px;border:1px solid #dce2ea;text-align:left}}th{{background:#f3f6fa}}code,pre{{font-family:ui-monospace,Consolas,monospace;font-size:12px}}.links{{display:flex;gap:14px;flex-wrap:wrap}}a{{color:#145fb8}}.pass{{color:#176a45;font-weight:650}}details{{background:#f6f8fb;padding:10px 12px;border-radius:8px}}@media(max-width:850px){{main{{padding:16px}}.images{{grid-template-columns:1fr}}.card-head{{display:block}}.badge{{display:inline-block}}}}</style>
<main><h1>X24 / S07 合成泛化视觉回归</h1><p>生成器 <code>{html.escape(str(manifest['generator']['name']))} {html.escape(str(manifest['generator']['version']))}</code> · seed <code>{manifest['generator']['seed']}</code></p>
<div class="notice"><strong>证据边界：</strong>本页只验证冻结合成数据在 PlotAgent 两个渲染器中的泛化表现。没有 Origin 官方参考图，不伪造 reference，也不计入 Origin 官方同源 visual admission。每个案例的 Matplotlib 与 Origin 都由页面所链接的同一 PlotSpec 和同一 ResolvedRenderPlan 产生。</div>
{"".join(cards)}</main></html>"""
    (output / "index.html").write_text(document, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--case", dest="case_ids", action="append")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    known_ids = {str(case["case_id"]) for case in manifest["cases"]}
    selected_ids = set(args.case_ids or known_ids)
    if unknown := selected_ids - known_ids:
        raise SystemExit(f"unknown audit cases: {', '.join(sorted(unknown))}")
    results: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        case_id = str(case["case_id"])
        if case_id in selected_ids:
            results.append(_render_case(case, output))
            continue
        readback_path = output / case_id / "readback.json"
        if not readback_path.is_file():
            raise RuntimeError(f"unselected case has no existing audit result: {case_id}")
        results.append(json.loads(readback_path.read_text(encoding="utf-8")))
    pair_checks = _assert_dynamic_pairs(results)
    suite = {
        "suite_id": manifest["suite_id"],
        "generator": manifest["generator"],
        "admission_class": manifest["admission_class"],
        "origin_official_same_source_admission": False,
        "pair_checks": pair_checks,
        "cases": results,
    }
    (output / "manifest.json").write_text(
        json.dumps(suite, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_index(manifest, results, output)
    print(output / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
