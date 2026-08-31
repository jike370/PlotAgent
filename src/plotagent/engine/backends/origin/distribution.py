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
    SetObservationOverlay,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import (
    DistributionData,
    distribution_groups,
    regular_observation_positions,
)
from plotagent.engine.product_style import k14_auto_range_bounds
from plotagent.engine.repository import document_ref
from plotagent.plot_calculations.kernels import scott_kde_geometry

from .messages import OriginWorkerRequest
from .native_distribution import (
    BOX_RANGE,
    BOX_TYPE,
    DIST_BANDWIDTH,
    DIST_BANDWIDTH_FACTOR,
    DIST_CURVE_SCALE,
    DIST_CURVE_TYPE,
    DIST_EXTEND,
    DIST_SCALE_TYPE,
    HAS_OUTLIERS,
    WHISKER_COEFF,
    WHISKER_RANGE,
    configure_native_distribution,
    read_native_distribution_value,
    set_native_distribution_outliers,
)
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
_SYMBOL_CODES = {
    "circle": 2,
    "square": 1,
    "triangle": 3,
    "triangle_up": 3,
    "triangle_down": 4,
    "diamond": 5,
}
_INTERIOR_CODES = {"solid": 0, "open": 1, "hollow": 1}
_X05_OFFICIAL_MENU_COMMAND = "worksheet -s 1 0 {last_column} 0; worksheet -p 206 Beeswarm;"
_OFFICIAL_MENU_COMMANDS = {
    "K12": "worksheet -s 1 0 {last_column} 0; worksheet -p 206 ColumnScatter;",
    "K13": "worksheet -s 1 0 {last_column} 0; worksheet -p 206 Box;",
    "K14": "worksheet -s 1 0 {last_column} 0; worksheet -p 206 Violin;",
}

# Origin 2024's native BoxChart enums (OriginC/System/OC_const.h).
_BOX_TYPE_BOX = 0
_BOX_RANGE_25_75 = 2
_WHISKER_RANGE_OUTLIER = 6

# Origin 2024 distribution fields: Kernel Smooth curve, negative custom
# bandwidth selector (report_utils.c), and Width scale (Count/Width/Area order).
_KERNEL_SMOOTH = 8
_BANDWIDTH_CUSTOM = -1
_BANDWIDTH_CUSTOM_READBACK = 255
_VIOLIN_SCALE_WIDTH = 1
_VIOLIN_GRID_POINTS = 256
_BOX_OUTLIER_LEGEND = '\\l(1,O) %(1,@V"Box_O")'
# OriginPro 2024's COM/LabTalk text bridge is code-page dependent.  Keep this
# engine-authored legend entry ASCII so a Chinese Windows code page cannot
# corrupt it during save/reopen.
_RAW_OBSERVATION_LEGEND_LABEL = "Raw observations"


