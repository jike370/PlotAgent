"""Closed worksheet/XY template binder shared by simple Agent Native profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineColumn,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.repository import document_ref

from .profile import OriginTemplateProfile, resolve_official_template

_LINE_STYLE_CODES = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3, "none": 10}
_SYMBOL_CODES = {
    "square": 1,
    "circle": 2,
    "triangle": 3,
    "triangle_up": 3,
    "diamond": 5,
}
_TITLE_NAME = "_ENGINE_TITLE"


@dataclass(frozen=True, slots=True)
class OriginXYDefinition:
    template: OriginTemplateProfile
    plot_type: str
    object_kind: str
    supports_line: bool
    supports_symbol: bool


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

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        document.plot_id.removeprefix("plot:")
        if isinstance(action, CreatePlot):
            return
        if isinstance(action, BindFields):
            self._write_data(document, data)
            self.layer.rescale()
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
