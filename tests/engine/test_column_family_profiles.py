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
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
    PlotEngineAction,
    SetLegend,
    SetObservationOverlay,
    SetSeriesStyle,
    SetTitle,
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
from plotagent.engine.backends.origin.native_distribution import (
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
)
from plotagent.engine.profile_data import (
    category_series_grid,
    distribution_groups,
    k09_grouped_indexed_data,
    regular_observation_positions,
)
from plotagent.engine.visual_t1 import split_visual_actions

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
        fill_stroke_color="#AA3300",
        fill_stroke_width_pt=1.2,
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
    change = backend.stage(document, actions, EngineRenderSource(data=view))
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
    state = renderer._state(document, split_visual_actions(actions)[0], grid)
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


def test_k09_preserves_long_rows_for_origin_grouped_indexed_route() -> None:
    document, _, view = _case("K09", 3)
    indexed = k09_grouped_indexed_data(document, view)

    assert indexed.indexes == (1, 2, 3, 4, 5, 6)
    assert indexed.categories == ("B", "B", "B", "A", "A", "A")
    assert indexed.groups == ("S1", "S2", "S3", "S1", "S2", "S3")
    assert indexed.values == (11.0, 12.0, 13.0, 21.0, 22.0, 23.0)


class _Label:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.name = ""
        self.values = {"show": 1}

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def set_float(self, name: str, value: float) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)


class _Axis:
    scale = "linear"
    limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin, end, step=1.0) -> None:
        self.limits = (float(begin), float(end), float(step))


class _Plot:
    def __init__(self, dataset_name: str = "", plot_type: int = 206) -> None:
        self.obj = self
        self.DatasetName = dataset_name
        self.plot_type = plot_type
        self._color = (22, 118, 210)
        self.floats = {"line.width": 0.8}
        self.commands: list[str] = []
        self.ints = {"show": 1}
        self.style_options: dict[str, int | float] = {}

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

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)


class _ThemeNode:
    def __init__(
        self,
        name: str,
        value: int = 0,
        children=(),
        *,
        double: float | None = None,
    ) -> None:
        self.Name = name
        self.nVal = value
        self.dVal = float(value) if double is None else double
        self.Children = list(children)

    def SetIntValue(self, value: int) -> None:
        self.nVal = value

    def GetValue(self) -> int:
        return self.nVal

    def GetIntValue(self) -> int:
        return self.nVal

    def SetDoubleValue(self, value: float) -> None:
        self.dVal = value

    def GetDoubleValue(self) -> float:
        return self.dVal


class _Layer:
    def __init__(self) -> None:
        self.obj = self
        self.labels = {"xb": _Label("X"), "yl": _Label("Y")}
        self.axes = {"x": _Axis(), "y": _Axis()}
        self.plots: list[_Plot] = []
        self.add_calls: list[dict[str, object]] = []
        self.group_calls: list[tuple[object, ...]] = []
        self.numeric_properties: dict[str, int | float] = {}
        self.theme = _ThemeNode(
            "Root",
            children=(
                _ThemeNode(
                    "Stack",
                    children=(
                        _ThemeNode("Offset"),
                        _ThemeNode("StackOffset"),
                    ),
                ),
            ),
        )

    def add_plot(self, sheet, **kwargs):
        self.add_calls.append(kwargs)
        coly = kwargs.get("coly")
        dataset_name = "" if coly is None else sheet.obj[int(coly)].DatasetName
        raw_type = kwargs.get("type", kwargs.get("official", 206))
        plot_type = 201 if raw_type in {"s", "scatter", 201} else 206
        plot = _Plot(dataset_name, plot_type)
        self.plots.append(plot)
        return plot

    def plot_list(self):
        return self.plots

    def group(self, *args) -> None:
        self.group_calls.append(args)

    def rescale(self) -> None:
        return None

    def set_int(self, name: str, value: int) -> None:
        self.numeric_properties[name] = int(value)

    def get_int(self, name: str) -> int:
        return int(self.numeric_properties.get(name, 0))

    def set_float(self, name: str, value: float) -> None:
        self.numeric_properties[name] = float(value)

    def get_float(self, name: str) -> float:
        return float(self.numeric_properties.get(name, 0.0))

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
        if command == "legend":
            self.labels["legend"] = _Label()
        elif command.startswith("label -j 1 -n _ENGINE_TITLE"):
            self.labels["_ENGINE_TITLE"] = _Label("PlotAgentTitlePlaceholder")
        else:
            raise AssertionError(command)
        return True

    def GetTheme(self):
        return self.theme

    def PutTheme(self, theme) -> None:
        assert theme is self.theme


