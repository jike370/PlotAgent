from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.k01 as k01_module
import plotagent.engine.backends.origin.k08 as k08_module
from plotagent.contracts.canonical import canonical_hash
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.backends.origin import (
    K01_ORIGIN_PROFILE,
    K08_ORIGIN_PROFILE,
    OriginBackend,
    resolve_official_template,
)
from plotagent.engine.backends.origin.k01 import K01OriginProject
from plotagent.engine.backends.origin.k08 import K08OriginProject
from plotagent.engine.backends.origin.messages import OriginWorkerResponse
from plotagent.engine.ports import EngineReadback
from plotagent.engine.repository import document_ref

HASH = "1" * 64
STYLE_HASH = "2" * 64


def _objects():
    return ()


def _document() -> tuple[PlotDocument, CreatePlot, EngineDataView]:
    data_ref = EngineDataRef(
        kind="source",
        dataset_id="dataset.demo",
        version=1,
        content_hash=HASH,
    )
    action = CreatePlot(
        action_id="action:create",
        plot_id="plot:origin-line",
        profile_id="K01",
        data=data_ref,
        bindings=(
            FieldBinding(role="x", field_id="field:x"),
            FieldBinding(role="y", field_id="field:y"),
        ),
    )
    document = PlotDocument(
        plot_id=action.plot_id,
        plot_version=1,
        profile_id="K01",
        data=data_ref,
        bindings=action.bindings,
        applied_action_ids=(action.action_id,),
    )
    view = EngineDataView(
        data=data_ref,
        row_ids=("row:1", "row:2"),
        columns=(
            EngineColumn(
                field=EngineField(field_id="field:x", name="X", logical_type="numeric"),
                values=(1.0, 2.0),
            ),
            EngineColumn(
                field=EngineField(field_id="field:y", name="Y", logical_type="numeric"),
                values=(3.0, 4.0),
            ),
        ),
    )
    return document, action, view


class Worker:
    def __init__(self) -> None:
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        Path(request.output_opju).write_bytes(b"fake-opju")
        return OriginWorkerResponse(
            readback=EngineReadback(
                document=document_ref(request.document),
                backend="origin",
                objects=_objects(),
                data_hash=canonical_hash(request.data),
                style_hash=STYLE_HASH,
            )
        )


def test_official_template_resolution_is_hash_pinned(tmp_path: Path) -> None:
    template = tmp_path / K01_ORIGIN_PROFILE.filename
    template.write_bytes(b"official-template")
    profile = K01_ORIGIN_PROFILE.model_copy(
        update={"sha256": __import__("hashlib").sha256(template.read_bytes()).hexdigest()}
    )
    assert resolve_official_template(tmp_path, profile) == template
    template.write_bytes(b"modified")
    try:
        resolve_official_template(tmp_path, profile)
    except ValueError as error:
        assert "hash differs" in str(error)
    else:  # pragma: no cover
        raise AssertionError("modified official template was accepted")


def test_origin_backend_stages_opju_without_legacy_plan(tmp_path: Path) -> None:
    document, action, view = _document()
    worker = Worker()
    backend = OriginBackend(tmp_path / "origin", tmp_path / "install", worker)
    change = backend.stage(document, (action,), view)

    assert worker.requests[0].document == document
    assert worker.requests[0].data == view
    change.publish()
    change.finalize()
    target = tmp_path / "origin" / "origin-line" / "v1" / "plot.opju"
    assert target.read_bytes() == b"fake-opju"
    exported = backend.export(document, tmp_path / "export.opju", "opju")
    assert exported.artifact_size == len(b"fake-opju")


def test_k01_origin_binder_has_no_legacy_plan_or_renderer_import() -> None:
    source = inspect.getsource(__import__(K01OriginProject.__module__, fromlist=["*"]))
    assert "plotagent.origin" not in source
    assert "OriginPlan" not in source
    assert "ResolvedPlot" not in source


class FakeLabel:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.name = ""
        self.values: dict[str, int] = {"show": 1}

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = value

    def get_int(self, name: str) -> int:
        return self.values.get(name, 0)


class FakeAxis:
    def __init__(self) -> None:
        self.scale = "linear"
        self.limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin=None, end=None, step=None) -> None:
        self.limits = (
            float(self.limits[0] if begin is None else begin),
            float(self.limits[1] if end is None else end),
            float(self.limits[2] if step is None else step),
        )


class FakePlot:
    def __init__(self) -> None:
        self._color = (22, 118, 210)
        self.floats = {"line.width": 1.5}
        self.ints = {"line.style": 0}

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

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints[name]