def _effective_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[PlotEngineAction, ...]:
    return actions


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
        if self.profile_id != "X05":
            self._remove_workbook_residue(book)
        if self.profile_id == "X05":
            command = _X05_OFFICIAL_MENU_COMMAND.format(last_column=len(distribution.groups))
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
                    self._rebuild_native_data_legend()
                native = self._assert_official_x05_structure(distribution)
            record_origin_trace("native_beeswarm_confirmed", "completed", details=native)
            self.layer.rescale()
            return
        command = _OFFICIAL_MENU_COMMANDS[self.profile_id].format(
            last_column=len(distribution.groups)
        )
        with origin_trace_step(
            "official_plot_command_execute",
            details={"labtalk": command, "template_filename": template.name},
        ):
            self.sheet.activate()
            if not self.op.lt_exec(command):
                raise RuntimeError(f"Origin rejected the official {self.profile_id} plot command")
        with origin_trace_step("native_structure_readback"):
            graphs = list(self.op.pages("g"))
            if len(graphs) != 1:
                raise RuntimeError(
                    f"Origin {self.profile_id} command must create exactly one graph"
                )
            self.graph = graphs[0]
            self.graph.name = f"G{token}"
            self.graph.lname = f"{self.profile_id} {template.stem} / {document.plot_id}"
            self.layer = self.graph[0]
            self.plots = list(self.layer.plot_list())
            self._configure_native_profile(distribution)
            native = self._assert_official_structure(distribution)
        record_origin_trace(
            f"native_{self.profile_id.lower()}_confirmed",
            "completed",
            details=native,
        )
        self.layer.rescale()
        if self.profile_id == "K14":
            self._apply_k14_product_geometry(distribution)

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

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        distribution = self._distribution(document, data)
        document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
            return
        if isinstance(action, SetObservationOverlay) and self.profile_id == "K13":
            self._apply_observation_overlay(distribution, action)
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
        overlay = next(
            (
                action
                for action in reversed(actions)
                if isinstance(action, SetObservationOverlay)
            ),
            None,
        )
        expected_plot_count = len(distribution.groups) * (2 if overlay is not None else 1)
        if len(self.plots) != expected_plot_count:
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
        else:
            snapshot.update(self._assert_official_structure(distribution, overlay))
        if self.profile_id == "K14":
            snapshot["product_geometry"] = self._assert_k14_product_geometry(
                distribution
            )
        if overlay is not None:
            snapshot["observation_overlay"] = self._verify_observation_overlay(
                distribution,
                overlay,
            )
        group_count = len(distribution.groups)
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
                for index in range(1, group_count + 1)
            ),
            *(
                (
                    EngineObjectRef(
                        semantic_id=f"observation_overlay:{token}.raw",
                        backend="origin",
                        object_kind="observation_overlay",
                        native_ref=(
                            f"graph:{self.graph.name}.layer:1.plots:"
                            f"{group_count + 1}-{group_count * 2}"
                        ),
                    ),
                )
                if overlay is not None
                else ()
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

    def _apply_k14_product_geometry(self, distribution: DistributionData) -> None:
        x_label = self.layer.label("xb")
        y_label = self.layer.label("yl")
        if x_label is None or y_label is None:
            raise RuntimeError("Origin K14 official template is missing an axis title object")
        x_label.text = "Group"
        y_label.text = distribution.value_field_name
        x_label.set_int("show", 1)
        y_label.set_int("show", 1)
        x_bounds, y_bounds = k14_auto_range_bounds(
            tuple(value for group in distribution.groups for value in group.values),
            len(distribution.groups),
        )
        self.layer.axis("x").limits = x_bounds
        self.layer.axis("y").limits = y_bounds

    def _assert_k14_product_geometry(
        self,
        distribution: DistributionData,
    ) -> dict[str, object]:
        x_label = self.layer.label("xb")
        y_label = self.layer.label("yl")
        if x_label is None or y_label is None:
            raise RuntimeError("Origin K14 lost an axis title after reopen")
        if (
            str(x_label.text) != "Group"
            or str(y_label.text) != distribution.value_field_name
            or int(x_label.get_int("show")) != 1
            or int(y_label.get_int("show")) != 1
        ):
            raise RuntimeError("Origin K14 axis titles differ after reopen")
        x_bounds, y_bounds = k14_auto_range_bounds(
            tuple(value for group in distribution.groups for value in group.values),
            len(distribution.groups),
        )
        observed: dict[str, list[float] | str] = {
            "x_title": str(x_label.text),
            "y_title": str(y_label.text),
        }
        for axis_name, expected in (("x", x_bounds), ("y", y_bounds)):
            actual = tuple(float(value) for value in self.layer.axis(axis_name).limits[:2])
            if any(
                abs(left - right) > 1e-8
                for left, right in zip(actual, expected, strict=True)
            ):
                raise RuntimeError(
                    f"Origin K14 product {axis_name.upper()}-axis range changed after reopen"
                )
            observed[f"{axis_name}_limits"] = list(actual)
        return observed

    def _apply_observation_overlay(
        self,
        distribution: DistributionData,
        action: SetObservationOverlay,
    ) -> None:
        """Materialize deterministic scatter points over the official box plots."""

        group_count = len(distribution.groups)
        plots = list(self.layer.plot_list())
        if len(plots) not in {group_count, group_count * 2}:
            raise RuntimeError("Origin K13 observation overlay found unexpected plot structure")
        for index, group in enumerate(distribution.groups):
            x_values = regular_observation_positions(
                index + 1,
                len(group.values),
                action.jitter_fraction,
            )
            self.sheet.from_list(
                group_count + index,
                list(x_values),
                lname=f"{group.label} observation x",
                axis="X",
            )
        if len(plots) == group_count:
            for index in range(group_count):
                plot = self.layer.add_plot(
                    self.sheet,
                    coly=index,
                    colx=group_count + index,
                    type="s",
                )
                if plot is None:
                    raise RuntimeError("Origin K13 could not create a raw-observation plot")
            plots = list(self.layer.plot_list())
        self.plots = plots
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe Origin K13 graph name: {graph_name!r}")
        self.graph.activate()
        set_native_distribution_outliers(
            self.op,
            graph_name,
            1,
            visible=not action.visible,
        )
        self._update_observation_legend(group_count, visible=action.visible)
        if not self.op.lt_exec("layer -gu;"):
            raise RuntimeError("Origin K13 could not make observation styles independent")
        for index in range(group_count):
            plot_index = group_count + index + 1
            plot_ref = f"__K13OBS{index + 1}"
            command = (
                f"range {plot_ref}=[{graph_name}]1!{plot_index}; "
                f"set {plot_ref} -k {_SYMBOL_CODES[action.marker_shape]}; "
                f"set {plot_ref} -z {action.marker_size_pt:.12g}; "
                f"set {plot_ref} -kf {_INTERIOR_CODES[action.marker_interior]}; "
                f'set {plot_ref} -csf color("{action.marker_fill_color}"); '
                f'set {plot_ref} -cse color("{action.marker_stroke_color}");'
            )
            if not self.op.lt_exec(command):
                raise RuntimeError("Origin K13 rejected an observation point style")
            self.layer.set_int(f"plot{plot_index}.show", int(action.visible))
            # ``Layer.set_float`` accepts only a subset of the LabTalk object
            # tree.  It appeared to succeed for ``plotN.symbol.transparency``
            # but Origin reopened the project with the template default.  Use
            # the same explicit layer plot property contract as the common T1
            # visual adapter so persistence is mechanically verifiable.
            if not self.op.lt_exec(
                f"layer.plot{plot_index}.symbol.transparency="
                f"{(1 - action.marker_opacity) * 100:.12g};"
            ):
                raise RuntimeError("Origin K13 rejected observation point opacity")

    def _update_observation_legend(self, group_count: int, *, visible: bool) -> None:
        """Keep the native box legend truthful after replacing outlier symbols."""

        legend = self.layer.label("legend")
        if legend is None:
            return
        raw_line = f"\\l({group_count + 1}) {_RAW_OBSERVATION_LEGEND_LABEL}"
        lines = [
            line
            for line in str(legend.text).splitlines()
            if 'Box_O' not in line and _RAW_OBSERVATION_LEGEND_LABEL not in line
        ]
        lines.append(raw_line if visible else _BOX_OUTLIER_LEGEND)
        legend.text = "\r\n".join(lines)

    def _configure_native_profile(self, distribution: DistributionData) -> None:
        if len(self.plots) != len(distribution.groups):
            raise RuntimeError(
                f"Origin {self.profile_id} official command produced the wrong group count"
            )
        if self.profile_id == "K12":
            # ColumnScatter.otp owns the official defaults.  OriginExt returns
            # no reliable native format tree for this plot, so only PID/source
            # structure is mechanically asserted and appearance stays a live
            # visual gate.
            return
        if self.profile_id == "K14":
            graph_name = str(self.graph.name)
            self.graph.activate()
            if not self.op.lt_exec(f"range __K14HEAD=[{graph_name}]1!1; set __K14HEAD -gm 1;"):
                raise RuntimeError("Origin could not make K14 group formatting independent")
        if self.profile_id == "K13":
            configure_native_distribution(
                self.op,
                str(self.graph.name),
                1,
                13,
            )
            return
        pooled_values = tuple(value for group in distribution.groups for value in group.values)
        bandwidth = scott_kde_geometry(
            pooled_values,
            grid_points=_VIOLIN_GRID_POINTS,
            extend_bandwidths=0.0,
        ).bandwidth
        configure_native_distribution(
            self.op,
            str(self.graph.name),
            1,
            14,
            bandwidth=bandwidth,
        )

    def _assert_official_structure(
        self,
        distribution: DistributionData,
        overlay: SetObservationOverlay | None = None,
    ) -> dict[str, object]:
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe Origin {self.profile_id} graph name: {graph_name!r}")
        self.graph.activate()
        variable_prefix = f"__{self.profile_id}"
        self.op.lt_exec(f"page.active=1; layer -c; {variable_prefix}COUNT=count;")
        plot_count = int(self.op.lt_float(f"{variable_prefix}COUNT"))
        plot_types: list[int] = []
        for index in range(1, plot_count + 1):
            self.op.lt_exec(
                f"range {variable_prefix}P=[{graph_name}]1!{index}; "
                f"get {variable_prefix}P -pt {variable_prefix}PT{index};"
            )
            plot_types.append(int(self.op.lt_float(f"{variable_prefix}PT{index}")))
        group_count = len(distribution.groups)
        expected_plot_count = group_count * (2 if overlay is not None else 1)
        box_plot_types = plot_types[:group_count]
        overlay_plot_types = plot_types[group_count:]
        if (
            plot_count != expected_plot_count
            or any(plot_type != 206 for plot_type in box_plot_types)
            or (overlay is not None and any(plot_type != 201 for plot_type in overlay_plot_types))
        ):
            raise RuntimeError(
                f"Origin {self.profile_id} is not the official PID 206 group structure: "
                f"plot_types={plot_types}, group_count={len(distribution.groups)}"
            )
        actual_designations = [
            int(self.sheet.get_int(f"col{index + 1}.type"))
            for index in range(len(distribution.groups))
        ]
        if actual_designations != [1] * len(distribution.groups):
            raise RuntimeError(
                f"Origin {self.profile_id} source columns must remain native Y columns"
            )
        expected_sources = [
            str(self.sheet.obj[index].DatasetName) for index in range(len(distribution.groups))
        ]
        actual_sources = [
            str(plot.obj.DatasetName) for plot in self.plots[:group_count]
        ]
        if actual_sources != expected_sources:
            raise RuntimeError(
                f"Origin {self.profile_id} native source bindings changed after readback"
            )

        if self.profile_id == "K12":
            return {
                "official_menu_command": _OFFICIAL_MENU_COMMANDS[self.profile_id].format(
                    last_column=len(distribution.groups)
                ),
                "native_plot_types": box_plot_types,
                "worksheet_designations": actual_designations,
                "native_sources": actual_sources,
                "native_settings": "official_default_requires_live_visual_gate",
            }

        native_settings: list[dict[str, int | float]] = []
        if self.profile_id == "K14":
            self.op.lt_exec(f"range __K14HEAD=[{graph_name}]1!1; get __K14HEAD -gm __K14GROUPMODE;")
            group_mode = int(self.op.lt_float("__K14GROUPMODE"))
            # The binder's individual-edit mode reads back as 1.  The shared
            # visual pass may subsequently dissolve the presentation group so
            # each visible PID 206 owns its style; Origin then reads 0.  Both
            # preserve independent groups, while native per-plot style
            # readback provides the stronger final proof.
            if group_mode not in {0, 1}:
                raise RuntimeError(
                    "Origin K14 lost independent per-group formatting: "
                    f"group_mode={group_mode}"
                )
        pooled_bandwidth = None
        if self.profile_id == "K14":
            pooled_values = tuple(value for group in distribution.groups for value in group.values)
            pooled_bandwidth = scott_kde_geometry(
                pooled_values,
                grid_points=_VIOLIN_GRID_POINTS,
                extend_bandwidths=0.0,
            ).bandwidth
        for index, _group in enumerate(distribution.groups, start=1):
            if self.profile_id == "K13":
                state: dict[str, int | float] = {
                    "BoxType": read_native_distribution_value(
                        self.op, graph_name, index, BOX_TYPE, numeric_type="int"
                    ),
                    "BoxRange": read_native_distribution_value(
                        self.op, graph_name, index, BOX_RANGE, numeric_type="int"
                    ),
                    "WhiskerRange": read_native_distribution_value(
                        self.op, graph_name, index, WHISKER_RANGE, numeric_type="int"
                    ),
                    "WhiskerCoeff": read_native_distribution_value(
                        self.op, graph_name, index, WHISKER_COEFF, numeric_type="double"
                    ),
                    "HasOutliers": read_native_distribution_value(
                        self.op, graph_name, index, HAS_OUTLIERS, numeric_type="int"
                    ),
                }
                if state != {
                    "BoxType": _BOX_TYPE_BOX,
                    "BoxRange": _BOX_RANGE_25_75,
                    "WhiskerRange": _WHISKER_RANGE_OUTLIER,
                    "WhiskerCoeff": 1.5,
                    "HasOutliers": 0 if overlay is not None and overlay.visible else 1,
                }:
                    raise RuntimeError("Origin K13 lost its explicit Tukey 1.5 x IQR contract")
            else:
                expected_bandwidth = pooled_bandwidth
                if expected_bandwidth is None:
                    raise RuntimeError("Origin K14 pooled bandwidth is unavailable")
                state = {
                    "CurveType": read_native_distribution_value(
                        self.op, graph_name, index, DIST_CURVE_TYPE, numeric_type="int"
                    ),
                    "CurveScale": read_native_distribution_value(
                        self.op, graph_name, index, DIST_CURVE_SCALE, numeric_type="int"
                    ),
                    "ScaleType": read_native_distribution_value(
                        self.op, graph_name, index, DIST_SCALE_TYPE, numeric_type="int"
                    ),
                    "BandwidthMode": read_native_distribution_value(
                        self.op, graph_name, index, DIST_BANDWIDTH, numeric_type="int"
                    ),
                    "Bandwidth": read_native_distribution_value(
                        self.op,
                        graph_name,
                        index,
                        DIST_BANDWIDTH_FACTOR,
                        numeric_type="double",
                    ),
                    "Extend": read_native_distribution_value(
                        self.op, graph_name, index, DIST_EXTEND, numeric_type="double"
                    ),
                }
                if (
                    state["CurveType"] != _KERNEL_SMOOTH
                    or state["CurveScale"] != 100
                    or state["ScaleType"] != _VIOLIN_SCALE_WIDTH
                    or state["BandwidthMode"] != _BANDWIDTH_CUSTOM_READBACK
                    or abs(float(state["Bandwidth"]) - expected_bandwidth) > 1e-12
                    or abs(float(state["Extend"])) > 1e-12
                ):
                    raise RuntimeError(
                        f"Origin K14 group {index} lost the shared violin bandwidth "
                        f"contract: observed={state!r}, expected_bandwidth="
                        f"{expected_bandwidth:.17g}"
                    )
            native_settings.append(state)
        return {
            "official_menu_command": _OFFICIAL_MENU_COMMANDS[self.profile_id].format(
                last_column=len(distribution.groups)
            ),
            "native_plot_types": box_plot_types,
            "observation_plot_types": overlay_plot_types,
            "worksheet_designations": actual_designations,
            "native_sources": actual_sources,
            "native_settings": native_settings,
        }

    def _verify_observation_overlay(
        self,
        distribution: DistributionData,
        action: SetObservationOverlay,
    ) -> dict[str, object]:
        if self.profile_id != "K13":
            raise RuntimeError("observation overlays are only valid for K13")
        group_count = len(distribution.groups)
        if len(self.plots) != group_count * 2:
            raise RuntimeError("Origin K13 observation plots did not survive reopen")
        designations = [
            int(self.sheet.get_int(f"col{group_count + index + 1}.type"))
            for index in range(group_count)
        ]
        if designations != [4] * group_count:
            raise RuntimeError("Origin K13 observation X columns lost their X designation")
        expected_sources = [
            str(self.sheet.obj[index].DatasetName) for index in range(group_count)
        ]
        actual_sources = [
            str(plot.obj.DatasetName) for plot in self.plots[group_count:]
        ]
        if actual_sources != expected_sources:
            raise RuntimeError("Origin K13 observation plots no longer reuse box Y sources")
        expected_fill = int(self.op.lt_float(f'color("{action.marker_fill_color}")'))
        expected_stroke = int(self.op.lt_float(f'color("{action.marker_stroke_color}")'))
        style_rows: list[dict[str, int | float]] = []
        x_positions: list[list[float]] = []
        graph_name = str(self.graph.name)
        self.graph.activate()
        x_start, x_end, x_step, *_ = (
            float(value) for value in self.layer.axis("x").limits
        )
        expected_x_limits = (0.5, group_count + 0.5, 1.0)
        if any(
            abs(observed - wanted) > 1e-12
            for observed, wanted in zip(
                (x_start, x_end, x_step), expected_x_limits, strict=True
            )
        ):
            raise RuntimeError("Origin K13 observation overlay changed category-axis limits")
        legend = self.layer.label("legend")
        if legend is not None:
            legend_text = str(legend.text)
            raw_line = f"\\l({group_count + 1}) {_RAW_OBSERVATION_LEGEND_LABEL}"
            expected_line = raw_line if action.visible else _BOX_OUTLIER_LEGEND
            forbidden = _BOX_OUTLIER_LEGEND if action.visible else raw_line
            if expected_line not in legend_text or forbidden in legend_text:
                raise RuntimeError("Origin K13 observation legend changed after reopen")
        for index, group in enumerate(distribution.groups):
            expected_x = regular_observation_positions(
                index + 1,
                len(group.values),
                action.jitter_fraction,
            )
            actual_x = tuple(
                float(value) for value in self.sheet.to_list(group_count + index)
            )
            if len(actual_x) != len(expected_x) or any(
                abs(observed - wanted) > 1e-12
                for observed, wanted in zip(actual_x, expected_x, strict=True)
            ):
                raise RuntimeError("Origin K13 deterministic observation positions changed")
            x_positions.append(list(actual_x))
            plot_index = group_count + index + 1
            plot_ref = f"__K13VERIFY{index + 1}"
            if not self.op.lt_exec(
                f"range {plot_ref}=[{graph_name}]1!{plot_index}; "
                f"get {plot_ref} -k __K13VK{index + 1}; "
                f"get {plot_ref} -z __K13VZ{index + 1}; "
                f"get {plot_ref} -kf __K13VF{index + 1}; "
                f"get {plot_ref} -csf __K13VCF{index + 1}; "
                f"get {plot_ref} -cse __K13VCE{index + 1};"
            ):
                raise RuntimeError("Origin K13 could not read observation point styles")
            state: dict[str, int | float] = {
                "visible": int(self.layer.get_int(f"plot{plot_index}.show")),
                "marker_shape": int(self.op.lt_float(f"__K13VK{index + 1}")),
                "marker_size_pt": float(self.op.lt_float(f"__K13VZ{index + 1}")),
                "marker_interior": int(self.op.lt_float(f"__K13VF{index + 1}")),
                "marker_fill_color": int(self.op.lt_float(f"__K13VCF{index + 1}")),
                "marker_stroke_color": int(self.op.lt_float(f"__K13VCE{index + 1}")),
                "marker_opacity": 1
                - float(self.op.lt_float(f"layer.plot{plot_index}.symbol.transparency"))
                / 100,
            }
            expected_state: dict[str, int | float] = {
                "visible": int(action.visible),
                "marker_shape": _SYMBOL_CODES[action.marker_shape],
                "marker_size_pt": action.marker_size_pt,
                "marker_interior": _INTERIOR_CODES[action.marker_interior],
                "marker_fill_color": expected_fill,
                "marker_stroke_color": expected_stroke,
                "marker_opacity": action.marker_opacity,
            }
            for key, wanted in expected_state.items():
                observed = state[key]
                if isinstance(wanted, float):
                    if abs(float(observed) - wanted) > 1e-9:
                        raise RuntimeError(
                            f"Origin K13 observation {key} changed after reopen"
                        )
                elif observed != wanted:
                    raise RuntimeError(
                        f"Origin K13 observation {key} changed after reopen"
                    )
            style_rows.append(state)
        return {
            "group_count": group_count,
            "point_count": sum(len(group.values) for group in distribution.groups),
            "jitter_fraction": action.jitter_fraction,
            "category_axis_limits": list(expected_x_limits),
            "legend_entry": (
                _RAW_OBSERVATION_LEGEND_LABEL if action.visible else "native_outliers"
            ),
            "x_positions": x_positions,
            "styles": style_rows,
            "same_source_rows": True,
        }

    def _assert_official_x05_structure(self, distribution: DistributionData) -> dict[str, object]:
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe Origin X05 graph name: {graph_name!r}")
        self.graph.activate()
        self.op.lt_exec("page.active=1; layer -c; __X05COUNT=count;")
        plot_count = int(self.op.lt_float("__X05COUNT"))
        plot_types: list[int] = []
        for index in range(1, plot_count + 1):
            self.op.lt_exec(f"range __X05P=[{graph_name}]1!{index}; get __X05P -pt __X05PT{index};")
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

    def _rebuild_native_data_legend(self) -> Any:
        self.layer.activate()
        self.op.lt_exec(
            "legendbox mode:=replace box:=0 range:=0 whisker:=0 mdl:=0 ml:=0 "
            "max:=0 perc99:=0 mean:=0 Median:=0 perc1:=0 min:=0 cp:=0 "
            "data:=1 id:=L outlier:=0 extreme:=0 cm:=0 cmd:=0 cd:=0 ccp:=0;"
        )
        legend = self.layer.label("legend")
        if legend is None:
            raise RuntimeError(
                f"Origin {self.profile_id} could not build its data-symbol-only legend"
            )
        return legend

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
