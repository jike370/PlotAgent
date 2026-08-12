from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.calculated_distribution as origin_module
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
)
from plotagent.engine.backends.matplotlib import K15HistogramRenderer, K16DensityRenderer
from plotagent.engine.backends.origin import K15_ORIGIN_PROFILE, K16_ORIGIN_PROFILE
from plotagent.engine.backends.origin.calculated_distribution import (
    CalculatedDistributionOriginProject,
)
from plotagent.engine.backends.origin.native_distribution import DATA_HEIGHT_TYPE
from plotagent.engine.profile_data import k15_histogram, k16_density
from plotagent.plot_calculations.kernels import histogram_geometry, scott_kde_geometry

HASH = "5" * 64


def _case(profile_id: str, *, grouped: bool = False):
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{profile_id.lower()}",
        version=1,
        content_hash=HASH,
    )
    bindings = [FieldBinding(role="value", field_id="field:value")]
    columns = [
        EngineColumn(
            field=EngineField(
                field_id="field:value",
                name="Measurement",
                logical_type="numeric",
            ),
            values=(1.0, 1.5, 2.0, 2.5, 4.0, 4.5),
        )
    ]
    if grouped:
        bindings.append(FieldBinding(role="group", field_id="field:group"))
        columns.append(
            EngineColumn(
                field=EngineField(
                    field_id="field:group",
                    name="Cohort",
                    logical_type="categorical",
                ),
                values=("A", "A", "A", "B", "B", "B"),
            )
        )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-case",
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
        row_ids=tuple(f"row:{index}" for index in range(6)),
        columns=tuple(columns),
    )
    return document, (create,), view


def test_k15_and_legacy_calculation_share_one_histogram_kernel() -> None:
    document, _, view = _case("K15")
    histogram = k15_histogram(document, view)
    kernel = histogram_geometry((1.0, 1.5, 2.0, 2.5, 4.0, 4.5))

    assert histogram.center == kernel.center
    assert histogram.height == kernel.height
    assert histogram.left == kernel.left
    assert histogram.right == kernel.right


def test_k16_groups_use_the_frozen_scott_kernel() -> None:
    document, _, view = _case("K16", grouped=True)
    density = k16_density(document, view)

    assert tuple(series.label for series in density.series) == ("A", "B")
    assert density.series[0].grid == scott_kde_geometry((1.0, 1.5, 2.0)).grid
    assert density.series[1].density == scott_kde_geometry((2.5, 4.0, 4.5)).density


@pytest.mark.parametrize(
    ("profile_id", "renderer", "grouped"),
    (("K15", K15HistogramRenderer(), False), ("K16", K16DensityRenderer(), True)),
)
def test_calculated_distribution_matplotlib_renderers_accept_raw_observations(
    tmp_path: Path,
    profile_id: str,
    renderer,
    grouped: bool,
) -> None:
    document, actions, view = _case(profile_id, grouped=grouped)
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
    def __init__(self, dataset_name: str = "") -> None:
        self.obj = self
        self.DatasetName = dataset_name
        self.values = {"show": 1}
        self.command = ""

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)

    def set_cmd(self, command: str) -> None:
        self.command = command


class _Label:
    def __init__(self, text: str) -> None:
        self.text = text
        self.values = {"show": 1}

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value


class _Layer:
    def __init__(self) -> None:
        self.plots: list[_Plot] = []
        self.add_calls: list[dict[str, object]] = []
        self.labels = {"XT": _Label(" "), "YR": _Label(" ")}

    def plot_list(self) -> list[_Plot]:
        return self.plots

    def add_plot(self, sheet, **kwargs) -> _Plot:
        coly = kwargs.get("coly")
        dataset_name = "" if coly is None else f"DataBook_Sheet1_{int(coly) + 1}"
        plot = _Plot(dataset_name)
        self.plots.append(plot)
        self.add_calls.append(kwargs)
        return plot

    def rescale(self) -> None:
        return None

    def label(self, name: str):
        return self.labels.get(name)


class _Graph:
    def __init__(self) -> None:
        self.name = "Graph1"
        self.layer = _Layer()
        self.lname = ""

    def __getitem__(self, index: int) -> _Layer:
        assert index == 0
        return self.layer

    def activate(self) -> None:
        return None


