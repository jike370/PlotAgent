from __future__ import annotations

import inspect
import re
import warnings
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
    SetAxis,
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
from plotagent.engine.visual_t1 import split_visual_actions

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
        arguments: dict[str, object]
        if profile_id == "X05":
            arguments = {
                "marker_shape": "diamond",
                "marker_size_pt": 6.0,
                "marker_stroke_color": color,
            }
        elif profile_id == "X13":
            arguments = {"fill_color": color}
        else:
            arguments = {"line_stroke_color": color, "line_width_pt": 1.2}
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
    styles: list[tuple[str, str]] = []
    if middle:
        roles.append("middle")
        columns.append(("field:middle", "Middle", "numeric", (2.0, 3.0, 2.5)))
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


def test_x09_preserves_rows_and_ordered_boundaries_without_sorting() -> None:
    document, _actions, view = _x09_case()
    intervals = x09_floating_intervals(document, view)
    assert intervals.categories == ("C", "A", "B")
    assert intervals.middle_values == (2.0, 3.0, 2.5)
    descending = view.model_copy(
        update={
            "columns": tuple(
                column.model_copy(update={"values": (0.5, 4.5, 2.5)})
                if column.field.field_id == "field:middle"
                else column
                for column in view.columns
            )
        }
    )
    observed = x09_floating_intervals(document, descending)
    assert observed.start_values == (1.0, 2.0, 1.5)
    assert observed.middle_values == (0.5, 4.5, 2.5)
    assert observed.end_values == (3.0, 4.0, 3.5)


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
        (X09FloatingIntervalRenderer(), _x09_case, "floating_column_group", 1),
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

    def set_float(self, name: str, value: float) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)

    def get_float(self, name: str) -> float:
        return float(self.values.get(name, 0.0))


class _Axis:
    def __init__(self) -> None:
        self.scale = "linear"
        self.limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin, end, step=1.0) -> None:
        self.limits = (float(begin), float(end), float(step))


class _Plot:
    def __init__(self, dataset_name: str = "D_B") -> None:
        self.obj = self
        self.DatasetName = dataset_name
        self._color = (22, 118, 210)
        self.floats = {"line.width": 0.8}
        self.values = {"type": 206, "show": 1}
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

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)


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
        if _x is not None:
            label.values["x1"] = float(_x)
        if _y is not None:
            label.values["y1"] = float(_y)
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

    def activate(self) -> None:
        return None


class _Sheet:
    def __init__(self) -> None:
        self.obj = self
        self.columns: dict[int, list[object]] = {}
        self.designations: dict[int, int] = {}
        self.activated = False

    def __getitem__(self, index: int):
        return index

    def from_list(self, column: int, values, **kwargs) -> None:
        self.columns[column] = list(values)
        if "axis" in kwargs:
            self.designations[column] = {"X": 4, "Y": 1}.get(kwargs["axis"], 2)

    def to_list(self, column: int):
        return self.columns[column]

    def get_int(self, expression: str) -> int:
        index = int(expression.removeprefix("col").removesuffix(".type")) - 1
        return self.designations[index]

    def activate(self) -> None:
        self.activated = True


class _Book:
    def __init__(self) -> None:
        self.name = "D"
        self.sheet = _Sheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet

    def destroy(self) -> None:
        raise AssertionError("authoritative workbook must not be destroyed")


