from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.distribution as distribution_origin
import plotagent.engine.backends.origin.x09 as x09_origin
import plotagent.engine.backends.origin.x13 as x13_origin
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
    PlotEngineAction,
    SetLegend,
    SetSeriesStyle,
)
from plotagent.engine.backends.matplotlib import (
    MatplotlibBackend,
    X05BeeswarmRenderer,
    X09FloatingIntervalRenderer,
    X13PopulationPyramidRenderer,
)
from plotagent.engine.backends.origin import (
    X05_ORIGIN_PROFILE,
    X09_ORIGIN_PROFILE,
    X13_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.distribution import DistributionOriginProject
from plotagent.engine.backends.origin.x09 import X09OriginProject
from plotagent.engine.backends.origin.x13 import X13OriginProject
from plotagent.engine.profile_data import (
    distribution_groups,
    x09_floating_intervals,
    x13_population_pyramid,
)
from plotagent.engine.profiles import (
    X05_BEESWARM_PROFILE,
    X09_FLOATING_INTERVAL_PROFILE,
    X13_POPULATION_PYRAMID_PROFILE,
)

HASH = "7" * 64


def _case(
    profile_id: str,
    roles: tuple[str, ...],
    columns: tuple[tuple[str, str, str, tuple[object, ...]], ...],
    styles: tuple[tuple[str, str], ...],
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{profile_id.lower()}",
        version=1,
        content_hash=HASH,
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=field_id)
        for role, (field_id, _name, _logical_type, _values) in zip(roles, columns, strict=True)
    )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-native",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    actions: list[PlotEngineAction] = [create]
    for index, (target, color) in enumerate(styles, start=1):
        arguments: dict[str, object] = {"color": color}
        if profile_id == "X05":
            arguments.update(symbol="diamond", symbol_size_pt=6.0)
        else:
            arguments.update(line_width_pt=1.2)
        actions.append(
            SetSeriesStyle(
                action_id=f"action:style-{profile_id.lower()}-{index}",
                target=f"series:{profile_id.lower()}-native.{target}",
                expected_plot_version=index,
                **arguments,
            )
        )
    actions.append(
        SetLegend(
            action_id=f"action:legend-{profile_id.lower()}",
            target=f"legend:{profile_id.lower()}-native.main",
            expected_plot_version=len(actions),
            visible=True,
        )
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=len(actions),
        parent_version=len(actions) - 1,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    row_count = len(columns[0][3])
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(row_count)),
        columns=tuple(
            EngineColumn(
                field=EngineField(
                    field_id=field_id,
                    name=name,
                    logical_type=logical_type,  # type: ignore[arg-type]
                ),
                values=values,
            )
            for field_id, name, logical_type, values in columns
        ),
    )
    return document, tuple(actions), view


def _x05_case(group_count: int = 3):
    groups = tuple(f"Group {group}" for group in range(1, group_count + 1) for _index in range(5))
    values = tuple(
        float(group * 10 + observation)
        for group in range(1, group_count + 1)
        for observation in range(5)
    )
    return _case(
        "X05",
        ("value", "group"),
        (
            ("field:value", "Response", "numeric", values),
            ("field:group", "Cohort", "categorical", groups),
        ),
        ((f"group_{group_count}", "#AA3300"),),
    )


def _x09_case(*, middle: bool = True):
    columns: list[tuple[str, str, str, tuple[object, ...]]] = [
        ("field:category", "Sample", "categorical", ("C", "A", "B")),
        ("field:start", "Start", "numeric", (1.0, 2.0, 1.5)),
        ("field:end", "End", "numeric", (3.0, 4.0, 3.5)),
    ]
    roles = ["category", "start", "end"]
    styles = [("lower", "#2255AA")]
    if middle:
        roles.append("middle")
        columns.append(("field:middle", "Middle", "numeric", (2.0, 3.0, 2.5)))
        styles.append(("upper", "#CC6600"))
    return _case("X09", tuple(roles), tuple(columns), tuple(styles))


def _x13_case():
    return _case(
        "X13",
        ("category", "left", "right"),
        (
            ("field:age", "Age group", "categorical", ("0–9", "10–19", "20–29")),
            ("field:left", "Male", "numeric", (10.0, 12.0, 9.0)),
            ("field:right", "Female", "numeric", (11.0, 13.0, 10.0)),
        ),
        (("left", "#2255AA"), ("right", "#CC6600")),
    )


@pytest.mark.parametrize("group_count", (1, 3, 5))
def test_x05_preserves_dynamic_raw_groups(group_count: int) -> None:
    document, _actions, view = _x05_case(group_count)
    groups = distribution_groups(document, view, profile_id="X05")
    assert len(groups.groups) == group_count
    assert all(len(group.values) == 5 for group in groups.groups)


