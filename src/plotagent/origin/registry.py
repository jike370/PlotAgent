"""Template-first Origin O1 adapter registry for the 38-chart product surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Never

from plotagent.contracts.base import ChartTypeId
from plotagent.contracts.engine_profiles import CHART_PROFILES_BY_ID, TemplateTier
from plotagent.contracts.registry import PRODUCT_CHART_IDS

OriginAdapterFamily = Literal["xy", "bar", "distribution", "matrix", "special", "facet"]
OriginDataLayout = Literal["worksheet", "matrixbook"]


@dataclass(frozen=True, slots=True)
class OriginAdapterRegistration:
    chart_type_id: ChartTypeId
    adapter_family: OriginAdapterFamily
    allowed_geometries: tuple[str, ...]
    data_layout: OriginDataLayout
    adapter_id: str
    adapter_version: str
    template_filename: str
    template_sha256: str
    template_tier: TemplateTier
    binder_id: str
    declared_patch_ids: tuple[str, ...]
    capability: Literal["O1"] = "O1"
    known_differences: tuple[str, ...] = ()


# family, allowed geometries, native data layout. Template identity and binder
# come exclusively from the frozen ChartProfile catalog.
_ADAPTER_ROWS: dict[
    ChartTypeId,
    tuple[OriginAdapterFamily, tuple[str, ...], OriginDataLayout],
] = {
    "K01": ("xy", ("xy.line",), "worksheet"),
    "K02": ("xy", ("xy.line", "xy.symbol"), "worksheet"),
    "K03": ("xy", ("xy.symbol",), "worksheet"),
    "K04": ("xy", ("xy.bubble",), "worksheet"),
    "K06": ("xy", ("xy.symbol", "xy.error"), "worksheet"),
    "K07": ("xy", ("xy.line", "xy.band"), "worksheet"),
    "K08": ("bar", ("bar.single",), "worksheet"),
    "K09": ("bar", ("bar.grouped",), "worksheet"),
    "K10": ("bar", ("bar.stacked",), "worksheet"),
    "K11": ("bar", ("bar.percent",), "worksheet"),
    "K12": ("distribution", ("distribution.strip",), "worksheet"),
    "K13": ("distribution", ("distribution.box",), "worksheet"),
    "K14": ("distribution", ("distribution.violin",), "worksheet"),
    "K15": ("distribution", ("distribution.histogram",), "worksheet"),
    "K16": ("distribution", ("distribution.density",), "worksheet"),
    "K18": ("xy", ("xy.area",), "worksheet"),
    "K19": ("xy", ("xy.datetime_line",), "worksheet"),
    "K20": ("matrix", ("matrix.heatmap",), "matrixbook"),
    "K21": ("matrix", ("matrix.correlation",), "matrixbook"),
    "K22": ("matrix", ("matrix.contour",), "matrixbook"),
    "K24": ("facet", ("facet.xy",), "worksheet"),
    "K25": ("facet", ("xy.line", "xy.symbol", "xy.error", "xy.band", "xy.area"), "worksheet"),
    "S01": (
        "special",
        ("special.survival_step", "special.survival_band", "special.risk_table"),
        "worksheet",
    ),
    "S21": (
        "special",
        ("special.forest_interval", "special.forest_symbol"),
        "worksheet",
    ),
    "S34": ("xy", ("xy.nyquist",), "worksheet"),
    "S61": ("matrix", ("matrix.confusion",), "matrixbook"),
    "X02": ("special", ("special.drop_line",), "worksheet"),
    "X03": ("special", ("xy.line", "xy.symbol"), "worksheet"),
    "X05": ("special", ("distribution.strip",), "worksheet"),
    "X09": ("special", ("bar.floating",), "worksheet"),
    "X13": ("special", ("bar.horizontal",), "worksheet"),
    "X23": ("special", ("xy.line",), "worksheet"),
    "X24": ("special", ("bar.single", "xy.line"), "worksheet"),
    "X35": ("special", ("bar.floating",), "worksheet"),
    "X36": ("special", ("bar.single", "xy.line"), "worksheet"),
    "X38": ("special", ("xy.line",), "worksheet"),
    "X39": ("special", ("xy.line", "xy.symbol"), "worksheet"),
    "X40": ("special", ("xy.line", "xy.symbol"), "worksheet"),
}


def _entry(chart_type_id: ChartTypeId) -> OriginAdapterRegistration:
    family, geometries, layout = _ADAPTER_ROWS[chart_type_id]
    profile = CHART_PROFILES_BY_ID[chart_type_id]
    return OriginAdapterRegistration(
        chart_type_id=chart_type_id,
        adapter_family=family,
        allowed_geometries=geometries,
        data_layout=layout,
        adapter_id=profile.origin.binder_id,
        adapter_version=profile.profile_version,
        template_filename=profile.origin.filename,
        template_sha256=profile.origin.sha256,
        template_tier=profile.origin.tier,
        binder_id=profile.origin.binder_id,
        declared_patch_ids=profile.origin.declared_patch_ids,
    )


ORIGIN_ADAPTERS: tuple[OriginAdapterRegistration, ...] = tuple(
    _entry(chart_type_id) for chart_type_id in PRODUCT_CHART_IDS
)
ORIGIN_ADAPTERS_BY_ID = {entry.chart_type_id: entry for entry in ORIGIN_ADAPTERS}


def _registry_failure(message: str) -> Never:
    raise RuntimeError(message)


if set(_ADAPTER_ROWS) != set(PRODUCT_CHART_IDS):
    _registry_failure("Origin adapter rows must exactly match the 38-chart product surface")
if len(ORIGIN_ADAPTERS) != 38 or len(ORIGIN_ADAPTERS_BY_ID) != 38:
    _registry_failure("the Origin adapter registry must contain exactly 38 unique chart IDs")
for _chart_id, _adapter in ORIGIN_ADAPTERS_BY_ID.items():
    if _adapter.capability != "O1" or _adapter.known_differences:
        _registry_failure(f"{_chart_id} must declare O1 with no known differences")


class OriginAdapterNotFoundError(ValueError):
    code = "CAPABILITY_MISSING"


def get_origin_adapter(chart_type_id: str) -> OriginAdapterRegistration:
    """Return one frozen template-first product adapter; all other IDs are rejected."""

    try:
        return ORIGIN_ADAPTERS_BY_ID[chart_type_id]  # type: ignore[index]
    except KeyError as error:
        raise OriginAdapterNotFoundError(
            f"{chart_type_id!r} has no template-first Origin O1 adapter"
        ) from error
