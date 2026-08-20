from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.dual_y_special as dual_origin
import plotagent.engine.backends.origin.x24 as x24_origin
import plotagent.engine.backends.origin.x38 as x38_origin
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
    X24ParetoRenderer,
    X35DualYColumnRenderer,
    X36DualYColumnLineRenderer,
    X38OffsetStackRenderer,
)
from plotagent.engine.backends.origin import (
    X24_ORIGIN_PROFILE,
    X35_ORIGIN_PROFILE,
    X36_ORIGIN_PROFILE,
    X38_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.dual_y_special import DualYSpecialOriginProject
from plotagent.engine.backends.origin.x24 import X24OriginProject
from plotagent.engine.backends.origin.x38 import X38OriginProject
from plotagent.engine.profile_data import (
    x24_pareto,
    x24_pareto_source,
    x35_series,
    x36_series,
    x38_offset_stack,
)
from plotagent.engine.profiles import (
    X24_PARETO_PROFILE,
    X35_DUAL_Y_COLUMN_PROFILE,
    X36_DUAL_Y_COLUMN_LINE_PROFILE,
    X38_OFFSET_STACK_PROFILE,
)
from plotagent.engine.visual_t1 import split_visual_actions

HASH = "8" * 64


def _case(
    profile_id: str,
    roles: tuple[str, ...],
    columns: tuple[tuple[str, str, str, tuple[object, ...]], ...],
    *,
    styles: tuple[tuple[str, dict[str, object]], ...] = (),
):
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{profile_id.lower()}",
        version=1,
        content_hash=HASH,
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=field_id)
        for role, (field_id, _name, _type, _values) in zip(roles, columns, strict=True)
    )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-t1",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    actions: list[PlotEngineAction] = [create]
    for target, arguments in styles:
        actions.append(
            SetSeriesStyle(
                action_id=f"action:style-{profile_id.lower()}-{len(actions)}",
                target=f"series:{profile_id.lower()}-t1.{target}",
                expected_plot_version=len(actions),
                **arguments,
            )
        )
    actions.append(
        SetLegend(
            action_id=f"action:legend-{profile_id.lower()}",
            target=f"legend:{profile_id.lower()}-t1.main",
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
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(len(columns[0][3]))),
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


def _x24_case():
    return _case(
        "X24",
        ("category", "value"),
        (
            ("field:category", "Cause", "categorical", ("A", "B", "A", "D")),
            ("field:value", "Count", "numeric", (5.0, 20.0, 10.0, 0.0)),
        ),
        styles=(
            ("bars", {"line_stroke_color": "#2255AA", "line_width_pt": 1.1}),
            (
                "cumulative",
                {
                    "line_stroke_color": "#CC6600",
                    "line_width_pt": 1.8,
                    "line_style": "dash",
                },
            ),
        ),
    )


def _dual_case(profile_id: str):
    right_style: dict[str, object] = {
        "line_stroke_color": "#CC6600",
        "line_width_pt": 1.5,
    }
    if profile_id == "X36":
        right_style.update(line_style="dash", marker_shape="diamond", marker_size_pt=6.0)
    return _case(
        profile_id,
        ("category", "left", "right"),
        (
            ("field:category", "Month", "categorical", ("Jan", "Feb", "Mar")),
            ("field:left", "Rain", "numeric", (12.0, 18.0, 9.0)),
            ("field:right", "Temperature", "numeric", (3.0, 7.0, 11.0)),
        ),
        styles=(
            ("left", {"line_stroke_color": "#2255AA", "line_width_pt": 1.0}),
            ("right", right_style),
        ),
    )


def _x38_case(group_count: int = 3):
    x_values = tuple(float(x) for x in range(1, 5))
    roles = ("x",) + tuple(f"series_{index + 1}" for index in range(group_count))
    columns = (("field:x", "Energy", "numeric", x_values),) + tuple(
        (
            f"field:series-{index + 1}",
            f"Spectrum {index + 1}",
            "numeric",
            tuple(float(index * 10 + x) for x in range(1, 5)),
        )
        for index in range(group_count)
    )
    return _case(
        "X38",
        roles,
        columns,
        styles=(),
    )


def test_profile_data_preserves_authoritative_semantics() -> None:
    document, _actions, view = _x24_case()
    source = x24_pareto_source(document, view)
    assert source.categories == ("A", "B", "A", "D")
    assert source.values == (5.0, 20.0, 10.0, 0.0)
    pareto = x24_pareto(document, view)
    assert pareto.categories == ("B", "A", "D")
    assert pareto.values == (20.0, 15.0, 0.0)
    assert pareto.cumulative_percent[-1] == pytest.approx(100.0)

    for profile_id, normalizer in (("X35", x35_series), ("X36", x36_series)):
        document, _actions, view = _dual_case(profile_id)
        dual = normalizer(document, view)
        assert dual.x_labels == ("Jan", "Feb", "Mar")
        assert dual.left_values == (12.0, 18.0, 9.0)


@pytest.mark.parametrize("group_count", (1, 3, 5))
def test_x38_preserves_raw_aligned_series(group_count: int) -> None:
    document, _actions, view = _x38_case(group_count)
    offset = x38_offset_stack(document, view)
    assert len(offset.series) == group_count
    assert all(series.x_values == (1.0, 2.0, 3.0, 4.0) for series in offset.series)
    assert offset.series[-1].y_values[-1] == float((group_count - 1) * 10 + 4)


@pytest.mark.parametrize(
    ("renderer", "case", "kind", "count"),
    (
        (X24ParetoRenderer(), _x24_case, "pareto_cumulative_series", 1),
        (X35DualYColumnRenderer(), lambda: _dual_case("X35"), "dual_y_column_series", 2),
        (X36DualYColumnLineRenderer(), lambda: _dual_case("X36"), "dual_y_line_series", 1),
        (X38OffsetStackRenderer(), _x38_case, "offset_line_series", 3),
    ),
)
def test_independent_matplotlib_renderers_emit_semantic_objects(
    tmp_path: Path, renderer, case, kind: str, count: int
) -> None:
    document, actions, view = case()
    backend = MatplotlibBackend(tmp_path / renderer.profile_id, (renderer,))
    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()
    readback = backend.readback(document)
    assert len([item for item in readback.objects if item.object_kind == kind]) == count
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
        self.ints = {"show": 1}
        self.floats: dict[str, float] = {}

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats.get(name, 0.0)


class _Axis:
    def __init__(self) -> None:
        self.scale = "linear"
        self.limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin=None, end=None, step=None) -> None:
        self.limits = (
            float(self.limits[0] if begin is None else begin),
            float(self.limits[1] if end is None else end),
            float(self.limits[2] if step is None else step),
        )


