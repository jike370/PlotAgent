"""Closed worksheet/XY template binder shared by simple Agent Native profiles."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    AddAnnotation,
    BindFields,
    CreatePlot,
    EngineColumn,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.repository import document_ref

from .profile import OriginTemplateProfile, resolve_official_template
from .readback import axis_scale_matches

_LINE_STYLE_CODES = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3, "none": 10}
_SYMBOL_CODES = {
    "square": 1,
    "circle": 2,
    "triangle": 3,
    "triangle_up": 3,
    "diamond": 5,
}
_TITLE_NAME = "_ENGINE_TITLE"


def _annotation_name(semantic_id: str) -> str:
    return "_ENGINE_ANNOTATION_" + sha256(semantic_id.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class OriginXYDefinition:
    template: OriginTemplateProfile
    plot_type: str
    object_kind: str
    supports_line: bool
    supports_symbol: bool


def _hex_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _safe_legend_label(value: str) -> str:
    output: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character in {"\\", "%", "$"}:
            output.append(f"\\x({codepoint:04X})")
        elif character in {"\r", "\n", "\t"} or codepoint < 0x20 or codepoint == 0x7F:
            output.append(" ")
        else:
            output.append(character)
    return "".join(output).strip()


class OriginXYProject:
    """Bind one numeric XY profile directly to its official graph template."""

    def __init__(self, op: Any, definition: OriginXYDefinition) -> None:
        self.op = op
        self.definition = definition
        self.graph: Any = None
        self.layer: Any = None
        self.plot: Any = None
        self.sheet: Any = None

    @property
    def profile_id(self) -> str:
        return self.definition.template.profile_id

    def create(
        self,
        install_dir: Path,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        template = resolve_official_template(install_dir, self.definition.template)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
        self.sheet = book[0]
        self._write_data(document, data)
        argument = template.with_suffix(template.suffix.lower())
        self.graph = self.op.new_graph(f"G{token}", template=str(argument), hidden=True)
        if self.graph is None:
            raise RuntimeError(
                "Origin could not create "
                f"{self.profile_id} from {self.definition.template.filename}"
            )
        self.layer = self.graph[0]
        self.plot = self.layer.add_plot(
            self.sheet,
            coly=1,
            colx=0,
            type=self.definition.plot_type,
        )
        if self.plot is None:
            raise RuntimeError(f"Origin template rejected the {self.profile_id} native plot")
        self.layer.rescale()

    def open(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not open the previous project: {project_path}")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError(f"{self.profile_id} project must contain one graph and one workbook")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        plots = self.layer.plot_list()
        if len(plots) != 1:
            raise RuntimeError(f"{self.profile_id} project must contain one native plot")
        self.plot = plots[0]
        self.sheet = books[0][0]

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> None:
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, CreatePlot):
            return
        if isinstance(action, BindFields):
            self._write_data(document, data)
            self.layer.rescale()
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError(f"{self.profile_id} title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None:
                label = self.layer.add_label(action.text, 40, 2)
                if label is None:
                    raise RuntimeError(f"Origin could not create the {self.profile_id} title")
                label.name = _TITLE_NAME
            label.text = action.text
            label.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError(f"{self.profile_id} axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if action.scale not in {"linear", "log10"}:
                    raise ValueError(f"Origin {self.profile_id} axes support only linear or log10")
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
                    raise RuntimeError(
                        f"Origin {self.profile_id} template has no writable axis label"
                    )
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            if action.target != f"series:{token}.primary":
                raise ValueError(f"{self.profile_id} series target does not belong to this plot")
            if action.color is not None:
                self.plot.color = action.color
            if action.line_width_pt is not None:
                if not self.definition.supports_line:
                    raise ValueError(f"{self.profile_id} does not expose a line width")
                self.plot.set_float("line.width", action.line_width_pt)
            if action.line_style is not None:
                if not self.definition.supports_line:
                    raise ValueError(f"{self.profile_id} does not expose a line style")
                self.plot.set_int("line.style", _LINE_STYLE_CODES[action.line_style])
            if action.symbol is not None:
                if not self.definition.supports_symbol:
                    raise ValueError(f"{self.profile_id} does not expose a symbol")
                try:
                    self.plot.symbol_kind = _SYMBOL_CODES[action.symbol]
                except KeyError as error:
                    raise ValueError(
                        f"Origin {self.profile_id} does not support symbol {action.symbol}"
                    ) from error
            if action.symbol_size_pt is not None:
                if not self.definition.supports_symbol:
                    raise ValueError(f"{self.profile_id} does not expose a symbol size")
                self.plot.symbol_size = action.symbol_size_pt
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError(f"{self.profile_id} legend target does not belong to this plot")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError(f"Origin could not create a linked {self.profile_id} legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                value_name = self._bound_columns(document, data)[1].field.name
                legend.text = f"\\l(1) {_safe_legend_label(value_name)}"
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        if isinstance(action, AddAnnotation):
            if action.target != document.plot_id:
                raise ValueError(
                    f"{self.profile_id} annotation target does not belong to this plot"
                )
            native_name = _annotation_name(action.annotation_id)
            label = self.layer.label(native_name)
            if label is None:
                label = self.layer.add_label(action.text, action.x, action.y)
                if label is None:
                    raise RuntimeError(f"Origin could not create the {self.profile_id} annotation")
                label.name = native_name
            label.text = action.text
            label.set_int("show", 1)
            return
        raise ValueError(f"Origin {self.profile_id} binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError(f"Origin did not save a non-empty {self.profile_id} project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        x_column, y_column = self._bound_columns(document, data)
        self._assert_values(self.sheet.to_list(0), x_column.values, "x")
        self._assert_values(self.sheet.to_list(1), y_column.values, "y")
        token = document.plot_id.removeprefix("plot:")
        style_snapshot: dict[str, object] = {}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError(f"Origin {self.profile_id} title did not survive readback")
                style_snapshot["title"] = title.text
            elif isinstance(action, SetAxis):
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                axis = self.layer.axis(axis_name)
                if action.scale is not None and not axis_scale_matches(axis.scale, action.scale):
                    raise RuntimeError(
                        f"Origin {self.profile_id} axis scale did not survive readback"
                    )
                if action.label is not None:
                    label = self.layer.label("xb" if axis_name == "x" else "yl")
                    if label is None or label.text != action.label:
                        raise RuntimeError(
                            f"Origin {self.profile_id} axis label did not survive readback"
                        )
                style_snapshot[f"axis_{axis_name}"] = {
                    "scale": axis.scale,
                    "limits": tuple(float(value) for value in axis.limits),
                }
            elif isinstance(action, SetSeriesStyle):
                if action.color is not None and tuple(self.plot.color) != _hex_rgb(action.color):
                    raise RuntimeError(
                        f"Origin {self.profile_id} series color did not survive readback"
                    )
                if (
                    action.line_width_pt is not None
                    and abs(self.plot.get_float("line.width") - action.line_width_pt) > 0.01
                ):
                    raise RuntimeError(
                        f"Origin {self.profile_id} line width did not survive readback"
                    )
                if action.symbol_size_pt is not None and (
                    abs(float(self.plot.symbol_size) - action.symbol_size_pt) > 0.01
                ):
                    raise RuntimeError(
                        f"Origin {self.profile_id} symbol size did not survive readback"
                    )
                style_snapshot["series"] = {
                    "color": tuple(self.plot.color),
                    "line_width": self.plot.get_float("line.width"),
                }
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError(
                        f"Origin {self.profile_id} legend visibility did not survive readback"
                    )
                style_snapshot["legend"] = {"visible": action.visible, "text": legend.text}
            elif isinstance(action, AddAnnotation):
                label = self.layer.label(_annotation_name(action.annotation_id))
                if label is None or label.text != action.text or not label.get_int("show"):
                    raise RuntimeError(
                        f"Origin {self.profile_id} annotation did not survive readback"
                    )
        objects = (
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
                object_kind=self.definition.object_kind,
                native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
            ),
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="origin",
                object_kind="legend",
                native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
            ),
        )
        return EngineReadback(
            document=document_ref(document),
            backend="origin",
            objects=objects,
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, style_snapshot)),
        )

    def _write_data(self, document: PlotDocument, data: EngineDataView) -> None:
        x_column, y_column = self._bound_columns(document, data)
        self.sheet.from_list(
            0,
            list(x_column.values),
            lname=x_column.field.name,
            units=x_column.field.unit_label or "",
            axis="X",
        )
        self.sheet.from_list(
            1,
            list(y_column.values),
            lname=y_column.field.name,
            units=y_column.field.unit_label or "",
            axis="Y",
        )

    @staticmethod
    def _bound_columns(
        document: PlotDocument,
        data: EngineDataView,
    ) -> tuple[EngineColumn, EngineColumn]:
        bindings = {binding.role: binding.field_id for binding in document.bindings}
        columns = {column.field.field_id: column for column in data.columns}
        return columns[bindings["x"]], columns[bindings["y"]]

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin XY {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if observed is None and wanted is None:
                continue
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-12:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin XY {role} values differ after reopen")
