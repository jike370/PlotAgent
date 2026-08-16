from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.x23 as x23_module
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.backends.origin import X23_ORIGIN_PROFILE
from plotagent.engine.backends.origin.x23 import X23OriginProject
from plotagent.engine.visual_t1 import split_visual_actions

HASH = "5" * 64


class FakeLabel:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.name = ""
        self.values = {"show": 1}

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.values[name] = value


class FakeAxis:
    def __init__(self) -> None:
        self.scale = "linear"
        self.limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin=None, end=None, step=None) -> None:
        self.limits = (
            float(self.limits[0] if begin is None else begin),
            float(self.limits[1] if end is None else end),
            float(self.limits[2] if step is None else step),
        )


class FakePlot:
    def __init__(self, dataset_name: str = "Dorigin_dual_B") -> None:
        self.obj = self
        self.DatasetName = dataset_name
        self._color = (0, 0, 0)
        self.floats = {"line.width": 1.0}
        self.ints = {"line.style": 0}

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value) -> None:
        self._color = tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats[name]

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints[name]


class FakeLayer:
    def __init__(self, right: bool = False) -> None:
        self.obj = self
        self.labels = {
            "xb": FakeLabel("X"),
            "yl": FakeLabel("Y"),
            **({"yr": FakeLabel("Y2")} if right else {}),
        }
        self.axes = {"x": FakeAxis(), "y": FakeAxis()}
        self.plots: list[FakePlot] = []
        self.ints: dict[str, int] = {}
        self.strings: dict[str, str] = {}

    def add_plot(self, sheet, *, coly, colx, type):
        raise AssertionError("X23 must not manually add plots after the official menu section")

    def plot_list(self):
        return self.plots

    def rescale(self) -> None:
        return None

    def label(self, name: str):
        direct = self.labels.get(name)
        if direct is not None:
            return direct
        return next((label for label in self.labels.values() if label.name == name), None)

    def add_label(self, text: str, x=None, y=None):
        label = FakeLabel(text)
        self.labels[f"new-{len(self.labels)}"] = label
        return label

    def axis(self, name: str):
        return self.axes[name]

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_str(self, name: str, value: str) -> None:
        self.strings[name] = value

    def get_str(self, name: str) -> str:
        return self.strings[name]

    def activate(self) -> None:
        return None

    def LT_execute(self, command: str) -> bool:
        assert command == "legend"
        self.labels["legend"] = FakeLabel()
        return True


class FakeGraph:
    def __init__(self) -> None:
        self.name = "Gdual"
        self.layers = (FakeLayer(), FakeLayer(right=True))

    def __iter__(self):
        return iter(self.layers)


class FakeSheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}
        self.designation = ""

    def from_list(self, index, values, **kwargs) -> None:
        self.columns[index] = list(values)

    def to_list(self, index):
        return self.columns[index]

    def cols_axis(self, value: str) -> None:
        self.designation = value

    def get_int(self, expression: str) -> int:
        index = int(expression.removeprefix("col").removesuffix(".type")) - 1
        return (4, 1, 1)[index]

    def activate(self) -> None:
        return None

    def lt_exec(self, command: str) -> bool:
        return True


class FakeBook:
    def __init__(self) -> None:
        self.name = "Dorigin_dual"
        self.sheet = FakeSheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet

    def destroy(self) -> None:
        raise AssertionError("the authoritative X23 workbook must not be destroyed")