class _Plot:
    def __init__(self, native_type: object, dataset_name: str = "") -> None:
        self.obj = self
        self.DatasetName = dataset_name
        self.native_type = native_type
        self.ints = {"show": 1, "line.style": 0}
        self.floats = {"line.width": 1.0}
        self.color = (0, 0, 0)
        self.symbol_kind = 1
        self.symbol_size = 5.0

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats[name]


class _Layer:
    def __init__(self, origin=None, index: int = 0, *, right: bool = False, pid: int = 0) -> None:
        self.obj = self
        self.origin = origin
        self.index = index
        self.pid = pid
        self.labels = {"xb": _Label("X"), "yl": _Label("Y")}
        if right:
            self.labels["yr"] = _Label("Y2")
        self.axes = {"x": _Axis(), "y": _Axis()}
        if right:
            self.axes["y"].limits = (0.0, 110.0, 20.0)
        self.plots: list[_Plot] = []
        self.ints: dict[str, int] = {}
        self.floats: dict[str, float] = {}
        self.strings: dict[str, str] = {}

    def add_plot(self, sheet, *, coly, colx, type):
        plot = _Plot(type)
        self.plots.append(plot)
        return plot

    def plot_list(self):
        return self.plots

    def rescale(self) -> None:
        return None

    def axis(self, name: str):
        return self.axes[name]

    def label(self, name: str):
        return self.labels.get(name) or next(
            (item for item in self.labels.values() if item.name == name), None
        )

    def add_label(self, text: str, x=None, y=None):
        label = _Label(text)
        self.labels[f"new-{len(self.labels)}"] = label
        return label

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats.get(name, 0.0)

    def set_str(self, name: str, value: str) -> None:
        self.strings[name] = value

    def activate(self) -> None:
        if self.origin is not None:
            self.origin.active_layer = self.index

    def LT_execute(self, command: str) -> bool:
        if command == "legend":
            self.labels["legend"] = _Label()
        elif "_ENGINE_TITLE" in command:
            title = _Label()
            title.name = "_ENGINE_TITLE"
            self.labels["_ENGINE_TITLE"] = title
        else:
            raise AssertionError(command)
        return True


