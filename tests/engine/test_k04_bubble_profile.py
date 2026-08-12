from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.k04 as origin_module
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
    SetChartParameter,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.backends.matplotlib import K04BubbleRenderer, MatplotlibBackend
from plotagent.engine.backends.origin.k04 import K04OriginProject
from plotagent.engine.profile_data import k04_bubble

HASH = "4" * 64


def _case(
    *,
    scales: bool = False,
    edits: bool = False,
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id="dataset.bubble",
        version=1,
        content_hash=HASH,
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=f"field:{role}") for role in ("x", "y", "size", "color")
    )
    create = CreatePlot(
        action_id="action:create-k04",
        plot_id="plot:k04-bubble",
        profile_id="K04",
        data=data,
        bindings=bindings,
    )
    action_list: list[PlotEngineAction] = [create]
    if edits:
        action_list.extend(
            (
                SetTitle(
                    action_id="action:k04-title",
                    target=create.plot_id,
                    expected_plot_version=1,
                    text="Edited bubbles",
                ),
                SetAxis(
                    action_id="action:k04-axis",
                    target="axis:k04-bubble.y",
                    expected_plot_version=2,
                    label="Edited Y",
                    scale="log10",
                ),
                SetSeriesStyle(
                    action_id="action:k04-style",
                    target="series:k04-bubble.primary",
                    expected_plot_version=3,
                    symbol="diamond",
                    symbol_size_pt=16,
                ),
                SetLegend(
                    action_id="action:k04-legend",
                    target="legend:k04-bubble.main",
                    expected_plot_version=4,
                    visible=True,
                ),
            )
        )
    if scales:
        action_list.extend(
            (
                SetChartParameter(
                    action_id="action:k04-color-scale",
                    target=create.plot_id,
                    expected_plot_version=len(action_list),
                    parameter="color_scale_visible",
                    value=True,
                ),
                SetChartParameter(
                    action_id="action:k04-size-key",
                    target=create.plot_id,
                    expected_plot_version=len(action_list) + 1,
                    parameter="size_key_visible",
                    value=True,
                ),
            )
        )
    actions = tuple(action_list)
    version = len(actions)
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=version,
        parent_version=None if version == 1 else version - 1,
        profile_id="K04",
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    values = {
        "x": (1.0, 2.0, 3.0, 4.0),
        "y": (2.0, 3.0, 2.5, 4.5),
        "size": (1.0, 4.0, 9.0, 16.0),
        "color": (0.1, 0.3, 0.7, 1.0),
    }
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(4)),
        columns=tuple(
            EngineColumn(
                field=EngineField(
                    field_id=f"field:{role}",
                    name=role.title(),
                    logical_type="numeric",
                ),
                values=column_values,
            )
            for role, column_values in values.items()
        ),
    )
    return document, actions, view


def test_k04_binding_size_keeps_bubble_scale_but_color_scale_is_opt_in(
    tmp_path: Path,
) -> None:
    document, actions, view = _case()
    bubble = k04_bubble(document, view)
    assert bubble.size_values == (1.0, 4.0, 9.0, 16.0)
    assert bubble.color_values == (0.1, 0.3, 0.7, 1.0)

    backend = MatplotlibBackend(tmp_path / "artifacts", (K04BubbleRenderer(),))
    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()
    kinds = {item.object_kind for item in backend.readback(document).objects}

    assert "color_scale" not in kinds
    assert "size_key" in kinds
    assert (tmp_path / "artifacts" / "k04-bubble" / "v1" / "preview.png").stat().st_size > 0


def test_k04_scales_are_explicit_shared_parameters(tmp_path: Path) -> None:
    document, actions, view = _case(scales=True, edits=True)
    backend = MatplotlibBackend(tmp_path / "artifacts", (K04BubbleRenderer(),))
    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()

    kinds = {item.object_kind for item in backend.readback(document).objects}
    assert {"color_scale", "size_key"} <= kinds


def test_k04_rejects_negative_sizes() -> None:
    document, _, view = _case()
    invalid = view.model_copy(
        update={
            "columns": tuple(
                column.model_copy(update={"values": (1.0, -1.0, 2.0, 3.0)})
                if column.field.field_id == "field:size"
                else column
                for column in view.columns
            )
        }
    )
    with pytest.raises(ValueError, match="non-negative"):
        k04_bubble(document, invalid)


class _Label:
    def __init__(self, text: str = "", *, name: str = "", show: int = 1) -> None:
        self.text = text
        self.name = name
        self.values = {"show": show, "link": 0}

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)


class _NativeObject:
    def __init__(self, object_type: int) -> None:
        self.object_type = object_type

    def IsValid(self) -> bool:
        return True


class _GraphObjects:
    def __init__(self) -> None:
        self.added: list[_NativeObject] = []

    def Add(self, object_type: int) -> _NativeObject:
        native = _NativeObject(object_type)
        self.added.append(native)
        return native


class _LayerObject:
    def __init__(self, layer: _Layer) -> None:
        self.layer = layer
        self.GraphObjects = _GraphObjects()

    def LT_execute(self, command: str) -> bool:
        assert command == "legend"
        self.layer.labels["legend"] = _Label(name="legend")
        return True


class _Axis:
    def __init__(self) -> None:
        self.scale = "linear"
        self.limits = (0.0, 1.0, 0.1)

    def set_limits(self, begin: float, end: float, step: float | None = None) -> None:
        self.limits = (begin, end, 0.1 if step is None else step)


class _Plot:
    def __init__(self) -> None:
        self.color: object = (22, 118, 210)
        self.symbol_size: object = ("size", 1)
        self.symbol_sizefactor = 1.0
        self.symbol_kind = 2
        self.obj = _PlotObject()


