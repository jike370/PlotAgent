from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import numpy as np
import pytest

import plotagent.engine.backends.origin.k24 as k24_origin
import plotagent.engine.backends.origin.s34 as s34_origin
import plotagent.engine.backends.origin.s61 as s61_origin
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
)
from plotagent.engine.backends.matplotlib import (
    K24FacetRenderer,
    MatplotlibBackend,
    S34NyquistRenderer,
    S61ConfusionRenderer,
)
from plotagent.engine.backends.origin import (
    K24_ORIGIN_PROFILE,
    S34_ORIGIN_PROFILE,
    S61_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.k24 import K24OriginProject
from plotagent.engine.backends.origin.s34 import S34OriginProject
from plotagent.engine.backends.origin.s61 import S61OriginProject
from plotagent.engine.backends.origin.trace import OriginExecutionTrace
from plotagent.engine.profile_data import (
    k24_facets,
    s34_nyquist,
    s61_confusion_grid,
)
from plotagent.engine.profiles import (
    K24_FACET_PROFILE,
    S34_NYQUIST_PROFILE,
    S61_CONFUSION_PROFILE,
)

HASH = "9" * 64


def _case(profile_id: str, columns: tuple[tuple[str, str, str, str, tuple[object, ...]], ...]):
    data = EngineDataRef(
        kind="source", dataset_id=f"dataset.{profile_id.lower()}", version=1, content_hash=HASH
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=field_id)
        for role, field_id, _name, _logical_type, _values in columns
    )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-t2",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=(create.action_id,),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(len(columns[0][4]))),
        columns=tuple(
            EngineColumn(
                field=EngineField(
                    field_id=field_id,
                    name=name,
                    logical_type=logical_type,  # type: ignore[arg-type]
                ),
                values=values,
            )
            for _role, field_id, name, logical_type, values in columns
        ),
    )
    return document, (create,), view


def _k24_case(panel_count: int = 3):
    labels = tuple(f"Panel {index + 1}" for index in range(panel_count) for _point in range(4))
    x = tuple(float(point) for _panel in range(panel_count) for point in range(4))
    y = tuple(float(panel * 10 + point) for panel in range(panel_count) for point in range(4))
    return _case(
        "K24",
        (
            ("facet", "field:facet", "Condition", "categorical", labels),
            ("base_x", "field:x", "Time", "numeric", x),
            ("base_y", "field:y", "Signal", "numeric", y),
        ),
    )


def _s34_case(series_count: int = 3):
    labels = tuple(f"Cell {index + 1}" for index in range(series_count) for _point in range(5))
    real = tuple(float(point + series) for series in range(series_count) for point in range(5))
    imaginary = tuple(
        float((point + 1) * (5 - point) + series)
        for series in range(series_count)
        for point in range(5)
    )
    frequency = tuple(
        float(10000 / (point + 1)) for _series in range(series_count) for point in range(5)
    )
    return _case(
        "S34",
        (
            ("z_real", "field:real", "Z real", "numeric", real),
            ("z_imaginary", "field:imag", "-Z imaginary", "numeric", imaginary),
            ("frequency", "field:frequency", "Frequency", "numeric", frequency),
            ("series", "field:series", "Cell", "categorical", labels),
        ),
    )


def _s61_case(*, aggregated: bool = True):
    actual = ("Cat", "Cat", "Dog", "Dog", "Bird", "Bird")
    predicted = ("Cat", "Dog", "Cat", "Dog", "Cat", "Bird")
    columns: list[tuple[str, str, str, str, tuple[object, ...]]] = [
        ("actual", "field:actual", "Actual", "categorical", actual),
        ("predicted", "field:predicted", "Predicted", "categorical", predicted),
    ]
    if aggregated:
        columns.append(("count", "field:count", "Count", "numeric", (42, 4, 5, 38, 5, 34)))
    return _case("S61", tuple(columns))


@pytest.mark.parametrize("panel_count", (2, 3, 5))
def test_k24_materializes_dynamic_facets(panel_count: int) -> None:
    document, _actions, view = _k24_case(panel_count)
    facets = k24_facets(document, view)
    assert len(facets.panels) == panel_count
    assert all(len(panel.x_values) == 4 for panel in facets.panels)