class _Graph:
    def __init__(self, layer_count: int, origin=None, pids: tuple[int, ...] = ()) -> None:
        self.name = "Gspecial"
        self.lname = ""
        self.layers = tuple(
            _Layer(
                origin,
                index,
                right=index == 1,
                pid=pids[index] if index < len(pids) else 0,
            )
            for index in range(layer_count)
        )

    def __iter__(self):
        return iter(self.layers)

    def __getitem__(self, index: int):
        return self.layers[index]

    def activate(self) -> None:
        return None


class _Sheet:
    def __init__(self, name: str = "Sheet1") -> None:
        self.name = name
        self.columns: dict[int, list[object]] = {}
        self.column_options: dict[int, dict[str, object]] = {}
        self.properties = {
            "col1.categorical.type": 0,
            "col1.categorical.sort": 0,
        }
        self.cols = 0

    def from_list(self, index, values, **kwargs) -> None:
        self.columns[index] = list(values)
        self.column_options[index] = dict(kwargs)
        self.cols = max(self.cols, index + 1)

    def to_list(self, index):
        return self.columns[index]

    @property
    def rows(self) -> int:
        return max((len(values) for values in self.columns.values()), default=0)

    def activate(self) -> None:
        return None

    def lt_exec(self, command: str) -> None:
        if "wks.col1.categorical.type=2" in command:
            self.properties["col1.categorical.type"] = 2
        if "wks.col1.categorical.sort=0" in command:
            self.properties["col1.categorical.sort"] = 0

    def set_int(self, expression: str, value: int) -> None:
        self.properties[expression] = value

    def get_int(self, expression: str) -> int:
        return int(self.properties.get(expression, 0))

    def lt_range(self, _include_sheet: bool) -> str:
        return "[DX24]Sheet1"


class _Book:
    def __init__(self) -> None:
        self.name = "DX24"
        self.sheets = [_Sheet()]

    def __getitem__(self, index: int):
        return self.sheets[index]

    def __iter__(self):
        return iter(self.sheets)

    def destroy(self) -> None:
        return None


class _Origin:
    def __init__(self) -> None:
        self.book = _Book()
        self.graph = _Graph(1, self)
        self.active_layer = 0
        self.commands: list[str] = []

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, kind, name, *, hidden):
        self.book = _Book()
        self.book.name = name
        return self.book

    def new_graph(self, name, *, template, hidden):
        layer_count = 1 if "offsetstacky" in template.lower() else 2
        self.graph = _Graph(layer_count, self)
        self.graph.name = name
        return self.graph

    def pages(self, kind: str):
        return [self.book] if kind == "w" else [self.graph]

    def lt_exec(self, command: str) -> None:
        self.commands.append(command)
        if "!page.active=" in command:
            active = command.rsplit("!page.active=", 1)[1].split(";", 1)[0]
            self.active_layer = int(active) - 1
        elif command.startswith("plot_paretobin "):
            source = self.book[0]
            totals: dict[str, float] = {}
            for label, value in zip(source.columns[0], source.columns[1], strict=True):
                totals[str(label)] = totals.get(str(label), 0.0) + float(value)
            ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
            total = sum(value for _label, value in ordered)
            running = 0.0
            report = _Sheet("ParetoBin1")
            report.from_list(0, [label for label, _value in ordered])
            report.from_list(1, [value for _label, value in ordered])
            cumulative: list[float] = []
            for _label, value in ordered:
                running += value
                cumulative.append(running / total * 100.0)
            report.from_list(2, cumulative)
            self.book.sheets.append(report)
            self.graph = _Graph(2, self, (203, 202))
        elif "run.section(plot,2YsCol)" in command:
            self.graph = _Graph(2, self, (203, 203))
            self.graph.layers[0].plots = [_Plot(203, f"{self.book.name}_B")]
            self.graph.layers[1].plots = [_Plot(203, f"{self.book.name}_C")]
        elif "run.section(plot,2YsColSymb)" in command:
            self.graph = _Graph(2, self, (203, 202))
            self.graph.layers[0].plots = [_Plot(203, f"{self.book.name}_B")]
            self.graph.layers[1].plots = [_Plot(202, f"{self.book.name}_C")]
        elif "run.section(plot,OffsetYs)" in command:
            self.graph = _Graph(1, self, (200,))
            self.graph.layers[0].plots = [
                _Plot(200, f"{self.book.name}_{chr(66 + index)}")
                for index in range(self.book[0].cols - 1)
            ]

    def lt_float(self, expression: str) -> float:
        if expression == "layer.plot1.pid":
            return float(self.graph.layers[self.active_layer].pid)
        if expression.startswith(("__X35PT", "__X36PT")):
            return float(self.graph.layers[self.active_layer].pid)
        if expression.endswith("CATTYPE"):
            return float(self.book[0].properties["col1.categorical.type"])
        if expression.endswith("CATSORT"):
            return float(self.book[0].properties["col1.categorical.sort"])
        if expression.startswith("__X38P") and expression.endswith("PT"):
            return 200.0
        if expression.startswith('color("'):
            return 42.0
        if "SYS" in expression:
            return 1.0
        if "SY" in expression:
            return 0.0
        return 0.0


