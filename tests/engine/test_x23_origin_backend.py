from __future__ import annotations

import inspect
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
    def __init__(self) -> None:
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
        assert type == "l"
        plot = FakePlot()
        self.plots.append(plot)
        return plot

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


class FakeBook:
    def __init__(self) -> None:
        self.sheet = FakeSheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet


class FakeOrigin:
    def __init__(self) -> None:
        self.book = FakeBook()
        self.graph = FakeGraph()
        self.template = ""

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, kind, name, *, hidden):
        assert kind == "w"
        return self.book

    def new_graph(self, name, *, template, hidden):
        self.graph.name = name
        self.template = template
        return self.graph


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
        SetTitle(action_id="action:title", target=create.plot_id, text="Native dual Y"),
        SetAxis(
            action_id="action:right-axis",
            target="axis:origin-dual.y_right",
            label="GDP (USD)",
            minimum=15_000,
            maximum=30_000,
        ),
        SetSeriesStyle(
            action_id="action:left-style",
            target="series:origin-dual.left",
            color="#0F766E",
            line_width_pt=2.0,
        ),
        SetSeriesStyle(
            action_id="action:right-style",
            target="series:origin-dual.right",
            color="#BE123C",
            line_style="dash",
        ),
        SetLegend(
            action_id="action:legend",
            target="legend:origin-dual.main",
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
    for action in actions:
        project.apply(document, action, view)
    project.reconcile(document, actions, view)
    readback = project.verify(document, actions, view)

    assert readback.document.plot_version == 6
    assert Path(op.template).name.casefold() == X23_ORIGIN_PROFILE.filename.casefold()
    assert [len(layer.plots) for layer in op.graph.layers] == [1, 1]
    assert op.book.sheet.designation == "xyy"
    assert op.graph.layers[0].plots[0].color == (15, 118, 110)
    assert op.graph.layers[1].plots[0].color == (190, 18, 60)
    assert "\\l(1, style:l)" in op.graph.layers[0].labels["legend"].text
    assert "\\l(2.1, style:l)" in op.graph.layers[0].labels["legend"].text


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
