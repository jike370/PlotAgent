from __future__ import annotations

import inspect
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

import plotagent.engine.backends.origin.column_family as origin_module
import plotagent.engine.backends.origin.distribution as distribution_origin_module
from plotagent.engine import (
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
)
from plotagent.engine.backends.matplotlib import (
    K09GroupedColumnRenderer,
    K10StackedColumnRenderer,
    K11PercentStackRenderer,
    K12StripRenderer,
    K13BoxRenderer,
    K14ViolinRenderer,
    MatplotlibBackend,
)
from plotagent.engine.backends.origin import (
    K09_ORIGIN_PROFILE,
    K10_ORIGIN_PROFILE,
    K11_ORIGIN_PROFILE,
    K12_ORIGIN_PROFILE,
    K13_ORIGIN_PROFILE,
    K14_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.column_family import ColumnFamilyOriginProject
from plotagent.engine.backends.origin.distribution import DistributionOriginProject
from plotagent.engine.profile_data import category_series_grid, distribution_groups

HASH = "9" * 64


def _case(
    profile_id: str,
    series_count: int,
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{profile_id.lower()}",
        version=1,
        content_hash=HASH,
    )
    series_role = "group" if profile_id == "K09" else "component"
    categories = ("B", "A")
    rows = tuple(
        (category, f"S{series}", float(category_index * 10 + series))
        for category_index, category in enumerate(categories, start=1)
        for series in range(1, series_count + 1)
    )
    bindings = (
        FieldBinding(role="category", field_id="field:category"),
        FieldBinding(role=series_role, field_id="field:series"),
        FieldBinding(role="value", field_id="field:value"),
    )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-columns",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    style = SetSeriesStyle(
        action_id=f"action:style-{profile_id.lower()}",
        target=f"series:{profile_id.lower()}-columns.{series_role}_{series_count}",
        expected_plot_version=1,
        color="#AA3300",
        line_width_pt=1.2,
    )
    legend = SetLegend(
        action_id=f"action:legend-{profile_id.lower()}",
        target=f"legend:{profile_id.lower()}-columns.main",
        expected_plot_version=2,
        visible=True,
    )
    actions: tuple[PlotEngineAction, ...] = (create, style, legend)
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=3,
        parent_version=2,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(len(rows))),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:category",
                    name="Condition",
                    logical_type="categorical",
                ),
                values=tuple(row[0] for row in rows),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:series",
                    name="Cohort",
                    logical_type="categorical",
                ),
                values=tuple(row[1] for row in rows),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:value",
                    name="Response",
                    logical_type="numeric",
                ),
                values=tuple(row[2] for row in rows),
            ),
        ),
    )
    return document, actions, view


@pytest.mark.parametrize("profile_id", ("K09", "K10", "K11"))
@pytest.mark.parametrize("series_count", (1, 3, 5))
def test_column_family_grid_preserves_first_appearance_and_dynamic_series(
    profile_id: str,
    series_count: int,
) -> None:
    document, _, view = _case(profile_id, series_count)
    grid = category_series_grid(document, view, profile_id=profile_id)  # type: ignore[arg-type]

    assert grid.category_labels == ("B", "A")
    assert grid.series_labels == tuple(f"S{index}" for index in range(1, series_count + 1))
    assert len(grid.values) == 2
    assert all(len(row) == series_count for row in grid.values)


def test_column_family_rejects_duplicate_cells() -> None:
    document, _, view = _case("K09", 1)
    duplicate = view.model_copy(
        update={
            "row_ids": (*view.row_ids, "row:duplicate"),
            "columns": tuple(
                column.model_copy(update={"values": (*column.values, column.values[0])})
                for column in view.columns
            ),
        }
    )
    with pytest.raises(ValueError, match="duplicate category/series"):
        category_series_grid(document, duplicate, profile_id="K09")


@pytest.mark.parametrize(
    ("profile_id", "renderer", "object_kind"),
    (
        ("K09", K09GroupedColumnRenderer(), "grouped_column_series"),
        ("K10", K10StackedColumnRenderer(), "stacked_column_series"),
        ("K11", K11PercentStackRenderer(), "percent_column_series"),
    ),
)
def test_independent_column_renderers_emit_one_semantic_series_per_data_series(
    tmp_path: Path,
    profile_id: str,
    renderer,
    object_kind: str,
) -> None:
    document, actions, view = _case(profile_id, 3)
    backend = MatplotlibBackend(tmp_path / profile_id, (renderer,))
    change = backend.stage(document, actions, view)
    change.publish()
    readback = backend.readback(document)

    assert len([item for item in readback.objects if item.object_kind == object_kind]) == 3
    assert (
        tmp_path / profile_id / f"{profile_id.lower()}-columns" / "v3" / "preview.png"
    ).stat().st_size > 1_000


