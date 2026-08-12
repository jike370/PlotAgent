"""Official-template binders for native K12/K13/K14 distribution plots."""

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
from plotagent.engine.profile_data import DistributionData, distribution_groups
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import (
    K12_ORIGIN_PROFILE,
    K13_ORIGIN_PROFILE,
    K14_ORIGIN_PROFILE,
    X05_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)
from .trace import origin_trace_step, record_origin_trace

_TITLE_NAME = "_ENGINE_TITLE"
_SYMBOL_CODES = {"circle": 2, "square": 1, "triangle": 3, "triangle_up": 3, "diamond": 5}
_X05_OFFICIAL_MENU_COMMAND = "worksheet -s 1 0 {last_column} 0; worksheet -p 206 Beeswarm;"


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
    last_binding = max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    return tuple(
        action
        for index, action in enumerate(actions)
        if not (isinstance(action, SetSeriesStyle) and index < last_binding)
    )


class DistributionOriginProject:
    """Bind raw observations to a named official native plot template."""

    def __init__(self, op: Any, *, profile_id: Literal["K12", "K13", "K14", "X05"]) -> None:
        self.op = op
        self.profile_id = profile_id
        self.profile: OriginTemplateProfile = {
            "K12": K12_ORIGIN_PROFILE,
            "K13": K13_ORIGIN_PROFILE,
            "K14": K14_ORIGIN_PROFILE,
            "X05": X05_ORIGIN_PROFILE,
        }[profile_id]
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": self.profile.filename},
        ):
            template = resolve_official_template(install_dir, self.profile)
        distribution = self._distribution(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
            if book is None:
                raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
            self.sheet = book[0]
            if self.profile_id == "X05":
                self._remove_workbook_residue(book)
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": len(distribution.groups),
                "group_sizes": [len(group.values) for group in distribution.groups],
            },
        ):
            self._write_data(distribution)
        if self.profile_id == "X05":
            command = _X05_OFFICIAL_MENU_COMMAND.format(
                last_column=len(distribution.groups)
            )
            with origin_trace_step(
                "official_plot_command_execute",
                details={"labtalk": command, "template_filename": template.name},
            ):
                self.sheet.activate()
                self.op.lt_exec(command)
            with origin_trace_step("native_structure_readback"):
                graphs = list(self.op.pages("g"))
                if len(graphs) != 1:
                    raise RuntimeError("Origin Beeswarm command must create exactly one graph")
                self.graph = graphs[0]
                self.graph.name = f"G{token}"
                self.graph.lname = f"X05 {template.stem} / {document.plot_id}"
                self.layer = self.graph[0]
                self.plots = list(self.layer.plot_list())
                with origin_trace_step("native_data_legend_rebuild"):
                    self._rebuild_x05_data_legend()
                native = self._assert_official_x05_structure(distribution)
            record_origin_trace("native_beeswarm_confirmed", "completed", details=native)
            self.layer.rescale()
            return
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
        self.plots = []
        for index in range(len(distribution.groups)):
            # '?' asks the selected official template for its native plot type.
            # In particular, K14 must remain a native violin and may never be
            # simulated with line/fill primitives that create edge artifacts.
            plot = self.layer.add_plot(self.sheet, coly=index, colx="#", type="?")
            if plot is None:
                raise RuntimeError(f"Origin rejected {self.profile_id} native group {index + 1}")
            self.plots.append(plot)
        self.layer.rescale()

    def _remove_workbook_residue(self, authoritative_book: Any) -> None:
        for residue in tuple(self.op.pages("w")):
            if residue.name == authoritative_book.name:
                continue
            if residue.name == "Book1":
                residue.destroy()

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
        self.plots = list(self.layer.plot_list())
        self.sheet = books[0][0]

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> None:
        distribution = self._distribution(document, data)
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
                if axis_name == "x" and action.scale != "categorical":
                    raise ValueError("Origin distribution X axes support only categorical scale")
                if axis_name == "y":
                    if action.scale not in {"linear", "log10"}:
                        raise ValueError("Origin distribution Y axes support only linear or log10")
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
            ordinal = self._series_ordinal(action.target, token, len(self.plots))
            plot = self.plots[ordinal - 1]
            if action.color is not None:
                self._set_series_rgb(distribution, ordinal, action.color)
            if action.line_width_pt is not None:
                raise ValueError(
                    f"Origin {self.profile_id} does not expose a common series line-width edit"
                )
            if action.symbol is not None:
                if self.profile_id not in {"K12", "X05"}:
                    raise ValueError(f"Origin {self.profile_id} does not expose symbol edits")
                try:
                    plot.symbol_kind = _SYMBOL_CODES[action.symbol]
                except KeyError as error:
                    raise ValueError(
                        f"Origin {self.profile_id} does not support symbol {action.symbol}"
                    ) from error
            if action.symbol_size_pt is not None:
                if self.profile_id not in {"K12", "X05"}:
                    raise ValueError(f"Origin {self.profile_id} does not expose symbol-size edits")
                plot.symbol_size = action.symbol_size_pt
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError(f"{self.profile_id} legend target does not belong to this plot")
            if self.profile_id == "X05":
                legend = (
                    self._rebuild_x05_data_legend()
                    if action.visible
                    else self.layer.label("legend")
                )
                if legend is not None and action.visible is not None:
                    legend.set_int("show", int(action.visible))
                return
            legend = self.layer.label("legend")
            if action.visible and legend is None:
                self.layer.activate()
                if not self.layer.obj.LT_execute("legend"):
                    raise RuntimeError(f"Origin could not create the {self.profile_id} legend")
                legend = self.layer.label("legend")
            if legend is not None and action.visible is not None:
                legend.text = "\n".join(
                    f"\\l({index}) {_safe_label(group.label)}"
                    for index, group in enumerate(distribution.groups, start=1)
                )
                legend.set_int("link", 1)
                legend.set_int("show", int(action.visible))
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
        distribution = self._distribution(document, data)
        if len(self.plots) != len(distribution.groups):
            raise RuntimeError(f"Origin {self.profile_id} group count differs after reopen")
        for index, group in enumerate(distribution.groups):
            actual = tuple(float(value) for value in self.sheet.to_list(index))
            if actual != group.values:
                raise RuntimeError(f"Origin {self.profile_id} observations differ after reopen")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {
            "profile": self.profile_id,
            "group_count": len(distribution.groups),
        }
        if self.profile_id == "X05":
            snapshot.update(self._assert_official_x05_structure(distribution))
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError(f"Origin {self.profile_id} title did not survive readback")
            elif isinstance(action, SetSeriesStyle):
                ordinal = self._series_ordinal(action.target, token, len(self.plots))
                if action.color is not None:
                    self._assert_series_rgb(distribution, ordinal, action.color)
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
                    semantic_id=f"series:{token}.group_{index}",
                    backend="origin",
                    object_kind=f"{self.profile_id.lower()}_native_group",
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

    def _distribution(self, document: PlotDocument, data: EngineDataView) -> DistributionData:
        return distribution_groups(document, data, profile_id=self.profile_id)

    def _write_data(self, distribution: DistributionData) -> None:
        for index, group in enumerate(distribution.groups):
            self.sheet.from_list(index, list(group.values), lname=group.label, axis="Y")

    def _assert_official_x05_structure(
        self, distribution: DistributionData
    ) -> dict[str, object]:
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe Origin X05 graph name: {graph_name!r}")
        self.graph.activate()
        self.op.lt_exec("page.active=1; layer -c; __X05COUNT=count;")
        plot_count = int(self.op.lt_float("__X05COUNT"))
        plot_types: list[int] = []
        for index in range(1, plot_count + 1):
            self.op.lt_exec(
                f"range __X05P=[{graph_name}]1!{index}; "
                f"get __X05P -pt __X05PT{index};"
            )
            plot_types.append(int(self.op.lt_float(f"__X05PT{index}")))
        if len(plot_types) != len(distribution.groups) or any(
            plot_type != 206 for plot_type in plot_types
        ):
            raise RuntimeError(
                "Origin X05 native Beeswarm signature differs from the official "
                f"group contract: plot_types={plot_types}, "
                f"group_count={len(distribution.groups)}"
            )
        expected_designations = [1] * len(distribution.groups)
        actual_designations = [
            int(self.sheet.get_int(f"col{index + 1}.type"))
            for index in range(len(expected_designations))
        ]
        if actual_designations != expected_designations:
            raise RuntimeError(
                "Origin X05 worksheet designation changed: "
                f"expected={expected_designations}, actual={actual_designations}"
            )
        return {
            "official_menu_command": _X05_OFFICIAL_MENU_COMMAND.format(
                last_column=len(distribution.groups)
            ),
            "native_plot_types": plot_types,
            "worksheet_designations": actual_designations,
            "arrange_points": "requires_live_theme_readback",
        }

    def _rebuild_x05_data_legend(self) -> Any:
        self.layer.activate()
        self.op.lt_exec(
            "legendbox mode:=replace box:=0 range:=0 whisker:=0 mdl:=0 ml:=0 "
            "max:=0 perc99:=0 mean:=0 Median:=0 perc1:=0 min:=0 cp:=0 "
            "data:=1 dataid:=L outlier:=0 extreme:=0 cm:=0 cmd:=0 cd:=0 ccp:=0;"
        )
        legend = self.layer.label("legend")
        if legend is None:
            raise RuntimeError("Origin X05 could not build its data-symbol-only legend")
        return legend

    def _set_series_rgb(
        self,
        distribution: DistributionData,
        ordinal: int,
        color: str,
    ) -> None:
        rgb = self._hex_rgb(color)
        group_count = len(distribution.groups)
        base_column = group_count + (ordinal - 1) * 3
        row_count = len(distribution.groups[ordinal - 1].values)
        for offset, (channel, value) in enumerate(zip("RGB", rgb, strict=True)):
            self.sheet.from_list(
                base_column + offset,
                [value] * row_count,
                lname=f"Style {ordinal} {channel}",
            )
        plot = self.plots[ordinal - 1]
        if hasattr(self.op, "color_col"):
            plot.color = self.op.color_col(base_column - (ordinal - 1), "r")
        else:
            plot.color = color

    def _assert_series_rgb(
        self,
        distribution: DistributionData,
        ordinal: int,
        color: str,
    ) -> None:
        expected = self._hex_rgb(color)
        group_count = len(distribution.groups)
        base_column = group_count + (ordinal - 1) * 3
        row_count = len(distribution.groups[ordinal - 1].values)
        for offset, value in enumerate(expected):
            observed = self.sheet.to_list(base_column + offset)
            if len(observed) != row_count or any(int(item) != value for item in observed):
                raise RuntimeError(
                    f"Origin {self.profile_id} series RGB modifier did not survive readback"
                )

    def _series_ordinal(self, target: str, token: str, group_count: int) -> int:
        prefix = f"series:{token}.group_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        if not suffix.isdigit() or not 1 <= int(suffix) <= group_count:
            raise ValueError(f"{self.profile_id} series target is outside the materialized groups")
        return int(suffix)

    @staticmethod
    def _hex_rgb(value: str) -> tuple[int, int, int]:
        return cast(tuple[int, int, int], tuple(int(value[i : i + 2], 16) for i in (1, 3, 5)))


def _execute(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
    profile_id: Literal["K12", "K13", "K14", "X05"],
) -> EngineReadback:
    project = DistributionOriginProject(op, profile_id=profile_id)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    for action in actions:
        project.apply(request.document, action, request.data)
    project.save(output)
    reopened = DistributionOriginProject(op, profile_id=profile_id)
    reopened.reopen(output)
    return reopened.verify(request.document, actions, request.data)


def execute_k12_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K12")


def execute_k13_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K13")


def execute_k14_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K14")


def execute_x05_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "X05")