class FakeLayer:
    def __init__(self) -> None:
        self.obj = self
        self.labels = {"xb": FakeLabel("X"), "yl": FakeLabel("Y")}
        self.axes = {"x": FakeAxis(), "y": FakeAxis()}
        self.plots: list[FakePlot] = []

    def add_plot(self, sheet, *, coly, colx, type):
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
        assert command == "legend"
        self.labels["legend"] = FakeLabel()
        return True


class FakeGraph:
    def __init__(self, name: str) -> None:
        self.name = name
        self.layer = FakeLayer()

    def __getitem__(self, index: int):
        assert index == 0
        return self.layer


class FakeSheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}

    def from_list(self, col, data, **kwargs) -> None:
        self.columns[col] = list(data)

    def to_list(self, col):
        return self.columns[col]


class FakeBook:
    def __init__(self) -> None:
        self.sheet = FakeSheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet


class FakeOrigin:
    def __init__(self) -> None:
        self.book = FakeBook()
        self.graph = FakeGraph("Gline")

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, *args, **kwargs):
        return self.book

    def new_graph(self, name, **kwargs):
        self.graph.name = name
        return self.graph


def test_k01_binder_applies_typed_actions_to_native_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, create, view = _document()
    actions = (
        create,
        SetTitle(
            action_id="action:title",
            target=document.plot_id,
            expected_plot_version=1,
            text="Native line",
        ),
        SetAxis(
            action_id="action:axis",
            target="axis:origin-line.y",
            expected_plot_version=2,
            label="Response",
            scale="log10",
            minimum=1.0,
            maximum=10.0,
        ),
        SetSeriesStyle(
            action_id="action:style",
            target="series:origin-line.primary",
            expected_plot_version=3,
            color="#AA2200",
            line_width_pt=2.0,
            line_style="dash",
        ),
        SetLegend(
            action_id="action:legend",
            target="legend:origin-line.main",
            expected_plot_version=4,
            visible=True,
        ),
    )
    document = document.model_copy(
        update={
            "plot_version": 5,
            "parent_version": 4,
            "applied_action_ids": tuple(action.action_id for action in actions),
        }
    )
    monkeypatch.setattr(
        k01_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / "LINE.otpu",
    )
    op = FakeOrigin()
    project = K01OriginProject(op)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert readback.document.plot_version == 5
    assert op.graph.layer.axes["y"].scale == "log10"
    assert op.graph.layer.plots[0].color == (170, 34, 0)
    assert op.graph.layer.labels["legend"].get_int("show") == 1


def test_k08_binder_uses_column_template_and_native_column_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_ref = EngineDataRef(
        kind="source",
        dataset_id="dataset.column",
        version=1,
        content_hash=HASH,
    )
    create = CreatePlot(
        action_id="action:create-column",
        plot_id="plot:origin-column",
        profile_id="K08",
        data=data_ref,
        bindings=(
            FieldBinding(role="category", field_id="field:category"),
            FieldBinding(role="value", field_id="field:value"),
        ),
    )
    view = EngineDataView(
        data=data_ref,
        row_ids=("row:1", "row:2"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:category",
                    name="Condition",
                    logical_type="categorical",
                ),
                values=("A", "B"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:value",
                    name="Response",
                    logical_type="numeric",
                ),
                values=(3.0, 5.0),
            ),
        ),
    )
    actions = (
        create,
        SetTitle(
            action_id="action:column-title",
            target=create.plot_id,
            expected_plot_version=1,
            text="Native column",
        ),
        SetAxis(
            action_id="action:column-axis",
            target="axis:origin-column.y",
            expected_plot_version=2,
            label="Response",
            minimum=0,
            maximum=6,
        ),
        SetSeriesStyle(
            action_id="action:column-style",
            target="series:origin-column.primary",
            expected_plot_version=3,
            color="#3366CC",
            line_width_pt=1.0,
        ),
        SetLegend(
            action_id="action:column-legend",
            target="legend:origin-column.main",
            expected_plot_version=4,
            visible=True,
        ),
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=5,
        parent_version=4,
        profile_id="K08",
        data=data_ref,
        bindings=create.bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    monkeypatch.setattr(
        k08_module,
        "resolve_official_template",
        lambda install, profile: tmp_path / K08_ORIGIN_PROFILE.filename,
    )
    op = FakeOrigin()
    project = K08OriginProject(op)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    readback = project.verify(document, actions, view)

    assert readback.document.plot_version == 5
    assert op.graph.layer.plots[0].color == (51, 102, 204)
    assert op.graph.layer.labels["legend"].text.startswith("\\l(1, style:b)")


def test_k08_template_identity_is_pinned_to_column_otpu() -> None:
    assert K08_ORIGIN_PROFILE.filename == "COLUMN.otpu"
    assert K08_ORIGIN_PROFILE.sha256 == (
        "ec9e654e886056a466c3447afeab950d371ac6f297d5e325b25e99b7a3d769cd"
    )
