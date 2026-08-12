from __future__ import annotations

import inspect
import json
import subprocess
import sys
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
from plotagent.engine.backends.origin.wide_series import (
    WideSeriesOriginProject,
    read_wide_series_native_snapshot,
)
from plotagent.engine.profile_data import wide_series, x03_lollipop
from plotagent.engine.profiles import X39_LINE_SERIES_PROFILE, X40_BEFORE_AFTER_PROFILE

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


def test_x39_preserves_bound_values_as_source_y_columns() -> None:
    document, _, view = _case("X39", series_count=3, row_count=5)
    data = wide_series(document, view, profile_id="X39")

    assert data.column_labels == ("Measure 1", "Measure 2", "Measure 3")
    assert data.column_values == (
        (1.0, 2.0, 3.0, 4.0, 5.0),
        (2.0, 3.0, 4.0, 5.0, 6.0),
        (3.0, 4.0, 5.0, 6.0, 7.0),
    )
    assert data.row_count == 5


def test_x40_rejects_unpaired_third_value_column() -> None:
    document, _, view = _case("X40", series_count=3)
    with pytest.raises(ValueError, match="exactly two"):
        wide_series(document, view, profile_id="X40")


@pytest.mark.parametrize(
    "profile",
    (X39_LINE_SERIES_PROFILE, X40_BEFORE_AFTER_PROFILE),
)
def test_row_wise_profiles_expose_columns_and_one_connector_group(profile) -> None:
    assert tuple(item.object_alias for item in profile.objects) == (
        "x_axis",
        "y_axis",
        "connector",
        "legend",
    )
    assert profile.objects[2].object_key == "connector"
    assert profile.repeatable_objects[0].object_key_prefix == "column"


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
    if profile_id in {"X39", "X40"}:
        semantic_ids = tuple(item.semantic_id for item in readback.objects)
        token = document.plot_id.removeprefix("plot:")
        assert f"series:{token}.connector" in semantic_ids
        assert tuple(
            semantic_id
            for semantic_id in semantic_ids
            if semantic_id.startswith(f"series:{token}.column_")
        ) == tuple(
            f"series:{token}.column_{index}" for index in range(1, series_count + 1)
        )
        assert not any(".row_" in semantic_id for semantic_id in semantic_ids)


class _Plot:
    def __init__(self, plot_type: int = 206) -> None:
        self.values = {"show": 1, "type": plot_type}

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
        self.name = "G"
        self.lname = ""
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
        self.long_names: dict[int, str] = {}
        self.comments: dict[int, str] = {}
        self.activated = False
        self.categorical_type = 0
        self.categorical_sort = 0

    def from_list(self, index: int, values, **kwargs) -> None:
        self.columns[index] = list(values)
        self.designations[index] = {"X": 4, "Y": 1}.get(kwargs.get("axis"), 2)
        self.long_names[index] = kwargs.get("lname", "")
        self.comments[index] = kwargs.get("comments", "")

    @property
    def cols(self) -> int:
        return len(self.columns)

    def to_list(self, index: int) -> list[object]:
        return self.columns[index]

    def get_int(self, expression: str) -> int:
        index = int(expression.removeprefix("col").removesuffix(".type")) - 1
        return self.designations[index]

    def get_labels(self, kind: str) -> list[str]:
        labels = self.long_names if kind == "L" else self.comments
        return [labels[index] for index in range(self.cols)]

    def activate(self) -> None:
        self.activated = True

    def lt_exec(self, command: str) -> bool:
        assert command == (
            "wks.col1.categorical.type=2; wks.col1.categorical.sort=0;"
        )
        self.categorical_type = 2
        self.categorical_sort = 0
        return True


class _Book:
    def __init__(self) -> None:
        self.name = "D"
        self.sheet = _Sheet()

    def __getitem__(self, index: int) -> _Sheet:
        assert index == 0
        return self.sheet

    def destroy(self) -> None:
        raise AssertionError("authoritative workbook must not be destroyed")