def test_x09_preserves_rows_and_validates_all_boundaries() -> None:
    document, _actions, view = _x09_case()
    intervals = x09_floating_intervals(document, view)
    assert intervals.categories == ("C", "A", "B")
    assert intervals.middle_values == (2.0, 3.0, 2.5)
    invalid = view.model_copy(
        update={
            "columns": tuple(
                column.model_copy(update={"values": (0.5, *column.values[1:])})
                if column.field.field_id == "field:middle"
                else column
                for column in view.columns
            )
        }
    )
    with pytest.raises(ValueError, match="start <= middle <= end"):
        x09_floating_intervals(document, invalid)


def test_x13_preserves_positive_magnitudes_and_rejects_negative_input() -> None:
    document, _actions, view = _x13_case()
    pyramid = x13_population_pyramid(document, view)
    assert pyramid.left_values == (10.0, 12.0, 9.0)
    invalid = view.model_copy(
        update={
            "columns": tuple(
                column.model_copy(update={"values": (-1.0, *column.values[1:])})
                if column.field.field_id == "field:left"
                else column
                for column in view.columns
            )
        }
    )
    with pytest.raises(ValueError, match="non-negative"):
        x13_population_pyramid(document, invalid)


@pytest.mark.parametrize(
    ("renderer", "case", "object_kind", "count"),
    (
        (X05BeeswarmRenderer(), _x05_case, "beeswarm_series", 3),
        (X09FloatingIntervalRenderer(), _x09_case, "floating_interval_segment", 2),
        (X13PopulationPyramidRenderer(), _x13_case, "population_bar_series", 2),
    ),
)
def test_independent_matplotlib_renderers_emit_profile_native_objects(
    tmp_path: Path,
    renderer,
    case,
    object_kind: str,
    count: int,
) -> None:
    document, actions, view = case()
    backend = MatplotlibBackend(tmp_path / renderer.profile_id, (renderer,))
    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()
    readback = backend.readback(document)
    assert len([item for item in readback.objects if item.object_kind == object_kind]) == count
    output = (
        tmp_path
        / renderer.profile_id
        / document.plot_id.removeprefix("plot:")
        / f"v{document.plot_version}"
    )
    assert (output / "preview.png").stat().st_size > 1_000
    assert (output / "preview.svg").stat().st_size > 1_000


class _Label:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.name = ""
        self.values = {"show": 1}

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)


class _Axis:
    def __init__(self) -> None:
        self.scale = "linear"
        self.limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin, end, step=1.0) -> None:
        self.limits = (float(begin), float(end), float(step))


class _Plot:
    def __init__(self) -> None:
        self._color = (22, 118, 210)
        self.floats = {"line.width": 0.8}
        self.symbol_kind = 2
        self.symbol_size = 5.0

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


class _Native:
    def IsValid(self) -> bool:
        return True


class _Layer:
    def __init__(self) -> None:
        self.obj = self
        self.labels = {"xb": _Label("X"), "yl": _Label("Y")}
        self.axes = {"x": _Axis(), "y": _Axis()}
        self.plots: list[_Plot] = []
        self.add_calls: list[dict[str, object]] = []
        self.native_calls: list[tuple[object, int, bool]] = []
        self.group_calls: list[tuple[object, ...]] = []

    def add_plot(self, _sheet, **kwargs):
        self.add_calls.append(kwargs)
        plot = _Plot()
        self.plots.append(plot)
        return plot

    def AddPlot(self, data_range, plot_type: int, rescale: bool):
        self.native_calls.append((data_range, plot_type, rescale))
        self.plots.extend((_Plot(), _Plot()))
        return _Native()

    def plot_list(self):
        return self.plots

    def group(self, *args) -> None:
        self.group_calls.append(args)

    def rescale(self) -> None:
        return None

    def label(self, name: str):
        direct = self.labels.get(name)
        if direct is not None:
            return direct
        return next((label for label in self.labels.values() if label.name == name), None)

    def add_label(self, text: str, _x=None, _y=None):
        label = _Label(text)
        self.labels[f"new-{len(self.labels)}"] = label
        return label

    def axis(self, name: str):
        return self.axes[name]

    def activate(self) -> None:
        return None

    def LT_execute(self, command: str) -> bool:
        assert command == "legend"
        self.labels["legend"] = _Label()
        return True


class _Graph:
    def __init__(self, layer_count: int) -> None:
        self.name = "G"
        self.layers = tuple(_Layer() for _index in range(layer_count))

    def __getitem__(self, index: int):
        return self.layers[index]

    def __iter__(self):
        return iter(self.layers)