def test_k09_grouped_columns_do_not_overlap_for_five_groups() -> None:
    document, actions, view = _case("K09", 5)
    renderer = K09GroupedColumnRenderer()
    grid = category_series_grid(document, view, profile_id="K09")
    state = renderer._state(document, actions, grid)
    figure, axis = plt.subplots()
    containers = renderer._draw(
        axis,
        np.arange(len(grid.category_labels), dtype=float),
        np.asarray(grid.values),
        grid,
        state,
    )
    first_category = sorted(
        (
            container.patches[0].get_x(),
            container.patches[0].get_x() + container.patches[0].get_width(),
        )
        for container in containers
    )
    plt.close(figure)
    assert all(
        left[1] <= right[0] + 1e-12
        for left, right in zip(first_category, first_category[1:], strict=False)
    )


def test_k11_normalizes_each_category_to_exactly_one_hundred_percent() -> None:
    document, _, view = _case("K11", 3)
    renderer = K11PercentStackRenderer()
    values = renderer._plot_values(category_series_grid(document, view, profile_id="K11"))
    assert tuple(np.sum(values, axis=1)) == pytest.approx((100.0, 100.0))


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
    scale = "linear"
    limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin, end, step=1.0) -> None:
        self.limits = (float(begin), float(end), float(step))


class _Plot:
    def __init__(self) -> None:
        self._color = (22, 118, 210)
        self.floats = {"line.width": 0.8}
        self.commands: list[str] = []

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

    def set_cmd(self, command: str) -> None:
        self.commands.append(command)


class _Layer:
    def __init__(self) -> None:
        self.obj = self
        self.labels = {"xb": _Label("X"), "yl": _Label("Y")}
        self.axes = {"x": _Axis(), "y": _Axis()}
        self.plots: list[_Plot] = []
        self.add_calls: list[dict[str, object]] = []
        self.group_calls: list[tuple[object, ...]] = []

    def add_plot(self, sheet, **kwargs):
        self.add_calls.append(kwargs)
        plot = _Plot()
        self.plots.append(plot)
        return plot

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

    def add_label(self, text: str, x=None, y=None):
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
    def __init__(self) -> None:
        self.name = "G"
        self.layer = _Layer()

    def __getitem__(self, index: int):
        assert index == 0
        return self.layer


class _Sheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}

    def from_list(self, column: int, values, **kwargs) -> None:
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
        self.graph = _Graph()
        self.template = ""

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs):
        return self.book

    def new_graph(self, name: str, *, template: str, hidden: bool):
        self.graph.name = name
        self.template = template
        return self.graph


@pytest.mark.parametrize(
    ("profile_id", "profile"),
    (("K09", K09_ORIGIN_PROFILE), ("K10", K10_ORIGIN_PROFILE), ("K11", K11_ORIGIN_PROFILE)),
)
def test_column_family_origin_binders_start_from_pinned_official_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
    profile,
) -> None:
    document, actions, view = _case(profile_id, 3)
    monkeypatch.setattr(
        origin_module,
        "resolve_official_template",
        lambda install, selected: tmp_path / selected.filename,
    )
    origin = _Origin()
    project = ColumnFamilyOriginProject(origin, profile_id=profile_id)  # type: ignore[arg-type]
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert Path(origin.template).name.lower() == profile.filename.lower()
    assert origin.graph.layer.add_calls == [
        {"coly": index, "colx": 0, "type": "?"} for index in range(1, 4)
    ]
    assert origin.graph.layer.group_calls == [(True, 0, 2)]
    assert origin.graph.layer.labels["legend"].text.count("\\l(") == 3
    assert (
        len([item for item in readback.objects if item.object_kind.endswith("native_series")]) == 3
    )
    if profile_id == "K09":
        assert origin.graph.layer.plots[0].commands == ["-vg 73"]


def test_column_family_new_path_has_no_legacy_compiler_dependency() -> None:
    modules = (
        K09GroupedColumnRenderer.__module__,
        K10StackedColumnRenderer.__module__,
        K11PercentStackRenderer.__module__,
        ColumnFamilyOriginProject.__module__,
    )
    source = "\n".join(inspect.getsource(__import__(module, fromlist=["*"])) for module in modules)
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source


