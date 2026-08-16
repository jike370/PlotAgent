"""Official-template binder for the native K15 histogram."""

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
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import (
    DistributionData,
    HistogramData,
    distribution_groups,
    k15_histogram,
)
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .native_distribution import (
    DATA_HEIGHT_TYPE,
    configure_native_distribution,
    read_native_distribution_value,
)
from .profile import (
    K15_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)

_TITLE_NAME = "_ENGINE_TITLE"
_HISTOGRAM_PID = 219
_HISTOGRAM_DATA_HEIGHT_COUNT = 0


def _effective_actions(actions: tuple[PlotEngineAction, ...]) -> tuple[PlotEngineAction, ...]:
    return actions


class CalculatedDistributionOriginProject:
    def __init__(self, op: Any) -> None:
        self.op = op
        self.profile_id = "K15"
        self.profile: OriginTemplateProfile = K15_ORIGIN_PROFILE
        self.graph: Any = None
        self.layer: Any = None
        self.sheet: Any = None
        self.plots: list[Any] = []

    def create(self, install_dir: Path, document: PlotDocument, data: EngineDataView) -> None:
        resolve_official_template(install_dir, self.profile)
        self.op.new(asksave=False)
        token = document.plot_id.removeprefix("plot:").replace("-", "_")
        book = self.op.new_book("w", f"D{token}", hidden=True)
        if book is None:
            raise RuntimeError(f"Origin could not create the {self.profile_id} workbook")
        for residue in tuple(self.op.pages("w")):
            if residue.name == "Book1" and residue.name != book.name:
                residue.destroy()
        self.sheet = book[0]
        distribution = distribution_groups(document, data, profile_id="K15")
        if len(distribution.groups) != 1:
            raise ValueError("K15 accepts one raw observation series")
        self._write_histogram_source(distribution)
        self.sheet.activate()
        self.sheet.lt_exec("worksheet -s 1 0 1 0; worksheet -p 219 Hist;")
        graphs = list(self.op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError("Origin Hist command must create exactly one graph")
        self.graph = graphs[0]
        self.graph.lname = f"K15 Histogram / {document.plot_id}"
        self.layer = self.graph[0]
        self._hide_blank_opposite_axis_titles()
        self.plots = [plot for plot in self.layer.plot_list() if plot.get_int("show") != 0]
        if len(self.plots) != 1:
            raise RuntimeError("Origin Hist command must create one native histogram plot")
        self._configure_native_histogram(k15_histogram(document, data))
        self._assert_native_histogram(k15_histogram(document, data))
        self.layer.rescale()

    def _hide_blank_opposite_axis_titles(self) -> None:
        """Hide whitespace-only top/right titles shipped by Hist.otpu.

        Origin renders those blank title objects as detached black dashes in
        exported PNGs. They carry no data or axis semantics; bottom/left
        titles remain linked to the native histogram source.
        """

        for name in ("XT", "YR"):
            label = self.layer.label(name)
            if label is not None and not str(label.text).strip():
                label.set_int("show", 0)

    def reopen(
        self,
        project_path: Path,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError(
                f"fresh Origin session could not reopen the staged {self.profile_id} project"
            )
        graphs = list(self.op.pages("g"))
        books = list(self.op.pages("w"))
        if len(graphs) != 1 or not books:
            raise RuntimeError(f"fresh {self.profile_id} project has unexpected page count")
        self.graph = graphs[0]
        self.layer = self.graph[0]
        self.plots = [plot for plot in self.layer.plot_list() if plot.get_int("show") != 0]
        distribution = distribution_groups(document, data, profile_id="K15")
        expected = distribution.groups[0].values
        candidates = [
            book[0]
            for book in books
            if len(book)
            and int(book[0].cols) == 1
            and self._values_match(book[0].to_list(0), expected)
        ]
        if len(candidates) != 1:
            raise RuntimeError(
                "fresh K15 project cannot uniquely locate the raw observation worksheet"
            )
        self.sheet = candidates[0]

    def apply(self, document: PlotDocument, action: PlotEngineAction, data: EngineDataView) -> None:
        document.plot_id.removeprefix("plot:")
        if isinstance(action, (CreatePlot, BindFields)):
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
        distribution = distribution_groups(document, data, profile_id="K15")
        if len(distribution.groups) != 1:
            raise ValueError("K15 accepts one raw observation series")
        if len(self.plots) != 1:
            raise RuntimeError("Origin K15 must contain one visible native histogram series")
        if int(self.sheet.cols) != 1:
            raise RuntimeError("Origin K15 source workbook must retain exactly one raw column")
        self._assert_values(
            self.sheet.to_list(0),
            distribution.groups[0].values,
            "raw observations",
        )
        histogram = k15_histogram(document, data)
        native_histogram = self._assert_native_histogram(histogram)
        token = document.plot_id.removeprefix("plot:")
        snapshot: dict[str, object] = {"profile": self.profile_id, "series": len(self.plots)}
        snapshot["native_histogram"] = native_histogram
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
                    semantic_id=f"series:{token}.primary",
                    backend="origin",
                    object_kind="histogram_series",
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

    def _write_histogram_source(self, distribution: DistributionData) -> None:
        self.sheet.cols = 1
        self.sheet.from_list(
            0,
            list(distribution.groups[0].values),
            lname=distribution.value_field_name,
            axis="Y",
        )

    def _configure_native_histogram(self, histogram: HistogramData) -> None:
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe Origin K15 graph name: {graph_name!r}")
        if len(histogram.left) == 0 or len(histogram.right) != len(histogram.left):
            raise RuntimeError("K15 frozen histogram has invalid bin geometry")
        begin = float(histogram.left[0])
        end = float(histogram.right[-1])
        size = float(histogram.right[0] - histogram.left[0])
        if size <= 0:
            raise RuntimeError("K15 frozen histogram bin size must be positive")
        self.graph.activate()
        command = (
            f"range __K15P=[{graph_name}]1!1; "
            f"set __K15P -hbb {begin:.17g}; "
            f"set __K15P -hbe {end:.17g}; "
            f"set __K15P -hbs {size:.17g};"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not write the frozen K15 native histogram bins")
        configure_native_distribution(
            self.op,
            graph_name,
            1,
            15,
        )

    def _assert_native_histogram(self, histogram: HistogramData) -> dict[str, object]:
        graph_name = str(self.graph.name)
        if not graph_name.replace("_", "").isalnum():
            raise RuntimeError(f"unsafe Origin K15 graph name: {graph_name!r}")
        self.graph.activate()
        command = (
            f"range __K15P=[{graph_name}]1!1; "
            "get __K15P -pt __K15PID; "
            "get __K15P -hbb __K15BEGIN; "
            "get __K15P -hbe __K15END; "
            "get __K15P -hbs __K15SIZE;"
        )
        if not self.op.lt_exec(command):
            raise RuntimeError("Origin could not read the K15 native histogram properties")
        plot_type = int(self.op.lt_float("__K15PID"))
        begin = float(self.op.lt_float("__K15BEGIN"))
        end = float(self.op.lt_float("__K15END"))
        size = float(self.op.lt_float("__K15SIZE"))
        expected_begin = float(histogram.left[0])
        expected_end = float(histogram.right[-1])
        expected_size = float(histogram.right[0] - histogram.left[0])
        if plot_type != _HISTOGRAM_PID:
            raise RuntimeError("Origin K15 did not retain the native PID 219 Histogram")
        for label, actual, expected in (
            ("begin", begin, expected_begin),
            ("end", end, expected_end),
            ("size", size, expected_size),
        ):
            tolerance = max(1e-12, abs(expected) * 1e-12)
            if abs(actual - expected) > tolerance:
                raise RuntimeError(
                    f"Origin K15 frozen histogram {label} differs after native readback"
                )
        data_height = int(
            read_native_distribution_value(
                self.op,
                graph_name,
                1,
                DATA_HEIGHT_TYPE,
                numeric_type="int",
            )
        )
        if data_height != _HISTOGRAM_DATA_HEIGHT_COUNT:
            raise RuntimeError("Origin K15 Data Height must read back as Count")
        return {
            "plot_type": plot_type,
            "bin_begin": begin,
            "bin_end": end,
            "bin_size": size,
            "bin_count": len(histogram.count),
            "data_height": "Count",
            "rule": histogram.rule,
        }

    @staticmethod
    def _assert_values(actual: list[object], expected: tuple[object, ...], name: str) -> None:
        if len(actual) != len(expected):
            raise RuntimeError(f"Origin {name} row count differs after reopen")
        for observed, wanted in zip(actual, expected, strict=True):
            if abs(float(cast(Any, observed)) - float(cast(Any, wanted))) > 1e-9:
                raise RuntimeError(f"Origin {name} values differ after reopen")

    @staticmethod
    def _values_match(actual: list[object], expected: tuple[float, ...]) -> bool:
        if len(actual) != len(expected):
            return False
        try:
            return all(
                abs(float(cast(Any, observed)) - wanted) <= 1e-9
                for observed, wanted in zip(actual, expected, strict=True)
            )
        except (TypeError, ValueError):
            return False


def _execute(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    project = CalculatedDistributionOriginProject(op)
    project.create(install_dir, request.document, request.data)
    actions = _effective_actions(request.actions)
    for action in actions:
        project.apply(request.document, action, request.data)
    project.save(output)
    reopened = CalculatedDistributionOriginProject(op)
    reopened.reopen(output, request.document, request.data)
    return reopened.verify(request.document, actions, request.data)


def execute_k15_request(
    op: Any, request: OriginWorkerRequest, install_dir: Path, output: Path
) -> EngineReadback:
    return _execute(op, request, install_dir, output)
