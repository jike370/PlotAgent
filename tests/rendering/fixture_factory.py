"""Deterministic minimal geometry for every explicit v1 chart entry."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal, cast

from plotagent.contracts.base import (
    CalculationKind,
    ChartTypeId,
    PlotCalculationResultRef,
    PrecomputedKind,
    PreparedDatasetRef,
)
from plotagent.contracts.plots import (
    AllGeometryKind,
    AxisScaleKind,
    AxisSpec,
    CalculatedSeriesData,
    CategoricalFamily,
    DistributionFamily,
    DoseResponseFamily,
    FacetFamily,
    ForestFamily,
    MatrixFamily,
    PlotFamily,
    PlotProvenance,
    PlotSpec,
    PrecomputedDataRef,
    PrecomputedSeriesData,
    PreparedSeriesData,
    SafeRichText,
    SafeTextNode,
    ScaleSpec,
    SeriesData,
    SeriesSpec,
    SpecialFamily,
    StyleSourceRef,
    SurvivalFamily,
    XYFamily,
)
from plotagent.rendering import PanelPlan, PlotResolver, RenderDataStore, RenderTable, ResolvedPlot
from tests.contracts.helpers import profile, style

type DataKind = Literal["prepared", "calculated", "precomputed"]
type SvgTextMode = Literal["text_to_path", "editable_text"]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


@dataclass(frozen=True, slots=True)
class SeriesFixture:
    geometry: AllGeometryKind
    data_kind: DataKind
    roles: tuple[str, ...]
    values: tuple[tuple[object, ...], ...]
    calculation_kind: CalculationKind | None = None
    precomputed_kind: PrecomputedKind | None = None


def _series(
    geometry: AllGeometryKind,
    data_kind: DataKind,
    roles: tuple[str, ...],
    *values: tuple[object, ...],
    calculation_kind: CalculationKind | None = None,
    precomputed_kind: PrecomputedKind | None = None,
) -> SeriesFixture:
    return SeriesFixture(
        geometry=geometry,
        data_kind=data_kind,
        roles=roles,
        values=values,
        calculation_kind=calculation_kind,
        precomputed_kind=precomputed_kind,
    )


_FIXTURES: dict[str, tuple[SeriesFixture, ...]] = {
    "K01": (_series("line", "prepared", ("x", "y"), (0.0, 1.0, 2.0), (1.0, 2.5, 2.0)),),
    "K02": (
        _series("line", "prepared", ("x", "y"), (0.0, 1.0, 2.0), (1.0, 2.5, 2.0)),
        _series("symbol", "prepared", ("x", "y"), (0.0, 1.0, 2.0), (1.0, 2.5, 2.0)),
    ),
    "K03": (_series("symbol", "prepared", ("x", "y"), (0.0, 1.0, 2.0), (2.0, 1.0, 3.0)),),
    "K04": (
        _series(
            "symbol",
            "prepared",
            ("x", "y", "size", "color"),
            (0.0, 1.0, 2.0),
            (1.0, 2.0, 1.5),
            (1.0, 3.0, 6.0),
            (0.1, 0.5, 0.9),
        ),
    ),
    "K05": (
        _series(
            "line",
            "precomputed",
            ("x", "y"),
            (0.0, 1.0, 2.0),
            (1.0, 1.8, 3.1),
            precomputed_kind="curve",
        ),
    ),
    "K06": (
        _series(
            "error_bar",
            "calculated",
            ("x", "center", "x_lower", "x_upper", "lower", "upper"),
            (1.0, 2.0, 3.0),
            (2.0, 3.0, 2.5),
            (0.8, 1.7, 2.6),
            (1.2, 2.3, 3.4),
            (1.5, 2.4, 2.0),
            (2.5, 3.6, 3.0),
            calculation_kind="summary_error",
        ),
    ),
    "K07": (
        _series(
            "line",
            "calculated",
            ("x", "center"),
            (0.0, 1.0, 2.0),
            (2.0, 2.5, 3.0),
            calculation_kind="summary_error",
        ),
        _series(
            "band",
            "calculated",
            ("x", "lower", "upper"),
            (0.0, 1.0, 2.0),
            (1.5, 2.0, 2.4),
            (2.5, 3.0, 3.6),
            calculation_kind="summary_error",
        ),
    ),
    "K08": (
        _series(
            "bar",
            "calculated",
            ("category", "value", "lower", "upper"),
            ("A", "B"),
            (2.0, 3.0),
            (1.7, 2.6),
            (2.3, 3.4),
            calculation_kind="summary_error",
        ),
    ),
    "K09": (
        _series(
            "bar",
            "calculated",
            ("category", "group", "value"),
            ("A", "A", "B", "B"),
            ("G1", "G2", "G1", "G2"),
            (2.0, 3.0, 2.5, 3.5),
            calculation_kind="summary_error",
        ),
    ),
    "K10": (
        _series(
            "bar",
            "prepared",
            ("category", "component", "value"),
            ("A", "A", "B", "B"),
            ("C1", "C2", "C1", "C2"),
            (2.0, 1.0, 1.5, 2.5),
        ),
    ),
    "K11": (
        _series(
            "bar",
            "calculated",
            ("category", "component", "value"),
            ("A", "A", "B", "B"),
            ("C1", "C2", "C1", "C2"),
            (0.4, 0.6, 0.7, 0.3),
            calculation_kind="percent_stack",
        ),
    ),
    "K12": (
        _series(
            "strip", "prepared", ("value", "group"), (1.0, 1.5, 2.0, 2.5), ("A", "A", "B", "B")
        ),
    ),
    "K13": (
        _series(
            "box",
            "calculated",
            ("group", "q1", "median", "q3", "whisker_low", "whisker_high"),
            ("A", "B"),
            (1.0, 1.5),
            (1.5, 2.0),
            (2.0, 2.7),
            (0.5, 1.0),
            (2.5, 3.1),
            calculation_kind="tukey_box",
        ),
    ),
    "K14": (
        _series(
            "violin",
            "calculated",
            ("group", "grid", "density"),
            ("A", "A", "A", "A"),
            (0.0, 1.0, 2.0, 3.0),
            (0.1, 0.8, 0.7, 0.1),
            calculation_kind="violin_kde",
        ),
    ),
    "K15": (
        _series(
            "histogram",
            "calculated",
            ("left", "right", "height"),
            (0.0, 1.0, 2.0),
            (1.0, 2.0, 3.0),
            (2.0, 4.0, 1.0),
            calculation_kind="histogram_binning",
        ),
    ),
    "K16": (
        _series(
            "density",
            "calculated",
            ("grid", "density"),
            (0.0, 1.0, 2.0, 3.0),
            (0.1, 0.6, 0.5, 0.1),
            calculation_kind="density_kde",
        ),
    ),
    "K17": (
        _series(
            "step",
            "calculated",
            ("x", "probability"),
            (0.0, 1.0, 2.0, 3.0),
            (0.25, 0.5, 0.75, 1.0),
            calculation_kind="ecdf",
        ),
    ),
    "K18": (_series("area", "prepared", ("x", "y"), (0.0, 1.0, 2.0), (1.0, 2.0, 1.5)),),
    "K19": (
        _series(
            "line",
            "prepared",
            ("time", "value"),
            ("2026-01-01", "2026-01-02", "2026-01-03"),
            (1.0, 2.0, 1.5),
        ),
    ),
    "K20": (
        _series(
            "heatmap",
            "calculated",
            ("row", "column", "value"),
            ("R1", "R1", "R2", "R2"),
            ("C1", "C2", "C1", "C2"),
            (1.0, 2.0, 3.0, 4.0),
            calculation_kind="matrix_projection",
        ),
    ),
    "K21": (
        _series(
            "heatmap",
            "precomputed",
            ("row_label", "column_label", "value"),
            ("A", "A", "B", "B"),
            ("A", "B", "A", "B"),
            (1.0, 0.4, 0.4, 1.0),
            precomputed_kind="matrix",
        ),
    ),
    "K22": (
        _series(
            "contour",
            "precomputed",
            ("x", "y", "z"),
            (0.0, 1.0, 0.0, 1.0),
            (0.0, 0.0, 1.0, 1.0),
            (0.0, 1.0, 1.0, 2.0),
            precomputed_kind="matrix_grid",
        ),
    ),
    "K24": (
        _series(
            "panel",
            "prepared",
            ("facet", "base_x", "base_y"),
            ("A", "A", "B", "B"),
            (0.0, 1.0, 0.0, 1.0),
            (1.0, 2.0, 2.0, 1.0),
        ),
    ),
    "S01": (
        _series(
            "step",
            "precomputed",
            ("time", "survival"),
            (0.0, 1.0, 2.0, 3.0),
            (1.0, 0.8, 0.65, 0.5),
            precomputed_kind="step_curve",
        ),
    ),
    "S05": (
        _series(
            "line",
            "precomputed",
            ("dose", "response"),
            (0.1, 1.0, 10.0, 100.0),
            (0.05, 0.2, 0.75, 0.95),
            precomputed_kind="curve",
        ),
    ),
    "S21": (
        _series(
            "interval",
            "precomputed",
            ("label", "effect", "lower", "upper", "weight"),
            ("Study 1", "Study 2", "Study 3"),
            (0.9, 1.2, 1.05),
            (0.7, 0.95, 0.8),
            (1.1, 1.5, 1.3),
            (0.3, 0.5, 0.2),
            precomputed_kind="effect_interval",
        ),
    ),
    "S25": (
        _series(
            "line",
            "precomputed",
            ("spectral_axis", "intensity"),
            (400.0, 500.0, 600.0, 700.0),
            (0.1, 0.8, 0.5, 0.2),
            precomputed_kind="spectrum",
        ),
    ),
    "S31": (
        _series(
            "line",
            "precomputed",
            ("angle", "intensity"),
            (10.0, 20.0, 30.0, 40.0),
            (10.0, 80.0, 20.0, 50.0),
            precomputed_kind="spectrum",
        ),
    ),
    "S34": (
        _series(
            "line",
            "precomputed",
            ("z_real", "z_imaginary", "frequency"),
            (0.2, 0.5, 1.0, 1.5),
            (0.0, 0.6, 0.8, 0.2),
            (1000.0, 100.0, 10.0, 1.0),
            precomputed_kind="complex_curve",
        ),
    ),
    "S61": (
        _series(
            "heatmap",
            "calculated",
            ("actual", "predicted", "value"),
            ("A", "A", "B", "B"),
            ("A", "B", "A", "B"),
            (12.0, 2.0, 1.0, 10.0),
            calculation_kind="confusion_count",
        ),
    ),
    "X01": (_series("step", "prepared", ("x", "y"), (0.0, 1.0, 2.0, 3.0), (1.0, 1.8, 1.2, 2.4)),),
    "X02": (
        _series(
            "lollipop",
            "prepared",
            ("category", "value"),
            ("A", "B", "C", "D"),
            (2.0, 4.2, 3.1, 5.0),
        ),
    ),
    "X03": (
        _series(
            "dumbbell",
            "prepared",
            ("category", "start", "end"),
            ("A", "B", "C"),
            (1.0, 2.5, 1.8),
            (2.4, 1.7, 3.2),
        ),
    ),
    "X05": (
        _series(
            "beeswarm",
            "prepared",
            ("value", "group"),
            (1.0, 1.2, 1.1, 2.0, 2.3, 2.1),
            ("A", "A", "A", "B", "B", "B"),
        ),
    ),
    "X07": (
        _series(
            "ridgeline",
            "prepared",
            ("value", "group"),
            (0.8, 1.0, 1.2, 1.8, 2.0, 2.2, 2.7, 3.0, 3.2),
            ("A", "A", "A", "B", "B", "B", "C", "C", "C"),
        ),
    ),
    "X09": (
        _series(
            "floating_bar",
            "prepared",
            ("category", "start", "middle", "end"),
            ("A", "B", "C"),
            (1.0, 2.0, 1.5),
            (1.8, 2.9, 2.2),
            (2.5, 3.8, 3.0),
        ),
    ),
    "X11": (
        _series(
            "bridge",
            "prepared",
            ("category", "delta"),
            ("Start", "Gain", "Loss", "Finish"),
            (3.0, 2.0, -1.2, 0.8),
        ),
    ),
    "X12": (
        _series(
            "bullet",
            "prepared",
            ("item", "actual_value", "target", "range1", "range2", "range3"),
            ("A", "B", "C"),
            (72.0, 86.0, 61.0),
            (80.0, 82.0, 75.0),
            (60.0, 60.0, 60.0),
            (80.0, 80.0, 80.0),
            (100.0, 100.0, 100.0),
        ),
    ),
    "X13": (
        _series(
            "pyramid",
            "prepared",
            ("category", "left", "right"),
            ("0-19", "20-39", "40-59", "60+"),
            (18.0, 24.0, 20.0, 12.0),
            (17.0, 23.0, 22.0, 15.0),
        ),
    ),
    "X15": (
        _series(
            "scatter_matrix",
            "prepared",
            ("x", "y", "z"),
            (1.0, 2.0, 3.0, 4.0, 5.0),
            (2.0, 1.5, 3.5, 3.0, 4.8),
            (5.0, 4.2, 3.6, 2.4, 1.2),
        ),
    ),
    "X16": (
        _series(
            "density2d",
            "prepared",
            ("x", "y"),
            tuple(float(i % 10) + (i % 3) * 0.08 for i in range(60)),
            tuple(float((i * 7) % 10) + (i % 5) * 0.06 for i in range(60)),
        ),
    ),
    "X17": (
        _series(
            "marginal",
            "prepared",
            ("x", "y"),
            tuple(float(i) / 4 for i in range(24)),
            tuple(float(i) / 5 + ((i % 4) - 1.5) * 0.4 for i in range(24)),
        ),
    ),
    "X18": (
        _series(
            "probability", "prepared", ("value",), (-1.7, -1.1, -0.6, -0.2, 0.0, 0.3, 0.7, 1.2, 1.8)
        ),
    ),
    "X19": (
        _series(
            "agreement",
            "prepared",
            ("method_a", "method_b"),
            (10.0, 12.0, 14.0, 16.0, 18.0, 20.0),
            (10.4, 11.5, 14.3, 15.2, 18.8, 19.4),
        ),
    ),
    "X23": (
        _series(
            "dual_axis",
            "prepared",
            ("x", "left", "right"),
            (0.0, 1.0, 2.0, 3.0),
            (1.0, 2.0, 2.6, 3.4),
            (120.0, 150.0, 132.0, 180.0),
        ),
    ),
    "X24": (
        _series(
            "bridge",
            "prepared",
            ("category", "value"),
            ("A", "B", "C", "D"),
            (48.0, 26.0, 15.0, 11.0),
        ),
    ),
    "X35": (
        _series(
            "dual_axis",
            "prepared",
            ("category", "left", "right"),
            ("A", "B", "C", "D"),
            (2.0, 3.5, 2.8, 4.2),
            (80.0, 95.0, 76.0, 110.0),
        ),
    ),
    "X36": (
        _series(
            "dual_axis",
            "prepared",
            ("category", "left", "right"),
            ("A", "B", "C", "D"),
            (2.0, 3.5, 2.8, 4.2),
            (80.0, 95.0, 76.0, 110.0),
        ),
    ),
    "X37": (
        _series(
            "dual_axis",
            "prepared",
            ("group", "left", "right"),
            ("A", "A", "A", "B", "B", "B"),
            (1.0, 1.4, 1.8, 2.1, 2.5, 2.9),
            (80.0, 90.0, 84.0, 110.0, 125.0, 118.0),
        ),
    ),
    "X38": (
        _series(
            "y_offset",
            "prepared",
            ("x", "y", "series"),
            (0.0, 1.0, 2.0, 0.0, 1.0, 2.0),
            (1.0, 1.8, 1.3, 0.8, 1.4, 2.0),
            ("A", "A", "A", "B", "B", "B"),
        ),
    ),
    "S07": (
        _series(
            "volcano",
            "prepared",
            ("feature", "log2fc", "pvalue"),
            ("g1", "g2", "g3", "g4", "g5", "g6"),
            (-2.2, -1.4, -0.4, 0.3, 1.3, 2.4),
            (0.001, 0.02, 0.4, 0.8, 0.03, 0.0005),
        ),
    ),
}


def _family(chart_id: str, geometries: tuple[AllGeometryKind, ...]) -> PlotFamily:
    if chart_id.startswith("X") or chart_id == "S07":
        return SpecialFamily(geometry=cast(Any, geometries))
    if chart_id in {"K08", "K09", "K10", "K11"}:
        return CategoricalFamily(geometry=("bar",))
    if chart_id in {"K12", "K13", "K14", "K15", "K16", "K17"}:
        return DistributionFamily(
            geometry=cast(
                tuple[Literal["strip", "box", "violin", "histogram", "density", "step"], ...],
                geometries,
            )
        )
    if chart_id in {"K20", "K21", "K22", "S61"}:
        return MatrixFamily(geometry=cast(tuple[Literal["heatmap", "contour"], ...], geometries))
    if chart_id == "S01":
        return SurvivalFamily(
            geometry=cast(tuple[Literal["step", "band", "risk_table"], ...], geometries)
        )
    if chart_id == "S05":
        return DoseResponseFamily(
            geometry=cast(tuple[Literal["symbol", "line", "band"], ...], geometries)
        )
    if chart_id == "S21":
        return ForestFamily(geometry=cast(tuple[Literal["interval", "symbol"], ...], geometries))
    if chart_id in {"K24", "K25"}:
        return FacetFamily(geometry=("panel",))
    return XYFamily(
        geometry=cast(
            tuple[Literal["line", "symbol", "error_bar", "band", "area"], ...],
            geometries,
        )
    )


def _axis_scales(chart_id: str) -> tuple[AxisScaleKind, AxisScaleKind]:
    if chart_id in {"K08", "K09", "K10", "K11", "K12", "K13", "K14"}:
        return "categorical", "linear"
    if chart_id in {"K20", "K21", "S61"}:
        return "categorical", "categorical"
    if chart_id == "S21":
        return "linear", "categorical"
    if chart_id == "K19":
        return "datetime", "linear"
    if chart_id == "S05":
        return "log10", "linear"
    if chart_id == "X13":
        return "linear", "categorical"
    if chart_id in {"X02", "X05", "X09", "X11", "X12", "X24", "X35", "X36", "X37"}:
        return "categorical", "linear"
    if chart_id == "X03":
        return "linear", "categorical"
    return "linear", "linear"


def build_plot_and_store(chart_id: str) -> tuple[PlotSpec, RenderDataStore]:
    chart_type_id = cast(ChartTypeId, chart_id)
    fixtures = _FIXTURES[chart_id]
    prepared_refs: list[PreparedDatasetRef] = []
    precomputed_refs: list[PrecomputedDataRef] = []
    calculation_refs: list[PlotCalculationResultRef] = []
    series_specs: list[SeriesSpec] = []
    store: dict[str, RenderTable] = {}
    for index, fixture in enumerate(fixtures):
        field_ids = tuple(f"field:{chart_id.lower()}.{index}.{role}" for role in fixture.roles)
        table = RenderTable.from_columns(dict(zip(field_ids, fixture.values, strict=True)))
        prepared_ref = PreparedDatasetRef(
            prepared_dataset_id=f"prepared:{chart_id.lower()}.{index}",
            prepared_version=1,
            content_hash=_hash(f"{chart_id}:{index}:prepared"),
        )
        prepared_refs.append(prepared_ref)
        if fixture.data_kind == "prepared":
            data: SeriesData = PreparedSeriesData(
                prepared_dataset_ref=prepared_ref,
                role_fields=field_ids,
            )
            store[prepared_ref.content_hash] = table
        elif fixture.data_kind == "calculated":
            assert fixture.calculation_kind is not None
            calculation_ref = PlotCalculationResultRef(
                calculation_id=f"plotcalc:{chart_id.lower()}.{index}",
                result_version=1,
                calculation_kind=fixture.calculation_kind,
                content_hash=_hash(f"{chart_id}:{index}:calculated"),
            )
            calculation_refs.append(calculation_ref)
            data = CalculatedSeriesData(
                calculation_result_ref=calculation_ref,
                role_fields=field_ids,
            )
            store[calculation_ref.content_hash] = table
        else:
            assert fixture.precomputed_kind is not None
            precomputed_ref = PrecomputedDataRef(
                precomputed_id=f"precomputed:{chart_id.lower()}.{index}",
                precomputed_version=1,
                precomputed_kind=fixture.precomputed_kind,
                content_hash=_hash(f"{chart_id}:{index}:precomputed"),
                data_ref_hash=table.object_hash,
                field_ids=field_ids,
            )
            precomputed_refs.append(precomputed_ref)
            data = PrecomputedSeriesData(
                precomputed_data_ref=precomputed_ref,
                role_fields=field_ids,
            )
            store[table.object_hash] = table
        series_specs.append(
            SeriesSpec(
                series_id=f"series:{chart_id.lower()}.{index}",
                geometry=fixture.geometry,
                data=data,
                label=_text(f"Series {index + 1}") if len(fixtures) > 1 else None,
            )
        )
    x_scale, y_scale = _axis_scales(chart_id)
    dual_axis = chart_id in {"X23", "X24", "X35", "X36", "X37"}
    scales = (
        ScaleSpec(scale_id="scale:x", kind=x_scale),
        ScaleSpec(scale_id="scale:y", kind=y_scale),
    )
    axes = (
        AxisSpec(
            axis_id="axis:x",
            scale_id="scale:x",
            orientation="x",
            position="bottom",
            label=_text("X"),
        ),
        AxisSpec(
            axis_id="axis:y", scale_id="scale:y", orientation="y", position="left", label=_text("Y")
        ),
    )
    if dual_axis:
        scales += (ScaleSpec(scale_id="scale:y_right", kind="linear"),)
        axes += (
            AxisSpec(
                axis_id="axis:y_right",
                scale_id="scale:y_right",
                orientation="y",
                position="right",
                label=_text("Right Y"),
            ),
        )
    plot = PlotSpec(
        plot_id=f"plot:{chart_id.lower()}",
        plot_version=1,
        chart_type_id=chart_type_id,
        family=_family(chart_id, tuple(dict.fromkeys(item.geometry for item in fixtures))),
        prepared_data_refs=tuple(prepared_refs),
        precomputed_data_refs=tuple(precomputed_refs),
        plot_calculation_refs=tuple(calculation_refs),
        scales=scales,
        axes=axes,
        series=tuple(series_specs),
        style_sources=(
            StyleSourceRef(
                source_kind="project",
                source_id="style.fixture",
                source_version=1,
                content_hash=_hash("style.fixture"),
            ),
        ),
        resolved_style=style(),
        publication_profile=profile(),
        provenance=PlotProvenance(origin="manual", engine_build_hash=_hash("fixture.build")),
    )
    return plot, RenderDataStore(store)


def resolve_chart(chart_id: str, *, svg_text_mode: SvgTextMode = "text_to_path") -> ResolvedPlot:
    if chart_id != "K25":
        plot, store = build_plot_and_store(chart_id)
        return PlotResolver().resolve(plot, store, svg_text_mode=svg_text_mode)
    child_plot, child_store = build_plot_and_store("K01")
    child = PlotResolver().resolve(child_plot, child_store, svg_text_mode=svg_text_mode)
    placeholder_ref = PreparedDatasetRef(
        prepared_dataset_id="prepared:k25.placeholder",
        prepared_version=1,
        content_hash=_hash("K25:placeholder"),
    )
    parent = PlotSpec(
        plot_id="plot:k25",
        plot_version=1,
        chart_type_id="K25",
        family=FacetFamily(geometry=("panel",)),
        prepared_data_refs=(placeholder_ref,),
        scales=(
            ScaleSpec(scale_id="scale:x", kind="linear"),
            ScaleSpec(scale_id="scale:y", kind="linear"),
        ),
        axes=(
            AxisSpec(
                axis_id="axis:x",
                scale_id="scale:x",
                orientation="x",
                position="bottom",
                label=_text("X"),
            ),
            AxisSpec(
                axis_id="axis:y",
                scale_id="scale:y",
                orientation="y",
                position="left",
                label=_text("Y"),
            ),
        ),
        series=(
            SeriesSpec(
                series_id="series:k25.panels",
                geometry="panel",
                data=PreparedSeriesData(
                    prepared_dataset_ref=placeholder_ref, role_fields=("field:panel",)
                ),
            ),
        ),
        style_sources=(
            StyleSourceRef(
                source_kind="project",
                source_id="style.fixture",
                source_version=1,
                content_hash=_hash("style.fixture"),
            ),
        ),
        resolved_style=style(),
        publication_profile=profile(),
        provenance=PlotProvenance(origin="manual", engine_build_hash=_hash("fixture.build")),
    )
    return PlotResolver().resolve_panel_plans(
        parent,
        (
            PanelPlan("panel:a", child, 0.1, 0.1, 42.9, 59.8, _text("A")),
            PanelPlan("panel:b", child, 46.0, 0.1, 42.9, 59.8, _text("B")),
        ),
        svg_text_mode=svg_text_mode,
    )
