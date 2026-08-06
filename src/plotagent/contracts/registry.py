"""Frozen metadata for the 52 first-release chart identifiers."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from plotagent.contracts.base import (
    CalculationKind,
    ChartTypeId,
    FamilyKind,
    OriginCapability,
    PrecomputedKind,
    StrictModel,
)

GeometryKind = Literal[
    "line",
    "symbol",
    "error_bar",
    "band",
    "area",
    "bar",
    "strip",
    "box",
    "violin",
    "histogram",
    "density",
    "step",
    "heatmap",
    "contour",
    "risk_table",
    "interval",
    "panel",
    "lollipop",
    "dumbbell",
    "beeswarm",
    "ridgeline",
    "floating_bar",
    "bridge",
    "bullet",
    "pyramid",
    "scatter_matrix",
    "density2d",
    "marginal",
    "probability",
    "agreement",
    "dual_axis",
    "y_offset",
    "volcano",
]


class ExportCapabilities(StrictModel):
    png: Literal[True] = True
    svg: Literal[True] = True
    opju: OriginCapability = "O1"


class ChartRegistration(StrictModel):
    chart_type_id: ChartTypeId
    english_name: str
    family: FamilyKind
    geometries: tuple[GeometryKind, ...]
    required_roles: tuple[str, ...]
    optional_roles: tuple[str, ...] = ()
    required_calculations: tuple[CalculationKind, ...] = ()
    allowed_calculations: tuple[CalculationKind, ...] = ()
    required_precomputed: tuple[PrecomputedKind, ...] = ()
    exports: ExportCapabilities = ExportCapabilities()

    @model_validator(mode="after")
    def valid_registration(self) -> ChartRegistration:
        if not self.geometries:
            raise ValueError("a chart must declare at least one geometry")
        if not set(self.required_calculations).issubset(self.allowed_calculations):
            raise ValueError("required calculations must also be allowed")
        if len(set(self.required_roles)) != len(self.required_roles):
            raise ValueError("required roles must be unique")
        if set(self.required_roles) & set(self.optional_roles):
            raise ValueError("required and optional roles cannot overlap")
        return self


def _chart(
    chart_type_id: ChartTypeId,
    english_name: str,
    family: FamilyKind,
    geometries: tuple[GeometryKind, ...],
    required_roles: tuple[str, ...],
    *,
    optional_roles: tuple[str, ...] = (),
    required_calculations: tuple[CalculationKind, ...] = (),
    allowed_calculations: tuple[CalculationKind, ...] = (),
    required_precomputed: tuple[PrecomputedKind, ...] = (),
) -> ChartRegistration:
    return ChartRegistration(
        chart_type_id=chart_type_id,
        english_name=english_name,
        family=family,
        geometries=geometries,
        required_roles=required_roles,
        optional_roles=optional_roles,
        required_calculations=required_calculations,
        allowed_calculations=allowed_calculations,
        required_precomputed=required_precomputed,
    )


CHART_REGISTRY: tuple[ChartRegistration, ...] = (
    _chart("K01", "Line plot", "xy", ("line",), ("x", "y")),
    _chart("K02", "Line and symbol", "xy", ("line", "symbol"), ("x", "y")),
    _chart("K03", "Scatter plot", "xy", ("symbol",), ("x", "y"), optional_roles=("group",)),
    _chart(
        "K04",
        "Bubble and colormap scatter",
        "xy",
        ("symbol",),
        ("x", "y"),
        optional_roles=("size", "color", "group"),
    ),
    _chart(
        "K05",
        "Regression plot with supplied curve",
        "xy",
        ("symbol", "line", "band"),
        ("x", "y"),
        required_precomputed=("curve",),
        optional_roles=("lower", "upper"),
    ),
    _chart(
        "K06",
        "Point estimate and error bar",
        "xy",
        ("symbol", "error_bar"),
        ("center",),
        optional_roles=("lower", "upper", "error", "group"),
        allowed_calculations=("summary_error",),
    ),
    _chart(
        "K07",
        "Error ribbon",
        "xy",
        ("line", "band"),
        ("x", "center"),
        optional_roles=("lower", "upper", "group"),
        allowed_calculations=("summary_error",),
    ),
    _chart(
        "K08",
        "Column and bar",
        "categorical",
        ("bar",),
        ("category", "value"),
        allowed_calculations=("summary_error",),
    ),
    _chart(
        "K09",
        "Grouped bar",
        "categorical",
        ("bar",),
        ("category", "group", "value"),
        allowed_calculations=("summary_error",),
    ),
    _chart("K10", "Stacked bar", "categorical", ("bar",), ("category", "component", "value")),
    _chart(
        "K11",
        "100 percent stacked bar",
        "categorical",
        ("bar",),
        ("category", "component", "value"),
        required_calculations=("percent_stack",),
        allowed_calculations=("percent_stack",),
    ),
    _chart(
        "K12",
        "Dot and strip plot",
        "distribution",
        ("strip",),
        ("value",),
        optional_roles=("group",),
    ),
    _chart(
        "K13",
        "Box plot",
        "distribution",
        ("box",),
        ("value",),
        optional_roles=("group",),
        required_calculations=("tukey_box",),
        allowed_calculations=("tukey_box",),
    ),
    _chart(
        "K14",
        "Violin plot",
        "distribution",
        ("violin",),
        ("value",),
        optional_roles=("group",),
        required_calculations=("violin_kde",),
        allowed_calculations=("violin_kde",),
    ),
    _chart(
        "K15",
        "Histogram",
        "distribution",
        ("histogram",),
        ("value",),
        required_calculations=("histogram_binning",),
        allowed_calculations=("histogram_binning",),
    ),
    _chart(
        "K16",
        "KDE density",
        "distribution",
        ("density",),
        ("value",),
        optional_roles=("group",),
        required_calculations=("density_kde",),
        allowed_calculations=("density_kde",),
    ),
    _chart(
        "K17",
        "ECDF and CCDF",
        "distribution",
        ("step",),
        ("value",),
        required_calculations=("ecdf",),
        allowed_calculations=("ecdf",),
    ),
    _chart("K18", "Area plot", "xy", ("area",), ("x", "y")),
    _chart(
        "K19", "Time-series plot", "xy", ("line",), ("time", "value"), optional_roles=("event",)
    ),
    _chart(
        "K20",
        "Heatmap",
        "matrix",
        ("heatmap",),
        ("row", "column", "value"),
        allowed_calculations=("matrix_projection",),
    ),
    _chart(
        "K21",
        "Correlation matrix from supplied matrix",
        "matrix",
        ("heatmap",),
        ("row_label", "column_label", "value"),
        required_precomputed=("matrix",),
    ),
    _chart(
        "K22",
        "Contour from supplied regular grid",
        "matrix",
        ("contour",),
        ("x", "y", "z"),
        required_precomputed=("matrix_grid",),
    ),
    _chart("K24", "Faceted plot", "facet", ("panel",), ("facet", "base_x", "base_y")),
    _chart("K25", "Multi-panel figure", "facet", ("panel",), ("panel",)),
    _chart(
        "S01",
        "Kaplan-Meier curve from supplied steps",
        "survival",
        ("step", "band", "risk_table"),
        ("time", "survival"),
        optional_roles=("lower", "upper", "risk_count", "group"),
        required_precomputed=("step_curve",),
    ),
    _chart(
        "S05",
        "Dose-response from supplied curve",
        "dose_response",
        ("symbol", "line", "band"),
        ("dose", "response"),
        optional_roles=("lower", "upper", "parameter"),
        required_precomputed=("curve",),
    ),
    _chart(
        "S21",
        "Forest plot from supplied effects",
        "forest",
        ("interval", "symbol"),
        ("label", "effect", "lower", "upper"),
        optional_roles=("weight",),
        required_precomputed=("effect_interval",),
    ),
    _chart(
        "S25",
        "Continuous spectrum",
        "xy",
        ("line",),
        ("spectral_axis", "intensity"),
        required_precomputed=("spectrum",),
    ),
    _chart(
        "S31",
        "XRD diffraction",
        "xy",
        ("line",),
        ("angle", "intensity"),
        optional_roles=("peak_label",),
        required_precomputed=("spectrum",),
    ),
    _chart(
        "S34",
        "Nyquist plot",
        "xy",
        ("line", "symbol"),
        ("z_real", "z_imaginary"),
        optional_roles=("frequency",),
        required_precomputed=("complex_curve",),
    ),
    _chart(
        "S61",
        "Confusion matrix",
        "matrix",
        ("heatmap",),
        ("actual", "predicted"),
        required_calculations=("confusion_count",),
        allowed_calculations=("confusion_count",),
    ),
    _chart("X01", "Step plot", "special", ("step",), ("x", "y")),
    _chart(
        "X02",
        "Lollipop plot",
        "special",
        ("lollipop",),
        ("category", "value"),
        optional_roles=("baseline", "group"),
    ),
    _chart(
        "X03",
        "Dumbbell and paired change plot",
        "special",
        ("dumbbell",),
        ("category", "start", "end"),
        optional_roles=("group",),
    ),
    _chart(
        "X05",
        "Beeswarm plot",
        "special",
        ("beeswarm",),
        ("value",),
        optional_roles=("group",),
    ),
    _chart(
        "X07",
        "Ridgeline plot",
        "special",
        ("ridgeline",),
        ("value", "group"),
    ),
    _chart(
        "X09",
        "Floating interval bar",
        "special",
        ("floating_bar",),
        ("category", "start", "end"),
        optional_roles=("middle",),
    ),
    _chart(
        "X11",
        "Bridge waterfall chart",
        "special",
        ("bridge",),
        ("category", "delta"),
    ),
    _chart(
        "X12",
        "Bullet chart",
        "special",
        ("bullet",),
        ("item", "actual_value", "target"),
        optional_roles=("range1", "range2", "range3"),
    ),
    _chart(
        "X13",
        "Population pyramid",
        "special",
        ("pyramid",),
        ("category", "left", "right"),
    ),
    _chart(
        "X15",
        "Scatter matrix",
        "special",
        ("scatter_matrix",),
        ("x", "y", "z"),
    ),
    _chart("X16", "Two-dimensional density", "special", ("density2d",), ("x", "y")),
    _chart("X17", "Marginal scatter", "special", ("marginal",), ("x", "y")),
    _chart(
        "X18",
        "Q-Q and probability plot",
        "special",
        ("probability",),
        ("value",),
    ),
    _chart(
        "X19",
        "Bland-Altman agreement plot",
        "special",
        ("agreement",),
        ("method_a", "method_b"),
    ),
    _chart(
        "X23",
        "Dual-Y line plot",
        "special",
        ("dual_axis",),
        ("x", "left", "right"),
    ),
    _chart(
        "X24",
        "Pareto chart",
        "special",
        ("bridge",),
        ("category", "value"),
    ),
    _chart(
        "X35",
        "Dual-Y column plot",
        "special",
        ("dual_axis",),
        ("category", "left", "right"),
    ),
    _chart(
        "X36",
        "Dual-Y column-line plot",
        "special",
        ("dual_axis",),
        ("category", "left", "right"),
    ),
    _chart(
        "X37",
        "Dual-Y box plot",
        "special",
        ("dual_axis",),
        ("group", "left", "right"),
    ),
    _chart(
        "X38",
        "Y-offset stacked line plot",
        "special",
        ("y_offset",),
        ("x", "y", "series"),
    ),
    _chart(
        "S07",
        "Volcano plot",
        "special",
        ("volcano",),
        ("feature", "log2fc", "pvalue"),
        optional_roles=("qvalue",),
    ),
)

CHARTS_BY_ID = {item.chart_type_id: item for item in CHART_REGISTRY}

if len(CHART_REGISTRY) != 52 or len(CHARTS_BY_ID) != 52:
    raise RuntimeError("the first-release chart registry must contain exactly 52 unique chart IDs")


class ChartRegistry(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    charts: tuple[ChartRegistration, ...] = Field(min_length=52, max_length=52)

    @model_validator(mode="after")
    def unique_ids(self) -> ChartRegistry:
        ids = tuple(chart.chart_type_id for chart in self.charts)
        if len(set(ids)) != 52:
            raise ValueError("chart registry ids must be unique")
        return self


V1_CHART_REGISTRY = ChartRegistry(charts=CHART_REGISTRY)
