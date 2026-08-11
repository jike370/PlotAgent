"""X09 official FLOATBAR template binder with native XYY intervals."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

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
from plotagent.engine.profile_data import FloatingIntervalData, x09_floating_intervals
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X09_ORIGIN_PROFILE, resolve_official_template

_FLOATING_COLUMN = 207
_TITLE_NAME = "_ENGINE_TITLE"


def _safe_label(value: str) -> str:
    return "".join(
        f"\\x({ord(character):04X})" if character in {"\\", "%", "$"} else character
        for character in value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    ).strip()


class X09OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.segments: tuple[tuple[Any, ...], ...] = ()

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, X09_ORIGIN_PROFILE)
        intervals = x09_floating_intervals(document, data)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the X09 data workbook")
        self.sheet = book[0]
        self._write_data(intervals)
        self.graph = self.op.new_graph(
            f"G{token}",
            template=str(template.with_suffix(template.suffix.lower())),
            hidden=True,
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create a graph from FLOATBAR.OTP")
        self.layer = self.graph[0]
        boundaries = ((1, 2), (2, 3)) if intervals.middle_values is not None else ((1, 2),)
        segments: list[tuple[Any, ...]] = []
        for lower, upper in boundaries:
            before = len(self.layer.plot_list())
            data_range = self.op.make_DataRange(
                "X", self.sheet.obj[0], "Y", self.sheet.obj[lower], "Y", self.sheet.obj[upper]
            )
            native = self.layer.obj.AddPlot(data_range, _FLOATING_COLUMN, True)
            if native is None or not native.IsValid():
                raise RuntimeError("Origin FLOATBAR.OTP rejected one native interval segment")
            created = tuple(self.layer.plot_list()[before:])
            if len(created) != 2:
                raise RuntimeError("one native X09 interval must create exactly two boundary plots")
            self.layer.group(True, before, before + 1)
            segments.append(created)
        self.segments = tuple(segments)
        self.layer.rescale()

    def reopen(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError("fresh Origin session could not reopen the staged X09 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("fresh X09 project has unexpected graph or workbook count")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = tuple(self.layer.plot_list())
        if len(plots) not in {2, 4}:
            raise RuntimeError("fresh X09 project has an invalid native boundary count")
        self.segments = tuple(tuple(plots[index : index + 2]) for index in range(0, len(plots), 2))
        self.sheet = books[0][0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        intervals = x09_floating_intervals(document, data)
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("X09 title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None:
                label = self.layer.add_label(action.text, 40, 2)
                if label is None:
                    raise RuntimeError("Origin could not create the X09 title")
                label.name = _TITLE_NAME
            label.text = action.text
            label.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("X09 axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if axis_name == "x" and action.scale != "categorical":
                    raise ValueError("Origin X09 category axis supports only categorical scale")
                if axis_name == "y" and action.scale not in {"linear", "log10"}:
                    raise ValueError("Origin X09 interval axis supports only linear or log10")
                if axis_name == "y":
                    axis.scale = action.scale
            if action.minimum is not None and action.maximum is not None:
                begin, end = action.minimum, action.maximum
                if action.reverse:
                    begin, end = end, begin
                axis.set_limits(begin, end)
            elif action.reverse is not None:
                begin, end, step = (float(value) for value in axis.limits)
                should_reverse = begin < end if action.reverse else begin > end
                if should_reverse:
                    axis.set_limits(end, begin, abs(step))
            if action.label is not None:
                label = self.layer.label("xb" if axis_name == "x" else "yl")
                if label is None:
                    label = self.layer.add_label(action.label)
                if label is None:
                    raise RuntimeError("Origin X09 template has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            target = {
                f"series:{token}.lower": 0,
                f"series:{token}.upper": 1,
            }.get(action.target)
            if target is None or target >= len(self.segments):
                raise ValueError("X09 series target is outside the bound interval data")
            if any(
                value is not None
                for value in (action.line_style, action.symbol, action.symbol_size_pt)
            ):
                raise ValueError("Origin X09 exposes interval color and edge width only")
            for index, plot in enumerate(self.segments[target]):
                # A native floating column is represented by a grouped pair:
                # the first boundary plot owns the visible fill colour while
                # the second remains the native edge/boundary source.  Origin
                # restores the latter from its group list after reopen, so
                # claiming that both plots retain an arbitrary colour would be
                # a false public capability.
                if action.color is not None and index == 0:
                    plot.color = action.color
                if action.line_width_pt is not None:
                    plot.set_float("line.width", action.line_width_pt)
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main" or action.anchor is not None:
                raise ValueError("X09 legend target or anchor is not supported")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError("Origin could not create the X09 legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                labels = (
                    (intervals.end_field_name,)
                    if intervals.middle_values is None
                    else (cast(str, intervals.middle_field_name), intervals.end_field_name)
                )
                legend.text = "\n".join(
                    f"\\l({index * 2}) {_safe_label(label)}"
                    for index, label in enumerate(labels, start=1)
                )
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin X09 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty X09 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        intervals = x09_floating_intervals(document, data)
        expected_columns: tuple[tuple[object, ...], ...] = (
            intervals.categories,
            intervals.start_values,
            intervals.middle_values or intervals.end_values,
            intervals.end_values,
        )
        for index, expected in enumerate(expected_columns):
            actual = tuple(self.sheet.to_list(index))
            if len(actual) != len(expected) or any(
                str(found) != str(wanted)
                if isinstance(wanted, str)
                else abs(float(cast(Any, found)) - float(cast(Any, wanted))) > 1e-12
                for found, wanted in zip(actual, expected, strict=True)
            ):
                raise RuntimeError(f"Origin X09 data column {index} differs after reopen")
        expected_segments = 2 if intervals.middle_values is not None else 1
        if len(self.segments) != expected_segments:
            raise RuntimeError("Origin X09 segment count differs after reopen")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {"segment_count": len(self.segments)}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError("Origin X09 title did not survive readback")
            elif isinstance(action, SetSeriesStyle):
                ordinal = 0 if action.target == f"series:{token}.lower" else 1
                if ordinal >= len(self.segments):
                    raise RuntimeError("Origin X09 series disappeared after reopen")
                if action.color is not None:
                    expected_color = tuple(
                        int(action.color[index : index + 2], 16) for index in (1, 3, 5)
                    )
                    if tuple(self.segments[ordinal][0].color) != expected_color:
                        raise RuntimeError("Origin X09 segment color did not survive readback")
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError("Origin X09 legend visibility did not survive readback")
        objects = [
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
                semantic_id=f"series:{token}.lower",
                backend="origin",
                object_kind="native_floating_interval",
                native_ref=f"graph:{self.graph.name}.layer:1.plots:1-2",
            ),
        ]
        if len(self.segments) == 2:
            objects.append(
                EngineObjectRef(
                    semantic_id=f"series:{token}.upper",
                    backend="origin",
                    object_kind="native_floating_interval",
                    native_ref=f"graph:{self.graph.name}.layer:1.plots:3-4",
                )
            )
        objects.append(
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            )
        )
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, snapshot)),
        )

    def _write_data(self, intervals: FloatingIntervalData) -> None:
        columns: tuple[tuple[str, tuple[object, ...], str], ...] = (
            (intervals.category_field_name, intervals.categories, "X"),
            (intervals.start_field_name, intervals.start_values, "Y"),
            (
                intervals.middle_field_name or intervals.end_field_name,
                intervals.middle_values or intervals.end_values,
                "Y",
            ),
            (intervals.end_field_name, intervals.end_values, "Y"),
        )
        for index, (label, values, axis) in enumerate(columns):
            self.sheet.from_list(index, list(values), lname=label, axis=axis)


def execute_x09_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    project = X09OriginProject(op)
    project.create(install_dir, request.document, request.data)
    for action in request.actions:
        project.apply(request.document, action, request.data)
    project.save(output)
    reopened = X09OriginProject(op)
    reopened.reopen(output)
    return reopened.verify(request.document, request.actions, request.data)
