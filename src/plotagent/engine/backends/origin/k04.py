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
    SetChartParameter,
    SetPointMarkerMap,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import (
    K04BubbleData,
    PointMarkerShapeData,
    k04_bubble,
    point_marker_shapes,
)
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K04_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_BUBBLE_SCALE_NAME = "BUBBLELEGEND1"
_COLOR_SCALE_NAME = "SPECTRUM1"
_BUBBLE_SCALE_OBJECT_TYPE = 29
_COLOR_SCALE_OBJECT_TYPE = 13
_TITLE_NAME = "_ENGINE_TITLE"
_SYMBOL_CODES = {
    "square": 1,
    "circle": 2,
    "triangle": 3,
    "triangle_up": 3,
    "triangle_down": 4,
    "diamond": 5,
}
_OFFICIAL_HELP_URL = "https://docs.originlab.com/origin-help/bubble-color-map-graph/"
_OFFICIAL_MENU = "Plot > Basic 2D: Bubble + Color Mapped"


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
        if not (
            index < last_binding
            and isinstance(action, (SetChartParameter, SetPointMarkerMap))
        )
    )


class K04OriginProject:
    """One native bubble plot; the official template remains style authority."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None
        self.book: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": K04_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K04_ORIGIN_PROFILE)
        bubble = k04_bubble(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K04 workbook")
        self.book = book
        self.sheet = book[0]
        with origin_trace_step(
            "source_data_write",
            details={"designation": "XYYY", "row_count": len(bubble.x_values)},
        ):
            columns = self._write_data(bubble)
        plot_id, plot_template = self._official_plot_route(bubble)
        column_count = len(self._column_values(bubble))
        command = f"worksheet -s 1 0 {column_count} 0; worksheet -p {plot_id} {plot_template};"
        with origin_trace_step(
            "official_plot_command_execute",
            details={
                "labtalk": command,
                "native_plot_type": plot_id,
                "official_help_url": _OFFICIAL_HELP_URL,
                "official_menu": _OFFICIAL_MENU,
                "template_filename": template.name,
            },
        ):
            self.sheet.activate()
            if not self.op.lt_exec(command):
                raise RuntimeError("Origin could not execute the official K04 Bubble menu")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin Bubble menu must create exactly one graph")
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"K04 Bubble / {document.plot_id}"
        self.layer = self.graph[0]
        plots = list(self.layer.plot_list())
        if len(plots) != 1:
            raise RuntimeError("Origin Bubble menu must create one native bubble plot")
        self.plot = plots[0]
        with origin_trace_step("template_residue_remove"):
            for residue in tuple(self.op.pages("w")):
                if residue.name != book.name:
                    residue.destroy()
        self.layer.rescale()
        # The official Bubble + Color Mapped menu creates Bubble Scale itself.
        # Color Scale is optional in Origin and remains opt-in in PlotAgent.
        self._assert_auxiliary(_BUBBLE_SCALE_NAME, bubble.size_values is not None)
        color_scale = self.layer.label(_COLOR_SCALE_NAME)
        if color_scale is not None:
            color_scale.set_int("show", 0)
        native = self._assert_native_structure(bubble, columns, plot_id, None)
        record_origin_trace("native_bubble_confirmed", "completed", details=native)

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
        self.book = books[0]
        self.sheet = self.book[0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        bubble = k04_bubble(document, data)
        document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetChartParameter):
            if action.target != document.plot_id or not isinstance(action.value, bool):
                raise ValueError("K04 scale parameters require the plot target and a boolean")
            if action.parameter == "color_scale_visible":
                if action.value and bubble.color_values is None:
                    raise ValueError("K04 color scale requires a color binding")
                self._set_auxiliary(_COLOR_SCALE_NAME, _COLOR_SCALE_OBJECT_TYPE, action.value)
            elif action.parameter == "size_key_visible":
                if action.value and bubble.size_values is None:
                    raise ValueError("K04 size key requires a size binding")
                self._set_auxiliary(_BUBBLE_SCALE_NAME, _BUBBLE_SCALE_OBJECT_TYPE, action.value)
            else:
                raise ValueError(f"Origin K04 does not support parameter {action.parameter}")
            return
        if isinstance(action, SetPointMarkerMap):
            token = document.plot_id.removeprefix("plot:")
            if action.target != f"series:{token}.primary":
                raise ValueError("K04 point marker map must target the primary series")
            self._apply_point_marker_map(bubble, action, data)
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
        marker_action = next(
            (action for action in reversed(actions) if isinstance(action, SetPointMarkerMap)),
            None,
        )
        marker_data = (
            None if marker_action is None else point_marker_shapes(data, marker_action)
        )
        plot_id, _ = self._official_plot_route(bubble)
        columns = {
            "x": 0,
            "y": 1,
            "size": 2 if bubble.size_values is not None else None,
            "color": (
                2 + int(bubble.size_values is not None) if bubble.color_values is not None else None
            ),
        }
        native = self._assert_native_structure(bubble, columns, plot_id, marker_data)
        self._assert_auxiliary(_COLOR_SCALE_NAME, state.color_scale_visible)
        self._assert_auxiliary(_BUBBLE_SCALE_NAME, state.size_key_visible)
        token = document.plot_id.removeprefix("plot:")
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
                        "native_structure": native,
                        "actions": [action.model_dump(mode="json") for action in actions],
                    },
                )
            ),
        )

    def _write_data(self, bubble: K04BubbleData) -> dict[str, int | None]:
        columns: dict[str, int | None] = {"x": 0, "y": 1, "size": None, "color": None}
        self.sheet.cols = len(self._column_values(bubble))
        self.sheet.from_list(0, list(bubble.x_values), lname=bubble.x_field_name, axis="X")
        self.sheet.from_list(1, list(bubble.y_values), lname=bubble.y_field_name, axis="Y")
        next_column = 2
        if bubble.size_values is not None:
            columns["size"] = next_column
            self.sheet.from_list(
                next_column,
                list(bubble.size_values),
                lname=bubble.size_field_name or "Size",
                axis="Y",
            )
            next_column += 1
        if bubble.color_values is not None:
            columns["color"] = next_column
            self.sheet.from_list(
                next_column,
                list(bubble.color_values),
                lname=bubble.color_field_name or "Color",
                axis="Y",
            )
        return columns

    @staticmethod
    def _official_plot_route(bubble: K04BubbleData) -> tuple[int, str]:
        if bubble.size_values is not None and bubble.color_values is not None:
            return 248, "Bubble"
        if bubble.size_values is not None:
            return 193, "Bubble"
        if bubble.color_values is not None:
            return 247, "SCATTER"
        return 201, "SCATTER"

    def _assert_native_structure(
        self,
        bubble: K04BubbleData,
        columns: dict[str, int | None],
        expected_plot_id: int,
        marker_data: PointMarkerShapeData | None,
    ) -> dict[str, object]:
        if len(list(self.layer.plot_list())) != 1:
            raise RuntimeError("Origin K04 native plot count differs after reopen")
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError("Origin K04 graph name is not safe for native readback")
        self.graph.activate()
        self.op.lt_exec(f"range __K04P=[{graph_name}]Layer1!1; get __K04P -pt __K04PID;")
        observed_plot_id = int(float(self.op.lt_float("__K04PID")))
        if observed_plot_id != 201:
            raise RuntimeError(
                "Origin K04 official Bubble command must persist as one native Scatter "
                f"DataPlot with modifiers; observed PID {observed_plot_id}"
            )
        expected_designations = [4, 1]
        if bubble.size_values is not None:
            expected_designations.append(1)
        if bubble.color_values is not None:
            expected_designations.append(1)
        if marker_data is not None:
            expected_designations.append(1)
        observed_designations = [
            int(self.sheet.get_int(f"col{index}.type"))
            for index in range(1, len(expected_designations) + 1)
        ]
        if observed_designations != expected_designations:
            raise RuntimeError("Origin K04 worksheet designation differs after reopen")
        size_modifier: object = None
        if columns["size"] is not None:
            size_modifier = self.plot.symbol_size
            expected_modifier = self.op.modi_col(columns["size"] - 1)
            if size_modifier != expected_modifier:
                raise RuntimeError("Origin K04 size column modifier is not native")
        color_range: list[float] | None = None
        color_dataset: str | None = None
        if columns["color"] is not None:
            theme = self.plot.obj.GetTheme()
            color_map = self._theme_child(theme, "ColorMap")
            minimum = float(self._theme_child(color_map, "Min").GetValue())
            maximum = float(self._theme_child(color_map, "Max").GetValue())
            major_levels = int(self._theme_child(color_map, "MajorLevels").GetValue())
            values = tuple(value for value in bubble.color_values or () if value == value)
            data_minimum = min(values) if values else 0.0
            data_maximum = max(values) if values else 0.0
            span = data_maximum - data_minimum
            padding = (data_minimum - minimum) + (maximum - data_maximum)
            if not self.op.lt_exec(
                f"range __K04COLORPLOT=[{graph_name}]Layer1!1; "
                "string __K04COLORDATA$; "
                "get __K04COLORPLOT -csfd __K04COLORDATA$;"
            ):
                raise RuntimeError("Origin K04 color modifier source is unreadable")
            color_dataset = str(self.op.get_lt_str("__K04COLORDATA"))
            color_column = int(columns["color"])
            expected_color_dataset = (
                f"{self.book.name}_{chr(ord('A') + color_column)}"
            )
            if (
                not values
                or minimum > data_minimum
                or maximum < data_maximum
                or padding > max(span * 0.05, 1e-12)
                or major_levels != 8
                or color_dataset != expected_color_dataset
            ):
                raise RuntimeError(
                    "Origin K04 color modifier is not bound to its source range: "
                    f"observed=({minimum!r}, {maximum!r}, levels={major_levels}), "
                    f"expected_envelope=({data_minimum!r}, {data_maximum!r}, levels=8), "
                    f"dataset={color_dataset!r}, expected_dataset={expected_color_dataset!r}"
                )
            color_range = [minimum, maximum]
        shape_modifier: int | None = None
        if marker_data is not None:
            shape_column = len(self._column_values(bubble))
            expected_codes = [_SYMBOL_CODES[shape] for shape in marker_data.shapes]
            observed_codes = [int(float(value)) for value in self.sheet.to_list(shape_column)]
            if observed_codes != expected_codes:
                raise RuntimeError("Origin K04 point marker shape codes differ after reopen")
            if not self.op.lt_exec(
                f"range __K04SHAPEPLOT=[{graph_name}]Layer1!1; "
                "get __K04SHAPEPLOT -k __K04SHAPEINDEX;"
            ):
                raise RuntimeError("Origin K04 point marker shape modifier is unreadable")
            shape_modifier = int(float(self.op.lt_float("__K04SHAPEINDEX")))
            expected_shape_modifier = 100 + shape_column - 1
            if shape_modifier != expected_shape_modifier:
                raise RuntimeError("Origin K04 point marker shape modifier is not native")
        return {
            "column_designations": observed_designations,
            "color_map_range": color_range,
            "color_modifier_dataset": color_dataset,
            "official_creation_plot_id": expected_plot_id,
            "native_plot_id": observed_plot_id,
            "size_modifier": size_modifier,
            "shape_modifier": shape_modifier,
        }

    def _apply_point_marker_map(
        self,
        bubble: K04BubbleData,
        action: SetPointMarkerMap,
        data: EngineDataView,
    ) -> None:
        marker_data = point_marker_shapes(data, action)
        shape_column = len(self._column_values(bubble))
        self.sheet.cols = shape_column + 1
        self.sheet.from_list(
            shape_column,
            [_SYMBOL_CODES[shape] for shape in marker_data.shapes],
            lname=f"{marker_data.field_name} / marker shape",
            axis="Y",
        )
        graph_name = str(self.graph.name)
        book_name = str(self.book.name)
        sheet_name = str(self.sheet.name)
        if any(
            not name.replace("_", "").isalnum()
            for name in (graph_name, book_name, sheet_name)
        ):
            raise RuntimeError("Origin K04 native names are unsafe for marker shape binding")
        column_letter = chr(ord("A") + shape_column)
        self.graph.activate()
        command = (
            f"range __K04SHAPEPLOT=[{graph_name}]Layer1!1; "
            f"range __K04SHAPECODES=[{book_name}]{sheet_name}!col({column_letter}); "
            "set __K04SHAPEPLOT -ksn __K04SHAPECODES;"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin rejected the K04 point marker shape mapping")
        self.layer.rescale()

    @staticmethod
    def _theme_child(parent: Any, name: str) -> Any:
        try:
            return next(child for child in parent.Children if str(child.Name) == name)
        except StopIteration as error:
            raise RuntimeError(f"Origin K04 theme is missing {name}") from error

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
        state = _K04State(size_key_visible=bubble.size_values is not None)
        for action in actions:
            if isinstance(action, SetChartParameter):
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
