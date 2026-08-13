from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.k02 as k02_module
import plotagent.engine.backends.origin.k03 as k03_module
import plotagent.engine.backends.origin.k06 as k06_module
import plotagent.engine.backends.origin.k07 as k07_module
import plotagent.engine.backends.origin.k18 as k18_module
import plotagent.engine.backends.origin.x02 as x02_module
import plotagent.engine.backends.origin.xy as xy_module
from plotagent.engine import (
    BindFields,
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    PlotEngineAction,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.backends.origin import (
    K02_ORIGIN_PROFILE,
    K03_ORIGIN_PROFILE,
    K06_ORIGIN_PROFILE,
    K07_ORIGIN_PROFILE,
    K18_ORIGIN_PROFILE,
    X02_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.k02 import K02OriginProject
from plotagent.engine.backends.origin.k03 import K03OriginProject
from plotagent.engine.backends.origin.k03 import _effective_actions as k03_effective_actions
from plotagent.engine.backends.origin.k06 import K06OriginProject
from plotagent.engine.backends.origin.k07 import K07OriginProject
from plotagent.engine.backends.origin.x02 import X02OriginProject

HASH = "4" * 64


class FakeLabel:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.name = ""
        self.values = {"show": 1}
        self.floats: dict[str, float] = {}

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats.get(name, 0.0)


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


class FakeThemeNode:
    def __init__(self, name: str, value: int = 0, children=()) -> None:
        self.Name = name
        self.value = value
        self.Children = list(children)

    def GetValue(self):
        return self.value

    def SetIntValue(self, value: int) -> None:
        self.value = value


class FakePlot:
    def __init__(self) -> None:
        self.obj = self
        self.DatasetName = "Book1_B"
        self._color = (22, 118, 210)
        self.floats = {"line.width": 1.5}
        self.ints = {"line.style": 0}
        self.symbol_kind = 2
        self.symbol_size = 5.0
        self.theme = FakeThemeNode(
            "Root",
            children=(
                FakeThemeNode(
                    "ErrorBar2D",
                    children=tuple(
                        FakeThemeNode(name)
                        for name in (
                            "DirectionX",
                            "DirectionPlus",
                            "DirectionMinus",
                            "ConnectLineMode",
                            "ConnectLineFillArea",
                        )
                    ),
                ),
            ),
        )

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value) -> None:
        if isinstance(value, str):
            self._color = tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
        else:
            self._color = tuple(value)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats[name]

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints[name]

    def GetTheme(self):
        return self.theme

    def PutTheme(self, theme) -> None:
        self.theme = theme


class FakeLayer:
    def __init__(self) -> None:
        self.obj = self
        self.labels = {"xb": FakeLabel("X"), "yl": FakeLabel("Y")}
        self.axes = {"x": FakeAxis(), "y": FakeAxis()}
        self.plots: list[FakePlot] = []
        self.add_calls: list[dict[str, object]] = []
        self.group_calls: list[tuple[object, ...]] = []

    def add_plot(self, sheet, **kwargs):
        self.add_calls.append(kwargs)
        plot = FakePlot()
        self.plots.append(plot)
        return plot

    def plot_list(self):
        return self.plots

    def rescale(self) -> None:
        return None

    def group(self, *args) -> None:
        self.group_calls.append(args)

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

    def activate(self) -> None:
        return None

    def LT_execute(self, command: str) -> bool:
        if command == "legend":
            self.labels["legend"] = FakeLabel()
            return True
        match = re.fullmatch(r"label -j 1 -n (\S+) PlotAgentTitlePlaceholder;", command)
        if match is not None:
            title = FakeLabel("PlotAgentTitlePlaceholder")
            title.name = match.group(1)
            self.labels[match.group(1)] = title
            return True
        raise AssertionError(f"unexpected LabTalk label command: {command}")

    def __iter__(self):
        yield self


class FakeGraph:
    def __init__(self, name: str) -> None:
        self.name = name
        self.lname = name
        self.layer = FakeLayer()

    def __getitem__(self, index: int):
        assert index == 0
        return self.layer

    def __iter__(self):
        yield self.layer

    def activate(self) -> None:
        return None


class FakeSheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}
        self.designations: dict[int, str] = {}
        self.cols = 0

    def from_list(self, col, data, **kwargs) -> None:
        self.columns[col] = list(data)
        self.designations[col] = kwargs["axis"]

    def to_list(self, col):
        return self.columns[col]

    def activate(self) -> None:
        return None

    def lt_range(self, *_args) -> str:
        return "[DataBook]Sheet1"

    def get_int(self, name: str) -> int:
        ordinal = int(name.removeprefix("col").removesuffix(".type")) - 1
        return {"x": 4, "y": 1, "n": 2, "e": 3, "m": 7}[self.designations[ordinal].casefold()]