class _Origin:
    def __init__(self) -> None:
        self.book = _Book()
        self.graph: _Graph | None = None
        self.template = ""
        self.ranges: list[tuple[object, ...]] = []
        self.commands: list[str] = []
        self.active_layer = 1
        self.x13_styles = {
            1: {"color": 0, "width": 1.0},
            2: {"color": 0, "width": 1.0},
        }
        self.x13_plot_ids = {1: 203.0, 2: 203.0}
        self.x13_exchange_xy = {1: 1.0, 2: 1.0}
        self.x13_links = {"target": 1.0, "x": 1.0, "y": 2.0}
        self.x13_offsets = {
            1: {"SX": 0.0, "SXS": 1.0, "SY": 0.0, "SYS": 1.0},
            2: {"SX": 0.0, "SXS": 1.0, "SY": 0.0, "SYS": 1.0},
        }
        self.x13_source_columns = {1: {"X": "A", "Y": "B"}, 2: {"X": "A", "Y": "C"}}

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

    def pages(self, kind: str):
        if kind == "w":
            return [self.book]
        return [] if self.graph is None else [self.graph]

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        active = re.search(r"page\.active=(\d+)", command)
        if active:
            self.active_layer = int(active.group(1))
        if "run.section(plot,PopulationPyramid)" in command:
            self.graph = _Graph(2)
            self.graph[0].plots = [_Plot(f"{self.book.name}_B")]
            self.graph[1].plots = [_Plot(f"{self.book.name}_C")]
        elif "Beeswarm" in command:
            self.graph = _Graph(1)
            self.graph[0].plots = [_Plot() for _index in range(len(self.book.sheet.columns))]
        elif command.startswith("legendbox"):
            assert self.graph is not None
            self.graph[0].labels["legend"] = _Label("data symbols")
        category = re.search(r"-n (X13C\d{4}) CategoryPlaceholder", command)
        if category:
            assert self.graph is not None
            label = _Label("CategoryPlaceholder")
            label.name = category.group(1)
            self.graph[0].labels[category.group(1)] = label
        color = re.search(r'set %C -pfb color\("(#[0-9A-Fa-f]{6})"\)', command)
        if color:
            self.x13_styles[self.active_layer]["color"] = int(color.group(1)[1:], 16)
        width = re.search(r"set %C -pbw ([0-9.]+)", command)
        if width:
            self.x13_styles[self.active_layer]["width"] = float(width.group(1))
        return True

    def lt_float(self, expression: str) -> float:
        color = re.fullmatch(r'color\("(#[0-9A-Fa-f]{6})"\)', expression)
        if color:
            return float(int(color.group(1)[1:], 16))
        assert self.graph is not None
        if expression == "__X05COUNT":
            return float(len(self.graph[0].plots))
        if expression.startswith("__X05PT"):
            return 206.0
        native = re.fullmatch(r"__X13([12])(PT|SX|SXS|SY|SYS)", expression)
        if native:
            if native.group(2) == "PT":
                return self.x13_plot_ids[int(native.group(1))]
            return self.x13_offsets[int(native.group(1))][native.group(2)]
        exchange = re.fullmatch(r"__X13EX([12])", expression)
        if exchange:
            return self.x13_exchange_xy[int(exchange.group(1))]
        if expression in {"__X13LINK", "__X13XLINK", "__X13YLINK"}:
            return self.x13_links[
                {"__X13LINK": "target", "__X13XLINK": "x", "__X13YLINK": "y"}[expression]
            ]
        style = re.fullmatch(r"__X13STYLE([12])([CW])", expression)
        if style:
            key = "color" if style.group(2) == "C" else "width"
            return float(self.x13_styles[int(style.group(1))][key])
        return 0.0

    def get_lt_str(self, expression: str) -> str:
        source = re.fullmatch(r"__X13([12])([XY])S", expression)
        assert source is not None
        column = self.x13_source_columns[int(source.group(1))][source.group(2)]
        return f'[{self.book.name}]Sheet1!{column}"'


def test_x05_origin_binds_dynamic_groups_to_official_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, actions, view = _x05_case(3)
    resolved: list[str] = []

    def _resolve(_install, profile):
        resolved.append(profile.filename)
        return tmp_path / profile.filename

    monkeypatch.setattr(
        distribution_origin,
        "resolve_official_template",
        _resolve,
    )
    origin = _Origin()
    project = DistributionOriginProject(origin, profile_id="X05")
    project.create(tmp_path, document, view)
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    readback = project.verify(document, split_visual_actions(actions)[0], view)
    assert resolved == [X05_ORIGIN_PROFILE.filename]
    assert origin.commands[0] == "worksheet -s 1 0 3 0; worksheet -p 206 Beeswarm;"
    assert sum("layer -c" in command for command in origin.commands) == 2
    assert sum("get __X05P -pt" in command for command in origin.commands) == 6
    assert sum(command.startswith("legendbox") for command in origin.commands) == 1
    assert origin.graph is not None
    assert origin.graph[0].add_calls == []
    assert [plot.get_int("type") for plot in origin.graph[0].plots] == [206, 206, 206]
    assert (
        len([item for item in readback.objects if item.object_kind.endswith("native_group")]) == 3
    )


def test_x09_origin_uses_one_official_floatcol_command_without_generic_rebuild() -> None:
    source = inspect.getsource(x09_origin)
    matplotlib_source = inspect.getsource(X09FloatingIntervalRenderer)

    assert "worksheet -p 207 FloatCol" in source
    assert "set __X09P -gm 1" not in source
    assert "FloatBar" not in source
    assert ".new_graph(" not in source
    assert ".AddPlot(" not in source
    assert ".add_plot(" not in source
    assert ".plot_list(" not in source
    assert ".bar(" in matplotlib_source
    assert ".barh(" not in matplotlib_source


def test_x09_without_middle_writes_only_category_start_and_end() -> None:
    document, _actions, view = _x09_case(middle=False)
    intervals = x09_floating_intervals(document, view)
    project = X09OriginProject(None)
    project.sheet = _Sheet()

    project._write(intervals)

    assert project.sheet.columns == {
        0: ["C", "A", "B"],
        1: [1.0, 2.0, 1.5],
        2: [3.0, 4.0, 3.5],
    }


def test_x09_rebuilds_legend_from_visible_intervals_after_official_creation() -> None:
    source = inspect.getsource(X09OriginProject.create)

    assert '"native_legend_rebuild"' in source
    assert "self._set_legend(intervals, True)" in source