class _Graph:
    def __init__(self) -> None:
        self.name = "G"
        self.lname = ""
        self.layer = _Layer()

    def __getitem__(self, index: int):
        assert index == 0
        return self.layer

    def activate(self) -> None:
        return None


class _Sheet:
    def __init__(self, origin: _Origin) -> None:
        self.origin = origin
        self.columns: dict[int, list[object]] = {}
        self.designations: dict[int, int] = {}
        self.cols = 0

    def from_list(self, column: int, values, **kwargs) -> None:
        self.columns[column] = list(values)
        self.designations[column] = {"X": 4, "Y": 1, "N": 2}.get(kwargs.get("axis"), 0)
        self.cols = max(self.cols, column + 1)

    def to_list(self, column: int):
        return self.columns[column]

    def activate(self) -> None:
        return None

    def lt_range(self, include_sheet: bool) -> str:
        assert include_sheet is False
        return "[DataBook]Sheet1"

    def get_int(self, name: str) -> int:
        column = int(name.removeprefix("col").split(".", 1)[0]) - 1
        return self.designations[column]

    @property
    def obj(self):
        return self

    def __getitem__(self, column: int):
        return _DataColumn(f"{self.origin.book.name}_Sheet1_{column + 1}")


class _DataColumn:
    def __init__(self, dataset_name: str) -> None:
        self.DatasetName = dataset_name


class _Book:
    def __init__(self, origin: _Origin) -> None:
        self.name = "DataBook"
        self.sheet = _Sheet(origin)

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet

    def destroy(self) -> None:
        raise AssertionError("the authoritative data workbook must not be destroyed")