class FakeBook:
    def __init__(self) -> None:
        self.name = "Book1"
        self.sheet = FakeSheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet


class FakeOrigin:
    def __init__(self) -> None:
        self.book = FakeBook()
        self.graph = FakeGraph("G")
        self.graph_created = False
        self.commands: list[str] = []
        self.native_pid = 0
        self.k03_plot_index = 1
        self.lt_values: dict[str, float] = {
            "__X02COUNT": 1.0,
            "__X02PT": 201.0,
            "__X02LV": 1.0,
            "__X02SY": 0.0,
            "__X02SYS": 1.0,
            "__X02C": 0.0,
            "__X02LVC": 0.0,
            "__X02LVW": 500.0,
            "__X02LVS": 0.0,
            "__X02K": 2.0,
            "__X02Z": 5.0,
        }

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs):
        self.book.name = str(args[1])
        return self.book

    def new_graph(self, name, **kwargs):
        self.graph.name = name
        return self.graph

    def pages(self, kind: str):
        if kind == "w":
            return (self.book,)
        if kind == "g":
            return (self.graph,) if self.graph_created else ()
        return ()

    @staticmethod
    def _color(value: str) -> float:
        return float(int(value.removeprefix("#"), 16))

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        if "legendupdate dest:=layer update:=reconstruct" in command:
            self.graph.layer.labels["legend"] = FakeLabel()
        if "worksheet -p 202 LineSymb" in command:
            self.graph_created = True
            self.native_pid = 202
            self.graph.layer.plots = [FakePlot()]
        if "worksheet -p 201 Scatter" in command:
            self.graph_created = True
            self.native_pid = 201
            match = re.search(r"worksheet -s 1 0 (\d+) 0", command)
            assert match is not None
            self.graph.layer.plots = [FakePlot() for _ in range(int(match.group(1)) // 2)]
        if "worksheet -p 201 ERRBAR" in command:
            self.graph_created = True
            self.native_pid = 201
            self.graph.layer.plots = [FakePlot(), FakePlot(), FakePlot()]
        if "run.section(plot,ScatterErrorBand)" in command:
            self.graph_created = True
            self.native_pid = 201
            self.graph.layer.plots = [FakePlot(), FakePlot(), FakePlot()]
        if "set __K07MINUS -om __K07CENTER" in command:
            minus = self.graph.layer.plots[1].GetTheme().Children[0].Children
            plus = self.graph.layer.plots[2].GetTheme().Children[0].Children
            next(item for item in minus if item.Name == "DirectionMinus").value = 1
            next(item for item in plus if item.Name == "DirectionPlus").value = 1
        if "worksheet -p 201 DROPLINE" in command:
            self.graph_created = True
            self.native_pid = 201
            plot = FakePlot()
            plot.DatasetName = f"{self.book.name}_B"
            self.graph.layer.plots = [plot]
        k03_match = re.search(r"range __K03P=\[[^]]+\]1!(\d+)", command)
        if k03_match is not None:
            self.k03_plot_index = int(k03_match.group(1))
        for option, destination in (
            ("-c", "__X02C"),
            ("-lvc", "__X02LVC"),
            ("-lvw", "__X02LVW"),
            ("-lvs", "__X02LVS"),
            ("-k", "__X02K"),
            ("-z", "__X02Z"),
        ):
            match = re.search(
                rf"set __X02P {re.escape(option)} (color\(\"#[0-9A-Fa-f]{{6}}\"\)|[-+0-9.]+)",
                command,
            )
            if match is None:
                continue
            token = match.group(1)
            color_match = re.fullmatch(r'color\("(#[0-9A-Fa-f]{6})"\)', token)
            self.lt_values[destination] = (
                self._color(color_match.group(1)) if color_match is not None else float(token)
            )
        return True

    def lt_float(self, expression: str) -> float:
        color_match = re.fullmatch(r'color\("(#[0-9A-Fa-f]{6})"\)', expression)
        if color_match is not None:
            return self._color(color_match.group(1))
        if expression in {"__K02COUNT", "__K03COUNT", "__K06COUNT", "__K07COUNT"}:
            return float(len(self.graph.layer.plots))
        if expression in {"__K02PID", "__K03PID", "__K06PID", "__K07PID"}:
            return float(self.native_pid)
        return self.lt_values[expression]

    def get_lt_str(self, expression: str) -> str:
        if expression == "__K02XS":
            return f'[{self.book.name}]Sheet1!A"Time"'
        if expression == "__K02YS":
            return f'[{self.book.name}]Sheet1!B"Signal"'
        if expression == "__K03XS":
            letter = chr(65 + (self.k03_plot_index - 1) * 2)
            return f'[{self.book.name}]Sheet1!{letter}"X"'
        if expression == "__K03YS":
            letter = chr(66 + (self.k03_plot_index - 1) * 2)
            return f'[{self.book.name}]Sheet1!{letter}"Y"'
        if expression in {"__K06XS", "__K07XS"}:
            return f'[{self.book.name}]Sheet1!A"X"'
        if expression in {"__K06YS", "__K07YS"}:
            return f'[{self.book.name}]Sheet1!B"Center"'
        if expression == "__X02XS":
            return f'[{self.book.name}]Sheet1!A"Time"'
        if expression == "__X02YS":
            return f'[{self.book.name}]Sheet1!B"Signal"'
        raise KeyError(expression)


def _column(field_id: str, name: str, values: tuple[object, ...]) -> EngineColumn:
    return EngineColumn(
        field=EngineField(field_id=field_id, name=name, logical_type="numeric"),
        values=values,
    )


def _case(
    profile_id: str,
    roles: tuple[str, ...],
    columns: tuple[EngineColumn, ...],
    *,
    style: dict[str, object],
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{profile_id.lower()}",
        version=1,
        content_hash=HASH,
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=column.field.field_id)
        for role, column in zip(roles, columns, strict=True)
    )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-origin",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    title = SetTitle(
        action_id=f"action:title-{profile_id.lower()}",
        target=create.plot_id,
        expected_plot_version=1,
        text=f"Native {profile_id}",
    )
    series = SetSeriesStyle(
        action_id=f"action:style-{profile_id.lower()}",
        target=f"series:{profile_id.lower()}-origin.primary",
        expected_plot_version=2,
        color="#AA3300",
        **style,
    )
    legend = SetLegend(
        action_id=f"action:legend-{profile_id.lower()}",
        target=f"legend:{profile_id.lower()}-origin.main",
        expected_plot_version=3,
        visible=True,
    )
    actions: tuple[PlotEngineAction, ...] = (create, title, series, legend)
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=4,
        parent_version=3,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(1, len(columns[0].values) + 1)),
        columns=columns,
    )
    return document, actions, view


