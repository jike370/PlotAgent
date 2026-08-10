"""K03 grouped scatter bound directly to Origin's official SCATTER template."""

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
from plotagent.engine.profile_data import K03ScatterData, k03_scatter
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K03_ORIGIN_PROFILE, resolve_official_template

_SYMBOL_CODES = {"square": 1, "circle": 2, "triangle": 3, "triangle_up": 3, "diamond": 5}
_TITLE_NAME = "_ENGINE_TITLE"


def _safe_label(value: str) -> str:
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


def _effective_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[PlotEngineAction, ...]:
    """Reset data-derived series styles whenever fields are rebound."""

    last_binding = max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    return tuple(
        action
        for index, action in enumerate(actions)
        if not (isinstance(action, SetSeriesStyle) and index < last_binding)
    )


class K03OriginProject:
    """One worksheet pair and one native scatter plot per materialized group."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, K03_ORIGIN_PROFILE)
        scatter = k03_scatter(document, data)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError("Origin could not create the K03 workbook")
        self.sheet = book[0]
        self._write_data(scatter)
        self.graph = self.op.new_graph(
            f"G{token}",
            template=str(template.with_suffix(template.suffix.lower())),
            hidden=True,
        )
        if self.graph is None:
            raise RuntimeError("Origin could not create K03 from SCATTER.OTP")
        self.layer = self.graph[0]
        self.plots = []
        for index in range(len(scatter.groups)):
            plot = self.layer.add_plot(self.sheet, coly=index * 2 + 1, colx=index * 2, type="s")
            if plot is None:
                raise RuntimeError(f"Origin rejected K03 native scatter group {index + 1}")
            self.plots.append(plot)
        if len(self.plots) > 1:
            self.layer.group(True, 0, len(self.plots) - 1)
        self.layer.rescale()

    def reopen(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError("fresh Origin session could not reopen the staged K03 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("fresh K03 project has unexpected graph or workbook count")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = list(self.layer.plot_list())
        self.sheet = books[0][0]

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> None:
        scatter = k03_scatter(document, data)
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K03 title target does not belong to this plot")
            label = self.layer.label(_TITLE_NAME)
            if label is None:
                label = self.layer.add_label(action.text, 40, 2)
                if label is None:
                    raise RuntimeError("Origin could not create the K03 title")
                label.name = _TITLE_NAME
            label.text = action.text
            label.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError("K03 axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if action.scale not in {"linear", "log10"}:
                    raise ValueError("Origin K03 axes support only linear or log10")
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
                    raise RuntimeError("Origin K03 template has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            ordinal = self._series_ordinal(action.target, token, len(self.plots))
            plot = self.plots[ordinal - 1]
            if action.color is not None:
                plot.color = action.color
            if action.symbol is not None:
                try:
                    plot.symbol_kind = _SYMBOL_CODES[action.symbol]
                except KeyError as error:
                    raise ValueError(
                        f"Origin K03 does not support symbol {action.symbol}"
                    ) from error
            if action.symbol_size_pt is not None:
                plot.symbol_size = action.symbol_size_pt
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError("K03 legend target does not belong to this plot")
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError("Origin could not create a linked K03 legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                legend.text = "\n".join(
                    f"\\l({index}) {_safe_label(group.label)}"
                    for index, group in enumerate(scatter.groups, start=1)
                )
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
            return
        raise ValueError(f"Origin K03 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty K03 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        scatter = k03_scatter(document, data)
        if len(self.plots) != len(scatter.groups):
            raise RuntimeError("Origin K03 native plot count differs after reopen")
        for index, group in enumerate(scatter.groups):
            self._assert_values(self.sheet.to_list(index * 2), group.x_values, "x")
            self._assert_values(self.sheet.to_list(index * 2 + 1), group.y_values, "y")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {"group_count": len(scatter.groups)}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError("Origin K03 title did not survive readback")
                snapshot["title"] = title.text
            elif isinstance(action, SetAxis):
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                axis = self.layer.axis(axis_name)
                if action.scale is not None and axis.scale != action.scale:
                    raise RuntimeError("Origin K03 axis scale did not survive readback")
                if action.label is not None:
                    label = self.layer.label("xb" if axis_name == "x" else "yl")
                    if label is None or label.text != action.label:
                        raise RuntimeError("Origin K03 axis label did not survive readback")
            elif isinstance(action, SetSeriesStyle):
                ordinal = self._series_ordinal(action.target, token, len(self.plots))
                plot = self.plots[ordinal - 1]
                if action.color is not None and tuple(plot.color) != self._hex_rgb(action.color):
                    raise RuntimeError("Origin K03 series color did not survive readback")
                if action.symbol_size_pt is not None and (
                    abs(float(plot.symbol_size) - action.symbol_size_pt) > 0.01
                ):
                    raise RuntimeError("Origin K03 symbol size did not survive readback")
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if action.visible and (legend is None or not bool(legend.get_int("show"))):
                    raise RuntimeError("Origin K03 legend visibility did not survive readback")
                if not action.visible and legend is not None and bool(legend.get_int("show")):
                    raise RuntimeError("Origin K03 legend visibility did not survive readback")
                if action.visible and legend.text.count("\\l(") != len(scatter.groups):
                    raise RuntimeError("Origin K03 legend lost a group sample")
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
            *tuple(
                EngineObjectRef(
                    semantic_id=f"series:{token}.group_{index}",
                    backend="origin",
                    object_kind="scatter_series",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:{index}",
                )
                for index in range(1, len(self.plots) + 1)
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
            style_hash=canonical_hash(cast(JsonValue, snapshot)),
        )

    def _write_data(self, scatter: K03ScatterData) -> None:
        for index, group in enumerate(scatter.groups):
            self.sheet.from_list(
                index * 2,
                list(group.x_values),
                lname=scatter.x_field_name,
                axis="X",
            )
            self.sheet.from_list(
                index * 2 + 1,
                list(group.y_values),
                lname=group.label,
                axis="Y",
            )

    @staticmethod
    def _series_ordinal(target: str, token: str, group_count: int) -> int:
        prefix = f"series:{token}.group_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        if not suffix.isdigit() or not 1 <= int(suffix) <= group_count:
            raise ValueError("K03 series target is outside the materialized groups")
        return int(suffix)

    @staticmethod
    def _hex_rgb(value: str) -> tuple[int, int, int]:
        return cast(tuple[int, int, int], tuple(int(value[i : i + 2], 16) for i in (1, 3, 5)))

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[float, ...], role: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin K03 {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if observed is None and wanted != wanted:
                continue
            if abs(float(cast(Any, observed)) - wanted) > 1e-12:
                raise RuntimeError(f"Origin K03 {role} values differ after reopen")


def execute_k03_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    """Recreate from the official template so changed group counts remain native."""

    project = K03OriginProject(op)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    for action in actions:
        project.apply(request.document, action, request.data)
    project.save(output)

    reopened = K03OriginProject(op)
    reopened.reopen(output)
    return reopened.verify(request.document, actions, request.data)