def _distribution_case(
    profile_id: str,
    group_count: int,
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{profile_id.lower()}",
        version=1,
        content_hash=HASH,
    )
    rows = tuple(
        (f"G{group}", float(group * 10 + observation))
        for group in range(1, group_count + 1)
        for observation in range(1, 7)
    )
    bindings = (
        FieldBinding(role="value", field_id="field:value"),
        FieldBinding(role="group", field_id="field:group"),
    )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-distribution",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    style_arguments: dict[str, object] = {"color": "#AA3300"}
    if profile_id == "K12":
        style_arguments.update(symbol="diamond", symbol_size_pt=7.0)
    else:
        style_arguments.update(line_width_pt=1.4)
    style = SetSeriesStyle(
        action_id=f"action:style-{profile_id.lower()}",
        target=f"series:{profile_id.lower()}-distribution.group_{group_count}",
        expected_plot_version=1,
        **style_arguments,
    )
    legend = SetLegend(
        action_id=f"action:legend-{profile_id.lower()}",
        target=f"legend:{profile_id.lower()}-distribution.main",
        expected_plot_version=2,
        visible=True,
    )
    actions: tuple[PlotEngineAction, ...] = (create, style, legend)
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=3,
        parent_version=2,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(len(rows))),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:value", name="Measurement", logical_type="numeric"
                ),
                values=tuple(row[1] for row in rows),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:group", name="Cohort", logical_type="categorical"
                ),
                values=tuple(row[0] for row in rows),
            ),
        ),
    )
    return document, actions, view


@pytest.mark.parametrize("profile_id", ("K12", "K13", "K14"))
@pytest.mark.parametrize("group_count", (1, 3, 5))
def test_distribution_profiles_use_raw_dynamic_groups(
    profile_id: str,
    group_count: int,
) -> None:
    document, _, view = _distribution_case(profile_id, group_count)
    distribution = distribution_groups(document, view, profile_id=profile_id)  # type: ignore[arg-type]
    assert tuple(group.label for group in distribution.groups) == tuple(
        f"G{index}" for index in range(1, group_count + 1)
    )
    assert all(len(group.values) == 6 for group in distribution.groups)


@pytest.mark.parametrize(
    ("profile_id", "renderer", "object_kind"),
    (
        ("K12", K12StripRenderer(), "strip_series"),
        ("K13", K13BoxRenderer(), "box_series"),
        ("K14", K14ViolinRenderer(), "violin_series"),
    ),
)
def test_distribution_renderers_are_independent_and_dynamic(
    tmp_path: Path,
    profile_id: str,
    renderer,
    object_kind: str,
) -> None:
    document, actions, view = _distribution_case(profile_id, 3)
    backend = MatplotlibBackend(tmp_path / profile_id, (renderer,))
    change = backend.stage(document, actions, view)
    change.publish()
    readback = backend.readback(document)
    assert len([item for item in readback.objects if item.object_kind == object_kind]) == 3


def test_k14_matplotlib_omits_extrema_edge_lines() -> None:
    document, actions, view = _distribution_case("K14", 2)
    renderer = K14ViolinRenderer()
    distribution = distribution_groups(document, view, profile_id="K14")
    state = renderer._state(document, actions, distribution)
    figure, axis = plt.subplots()
    renderer._draw(axis, distribution, state)
    segments = tuple(
        segment
        for collection in axis.collections
        if hasattr(collection, "get_segments")
        for segment in collection.get_segments()
    )
    plt.close(figure)
    assert segments
    assert all(segment[0][1] == pytest.approx(segment[-1][1]) for segment in segments)


@pytest.mark.parametrize(
    ("profile_id", "profile"),
    (("K12", K12_ORIGIN_PROFILE), ("K13", K13_ORIGIN_PROFILE), ("K14", K14_ORIGIN_PROFILE)),
)
def test_distribution_origin_uses_only_the_official_native_plot_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
    profile,
) -> None:
    document, actions, view = _distribution_case(profile_id, 3)
    monkeypatch.setattr(
        distribution_origin_module,
        "resolve_official_template",
        lambda install, selected: tmp_path / selected.filename,
    )
    origin = _Origin()
    project = DistributionOriginProject(origin, profile_id=profile_id)  # type: ignore[arg-type]
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert Path(origin.template).name.lower() == profile.filename.lower()
    assert origin.graph.layer.add_calls == [
        {"coly": index, "colx": "#", "type": "?"} for index in range(3)
    ]
    assert (
        len([item for item in readback.objects if item.object_kind.endswith("native_group")]) == 3
    )
    assert "line" not in str(origin.graph.layer.add_calls).lower()
    assert "fill" not in str(origin.graph.layer.add_calls).lower()