@pytest.mark.parametrize("series_count", (1, 4, 5))
def test_s34_preserves_frequency_as_metadata_for_dynamic_series(series_count: int) -> None:
    document, _actions, view = _s34_case(series_count)
    nyquist = s34_nyquist(document, view)
    assert len(nyquist.series) == series_count
    assert nyquist.series[-1].frequency is not None


def test_s61_accepts_raw_samples_and_preaggregated_integer_counts() -> None:
    raw_document, _actions, raw_view = _s61_case(aggregated=False)
    raw = s61_confusion_grid(raw_document, raw_view)
    assert sum(sum(row) for row in raw.values) == 6
    document, _actions, view = _s61_case(aggregated=True)
    aggregated = s61_confusion_grid(document, view)
    assert aggregated.values[0] == (42.0, 4.0, 0.0)
    assert sum(sum(row) for row in aggregated.values) == 128


@pytest.mark.parametrize(
    ("renderer", "case", "object_kind"),
    (
        (K24FacetRenderer(), _k24_case, "facet_series"),
        (S34NyquistRenderer(), _s34_case, "nyquist_series"),
        (S61ConfusionRenderer(), _s61_case, "confusion_matrix"),
    ),
)
def test_t2_matplotlib_renderers_are_independent_and_semantic(
    tmp_path: Path, renderer, case, object_kind: str
) -> None:
    document, actions, view = case()
    backend = MatplotlibBackend(tmp_path / renderer.profile_id, (renderer,))
    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()
    assert any(item.object_kind == object_kind for item in change.readback.objects)
    target = tmp_path / renderer.profile_id / document.plot_id.removeprefix("plot:") / "v1"
    assert (target / "preview.png").stat().st_size > 1_000
    assert (target / "preview.svg").stat().st_size > 1_000


class _Label:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.name = ""
        self.ints = {"show": 1}
        self.floats: dict[str, float] = {}

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value


class _Axis:
    def __init__(self) -> None:
        self.limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin=None, end=None, step=None) -> None:
        self.limits = (
            float(self.limits[0] if begin is None else begin),
            float(self.limits[1] if end is None else end),
            float(self.limits[2] if step is None else step),
        )


class _Plot:
    def __init__(self, plot_type: object) -> None:
        self.plot_type = plot_type
        self.ints = {"show": 1, "label.show": 1}
        self.floats: dict[str, float] = {}
        self.color: object = "#000000"
        self.symbol_kind = 1
        self.symbol_size = 6.0
        self.transparency = 0
        self.commands: list[str] = []

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats.get(name, 0.0)

    def set_fill_area(self, **kwargs) -> None:
        self.fill = kwargs

    def set_cmd(self, *commands: str) -> None:
        self.commands.extend(commands)


class _Layer:
    def __init__(self) -> None:
        self.obj = self
        self.plots: list[_Plot] = []
        self.labels = {"xb": _Label("X"), "yl": _Label("Y")}
        self.axes = {"x": _Axis(), "y": _Axis()}
        self.ints: dict[str, int] = {}
        self.strings: dict[str, str] = {}
        self.layout = ""
        self.floats = {"width": 60.0, "height": 60.0}
        self.activated = False

    @property
    def xlim(self):
        return self.axes["x"].limits

    @property
    def ylim(self):
        return self.axes["y"].limits

    def add_plot(self, sheet, *, coly, colx, type):
        plot = _Plot(type)
        self.plots.append(plot)
        return plot

    def add_mplot(self, sheet, index, *, type):
        plot = _Plot(type)
        self.plots.append(plot)
        return plot

    def plot_list(self):
        return self.plots

    def axis(self, name: str):
        return self.axes[name]

    def label(self, name: str):
        return self.labels.get(name) or next(
            (label for label in self.labels.values() if label.name == name), None
        )

    def add_label(self, text: str, x=None, y=None):
        label = _Label(text)
        self.labels[f"new-{len(self.labels)}"] = label
        return label

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats[name]

    def set_str(self, name: str, value: str) -> None:
        self.strings[name] = value

    def rescale(self) -> None:
        return None

    def lt_exec(self, command: str) -> None:
        self.layout += command

    def activate(self) -> None:
        self.activated = True

    def LT_execute(self, command: str) -> bool:
        self.labels["legend"] = _Label()
        return True


