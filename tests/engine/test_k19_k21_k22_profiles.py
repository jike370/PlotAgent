from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import plotagent.engine.backends.origin.advanced_matrix as matrix_origin_module
import plotagent.engine.backends.origin.k19 as k19_origin_module
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    SetChartParameter,
)
from plotagent.engine.backends.matplotlib import (
    K19TimeSeriesRenderer,
    K21CorrelationMatrixRenderer,
    K22ContourRenderer,
)
from plotagent.engine.backends.origin import (
    K19_ORIGIN_PROFILE,
    K21_ORIGIN_PROFILE,
    K22_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.advanced_matrix import K21OriginProject, K22OriginProject
from plotagent.engine.backends.origin.k19 import K19OriginProject
from plotagent.engine.profile_data import (
    k19_time_series,
    k21_correlation_grid,
    k22_regular_grid,
)
from plotagent.engine.profiles import (
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
        FieldBinding(role="value", field_id="field:value"),
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
            ("field:value", "Signal", "numeric", (1.0, 1.4, 1.1, 2.0, 1.8)),
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
    k19_document, _k19_actions, k19_view = _k19_case()
    assert k19_time_series(k19_document, k19_view).time_values[0] == datetime(2026, 1, 1, 8)

    k21_document, _k21_actions, k21_view = _k21_case()
    correlation = k21_correlation_grid(k21_document, k21_view)
    assert correlation.row_labels == correlation.column_labels == ("A", "B")
    assert correlation.values == ((1.0, 0.25), (0.25, 1.0))

    k22_document, _k22_actions, k22_view = _k22_case()
    contour = k22_regular_grid(k22_document, k22_view)
    assert contour.x_values == (1.0, 2.0)
    assert contour.y_values == (10.0, 20.0)
    assert contour.z_values == ((1.0, 2.0), (3.0, 4.0))


def test_k19_rejects_non_increasing_time_and_k22_never_interpolates() -> None:
    document, _actions, view = _k19_case()
    repeated = view.model_copy(
        update={
            "columns": (
                view.columns[0].model_copy(
                    update={"values": (datetime(2026, 1, 1),) * len(view.row_ids)}
                ),
                view.columns[1],
            )
        }
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        k19_time_series(document, repeated)

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
        self.limits = (0.0, 1.0, 1.0)

    def set_limits(self, begin=None, end=None, step=None) -> None:
        self.limits = (
            float(self.limits[0] if begin is None else begin),
            float(self.limits[1] if end is None else end),
            float(self.limits[2] if step is None else step),
        )


class FakePlot:
    def __init__(self) -> None:
        self.color = (0, 0, 0)
        self.symbol_kind = 0
        self.symbol_size = 5.0
        self.floats = {"line.width": 1.5}
        self.ints = {"line.style": 0}
        self._zlevels = {"minors": 0, "levels": [0.0, 1.0]}

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


class FakeLayer:
    def __init__(self) -> None:
        self.labels = {"xb": FakeLabel("X"), "yl": FakeLabel("Y")}
        self.axes = {"x": FakeAxis(), "y": FakeAxis()}
        self.plots: list[FakePlot] = []
        self.added_type: int | str | None = None
        self.strings: dict[str, str] = {}

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

    def set_int(self, name: str, value: int) -> None:
        return None

    def set_str(self, name: str, value: str) -> None:
        self.strings[name] = value


class FakeGraph:
    def __init__(self) -> None:
        self.name = "Gdemo"
        self.layer = FakeLayer()

    def __getitem__(self, index: int):
        assert index == 0
        return self.layer


class FakeSheet:
    def __init__(self) -> None:
        self.frame = pd.DataFrame()
        self.values = np.empty((0, 0))
        self.xymap = (0.0, 0.0, 0.0, 0.0)
        self.designation = ""

    def from_df(self, frame: pd.DataFrame) -> None:
        self.frame = frame.copy()

    def to_df(self) -> pd.DataFrame:
        return self.frame.copy()

    def cols_axis(self, value: str) -> None:
        self.designation = value

    def from_np(self, values) -> None:
        self.values = np.asarray(values, dtype=float)

    def to_np2d(self):
        return self.values


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
        self.book_kind = ""
        self.template = ""

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, kind, name, *, hidden):
        self.book_kind = kind
        return self.book

    def new_graph(self, name, *, template, hidden):
        self.graph.name = name
        self.template = template
        return self.graph


def test_origin_profiles_bind_official_templates_and_native_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    k19_document, _actions, k19_view = _k19_case()
    monkeypatch.setattr(
        k19_origin_module,
        "resolve_official_template",
        lambda *_: tmp_path / "LINE.otpu",
    )
    k19_op = FakeOrigin()
    K19OriginProject(k19_op).create(tmp_path, k19_document, k19_view)
    assert Path(k19_op.template).name == "LINE.otpu"
    assert k19_op.book.sheet.designation == "xy"
    assert pd.api.types.is_datetime64_any_dtype(k19_op.book.sheet.frame.iloc[:, 0])

    k21_document, k21_actions, k21_view = _k21_case()
    monkeypatch.setattr(
        matrix_origin_module,
        "resolve_official_template",
        lambda _install, profile: tmp_path / profile.filename,
    )
    k21_op = FakeOrigin()
    k21 = K21OriginProject(k21_op)
    k21.create(tmp_path, k21_document, k21_view)
    k21.reconcile(k21_document, k21_actions, k21_view)
    assert Path(k21_op.template).name == "Heat_Map_With_Labels.otpu"
    assert k21_op.graph.layer.added_type == 105
    assert np.isnan(k21_op.book.sheet.values[0, 1])

    k22_document, k22_actions, k22_view = _k22_case()
    k22_op = FakeOrigin()
    k22 = K22OriginProject(k22_op)
    k22.create(tmp_path, k22_document, k22_view)
    k22.reconcile(k22_document, k22_actions, k22_view)
    assert Path(k22_op.template).name == "CONTOUR.otpu"
    assert k22_op.graph.layer.added_type == 226
    assert len(k22_op.graph.layer.plots[0].zlevels["levels"]) == 13


def test_template_hashes_and_modules_exclude_the_legacy_compiler() -> None:
    assert K19_ORIGIN_PROFILE.sha256.startswith("76a7ce886e22")
    assert K21_ORIGIN_PROFILE.sha256.startswith("d1a7fcd8af23")
    assert K22_ORIGIN_PROFILE.sha256.startswith("b4915054edd4")
    assert K19_TIME_SERIES_PROFILE.profile_id == "K19"
    assert K21_CORRELATION_MATRIX_PROFILE.profile_id == "K21"
    assert K22_CONTOUR_PROFILE.profile_id == "K22"
    sources = "\n".join(
        inspect.getsource(__import__(item.__module__, fromlist=["*"]))
        for item in (
            K19TimeSeriesRenderer,
            K21CorrelationMatrixRenderer,
            K22ContourRenderer,
            K19OriginProject,
            K21OriginProject,
            K22OriginProject,
        )
    )
    assert "plotagent.rendering" not in sources
    assert "PlotSpec" not in sources
    assert "ResolvedPlot" not in sources
