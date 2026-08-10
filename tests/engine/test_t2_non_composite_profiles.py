from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

import plotagent.engine.backends.origin.s61 as s61_origin
import plotagent.engine.backends.origin.scientific_t2 as scientific_origin
import plotagent.engine.backends.origin.structural_t2 as structural_origin
from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
)
from plotagent.engine.backends.matplotlib import (
    K24FacetRenderer,
    MatplotlibBackend,
    S01SurvivalRenderer,
    S21ForestRenderer,
    S34NyquistRenderer,
    S61ConfusionRenderer,
)
from plotagent.engine.backends.origin import (
    K24_ORIGIN_PROFILE,
    S01_ORIGIN_PROFILE,
    S21_ORIGIN_PROFILE,
    S34_ORIGIN_PROFILE,
    S61_ORIGIN_PROFILE,
)
from plotagent.engine.backends.origin.s61 import S61OriginProject
from plotagent.engine.backends.origin.scientific_t2 import S21OriginProject, S34OriginProject
from plotagent.engine.backends.origin.structural_t2 import K24OriginProject, S01OriginProject
from plotagent.engine.profile_data import (
    k24_facets,
    s01_survival,
    s21_forest,
    s34_nyquist,
    s61_confusion_grid,
)
from plotagent.engine.profiles import (
    K24_FACET_PROFILE,
    S01_SURVIVAL_PROFILE,
    S21_FOREST_PROFILE,
    S34_NYQUIST_PROFILE,
    S61_CONFUSION_PROFILE,
)

HASH = "9" * 64


def _case(profile_id: str, columns: tuple[tuple[str, str, str, str, tuple[object, ...]], ...]):
    data = EngineDataRef(
        kind="source", dataset_id=f"dataset.{profile_id.lower()}", version=1, content_hash=HASH
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=field_id)
        for role, field_id, _name, _logical_type, _values in columns
    )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-t2",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=(create.action_id,),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(len(columns[0][4]))),
        columns=tuple(
            EngineColumn(
                field=EngineField(
                    field_id=field_id,
                    name=name,
                    logical_type=logical_type,  # type: ignore[arg-type]
                ),
                values=values,
            )
            for _role, field_id, name, logical_type, values in columns
        ),
    )
    return document, (create,), view


def _k24_case(panel_count: int = 3):
    labels = tuple(f"Panel {index + 1}" for index in range(panel_count) for _point in range(4))
    x = tuple(float(point) for _panel in range(panel_count) for point in range(4))
    y = tuple(float(panel * 10 + point) for panel in range(panel_count) for point in range(4))
    return _case(
        "K24",
        (
            ("facet", "field:facet", "Condition", "categorical", labels),
            ("base_x", "field:x", "Time", "numeric", x),
            ("base_y", "field:y", "Signal", "numeric", y),
        ),
    )


def _s01_case(group_count: int = 2):
    groups = tuple(f"Group {index + 1}" for index in range(group_count) for _time in range(4))
    time = tuple(float(value) for _group in range(group_count) for value in (0, 2, 4, 6))
    survival = tuple(
        max(0.1, 1.0 - 0.1 * group - 0.12 * point)
        for group in range(group_count)
        for point in range(4)
    )
    lower = tuple(max(0.0, value - 0.05) for value in survival)
    upper = tuple(min(1.0, value + 0.05) for value in survival)
    risk = tuple(
        max(0, 40 - group * 4 - point * 6) for group in range(group_count) for point in range(4)
    )
    return _case(
        "S01",
        (
            ("time", "field:time", "Time", "numeric", time),
            ("survival", "field:survival", "Survival", "numeric", survival),
            ("lower", "field:lower", "Lower", "numeric", lower),
            ("upper", "field:upper", "Upper", "numeric", upper),
            ("risk_count", "field:risk", "At risk", "numeric", risk),
            ("group", "field:group", "Group", "categorical", groups),
        ),
    )