class _Sheet:
    def __init__(self, origin: _Origin) -> None:
        self.origin = origin
        self.columns: dict[int, list[object]] = {}
        self.cols = 0
        self.command = ""

    def from_list(self, index: int, values, **kwargs) -> None:
        self.columns[index] = list(values)
        self.cols = max(self.cols, index + 1)

    def activate(self) -> None:
        return None

    def lt_exec(self, command: str) -> None:
        self.command = command
        if "worksheet -p 219 Hist" in command:
            self.origin.graph.layer.add_plot(self, coly=0, colx="#", type=219)


class _Book:
    def __init__(self, origin: _Origin) -> None:
        self.name = "DataBook"
        self.sheet = _Sheet(origin)

    def __getitem__(self, index: int) -> _Sheet:
        assert index == 0
        return self.sheet

    def destroy(self) -> None:
        raise AssertionError("the authoritative data workbook must not be destroyed")


class _Origin:
    def __init__(self) -> None:
        self.graph = _Graph()
        self.book = _Book(self)
        self.template = ""
        self.histogram_values: dict[str, float] = {}

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs) -> _Book:
        return self.book

    def new_graph(self, name: str, *, template: str, hidden: bool) -> _Graph:
        self.template = template
        return self.graph

    def pages(self, kind: str):
        return [self.graph] if kind == "g" else [self.book]

    def lt_exec(self, command: str) -> bool:
        for option, variable in (
            ("-hbb", "__K15BEGIN"),
            ("-hbe", "__K15END"),
            ("-hbs", "__K15SIZE"),
        ):
            marker = f"set __K15P {option} "
            if marker in command:
                self.histogram_values[variable] = float(
                    command.split(marker, 1)[1].split(";", 1)[0]
                )
        return True

    def lt_float(self, expression: str) -> float:
        if expression == "__K15PID":
            return 219.0
        if expression in self.histogram_values:
            return self.histogram_values[expression]
        if expression == "layer.plot1.pid":
            return 219.0
        raise AssertionError(expression)


@pytest.mark.parametrize(
    ("profile_id", "profile", "grouped", "expected_calls"),
    (
        ("K15", K15_ORIGIN_PROFILE, False, 1),
        ("K16", K16_ORIGIN_PROFILE, True, 2),
    ),
)
def test_origin_binders_use_native_origin_geometry_from_raw_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
    profile,
    grouped: bool,
    expected_calls: int,
) -> None:
    document, _, view = _case(profile_id, grouped=grouped)
    monkeypatch.setattr(
        origin_module,
        "resolve_official_template",
        lambda install, selected: tmp_path / selected.filename,
    )
    native_values: dict[tuple[int, int], int | float] = {}

    def configure(_op, _graph, plot_index, native_profile, *, bandwidth=0.0) -> None:
        assert native_profile == 15
        native_values[(plot_index, DATA_HEIGHT_TYPE)] = 0

    def read(_op, _graph, plot_index, theme_id, *, numeric_type):
        return native_values[(plot_index, theme_id)]

    monkeypatch.setattr(origin_module, "configure_native_distribution", configure)
    monkeypatch.setattr(origin_module, "read_native_distribution_value", read)
    origin = _Origin()
    project = CalculatedDistributionOriginProject(origin, profile_id=profile_id)
    project.create(tmp_path, document, view)

    if profile_id == "K15":
        assert origin.template == ""
    else:
        assert Path(origin.template).name == profile.filename
    assert len(origin.graph.layer.add_calls) == expected_calls
    if profile_id == "K15":
        assert origin.book.sheet.command.endswith("worksheet -p 219 Hist;")
        assert origin.graph.layer.add_calls == [
            {"coly": 0, "colx": "#", "type": 219}
        ]
        assert set(origin.book.sheet.columns) == {0}
        assert origin.book.sheet.columns[0] == [1.0, 1.5, 2.0, 2.5, 4.0, 4.5]
        assert origin.graph.layer.labels["XT"].values["show"] == 0
        assert origin.graph.layer.labels["YR"].values["show"] == 0
        histogram = k15_histogram(document, view)
        assert origin.histogram_values == {
            "__K15BEGIN": pytest.approx(histogram.left[0]),
            "__K15END": pytest.approx(histogram.right[-1]),
            "__K15SIZE": pytest.approx(histogram.right[0] - histogram.left[0]),
        }
        assert native_values[(1, DATA_HEIGHT_TYPE)] == 0
    else:
        assert set(origin.book.sheet.columns) == {0, 1, 2, 3}


def test_k15_k16_new_path_has_no_legacy_compiler_dependency() -> None:
    modules = (K15HistogramRenderer.__module__, CalculatedDistributionOriginProject.__module__)
    source = "\n".join(inspect.getsource(__import__(module, fromlist=["*"])) for module in modules)
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