class _Graph:
    def __init__(self, layers: int) -> None:
        self.name = "GT2"
        self.lname = ""
        self.layers = [_Layer() for _index in range(layers)]
        self.floats = {"width": 1000.0, "height": 1000.0}

    def __iter__(self):
        return iter(self.layers)

    def __getitem__(self, index: int):
        return self.layers[index]

    def add_layer(self, _kind: int) -> None:
        self.layers.append(_Layer())

    def activate(self) -> None:
        return None

    def get_float(self, name: str) -> float:
        return self.floats[name]


class _Sheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}
        self.column_options: dict[int, dict[str, object]] = {}
        self.cols = 0
        self.matrix = np.empty((0, 0))
        self.xymap = (0.0, 1.0, 0.0, 1.0)

    def from_list(self, index, values, **kwargs) -> None:
        self.columns[index] = list(values)
        self.column_options[index] = dict(kwargs)

    def to_list(self, index):
        return self.columns[index]

    def get_int(self, name: str) -> int:
        if name.startswith("col") and name.endswith(".type"):
            index = int(name.removeprefix("col").removesuffix(".type")) - 1
            return {"X": 4, "Y": 1, "N": 2}[str(self.column_options[index]["axis"])]
        raise KeyError(name)

    def from_np(self, values) -> None:
        self.matrix = np.asarray(values)

    def to_np2d(self):
        return self.matrix

    def activate(self) -> None:
        return None

    def lt_range(self, _include_sheet: bool) -> str:
        return "[DK24]Sheet1"


class _Book:
    def __init__(self) -> None:
        self.name = "DK24"
        self.sheet = _Sheet()

    def __getitem__(self, index: int):
        return self.sheet

    def destroy(self) -> None:
        return None


