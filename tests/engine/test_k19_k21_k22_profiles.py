from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import plotagent.engine.backends.origin.advanced_matrix as matrix_origin_module
import plotagent.engine.backends.origin.k18 as k18_origin_module
import plotagent.engine.backends.origin.k19 as k19_origin_module
import plotagent.engine.backends.origin.k21 as k21_origin_module
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    SetAxis,
    SetChartParameter,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.backends.matplotlib import (
    K18AreaRenderer,
    K19TimeSeriesRenderer,
    K21CorrelationMatrixRenderer,
    K22ContourRenderer,
)
from plotagent.engine.backends.origin import (
    K18_ORIGIN_PROFILE,
    K19_ORIGIN_PROFILE,
    K21_ORIGIN_PROFILE,
    K22_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.advanced_matrix import K22OriginProject
from plotagent.engine.backends.origin.k18 import K18OriginProject
from plotagent.engine.backends.origin.k19 import K19OriginProject
from plotagent.engine.backends.origin.k21 import K21OriginProject
from plotagent.engine.profile_data import (
    k18_area_series,
    k19_time_series,
    k21_correlation_grid,
    k22_regular_grid,
)
from plotagent.engine.profiles import (
    K18_AREA_PROFILE,
    K19_TIME_SERIES_PROFILE,
    K21_CORRELATION_MATRIX_PROFILE,
    K22_CONTOUR_PROFILE,
)

HASH = "7" * 64


def _document(profile_id: str, bindings: tuple[FieldBinding, ...], actions=()) -> PlotDocument:
    return PlotDocument(
        plot_id=f"plot:{profile_id.lower()}-demo",
        plot_version=max(1, len(actions)),
        parent_version=None if len(actions) <= 1 else len(actions) - 1,
        profile_id=profile_id,
        data=EngineDataRef(
            kind="prepared" if profile_id in {"K21", "K22"} else "source",
            dataset_id=f"dataset.{profile_id.lower()}",
            version=1,
            content_hash=HASH,
        ),
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )


def _view(
    profile_id: str,
    fields: tuple[tuple[str, str, str, tuple[object, ...]], ...],
) -> EngineDataView:
    row_count = len(fields[0][3])
    return EngineDataView(
        data=EngineDataRef(
            kind="prepared" if profile_id in {"K21", "K22"} else "source",
            dataset_id=f"dataset.{profile_id.lower()}",
            version=1,
            content_hash=HASH,
        ),
        row_ids=tuple(f"row:{index}" for index in range(1, row_count + 1)),
        columns=tuple(
            EngineColumn(
                field=EngineField(field_id=field_id, name=name, logical_type=logical_type),
                values=values,
            )
            for field_id, name, logical_type, values in fields
        ),
    )


def _k19_case() -> tuple[PlotDocument, tuple[CreatePlot, ...], EngineDataView]:
    bindings = (
        FieldBinding(role="time", field_id="field:time"),
        FieldBinding(role="series_1", field_id="field:value-a"),
        FieldBinding(role="series_2", field_id="field:value-b"),
    )
    data_ref = EngineDataRef(
        kind="source", dataset_id="dataset.k19", version=1, content_hash=HASH
    )
    create = CreatePlot(
        action_id="action:k19-create",
        plot_id="plot:k19-demo",
        profile_id="K19",
        data=data_ref,
        bindings=bindings,
    )
    document = _document("K19", bindings, (create,))
    start = datetime(2026, 1, 1, 8)
    view = _view(
        "K19",
        (
            (
                "field:time",
                "Recorded at",
                "datetime",
                tuple(start + timedelta(hours=i) for i in range(5)),
            ),
            ("field:value-a", "Signal A", "numeric", (1.0, 1.4, 1.1, 2.0, 1.8)),
            ("field:value-b", "Signal B", "numeric", (0.7, 0.9, 1.2, 1.0, 1.5)),
        ),
    )
    return document, (create,), view


def _k18_case() -> tuple[PlotDocument, tuple[CreatePlot, ...], EngineDataView]:
    bindings = (
        FieldBinding(role="x", field_id="field:x"),
        FieldBinding(role="series_1", field_id="field:value-a"),
        FieldBinding(role="series_2", field_id="field:value-b"),
    )
    data_ref = EngineDataRef(
        kind="source", dataset_id="dataset.k18", version=1, content_hash=HASH
    )
    create = CreatePlot(
        action_id="action:k18-create",
        plot_id="plot:k18-demo",
        profile_id="K18",
        data=data_ref,
        bindings=bindings,
    )
    document = _document("K18", bindings, (create,))
    view = _view(
        "K18",
        (
            ("field:x", "Time", "numeric", (0.0, 1.0, 2.0, 3.0, 4.0)),
            ("field:value-a", "Signal A", "numeric", (1.0, 2.2, -0.5, 1.7, 2.4)),
            ("field:value-b", "Signal B", "numeric", (0.4, 1.1, 1.8, -0.2, 1.3)),
        ),
    )
    return document, (create,), view


def _k21_case() -> tuple[PlotDocument, tuple[object, ...], EngineDataView]:
    bindings = (
        FieldBinding(role="row_label", field_id="field:row-label"),
        FieldBinding(role="column_label", field_id="field:column-label"),
        FieldBinding(role="value", field_id="field:value"),
    )
    data_ref = EngineDataRef(
        kind="prepared", dataset_id="dataset.k21", version=1, content_hash=HASH
    )
    create = CreatePlot(
        action_id="action:k21-create",
        plot_id="plot:k21-demo",
        profile_id="K21",
        data=data_ref,
        bindings=bindings,
    )
    triangle = SetChartParameter(
        action_id="action:k21-triangle",
        target=create.plot_id,
        expected_plot_version=1,
        parameter="triangle",
        value="lower",
    )
    document = _document("K21", bindings, (create, triangle))
    view = _view(
        "K21",
        (
            ("field:row-label", "Row variable", "categorical", ("B", "B", "A", "A")),
            ("field:column-label", "Column variable", "categorical", ("A", "B", "A", "B")),
            ("field:value", "Correlation", "numeric", (0.25, 1.0, 1.0, 0.25)),
        ),
    )
    return document, (create, triangle), view


def _k22_case() -> tuple[PlotDocument, tuple[CreatePlot, ...], EngineDataView]:
    bindings = (
        FieldBinding(role="x", field_id="field:x"),
        FieldBinding(role="y", field_id="field:y"),
        FieldBinding(role="z", field_id="field:z"),
    )
    data_ref = EngineDataRef(
        kind="prepared", dataset_id="dataset.k22", version=1, content_hash=HASH
    )
    create = CreatePlot(
        action_id="action:k22-create",
        plot_id="plot:k22-demo",
        profile_id="K22",
        data=data_ref,
        bindings=bindings,
    )
    document = _document("K22", bindings, (create,))
    view = _view(
        "K22",
        (
            ("field:x", "Wavelength", "numeric", (2.0, 1.0, 2.0, 1.0)),
            ("field:y", "Temperature", "numeric", (20.0, 20.0, 10.0, 10.0)),
            ("field:z", "Amplitude", "numeric", (4.0, 3.0, 2.0, 1.0)),
        ),
    )
    return document, (create,), view


def test_profile_data_validates_datetime_correlation_and_complete_grid() -> None:
    k18_document, _k18_actions, k18_view = _k18_case()
    area = k18_area_series(k18_document, k18_view)
    assert area.x_values == (0.0, 1.0, 2.0, 3.0, 4.0)
    assert tuple(item.value_field_name for item in area.series) == (
        "Signal A",
        "Signal B",
    )

    k19_document, _k19_actions, k19_view = _k19_case()
    time_series = k19_time_series(k19_document, k19_view)
    assert time_series.time_values[0] == datetime(2026, 1, 1, 8)
    assert tuple(item.value_field_name for item in time_series.series) == (
        "Signal A",
        "Signal B",
    )

    k21_document, _k21_actions, k21_view = _k21_case()
    correlation = k21_correlation_grid(k21_document, k21_view)
    assert correlation.row_labels == correlation.column_labels == ("A", "B")
    assert correlation.values == ((1.0, 0.25), (0.25, 1.0))

    k22_document, _k22_actions, k22_view = _k22_case()
    contour = k22_regular_grid(k22_document, k22_view)
    assert contour.x_values == (1.0, 2.0)
    assert contour.y_values == (10.0, 20.0)
    assert contour.z_values == ((1.0, 2.0), (3.0, 4.0))


def test_k19_preserves_input_order_rejects_timezone_and_k22_never_interpolates() -> None:
    document, _actions, view = _k19_case()
    repeated = view.model_copy(
        update={
            "columns": (
                view.columns[0].model_copy(
                    update={"values": (datetime(2026, 1, 1),) * len(view.row_ids)}
                ),
                *view.columns[1:],
            )
        }
    )
    assert len(set(k19_time_series(document, repeated).time_values)) == 1

    timezone_aware = view.model_copy(
        update={
            "columns": (
                view.columns[0].model_copy(
                    update={
                        "values": tuple(
                            datetime(2026, 1, 1, hour, tzinfo=UTC)
                            for hour in range(5)
                        )
                    }
                ),
                *view.columns[1:],
            )
        }
    )
    with pytest.raises(ValueError, match="timezone offset"):
        k19_time_series(document, timezone_aware)

    sub_millisecond = view.model_copy(
        update={
            "columns": (
                view.columns[0].model_copy(
                    update={
                        "values": tuple(
                            datetime(2026, 1, 1, hour, microsecond=1)
                            for hour in range(5)
                        )
                    }
                ),
                *view.columns[1:],
            )
        }
    )
    with pytest.raises(ValueError, match="millisecond precision"):
        k19_time_series(document, sub_millisecond)

    k22_document, _actions, k22_view = _k22_case()
    incomplete = k22_view.model_copy(
        update={
            "row_ids": k22_view.row_ids[:-1],
            "columns": tuple(
                column.model_copy(update={"values": column.values[:-1]})
                for column in k22_view.columns
            ),
        }
    )
    with pytest.raises(ValueError, match="never interpolates"):
        k22_regular_grid(k22_document, incomplete)


@pytest.mark.parametrize(
    ("renderer", "case"),
    (
        (K18AreaRenderer(), _k18_case),
        (K19TimeSeriesRenderer(), _k19_case),
        (K21CorrelationMatrixRenderer(), _k21_case),
        (K22ContourRenderer(), _k22_case),
    ),
)
def test_independent_matplotlib_profiles_render(renderer, case, tmp_path: Path) -> None:
    document, actions, view = case()
    readback = renderer.render(
        document,
        actions,
        view,
        tmp_path / f"{renderer.profile_id}.png",
        tmp_path / f"{renderer.profile_id}.svg",
    )
    assert readback.document.plot_id == document.plot_id
    assert (tmp_path / f"{renderer.profile_id}.png").stat().st_size > 1_000
    assert (tmp_path / f"{renderer.profile_id}.svg").stat().st_size > 1_000


def test_k19_multi_series_actions_are_targeted_and_backend_neutral(tmp_path: Path) -> None:
    document, (create,), view = _k19_case()
    actions = (
        create,
        SetSeriesStyle(
            action_id="action:k19-style",
            expected_plot_version=1,
            target="series:k19-demo.line_2",
            color="#AA3300",
            line_width_pt=2.5,
            line_style="dash",
        ),
        SetAxis(
            action_id="action:k19-axis",
            expected_plot_version=2,
            target="axis:k19-demo.y",
            scale="linear",
            minimum=0.5,
            maximum=2.5,
            reverse=False,
            label="Edited signal",
        ),
        SetLegend(
            action_id="action:k19-legend",
            expected_plot_version=3,
            target="legend:k19-demo.main",
            visible=True,
            anchor="inside",
        ),
        SetTitle(
            action_id="action:k19-title",
            expected_plot_version=4,
            target="plot:k19-demo",
            text="K19 edited",
        ),
    )
    edited = document.model_copy(
        update={
            "plot_version": 5,
            "parent_version": 4,
            "applied_action_ids": tuple(action.action_id for action in actions),
        }
    )
    renderer = K19TimeSeriesRenderer()
    state = renderer._state(
        edited,
        actions,
        "Recorded at",
        ("Signal A", "Signal B"),
    )
    assert state.lines[0].color == "#1676D2"
    assert state.lines[1].color == "#AA3300"
    assert state.lines[1].line_width_pt == 2.5
    assert state.lines[1].line_style == "dash"
    assert (state.y_minimum, state.y_maximum, state.y_label) == (
        0.5,
        2.5,
        "Edited signal",
    )
    assert state.legend_visible and state.title == "K19 edited"
    readback = renderer.render(
        edited,
        actions,
        view,
        tmp_path / "k19-edited.png",
        tmp_path / "k19-edited.svg",
    )
    assert [
        item.semantic_id for item in readback.objects if item.object_kind == "datetime_line"
    ] == ["series:k19-demo.line_1", "series:k19-demo.line_2"]


def test_k18_multi_series_actions_are_targeted_and_backend_neutral(tmp_path: Path) -> None:
    document, (create,), view = _k18_case()
    actions = (
        create,
        SetSeriesStyle(
            action_id="action:k18-style",
            expected_plot_version=1,
            target="series:k18-demo.area_2",
            color="#AA3300",
            line_width_pt=2.5,
            line_style="dash",
        ),
        SetLegend(
            action_id="action:k18-legend",
            expected_plot_version=2,
            target="legend:k18-demo.main",
            visible=True,
            anchor="inside",
        ),
        SetTitle(
            action_id="action:k18-title",
            expected_plot_version=3,
            target="plot:k18-demo",
            text="K18 edited",
        ),
    )
    edited = document.model_copy(
        update={
            "plot_version": 4,
            "parent_version": 3,
            "applied_action_ids": tuple(action.action_id for action in actions),
        }
    )
    state = K18AreaRenderer._state(
        edited,
        actions,
        "Time",
        ("Signal A", "Signal B"),
    )
    assert state.areas[0].color == "#1676D2"
    assert state.areas[1].color == "#AA3300"
    assert state.areas[1].line_width_pt == 2.5
    assert state.areas[1].line_style == "dash"
    assert state.legend_visible and state.title == "K18 edited"
    readback = K18AreaRenderer().render(
        edited,
        actions,
        view,
        tmp_path / "k18-edited.png",
        tmp_path / "k18-edited.svg",
    )
    assert [
        item.semantic_id for item in readback.objects if item.object_kind == "area_series"
    ] == ["series:k18-demo.area_1", "series:k18-demo.area_2"]


def test_k18_requires_contiguous_series_and_rejects_log_with_non_positive_data() -> None:
    document, _actions, view = _k18_case()
    gapped = document.model_copy(
        update={
            "bindings": (
                document.bindings[0],
                document.bindings[1].model_copy(update={"role": "series_2"}),
                document.bindings[2].model_copy(update={"role": "series_3"}),
            )
        }
    )
    with pytest.raises(ValueError, match="contiguous series_1"):
        k18_area_series(gapped, view)

    log_action = SetAxis(
        action_id="action:k18-log",
        expected_plot_version=1,
        target="axis:k18-demo.y",
        scale="log10",
    )
    with pytest.raises(ValueError, match="must be positive"):
        K18AreaRenderer().render(
            document,
            (_actions[0], log_action),
            view,
            Path("unused.png"),
            Path("unused.svg"),
        )


def test_k19_origin_axis_display_follows_calendar_span() -> None:
    document, _actions, view = _k19_case()
    same_day = k19_time_series(document, view)
    assert K19OriginProject._axis_tick_display(same_day) == (3, 1, "Time / HH:mm")

    across_days = view.model_copy(
        update={
            "columns": (
                view.columns[0].model_copy(
                    update={
                        "values": tuple(
                            datetime(2026, 1, 1) + timedelta(days=index)
                            for index in range(5)
                        )
                    }
                ),
                *view.columns[1:],
            )
        }
    )
    assert K19OriginProject._axis_tick_display(
        k19_time_series(document, across_days)
    ) == (4, 1, "Date / Windows Short Date")


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

    def get_float(self, name: str) -> float:
        return float(self.values.get(name, 0.0))


class FakeAxis:
    def __init__(self) -> None:
        self.limits = (0.0, 1.0, 1.0)
        self.scale = "linear"

    def set_limits(self, begin=None, end=None, step=None) -> None:
        self.limits = (
            float(self.limits[0] if begin is None else begin),
            float(self.limits[1] if end is None else end),
            float(self.limits[2] if step is None else step),
        )


class FakeThemeNode:
    def __init__(self, name: str, value=None, children=()) -> None:
        self.Name = name
        self._value = value
        self.Children = list(children)

    def GetValue(self):
        return self._value

    def SetIntValue(self, value: int) -> None:
        self._value = value


class FakeGraphObject:
    def __init__(self, name: str, object_type: int) -> None:
        self.Name = name
        self._object_type = object_type

    def GetObjectType(self) -> int:
        return self._object_type


class FakePlot:
    def __init__(self) -> None:
        self.obj = self
        self.DatasetName = "Book1"
        self.color = (0, 0, 0)
        self.symbol_kind = 0
        self.symbol_size = 5.0
        self.floats = {"line.width": 1.5}
        self.ints = {"line.style": 0}
        self._zlevels = {"minors": 0, "levels": [0.0, 1.0]}
        self.theme = FakeThemeNode(
            "Root",
            children=(
                FakeThemeNode("Label", children=(FakeThemeNode("Enable", 1),)),
                FakeThemeNode("FillDispl", 1),
                FakeThemeNode("LabelDispl", 0),
            ),
        )

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def get_float(self, name: str) -> float:
        return self.floats[name]

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints[name]

    @property
    def zlevels(self):
        return self._zlevels

    @zlevels.setter
    def zlevels(self, value) -> None:
        self._zlevels = value

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
        self.added_type: int | str | None = None
        self.strings: dict[str, str] = {}
        self.ints: dict[str, int] = {}
        self.GraphObjects = [FakeGraphObject("SPECTRUM1", 13)]

    def add_plot(self, sheet, *, coly, colx, type):
        assert (colx, coly) == (0, 1)
        self.added_type = type
        plot = FakePlot()
        self.plots.append(plot)
        return plot

    def add_mplot(self, sheet, index, *, type):
        assert index == 0
        self.added_type = type
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

    def activate(self) -> None:
        return None

    def LT_execute(self, command: str) -> bool:
        if "label -j" in command:
            label = FakeLabel("PlotAgentTitlePlaceholder")
            label.name = "_ENGINE_TITLE"
            self.labels["title"] = label
        return True

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints[name]

    def set_str(self, name: str, value: str) -> None:
        self.strings[name] = value

    def get_str(self, name: str) -> str:
        return self.strings[name]


class FakeGraph:
    def __init__(self) -> None:
        self.name = "Gdemo"
        self.lname = ""
        self.layer = FakeLayer()

    def __getitem__(self, index: int):
        assert index == 0
        return self.layer

    def __len__(self) -> int:
        return 1

    def activate(self) -> None:
        return None


class FakeColumn:
    def __init__(self, sheet: FakeSheet, index: int) -> None:
        self.sheet = sheet
        self.index = index

    def GetDataFormat(self) -> int:
        return self.sheet.data_formats[self.index]

    @property
    def DatasetName(self) -> str:
        return "Book1"


class FakeSheet:
    def __init__(self) -> None:
        self.frame = pd.DataFrame()
        self.values = np.empty((0, 0))
        self.xymap = (0.0, 0.0, 0.0, 0.0)
        self.designation = ""
        self.data_formats = [0, 0]
        self.obj = self

    def from_df(self, frame: pd.DataFrame) -> None:
        self.frame = frame.copy()
        self.data_formats = [0] * len(frame.columns)

    def to_df(self) -> pd.DataFrame:
        return self.frame.copy()

    def cols_axis(self, value: str) -> None:
        self.designation = value

    @property
    def cols(self) -> int:
        return len(self.frame.columns)

    def activate(self) -> None:
        return None

    def as_date(self, index: int, display: str) -> None:
        assert index == 0
        assert display == "yyyy-MM-dd HH:mm:ss"
        self.data_formats[index] = 3

    def get_int(self, name: str) -> int:
        assert name.startswith("col") and name.endswith(".type")
        index = int(name.removeprefix("col").removesuffix(".type")) - 1
        return {"x": 4, "y": 1}[self.designation[index]]

    def __getitem__(self, index: int) -> FakeColumn:
        return FakeColumn(self, index)

    def from_np(self, values) -> None:
        self.values = np.asarray(values, dtype=float)

    def to_np2d(self):
        return self.values


class FakeBook:
    def __init__(self) -> None:
        self.name = "Book1"
        self.sheet = FakeSheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet

    def destroy(self) -> None:
        return None


class FakeOrigin:
    def __init__(self) -> None:
        self.book = FakeBook()
        self.graph = FakeGraph()
        self.book_kind = ""
        self.template = ""
        self.lt_values: dict[str, float] = {}
        self.lt_strings: dict[str, str] = {}
        self.commands: list[str] = []

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, kind, name, *, hidden):
        self.book_kind = kind
        return self.book

    def new_graph(self, name, *, template, hidden):
        self.graph.name = name
        self.template = template
        return self.graph

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        if "worksheet -p 204 Area" in command:
            self.graph.layer.plots = [
                FakePlot() for _index in range(self.book.sheet.cols - 1)
            ]
        if "__K18COUNT" in command:
            self.lt_values["__K18COUNT"] = len(self.graph.layer.plots)
        if "range __K18P=" in command:
            plot_index = int(command.split("]1!", 1)[1].split(";", 1)[0])
            column = chr(65 + plot_index)
            plot = self.graph.layer.plots[plot_index - 1]
            self.lt_values.update(
                {
                    "__K18PID": 204,
                    "__K18LINE": 1,
                    "__K18FILL": 2,
                    "__K18STYLE": plot.ints["line.style"],
                    "__K18WIDTH": plot.floats["line.width"] * 500,
                }
            )
            self.lt_strings.update(
                {
                    "__K18XS": '[Book1]Sheet1!A"Time"',
                    "__K18YS": f'[Book1]Sheet1!{column}"Signal {plot_index}"',
                }
            )
        if "worksheet -p 200 Line" in command:
            self.graph.layer.plots = [
                FakePlot() for _index in range(self.book.sheet.cols - 1)
            ]
        if "__k19_count" in command:
            self.lt_values["__k19_count"] = len(self.graph.layer.plots)
        if "range __k19_plot=" in command:
            plot_index = int(command.split("]1!", 1)[1].split(";", 1)[0])
            column = chr(65 + plot_index)
            self.lt_values["__k19_pid"] = 200
            self.lt_strings.update(
                {
                    "__k19_xs": '[Book1]Sheet1!A"Recorded at"',
                    "__k19_ys": f'[Book1]Sheet1!{column}"Signal {plot_index}"',
                }
            )
        if "__k19_axis_label_type" in command:
            configured = next(
                (
                    prior
                    for prior in reversed(self.commands)
                    if "layer.x.label.type=" in prior
                ),
                "layer.x.label.type=4; layer.x.label.timeFormat=1;",
            )
            self.lt_values["__k19_axis_label_type"] = (
                3 if "layer.x.label.type=3" in configured else 4
            )
            self.lt_values["__k19_axis_time_format"] = 1
        if "legendupdate" in command:
            label = FakeLabel(
                "\n".join(
                    f"\\l({index}) Signal {index}"
                    for index in range(1, len(self.graph.layer.plots) + 1)
                )
            )
            label.name = "legend"
            self.graph.layer.labels["legend"] = label
        if "__K21COUNT" in command:
            self.lt_values.update(
                {
                    "__K21COUNT": 1,
                    "__K21PID": 105,
                    "__K21ZMIN": -1,
                    "__K21ZMAX": 1,
                    "__K21CMAPTYPE": 0,
                }
            )
        return True

    def set_lt_str(self, name: str, value: str) -> bool:
        self.lt_strings[name] = value
        return True

    def lt_float(self, name: str) -> float:
        return self.lt_values[name]

    def get_lt_str(self, name: str) -> str:
        return self.lt_strings[name]

    def pages(self, kind: str):
        if kind == "g":
            return (self.graph,)
        if kind == "w":
            return (self.book,)
        return ()