class FakeOrigin:
    def __init__(self) -> None:
        self.book = FakeBook()
        self.graph = FakeGraph()
        self.commands: list[str] = []
        self.active_layer = 1
        self.styles = {
            1: {"color": 0, "width": 500.0, "style": 0},
            2: {"color": 0, "width": 500.0, "style": 0},
        }
        self.plot_ids = {1: 202.0, 2: 202.0}
        self.links = {"target": 1.0, "x": 1.0, "y": 0.0}
        self.offsets = {
            1: {"SX": 0.0, "SXS": 1.0, "SY": 0.0, "SYS": 1.0},
            2: {"SX": 0.0, "SXS": 1.0, "SY": 0.0, "SYS": 1.0},
        }
        self.source_columns = {1: {"X": "A", "Y": "B"}, 2: {"X": "A", "Y": "C"}}

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, kind, name, *, hidden):
        assert kind == "w"
        return self.book

    def pages(self, kind: str):
        return [self.book] if kind == "w" else [self.graph]

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        active = re.search(r"page\.active=(\d+)", command)
        if active:
            self.active_layer = int(active.group(1))
        if "run.section(plot,2Ys_Y-Y)" in command:
            self.graph.layers[0].plots = [FakePlot(f"{self.book.name}_B")]
            self.graph.layers[1].plots = [FakePlot(f"{self.book.name}_C")]
        color = re.search(r'set %C -cl color\("(#[0-9A-Fa-f]{6})"\)', command)
        if color:
            self.styles[self.active_layer]["color"] = int(color.group(1)[1:], 16)
        width = re.search(r"set %C -wp ([0-9.]+)", command)
        if width:
            self.styles[self.active_layer]["width"] = float(width.group(1)) * 500.0
        style = re.search(r"set %C -d (\d+)", command)
        if style:
            self.styles[self.active_layer]["style"] = int(style.group(1))
        return True

    def lt_float(self, expression: str) -> float:
        color = re.fullmatch(r'color\("(#[0-9A-Fa-f]{6})"\)', expression)
        if color:
            return float(int(color.group(1)[1:], 16))
        if expression in {"__X23LINK", "__X23XLINK"}:
            return self.links["target" if expression == "__X23LINK" else "x"]
        if expression == "__X23YLINK":
            return self.links["y"]
        native = re.fullmatch(r"__X23([12])(PT|K|Z|SX|SXS|SY|SYS)", expression)
        if native:
            if native.group(2) == "PT":
                return self.plot_ids[int(native.group(1))]
            if native.group(2) in {"K", "Z"}:
                return {"K": 2.0, "Z": 5.0}[native.group(2)]
            return self.offsets[int(native.group(1))][native.group(2)]
        style = re.fullmatch(r"__X23STYLE([12])([CWD])", expression)
        if style:
            key = {"C": "color", "W": "width", "D": "style"}[style.group(2)]
            return float(self.styles[int(style.group(1))][key])
        return 0.0

    def get_lt_str(self, expression: str) -> str:
        source = re.fullmatch(r"__X23([12])([XY])S", expression)
        assert source is not None
        column = self.source_columns[int(source.group(1))][source.group(2)]
        return f'[{self.book.name}]Sheet1!{column}"'


def _case():
    data_ref = EngineDataRef(
        kind="source",
        dataset_id="dataset.dual",
        version=1,
        content_hash=HASH,
    )
    create = CreatePlot(
        action_id="action:create-dual",
        plot_id="plot:origin-dual",
        profile_id="X23",
        data=data_ref,
        bindings=(
            FieldBinding(role="x", field_id="field:country"),
            FieldBinding(role="left", field_id="field:population"),
            FieldBinding(role="right", field_id="field:gdp"),
        ),
    )
    view = EngineDataView(
        data=data_ref,
        row_ids=("row:1", "row:2", "row:3"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:country",
                    name="Country",
                    logical_type="categorical",
                ),
                values=("A", "B", "C"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:population",
                    name="Population",
                    logical_type="numeric",
                ),
                values=(12.0, 15.0, 19.0),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:gdp",
                    name="GDP per capita",
                    logical_type="numeric",
                ),
                values=(20_000.0, 23_500.0, 22_000.0),
            ),
        ),
    )
    actions = (
        create,
        SetTitle(
            action_id="action:title",
            target=create.plot_id,
            expected_plot_version=1,
            text="Native dual Y",
        ),
        SetAxis(
            action_id="action:right-axis",
            target="axis:origin-dual.y_right",
            expected_plot_version=2,
            label="GDP (USD)",
            minimum=15_000,
            maximum=30_000,
        ),
        SetSeriesStyle(
            action_id="action:left-style",
            target="series:origin-dual.left",
            expected_plot_version=3,
            line_stroke_color="#0F766E",
            line_width_pt=2.0,
        ),
        SetSeriesStyle(
            action_id="action:right-style",
            target="series:origin-dual.right",
            expected_plot_version=4,
            line_stroke_color="#BE123C",
            line_style="dash",
        ),
        SetLegend(
            action_id="action:legend",
            target="legend:origin-dual.main",
            expected_plot_version=5,
            visible=True,
        ),
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=6,
        parent_version=5,
        profile_id=create.profile_id,
        data=data_ref,
        bindings=create.bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    return document, actions, view


def test_x23_binder_uses_doubley_template_and_two_native_layers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, actions, view = _case()
    template = tmp_path / X23_ORIGIN_PROFILE.filename
    monkeypatch.setattr(x23_module, "resolve_official_template", lambda install, profile: template)
    op = FakeOrigin()
    project = X23OriginProject(op)
    project.create(tmp_path, document, view)
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    project.reconcile(document, split_visual_actions(actions)[0], view)
    readback = project.verify(document, split_visual_actions(actions)[0], view)

    assert readback.document.plot_version == 6
    assert any("run.section(plot,2Ys_Y-Y)" in command for command in op.commands)
    assert [len(layer.plots) for layer in op.graph.layers] == [1, 1]
    assert op.book.sheet.designation == "xyy"
    assert op.styles[1]["color"] == 0
    assert op.styles[2]["color"] == 0
    assert "\\l(1)" in op.graph.layers[0].labels["legend"].text
    assert "\\l(2.1)" in op.graph.layers[0].labels["legend"].text


def test_x23_origin_uses_official_line_symbol_section_without_manual_line_rebuild() -> None:
    source = inspect.getsource(x23_module)

    assert "run.section(plot,2Ys_Y-Y)" in source
    assert "_LINE_SYMBOL = 202" in source
    assert ".add_plot(" not in inspect.getsource(X23OriginProject)
    assert 'type="l"' not in inspect.getsource(X23OriginProject)
    assert "style:l" not in source


@pytest.mark.parametrize(
    ("plot_ids", "links", "message"),
    (
        ({1: 200.0, 2: 202.0}, {"target": 1.0, "x": 1.0, "y": 0.0}, "Line\\+Symbol PID 202"),
        ({1: 202.0, 2: 202.0}, {"target": 1.0, "x": 0.0, "y": 0.0}, "straight 1:1 X"),
        ({1: 202.0, 2: 202.0}, {"target": 1.0, "x": 1.0, "y": 1.0}, "independent Y"),
    ),
)
def test_x23_rejects_plain_line_or_invalid_layer_linkage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plot_ids: dict[int, float],
    links: dict[str, float],
    message: str,
) -> None:
    document, _actions, view = _case()
    template = tmp_path / X23_ORIGIN_PROFILE.filename
    monkeypatch.setattr(x23_module, "resolve_official_template", lambda install, profile: template)
    op = FakeOrigin()
    op.plot_ids = plot_ids
    op.links = links

    with pytest.raises(RuntimeError, match=message):
        X23OriginProject(op).create(tmp_path, document, view)