class _Origin:
    def __init__(self) -> None:
        self.book = _Book()
        self.graph = _Graph()
        self.template = ""
        self.commands: list[str] = []
        self.native_member_count = 0
        self.native_plot_type = 0
        self.subgroup_size = 0

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs) -> _Book:
        return self.book

    def new_graph(self, name: str, *, template: str, hidden: bool) -> _Graph:
        self.template = template
        self.graph.name = name
        return self.graph

    def pages(self, kind: str):
        return [self.book] if kind == "w" else [self.graph]

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        if "Lollipop" in command:
            self.graph = _Graph()
            self.graph.layer.plots = [
                _Plot(201) for _index in range(len(self.book.sheet.columns) - 1)
            ]
            self.native_member_count = len(self.graph.layer.plots)
            self.native_plot_type = 201
        elif "run.section(Plot,LineSeries)" in command:
            self.graph = _Graph()
            self.native_member_count = len(self.book.sheet.columns)
            self.native_plot_type = 206
            self.graph.layer.plots = [
                _Plot(206) for _index in range(self.native_member_count)
            ]
        elif "run.section(Plot,BeforeAfter)" in command:
            self.graph = _Graph()
            self.native_member_count = len(self.book.sheet.columns)
            self.native_plot_type = 206
            self.subgroup_size = 2
            self.graph.layer.plots = [
                _Plot(206) for _index in range(self.native_member_count)
            ]
        return True

    def lt_float(self, expression: str) -> float:
        if expression == "__X03CATTYPE":
            return float(self.book.sheet.categorical_type)
        if expression == "__X03CATSORT":
            return float(self.book.sheet.categorical_sort)
        if expression == "__X03COUNT":
            return float(len(self.graph.layer.plots))
        if expression.startswith("__X03PT"):
            return 201.0
        if expression in {"__X39COUNT", "__X40COUNT"}:
            return float(self.native_member_count)
        if expression.startswith(("__X39PT", "__X40PT")):
            return float(self.native_plot_type)
        if expression == "layer.plot1.subgroupsize":
            return float(self.subgroup_size)
        if expression == "layer.plot1.subgrouplabelrow":
            return 0.0
        if expression == "layer.plot1.boxchart.type":
            return 2.0
        if expression == "layer.plot1.usepropssubgroup":
            return 0.0
        if expression == "layer.plot1.color":
            return 1.0
        if expression == "layer.plot1.line.width":
            return 1.2
        if expression == "layer.plot1.line.type":
            return 1.0
        if expression.startswith("layer.plot") and expression.endswith(".color"):
            return 1.0
        if expression.startswith("layer.plot") and expression.endswith(".symbol.kind"):
            return 2.0
        if expression.startswith("layer.plot") and expression.endswith(".symbol.size"):
            return 6.0
        if expression.startswith("layer.plot") and expression.endswith(".pid"):
            return float(self.native_plot_type)
        if expression.startswith("layer.plot") and expression.endswith(".index"):
            index = expression.removeprefix("layer.plot").removesuffix(".index")
            return float(index)
        return 0.0

    def get_lt_str(self, variable: str) -> str:
        prefix = "__X39" if variable.startswith("__X39") else "__X40"
        names = tuple(
            f"{self.book.name}_{chr(ord('A') + index)}"
            for index in range(self.native_member_count or self.book.sheet.cols)
        )
        if variable.startswith(prefix + "SOURCE"):
            index = int(variable.removeprefix(prefix + "SOURCE")) - 1
            return names[index]
        if variable == prefix + "NAMES":
            return "".join(f"|{name}" for name in names)
        if variable == prefix + "MEMBERS":
            return "".join(f"|{index}" for index in range(1, len(names) + 1))
        if variable == prefix + "HEADS":
            return "|1" * len(names)
        return ""


def test_x03_origin_uses_official_lollipop_menu_command_without_xy_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, view = _case("X03", series_count=4, row_count=4)
    resolved: list[str] = []

    def _resolve(_install, selected):
        resolved.append(selected.filename)
        return tmp_path / selected.filename

    monkeypatch.setattr(
        origin_module,
        "resolve_official_template",
        _resolve,
    )
    origin = _Origin()
    project = WideSeriesOriginProject(origin, profile_id="X03")
    project.create(tmp_path, document, view)

    assert resolved == [X03_ORIGIN_PROFILE.filename]
    assert origin.commands[0] == (
        "worksheet -s 1 0 5 0; run.section(Plot,general,201 Lollipop 0);"
    )
    assert "__X03CATTYPE=wks.col1.categorical.type" in origin.commands[1]
    assert "layer -c" in origin.commands[2]
    assert sum("get __X03P -pt" in command for command in origin.commands) == 4
    assert origin.graph.layer.add_calls == []
    assert [plot.get_int("type") for plot in origin.graph.layer.plots] == [201] * 4
    assert origin.book.sheet.designations == {0: 4, 1: 1, 2: 1, 3: 1, 4: 1}