class _Origin:
    def __init__(self) -> None:
        self.graph = _Graph()
        self.book = _Book(self)
        self.template = ""
        self.commands: list[str] = []
        self.color_col_calls: list[tuple[int, str]] = []
        self.k09_colors: list[int] = []
        self.group_edit_mode = 0
        self.member_fill = 0
        self.numeric_vars: dict[str, float] = {}

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs):
        return self.book

    def new_graph(self, name: str, *, template: str, hidden: bool):
        self.graph.name = name
        self.template = template
        return self.graph

    def pages(self, kind: str):
        return [self.book] if kind == "w" else [self.graph]

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        if "plot_gindexed" in command:
            self.graph.layer.add_plot(self.book.sheet, official="plot_gindexed")
            groups = tuple(dict.fromkeys(self.book.sheet.columns[3]))
            self.graph.layer.labels["legend"] = _Label(
                "\n".join(f"\\l(1.{index}) {label}" for index, label in enumerate(groups, 1))
            )
        elif "worksheet -p 213" in command:
            menu_name = command.split("worksheet -p 213 ", 1)[1].split(";", 1)[0]
            for _index in range(1, self.book.sheet.cols):
                self.graph.layer.add_plot(self.book.sheet, official=menu_name)
            stack = self.graph.layer.theme.Children[0]
            stack.Children[0].nVal = 1
            stack.Children[1].nVal = int(menu_name == "StackColP")
            self.graph.layer.labels["legend"] = _Label(
                "\n".join(
                    f"\\l({index}) %({index})" for index in range(self.book.sheet.cols - 1, 0, -1)
                )
            )
        elif "worksheet -p 206" in command:
            menu_name = command.split("worksheet -p 206 ", 1)[1].split(";", 1)[0]
            self.graph.layer.plots.clear()
            self.graph.layer.add_calls.clear()
            for column in range(self.book.sheet.cols):
                self.graph.layer.add_plot(
                    self.book.sheet,
                    coly=column,
                    official=menu_name,
                )
            self.graph.layer.axes["x"].limits = (
                0.5,
                float(self.book.sheet.cols) + 0.5,
                1.0,
            )
        elif command.startswith("legendupdate"):
            self.graph.layer.labels["legend"] = _Label(
                "\n".join(
                    f"\\l({index}) %({index})" for index in range(self.book.sheet.cols - 1, 0, -1)
                )
            )
        elif command.startswith("legendbox"):
            self.graph.layer.labels["legend"] = _Label(
                "\n".join(
                    f"\\l({index}) %({index}, @L)" for index in range(1, self.book.sheet.cols + 1)
                )
            )
        elif command.startswith("dataset __K") and "COLORS" in command:
            payload = command.split("{", 1)[1].split("}", 1)[0]
            self.k09_colors = [int(item.split('"', 2)[1][1:], 16) for item in payload.split(",")]
        elif " -gm 1" in command and " -pfb color" in command:
            self.group_edit_mode = 1
            self.member_fill = int(command.split('color("', 1)[1].split('"', 1)[0][1:], 16)
        elif "set __K14HEAD -gm 1" in command:
            self.group_edit_mode = 1
        elif command.startswith("range __K13OBS"):
            plot_index = int(command.split("]1!", 1)[1].split(";", 1)[0])
            plot = self.graph.layer.plots[plot_index - 1]
            for part in command.split("set ")[1:]:
                statement = part.split(";", 1)[0]
                if " -k " in statement:
                    plot.style_options["-k"] = int(statement.rsplit(" ", 1)[1])
                elif " -z " in statement:
                    plot.style_options["-z"] = float(statement.rsplit(" ", 1)[1])
                elif " -kf " in statement:
                    plot.style_options["-kf"] = int(statement.rsplit(" ", 1)[1])
                elif " -csf " in statement:
                    color = statement.split('color("', 1)[1].split('"', 1)[0]
                    plot.style_options["-csf"] = int(color[1:], 16)
                elif " -cse " in statement:
                    color = statement.split('color("', 1)[1].split('"', 1)[0]
                    plot.style_options["-cse"] = int(color[1:], 16)
        elif command.startswith("range __K13VERIFY"):
            plot_index = int(command.split("]1!", 1)[1].split(";", 1)[0])
            plot = self.graph.layer.plots[plot_index - 1]
            for part in command.split("get ")[1:]:
                tokens = part.split(";", 1)[0].split()
                option, variable = tokens[-2:]
                self.numeric_vars[variable] = float(plot.style_options[option])
        elif command.startswith("layer.plot") and ".symbol.transparency=" in command:
            property_path, raw_value = command.rstrip(";").split("=", 1)
            self.numeric_vars[property_path] = float(raw_value)
        return True

    def lt_float(self, expression: str) -> float:
        if expression.startswith(("__K12COUNT", "__K13COUNT", "__K14COUNT")):
            return float(len(self.graph.layer.plots))
        if expression.startswith(("__K12PT", "__K13PT", "__K14PT")):
            index = int(expression.rsplit("PT", 1)[1])
            return float(self.graph.layer.plots[index - 1].plot_type)
        if expression in self.numeric_vars:
            return self.numeric_vars[expression]
        if expression.startswith("layer.plot") and expression.endswith(".pid"):
            return 203.0 if "plot_gindexed" in self.commands[0] else 213.0
        if expression.startswith("__K") and expression.endswith("ENABLED"):
            return 1.0
        if expression.startswith("__K") and expression.endswith("GROUPMODE"):
            return float(self.group_edit_mode)
        if expression.startswith("__K") and expression.endswith("FILL"):
            return float(self.member_fill)
        if expression.startswith("__K") and "READ[" in expression:
            return float(self.k09_colors[int(expression.split("READ[", 1)[1][:-1]) - 1])
        if expression.startswith('color("'):
            return float(int(expression.split('"', 2)[1][1:], 16))
        if expression.startswith(("__K10COUNT", "__K11COUNT")):
            return float(len(self.graph.layer.plots))
        if expression.startswith(("__K10PT", "__K11PT")):
            return 213.0
        if expression == "__K09COUNT":
            return float(len(self.graph.layer.plots))
        if expression == "__K09PID":
            return 203.0
        raise AssertionError(expression)

    def get_lt_str(self, name: str) -> str:
        if name == "__K09XS":
            return f'[{self.book.name}]Sheet1!A"Index"'
        if name == "__K09YS":
            return f'[{self.book.name}]Sheet1!B"Value"'
        if "XS" in name:
            return f'[{self.book.name}]Sheet1!A"Category"'
        plot_index = int(name.split("YS", 1)[1])
        letter = chr(ord("B") + plot_index - 1)
        return f'[{self.book.name}]Sheet1!{letter}"S{plot_index}"'

    def color_col(self, offset: int, mode: str) -> str:
        self.color_col_calls.append((offset, mode))
        return "#AA3300"


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
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    readback = project.verify(document, split_visual_actions(actions)[0], view)

    if profile_id == "K09":
        assert origin.template == ""
        assert origin.commands[0] == (
            "worksheet -px ? gColumn plot_gindexed iy:=[DataBook]Sheet1!(,B) "
            "group:=[DataBook]Sheet1!(C,D) plottype:=0;"
        )
        assert origin.graph.layer.add_calls == [{"official": "plot_gindexed"}]
        assert origin.graph.layer.group_calls == []
        assert set(origin.book.sheet.columns) == {0, 1, 2, 3}
        assert all(
            label in origin.graph.layer.labels["legend"].text for label in ("S1", "S2", "S3")
        )
    else:
        assert origin.template == ""
        menu_name = "StackColumn" if profile_id == "K10" else "StackColP"
        assert origin.commands[0] == (f"worksheet -s 1 0 4 0; worksheet -p 213 {menu_name};")
        assert (
            "legendupdate dest:=layer update:=reconstruct legend:=separate mode:=lname;"
        ) in origin.commands
        assert origin.graph.layer.add_calls == [{"official": menu_name} for _index in range(1, 4)]
        assert origin.graph.layer.group_calls == []
        assert set(origin.book.sheet.columns) == {0, 1, 2, 3}
    assert origin.graph.layer.labels["legend"].text.count("\\l(") == 3
    native_members = [
        item
        for item in readback.objects
        if item.object_kind.endswith("native_series") or item.object_kind == "k09_native_subset"
    ]
    assert len(native_members) == 3
    if profile_id == "K09":
        assert origin.graph.layer.plots[0].commands == []
        assert origin.color_col_calls == []
        assert origin.k09_colors == []
    else:
        stack = origin.graph.layer.theme.Children[0]
        assert stack.Children[0].nVal == 1
        assert stack.Children[1].nVal == int(profile_id == "K11")
        assert origin.group_edit_mode == 0
        assert origin.color_col_calls == []
    if profile_id == "K11":
        assert origin.book.sheet.columns[1] == [11.0, 21.0]


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


