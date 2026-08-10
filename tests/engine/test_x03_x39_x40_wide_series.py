from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.wide_series as origin_module
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
)
from plotagent.engine.backends.matplotlib import (
    X03LollipopRenderer,
    X39LineSeriesRenderer,
    X40BeforeAfterRenderer,
)
from plotagent.engine.backends.origin import (
    X03_ORIGIN_PROFILE,
    X39_ORIGIN_PROFILE,
    X40_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.wide_series import WideSeriesOriginProject
from plotagent.engine.profile_data import transposed_series, x03_lollipop

HASH = "6" * 64


def _case(profile_id: str, *, series_count: int = 2, row_count: int = 4):
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{profile_id.lower()}",
        version=1,
        content_hash=HASH,
    )
    bindings: list[FieldBinding] = []
    columns: list[EngineColumn] = []
    if profile_id == "X03":
        bindings.append(FieldBinding(role="category", field_id="field:category"))
        columns.append(
            EngineColumn(
                field=EngineField(
                    field_id="field:category",
                    name="Sample",
                    logical_type="categorical",
                ),
                values=tuple(f"C{index}" for index in range(1, row_count + 1)),
            )
        )
    for index in range(1, series_count + 1):
        bindings.append(FieldBinding(role=f"series_{index}", field_id=f"field:s{index}"))
        columns.append(
            EngineColumn(
                field=EngineField(
                    field_id=f"field:s{index}",
                    name=(
                        ("Before", "After")[index - 1]
                        if profile_id == "X40" and index <= 2
                        else f"Measure {index}"
                    ),
                    logical_type="numeric",
                ),
                values=tuple(float(row + index) for row in range(row_count)),
            )
        )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-wide",
        profile_id=profile_id,
        data=data,
        bindings=tuple(bindings),
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id=profile_id,
        data=data,
        bindings=tuple(bindings),
        applied_action_ids=(create.action_id,),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(row_count)),
        columns=tuple(columns),
    )
    return document, (create,), view


def test_x03_accepts_contiguous_dynamic_series_columns() -> None:
    document, _, view = _case("X03", series_count=4, row_count=3)
    data = x03_lollipop(document, view)

    assert data.categories == ("C1", "C2", "C3")
    assert data.columns.labels == ("Measure 1", "Measure 2", "Measure 3", "Measure 4")
    assert len(data.columns.values) == 4


def test_x39_transposes_each_source_row_into_one_series() -> None:
    document, _, view = _case("X39", series_count=3, row_count=5)
    data = transposed_series(document, view, profile_id="X39")

    assert data.axis_labels == ("Measure 1", "Measure 2", "Measure 3")
    assert len(data.rows) == 5
    assert data.rows[0] == (1.0, 2.0, 3.0)


def test_x40_rejects_unpaired_third_value_column() -> None:
    document, _, view = _case("X40", series_count=3)
    with pytest.raises(ValueError, match="exactly two"):
        transposed_series(document, view, profile_id="X40")


@pytest.mark.parametrize(
    ("profile_id", "renderer", "series_count"),
    (
        ("X03", X03LollipopRenderer(), 4),
        ("X39", X39LineSeriesRenderer(), 3),
        ("X40", X40BeforeAfterRenderer(), 2),
    ),
)
def test_wide_series_matplotlib_renderers_follow_dynamic_data(
    tmp_path: Path,
    profile_id: str,
    renderer,
    series_count: int,
) -> None:
    document, actions, view = _case(profile_id, series_count=series_count)
    readback = renderer.render(
        document,
        actions,
        view,
        tmp_path / f"{profile_id}.png",
        tmp_path / f"{profile_id}.svg",
    )

    assert readback.document.plot_id == document.plot_id
    assert (tmp_path / f"{profile_id}.png").stat().st_size > 0
    assert (tmp_path / f"{profile_id}.svg").stat().st_size > 0


class _Plot:
    def __init__(self) -> None:
        self.values = {"show": 1}

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)


class _Layer:
    def __init__(self) -> None:
        self.plots: list[_Plot] = []
        self.add_calls: list[dict[str, object]] = []
        self.values: dict[str, object] = {}

    def plot_list(self) -> list[_Plot]:
        return self.plots

    def add_plot(self, sheet, **kwargs) -> _Plot:
        plot = _Plot()
        self.plots.append(plot)
        self.add_calls.append(kwargs)
        return plot

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def set_str(self, name: str, value: str) -> None:
        self.values[name] = value

    def rescale(self) -> None:
        return None


class _Graph:
    def __init__(self) -> None:
        self.layer = _Layer()

    def __getitem__(self, index: int) -> _Layer:
        assert index == 0
        return self.layer


class _Sheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}

    def from_list(self, index: int, values, **kwargs) -> None:
        self.columns[index] = list(values)


class _Book:
    def __init__(self) -> None:
        self.sheet = _Sheet()

    def __getitem__(self, index: int) -> _Sheet:
        assert index == 0
        return self.sheet


class _Origin:
    def __init__(self) -> None:
        self.book = _Book()
        self.graph = _Graph()
        self.template = ""

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs) -> _Book:
        return self.book

    def new_graph(self, name: str, *, template: str, hidden: bool) -> _Graph:
        self.template = template
        return self.graph


@pytest.mark.parametrize(
    ("profile_id", "profile", "series_count", "expected_plots"),
    (
        ("X03", X03_ORIGIN_PROFILE, 4, 4),
        ("X39", X39_ORIGIN_PROFILE, 3, 4),
        ("X40", X40_ORIGIN_PROFILE, 2, 4),
    ),
)
def test_wide_series_origin_binders_use_official_template_and_dynamic_native_plots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
    profile,
    series_count: int,
    expected_plots: int,
) -> None:
    document, _, view = _case(profile_id, series_count=series_count, row_count=4)
    monkeypatch.setattr(
        origin_module,
        "resolve_official_template",
        lambda install, selected: tmp_path / selected.filename,
    )
    origin = _Origin()
    project = WideSeriesOriginProject(origin, profile_id=profile_id)
    project.create(tmp_path, document, view)

    assert Path(origin.template).name == profile.filename
    assert len(origin.graph.layer.add_calls) == expected_plots
    assert all(call["type"] == "?" for call in origin.graph.layer.add_calls)


def test_wide_series_new_path_has_no_legacy_compiler_dependency() -> None:
    modules = (X03LollipopRenderer.__module__, WideSeriesOriginProject.__module__)
    source = "\n".join(inspect.getsource(__import__(module, fromlist=["*"])) for module in modules)
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