class _Sheet:
    def __init__(self) -> None:
        self.obj = self
        self.columns: dict[int, list[object]] = {}

    def __getitem__(self, index: int):
        return index

    def from_list(self, column: int, values, **_kwargs) -> None:
        self.columns[column] = list(values)

    def to_list(self, column: int):
        return self.columns[column]


class _Book:
    def __init__(self) -> None:
        self.sheet = _Sheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet


class _Origin:
    def __init__(self) -> None:
        self.book = _Book()
        self.graph: _Graph | None = None
        self.template = ""
        self.ranges: list[tuple[object, ...]] = []

    def new(self, *, asksave: bool) -> None:
        assert asksave is False

    def new_book(self, *_args, **_kwargs):
        return self.book

    def new_graph(self, name: str, *, template: str, hidden: bool):
        assert hidden is True
        self.template = template
        self.graph = _Graph(2 if "populationpyramid" in template.lower() else 1)
        self.graph.name = name
        return self.graph

    def make_DataRange(self, *args):
        self.ranges.append(args)
        return args


def test_x05_origin_binds_dynamic_groups_to_official_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, actions, view = _x05_case(3)
    monkeypatch.setattr(
        distribution_origin,
        "resolve_official_template",
        lambda _install, profile: tmp_path / profile.filename,
    )
    origin = _Origin()
    project = DistributionOriginProject(origin, profile_id="X05")
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)
    assert Path(origin.template).name.lower() == X05_ORIGIN_PROFILE.filename.lower()
    assert origin.graph is not None
    assert origin.graph[0].add_calls == [
        {"coly": index, "colx": "#", "type": "?"} for index in range(3)
    ]
    assert (
        len([item for item in readback.objects if item.object_kind.endswith("native_group")]) == 3
    )


def test_x09_origin_uses_two_native_xyy_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, actions, view = _x09_case()
    monkeypatch.setattr(
        x09_origin,
        "resolve_official_template",
        lambda _install, profile: tmp_path / profile.filename,
    )
    origin = _Origin()
    project = X09OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)
    assert Path(origin.template).name.lower() == X09_ORIGIN_PROFILE.filename.lower()
    assert origin.graph is not None
    assert [call[1] for call in origin.graph[0].native_calls] == [207, 207]
    assert origin.graph[0].group_calls == [(True, 0, 1), (True, 2, 3)]
    assert origin.graph[0].plots[0].color == (34, 85, 170)
    assert origin.graph[0].plots[2].color == (204, 102, 0)
    assert (
        len([item for item in readback.objects if item.object_kind == "native_floating_interval"])
        == 2
    )


def test_x13_origin_uses_both_official_template_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, actions, view = _x13_case()
    monkeypatch.setattr(
        x13_origin,
        "resolve_official_template",
        lambda _install, profile: tmp_path / profile.filename,
    )
    origin = _Origin()
    project = X13OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)
    assert Path(origin.template).name.lower() == X13_ORIGIN_PROFILE.filename.lower()
    assert origin.graph is not None
    assert [layer.add_calls for layer in origin.graph] == [
        [{"coly": 1, "colx": 0, "type": 215}],
        [{"coly": 2, "colx": 0, "type": 215}],
    ]
    assert (
        len([item for item in readback.objects if item.object_kind == "native_population_bar"]) == 2
    )


def test_profiles_publish_only_shared_agent_actions_and_pinned_templates() -> None:
    assert X05_BEESWARM_PROFILE.required_roles == ("value",)
    assert X09_FLOATING_INTERVAL_PROFILE.optional_roles == ("middle",)
    assert X13_POPULATION_PYRAMID_PROFILE.required_roles == ("category", "left", "right")
    assert X05_ORIGIN_PROFILE.sha256.startswith("301dd6c8c293")
    assert X09_ORIGIN_PROFILE.sha256.startswith("f1ea445735f9")
    assert X13_ORIGIN_PROFILE.sha256.startswith("2c5958a91130")
    operations = {
        profile.profile_id: tuple(capability.operation for capability in profile.capabilities)
        for profile in (
            X05_BEESWARM_PROFILE,
            X09_FLOATING_INTERVAL_PROFILE,
            X13_POPULATION_PYRAMID_PROFILE,
        )
    }
    assert all(
        "create_plot" in values and "export_plot" in values for values in operations.values()
    )


def test_new_profile_paths_do_not_import_the_old_compiler() -> None:
    modules = (
        X05BeeswarmRenderer.__module__,
        X09FloatingIntervalRenderer.__module__,
        X13PopulationPyramidRenderer.__module__,
        DistributionOriginProject.__module__,
        X09OriginProject.__module__,
        X13OriginProject.__module__,
    )
    source = "\n".join(inspect.getsource(__import__(module, fromlist=["*"])) for module in modules)
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