class _ThemeNode:
    def __init__(self, name: str, value: object = None, children=()) -> None:
        self.Name = name
        self._value = value
        self.Children = tuple(children)

    def GetValue(self) -> object:
        return self._value


class _PlotObject:
    DatasetName = "DK04_B"

    @staticmethod
    def GetTheme() -> _ThemeNode:
        return _ThemeNode(
            "Root",
            children=(
                _ThemeNode(
                    "ColorMap",
                    children=(
                        _ThemeNode("Min", 0.1),
                        _ThemeNode("Max", 1.0),
                        _ThemeNode("MajorLevels", 8),
                    ),
                ),
            ),
        )


class _Layer:
    def __init__(self) -> None:
        self.labels: dict[str, _Label] = {"BUBBLELEGEND1": _Label(name="BUBBLELEGEND1", show=1)}
        self.axes = {"x": _Axis(), "y": _Axis()}
        self.plot = _Plot()
        self.obj = _LayerObject(self)
        self.add_call: dict[str, object] | None = None

    def add_plot(self, sheet, **kwargs) -> _Plot:
        self.add_call = kwargs
        return self.plot

    def plot_list(self) -> list[_Plot]:
        return [self.plot]

    def label(self, name: str) -> _Label | None:
        direct = self.labels.get(name)
        if direct is not None:
            return direct
        return next((label for label in self.labels.values() if label.name == name), None)

    def add_label(self, text: str, *args) -> _Label:
        label = _Label(text)
        self.labels[f"new-{len(self.labels)}"] = label
        return label

    def axis(self, name: str) -> _Axis:
        return self.axes[name]

    def activate(self) -> None:
        return None

    def rescale(self) -> None:
        return None


class _Graph:
    def __init__(self) -> None:
        self.name = "G"
        self.layer = _Layer()

    def __getitem__(self, index: int) -> _Layer:
        assert index == 0
        return self.layer

    def activate(self) -> None:
        return None


class _Sheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}
        self.designations: dict[int, int] = {}
        self.cols = 0

    def from_list(self, column: int, values, **kwargs) -> None:
        self.columns[column] = list(values)
        self.designations[column + 1] = {"X": 4, "Y": 1, "N": 2}[kwargs["axis"]]

    def to_list(self, column: int) -> list[object]:
        return self.columns[column]

    def activate(self) -> None:
        return None

    def get_int(self, expression: str) -> int:
        return self.designations[int(expression.removeprefix("col").removesuffix(".type"))]


class _Book:
    def __init__(self) -> None:
        self.sheet = _Sheet()
        self.name = "DK04"

    def __getitem__(self, index: int) -> _Sheet:
        assert index == 0
        return self.sheet

    def destroy(self) -> None:
        return None


class _Origin:
    def __init__(self) -> None:
        self.book = _Book()
        self.graph = _Graph()
        self.commands: list[str] = []
        self.native_pid = 0
        self.graph_created = False

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs) -> _Book:
        return self.book

    def pages(self, kind: str):
        if kind == "w":
            return (self.book,)
        if kind == "g":
            return (self.graph,) if self.graph_created else ()
        return ()

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        if "worksheet -p 248 Bubble" in command:
            self.graph_created = True
            self.native_pid = 201
        return True

    def lt_float(self, expression: str) -> float:
        assert expression == "__K04PID"
        return float(self.native_pid)

    @staticmethod
    def modi_col(offset: int) -> tuple[str, int]:
        return ("size", offset)

    def Label(self, native: _NativeObject, layer_obj: _LayerObject) -> _Label:
        label = _Label()
        layer_obj.layer.labels[f"native-{len(layer_obj.layer.labels)}"] = label
        return label


def test_k04_origin_keeps_official_bubble_scale_and_hides_color_scale_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, actions, view = _case()
    monkeypatch.setattr(
        origin_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = _Origin()
    project = K04OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert any("worksheet -p 248 Bubble" in command for command in origin.commands)
    assert origin.graph.layer.add_call is None
    assert origin.graph.layer.plot.symbol_size == ("size", 1)
    assert origin.graph.layer.labels["BUBBLELEGEND1"].get_int("show") == 1
    assert "size_key" in {item.object_kind for item in readback.objects}
    assert "color_scale" not in {item.object_kind for item in readback.objects}


def test_k04_origin_creates_only_explicitly_requested_scales(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, actions, view = _case(scales=True, edits=True)
    monkeypatch.setattr(
        origin_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / profile.filename,
    )
    origin = _Origin()
    project = K04OriginProject(origin)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert origin.graph.layer.labels["BUBBLELEGEND1"].get_int("show") == 1
    spectrum = origin.graph.layer.label("SPECTRUM1")
    assert spectrum is not None and spectrum.get_int("show") == 1
    assert [item.object_type for item in origin.graph.layer.obj.GraphObjects.added] == [13]
    assert {"color_scale", "size_key"} <= {item.object_kind for item in readback.objects}
    assert origin.graph.layer.plot.symbol_kind == 5
    assert origin.graph.layer.plot.symbol_sizefactor == pytest.approx(1.0)
    assert origin.graph.layer.axis("y").scale == "log10"
    assert origin.graph.layer.label("yl").text == "Edited Y"
    assert origin.graph.layer.label("legend").get_int("show") == 1


def test_k04_new_path_has_no_legacy_compiler_dependency() -> None:
    modules = (K04BubbleRenderer.__module__, K04OriginProject.__module__)
    source = "\n".join(inspect.getsource(__import__(module, fromlist=["*"])) for module in modules)
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