class _Origin:
    def __init__(self) -> None:
        self.book = _Book()
        self.graph = _Graph(1)
        self.commands: list[str] = []
        self.native_plot_id = 202.0

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, kind, name, *, hidden):
        self.book = _Book()
        self.book.name = name
        return self.book

    def new_graph(self, name, *, template, hidden):
        layers = 2 if "survival" in template.lower() else 1
        self.graph = _Graph(layers)
        self.graph.name = name
        if "survival" in template.lower():
            self.graph.layers[0].labels["Title"] = _Label("template title")
        return self.graph

    def pages(self, kind: str):
        return [self.book] if kind == "w" else [self.graph]

    def lt_exec(self, command: str) -> None:
        self.commands.append(command)
        if command.startswith("plot_group "):
            self.graph = _Graph(1)
        if "worksheet -p 202 LINESYMB" in command:
            match = re.search(r"worksheet -s 1 0 (\d+) 0", command)
            assert match is not None
            self.graph = _Graph(1)
            self.graph.layers[0].plots = [
                _Plot(202) for _index in range(int(match.group(1)) // 2)
            ]

    def lt_float(self, expression: str) -> float:
        if expression.startswith('color("'):
            return 2.0
        if expression.startswith("__S34PID"):
            return 202.0
        if expression in {"layer.plot1.pid", "__K24PID"}:
            return self.native_plot_id
        if expression == "__K24COUNT":
            return 1.0
        return float("nan")

    def get_lt_str(self, expression: str) -> str:
        if expression.startswith("__S34XS"):
            ordinal = int(expression.removeprefix("__S34XS"))
            letter = chr(65 + (ordinal - 1) * 2)
            return f"[DS34]Sheet1!{letter}"
        if expression.startswith("__S34YS"):
            ordinal = int(expression.removeprefix("__S34YS"))
            letter = chr(66 + (ordinal - 1) * 2)
            return f"[DS34]Sheet1!{letter}"
        if expression == "__K24XS":
            return '[DK24]Sheet1!A"Time"'
        if expression == "__K24YS":
            return '[DK24]Sheet1!B"Signal"'
        return ""


@pytest.mark.parametrize("panel_count", (2, 3, 5))
def test_origin_k24_uses_one_native_trellis_layer(
    monkeypatch, tmp_path: Path, panel_count: int
) -> None:
    monkeypatch.setattr(
        k24_origin, "resolve_official_template", lambda *_: Path("Grouped.otp")
    )
    document, actions, view = _k24_case(panel_count)
    origin = _Origin()
    project = K24OriginProject(origin)
    trace = OriginExecutionTrace(
        path=tmp_path / "execution-trace.jsonl",
        profile_id="K24",
        plot_id=document.plot_id,
        plot_version=1,
    )
    trace.reset()
    with trace.activate():
        project.create(Path("."), document, view)
        project.reconcile(document, actions, view)
    assert K24FacetRenderer.__module__.endswith(".facet")
    assert K24OriginProject.__module__.endswith(".k24")
    assert len(tuple(project.graph)) == 1
    assert int(origin.lt_float("layer.plot1.pid")) == 202
    assert any(
        "plot_group " in command
        and "type:=linesymb" in command
        and "horz:=[DK24]Sheet1!(C)" in command
        and "color:=[DK24]Sheet1!(C)" in command
        and "template:=Grouped" in command
        for command in origin.commands
    )
    assert project.sheet.cols == 3
    assert project.sheet.column_options[0]["axis"] == "X"
    assert project.sheet.column_options[1]["axis"] == "Y"
    assert project.sheet.column_options[2]["axis"] == "N"
    assert len(set(project.sheet.columns[2])) == panel_count
    assert project.last_native_structure == {
        "official_route": "plot_group",
        "official_template": "Grouped.otp",
        "ordinary_primitive_fallback_used": False,
        "layer_count": 1,
        "plot_count": 1,
        "native_plot_type": 202,
        "x_source": '[DK24]Sheet1!A"Time"',
        "y_source": '[DK24]Sheet1!B"Signal"',
        "source_designations": [4, 1, 2],
        "facet_column_storage": "text N grouping column",
        "facet_count": panel_count,
        "facet_labels": [f"Panel {index + 1}" for index in range(panel_count)],
    }
    trace_rows = [
        json.loads(line)
        for line in trace.path.read_text(encoding="utf-8").splitlines()
    ]
    completed = {
        row["step"] for row in trace_rows if row["status"] == "completed"
    }
    assert {
        "official_template_resolve",
        "origin_project_initialize",
        "workbook_create",
        "source_data_write",
        "official_plot_group_execute",
        "native_structure_readback",
        "native_structure_confirmed",
        "agent_actions_apply",
    } <= completed
    assert [row["sequence"] for row in trace_rows] == list(
        range(1, len(trace_rows) + 1)
    )


def test_k24_agent_surface_matches_native_trellis_editability() -> None:
    capabilities = {
        capability.operation: capability.parameters
        for capability in K24_FACET_PROFILE.capabilities
    }
    assert set(capabilities) == {
        "create_plot",
        "bind_fields",
        "set_title",
        "set_axis",
        "set_series_style",
        "export_plot",
    }
    assert {"text", "font_family", "font_size_pt", "font_weight", "italic", "color"} == set(
        capabilities["set_title"]
    )
    assert {
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
        "visible",
    } == set(capabilities["set_series_style"])
    assert "color" not in capabilities["set_series_style"]


def test_origin_s34_uses_native_dynamic_plots(monkeypatch) -> None:
    monkeypatch.setattr(
        s34_origin, "resolve_official_template", lambda *_: Path("LINESYMB.otpu")
    )
    document, actions, view = _s34_case(4)
    nyquist = S34OriginProject(_Origin())
    nyquist.create(Path("."), document, view)
    nyquist.reconcile(document, actions, view)
    assert S34OriginProject.__module__.endswith(".s34")
    assert S34NyquistRenderer.__module__.endswith(".nyquist")
    assert len(nyquist.plots) == 4
    assert all(plot.plot_type == 202 for plot in nyquist.plots)
    assert any(
        command == "worksheet -s 1 0 8 0; worksheet -p 202 LINESYMB;"
        for command in nyquist.op.commands
    )
    assert nyquist.last_native_structure is not None
    assert nyquist.last_native_structure["official_template"] == "LINESYMB.otpu"
    assert nyquist.last_native_structure["official_plot_type"] == 202
    assert nyquist.last_native_structure["ordinary_primitive_fallback_used"] is False
    assert nyquist.last_native_structure["source_designations"] == [
        4,
        1,
        4,
        1,
        4,
        1,
        4,
        1,
        2,
        2,
        2,
        2,
    ]
    assert nyquist.last_native_structure["frequency_columns_plotted"] is False


def test_origin_s34_keeps_equal_scale_for_wide_editable_data(monkeypatch) -> None:
    """A legitimate wide Nyquist range must not make OPJU materialization fail.

    Project 126 exposed a 0..85 by 0..14 range.  Origin's documented unit-
    aspect workflow permits a shallow native layer; the renderer must preserve
    equal physical units instead of rejecting the project at an arbitrary
    percentage threshold.
    """

    monkeypatch.setattr(
        s34_origin, "resolve_official_template", lambda *_: Path("LINESYMB.otpu")
    )
    document, actions, view = _s34_case(1)
    project = S34OriginProject(_Origin())
    project.create(Path("."), document, view)
    project.graph.floats.update(width=6432.0, height=4923.0)
    project.layer.axes["x"].limits = (0.0, 85.0, 5.0)
    project.layer.axes["y"].limits = (0.0, 14.0, 2.0)

    project.reconcile(document, actions, view)

    snapshot = project._equal_scale_snapshot()
    assert snapshot["relative_error"] < 0.02
    assert project.layer.get_float("width") == pytest.approx(68.0)
    assert project.layer.get_float("height") == pytest.approx(14.63, abs=0.01)


def test_origin_s34_reflows_equal_scale_after_shared_axis_edits(monkeypatch) -> None:
    """Public SetAxis limits must not leave the pre-edit Nyquist layout behind."""

    monkeypatch.setattr(
        s34_origin, "resolve_official_template", lambda *_: Path("LINESYMB.otpu")
    )
    document, actions, view = _s34_case(1)
    project = S34OriginProject(_Origin())
    project.create(Path("."), document, view)
    project.graph.floats.update(width=6432.0, height=4923.0)
    project.layer.axes["x"].limits = (0.0, 85.0, 5.0)
    project.layer.axes["y"].limits = (0.0, 14.0, 2.0)
    project.reconcile(document, actions, view)
    assert project.layer.get_float("height") == pytest.approx(14.63, abs=0.01)

    project.layer.axes["x"].limits = (0.0, 40.0, 5.0)
    project.layer.axes["y"].limits = (0.0, 40.0, 5.0)
    snapshot = s34_origin.apply_s34_equal_scale_layout(project.graph)

    assert snapshot["relative_error"] < 0.02
    assert project.layer.get_float("width") == pytest.approx(52.05, abs=0.01)
    assert project.layer.get_float("height") == pytest.approx(68.0)


def test_origin_s61_writes_one_native_labeled_matrix(monkeypatch) -> None:
    monkeypatch.setattr(
        s61_origin, "resolve_official_template", lambda *_: Path("Heat_Map_With_Labels.otpu")
    )
    monkeypatch.setattr(
        S61OriginProject,
        "_configure_labels",
        lambda self, show: self.plot.set_int("label.show", int(show)),
    )
    monkeypatch.setattr(S61OriginProject, "_configure_color_scale", lambda *_: None)
    monkeypatch.setattr(
        S61OriginProject,
        "_native_structure",
        lambda *_: {
            "official_template": "Heat_Map_With_Labels.otpu",
            "native_plot_type": 105,
            "ordinary_primitive_fallback_used": False,
        },
    )
    document, actions, view = _s61_case()
    project = S61OriginProject(_Origin())
    project.create(Path("."), document, view)
    project.reconcile(document, actions, view)
    assert S61OriginProject.__module__.endswith(".s61")
    assert S61ConfusionRenderer.__module__.endswith(".confusion_matrix")
    assert project.plot.plot_type == 105
    assert project.sheet.matrix.tolist()[0] == [42.0, 4.0, 0.0]
    assert project.last_native_structure == {
        "official_template": "Heat_Map_With_Labels.otpu",
        "native_plot_type": 105,
        "ordinary_primitive_fallback_used": False,
    }


def test_t2_profiles_pin_templates_and_do_not_import_old_compiler() -> None:
    assert {
        profile.profile_id: profile.sha256
        for profile in (
            K24_ORIGIN_PROFILE,
            S34_ORIGIN_PROFILE,
            S61_ORIGIN_PROFILE,
        )
    } == {
        "K24": "b3a1999cc9e95e55d661863e60efbcc792af415bc83b0962f01f1636d35c7af0",
        "S34": "2f1292a939eac92cd0dc820309885caccfa53293d1db78d18447a5b5b329fed1",
        "S61": "d1a7fcd8af232aef9ca348eb178466a13a744eb700da7d49d39cfbe16c935c7d",
    }
    assert {
        profile.profile_id
        for profile in (
            K24_FACET_PROFILE,
            S34_NYQUIST_PROFILE,
            S61_CONFUSION_PROFILE,
        )
    } == {"K24", "S34", "S61"}
    source = "\n".join(
        inspect.getsource(module)
        for module in (s34_origin, s61_origin)
    )
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
