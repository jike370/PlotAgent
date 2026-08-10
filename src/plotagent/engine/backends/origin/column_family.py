"""Official-template binders for K09/K10/K11 native column families."""

from __future__ import annotations

from math import isnan
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
from plotagent.engine.profile_data import CategorySeriesGrid, category_series_grid
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import (
    K09_ORIGIN_PROFILE,
    K10_ORIGIN_PROFILE,
    K11_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)

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
    last_binding = max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    return tuple(
        action
        for index, action in enumerate(actions)
        if not (isinstance(action, SetSeriesStyle) and index < last_binding)
    )


class ColumnFamilyOriginProject:
    """One explicit binder; the official template retains chart semantics."""

    def __init__(
        self,
        op: Any,
        *,
        profile_id: Literal["K09", "K10", "K11"],
    ) -> None:
        self.op = op
        self.profile_id = profile_id
        self.profile: OriginTemplateProfile = {
            "K09": K09_ORIGIN_PROFILE,
            "K10": K10_ORIGIN_PROFILE,
            "K11": K11_ORIGIN_PROFILE,
        }[profile_id]
        self.series_key = "group" if profile_id == "K09" else "component"
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, self.profile)
        grid = self._grid(document, data)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
        self.sheet = book[0]
        self._write_data(grid)
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
        for index in range(len(grid.series_labels)):
            plot = self.layer.add_plot(self.sheet, coly=index + 1, colx=0, type="?")
            if plot is None:
                raise RuntimeError(f"Origin rejected {self.profile_id} native series {index + 1}")
            self.plots.append(plot)
        if len(self.plots) > 1:
            self.layer.group(True, 0, len(self.plots) - 1)
        if self.profile_id == "K09":
            # One explicit, bounded native edit.  The official COLUMN template
            # defines all other appearance; width only prevents dynamic groups
            # from overlapping as their count changes.
            width_ratio = 0.8 / len(self.plots)
            self.plots[0].set_cmd(f"-vg {round((1.0 - width_ratio) * 100)}")
        self.layer.rescale()
        self._set_legend(grid, True)

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
        grid = self._grid(document, data)
        token = document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
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
                if axis_name == "x" and action.scale != "categorical":
                    raise ValueError("Origin column category axes support only categorical scale")
                if axis_name == "y":
                    if action.scale not in {"linear", "log10"}:
                        raise ValueError("Origin column value axes support only linear or log10")
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
                plot.color = action.color
            if action.line_width_pt is not None:
                plot.set_float("line.width", action.line_width_pt)
            return
        if isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError(f"{self.profile_id} legend target does not belong to this plot")
            self._set_legend(grid, bool(action.visible))
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
        grid = self._grid(document, data)
        if len(self.plots) != len(grid.series_labels):
            raise RuntimeError(f"Origin {self.profile_id} native series count differs after reopen")
        self._assert_values(self.sheet.to_list(0), grid.category_labels, "category")
        for index, expected in enumerate(zip(*grid.values, strict=True), start=1):
            self._assert_values(self.sheet.to_list(index), tuple(expected), f"series {index}")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {
            "series_count": len(grid.series_labels),
            "profile": self.profile_id,
        }
        for action in actions:
            if isinstance(action, SetTitle):
                title = self.layer.label(_TITLE_NAME)
                if title is None or title.text != action.text or not title.get_int("show"):
                    raise RuntimeError(f"Origin {self.profile_id} title did not survive readback")
                snapshot["title"] = title.text
            elif isinstance(action, SetAxis) and action.label is not None:
                axis_name = "x" if action.target == f"axis:{token}.x" else "y"
                label = self.layer.label("xb" if axis_name == "x" else "yl")
                if label is None or label.text != action.label:
                    raise RuntimeError(
                        f"Origin {self.profile_id} axis label did not survive readback"
                    )
            elif isinstance(action, SetSeriesStyle):
                ordinal = self._series_ordinal(action.target, token, len(self.plots))
                plot = self.plots[ordinal - 1]
                if action.color is not None and tuple(plot.color) != self._hex_rgb(action.color):
                    raise RuntimeError(
                        f"Origin {self.profile_id} series color did not survive readback"
                    )
                if action.line_width_pt is not None and (
                    abs(float(plot.get_float("line.width")) - action.line_width_pt) > 0.01
                ):
                    raise RuntimeError(
                        f"Origin {self.profile_id} edge width did not survive readback"
                    )
            elif isinstance(action, SetLegend) and action.visible is not None:
                legend = self.layer.label("legend")
                if legend is None or bool(legend.get_int("show")) != action.visible:
                    raise RuntimeError(
                        f"Origin {self.profile_id} legend visibility did not survive readback"
                    )
                if action.visible and legend.text.count("\\l(") != len(grid.series_labels):
                    raise RuntimeError(f"Origin {self.profile_id} legend lost a native sample")
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
                    semantic_id=f"series:{token}.{self.series_key}_{index}",
                    backend="origin",
                    object_kind=f"{self.profile_id.lower()}_native_series",
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

    def _grid(self, document: PlotDocument, data: EngineDataView) -> CategorySeriesGrid:
        grid = category_series_grid(document, data, profile_id=self.profile_id)
        if self.profile_id != "K11":
            return grid
        values = tuple(tuple(value for value in row) for row in grid.values)
        if any(value < 0 for row in values for value in row if not isnan(value)):
            raise ValueError("K11 percent-stack values must be non-negative")
        totals = tuple(sum(value for value in row if not isnan(value)) for row in values)
        if any(total <= 0 for total in totals):
            raise ValueError("K11 each category must have a positive total")
        normalized = tuple(
            tuple(float("nan") if isnan(value) else value / total * 100.0 for value in row)
            for row, total in zip(values, totals, strict=True)
        )
        return CategorySeriesGrid(
            category_labels=grid.category_labels,
            series_labels=grid.series_labels,
            values=normalized,
            category_field_name=grid.category_field_name,
            value_field_name="Percent",
        )

    def _write_data(self, grid: CategorySeriesGrid) -> None:
        self.sheet.from_list(
            0,
            list(grid.category_labels),
            lname=grid.category_field_name,
            axis="X",
        )
        for index, (label, values) in enumerate(
            zip(grid.series_labels, zip(*grid.values, strict=True), strict=True),
            start=1,
        ):
            self.sheet.from_list(index, list(values), lname=label, axis="Y")

    def _set_legend(self, grid: CategorySeriesGrid, visible: bool) -> None:
        legend = self.layer.label("legend")
        if visible and legend is None:
            self.layer.activate()
            if not self.layer.obj.LT_execute("legend"):
                raise RuntimeError(f"Origin could not create the {self.profile_id} legend")
            legend = self.layer.label("legend")
        if legend is not None:
            legend.text = "\n".join(
                f"\\l({index}, style:b) {_safe_label(label)}"
                for index, label in enumerate(grid.series_labels, start=1)
            )
            legend.set_int("link", 1)
            legend.set_int("show", int(visible))

    def _series_ordinal(self, target: str, token: str, series_count: int) -> int:
        prefix = f"series:{token}.{self.series_key}_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        if not suffix.isdigit() or not 1 <= int(suffix) <= series_count:
            raise ValueError(f"{self.profile_id} series target is outside the materialized data")
        return int(suffix)

    @staticmethod
    def _hex_rgb(value: str) -> tuple[int, int, int]:
        return cast(tuple[int, int, int], tuple(int(value[i : i + 2], 16) for i in (1, 3, 5)))

    def _assert_values(
        self,
        actual: list[object],
        expected: tuple[object, ...],
        role: str,
    ) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin {self.profile_id} {role} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, float) and isnan(wanted) and observed is None:
                continue
            if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
                if abs(float(cast(Any, observed)) - float(wanted)) <= 1e-9:
                    continue
            elif observed == wanted:
                continue
            raise RuntimeError(f"Origin {self.profile_id} {role} values differ after reopen")


def _execute(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
    profile_id: Literal["K09", "K10", "K11"],
) -> EngineReadback:
    # Dynamic group/component counts make recreating from the official
    # template safer than mutating an earlier project's native plot group.
    project = ColumnFamilyOriginProject(op, profile_id=profile_id)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    for action in actions:
        project.apply(request.document, action, request.data)
    project.save(output)
    reopened = ColumnFamilyOriginProject(op, profile_id=profile_id)
    reopened.reopen(output)
    return reopened.verify(request.document, actions, request.data)


def execute_k09_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K09")


def execute_k10_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K10")


def execute_k11_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output, "K11")