def _s21_case(studies: int = 5):
    effect = tuple(0.7 + index * 0.08 for index in range(studies))
    return _case(
        "S21",
        (
            (
                "label",
                "field:label",
                "Study",
                "categorical",
                tuple(f"Study {i + 1}" for i in range(studies)),
            ),
            ("effect", "field:effect", "Effect", "numeric", effect),
            ("lower", "field:lower", "Lower", "numeric", tuple(value - 0.12 for value in effect)),
            ("upper", "field:upper", "Upper", "numeric", tuple(value + 0.16 for value in effect)),
            (
                "weight",
                "field:weight",
                "Weight",
                "numeric",
                tuple(float(i + 1) for i in range(studies)),
            ),
        ),
    )


def _s34_case(series_count: int = 3):
    labels = tuple(f"Cell {index + 1}" for index in range(series_count) for _point in range(5))
    real = tuple(float(point + series) for series in range(series_count) for point in range(5))
    imaginary = tuple(
        float((point + 1) * (5 - point) + series)
        for series in range(series_count)
        for point in range(5)
    )
    frequency = tuple(
        float(10000 / (point + 1)) for _series in range(series_count) for point in range(5)
    )
    return _case(
        "S34",
        (
            ("z_real", "field:real", "Z real", "numeric", real),
            ("z_imaginary", "field:imag", "-Z imaginary", "numeric", imaginary),
            ("frequency", "field:frequency", "Frequency", "numeric", frequency),
            ("series", "field:series", "Cell", "categorical", labels),
        ),
    )


def _s61_case(*, aggregated: bool = True):
    actual = ("Cat", "Cat", "Dog", "Dog", "Bird", "Bird")
    predicted = ("Cat", "Dog", "Cat", "Dog", "Cat", "Bird")
    columns: list[tuple[str, str, str, str, tuple[object, ...]]] = [
        ("actual", "field:actual", "Actual", "categorical", actual),
        ("predicted", "field:predicted", "Predicted", "categorical", predicted),
    ]
    if aggregated:
        columns.append(("count", "field:count", "Count", "numeric", (42, 4, 5, 38, 5, 34)))
    return _case("S61", tuple(columns))


@pytest.mark.parametrize("panel_count", (2, 3, 5))
def test_k24_materializes_dynamic_facets(panel_count: int) -> None:
    document, _actions, view = _k24_case(panel_count)
    facets = k24_facets(document, view)
    assert len(facets.panels) == panel_count
    assert all(len(panel.x_values) == 4 for panel in facets.panels)


@pytest.mark.parametrize("group_count", (1, 2, 4))
def test_s01_preserves_precomputed_steps_bands_and_risk(group_count: int) -> None:
    document, _actions, view = _s01_case(group_count)
    survival = s01_survival(document, view)
    assert len(survival.groups) == group_count
    assert survival.groups[-1].risk_count is not None
    assert survival.groups[-1].lower is not None


@pytest.mark.parametrize("studies", (3, 11))
def test_s21_preserves_supplied_effect_intervals_and_weight(studies: int) -> None:
    document, _actions, view = _s21_case(studies)
    forest = s21_forest(document, view)
    assert len(forest.labels) == studies
    assert forest.lower[0] < forest.effect[0] < forest.upper[0]


@pytest.mark.parametrize("series_count", (1, 4, 5))
def test_s34_preserves_frequency_as_metadata_for_dynamic_series(series_count: int) -> None:
    document, _actions, view = _s34_case(series_count)
    nyquist = s34_nyquist(document, view)
    assert len(nyquist.series) == series_count
    assert nyquist.series[-1].frequency is not None


def test_s61_accepts_raw_samples_and_preaggregated_integer_counts() -> None:
    raw_document, _actions, raw_view = _s61_case(aggregated=False)
    raw = s61_confusion_grid(raw_document, raw_view)
    assert sum(sum(row) for row in raw.values) == 6
    document, _actions, view = _s61_case(aggregated=True)
    aggregated = s61_confusion_grid(document, view)
    assert aggregated.values[0] == (42.0, 4.0, 0.0)
    assert sum(sum(row) for row in aggregated.values) == 128