def test_x09_axis_edits_are_routed_only_to_the_shared_visual_adapter() -> None:
    action = SetAxis(
        action_id="action:x09-vertical-value-axis",
        target="axis:x09-native.y",
        expected_plot_version=1,
        label="Interval value",
        scale="log10",
        minimum=0.1,
        maximum=10.0,
    )

    structural, visual = split_visual_actions((action,))

    assert structural == ()
    assert visual == (action,)


def test_x09_matplotlib_selects_a_font_covering_visible_cjk(tmp_path: Path) -> None:
    document, actions, view = _x09_case()
    names = {
        "field:category": "样本",
        "field:start": "起点",
        "field:end": "终点",
        "field:middle": "中间边界",
    }
    cjk_view = view.model_copy(
        update={
            "columns": tuple(
                column.model_copy(
                    update={
                        "field": column.field.model_copy(
                            update={"name": names[column.field.field_id]}
                        ),
                        "values": (
                            ("样本甲", "样本乙", "样本丙")
                            if column.field.field_id == "field:category"
                            else column.values
                        ),
                    }
                )
                for column in view.columns
            )
        }
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        X09FloatingIntervalRenderer().render(
            document,
            split_visual_actions(actions)[0],
            cjk_view,
            tmp_path / "x09-cjk.png",
            tmp_path / "x09-cjk.svg",
        )

    assert not [warning for warning in caught if "Glyph" in str(warning.message)]


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
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    readback = project.verify(document, split_visual_actions(actions)[0], view)
    assert any("run.section(plot,PopulationPyramid)" in command for command in origin.commands)
    assert origin.graph is not None
    assert [layer.add_calls for layer in origin.graph] == [[], []]
    assert (
        len([item for item in readback.objects if item.object_kind == "native_population_column"])
        == 2
    )


def test_x13_origin_uses_official_column_exchange_section_without_bar_rebuild() -> None:
    source = inspect.getsource(x13_origin)

    assert "run.section(plot,PopulationPyramid)" in source
    assert "_COLUMN = 203" in source
    assert "layer.exchangexy" in source
    assert ".add_plot(" not in inspect.getsource(X13OriginProject)
    assert "215" not in inspect.getsource(X13OriginProject)


@pytest.mark.parametrize(
    ("plot_ids", "exchange_xy", "message"),
    (
        ({1: 215.0, 2: 203.0}, {1: 1.0, 2: 1.0}, "ordinary Column PID 203"),
        ({1: 203.0, 2: 203.0}, {1: 0.0, 2: 1.0}, "lost PopulationPyramid ExchangeXY"),
    ),
)
def test_x13_rejects_bar_or_non_exchanged_template_structure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plot_ids: dict[int, float],
    exchange_xy: dict[int, float],
    message: str,
) -> None:
    document, _actions, view = _x13_case()
    monkeypatch.setattr(
        x13_origin,
        "resolve_official_template",
        lambda _install, profile: tmp_path / profile.filename,
    )
    origin = _Origin()
    origin.x13_plot_ids = plot_ids
    origin.x13_exchange_xy = exchange_xy

    with pytest.raises(RuntimeError, match=message):
        X13OriginProject(origin).create(tmp_path, document, view)


def test_x13_uses_only_stable_labtalk_structure_readback() -> None:
    source = inspect.getsource(X13OriginProject._assert_native_structure)

    assert "get %C -pt" in source
    assert "range -wx" in source and "range -wy" in source
    assert "layer.exchangexy" in source
    assert "layer.link" in source and "layer.x.link" in source and "layer.y.link" in source
    assert all(switch in source for switch in ("-sx", "-sxs", "-sy", "-sys"))
    assert "plot.obj.DatasetName" in source
    assert "OriginExt" not in source and "Theme" not in source


@pytest.mark.parametrize(
    ("mutator", "message"),
    (
        (lambda origin: origin.x13_source_columns[2].update(Y="B"), "lost source C"),
        (lambda origin: origin.x13_links.update(target=0.0), "parent/axis link signature"),
        (lambda origin: origin.x13_offsets[1].update(SY=2.0), "non-native plot offset/scale"),
    ),
)
def test_x13_fresh_gate_rejects_source_link_or_offset_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutator,
    message: str,
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
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    mutator(origin)

    with pytest.raises(RuntimeError, match=message):
        project.verify(document, split_visual_actions(actions)[0], view)


def test_x13_structural_gate_does_not_depend_on_a_visual_legend(
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
    for action in split_visual_actions(actions)[0]:
        project.apply(document, action, view)
    assert origin.graph is not None
    assert "legend" not in origin.graph[0].labels
    project.verify(document, split_visual_actions(actions)[0], view)


def test_profiles_publish_only_shared_agent_actions_and_pinned_templates() -> None:
    assert X05_BEESWARM_PROFILE.required_roles == ("value",)
    assert X09_FLOATING_INTERVAL_PROFILE.optional_roles == ("middle",)
    assert X13_POPULATION_PYRAMID_PROFILE.required_roles == ("category", "left", "right")
    assert X05_ORIGIN_PROFILE.sha256.startswith("301dd6c8c293")
    assert X09_ORIGIN_PROFILE.filename == "FloatCol.otp"
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