def test_k09_origin_route_explicitly_binds_official_xfunction_and_template() -> None:
    source = inspect.getsource(origin_module)

    assert "plot_gindexed" in source
    assert "worksheet -px ? gColumn plot_gindexed" in source
    assert "plottype:=0" in source
    assert ".new_graph(" not in source
    assert ".add_plot(" not in source


def test_official_stack_renderer_never_consumes_shared_visual_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, actions, view = _case("K10", 3)
    title = SetTitle(
        action_id="action:title-k10",
        target=document.plot_id,
        expected_plot_version=document.plot_version,
        text="K10 representative edit",
    )
    document = document.model_copy(
        update={
            "plot_version": document.plot_version + 1,
            "parent_version": document.plot_version,
            "applied_action_ids": (*document.applied_action_ids, title.action_id),
        }
    )
    monkeypatch.setattr(
        origin_module,
        "resolve_official_template",
        lambda install, selected: tmp_path / selected.filename,
    )
    origin = _Origin()
    project = ColumnFamilyOriginProject(origin, profile_id="K10")
    project.create(tmp_path, document, view)
    structural, visual = split_visual_actions((*actions, title))
    for action in structural:
        project.apply(document, action, view)
    project.verify(document, structural, view)

    assert title in visual
    assert "_ENGINE_TITLE" not in origin.graph.layer.labels


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
    style_arguments: dict[str, object]
    if profile_id == "K12":
        style_arguments = {
            "marker_shape": "diamond",
            "marker_size_pt": 7.0,
            "marker_stroke_color": "#AA3300",
        }
    elif profile_id == "K13":
        style_arguments = {"fill_stroke_color": "#AA3300"}
    else:
        style_arguments = {"line_stroke_color": "#AA3300"}
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
    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()
    readback = backend.readback(document)
    assert len([item for item in readback.objects if item.object_kind == object_kind]) == 3


