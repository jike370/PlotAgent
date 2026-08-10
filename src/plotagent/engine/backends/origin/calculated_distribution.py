"""Official-template binders for calculated K15/K16 distributions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

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
from plotagent.engine.profile_data import DensityData, HistogramData, k15_histogram, k16_density
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import (
    K15_ORIGIN_PROFILE,
    K16_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)

_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
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


def _effective_actions(actions: tuple[PlotEngineAction, ...]) -> tuple[PlotEngineAction, ...]:
    last_binding = max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    return tuple(
        action
        for index, action in enumerate(actions)
        if not (isinstance(action, SetSeriesStyle) and index < last_binding)
    )


class CalculatedDistributionOriginProject:
    def __init__(self, op: Any, *, profile_id: Literal["K15", "K16"]) -> None:
        self.op = op
        self.profile_id = profile_id
        self.profile: OriginTemplateProfile = (
            K15_ORIGIN_PROFILE if profile_id == "K15" else K16_ORIGIN_PROFILE
        )
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, self.profile)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
        self.sheet = book[0]
        self.graph = self.op.new_graph(
            f"G{token}",
            template=str(template.with_suffix(template.suffix.lower())),
            hidden=True,
        )
        if self.graph is None:
            raise RuntimeError(
                f"Origin could not create {self.profile_id} from {self.profile.filename}"
            )
        self.layer = self.graph[0]
        for plot in self.layer.plot_list():
            plot.set_int("show", 0)
        if self.profile_id == "K15":
            histogram = k15_histogram(document, data)
            self._write_histogram(histogram)
            plot = self.layer.add_plot(self.sheet, coly=1, colx=0, type=203)
            if plot is None:
                raise RuntimeError("Origin Hist.otpu rejected the fixed-bin native column plot")
            plot.set_cmd("-vg 0")
            self.plots = [plot]
        else:
            density = k16_density(document, data)
            self._write_density(density)
            self.plots = []
            for index in range(len(density.series)):
                plot = self.layer.add_plot(
                    self.sheet,
                    coly=index * 2 + 1,
                    colx=index * 2,
                    type="l",
                )
                if plot is None:
                    raise RuntimeError(f"Origin HISTDIST.otpu rejected density {index + 1}")
                self.plots.append(plot)
        self.layer.rescale()

    def reopen(self, project_path: Path) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError(
                f"fresh Origin session could not reopen the staged {self.profile_id} project"
            )
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError(
                f"fresh {self.profile_id} project has unexpected graph or workbook count"
            )
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = [plot for plot in self.layer.plot_list() if plot.get_int("show") != 0]
        self.sheet = books[0][0]

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> None:
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError(f"{self.profile_id} title target does not belong to this plot")
            title = self.layer.label(_TITLE_NAME)
            if title is None:
                title = self.layer.add_label(action.text, 40, 2)
                if title is None:
                    raise RuntimeError(f"Origin could not create the {self.profile_id} title")
                title.name = _TITLE_NAME
            title.text = action.text
            title.set_int("show", 1)
            return
        if isinstance(action, SetAxis):
            axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
            if axis_name is None:
                raise ValueError(f"{self.profile_id} axis target does not belong to this plot")
            axis = self.layer.axis(axis_name)
            if action.scale is not None:
                if action.scale not in {"linear", "log10"}:
                    raise ValueError(
                        f"Origin {self.profile_id} axes support only linear or log10"
                    )
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
                    raise RuntimeError(f"Origin {self.profile_id} has no writable axis label")
                label.text = action.label
                label.set_int("show", 1)
            return
        if isinstance(action, SetSeriesStyle):
            ordinal = self._series_ordinal(action.target, token)
            plot = self.plots[ordinal - 1]
            if action.color is not None:
                plot.color = action.color
            if action.line_width_pt is not None:
                plot.set_float("line.width", action.line_width_pt)
            if action.line_style is not None:
                if self.profile_id == "K15":
                    raise ValueError("Origin K15 does not expose a line style")
                if action.line_style == "none":
                    raise ValueError("Origin K16 cannot hide a density series")
                plot.set_int("line.style", _LINE_STYLE[action.line_style])
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError(f"{self.profile_id} legend target does not belong to this plot")
            visible = action.visible
            legend = self.layer.label("legend")
            if visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError(f"Origin could not create the {self.profile_id} legend")
                legend = self.layer.label("legend")
            if legend is not None and visible is not None:
                labels = self._labels(document, data)
                style = "b" if self.profile_id == "K15" else "l"
                legend.text = "\n".join(
                    f"\\l({index}, style:{style}) {_safe_label(label)}"
                    for index, label in enumerate(labels, start=1)
                )
                legend.set_int("link", 1)
                legend.set_int("show", int(visible))
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
        if self.profile_id == "K15":
            histogram = k15_histogram(document, data)
            if len(self.plots) != 1:
                raise RuntimeError("Origin K15 must contain one visible native histogram series")
            self._assert_values(self.sheet.to_list(0), histogram.center, "bin centers")
            self._assert_values(self.sheet.to_list(1), histogram.height, "bin heights")
        else:
            density = k16_density(document, data)
            if len(self.plots) != len(density.series):
                raise RuntimeError("Origin K16 density count differs after reopen")
            for index, series in enumerate(density.series):
                self._assert_values(self.sheet.to_list(index * 2), series.grid, "KDE grid")
                self._assert_values(
                    self.sheet.to_list(index * 2 + 1), series.density, "KDE density"
                )
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {"profile": self.profile_id, "series": len(self.plots)}
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError(f"Origin {self.profile_id} title did not survive readback")
            elif isinstance(action, SetSeriesStyle):
                ordinal = self._series_ordinal(action.target, token)
                plot = self.plots[ordinal - 1]
                if action.color is not None and tuple(plot.color) != self._hex_rgb(action.color):
                    raise RuntimeError(
                        f"Origin {self.profile_id} series color did not survive readback"
                    )
                if action.line_width_pt is not None and (
                    abs(float(plot.get_float("line.width")) - action.line_width_pt) > 0.01
                ):
                    raise RuntimeError(
                        f"Origin {self.profile_id} line width did not survive readback"
                    )
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError(
                        f"Origin {self.profile_id} legend visibility did not survive readback"
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
            *tuple(
                EngineObjectRef(
                    semantic_id=(
                        f"series:{token}.primary"
                        if self.profile_id == "K15"
                        else f"series:{token}.group_{index}"
                    ),
                    backend="origin",
                    object_kind=(
                        "histogram_series" if self.profile_id == "K15" else "density_series"
                    ),
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

    def _write_histogram(self, histogram: HistogramData) -> None:
        self.sheet.from_list(0, list(histogram.center), lname=histogram.value_field_name, axis="X")
        self.sheet.from_list(1, list(histogram.height), lname="Count", axis="Y")
        self.sheet.from_list(2, list(histogram.left), lname="Bin Left")
        self.sheet.from_list(3, list(histogram.right), lname="Bin Right")
        self.sheet.from_list(4, list(histogram.count), lname="Raw Count")

    def _write_density(self, density: DensityData) -> None:
        for index, series in enumerate(density.series):
            self.sheet.from_list(
                index * 2,
                list(series.grid),
                lname=density.value_field_name,
                axis="X",
            )
            self.sheet.from_list(index * 2 + 1, list(series.density), lname=series.label, axis="Y")

    def _labels(self, document: PlotDocument, data: EngineDataView) -> tuple[str, ...]:
        if self.profile_id == "K15":
            return (k15_histogram(document, data).value_field_name,)
        return tuple(series.label for series in k16_density(document, data).series)

    def _series_ordinal(self, target: str, token: str) -> int:
        if self.profile_id == "K15":
            if target != f"series:{token}.primary":
                raise ValueError("K15 series target does not belong to this plot")
            return 1
        prefix = f"series:{token}.group_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        if not suffix.isdigit() or not 1 <= int(suffix) <= len(self.plots):
            raise ValueError("K16 series target is outside the materialized groups")
        return int(suffix)

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], name: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin {name} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if abs(float(cast(Any, observed)) - float(cast(Any, wanted))) > 1e-9:
                raise RuntimeError(f"Origin {name} values differ after reopen")

    @staticmethod
    def _hex_rgb(value: str) -> tuple[int, int, int]:
        return cast(
            tuple[int, int, int],
            tuple(int(value[index : index + 2], 16) for index in (1, 3, 5)),
        )


def _execute(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
    profile_id: Literal["K15", "K16"],
) -> EngineReadback:
    project = CalculatedDistributionOriginProject(op, profile_id=profile_id)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    for action in actions:
        project.apply(request.document, action, request.data)
    project.save(output)
    reopened = CalculatedDistributionOriginProject(op, profile_id=profile_id)
    reopened.reopen(output)
    return reopened.verify(request.document, actions, request.data)


def execute_k15_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K15")


def execute_k16_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K16")
