from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from matplotlib.axes import Axes

from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    SetLegend,
    SetSeriesStyle,
)
from plotagent.engine.backends.matplotlib import (
    K02LineSymbolRenderer,
    K06PointErrorRenderer,
    K07ErrorBandRenderer,
    K18AreaRenderer,
    X02DropLineRenderer,
)

HASH = "3" * 64


def _column(field_id: str, name: str, values: tuple[object, ...]) -> EngineColumn:
    return EngineColumn(
        field=EngineField(field_id=field_id, name=name, logical_type="numeric"),
        values=values,
    )


def _case(
    profile_id: str,
    roles: tuple[str, ...],
    columns: tuple[EngineColumn, ...],
) -> tuple[PlotDocument, tuple[object, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{profile_id.lower()}",
        version=1,
        content_hash=HASH,
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=column.field.field_id)
        for role, column in zip(roles, columns, strict=True)
    )
    create = CreatePlot(
        action_id=f"action:create-{profile_id.lower()}",
        plot_id=f"plot:{profile_id.lower()}-demo",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    style = SetSeriesStyle(
        action_id=f"action:style-{profile_id.lower()}",
        target=(
            f"series:{profile_id.lower()}-demo.area_1"
            if profile_id == "K18"
            else f"series:{profile_id.lower()}-demo.primary"
        ),
        expected_plot_version=1,
        color="#AA3300",
        line_width_pt=2.0,
        **(
            {"symbol": "diamond", "symbol_size_pt": 7.0}
            if profile_id in {"K02", "K06"}
            else {"line_style": "dash"}
        ),
    )
    legend = SetLegend(
        action_id=f"action:legend-{profile_id.lower()}",
        target=f"legend:{profile_id.lower()}-demo.main",
        expected_plot_version=2,
        visible=True,
    )
    actions = (create, style, legend)
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=3,
        parent_version=2,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(1, len(columns[0].values) + 1)),
        columns=columns,
    )
    return document, actions, view


@pytest.mark.parametrize(
    ("renderer", "profile_id", "roles", "columns", "object_kind"),
    (
        (
            K02LineSymbolRenderer(),
            "K02",
            ("x", "y"),
            (
                _column("field:x", "Time", (0.0, 1.0, 2.0, 3.0)),
                _column("field:y", "Signal", (1.0, None, 2.5, 3.0)),
            ),
            "line_symbol_series",
        ),
        (
            K06PointErrorRenderer(),
            "K06",
            ("x", "center", "x_err_minus", "x_err_plus", "y_err_minus", "y_err_plus"),
            (
                _column("field:x", "Time", (1.0, 2.0, 3.0)),
                _column("field:center", "Estimate", (2.0, 3.0, 4.0)),
                _column("field:xm", "XErrMinus", (0.1, 0.2, 0.1)),
                _column("field:xp", "XErrPlus", (0.2, 0.3, 0.1)),
                _column("field:ym", "YErrMinus", (0.3, 0.4, 0.2)),
                _column("field:yp", "YErrPlus", (0.4, 0.5, 0.3)),
            ),
            "point_error_series",
        ),
        (
            K07ErrorBandRenderer(),
            "K07",
            ("x", "center", "lower", "upper"),
            (
                _column("field:x", "Dose", (0.0, 1.0, 2.0)),
                _column("field:center", "Response", (2.0, 3.0, 4.0)),
                _column("field:lower", "Lower", (1.5, 2.5, 3.0)),
                _column("field:upper", "Upper", (2.5, 3.7, 5.0)),
            ),
            "error_band_series",
        ),
        (
            K18AreaRenderer(),
            "K18",
            ("x", "series_1"),
            (
                _column("field:x", "Time", (0.0, 1.0, 2.0, 3.0)),
                _column("field:y", "Amount", (1.0, 3.0, None, 2.0)),
            ),
            "area_series",
        ),
        (
            X02DropLineRenderer(),
            "X02",
            ("x", "y"),
            (
                _column("field:x", "Position", (0.0, 1.0, 2.0, 3.0)),
                _column("field:y", "Signal", (-1.0, 3.0, 1.5, -0.5)),
            ),
            "drop_line_series",
        ),
    ),
)
def test_t1_family_renders_from_engine_data_without_legacy_resolver(
    tmp_path: Path,
    renderer,
    profile_id: str,
    roles: tuple[str, ...],
    columns: tuple[EngineColumn, ...],
    object_kind: str,
) -> None:
    document, actions, view = _case(profile_id, roles, columns)
    png = tmp_path / profile_id / "preview.png"
    svg = tmp_path / profile_id / "preview.svg"

    readback = renderer.render(document, actions, view, png, svg)

    assert png.stat().st_size > 1_000
    assert svg.stat().st_size > 1_000
    assert object_kind in {item.object_kind for item in readback.objects}
    source = inspect.getsource(__import__(renderer.__class__.__module__, fromlist=["*"]))
    assert "plotagent.rendering" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source


def test_k06_rejects_negative_error_magnitudes(tmp_path: Path) -> None:
    columns = (
        _column("field:x", "X", (1.0, 2.0)),
        _column("field:center", "Y", (2.0, 3.0)),
        _column("field:xm", "XErrMinus", (0.1, -0.2)),
        _column("field:xp", "XErrPlus", (0.1, 0.4)),
        _column("field:ym", "YErrMinus", (0.2, 0.3)),
        _column("field:yp", "YErrPlus", (0.2, 0.3)),
    )
    document, actions, view = _case(
        "K06",
        ("x", "center", "x_err_minus", "x_err_plus", "y_err_minus", "y_err_plus"),
        columns,
    )
    with pytest.raises(ValueError, match="error magnitudes must be non-negative"):
        K06PointErrorRenderer().render(
            document,
            actions,
            view,
            tmp_path / "preview.png",
            tmp_path / "preview.svg",
        )


def test_k07_rejects_inverted_band_bounds(tmp_path: Path) -> None:
    columns = (
        _column("field:x", "X", (1.0, 2.0)),
        _column("field:center", "Y", (2.0, 3.0)),
        _column("field:lower", "Lower", (1.0, 3.5)),
        _column("field:upper", "Upper", (3.0, 4.0)),
    )
    document, actions, view = _case("K07", ("x", "center", "lower", "upper"), columns)
    with pytest.raises(ValueError, match="lower <= center <= upper"):
        K07ErrorBandRenderer().render(
            document,
            actions,
            view,
            tmp_path / "preview.png",
            tmp_path / "preview.svg",
        )


def test_x02_drop_lines_end_at_the_visible_bottom_axis_not_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baselines: list[float] = []
    original = Axes.vlines

    def capture(self, x, ymin, ymax, *args, **kwargs):
        baselines.append(float(ymin))
        return original(self, x, ymin, ymax, *args, **kwargs)

    monkeypatch.setattr(Axes, "vlines", capture)
    columns = (
        _column("field:x", "X", (1.0, 2.0)),
        _column("field:y", "Y", (-2.0, 3.0)),
    )
    document, actions, view = _case("X02", ("x", "y"), columns)

    X02DropLineRenderer().render(
        document,
        actions,
        view,
        tmp_path / "preview.png",
        tmp_path / "preview.svg",
    )

    assert len(baselines) == 1
    assert baselines[0] < -2.0
    assert baselines[0] != 0.0
