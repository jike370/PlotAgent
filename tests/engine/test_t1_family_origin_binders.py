from __future__ import annotations

import inspect
from pathlib import Path

import pytest

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
from plotagent.engine.backends.origin.k18 import K18OriginProject
from plotagent.engine.backends.origin.x02 import X02OriginProject

HASH = "4" * 64


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
        self._color = (22, 118, 210)
        self.floats = {"line.width": 1.5}
        self.ints = {"line.style": 0}
        self.symbol_kind = 2
        self.symbol_size = 5.0

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
        assert command == "legend"
        self.labels["legend"] = FakeLabel()
        return True


class FakeGraph:
    def __init__(self, name: str) -> None:
        self.name = name
        self.layer = FakeLayer()

    def __getitem__(self, index: int):
        assert index == 0
        return self.layer


class FakeSheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}
        self.designations: dict[int, str] = {}

    def from_list(self, col, data, **kwargs) -> None:
        self.columns[col] = list(data)
        self.designations[col] = kwargs["axis"]

    def to_list(self, col):
        return self.columns[col]


class FakeBook:
    def __init__(self) -> None:
        self.sheet = FakeSheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet


class FakeOrigin:
    def __init__(self) -> None:
        self.book = FakeBook()
        self.graph = FakeGraph("G")

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs):
        return self.book

    def new_graph(self, name, **kwargs):
        self.graph.name = name
        return self.graph


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
        xy_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = FakeOrigin()
    project = K02OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert origin.graph.layer.add_calls == [{"coly": 1, "colx": 0, "type": "y"}]
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

    assert origin.graph.layer.add_calls == [
        {"coly": 1, "colx": 0, "type": "s"},
        {"coly": 3, "colx": 2, "type": "s"},
    ]
    assert origin.graph.layer.group_calls == [(True, 0, 1)]
    assert origin.graph.layer.labels["legend"].text == ("\\l(1) Control\n\\l(2) Treatment")
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


def test_k06_binds_real_x_and_y_error_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    columns = (
        _column("field:x", "X", (1.0, 2.0, 3.0)),
        _column("field:center", "Estimate", (2.0, 3.0, 4.0)),
        _column("field:xerr", "X error", (0.1, 0.2, 0.1)),
        _column("field:yerr", "Y error", (0.3, 0.4, 0.2)),
    )
    document, actions, view = _case(
        "K06",
        ("x", "center", "x_error", "y_error"),
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

    assert origin.graph.layer.add_calls == [
        {"coly": 1, "colx": 0, "colyerr": 2, "colxerr": 3, "type": "s"}
    ]
    assert origin.book.sheet.designations == {0: "X", 1: "Y", 2: "E", 3: "M"}
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

    assert origin.graph.layer.add_calls == [
        {"coly": 1, "colx": 0, "type": "?"},
        {"coly": 2, "colx": 0, "type": "?"},
        {"coly": 3, "colx": 0, "type": "?"},
    ]
    assert origin.graph.layer.labels["legend"].text.count("\\l(") == 1
    assert len({plot.color for plot in origin.graph.layer.plots}) == 1
    assert "error_band_series" in {item.object_kind for item in readback.objects}


@pytest.mark.parametrize(
    ("profile_id", "project_type", "style", "object_kind"),
    (
        (
            "K18",
            K18OriginProject,
            {"line_width_pt": 2.0, "line_style": "dash"},
            "area_series",
        ),
        (
            "X02",
            X02OriginProject,
            {
                "line_width_pt": 1.5,
                "line_style": "dot",
                "symbol": "diamond",
                "symbol_size_pt": 6.0,
            },
            "drop_line_series",
        ),
    ),
)
def test_official_template_native_xy_profiles_keep_template_plot_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
    project_type,
    style: dict[str, object],
    object_kind: str,
) -> None:
    columns = (
        _column("field:x", "X", (0.0, 1.0, 2.0)),
        _column("field:y", "Y", (-1.0, 3.0, 2.0)),
    )
    document, actions, view = _case(profile_id, ("x", "y"), columns, style=style)
    monkeypatch.setattr(
        xy_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = FakeOrigin()
    project = project_type(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert origin.graph.layer.add_calls == [{"coly": 1, "colx": 0, "type": "?"}]
    assert object_kind in {item.object_kind for item in readback.objects}


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