def test_origin_profiles_bind_official_templates_and_native_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    k18_document, k18_actions, k18_view = _k18_case()
    monkeypatch.setattr(
        k18_origin_module,
        "resolve_official_template",
        lambda *_: tmp_path / "AREA.otpu",
    )
    k18_op = FakeOrigin()
    k18 = K18OriginProject(k18_op)
    k18.create(tmp_path, k18_document, k18_view)
    k18_readback = k18.verify(k18_document, k18_actions, k18_view)
    assert K18_ORIGIN_PROFILE.filename == "AREA.otpu"
    assert k18_op.book.sheet.designation == "xyy"
    assert any("worksheet -p 204 Area" in command for command in k18_op.commands)
    assert len(k18_op.graph.layer.plots) == 2
    assert [
        item.semantic_id
        for item in k18_readback.objects
        if item.object_kind == "area_series"
    ] == ["series:k18-demo.area_1", "series:k18-demo.area_2"]

    k19_document, _actions, k19_view = _k19_case()
    monkeypatch.setattr(
        k19_origin_module,
        "resolve_official_template",
        lambda *_: tmp_path / "LINE.otpu",
    )
    k19_op = FakeOrigin()
    K19OriginProject(k19_op).create(tmp_path, k19_document, k19_view)
    assert K19_ORIGIN_PROFILE.filename == "LINE.otpu"
    assert k19_op.book.sheet.designation == "xyy"
    assert pd.api.types.is_datetime64_any_dtype(k19_op.book.sheet.frame.iloc[:, 0])
    assert any("worksheet -p 200 Line" in command for command in k19_op.commands)
    assert len(k19_op.graph.layer.plots) == 2
    assert k19_op.book.sheet.data_formats[0] == 3

    k21_document, k21_actions, k21_view = _k21_case()
    monkeypatch.setattr(
        k21_origin_module,
        "resolve_official_template",
        lambda _install, profile: tmp_path / profile.filename,
    )
    k21_op = FakeOrigin()
    k21 = K21OriginProject(k21_op)
    k21.create(tmp_path, k21_document, k21_view)
    k21.reconcile(k21_document, k21_actions, k21_view)
    assert Path(k21_op.template).name == "Heat_Map_With_Labels.otpu"
    assert k21_op.graph.layer.added_type == 105
    assert np.array_equal(
        k21_op.book.sheet.values,
        np.asarray(((1.0, 0.25), (0.25, 1.0))),
    )
    assert k21_op.graph.layer.plots[0].theme.Children[1].GetValue() == 4
    assert k21_op.graph.layer.plots[0].theme.Children[2].GetValue() == 2

    k22_document, k22_actions, k22_view = _k22_case()
    monkeypatch.setattr(
        matrix_origin_module,
        "resolve_official_template",
        lambda _install, profile: tmp_path / profile.filename,
    )
    k22_op = FakeOrigin()
    k22 = K22OriginProject(k22_op)
    k22.create(tmp_path, k22_document, k22_view)
    k22.reconcile(k22_document, k22_actions, k22_view)
    assert Path(k22_op.template).name == "CONTOUR.otpu"
    assert k22_op.graph.layer.added_type == 226
    assert len(k22_op.graph.layer.plots[0].zlevels["levels"]) == 13


def test_template_hashes_and_modules_exclude_the_legacy_compiler() -> None:
    assert K18_ORIGIN_PROFILE.sha256.startswith("c14ad432ffd6")
    assert K19_ORIGIN_PROFILE.sha256.startswith("76a7ce886e22")
    assert K21_ORIGIN_PROFILE.sha256.startswith("d1a7fcd8af23")
    assert K22_ORIGIN_PROFILE.sha256.startswith("b4915054edd4")
    assert K19_TIME_SERIES_PROFILE.profile_id == "K19"
    assert K18_AREA_PROFILE.profile_id == "K18"
    assert K21_CORRELATION_MATRIX_PROFILE.profile_id == "K21"
    assert K22_CONTOUR_PROFILE.profile_id == "K22"
    sources = "\n".join(
        inspect.getsource(__import__(item.__module__, fromlist=["*"]))
        for item in (
            K18AreaRenderer,
            K19TimeSeriesRenderer,
            K21CorrelationMatrixRenderer,
            K22ContourRenderer,
            K19OriginProject,
            K18OriginProject,
            K21OriginProject,
            K22OriginProject,
        )
    )
    assert "plotagent.rendering" not in sources
    assert "PlotSpec" not in sources
    assert "ResolvedPlot" not in sources
