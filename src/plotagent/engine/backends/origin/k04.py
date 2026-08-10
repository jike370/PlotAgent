"""K04 bound to Origin's official bubble template with opt-in scales."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
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
    SetChartParameter,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import K04BubbleData, k04_bubble
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K04_ORIGIN_PROFILE, resolve_official_template

_BUBBLE_SCALE_NAME = "BUBBLELEGEND1"
_COLOR_SCALE_NAME = "SPECTRUM1"
_BUBBLE_SCALE_OBJECT_TYPE = 29
_COLOR_SCALE_OBJECT_TYPE = 13
_TITLE_NAME = "_ENGINE_TITLE"
_SYMBOL_CODES = {"square": 1, "circle": 2, "triangle": 3, "triangle_up": 3, "diamond": 5}


@dataclass(frozen=True, slots=True)
class _K04State:
    title: str = ""
    color_scale_visible: bool = False
    size_key_visible: bool = False


def _effective_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[PlotEngineAction, ...]:
    """Discard data-dependent style/scale edits made before the last rebind."""

    last_binding = max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    return tuple(
        action
        for index, action in enumerate(actions)
        if not (index < last_binding and isinstance(action, (SetSeriesStyle, SetChartParameter)))
    )


class K04OriginProject:
    """One native bubble plot; the official template remains style authority."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, K04_ORIGIN_PROFILE)
        bubble = k04_bubble(document, data)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K04 workbook")
        self.sheet = book[0]
        columns = self._write_data(bubble)
        self.graph = self.op.new_graph(
            f"G{token}",
            template=str(template.with_suffix(template.suffix.lower())),
            hidden=True,
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create K04 from bubble.otpu")
        self.layer = self.graph[0]
        self.plot = self.layer.add_plot(self.sheet, coly=1, colx=0, type="s")
        if self.plot is None:
            raise RuntimeError("Origin bubble.otpu rejected the native scatter plot")
        if columns.get("size") is not None:
            self.plot.symbol_size = self.op.modi_col(cast(int, columns["size"]) - 1)
        if columns.get("color") is not None:
            self.plot.color = self.op.color_col(cast(int, columns["color"]) - 1, "m")
        self.layer.rescale()
        # bubble.otpu contains BUBBLELEGEND1.  Template presence is not user
        # intent, so both explanatory scales are explicitly hidden by default.
        self._set_auxiliary(_BUBBLE_SCALE_NAME, _BUBBLE_SCALE_OBJECT_TYPE, False)
        self._set_auxiliary(_COLOR_SCALE_NAME, _COLOR_SCALE_OBJECT_TYPE, False)

    def reopen(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError("fresh Origin session could not reopen the staged K04 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("fresh K04 project has unexpected graph or workbook count")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = list(self.layer.plot_list())
        if len(plots) != 1:
            raise RuntimeError("fresh K04 project must contain one native bubble plot")
        self.plot = plots[0]
        self.sheet = books[0][0]

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> None:
        bubble = k04_bubble(document, data)
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K04 title target does not belong to this plot")
            title = self.layer.label(_TITLE_NAME)
            if title is None:
                title = self.layer.add_label(action.text, 40, 2)
                if title is None:
                    raise RuntimeError("Origin could not create the K04 title")
                title.name = _TITLE_NAME
            title.text = action.text
            title.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("K04 axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if action.scale not in {"linear", "log10"}:
                    raise ValueError("Origin K04 axes support only linear or log10")
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
                label_name = "xb" if axis_name == "x" else "yl"
                label = self.layer.label(label_name)
                if label is None:
                    label = self.layer.add_label(action.label)
                if label is None:
                    raise RuntimeError("Origin K04 template has no writable axis label")
                label.name = label_name
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            if action.target != f"series:{token}.primary":
                raise ValueError("K04 series target does not belong to this plot")
            if action.color is not None:
                if bubble.color_values is not None:
                    raise ValueError("K04 fixed series color conflicts with the bound color field")
                self.plot.color = action.color
            if action.symbol is not None:
                try:
                    self.plot.symbol_kind = _SYMBOL_CODES[action.symbol]
                except KeyError as error:
                    raise ValueError(
                        f"Origin K04 does not support symbol {action.symbol}"
                    ) from error
            if action.symbol_size_pt is not None:
                if bubble.size_values is None:
                    self.plot.symbol_size = action.symbol_size_pt
                else:
                    maximum = max(value for value in bubble.size_values if value == value)
                    self.plot.symbol_sizefactor = (
                        0.0 if maximum <= 0 else action.symbol_size_pt / maximum
                    )
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("K04 legend target does not belong to this plot")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError("Origin could not create the K04 series legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                legend.text = f"\\l(1) {bubble.y_field_name}"
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        if isinstance(action, SetChartParameter):
            if action.target != document.plot_id or not isinstance(action.value, bool):
                raise ValueError("K04 scale parameters require the plot target and a boolean")
            if action.parameter == "color_scale_visible":
                if action.value and bubble.color_values is None:
                    raise ValueError("K04 color scale requires a color binding")
                self._set_auxiliary(
                    _COLOR_SCALE_NAME,
                    _COLOR_SCALE_OBJECT_TYPE,
                    action.value,
                )
            elif action.parameter == "size_key_visible":
                if action.value and bubble.size_values is None:
                    raise ValueError("K04 size key requires a size binding")
                self._set_auxiliary(
                    _BUBBLE_SCALE_NAME,
                    _BUBBLE_SCALE_OBJECT_TYPE,
                    action.value,
                )
            else:
                raise ValueError(f"Origin K04 does not support parameter {action.parameter}")
            return
        raise ValueError(f"Origin K04 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty K04 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        bubble = k04_bubble(document, data)
        expected_columns = self._column_values(bubble)
        for index, (role, expected) in enumerate(expected_columns):
            actual = tuple(self.sheet.to_list(index))
            if len(actual) != len(expected):
                raise RuntimeError(f"Origin K04 {role} row count differs after reopen")
            for observed, wanted in zip(actual, expected, strict=True):
                if observed is None and wanted != wanted:
                    continue
                if abs(float(observed) - wanted) > 1e-12:
                    raise RuntimeError(f"Origin K04 {role} values differ after reopen")
        state = self._state(document, actions, bubble)
        self._assert_auxiliary(_COLOR_SCALE_NAME, state.color_scale_visible)
        self._assert_auxiliary(_BUBBLE_SCALE_NAME, state.size_key_visible)
        token = document.plot_id.removeprefix("plot:")
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError("Origin K04 title did not survive readback")
            elif isinstance(action, SetAxis):
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                axis = self.layer.axis(axis_name)
                if action.scale is not None and axis.scale != action.scale:
                    raise RuntimeError("Origin K04 axis scale did not survive readback")
                if action.label is not None:
                    label = self.layer.label("xb" if axis_name == "x" else "yl")
                    if label is None or label.text != action.label:
                        raise RuntimeError("Origin K04 axis label did not survive readback")
            elif isinstance(action, SetSeriesStyle):
                if action.color is not None:
                    expected_color = tuple(
                        int(action.color[index : index + 2], 16) for index in (1, 3, 5)
                    )
                    if tuple(self.plot.color) != expected_color:
                        raise RuntimeError("Origin K04 series color did not survive readback")
                if (
                    action.symbol is not None
                    and self.plot.symbol_kind != _SYMBOL_CODES[action.symbol]
                ):
                    raise RuntimeError("Origin K04 symbol did not survive readback")
                if action.symbol_size_pt is not None:
                    if bubble.size_values is None:
                        actual_size = float(self.plot.symbol_size)
                        expected_size = action.symbol_size_pt
                    else:
                        maximum = max(value for value in bubble.size_values if value == value)
                        actual_size = float(self.plot.symbol_sizefactor)
                        expected_size = 0.0 if maximum <= 0 else action.symbol_size_pt / maximum
                    if abs(actual_size - expected_size) > 0.01:
                        raise RuntimeError("Origin K04 symbol size did not survive readback")
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                actual_visible = legend is not None and bool(legend.get_int("show"))
                if actual_visible != action.visible:
                    raise RuntimeError("Origin K04 legend visibility did not survive readback")
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
                semantic_id=f"series:{token}.primary",
                backend="origin",
                object_kind="bubble_series",
                native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
            ),
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            ),
        ]
        if state.color_scale_visible:
            objects.append(
                EngineObjectRef(
                    semantic_id=f"legend:{token}.color_scale",
                    backend="origin",
                    object_kind="color_scale",
                    native_ref=f"graph:{self.graph.name}.layer:1.label:{_COLOR_SCALE_NAME}",
                )
            )
        if state.size_key_visible:
            objects.append(
                EngineObjectRef(
                    semantic_id=f"legend:{token}.size_key",
                    backend="origin",
                    object_kind="size_key",
                    native_ref=f"graph:{self.graph.name}.layer:1.label:{_BUBBLE_SCALE_NAME}",
                )
            )
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "state": asdict(state),
                        "actions": [action.model_dump(mode="json") for action in actions],
                    },
                )
            ),
        )

    def _write_data(self, bubble: K04BubbleData) -> dict[str, int | None]:
        columns: dict[str, int | None] = {"x": 0, "y": 1, "size": None, "color": None}
        self.sheet.from_list(0, list(bubble.x_values), lname=bubble.x_field_name, axis="X")
        self.sheet.from_list(1, list(bubble.y_values), lname=bubble.y_field_name, axis="Y")
        next_column = 2
        if bubble.size_values is not None:
            columns["size"] = next_column
            self.sheet.from_list(
                next_column,
                list(bubble.size_values),
                lname=bubble.size_field_name or "Size",
                axis="N",
            )
            next_column += 1
        if bubble.color_values is not None:
            columns["color"] = next_column
            self.sheet.from_list(
                next_column,
                list(bubble.color_values),
                lname=bubble.color_field_name or "Color",
                axis="N",
            )
        return columns

    @staticmethod
    def _column_values(bubble: K04BubbleData) -> tuple[tuple[str, tuple[float, ...]], ...]:
        values: list[tuple[str, tuple[float, ...]]] = [
            ("x", bubble.x_values),
            ("y", bubble.y_values),
        ]
        if bubble.size_values is not None:
            values.append(("size", bubble.size_values))
        if bubble.color_values is not None:
            values.append(("color", bubble.color_values))
        return tuple(values)

    def _set_auxiliary(self, name: str, object_type: int, visible: bool) -> None:
        label = self.layer.label(name)
        if visible and label is None:
            self.layer.activate()
            native = self.layer.obj.GraphObjects.Add(object_type)
            if native is None or not native.IsValid():
                raise RuntimeError(f"Origin could not create K04 auxiliary object {name}")
            label = self.op.Label(native, self.layer.obj)
            label.name = name
        if label is not None:
            label.set_int("show", int(visible))

    def _assert_auxiliary(self, name: str, visible: bool) -> None:
        label = self.layer.label(name)
        actual = label is not None and bool(label.get_int("show"))
        if actual != visible:
            raise RuntimeError(f"Origin K04 auxiliary visibility differs for {name}")

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        bubble: K04BubbleData,
    ) -> _K04State:
        state = _K04State()
        for action in actions:
            if isinstance(action, SetTitle):
                state = replace(state, title=action.text)
            elif isinstance(action, SetChartParameter):
                if action.parameter == "color_scale_visible":
                    if action.value and bubble.color_values is None:
                        raise ValueError("K04 color scale requires a color binding")
                    state = replace(state, color_scale_visible=bool(action.value))
                elif action.parameter == "size_key_visible":
                    if action.value and bubble.size_values is None:
                        raise ValueError("K04 size key requires a size binding")
                    state = replace(state, size_key_visible=bool(action.value))
        return state


def execute_k04_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = K04OriginProject(op)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    for action in actions:
        project.apply(request.document, action, request.data)
    project.save(output)

    reopened = K04OriginProject(op)
    reopened.reopen(output)
    return reopened.verify(request.document, actions, request.data)
