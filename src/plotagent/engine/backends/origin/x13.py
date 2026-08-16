"""X13 official PopulationPyramid template binder."""

from __future__ import annotations

from math import isclose, isnan
from pathlib import Path
from typing import Any, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import PopulationPyramidData, x13_population_pyramid
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import X13_ORIGIN_PROFILE, resolve_official_template

_COLUMN = 203
_OFFICIAL_COMMAND = "worksheet -s 1 0 3 0; run.section(plot,PopulationPyramid);"
_TITLE_NAME = "_ENGINE_TITLE"
_CATEGORY_PREFIX = "X13C"


def _safe_label(value: str) -> str:
    return "".join(
        f"\\x({ord(character):04X})" if character in {"\\", "%", "$"} else character
        for character in value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    ).strip()


class X13OriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layers: tuple[Any, Any] | None = None
        self.plots: tuple[Any, Any] | None = None
        self.book: Any = None
        self.sheet: Any = None

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        template = resolve_official_template(install_dir, X13_ORIGIN_PROFILE)
        pyramid = x13_population_pyramid(document, data)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        self.book = self.op.new_book("w", f"D{token}", hidden=True)
        if self.book is None:
            raise RuntimeError("Origin could not create the X13 data workbook")
        for residue in tuple(self.op.pages("w")):
            if residue.name == "Book1" and residue.name != self.book.name:
                residue.destroy()
        self.sheet = self.book[0]
        self._write_data(pyramid)
        self.sheet.activate()
        self.op.lt_exec(_OFFICIAL_COMMAND)
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError(
                "Origin PopulationPyramid menu section must create exactly one graph"
            )
        self.graph = graphs[0]
        self.graph.name = f"G{token}"
        self.graph.lname = f"X13 {template.stem} / {document.plot_id}"
        self._bind_native_graph()
        self._assert_native_structure(verify_offsets=False)
        self._materialize_center_categories(pyramid)

    def reopen(self, project_path: Path, *, readonly: bool = True) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=readonly, asksave=False):
            raise RuntimeError("fresh Origin session could not reopen the staged X13 project")
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("fresh X13 project has unexpected graph or workbook count")
        self.graph, self.book = graphs[0], books[0]
        self.sheet = self.book[0]
        self._bind_native_graph()

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        if self.layers is None or self.plots is None:
            raise RuntimeError("X13 project is not initialized")
        x13_population_pyramid(document, data)
        document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        raise ValueError(f"Origin X13 binder cannot apply {action.operation}")

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Origin persists the active layer as part of the project view.  The
        # official population-pyramid page is intended to open on layer 1;
        # leaving layer 2 active can show only its opaque overlay on reopen.
        self.graph.activate()
        self.op.lt_exec(f"{self.graph.name}!page.active=1;")
        self.op.save(str(output_path))
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("Origin did not save a non-empty X13 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        if self.layers is None or self.plots is None:
            raise RuntimeError("X13 project is not initialized")
        pyramid = x13_population_pyramid(document, data)
        native = self._assert_native_structure(verify_offsets=True)
        expected = (pyramid.categories, pyramid.left_values, pyramid.right_values)
        for index, values in enumerate(expected):
            actual = tuple(self.sheet.to_list(index))
            if len(actual) != len(values) or any(
                str(found) != str(wanted)
                if isinstance(wanted, str)
                else abs(float(cast(Any, found)) - float(cast(Any, wanted))) > 1e-12
                for found, wanted in zip(actual, values, strict=True)
            ):
                raise RuntimeError(f"Origin X13 data column {index} differs after reopen")
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {"layers": 2, "categories": pyramid.categories}
        self._verify_center_categories(pyramid)
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
                    native_ref=f"graph:{self.graph.name}.layers:1-2.axis:x",
                ),
                EngineObjectRef(
                    semantic_id=f"axis:{token}.y",
                    backend="origin",
                    object_kind="axis",
                    native_ref=f"graph:{self.graph.name}.layer:1.axis:y",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.left",
                    backend="origin",
                    object_kind="native_population_column",
                    native_ref=f"graph:{self.graph.name}.layer:1.plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.right",
                    backend="origin",
                    object_kind="native_population_column",
                    native_ref=f"graph:{self.graph.name}.layer:2.plot:1",
                ),
                EngineObjectRef(
                    semantic_id=f"legend:{token}.main",
                    backend="origin",
                    object_kind="legend",
                    native_ref=f"graph:{self.graph.name}.layer:1.label:legend",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(cast(JsonValue, {**snapshot, **native})),
        )

    def _bind_native_graph(self) -> None:
        native_layers = tuple(self.graph)
        if len(native_layers) != 2:
            raise RuntimeError("Origin PopulationPyramid.otpu must provide exactly two layers")
        self.layers = (native_layers[0], native_layers[1])
        native_plots = tuple(tuple(layer.plot_list()) for layer in self.layers)
        if tuple(len(items) for items in native_plots) != (1, 1):
            raise RuntimeError("Origin PopulationPyramid must create one native plot per layer")
        self.plots = (native_plots[0][0], native_plots[1][0])

    def _materialize_center_categories(self, pyramid: PopulationPyramidData) -> None:
        if self.layers is None:
            raise RuntimeError("X13 project is not initialized")
        for layer_index in (1, 2):
            if not self.op.lt_exec(self._graph_layer_prefix(layer_index) + "axis -ps X L 0;"):
                raise RuntimeError("Origin could not hide X13 outer category tick labels")
        layer = self.layers[0]
        count = len(pyramid.categories)
        for row, category in enumerate(pyramid.categories, start=1):
            name = f"{_CATEGORY_PREFIX}{row:04d}"
            y_percent = self._category_page_y(row, count) * 100.0
            if not self.op.lt_exec(
                self._graph_layer_prefix(1)
                + f"label -p 100 {y_percent:.12g} -j 1 -n {name} CategoryPlaceholder;"
            ):
                raise RuntimeError(f"Origin could not create X13 category label {row}")
            label = layer.label(name)
            if label is None:
                raise RuntimeError(f"Origin could not address X13 category label {row}")
            label.text = str(category)
            label.set_int("show", 1)
            label.set_int("background", 1)
            label.set_int("fsize", 10)

    def _verify_center_categories(self, pyramid: PopulationPyramidData) -> None:
        if self.layers is None:
            raise RuntimeError("X13 project is not initialized")
        for row, category in enumerate(pyramid.categories, start=1):
            label = self.layers[0].label(f"{_CATEGORY_PREFIX}{row:04d}")
            if label is None or label.text != str(category) or not label.get_int("show"):
                raise RuntimeError(f"Origin X13 center category label {row} changed")

    @staticmethod
    def _category_page_y(row: int, count: int) -> float:
        if count <= 1:
            return 0.5
        return 1.0 - (row - 0.5) / count

    def _graph_layer_prefix(self, layer_index: int) -> str:
        return f"window -a {self.graph.name}; {self.graph.name}!page.active={layer_index}; "

    def _assert_native_structure(self, *, verify_offsets: bool) -> dict[str, object]:
        if self.book is None:
            raise RuntimeError("X13 source workbook is not initialized")
        expected_y_columns = ("B", "C")
        plot_ids: list[int] = []
        x_ranges: list[str] = []
        y_ranges: list[str] = []
        for layer_index, expected_y in enumerate(expected_y_columns, start=1):
            prefix = f"__X13{layer_index}"
            command = (
                self._graph_layer_prefix(layer_index)
                + f"__X13EX{layer_index}=layer.exchangexy; "
                + f"get %C -pt {prefix}PT; "
                + f"range -wx {prefix}X=1; range -wy {prefix}Y=1; "
                + f"string {prefix}XS$=%({prefix}X); "
                + f"string {prefix}YS$=%({prefix}Y);"
            )
            if verify_offsets:
                command += (
                    f" get %C -sx {prefix}SX; get %C -sxs {prefix}SXS;"
                    f" get %C -sy {prefix}SY; get %C -sys {prefix}SYS;"
                )
            self.op.lt_exec(command)
            plot_id = float(self.op.lt_float(f"{prefix}PT"))
            exchange_xy = float(self.op.lt_float(f"__X13EX{layer_index}"))
            if isnan(plot_id) or int(plot_id) != _COLUMN:
                raise RuntimeError(
                    f"Origin X13 layer {layer_index} is not ordinary Column PID {_COLUMN}"
                )
            if not isclose(exchange_xy, 1.0, abs_tol=1e-8):
                raise RuntimeError(
                    f"Origin X13 layer {layer_index} lost PopulationPyramid ExchangeXY"
                )
            x_range = str(self.op.get_lt_str(f"{prefix}XS"))
            y_range = str(self.op.get_lt_str(f"{prefix}YS"))
            source_prefix = f"[{self.book.name}]"
            if not x_range.startswith(source_prefix) or '!A"' not in x_range:
                raise RuntimeError(
                    f"Origin X13 layer {layer_index} lost category source A: {x_range!r}"
                )
            if not y_range.startswith(source_prefix) or f'!{expected_y}"' not in y_range:
                raise RuntimeError(
                    f"Origin X13 layer {layer_index} lost source {expected_y}: {y_range!r}"
                )
            if verify_offsets:
                values = (
                    float(self.op.lt_float(f"{prefix}SX")),
                    float(self.op.lt_float(f"{prefix}SXS")),
                    float(self.op.lt_float(f"{prefix}SY")),
                    float(self.op.lt_float(f"{prefix}SYS")),
                )
                if any(
                    not isclose(actual, expected, abs_tol=1e-8)
                    for actual, expected in zip(values, (0.0, 1.0, 0.0, 1.0), strict=True)
                ):
                    raise RuntimeError(
                        f"Origin X13 layer {layer_index} has non-native plot offset/scale {values}"
                    )
            plot_ids.append(int(plot_id))
            x_ranges.append(x_range)
            y_ranges.append(y_range)
        designations = [self.sheet.get_int(f"col{index}.type") for index in range(1, 4)]
        if designations != [4, 1, 1]:
            raise RuntimeError(
                f"Origin X13 source designation must remain XYY; observed {designations}"
            )
        datasets = tuple(str(plot.obj.DatasetName) for plot in self.plots or ())
        if len(datasets) != 2 or not datasets[0].endswith("_B") or not datasets[1].endswith("_C"):
            raise RuntimeError(
                f"Origin X13 Origin C datasets are not the native B/C sources: {datasets}"
            )
        self.op.lt_exec(
            self._graph_layer_prefix(2)
            + "__X13LINK=layer.link; __X13XLINK=layer.x.link; __X13YLINK=layer.y.link;"
        )
        link_target = int(self.op.lt_float("__X13LINK"))
        x_link = int(self.op.lt_float("__X13XLINK"))
        y_link = int(self.op.lt_float("__X13YLINK"))
        # PopulationPyramid.otpu links layer 2 to layer 1 with straight X
        # alignment and a custom mirrored Y transform. Origin's LINKED_AXIS
        # enum is None=0, Straight=1, Custom=2, Align=3.
        if (link_target, x_link, y_link) != (1, 1, 2):
            raise RuntimeError(
                "Origin X13 layer 2 lost its official parent/axis link signature; "
                f"observed {(link_target, x_link, y_link)}"
            )
        return {
            "official_menu_command": _OFFICIAL_COMMAND,
            "native_plot_ids": plot_ids,
            "exchange_xy": [True, True],
            "source_x_ranges": x_ranges,
            "source_y_ranges": y_ranges,
            "origin_c_datasets": list(datasets),
            "layer2_link": {"target": link_target, "x": x_link, "y": y_link},
            "worksheet_designations": designations,
        }

    def _assert_legend(
        self,
        pyramid: PopulationPyramidData,
        *,
        visible: bool,
        labels_written: bool,
    ) -> None:
        legend = self.layers[0].label("legend") if self.layers is not None else None
        if legend is None or legend.get_int("link") != 1:
            raise RuntimeError("Origin X13 legend is not a linked native legend")
        if bool(legend.get_int("show")) != visible:
            raise RuntimeError("Origin X13 legend visibility changed after reopen")
        text = str(legend.text)
        if text.count(r"\l(") != 2 or r"\l(1.1)" not in text or r"\l(2.1)" not in text:
            raise RuntimeError("Origin X13 legend lost its two cross-layer native samples")
        if labels_written and any(
            _safe_label(label) not in text
            for label in (pyramid.left_field_name, pyramid.right_field_name)
        ):
            raise RuntimeError("Origin X13 legend labels changed after reopen")

    def _write_data(self, pyramid: PopulationPyramidData) -> None:
        columns: tuple[tuple[str, tuple[object, ...], str], ...] = (
            (pyramid.category_field_name, pyramid.categories, "X"),
            (pyramid.left_field_name, pyramid.left_values, "Y"),
            (pyramid.right_field_name, pyramid.right_values, "Y"),
        )
        for index, (label, values, axis) in enumerate(columns):
            self.sheet.from_list(index, list(values), lname=label, axis=axis)


def execute_x13_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    structure_output = output.with_name(f"{output.stem}.official-structure.opju")
    project = X13OriginProject(op)
    project.create(install_dir, request.document, request.data)
    project.save(structure_output)

    editable = X13OriginProject(op)
    editable.reopen(structure_output, readonly=False)
    for action in request.actions:
        editable.apply(request.document, action, request.data)
    editable.save(output)

    reopened = X13OriginProject(op)
    reopened.reopen(output)
    readback = reopened.verify(request.document, request.actions, request.data)
    structure_output.unlink(missing_ok=True)
    return readback