@pytest.mark.parametrize(
    ("renderer", "case", "object_kind"),
    (
        (K24FacetRenderer(), _k24_case, "facet_series"),
        (S01SurvivalRenderer(), _s01_case, "survival_step_series"),
        (S21ForestRenderer(), _s21_case, "forest_intervals"),
        (S34NyquistRenderer(), _s34_case, "nyquist_series"),
        (S61ConfusionRenderer(), _s61_case, "confusion_matrix"),
    ),
)
def test_t2_matplotlib_renderers_are_independent_and_semantic(
    tmp_path: Path, renderer, case, object_kind: str
) -> None:
    document, actions, view = case()
    backend = MatplotlibBackend(tmp_path / renderer.profile_id, (renderer,))
    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()
    assert any(item.object_kind == object_kind for item in change.readback.objects)
    target = tmp_path / renderer.profile_id / document.plot_id.removeprefix("plot:") / "v1"
    assert (target / "preview.png").stat().st_size > 1_000
    assert (target / "preview.svg").stat().st_size > 1_000


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


class _Axis:
    def __init__(self) -> None:
        self.limits = (0.0, 10.0, 1.0)

    def set_limits(self, begin=None, end=None, step=None) -> None:
        self.limits = (
            float(self.limits[0] if begin is None else begin),
            float(self.limits[1] if end is None else end),
            float(self.limits[2] if step is None else step),
        )


class _Plot:
    def __init__(self, plot_type: object) -> None:
        self.plot_type = plot_type
        self.ints = {"show": 1, "label.show": 1}
        self.floats: dict[str, float] = {}
        self.color: object = "#000000"
        self.symbol_kind = 1
        self.symbol_size = 6.0

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value

    def set_fill_area(self, **kwargs) -> None:
        self.fill = kwargs


class _Layer:
    def __init__(self) -> None:
        self.obj = self
        self.plots: list[_Plot] = []
        self.labels = {"xb": _Label("X"), "yl": _Label("Y")}
        self.axes = {"x": _Axis(), "y": _Axis()}
        self.ints: dict[str, int] = {}
        self.strings: dict[str, str] = {}
        self.layout = ""

    def add_plot(self, sheet, *, coly, colx, type):
        plot = _Plot(type)
        self.plots.append(plot)
        return plot

    def add_mplot(self, sheet, index, *, type):
        plot = _Plot(type)
        self.plots.append(plot)
        return plot

    def plot_list(self):
        return self.plots

    def axis(self, name: str):
        return self.axes[name]

    def label(self, name: str):
        return self.labels.get(name) or next(
            (label for label in self.labels.values() if label.name == name), None
        )

    def add_label(self, text: str, x=None, y=None):
        label = _Label(text)
        self.labels[f"new-{len(self.labels)}"] = label
        return label

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def set_str(self, name: str, value: str) -> None:
        self.strings[name] = value

    def rescale(self) -> None:
        return None

    def lt_exec(self, command: str) -> None:
        self.layout = command

    def activate(self) -> None:
        return None

    def LT_execute(self, command: str) -> bool:
        self.labels["legend"] = _Label()
        return True


class _Graph:
    def __init__(self, layers: int) -> None:
        self.name = "GT2"
        self.layers = [_Layer() for _index in range(layers)]

    def __iter__(self):
        return iter(self.layers)

    def __getitem__(self, index: int):
        return self.layers[index]

    def add_layer(self, _kind: int) -> None:
        self.layers.append(_Layer())


class _Sheet:
    def __init__(self) -> None:
        self.columns: dict[int, list[object]] = {}
        self.matrix = np.empty((0, 0))
        self.xymap = (0.0, 1.0, 0.0, 1.0)

    def from_list(self, index, values, **kwargs) -> None:
        self.columns[index] = list(values)

    def to_list(self, index):
        return self.columns[index]

    def from_np(self, values) -> None:
        self.matrix = np.asarray(values)

    def to_np2d(self):
        return self.matrix


class _Book:
    def __init__(self) -> None:
        self.sheet = _Sheet()

    def __getitem__(self, index: int):
        return self.sheet


