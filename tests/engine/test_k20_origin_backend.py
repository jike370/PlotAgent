from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

import plotagent.engine.backends.origin.k20 as k20_module
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    SetAxis,
    SetTitle,
)
from plotagent.engine.backends.origin import K20_ORIGIN_PROFILE
from plotagent.engine.backends.origin.k20 import K20OriginProject

HASH = "3" * 64


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


class FakeMatrixPlot:
    pass


class FakeLayer:
    def __init__(self) -> None:
        self.labels = {"xb": FakeLabel("X"), "yl": FakeLabel("Y")}
        self.axes = {"x": FakeAxis(), "y": FakeAxis()}
        self.plots: list[FakeMatrixPlot] = []
        self.ints: dict[str, int] = {}
        self.strings: dict[str, str] = {}
        self.added_type: int | None = None

    def add_mplot(self, sheet, index, *, type):
        assert index == 0
        self.added_type = type
        plot = FakeMatrixPlot()
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
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_str(self, name: str, value: str) -> None:
        self.strings[name] = value

    def get_str(self, name: str) -> str:
        return self.strings[name]


class FakeGraph:
    def __init__(self) -> None:
        self.name = "Gheatmap"
        self.layer = FakeLayer()

    def __getitem__(self, index: int):
        assert index == 0
        return self.layer


class FakeMatrixSheet:
    def __init__(self) -> None:
        self.values = np.empty((0, 0))
        self.xymap = (0.0, 0.0, 0.0, 0.0)

    def from_np(self, values) -> None:
        self.values = np.asarray(values, dtype=float)

    def to_np2d(self):
        return self.values


class FakeMatrixBook:
    def __init__(self) -> None:
        self.sheet = FakeMatrixSheet()

    def __getitem__(self, index: int):
        assert index == 0
        return self.sheet


class FakeOrigin:
    def __init__(self) -> None:
        self.book = FakeMatrixBook()
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


def _case():
    data_ref = EngineDataRef(
        kind="source",
        dataset_id="dataset.matrix",
        version=1,
        content_hash=HASH,
    )
    create = CreatePlot(
        action_id="action:create-matrix",
        plot_id="plot:origin-heatmap",
        profile_id="K20",
        data=data_ref,
        bindings=(
            FieldBinding(role="row", field_id="field:row"),
            FieldBinding(role="column", field_id="field:column"),
            FieldBinding(role="value", field_id="field:value"),
        ),
    )
    view = EngineDataView(
        data=data_ref,
        row_ids=("row:1", "row:2", "row:3", "row:4"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:row",
                    name="Protein",
                    logical_type="categorical",
                ),
                values=("P2", "P1", "P2", "P1"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:column",
                    name="Condition",
                    logical_type="categorical",
                ),
                values=("Control", "Control", "Drug", "Drug"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:value",
                    name="Expression",
                    logical_type="numeric",
                ),
                values=(2.0, 1.0, 4.0, 3.0),
            ),
        ),
    )
    actions = (
        create,
        SetTitle(
            action_id="action:matrix-title",
            target=create.plot_id,
            expected_plot_version=1,
            text="Native heatmap",
        ),
        SetAxis(
            action_id="action:matrix-axis",
            target="axis:origin-heatmap.y",
            expected_plot_version=2,
            label="Protein ID",
            reverse=True,
        ),
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=3,
        parent_version=2,
        profile_id="K20",
        data=data_ref,
        bindings=create.bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    return document, actions, view


def test_k20_binder_uses_official_template_and_native_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, actions, view = _case()
    template = tmp_path / K20_ORIGIN_PROFILE.filename
    monkeypatch.setattr(k20_module, "resolve_official_template", lambda install, profile: template)
    op = FakeOrigin()
    project = K20OriginProject(op)
    project.create(tmp_path, document, view)
    for action in actions:
        project.apply(document, action, view)
    project.reconcile(document, actions, view)
    readback = project.verify(document, actions, view)

    assert readback.document.plot_version == 3
    assert op.book_kind == "m"
    assert Path(op.template).name.casefold() == K20_ORIGIN_PROFILE.filename.casefold()
    assert op.graph.layer.added_type == 105
    assert op.book.sheet.values.tolist() == [[2.0, 4.0], [1.0, 3.0]]
    assert op.graph.layer.strings["x.label.string"] == '"Control" "Drug"'
    assert op.graph.layer.strings["y.label.string"] == '"P2" "P1"'
    assert op.graph.layer.axes["y"].limits == (0.5, 2.5, 1.0)


def test_k20_template_identity_is_pinned_to_heat_map_otpu() -> None:
    assert K20_ORIGIN_PROFILE.filename == "Heat_Map.otpu"
    assert K20_ORIGIN_PROFILE.sha256 == (
        "9bd8240ca582bbedfec797ea27b1ec5c2906939e304fa343cd1821bae2ffbb9f"
    )


def test_k20_origin_binder_has_no_legacy_plan_or_renderer_import() -> None:
    source = inspect.getsource(__import__(K20OriginProject.__module__, fromlist=["*"]))
    assert "plotagent.origin" not in source
    assert "OriginPlan" not in source
    assert "ResolvedPlot" not in source
