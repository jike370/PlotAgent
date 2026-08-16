"""K24 official ``Grouped.otp`` Trellis binder."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isnan
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
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import TrellisData, k24_trellis_data
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K24_ORIGIN_PROFILE, resolve_official_template
from .trace import origin_trace_step, record_origin_trace

_TITLE_NAME = "_ENGINE_TITLE"
_COLORS = ("#2A6FDB", "#D94B4B", "#2A9D6F", "#8A5CC2", "#D88700")


@dataclass(frozen=True, slots=True)
class _K24State:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None
    x_reverse: bool = False
    y_reverse: bool = False


@dataclass(frozen=True, slots=True)
class _K24Style:
    color: str | None = None


class K24OriginProject:
    """Create one native single-layer Trellis graph through ``plot_group``."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.last_native_structure: dict[str, object] | None = None

    def create(
        self,
        install_dir: Path,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        with origin_trace_step(
            "official_template_resolve",
            details={"template_filename": K24_ORIGIN_PROFILE.filename},
        ):
            template = resolve_official_template(install_dir, K24_ORIGIN_PROFILE)
        trellis = k24_trellis_data(document, data)
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        with origin_trace_step("workbook_create"):
            book = self.op.new_book("w", f"D{token}", hidden=True)
            if book is None:
                raise RuntimeError("Origin could not create the K24 workbook")
            for residue in tuple(self.op.pages("w")):
                if residue.name == "Book1" and residue.name != book.name:
                    residue.destroy()
            self.sheet = book[0]
        with origin_trace_step(
            "source_data_write",
            details={
                "column_count": 3,
                "row_count": len(trellis.x_values),
                "facet_count": len(trellis.facet_labels),
                "designations": ["X", "Y", "N"],
                "facet_column_contains_text_groups": True,
            },
        ):
            self._write(trellis)
        with origin_trace_step(
            "official_plot_group_execute",
            details={
                "route": "plot_group X-Function",
                "plot_type": "linesymb",
                "horizontal_group_role": "facet",
                "color_group_role": "facet",
                "template_filename": template.name,
                "ordinary_primitive_fallback_used": False,
            },
        ):
            self.sheet.activate()
            source = self.sheet.lt_range(False)
            command = (
                f"plot_group iy:={source}!(A,B) type:=linesymb dyaxes:=0 "
                f"horz:={source}!(C) color:={source}!(C) template:={template.stem};"
            )
            self.op.lt_exec(command)
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin plot_group must create exactly one K24 graph")
        self.graph = graphs[0]
        self.graph.lname = f"K24 Trellis / {document.plot_id}"
        layers = tuple(self.graph)
        if len(layers) != 1:
            raise RuntimeError("Origin K24 Trellis must remain one native layer")
        self.layer = layers[0]
        self.layer.rescale()
        with origin_trace_step("native_structure_readback"):
            native = self._native_structure(trellis)
        self.last_native_structure = native
        record_origin_trace("native_structure_confirmed", "completed", details=native)

    def open(self, output: Path, *, readonly: bool = False) -> None:
        with origin_trace_step("origin_project_initialize"):
            self.op.new(asksave=False)
        with origin_trace_step(
            "opju_open", details={"filename": output.name, "readonly": readonly}
        ):
            if not self.op.open(str(output), readonly=readonly, asksave=False):
                raise RuntimeError("Origin could not reopen K24")
        graphs, books = list(self.op.pages("g")), list(self.op.pages("w"))
        if len(graphs) != 1 or len(books) != 1:
            raise RuntimeError("K24 must contain one graph and one workbook")
        self.graph, self.sheet = graphs[0], books[0][0]
        layers = tuple(self.graph)
        if len(layers) != 1:
            raise RuntimeError("K24 Trellis changed from its one-layer native structure")
        self.layer = layers[0]

    def reconcile(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> None:
        trellis = k24_trellis_data(document, data)
        with origin_trace_step("agent_actions_apply", details={"action_count": len(actions)}):
            state, styles = self._state(document, actions, trellis)
            self._set_axis_state(state)
            self._set_title(state.title)
            self._apply_facet_colors(styles)

    def save(self, output: Path) -> None:
        with origin_trace_step("opju_save", details={"filename": output.name}):
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                raise FileExistsError(
                    f"Origin refuses to overwrite existing K24 artifact: {output}"
                )
            self.op.save(str(output))
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("Origin did not save a non-empty K24 project")

    def verify(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
    ) -> EngineReadback:
        trellis = k24_trellis_data(document, data)
        state, styles = self._state(document, actions, trellis)
        with origin_trace_step("reopened_source_data_verify"):
            self._assert_values(self.sheet.to_list(0), trellis.x_values, "X")
            self._assert_values(self.sheet.to_list(1), trellis.y_values, "Y")
            self._assert_values(self.sheet.to_list(2), trellis.facet_values, "facet")
        with origin_trace_step("reopened_native_structure_verify"):
            native = self._native_structure(trellis)
        with origin_trace_step("reopened_agent_edits_verify"):
            self._assert_labels(state)
            self._assert_axis_limits(state)
            self._assert_facet_colors(styles)
        self.last_native_structure = native
        token = document.plot_id.removeprefix("plot:")
        objects: list[EngineObjectRef] = [
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
        ]
        for index in range(len(trellis.facet_labels)):
            objects.extend(
                (
                    EngineObjectRef(
                        semantic_id=f"panel:{token}.facet_{index + 1}",
                        backend="origin",
                        object_kind="facet_panel",
                        native_ref=(f"graph:{self.graph.name}.layer:1.trellis_panel:{index + 1}"),
                    ),
                    EngineObjectRef(
                        semantic_id=f"series:{token}.facet_{index + 1}",
                        backend="origin",
                        object_kind="facet_series",
                        native_ref=(f"graph:{self.graph.name}.layer:1.trellis_subset:{index + 1}"),
                    ),
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
                        "styles": [asdict(style) for style in styles],
                        "native_structure": native,
                    },
                )
            ),
        )

    def _write(self, trellis: TrellisData) -> None:
        self.sheet.cols = 3
        self.sheet.from_list(0, list(trellis.x_values), lname=trellis.x_field_name, axis="X")
        self.sheet.from_list(1, list(trellis.y_values), lname=trellis.y_field_name, axis="Y")
        self.sheet.from_list(
            2,
            list(trellis.facet_values),
            lname=trellis.facet_field_name,
            axis="N",
        )

    def _native_structure(self, trellis: TrellisData) -> dict[str, object]:
        self.graph.activate()
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe K24 graph name for readback: {graph_name!r}")
        self.op.lt_exec(
            "page.active=1; layer -c; __K24COUNT=count; "
            f"range __K24P=[{graph_name}]1!1; get __K24P -pt __K24PID; "
            "range -wx __K24X=__K24P; range -wy __K24Y=__K24P; "
            "string __K24XS$=%(__K24X); string __K24YS$=%(__K24Y);"
        )
        plot_count = int(self.op.lt_float("__K24COUNT"))
        plot_id = int(self.op.lt_float("__K24PID"))
        x_source = str(self.op.get_lt_str("__K24XS"))
        y_source = str(self.op.get_lt_str("__K24YS"))
        layer_count = len(tuple(self.graph))
        if layer_count != 1 or plot_count != 1 or plot_id != 202:
            raise RuntimeError("Origin K24 must retain one single-layer PID 202 Trellis")
        if "!A" not in x_source or "!B" not in y_source:
            raise RuntimeError("Origin K24 lost the source X/Y range binding")
        designations = tuple(int(self.sheet.get_int(f"col{index}.type")) for index in range(1, 4))
        if designations != (4, 1, 2):
            raise RuntimeError("Origin K24 source designations must remain X/Y/N")
        observed_labels = tuple(dict.fromkeys(str(value) for value in self.sheet.to_list(2)))
        if observed_labels != trellis.facet_labels:
            raise RuntimeError("Origin K24 facet order differs from the source contract")
        return {
            "official_route": "plot_group",
            "official_template": K24_ORIGIN_PROFILE.filename,
            "ordinary_primitive_fallback_used": False,
            "layer_count": layer_count,
            "plot_count": plot_count,
            "native_plot_type": plot_id,
            "x_source": x_source,
            "y_source": y_source,
            "source_designations": list(designations),
            "facet_column_storage": "text N grouping column",
            "facet_count": len(observed_labels),
            "facet_labels": list(observed_labels),
        }

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        trellis: TrellisData,
    ) -> tuple[_K24State, tuple[_K24Style, ...]]:
        document.plot_id.removeprefix("plot:")
        state = _K24State(x_label=trellis.x_field_name, y_label=trellis.y_field_name)
        styles = tuple(_K24Style() for _label in trellis.facet_labels)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetChartParameter):
                raise ValueError("K24 exposes neither a standalone legend nor manual panel layout")
            raise ValueError(f"Origin K24 cannot apply {action.operation}")
        return state, styles

    def _set_axis_state(self, state: _K24State) -> None:
        for axis_name in ("x", "y"):
            minimum = getattr(state, f"{axis_name}_minimum")
            maximum = getattr(state, f"{axis_name}_maximum")
            reverse = getattr(state, f"{axis_name}_reverse")
            native = self.layer.axis(axis_name)
            if minimum is not None and maximum is not None:
                begin, end = float(minimum), float(maximum)
                if reverse:
                    begin, end = end, begin
                native.set_limits(begin, end)
            elif reverse:
                limits = getattr(native, "limits", (0.0, 1.0, 0.1))
                native.set_limits(float(limits[1]), float(limits[0]))
        self._set_axis_label("x", state.x_label)
        self._set_axis_label("y", state.y_label)

    def _set_axis_label(self, axis_name: str, text: str) -> None:
        label = self.layer.label("xb" if axis_name == "x" else "yl")
        if label is None:
            label = self.layer.add_label(text)
        if label is None:
            raise RuntimeError("Origin K24 template has no writable axis label")
        label.text = text
        label.set_int("show", 1)

    def _set_title(self, text: str) -> None:
        title = self.layer.label(_TITLE_NAME)
        if title is None and text:
            self.layer.activate()
            if not self.layer.obj.LT_execute(
                f"label -b 4 -j 1 -n {_TITLE_NAME} PlotAgentTitlePlaceholder;"
            ):
                raise RuntimeError("Origin could not create the K24 title")
            title = self.layer.label(_TITLE_NAME)
        if title is not None:
            title.text = text
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.06)
            title.set_int("show", int(bool(text)))

    def _apply_facet_colors(self, styles: tuple[_K24Style, ...]) -> None:
        if not any(style.color is not None for style in styles):
            return
        native = self._read_color_list("-cu", len(styles), "__K24DEFAULT")
        values: list[str] = []
        for index, style in enumerate(styles):
            if style.color is not None:
                values.append(f'color("{style.color}")')
            elif index < len(native) and not isnan(native[index]):
                values.append(str(int(native[index])))
            else:
                values.append(f'color("{_COLORS[index % len(_COLORS)]}")')
        expression = ",".join(values)
        self.graph.activate()
        self.op.lt_exec(
            f"dataset __K24COLORS={{{expression}}}; "
            "set %C -cue 1; set %C -cu __K24COLORS; "
            "set %C -cus __K24COLORS; set %C -cusf __K24COLORS;"
        )

    def _assert_facet_colors(self, styles: tuple[_K24Style, ...]) -> None:
        edited = tuple(
            (index, style.color) for index, style in enumerate(styles, start=1) if style.color
        )
        if not edited:
            return
        self.graph.activate()
        self.op.lt_exec("get %C -cue __K24ENABLED;")
        if int(self.op.lt_float("__K24ENABLED")) != 1:
            raise RuntimeError("Origin K24 facet color list was disabled after reopen")
        for option, variable in (
            ("-cu", "__K24LINE"),
            ("-cus", "__K24SYMBOL"),
            ("-cusf", "__K24FILL"),
        ):
            values = self._read_color_list(option, len(styles), variable)
            for ordinal, color in edited:
                expected = int(self.op.lt_float(f'color("{color}")'))
                if ordinal > len(values) or int(values[ordinal - 1]) != expected:
                    raise RuntimeError(f"Origin K24 {option} facet color did not survive readback")

    def _read_color_list(self, option: str, count: int, variable: str) -> tuple[float, ...]:
        self.graph.activate()
        self.op.lt_exec(f"dataset {variable}; get %C {option} {variable};")
        return tuple(
            float(self.op.lt_float(f"{variable}[{index}]")) for index in range(1, count + 1)
        )

    def _assert_labels(self, state: _K24State) -> None:
        x_label = self.layer.label("xb")
        y_label = self.layer.label("yl")
        if x_label is None or x_label.text != state.x_label:
            raise RuntimeError("Origin K24 X-axis label did not survive readback")
        if y_label is None or y_label.text != state.y_label:
            raise RuntimeError("Origin K24 Y-axis label did not survive readback")
        title = self.layer.label(_TITLE_NAME)
        if state.title and (
            title is None or title.text != state.title or title.get_int("show") == 0
        ):
            raise RuntimeError("Origin K24 title did not survive readback")

    def _assert_axis_limits(self, state: _K24State) -> None:
        for axis_name in ("x", "y"):
            minimum = getattr(state, f"{axis_name}_minimum")
            maximum = getattr(state, f"{axis_name}_maximum")
            if minimum is None or maximum is None:
                continue
            observed = tuple(float(value) for value in self.layer.axis(axis_name).limits[:2])
            expected = (float(minimum), float(maximum))
            if getattr(state, f"{axis_name}_reverse"):
                expected = expected[::-1]
            if any(
                abs(left - right) > 1e-8 for left, right in zip(observed, expected, strict=True)
            ):
                raise RuntimeError(f"Origin K24 {axis_name.upper()} limits changed after reopen")

    @staticmethod
    def _assert_values(actual: list[Any], expected: tuple[Any, ...], label: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin K24 {label} row count changed after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if isinstance(wanted, float) and isnan(wanted):
                if not isinstance(observed, float) or not isnan(observed):
                    raise RuntimeError(f"Origin K24 {label} missing value changed after reopen")
            elif observed != wanted:
                raise RuntimeError(f"Origin K24 {label} values changed after reopen")


def execute_k24_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    # A panel-set change is structural.  The stable path is to invoke the
    # official X-Function again and replay the declarative Agent actions.
    project = K24OriginProject(op)
    with origin_trace_step(
        "official_rebuild_from_document",
        details={
            "previous_project_ignored": request.previous_opju is not None,
            "reason": "Trellis panel membership is data driven",
        },
    ):
        project.create(install_dir, request.document, request.data)
        project.reconcile(request.document, request.actions, request.data)
    project.save(output)
    reopened = K24OriginProject(op)
    reopened.open(output, readonly=True)
    return reopened.verify(request.document, request.actions, request.data)
