"""Frozen metadata for the 54 current chart identifiers."""

from __future__ import annotations

from typing import Literal, get_args

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
    "drop_line",
    "lollipop",
    "line_series",
    "before_after",
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

AdmissionStatus = Literal["product", "internal_only", "removed"]
VisualEvidenceLevel = Literal["origin_reference", "synthetic_visual", "unqualified"]
EditCapability = Literal[
    "plot_title",
    "axis_label",
    "axis_range",
    "axis_scale",
    "axis_ticks",
    "font",
    "legend_visibility",
    "legend_position",
    "canvas_size",
    "publication_profile",
    "safe_annotation",
    "series_color",
    "line_width",
    "line_style",
    "marker_size",
    "symbol_shape",
    "symbol_interior",
    "palette",
    "bar_fill",
    "bar_edge",
    "bar_width",
    "bar_gap",
    "error_style",
    "band_style",
    "colorbar",
    "dual_y_style",
    "panel_style",
    "y_offset",
    "chart_parameters",
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
    admission: AdmissionStatus = "product"
    visual_evidence: VisualEvidenceLevel = "origin_reference"
    edit_capabilities: tuple[EditCapability, ...] = ()
    unsupported_edit_capabilities: tuple[EditCapability, ...] = ()

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
        if set(self.edit_capabilities) & set(self.unsupported_edit_capabilities):
            raise ValueError("supported and unsupported edit capabilities cannot overlap")
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


_BASE_CHART_REGISTRY: tuple[ChartRegistration, ...] = (
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
        optional_roles=("x", "x_lower", "x_upper", "lower", "upper", "error", "group"),
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
        optional_roles=("count",),
        required_calculations=("confusion_count",),
        allowed_calculations=("confusion_count",),
    ),
    _chart("X01", "Step plot", "special", ("step",), ("x", "y")),
    _chart(
        "X02",
        "Drop line plot",
        "special",
        ("drop_line",),
        ("x", "y"),
    ),
    _chart(
        "X03",
        "Origin lollipop plot",
        "special",
        ("lollipop",),
        ("category", "series_1", "series_2"),
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
        "X39",
        "Line series plot",
        "special",
        ("line_series",),
        ("series_1", "series_2"),
    ),
    _chart(
        "X40",
        "Before-after plot",
        "special",
        ("before_after",),
        ("series_1", "series_2"),
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

_PRODUCT_CHART_IDS: frozenset[ChartTypeId] = frozenset(
    {
        "K01",
        "K02",
        "K03",
        "K04",
        "K06",
        "K07",
        "K08",
        "K09",
        "K10",
        "K11",
        "K12",
        "K13",
        "K14",
        "K15",
        "K16",
        "K18",
        "K19",
        "K20",
        "K21",
        "K22",
        "K24",
        "K25",
        "S01",
        "S21",
        "S34",
        "S61",
        "X02",
        "X03",
        "X05",
        "X09",
        "X13",
        "X23",
        "X24",
        "X35",
        "X36",
        "X38",
        "X39",
        "X40",
    }
)

_REMOVED_CHART_IDS: frozenset[ChartTypeId] = frozenset(
    {"K05", "K17", "S05", "S07", "S25", "S31", "X01"}
)

_EDIT_PROFILES: dict[ChartTypeId, str] = {
    "K01": "GL",
    "K02": "GLM",
    "K03": "GM",
    "K04": "GMP",
    "K05": "GLME",
    "K06": "GME",
    "K07": "GLE",
    "K08": "GBE",
    "K09": "GBE",
    "K10": "GB",
    "K11": "GB",
    "K12": "GM",
    "K13": "GBL",
    "K14": "GBL",
    "K15": "GB",
    "K16": "GLB",
    "K17": "GL",
    "K18": "GLB",
    "K19": "GL",
    "K20": "GP",
    "K21": "GP",
    "K22": "GPL",
    "K24": "GFLM",
    "K25": "GF",
    "S01": "GLEF",
    "S05": "GLME",
    "S21": "GME",
    "S25": "GL",
    "S31": "GL",
    "S34": "GLM",
    "S61": "GP",
    "X01": "GL",
    "X02": "GLM",
    "X03": "GLM",
    "X05": "GM",
    "X07": "GLB",
    "X09": "GBM",
    "X11": "GBL",
    "X12": "GBM",
    "X13": "GB",
    "X15": "GMF",
    "X16": "GP",
    "X17": "GMBF",
    "X18": "GML",
    "X19": "GML",
    "X23": "GLMY",
    "X24": "GBLMY",
    "X35": "GBY",
    "X36": "GBLMY",
    "X37": "GBY",
    "X38": "GLO",
    "X39": "GLM",
    "X40": "GLM",
    "S07": "GM",
}

_ALL_EDIT_CAPABILITIES: tuple[EditCapability, ...] = get_args(EditCapability)
_PROFILE_CAPABILITIES: dict[str, tuple[EditCapability, ...]] = {
    "G": (
        "plot_title",
        "axis_label",
        "axis_range",
        "axis_scale",
        "axis_ticks",
        "font",
        "legend_visibility",
        "legend_position",
        "canvas_size",
        "publication_profile",
        "safe_annotation",
    ),
    "L": ("series_color", "line_width", "line_style"),
    "M": ("series_color", "marker_size", "symbol_shape", "symbol_interior"),
    "B": (
        "series_color",
        "line_width",
        "bar_fill",
        "bar_edge",
        "bar_width",
        "bar_gap",
    ),
    "E": ("series_color", "line_width", "marker_size", "error_style", "band_style"),
    "P": ("palette", "colorbar"),
    "Y": ("dual_y_style",),
    "F": ("panel_style",),
    "O": ("y_offset",),
}


def _edit_capabilities(profile: str) -> tuple[EditCapability, ...]:
    ordered: list[EditCapability] = []
    for code in profile:
        for capability in _PROFILE_CAPABILITIES[code]:
            if capability not in ordered:
                ordered.append(capability)
    return tuple(ordered)


def _qualified_registration(chart: ChartRegistration) -> ChartRegistration:
    supported = list(_edit_capabilities(_EDIT_PROFILES[chart.chart_type_id]))
    if chart.chart_type_id == "X24":
        supported.append("chart_parameters")
    admission: AdmissionStatus
    if chart.chart_type_id in _PRODUCT_CHART_IDS:
        admission = "product"
    elif chart.chart_type_id in _REMOVED_CHART_IDS:
        admission = "removed"
    else:
        admission = "internal_only"
    evidence: VisualEvidenceLevel
    if admission == "product" and chart.chart_type_id == "X24":
        evidence = "synthetic_visual"
    elif admission == "product":
        evidence = "origin_reference"
    else:
        evidence = "unqualified"
    return chart.model_copy(
        update={
            "admission": admission,
            "visual_evidence": evidence,
            "edit_capabilities": tuple(supported),
            "unsupported_edit_capabilities": tuple(
                capability for capability in _ALL_EDIT_CAPABILITIES if capability not in supported
            ),
        }
    )


CHART_REGISTRY: tuple[ChartRegistration, ...] = tuple(
    _qualified_registration(chart) for chart in _BASE_CHART_REGISTRY
)
CHARTS_BY_ID = {item.chart_type_id: item for item in CHART_REGISTRY}
PRODUCT_CHARTS: tuple[ChartRegistration, ...] = tuple(
    chart for chart in CHART_REGISTRY if chart.admission == "product"
)
PRODUCT_CHART_IDS: tuple[ChartTypeId, ...] = tuple(chart.chart_type_id for chart in PRODUCT_CHARTS)
REMOVED_CHART_IDS: tuple[ChartTypeId, ...] = tuple(
    chart.chart_type_id for chart in CHART_REGISTRY if chart.admission == "removed"
)

_EXPECTED_CHART_IDS = frozenset(get_args(ChartTypeId))
if set(CHARTS_BY_ID) != _EXPECTED_CHART_IDS or set(_EDIT_PROFILES) != _EXPECTED_CHART_IDS:
    raise RuntimeError("chart registry and capability metadata must cover every ChartTypeId")
if set(PRODUCT_CHART_IDS) != _PRODUCT_CHART_IDS:
    raise RuntimeError("product chart admission metadata is inconsistent")
if set(REMOVED_CHART_IDS) != _REMOVED_CHART_IDS:
    raise RuntimeError("removed chart admission metadata is inconsistent")


class ChartRegistry(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    charts: tuple[ChartRegistration, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> ChartRegistry:
        ids = tuple(chart.chart_type_id for chart in self.charts)
        if len(set(ids)) != len(ids):
            raise ValueError("chart registry ids must be unique")
        return self


V1_CHART_REGISTRY = ChartRegistry(charts=CHART_REGISTRY)
