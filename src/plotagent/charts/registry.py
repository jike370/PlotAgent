"""Rendering metadata for the exact 52 first-release scientific charts.

The W0 contract registry is the persisted public contract.  This module adds the
W4-only adapter family, data-chain mode, and renderer limitations.  Every chart
has an explicit entry so a capability review never depends on name heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Never

from plotagent.contracts.base import CalculationKind, ChartTypeId, PrecomputedKind
from plotagent.contracts.registry import (
    CHARTS_BY_ID as CONTRACT_CHARTS_BY_ID,
)
from plotagent.contracts.registry import (
    PRODUCT_CHART_IDS,
    AdmissionStatus,
    EditCapability,
    VisualEvidenceLevel,
)

AdapterFamily = Literal["xy", "bar", "distribution", "matrix", "special", "facet"]
DataChainMode = Literal["direct", "fixed", "user_precomputed", "panel_plans"]


@dataclass(frozen=True, slots=True)
class ExportCapability:
    png: bool
    svg: bool
    opju: Literal["O1"]


V1_EXPORTS = ExportCapability(png=True, svg=True, opju="O1")


@dataclass(frozen=True, slots=True)
class ChartAdapterRegistration:
    chart_type_id: ChartTypeId
    adapter_family: AdapterFamily
    required_roles: tuple[str, ...]
    optional_roles: tuple[str, ...]
    data_modes: tuple[DataChainMode, ...]
    fixed_calculations: tuple[CalculationKind, ...]
    required_precomputed: tuple[PrecomputedKind, ...]
    exports: ExportCapability
    limitations: tuple[str, ...]
    admission: AdmissionStatus
    visual_evidence: VisualEvidenceLevel
    edit_capabilities: tuple[EditCapability, ...]


def _entry(
    chart_type_id: ChartTypeId,
    adapter_family: AdapterFamily,
    required_roles: tuple[str, ...],
    optional_roles: tuple[str, ...],
    data_modes: tuple[DataChainMode, ...],
    fixed_calculations: tuple[CalculationKind, ...],
    required_precomputed: tuple[PrecomputedKind, ...],
    limitations: tuple[str, ...],
) -> ChartAdapterRegistration:
    contract = CONTRACT_CHARTS_BY_ID[chart_type_id]
    return ChartAdapterRegistration(
        chart_type_id=chart_type_id,
        adapter_family=adapter_family,
        required_roles=required_roles,
        optional_roles=optional_roles,
        data_modes=data_modes,
        fixed_calculations=fixed_calculations,
        required_precomputed=required_precomputed,
        exports=V1_EXPORTS,
        limitations=limitations,
        admission=contract.admission,
        visual_evidence=contract.visual_evidence,
        edit_capabilities=contract.edit_capabilities,
    )


CHARTS: tuple[ChartAdapterRegistration, ...] = (
    _entry(
        "K01",
        "xy",
        ("x", "y"),
        (),
        ("direct",),
        (),
        (),
        ("Input order is preserved; the renderer does not sort or aggregate.",),
    ),
    _entry(
        "K02",
        "xy",
        ("x", "y"),
        (),
        ("direct",),
        (),
        (),
        ("Line and symbols consume the same supplied observations.",),
    ),
    _entry(
        "K03",
        "xy",
        ("x", "y"),
        ("group",),
        ("direct",),
        (),
        (),
        ("Jitter, when requested, is resolved deterministically before rendering.",),
    ),
    _entry(
        "K04",
        "xy",
        ("x", "y"),
        ("size", "color", "group"),
        ("direct",),
        (),
        (),
        ("Bubble area and continuous color are resolved from supplied fields only.",),
    ),
    _entry(
        "K05",
        "xy",
        ("x", "y"),
        ("lower", "upper"),
        ("direct", "user_precomputed"),
        (),
        ("curve",),
        ("No regression or interval estimation is performed.",),
    ),
    _entry(
        "K06",
        "xy",
        ("center",),
        ("lower", "upper", "error", "group"),
        ("direct", "fixed"),
        ("summary_error",),
        (),
        ("Bounds or symmetric error semantics must already be explicit.",),
    ),
    _entry(
        "K07",
        "xy",
        ("x", "center"),
        ("lower", "upper", "group"),
        ("direct", "fixed"),
        ("summary_error",),
        (),
        ("The adapter never estimates a confidence interval.",),
    ),
    _entry(
        "K08",
        "bar",
        ("category", "value"),
        (),
        ("direct", "fixed"),
        ("summary_error",),
        (),
        ("The numeric axis includes zero.",),
    ),
    _entry(
        "K09",
        "bar",
        ("category", "group", "value"),
        (),
        ("direct", "fixed"),
        ("summary_error",),
        (),
        ("Group order follows the supplied stable order.",),
    ),
    _entry(
        "K10",
        "bar",
        ("category", "component", "value"),
        (),
        ("direct",),
        (),
        (),
        ("Positive and negative stacks use separate supplied-value accumulators.",),
    ),
    _entry(
        "K11",
        "bar",
        ("category", "component", "value"),
        (),
        ("fixed",),
        ("percent_stack",),
        (),
        ("Percent normalization must come from W3 output.",),
    ),
    _entry(
        "K12",
        "distribution",
        ("value",),
        ("group",),
        ("direct",),
        (),
        (),
        ("Visual jitter is deterministic and does not alter source values.",),
    ),
    _entry(
        "K13",
        "distribution",
        ("value",),
        ("group",),
        ("fixed",),
        ("tukey_box",),
        (),
        ("Quartiles, whiskers, and outliers come from W3 geometry.",),
    ),
    _entry(
        "K14",
        "distribution",
        ("value",),
        ("group",),
        ("fixed",),
        ("violin_kde",),
        (),
        ("Density grids and bandwidths come from W3 geometry.",),
    ),
    _entry(
        "K15",
        "distribution",
        ("value",),
        (),
        ("fixed",),
        ("histogram_binning",),
        (),
        ("Bin edges and heights come from W3 geometry.",),
    ),
    _entry(
        "K16",
        "distribution",
        ("value",),
        ("group",),
        ("fixed",),
        ("density_kde",),
        (),
        ("KDE grids and density values come from W3 geometry.",),
    ),
    _entry(
        "K17",
        "distribution",
        ("value",),
        (),
        ("fixed",),
        ("ecdf",),
        (),
        ("Step coordinates and ECDF/CCDF mode come from W3 geometry.",),
    ),
    _entry(
        "K18",
        "xy",
        ("x", "y"),
        (),
        ("direct",),
        (),
        (),
        ("Area uses a zero baseline and does not aggregate observations.",),
    ),
    _entry(
        "K19",
        "xy",
        ("time", "value"),
        ("event",),
        ("direct",),
        (),
        (),
        ("No resampling, timezone conversion, or aggregation is performed.",),
    ),
    _entry(
        "K20",
        "matrix",
        ("row", "column", "value"),
        (),
        ("direct", "fixed"),
        ("matrix_projection",),
        (),
        ("Coordinates must be unique; cells are never aggregated.",),
    ),
    _entry(
        "K21",
        "matrix",
        ("row_label", "column_label", "value"),
        (),
        ("user_precomputed",),
        (),
        ("matrix",),
        ("No correlation or significance calculation is performed.",),
    ),
    _entry(
        "K22",
        "matrix",
        ("x", "y", "z"),
        (),
        ("user_precomputed",),
        (),
        ("matrix_grid",),
        ("Only a complete regular grid is accepted; no interpolation.",),
    ),
    _entry(
        "K24",
        "facet",
        ("facet", "base_x", "base_y"),
        (),
        ("direct",),
        (),
        (),
        ("Panels are split only by the explicit facet field.",),
    ),
    _entry(
        "K25",
        "facet",
        ("panel",),
        (),
        ("panel_plans",),
        (),
        (),
        ("Only explicit child RenderPlans and placements are accepted.",),
    ),
    _entry(
        "S01",
        "special",
        ("time", "survival"),
        ("lower", "upper", "risk_count", "group"),
        ("user_precomputed",),
        (),
        ("step_curve",),
        ("No KM, Greenwood, log-rank, or Cox calculation is performed.",),
    ),
    _entry(
        "S05",
        "xy",
        ("dose", "response"),
        ("lower", "upper", "parameter"),
        ("direct", "user_precomputed"),
        (),
        ("curve",),
        ("No 4PL/5PL fit or dose metric estimation is performed.",),
    ),
    _entry(
        "S21",
        "special",
        ("label", "effect", "lower", "upper"),
        ("weight",),
        ("user_precomputed",),
        (),
        ("effect_interval",),
        ("No meta-analysis pooling or effect calculation is performed.",),
    ),
    _entry(
        "S25",
        "xy",
        ("spectral_axis", "intensity"),
        (),
        ("user_precomputed",),
        (),
        ("spectrum",),
        ("No baseline, smoothing, or normalization is performed.",),
    ),
    _entry(
        "S31",
        "xy",
        ("angle", "intensity"),
        ("peak_label",),
        ("user_precomputed",),
        (),
        ("spectrum",),
        ("No background removal, peak finding, or fitting is performed.",),
    ),
    _entry(
        "S34",
        "xy",
        ("z_real", "z_imaginary"),
        ("frequency",),
        ("user_precomputed",),
        (),
        ("complex_curve",),
        ("No equivalent-circuit fit is performed.",),
    ),
    _entry(
        "S61",
        "matrix",
        ("actual", "predicted"),
        (),
        ("fixed",),
        ("confusion_count",),
        (),
        ("Counts and normalization come from W3 geometry.",),
    ),
    _entry(
        "X01",
        "special",
        ("x", "y"),
        (),
        ("direct",),
        (),
        (),
        ("Input order is preserved; step direction is a closed visual preset.",),
    ),
    _entry(
        "X02",
        "special",
        ("category", "value"),
        ("baseline", "group"),
        ("direct",),
        (),
        (),
        ("The baseline is visual geometry and defaults to zero.",),
    ),
    _entry(
        "X03",
        "special",
        ("category", "start", "end"),
        ("group",),
        ("direct",),
        (),
        (),
        ("No pairing is inferred; each row is one explicit pair.",),
    ),
    _entry(
        "X05",
        "special",
        ("value",),
        ("group",),
        ("direct",),
        (),
        (),
        ("Beeswarm displacement is deterministic and never changes source values.",),
    ),
    _entry(
        "X07",
        "special",
        ("value", "group"),
        (),
        ("direct",),
        (),
        (),
        ("KDE and vertical offsets are fixed chart-only geometry.",),
    ),
    _entry(
        "X09",
        "special",
        ("category", "start", "end"),
        ("middle",),
        ("direct",),
        (),
        (),
        ("Start and end must be explicit; an optional middle boundary creates two segments.",),
    ),
    _entry(
        "X11",
        "special",
        ("category", "delta"),
        (),
        ("direct",),
        (),
        (),
        ("Only the cumulative bridge geometry is calculated.",),
    ),
    _entry(
        "X12",
        "special",
        ("item", "actual_value", "target"),
        ("range1", "range2", "range3"),
        ("direct",),
        (),
        (),
        ("Qualitative ranges and targets must be supplied.",),
    ),
    _entry(
        "X13",
        "special",
        ("category", "left", "right"),
        (),
        ("direct",),
        (),
        (),
        ("Both sides share a zero baseline and absolute tick labels.",),
    ),
    _entry(
        "X15",
        "special",
        ("x", "y", "z"),
        (),
        ("direct",),
        (),
        (),
        ("The first-release matrix accepts exactly three supplied variables.",),
    ),
    _entry(
        "X16",
        "special",
        ("x", "y"),
        (),
        ("direct",),
        (),
        (),
        ("Two-dimensional binning is fixed chart-only geometry.",),
    ),
    _entry(
        "X17",
        "special",
        ("x", "y"),
        (),
        ("direct",),
        (),
        (),
        ("Marginal histograms use the same observations as the central scatter.",),
    ),
    _entry(
        "X18",
        "special",
        ("value",),
        (),
        ("direct",),
        (),
        (),
        ("Normal theoretical quantiles and reference line are fixed chart-only geometry.",),
    ),
    _entry(
        "X19",
        "special",
        ("method_a", "method_b"),
        (),
        ("direct",),
        (),
        (),
        ("Mean difference and limits of agreement are fixed chart-only calculations.",),
    ),
    _entry(
        "X23",
        "special",
        ("x", "left", "right"),
        (),
        ("direct",),
        (),
        (),
        ("Axis ownership is explicit; automatic dual-axis suggestions are forbidden.",),
    ),
    _entry(
        "X24",
        "special",
        ("category", "value"),
        (),
        ("direct",),
        (),
        (),
        ("Descending order and cumulative percentage are fixed chart-only calculations.",),
    ),
    _entry(
        "X35",
        "special",
        ("category", "left", "right"),
        (),
        ("direct",),
        (),
        (),
        ("Axis ownership is explicit; automatic dual-axis suggestions are forbidden.",),
    ),
    _entry(
        "X36",
        "special",
        ("category", "left", "right"),
        (),
        ("direct",),
        (),
        (),
        ("Left values are columns and right values are a line on an explicit axis.",),
    ),
    _entry(
        "X37",
        "special",
        ("group", "left", "right"),
        (),
        ("direct",),
        (),
        (),
        ("Quartiles are fixed chart-only geometry on two explicit Y axes.",),
    ),
    _entry(
        "X38",
        "special",
        ("x", "y", "series"),
        (),
        ("direct",),
        (),
        (),
        ("Offsets affect display only and never modify persisted source data.",),
    ),
    _entry(
        "S07",
        "special",
        ("feature", "log2fc", "pvalue"),
        ("qvalue",),
        ("direct",),
        (),
        (),
        ("No differential expression or FDR calculation is performed.",),
    ),
)

CHARTS_BY_ID = {entry.chart_type_id: entry for entry in CHARTS}


def _fail_registry(message: str) -> Never:
    raise RuntimeError(message)


if set(CHARTS_BY_ID) != set(CONTRACT_CHARTS_BY_ID):
    _fail_registry("the W4 chart IDs must exactly match the W0 contract registry")
for _chart_id, _runtime in CHARTS_BY_ID.items():
    _contract = CONTRACT_CHARTS_BY_ID[_chart_id]
    if _runtime.required_roles != _contract.required_roles:
        _fail_registry(f"{_chart_id} required roles drifted from the W0 contract")
    if _runtime.optional_roles != _contract.optional_roles:
        _fail_registry(f"{_chart_id} optional roles drifted from the W0 contract")
    if set(_runtime.fixed_calculations) != set(_contract.allowed_calculations):
        _fail_registry(f"{_chart_id} fixed calculations drifted from the W0 contract")
    if _runtime.required_precomputed != _contract.required_precomputed:
        _fail_registry(f"{_chart_id} precomputed requirements drifted from the W0 contract")
    if not (_runtime.exports.png and _runtime.exports.svg and _runtime.exports.opju == "O1"):
        _fail_registry(f"{_chart_id} must retain PNG/SVG and O1 capability")


class ChartRegistryError(ValueError):
    code = "PLOTSPEC_CHART_UNKNOWN"


def get_chart(chart_type_id: str) -> ChartAdapterRegistration:
    """Return any internal adapter, including entries hidden from product admission."""

    try:
        return CHARTS_BY_ID[chart_type_id]  # type: ignore[index]
    except KeyError as error:
        raise ChartRegistryError(f"{chart_type_id!r} is not a first-release chart type") from error


def get_product_chart(chart_type_id: str) -> ChartAdapterRegistration:
    """Return a user/Agent-admitted chart and reject internal-only adapters."""

    chart = get_chart(chart_type_id)
    if chart.admission != "product":
        raise ChartRegistryError(f"{chart_type_id!r} is retained for internal regression only")
    return chart


PRODUCT_CHARTS = tuple(CHARTS_BY_ID[chart_id] for chart_id in PRODUCT_CHART_IDS)


def patch_operations_for_chart(chart_type_id: str) -> tuple[str, ...]:
    """Project edit capability metadata onto the closed Agent patch vocabulary."""

    capabilities = set(get_chart(chart_type_id).edit_capabilities)
    operations: list[str] = []
    for operation, required in (
        ("set_axis_range", {"axis_range"}),
        ("set_axis_scale", {"axis_scale"}),
        ("set_axis_label", {"axis_label"}),
        (
            "set_series_style",
            {
                "series_color",
                "line_width",
                "line_style",
                "marker_size",
                "symbol_shape",
                "symbol_interior",
            },
        ),
        ("set_category_color", {"series_color"}),
        ("set_palette", {"palette"}),
        ("set_legend_visibility", {"legend_visibility"}),
        ("move_legend", {"legend_position"}),
        ("apply_publication_profile", {"publication_profile"}),
        ("set_canvas_size", {"canvas_size"}),
    ):
        if capabilities & required:
            operations.append(operation)
    return tuple(operations)