def test_k14_matplotlib_omits_extrema_edge_lines() -> None:
    document, actions, view = _distribution_case("K14", 2)
    renderer = K14ViolinRenderer()
    distribution = distribution_groups(document, view, profile_id="K14")
    state = renderer._state(document, split_visual_actions(actions)[0], distribution)
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


def test_k13_observation_overlay_is_deterministic_and_preserves_box_geometry() -> None:
    document, actions, view = _distribution_case("K13", 3)
    overlay = SetObservationOverlay(
        action_id="action:k13-observations",
        target="observation_overlay:k13-distribution.raw",
        expected_plot_version=document.plot_version,
        jitter_fraction=0.2,
        marker_shape="triangle_down",
        marker_size_pt=5,
    )
    rendered_document = document.model_copy(
        update={
            "plot_version": document.plot_version + 1,
            "parent_version": document.plot_version,
            "applied_action_ids": (*document.applied_action_ids, overlay.action_id),
        }
    )
    renderer = K13BoxRenderer()
    distribution = distribution_groups(rendered_document, view, profile_id="K13")

    baseline_state = renderer._state(
        document,
        split_visual_actions(actions)[0],
        distribution,
    )
    baseline_figure, baseline_axis = plt.subplots()
    renderer._draw(baseline_axis, distribution, baseline_state)
    baseline_lines = tuple(
        tuple(tuple(float(cell) for cell in row) for row in line.get_xydata())
        for line in baseline_axis.lines
        if line.get_marker() in {None, "None", ""}
    )

    structural, _ = split_visual_actions((*actions, overlay))
    overlay_state = renderer._state(rendered_document, structural, distribution)
    overlay_figure, overlay_axis = plt.subplots()
    renderer._draw(overlay_axis, distribution, overlay_state)
    overlay_lines = tuple(
        tuple(tuple(float(cell) for cell in row) for row in line.get_xydata())
        for line in overlay_axis.lines
        if line.get_marker() in {None, "None", ""}
    )
    assert overlay_lines == baseline_lines
    assert len(overlay_axis.collections) == 3
    for ordinal, collection in enumerate(overlay_axis.collections, start=1):
        offsets = collection.get_offsets()
        assert tuple(float(value) for value in offsets[:, 0]) == pytest.approx(
            regular_observation_positions(ordinal, 6, 0.2)
        )
        assert tuple(float(value) for value in offsets[:, 1]) == distribution.groups[
            ordinal - 1
        ].values
    plt.close(baseline_figure)
    plt.close(overlay_figure)


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
    native_values: dict[tuple[int, int], int | float] = {}

    def configure(_op, _graph, plot_index, native_profile, *, bandwidth=0.0) -> None:
        if native_profile == 13:
            values = {
                BOX_TYPE: 0,
                BOX_RANGE: 2,
                WHISKER_RANGE: 6,
                WHISKER_COEFF: 1.5,
                HAS_OUTLIERS: 1,
            }
        else:
            values = {
                DIST_CURVE_TYPE: 8,
                DIST_CURVE_SCALE: 100,
                DIST_SCALE_TYPE: 1,
                DIST_BANDWIDTH: 255,
                DIST_BANDWIDTH_FACTOR: bandwidth,
                DIST_EXTEND: 0.0,
            }
        native_values.update({(plot_index, theme_id): value for theme_id, value in values.items()})

    def read(_op, _graph, plot_index, theme_id, *, numeric_type):
        return native_values[(1, theme_id)]

    monkeypatch.setattr(distribution_origin_module, "configure_native_distribution", configure)
    monkeypatch.setattr(distribution_origin_module, "read_native_distribution_value", read)
    origin = _Origin()
    project = DistributionOriginProject(origin, profile_id=profile_id)  # type: ignore[arg-type]
    project.create(tmp_path, document, view)
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    readback = project.verify(document, split_visual_actions(actions)[0], view)

    assert origin.template == ""
    menu_name = {"K12": "ColumnScatter", "K13": "Box", "K14": "Violin"}[profile_id]
    assert origin.commands[0] == (f"worksheet -s 1 0 3 0; worksheet -p 206 {menu_name};")
    assert origin.graph.layer.add_calls == [
        {"coly": index, "official": menu_name} for index in range(3)
    ]
    assert (
        len([item for item in readback.objects if item.object_kind.endswith("native_group")]) == 3
    )
    assert "line" not in str(origin.graph.layer.add_calls).lower()
    assert "fill" not in str(origin.graph.layer.add_calls).lower()

    if profile_id == "K12":
        assert native_values == {}
    elif profile_id == "K13":
        assert native_values[(1, BOX_TYPE)] == 0
        assert native_values[(1, BOX_RANGE)] == 2
        assert native_values[(1, WHISKER_RANGE)] == 6
        assert native_values[(1, WHISKER_COEFF)] == pytest.approx(1.5)
        assert native_values[(1, HAS_OUTLIERS)] == 1
    else:
        pooled = tuple(value for start in (11, 21, 31) for value in range(start, start + 6))
        expected_bandwidth = np.std(pooled, ddof=1) * len(pooled) ** (-1 / 5)
        assert native_values[(1, DIST_CURVE_TYPE)] == 8
        assert native_values[(1, DIST_CURVE_SCALE)] == 100
        assert native_values[(1, DIST_SCALE_TYPE)] == 1
        assert native_values[(1, DIST_BANDWIDTH)] == 255
        assert native_values[(1, DIST_BANDWIDTH_FACTOR)] == pytest.approx(expected_bandwidth)
        assert native_values[(1, DIST_EXTEND)] == 0.0
        assert origin.group_edit_mode == 1