def test_origin_x24_delegates_sort_merge_and_cumulative_to_paretobin(monkeypatch) -> None:
    monkeypatch.setattr(
        x24_origin, "resolve_official_template", lambda *_args: Path("ParetoBin.otpu")
    )
    document, actions, view = _x24_case()
    origin = _Origin()
    project = X24OriginProject(origin)
    project.create(Path("."), document, view)
    project.reconcile(document, split_visual_actions(actions)[0], view)
    assert project.source_sheet.columns[0] == ["A", "B", "A", "D"]
    assert project.report_sheet.columns[0] == ["B", "A", "D"]
    assert project.report_sheet.columns[1] == [20.0, 15.0, 0.0]
    assert project.report_sheet.columns[2][-1] == pytest.approx(100.0)
    assert any(command.startswith("plot_paretobin ") for command in origin.commands)
    assert all("plot_paretoraw" not in command for command in origin.commands)
    assert [layer.pid for layer in project._layers()] == [203, 202]


@pytest.mark.parametrize(("profile_id", "types"), (("X35", (203, 203)), ("X36", (203, 202))))
def test_origin_dual_y_special_uses_both_official_layers(
    monkeypatch, profile_id: str, types
) -> None:
    monkeypatch.setattr(
        dual_origin, "resolve_official_template", lambda *_args: Path(f"{profile_id}.otpu")
    )
    document, actions, view = _dual_case(profile_id)
    origin = _Origin()
    project = DualYSpecialOriginProject(origin, profile_id=profile_id)  # type: ignore[arg-type]
    project.create(Path("."), document, view)
    project.reconcile(document, split_visual_actions(actions)[0], view)
    assert tuple(plot.native_type for plot in project._plots()) == types
    assert project.sheet.columns[0] == ["Jan", "Feb", "Mar"]
    assert project.sheet.properties["col1.categorical.type"] == 2
    assert project.sheet.properties["col1.categorical.sort"] == 0
    assert any(command == "doc -u;" for command in origin.commands)
    assert not any("!page.active=1; set %C -pfb" in command for command in origin.commands)


def test_origin_x35_rejects_automatic_axis_that_makes_right_column_float(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        dual_origin, "resolve_official_template", lambda *_args: Path("2Ys_Col.otpu")
    )
    document, actions, view = _dual_case("X35")
    origin = _Origin()
    project = DualYSpecialOriginProject(origin, profile_id="X35")
    project.create(Path("."), document, view)
    project.reconcile(document, split_visual_actions(actions)[0], view)
    origin.graph.layers[1].axes["y"].limits = (4.0, 12.0, 2.0)
    state = project._state(
        document, split_visual_actions(actions)[0], project._data(document, view)
    )
    with pytest.raises(RuntimeError, match="ordinary column cannot appear floating"):
        project._assert_default_column_baselines(state)


def test_origin_dual_y_save_refuses_stale_probe_artifact(tmp_path: Path) -> None:
    target = tmp_path / "plot.opju"
    target.write_bytes(b"stale")
    project = DualYSpecialOriginProject(_Origin(), profile_id="X35")  # type: ignore[arg-type]
    with pytest.raises(FileExistsError, match="refuses to overwrite"):
        project.save(target)