def test_x23_uses_only_stable_labtalk_structure_readback() -> None:
    source = inspect.getsource(X23OriginProject._assert_native_structure)

    assert "get %C -pt" in source and "get %C -k" in source and "get %C -z" in source
    assert "range -wx" in source and "range -wy" in source
    assert "layer.link" in source and "layer.x.link" in source and "layer.y.link" in source
    assert all(switch in source for switch in ("-sx", "-sxs", "-sy", "-sys"))
    assert "plot.obj.DatasetName" in source
    assert "OriginExt" not in source and "Theme" not in source


@pytest.mark.parametrize(
    ("mutator", "message"),
    (
        (lambda origin: origin.source_columns[2].update(X="D"), "lost shared X source A"),
        (lambda origin: origin.offsets[2].update(SXS=2.0), "non-native offset/scale"),
    ),
)
def test_x23_fresh_gate_rejects_source_or_offset_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutator,
    message: str,
) -> None:
    document, actions, view = _case()
    template = tmp_path / X23_ORIGIN_PROFILE.filename
    monkeypatch.setattr(x23_module, "resolve_official_template", lambda install, profile: template)
    op = FakeOrigin()
    project = X23OriginProject(op)
    project.create(tmp_path, document, view)
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    project.reconcile(document, split_visual_actions(actions)[0], view)
    mutator(op)

    with pytest.raises(RuntimeError, match=message):
        project.verify(document, split_visual_actions(actions)[0], view)


def test_x23_fresh_gate_rejects_unlinked_or_incomplete_legend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, actions, view = _case()
    template = tmp_path / X23_ORIGIN_PROFILE.filename
    monkeypatch.setattr(x23_module, "resolve_official_template", lambda install, profile: template)
    op = FakeOrigin()
    project = X23OriginProject(op)
    project.create(tmp_path, document, view)
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    project.reconcile(document, split_visual_actions(actions)[0], view)
    legend = op.graph.layers[0].labels["legend"]
    legend.set_int("link", 0)

    with pytest.raises(RuntimeError, match="legend visibility"):
        project.verify(document, split_visual_actions(actions)[0], view)


def test_x23_template_identity_is_pinned_to_doubley_otp() -> None:
    assert X23_ORIGIN_PROFILE.filename == "DOUBLEY.OTP"
    assert X23_ORIGIN_PROFILE.sha256 == (
        "487547eb206e4645f3380a9a021ceb7fbcf4ec4d1fdb0a870d1eb0cde0c7641b"
    )


def test_x23_origin_binder_has_no_legacy_plan_or_renderer_import() -> None:
    source = inspect.getsource(__import__(X23OriginProject.__module__, fromlist=["*"]))
    assert "plotagent.origin" not in source
    assert "OriginPlan" not in source
    assert "ResolvedPlot" not in source
