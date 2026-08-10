"""K19 official TimeSeries template binder with native datetime data."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import k19_time_series
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K19_ORIGIN_PROFILE, resolve_official_template

_TITLE_NAME = "_ENGINE_TITLE"
_LINE_STYLE_CODES = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3, "none": 10}
_SYMBOL_CODES = {"none": 0, "square": 1, "circle": 2, "triangle": 3, "diamond": 5}


def _safe_label(value: str) -> str:
    return "".join(
        f"\\x({ord(character):04X})" if character in {"\\", "%", "$"} else character
        for character in value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    ).strip()


class K19OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, K19_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K19 workbook")
        self.sheet = book[0]
        self._write_data(document, data)
        self.graph = self.op.new_graph(
            f"G{token}", template=str(template.with_suffix(template.suffix.lower())), hidden=True
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create K19 from TimeSeries.otp")
        self.layer = self.graph[0]
        self.plot = self.layer.add_plot(self.sheet, coly=1, colx=0, type="?")
        if self.plot is None:
            raise RuntimeError("Origin TimeSeries.otp rejected the native datetime line")
        self.layer.rescale()

    def open(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not open the previous K19 project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K19 project must contain one graph and one workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = self.layer.plot_list()
        if len(plots) != 1:
            raise RuntimeError("K19 project must contain one native datetime plot")
        self.plot = plots[0]
        self.sheet = books[0][0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, CreatePlot):
            return
        if isinstance(action, BindFields):
            self._write_data(document, data)
            self.layer.rescale()
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K19 title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None:
                label = self.layer.add_label(action.text, 40, 2)
                if label is None:
                    raise RuntimeError("Origin could not create the K19 title")
                label.name = _TITLE_NAME
            label.text = action.text
            label.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("K19 axis target does not belong to this plot")
            expected_scale = "datetime" if axis_name == "x" else "linear"
            if action.scale not in {None, expected_scale}:
                raise ValueError(f"K19 {axis_name} axis requires {expected_scale} scale")
            if action.minimum is not None or action.maximum is not None:
                raise ValueError("K19 public datetime axes do not expose numeric bounds")
            if action.reverse is not None:
                axis = self.layer.axis(axis_name)
                begin, end, step = (float(value) for value in axis.limits)
                should_reverse = begin < end if action.reverse else begin > end
                if should_reverse:
                    axis.set_limits(end, begin, abs(step))
            if action.label is not None:
                label = self.layer.label("xb" if axis_name == "x" else "yl")
                if label is None:
                    label = self.layer.add_label(action.label)
                if label is None:
                    raise RuntimeError("Origin TimeSeries.otp has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            if action.target != f"series:{token}.primary":
                raise ValueError("K19 series target does not belong to this plot")
            if action.color is not None:
                self.plot.color = action.color
            if action.line_width_pt is not None:
                self.plot.set_float("line.width", action.line_width_pt)
            if action.line_style is not None:
                self.plot.set_int("line.style", _LINE_STYLE_CODES[action.line_style])
            if action.symbol is not None:
                try:
                    self.plot.symbol_kind = _SYMBOL_CODES[action.symbol]
                except KeyError as error:
                    raise ValueError(
                        f"Origin K19 does not support symbol {action.symbol}"
                    ) from error
            if action.symbol_size_pt is not None:
                self.plot.symbol_size = action.symbol_size_pt
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("K19 legend target does not belong to this plot")
            if action.anchor not in {None, "inside"}:
                raise ValueError("K19 currently exposes only the template legend anchor")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError("Origin could not create the linked K19 legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                legend_label = _safe_label(k19_time_series(document, data).value_field_name)
                legend.text = f"\\l(1) {legend_label}"
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin K19 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty K19 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        expected = k19_time_series(document, data)
        frame = self.sheet.to_df()
        observed_times = tuple(pd.to_datetime(frame.iloc[:, 0]).dt.to_pydatetime())
        if observed_times != expected.time_values:
            raise RuntimeError("Origin K19 datetime values differ after reopen")
        observed_values = frame.iloc[:, 1].to_numpy(dtype=float)
        if not np.allclose(observed_values, expected.values, rtol=0, atol=1e-12, equal_nan=True):
            raise RuntimeError("Origin K19 values differ after reopen")
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError("Origin K19 title did not survive readback")
                style_snapshot["title"] = action.text
            elif isinstance(action, SetAxis) and action.label is not None:
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                label = self.layer.label("xb" if axis_name == "x" else "yl")
                if label is None or label.text != action.label:
                    raise RuntimeError("Origin K19 axis label did not survive readback")
                style_snapshot[f"axis_{axis_name}"] = action.label
            elif isinstance(action, SetSeriesStyle):
                style_snapshot["series"] = {
                    "line_width": self.plot.get_float("line.width"),
                    "line_style": self.plot.get_int("line.style"),
                    "symbol_kind": self.plot.symbol_kind,
                }
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError("Origin K19 legend visibility did not survive readback")
                style_snapshot["legend"] = action.visible
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=(
                EngineObjectRef(
                    semantic_id=document.plot_id,
                    backend="origin",
                    object_kind="graph",
                    native_ref=f"graph:{self.graph.name}",
                ),
                EngineObjectRef(
                    semantic_id=f"axis:{token}.x",
                    backend="origin",
                    object_kind="axis",
                    native_ref=f"graph:{self.graph.name}.layer:1.axis:x",
                ),
                EngineObjectRef(
                    semantic_id=f"axis:{token}.y",
                    backend="origin",
                    object_kind="axis",
                    native_ref=f"graph:{self.graph.name}.layer:1.axis:y",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.primary",
                    backend="origin",
                    object_kind="datetime_line",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, style_snapshot)),
        )

    def _write_data(self, document: PlotDocument, data: EngineDataView) -> None:
        series = k19_time_series(document, data)
        self.sheet.from_df(
            pd.DataFrame(
                {
                    series.time_field_name: pd.to_datetime(series.time_values),
                    series.value_field_name: series.values,
                }
            )
        )
        self.sheet.cols_axis("xy")


def execute_k19_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K19OriginProject(op)
    if request.previous_opju is None:
        project.create(install_dir, request.document, request.data)
        pending: tuple[PlotEngineAction, ...] = request.actions
    else:
        project.open(Path(request.previous_opju))
        pending = request.actions[-1:]
    for action in pending:
        project.apply(request.document, action, request.data)
    project.save(output)
    reopened = K19OriginProject(op)
    reopened.open(output)
    return reopened.verify(request.document, request.actions, request.data)