@pytest.mark.parametrize(
    ("profile_id", "profile", "series_count", "expected_command"),
    (
        (
            "X39",
            X39_ORIGIN_PROFILE,
            4,
            "worksheet -s 1 0 4 0; run.section(Plot,LineSeries);",
        ),
        (
            "X40",
            X40_ORIGIN_PROFILE,
            2,
            "worksheet -s 1 0 2 0; run.section(Plot,BeforeAfter);",
        ),
    ),
)
def test_x39_x40_origin_keep_official_wide_table_and_menu_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
    profile,
    series_count: int,
    expected_command: str,
) -> None:
    document, _, view = _case(
        profile_id,
        series_count=series_count,
        row_count=5,
    )
    resolved: list[str] = []

    def _resolve(_install, selected):
        resolved.append(selected.filename)
        return tmp_path / selected.filename

    monkeypatch.setattr(origin_module, "resolve_official_template", _resolve)
    origin = _Origin()
    project = WideSeriesOriginProject(origin, profile_id=profile_id)
    project.create(tmp_path, document, view)

    expected_columns = {
        index: list(view.columns[index].values) for index in range(series_count)
    }
    assert resolved == [profile.filename]
    assert origin.commands[0] == expected_command
    assert origin.template == ""
    assert origin.book.sheet.columns == expected_columns
    assert origin.book.sheet.designations == {index: 1 for index in range(series_count)}
    assert origin.book.sheet.long_names == {
        index: view.columns[index].field.name for index in range(series_count)
    }
    assert origin.book.sheet.comments == {index: "" for index in range(series_count)}
    assert origin.graph.layer.add_calls == []
    assert project.plots == []
    assert project.native_member_count == series_count
    assert project.native_snapshot["native_plot_types"] == (206,) * series_count
    assert project.native_snapshot["source_layout"] == "worksheet_wide"
    assert project.native_snapshot["native_group_count"] == 1
    assert project.native_snapshot["native_group_heads"] == (1,)
    assert project.native_snapshot["members_bind_source_columns"] is True
    assert project.native_snapshot["long_names"] == tuple(
        view.columns[index].field.name for index in range(series_count)
    )
    assert project.native_snapshot["comments"] == ("",) * series_count
    if profile_id == "X40":
        assert project.native_snapshot["subgroup_size"] == 2


@pytest.mark.parametrize(
    ("profile_id", "long_names", "comments", "subgroup_size"),
    (
        ("X39", ("Week1", "Week2", "Week3"), ("", "", ""), 0),
        (
            "X40",
            ("Before", "After", "Before", "After"),
            ("6 to 10", "6 to 10", "11-16", "11-16"),
            2,
        ),
    ),
)
def test_official_sample_snapshot_records_group_and_label_metadata_without_plot_list(
    profile_id: str,
    long_names: tuple[str, ...],
    comments: tuple[str, ...],
    subgroup_size: int,
) -> None:
    origin = _Origin()
    origin.book.name = "Book1"
    origin.native_member_count = len(long_names)
    origin.native_plot_type = 206
    origin.subgroup_size = subgroup_size
    for index, (long_name, comment) in enumerate(
        zip(long_names, comments, strict=True)
    ):
        origin.book.sheet.from_list(
            index,
            [float(index + row) for row in range(5)],
            lname=long_name,
            comments=comment,
            axis="Y",
        )
    snapshot = read_wide_series_native_snapshot(
        origin,
        origin.book.sheet,
        origin.graph,
        profile_id=profile_id,
        column_count=len(long_names),
    )

    assert snapshot["source_layout"] == "worksheet_wide"
    assert snapshot["worksheet_column_count"] == len(long_names)
    assert snapshot["source_row_counts"] == (5,) * len(long_names)
    assert snapshot["long_names"] == long_names
    assert snapshot["comments"] == comments
    assert snapshot["native_plot_types"] == (206,) * len(long_names)
    assert snapshot["native_group_count"] == 1
    assert snapshot["native_group_heads"] == (1,)
    assert snapshot["members_bind_source_columns"] is True
    assert snapshot["subgroup_size"] == subgroup_size
    probe_source = inspect.getsource(read_wide_series_native_snapshot)
    assert "doc -e D" in probe_source
    assert "plot_list(" not in probe_source
    assert "Theme" not in probe_source


def test_x39_x40_matplotlib_use_one_collection_not_one_public_plot_per_row() -> None:
    source = inspect.getsource(origin_module.WideSeriesOriginProject.create)
    matplotlib_source = inspect.getsource(X39LineSeriesRenderer.render) + inspect.getsource(
        X40BeforeAfterRenderer.render
    )

    assert "transposed" not in source
    assert "add_plot" not in source
    assert "_draw_wide_series" in matplotlib_source


def test_x03_matplotlib_draws_follow_plot_segments_not_zero_baseline_stems() -> None:
    source = inspect.getsource(X03LollipopRenderer.render)

    assert ".hlines(" in source
    assert ".vlines(" not in source
    assert "axhline(0.0" not in source


def test_wide_series_new_path_has_no_legacy_compiler_dependency() -> None:
    modules = (X03LollipopRenderer.__module__, WideSeriesOriginProject.__module__)
    source = "\n".join(inspect.getsource(__import__(module, fromlist=["*"])) for module in modules)
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source


def test_x39_x40_live_probe_plan_is_com_free_and_explicit() -> None:
    script = Path(__file__).parents[2] / "scripts" / "probe_x39_x40_origin_live.py"
    result = subprocess.run(
        [sys.executable, str(script), "--phase", "plan"],
        cwd=script.parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)

    assert plan["profiles"]["X39"]["official_menu"] == (
        "run.section(Plot,LineSeries)"
    )
    assert plan["profiles"]["X40"]["official_menu"] == (
        "run.section(Plot,BeforeAfter)"
    )
    assert "fresh" in plan["phases"]
    assert "Connect Within Subgroup" in plan["manual_gate"]
    script_source = script.read_text(encoding="utf-8")
    assert "--allow-origin-com" in script_source
    assert "plot_list(" not in script_source
    assert "Theme" not in script_source