class _Origin:
    def __init__(self) -> None:
        self.book = _Book()
        self.graph = _Graph(1)

    def new(self, *, asksave: bool) -> None:
        return None

    def new_book(self, kind, name, *, hidden):
        self.book = _Book()
        return self.book

    def new_graph(self, name, *, template, hidden):
        layers = 2 if "survival" in template.lower() else 1
        self.graph = _Graph(layers)
        self.graph.name = name
        return self.graph


@pytest.mark.parametrize("panel_count", (2, 3, 5))
def test_origin_k24_uses_dynamic_native_template_layers(monkeypatch, panel_count: int) -> None:
    monkeypatch.setattr(
        structural_origin, "resolve_official_template", lambda *_: Path("mgroups.otpu")
    )
    document, actions, view = _k24_case(panel_count)
    project = K24OriginProject(_Origin())
    project.create(Path("."), document, view)
    project.reconcile(document, actions, view)
    assert len(project.plots) == panel_count
    assert all(plot.plot_type == 200 for plot in project.plots)


def test_origin_s01_keeps_native_steps_bands_and_editable_risk_labels(monkeypatch) -> None:
    monkeypatch.setattr(
        structural_origin, "resolve_official_template", lambda *_: Path("SurvivalPlot.otp")
    )
    document, actions, view = _s01_case(2)
    project = S01OriginProject(_Origin())
    project.create(Path("."), document, view)
    project.reconcile(document, actions, view)
    assert len(project.plots) == 6
    assert any(
        label.name.startswith("_ENGINE_RISK_") for label in project._layers()[1].labels.values()
    )


def test_origin_s21_and_s34_use_native_dynamic_plots(monkeypatch) -> None:
    monkeypatch.setattr(
        scientific_origin, "resolve_official_template", lambda *_: Path("template.otp")
    )
    document, actions, view = _s21_case(5)
    forest = S21OriginProject(_Origin())
    forest.create(Path("."), document, view)
    forest.reconcile(document, actions, view)
    assert len(forest.plots) == 7

    document, actions, view = _s34_case(4)
    nyquist = S34OriginProject(_Origin())
    nyquist.create(Path("."), document, view)
    nyquist.reconcile(document, actions, view)
    assert len(nyquist.plots) == 4
    assert all(plot.plot_type == 202 for plot in nyquist.plots)


def test_origin_s61_writes_one_native_labeled_matrix(monkeypatch) -> None:
    monkeypatch.setattr(
        s61_origin, "resolve_official_template", lambda *_: Path("Heat_Map_With_Labels.otpu")
    )
    document, actions, view = _s61_case()
    project = S61OriginProject(_Origin())
    project.create(Path("."), document, view)
    project.reconcile(document, actions, view)
    assert project.plot.plot_type == 105
    assert project.sheet.matrix.tolist()[0] == [42.0, 4.0, 0.0]


def test_t2_profiles_pin_templates_and_do_not_import_old_compiler() -> None:
    assert {
        profile.profile_id: profile.sha256
        for profile in (
            K24_ORIGIN_PROFILE,
            S01_ORIGIN_PROFILE,
            S21_ORIGIN_PROFILE,
            S34_ORIGIN_PROFILE,
            S61_ORIGIN_PROFILE,
        )
    } == {
        "K24": "391e5689e8f5436f029099086a9e65b50679606120275a6a958417d235f1dd9b",
        "S01": "0b8759367ce19f1a82cfb9630ffefd849e0c600bce1e909985645c0a47de046b",
        "S21": "fb319b1a6918427767373917ddda2cc5b95a88d9d295ff06e866762b955dd161",
        "S34": "2f1292a939eac92cd0dc820309885caccfa53293d1db78d18447a5b5b329fed1",
        "S61": "d1a7fcd8af232aef9ca348eb178466a13a744eb700da7d49d39cfbe16c935c7d",
    }
    assert {
        profile.profile_id
        for profile in (
            K24_FACET_PROFILE,
            S01_SURVIVAL_PROFILE,
            S21_FOREST_PROFILE,
            S34_NYQUIST_PROFILE,
            S61_CONFUSION_PROFILE,
        )
    } == {"K24", "S01", "S21", "S34", "S61"}
    source = "\n".join(
        inspect.getsource(module) for module in (structural_origin, scientific_origin, s61_origin)
    )
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