def test_new_t1_official_template_identities_are_hash_pinned() -> None:
    assert (K02_ORIGIN_PROFILE.filename, K02_ORIGIN_PROFILE.sha256) == (
        "LINESYMB.otpu",
        "2f1292a939eac92cd0dc820309885caccfa53293d1db78d18447a5b5b329fed1",
    )
    assert (K06_ORIGIN_PROFILE.filename, K06_ORIGIN_PROFILE.sha256) == (
        "ERRBAR.otpu",
        "c17ebd8f68f8585c3bb4c431e75f4dc1724e3f54ee1fd7d0977b6cadcf1c599b",
    )
    assert (K03_ORIGIN_PROFILE.filename, K03_ORIGIN_PROFILE.sha256) == (
        "SCATTER.OTP",
        "efef85d7c3db5028c565a57e15c86f97d6ebeded6d779c1cdb11328a7fbd4a99",
    )
    assert (K07_ORIGIN_PROFILE.filename, K07_ORIGIN_PROFILE.sha256) == (
        "ERRORBAND.otp",
        "dfd36bf19bf3cf81bebd7d2b7d04a0ef05f07f90243678ddf3d03eded342c763",
    )
    assert (K18_ORIGIN_PROFILE.filename, K18_ORIGIN_PROFILE.sha256) == (
        "AREA.otpu",
        "c14ad432ffd60db09f6763b7b988de4aa554dcf0d9772b18334970fb83eddaec",
    )
    assert (X02_ORIGIN_PROFILE.filename, X02_ORIGIN_PROFILE.sha256) == (
        "DROPLINE.OTP",
        "69cbcf9349249092e2e32c8955c88c0a265ac47a46811885593d9eced643299f",
    )