def test_k13_origin_overlay_reuses_y_sources_and_persists_deterministic_x(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, actions, view = _distribution_case("K13", 3)
    overlay = SetObservationOverlay(
        action_id="action:k13-origin-observations",
        target="observation_overlay:k13-distribution.raw",
        expected_plot_version=document.plot_version,
        jitter_fraction=0.2,
        marker_shape="triangle_down",
        marker_size_pt=5,
        marker_interior="open",
        marker_fill_color="#F4F4F4",
        marker_stroke_color="#222222",
        marker_opacity=0.75,
    )
    rendered_document = document.model_copy(
        update={
            "plot_version": document.plot_version + 1,
            "parent_version": document.plot_version,
            "applied_action_ids": (*document.applied_action_ids, overlay.action_id),
        }
    )
    monkeypatch.setattr(
        distribution_origin_module,
        "resolve_official_template",
        lambda install, selected: tmp_path / selected.filename,
    )
    native_values = {
        theme_id: value
        for theme_id, value in {
            BOX_TYPE: 0,
            BOX_RANGE: 2,
            WHISKER_RANGE: 6,
            WHISKER_COEFF: 1.5,
            HAS_OUTLIERS: 1,
        }.items()
    }
    monkeypatch.setattr(
        distribution_origin_module,
        "configure_native_distribution",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        distribution_origin_module,
        "read_native_distribution_value",
        lambda _op, _graph, _plot, theme_id, *, numeric_type: native_values[theme_id],
    )
    monkeypatch.setattr(
        distribution_origin_module,
        "set_native_distribution_outliers",
        lambda _op, _graph, _plot, *, visible: native_values.__setitem__(
            HAS_OUTLIERS, int(visible)
        ),
    )
    origin = _Origin()
    project = DistributionOriginProject(origin, profile_id="K13")
    project.create(tmp_path, rendered_document, view)
    structural, _ = split_visual_actions((*actions, overlay))
    for action in structural:
        project.apply(rendered_document, action, view)
    # Reapplying the same complete state must update, not duplicate, native plots.
    project.apply(rendered_document, overlay, view)
    readback = project.verify(rendered_document, structural, view)

    assert [plot.plot_type for plot in origin.graph.layer.plots] == [
        206,
        206,
        206,
        201,
        201,
        201,
    ]
    assert len(origin.graph.layer.plots) == 6
    assert native_values[HAS_OUTLIERS] == 0
    assert tuple(origin.book.sheet.to_list(3)) == pytest.approx(
        regular_observation_positions(1, 6, 0.2)
    )
    assert tuple(origin.book.sheet.to_list(4)) == pytest.approx(
        regular_observation_positions(2, 6, 0.2)
    )
    assert tuple(origin.book.sheet.to_list(5)) == pytest.approx(
        regular_observation_positions(3, 6, 0.2)
    )
    assert [
        plot.DatasetName for plot in origin.graph.layer.plots[3:]
    ] == [plot.DatasetName for plot in origin.graph.layer.plots[:3]]
    assert any(
        item.semantic_id == "observation_overlay:k13-distribution.raw"
        and item.object_kind == "observation_overlay"
        for item in readback.objects
    )


def test_k14_matplotlib_writes_the_same_shared_absolute_bandwidth_contract() -> None:
    document, actions, view = _distribution_case("K14", 3)
    renderer = K14ViolinRenderer()
    distribution = distribution_groups(document, view, profile_id="K14")
    state = renderer._state(document, split_visual_actions(actions)[0], distribution)
    figure, axis = plt.subplots()
    original = axis.violinplot
    calls: list[dict[str, object]] = []

    def capture(*args, **kwargs):
        calls.append(dict(kwargs))
        return original(*args, **kwargs)

    axis.violinplot = capture  # type: ignore[method-assign]
    renderer._draw(axis, distribution, state)
    plt.close(figure)

    assert len(calls) == 3
    pooled = tuple(value for group in distribution.groups for value in group.values)
    shared_bandwidth = np.std(pooled, ddof=1) * len(pooled) ** (-1 / 5)
    for call, group in zip(calls, distribution.groups, strict=True):
        expected_factor = shared_bandwidth / np.std(group.values, ddof=1)
        assert call["bw_method"] == pytest.approx(expected_factor)
        assert call["points"] == 256
        assert call["showextrema"] is False