@pytest.mark.parametrize("group_count", (1, 3, 5))
def test_origin_x38_keeps_raw_y_and_creates_dynamic_template_plots(
    monkeypatch, group_count: int
) -> None:
    monkeypatch.setattr(
        x38_origin, "resolve_official_template", lambda *_args: Path("OffsetStackY.otp")
    )
    document, actions, view = _x38_case(group_count)
    origin = _Origin()
    project = X38OriginProject(origin)
    project.create(Path("."), document, view)
    project.reconcile(document, split_visual_actions(actions)[0], view)
    offset = x38_offset_stack(document, view)
    assert len(project.plots) == group_count
    for index, series in enumerate(offset.series, start=1):
        assert project.sheet.columns[index] == list(series.y_values)
    assert any("run.section(plot,OffsetYs)" in command for command in origin.commands)
    assert not any(" -gm " in command for command in origin.commands)


def test_origin_x38_default_preserves_official_template_styling(monkeypatch) -> None:
    monkeypatch.setattr(
        x38_origin, "resolve_official_template", lambda *_args: Path("OffsetStackY.otp")
    )
    document, actions, view = _x38_case()
    create = actions[0]
    document = document.model_copy(
        update={
            "plot_version": 1,
            "parent_version": None,
            "applied_action_ids": (create.action_id,),
        }
    )
    origin = _Origin()
    project = X38OriginProject(origin)
    project.create(Path("."), document, view)
    project.reconcile(document, (create,), view)
    assert not any(" -gm " in command for command in origin.commands)
    assert not any(" -wp " in command for command in origin.commands)
    assert not any("_ENGINE_TITLE" in command for command in origin.commands)


def test_origin_x38_save_refuses_stale_probe_artifact(tmp_path: Path) -> None:
    target = tmp_path / "plot.opju"
    target.write_bytes(b"stale")
    project = X38OriginProject(_Origin())
    with pytest.raises(FileExistsError, match="refuses to overwrite"):
        project.save(target)


def test_x38_series_width_is_routed_only_to_the_shared_visual_adapter() -> None:
    document, actions, view = _x38_case()
    width = SetSeriesStyle(
        action_id="action:x38-unsupported-width",
        target="series:x38-t1.group_1",
        expected_plot_version=1,
        line_width_pt=2.0,
    )
    structural, visual = split_visual_actions((actions[0], width))

    assert structural == (actions[0],)
    assert visual == (width,)


def test_remaining_t1_profiles_pin_official_templates_and_public_actions() -> None:
    profiles = {
        profile.profile_id: profile
        for profile in (
            X24_PARETO_PROFILE,
            X35_DUAL_Y_COLUMN_PROFILE,
            X36_DUAL_Y_COLUMN_LINE_PROFILE,
            X38_OFFSET_STACK_PROFILE,
        )
    }
    assert {
        profile.profile_id: profile.sha256
        for profile in (
            X24_ORIGIN_PROFILE,
            X35_ORIGIN_PROFILE,
            X36_ORIGIN_PROFILE,
            X38_ORIGIN_PROFILE,
        )
    } == {
        "X24": "fa991237fbf2f5a0139b4acd6ba44372928f55922a8c347941d3a6442559ba84",
        "X35": "cba0737aaa4c2ab24a62062cfe37c095c5651d9048519b3fc2a3e9ccaa058ca9",
        "X36": "6e951a3dd1f08cb2122cac48ce37476eef54d54c9fb424211e9fce39c677e1ab",
        "X38": "c6d7548cf7389e5d53282c6d1873aa2e8e184de96ae54d2cd71937f0a56d98d3",
    }
    assert "set_chart_parameter" not in {
        capability.operation for capability in profiles["X24"].capabilities
    }
    assert profiles["X38"].repeatable_objects[0].object_key_prefix == "group"
    x38_capabilities = {
        capability.operation: capability.parameters for capability in profiles["X38"].capabilities
    }
    assert {
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "line_opacity",
        "visible",
    } == set(x38_capabilities["set_series_style"])


def test_remaining_t1_implementation_does_not_import_old_plot_compiler() -> None:
    source = "\n".join(
        inspect.getsource(module)
        for module in (
            x24_origin,
            dual_origin,
            x38_origin,
        )
    )
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
    x38_source = inspect.getsource(x38_origin)
    assert "run.section(plot,OffsetYs)" in x38_source
    assert ".new_graph(" not in x38_source
    assert ".add_plot(" not in x38_source