def test_k02_binds_one_native_line_symbol_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    columns = (
        _column("field:x", "Time", (0.0, 1.0, 2.0)),
        _column("field:y", "Signal", (1.0, 2.0, 4.0)),
    )
    document, actions, view = _case(
        "K02",
        ("x", "y"),
        columns,
        style={
            "line_width_pt": 2.0,
            "line_style": "dash",
            "symbol": "diamond",
            "symbol_size_pt": 7.0,
        },
    )
    monkeypatch.setattr(
        k02_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = FakeOrigin()
    project = K02OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert any("worksheet -p 202 LineSymb" in command for command in origin.commands)
    assert origin.graph.layer.add_calls == []
    assert origin.graph.layer.plots[0].symbol_kind == 5
    assert origin.graph.layer.labels["legend"].text.count("\\l(") == 1
    assert "line_symbol_series" in {item.object_kind for item in readback.objects}


def test_k03_binds_one_native_scatter_plot_per_data_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = EngineDataRef(
        kind="source",
        dataset_id="dataset.k03",
        version=1,
        content_hash=HASH,
    )
    columns = (
        _column("field:x", "Dose", (0.0, 1.0, 2.0, 3.0)),
        _column("field:y", "Response", (1.0, 2.0, 4.0, 3.0)),
        EngineColumn(
            field=EngineField(
                field_id="field:group",
                name="Cohort",
                logical_type="categorical",
            ),
            values=("Control", "Treatment", "Control", "Treatment"),
        ),
    )
    bindings = (
        FieldBinding(role="x", field_id="field:x"),
        FieldBinding(role="y", field_id="field:y"),
        FieldBinding(role="group", field_id="field:group"),
    )
    create = CreatePlot(
        action_id="action:create-k03",
        plot_id="plot:k03-origin",
        profile_id="K03",
        data=data,
        bindings=bindings,
    )
    style = SetSeriesStyle(
        action_id="action:style-k03",
        target="series:k03-origin.group_2",
        expected_plot_version=1,
        color="#AA3300",
        symbol="diamond",
        symbol_size_pt=7,
    )
    legend = SetLegend(
        action_id="action:legend-k03",
        target="legend:k03-origin.main",
        expected_plot_version=2,
        visible=True,
    )
    actions: tuple[PlotEngineAction, ...] = (create, style, legend)
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=3,
        parent_version=2,
        profile_id="K03",
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=("row:1", "row:2", "row:3", "row:4"),
        columns=columns,
    )
    monkeypatch.setattr(
        k03_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = FakeOrigin()
    project = K03OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert any("worksheet -p 201 Scatter" in command for command in origin.commands)
    assert origin.graph.layer.add_calls == []
    assert origin.graph.layer.group_calls == [(False, 0, 1)]
    assert origin.graph.layer.labels["legend"].text == ("\\l(1) %(1)\n\\l(2) %(2)")
    assert origin.graph.layer.plots[1].symbol_kind == 5
    assert {
        item.semantic_id for item in readback.objects if item.object_kind == "scatter_series"
    } == {
        "series:k03-origin.group_1",
        "series:k03-origin.group_2",
    }


def test_k03_rebinding_discards_only_prior_data_derived_series_styles() -> None:
    create = CreatePlot(
        action_id="action:create",
        plot_id="plot:k03-reset",
        profile_id="K03",
        data=EngineDataRef(
            kind="source",
            dataset_id="dataset.k03",
            version=1,
            content_hash=HASH,
        ),
        bindings=(FieldBinding(role="x", field_id="field:x"),),
    )
    old_style = SetSeriesStyle(
        action_id="action:old-style",
        target="series:k03-reset.group_2",
        expected_plot_version=1,
        color="#AA3300",
    )
    rebind = BindFields(
        action_id="action:rebind",
        target=create.plot_id,
        expected_plot_version=2,
        data=create.data,
        bindings=create.bindings,
    )
    title = SetTitle(
        action_id="action:title",
        target=create.plot_id,
        expected_plot_version=3,
        text="Retained title",
    )

    assert k03_effective_actions((create, old_style, rebind, title)) == (
        create,
        rebind,
        title,
    )


def test_k06_converts_absolute_bounds_to_native_asymmetric_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    columns = (
        _column("field:x", "X", (1.0, 2.0, 3.0)),
        _column("field:center", "Estimate", (2.0, 3.0, 4.0)),
        _column("field:xl", "X lower", (0.9, 1.8, 2.9)),
        _column("field:xu", "X upper", (1.2, 2.3, 3.1)),
        _column("field:lower", "Lower", (1.7, 2.6, 3.8)),
        _column("field:upper", "Upper", (2.4, 3.5, 4.3)),
    )
    document, actions, view = _case(
        "K06",
        ("x", "center", "x_lower", "x_upper", "lower", "upper"),
        columns,
        style={"line_width_pt": 1.8, "symbol": "square", "symbol_size_pt": 6.0},
    )
    monkeypatch.setattr(
        k06_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = FakeOrigin()
    project = K06OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert any("worksheet -p 201 ERRBAR" in command for command in origin.commands)
    assert origin.graph.layer.add_calls == []
    assert origin.book.sheet.designations == {
        0: "X", 1: "Y", 2: "E", 3: "E", 4: "M", 5: "M"
    }
    assert origin.book.sheet.columns[2] == pytest.approx([0.3, 0.4, 0.2])
    assert origin.book.sheet.columns[3] == pytest.approx([0.4, 0.5, 0.3])
    assert origin.book.sheet.columns[4] == pytest.approx([0.1, 0.2, 0.1])
    assert origin.book.sheet.columns[5] == pytest.approx([0.2, 0.3, 0.1])
    assert any("set __K06YMINUS -om __K06CENTER" in command for command in origin.commands)
    assert origin.graph.layer.plots[0].symbol_kind == 1
    assert "point_error_series" in {item.object_kind for item in readback.objects}


def test_k07_binds_center_and_band_without_boundary_legend_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    columns = (
        _column("field:x", "Dose", (0.0, 1.0, 2.0)),
        _column("field:center", "Response", (2.0, 3.0, 4.0)),
        _column("field:lower", "Lower", (1.5, 2.4, 3.2)),
        _column("field:upper", "Upper", (2.5, 3.8, 4.9)),
    )
    document, actions, view = _case(
        "K07",
        ("x", "center", "lower", "upper"),
        columns,
        style={"line_width_pt": 2.1, "line_style": "dot"},
    )
    monkeypatch.setattr(
        k07_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = FakeOrigin()
    project = K07OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert any("run.section(plot,ScatterErrorBand)" in command for command in origin.commands)
    assert any("set __K07MINUS -om __K07CENTER" in command for command in origin.commands)
    assert any("set __K07PLUS -op __K07CENTER" in command for command in origin.commands)
    for plot in origin.graph.layer.plots[1:]:
        values = {item.Name: item.GetValue() for item in plot.GetTheme().Children[0].Children}
        assert values["ConnectLineMode"] == 1
        assert values["ConnectLineFillArea"] == 1
    assert origin.graph.layer.add_calls == []
    assert origin.book.sheet.designations == {0: "X", 1: "Y", 2: "E", 3: "E"}
    assert origin.book.sheet.columns[2] == pytest.approx([0.5, 0.6, 0.8])
    assert origin.book.sheet.columns[3] == pytest.approx([0.5, 0.8, 0.9])
    assert origin.graph.layer.labels["legend"].text.count("\\l(") == 1
    assert len({plot.color for plot in origin.graph.layer.plots}) == 1
    assert "error_band_series" in {item.object_kind for item in readback.objects}


@pytest.mark.parametrize("row_count", (1, 7, 20))
def test_x02_uses_official_drop_line_command_and_preserves_raw_dynamic_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    row_count: int,
) -> None:
    x_values = tuple(float(index) for index in range(row_count))
    y_values = tuple(10.0 + float(index % 5) for index in range(row_count))
    columns = (
        _column("field:x", "Time", x_values),
        _column("field:y", "Signal", y_values),
    )
    document, actions, view = _case(
        "X02",
        ("x", "y"),
        columns,
        style={
            "line_width_pt": 2.0,
            "line_style": "dot",
            "symbol": "diamond",
            "symbol_size_pt": 6.0,
        },
    )
    monkeypatch.setattr(
        x02_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = FakeOrigin()
    project = X02OriginProject(origin)
    project.create(tmp_path, document, view)
    project.reconcile(document, actions, view)
    readback = project.verify(document, actions, view)

    assert any(
        "worksheet -s 1 0 2 0; worksheet -p 201 DROPLINE;" in command for command in origin.commands
    )
    assert origin.graph.layer.add_calls == []
    assert origin.book.sheet.designations == {0: "X", 1: "Y"}
    assert origin.book.sheet.columns == {0: list(x_values), 1: list(y_values)}
    assert origin.lt_values["__X02PT"] == 201.0
    assert origin.lt_values["__X02LV"] == 1.0
    assert origin.lt_values["__X02SY"] == 0.0
    assert origin.lt_values["__X02SYS"] == 1.0
    assert "drop_line_series" in {item.object_kind for item in readback.objects}


def test_x02_renderer_has_no_generic_graph_or_plot_construction() -> None:
    source = inspect.getsource(x02_module)

    assert "OriginXYProject" not in source
    assert ".new_graph(" not in source
    assert ".add_plot(" not in source
    assert ".plot_list(" not in source
    assert "worksheet -p 201 DROPLINE" in source


@pytest.mark.parametrize(
    ("module", "official_command"),
    (
        (k06_module, "worksheet -p 201 ERRBAR"),
        (k07_module, "run.section(plot,ScatterErrorBand)"),
    ),
)
def test_error_renderers_use_official_menu_without_generic_plot_construction(
    module: object, official_command: str
) -> None:
    source = inspect.getsource(module)

    assert ".new_graph(" not in source
    assert ".add_plot(" not in source
    assert official_command in source


def test_new_t1_origin_binders_do_not_import_the_legacy_compiler() -> None:
    for module in (
        xy_module,
        k03_module,
        k06_module,
        k07_module,
        k18_module,
        x02_module,
    ):
        source = inspect.getsource(module)
        assert "plotagent.origin" not in source
        assert "plotagent.rendering" not in source
        assert "OriginPlan" not in source
        assert "ResolvedPlot" not in source
