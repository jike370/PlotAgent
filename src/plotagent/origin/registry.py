"""Exact Origin O1 adapter registry for the frozen 31-chart v1 surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Never

from plotagent.charts.registry import CHARTS_BY_ID as RENDER_CHARTS_BY_ID
from plotagent.contracts.base import ChartTypeId

from .constants import ORIGIN_TEMPLATE_ID, ORIGIN_TEMPLATE_SHA256

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
    template_id: str = ORIGIN_TEMPLATE_ID
    template_sha256: str = ORIGIN_TEMPLATE_SHA256
    capability: Literal["O1"] = "O1"
    known_differences: tuple[str, ...] = ()


def _entry(
    chart_type_id: ChartTypeId,
    family: OriginAdapterFamily,
    geometries: tuple[str, ...],
    layout: OriginDataLayout = "worksheet",
) -> OriginAdapterRegistration:
    return OriginAdapterRegistration(
        chart_type_id=chart_type_id,
        adapter_family=family,
        allowed_geometries=geometries,
        data_layout=layout,
        adapter_id=f"plotagent.origin.{family}.{chart_type_id.lower()}",
        adapter_version="1.0.0",
    )


ORIGIN_ADAPTERS: tuple[OriginAdapterRegistration, ...] = (
    _entry("K01", "xy", ("xy.line",)),
    _entry("K02", "xy", ("xy.line", "xy.symbol")),
    _entry("K03", "xy", ("xy.symbol",)),
    _entry("K04", "xy", ("xy.bubble",)),
    _entry("K05", "xy", ("xy.symbol", "xy.line", "xy.band")),
    _entry("K06", "xy", ("xy.symbol", "xy.error")),
    _entry("K07", "xy", ("xy.line", "xy.band")),
    _entry("K08", "bar", ("bar.single",)),
    _entry("K09", "bar", ("bar.grouped",)),
    _entry("K10", "bar", ("bar.stacked",)),
    _entry("K11", "bar", ("bar.percent",)),
    _entry("K12", "distribution", ("distribution.strip",)),
    _entry("K13", "distribution", ("distribution.box",)),
    _entry("K14", "distribution", ("distribution.violin",)),
    _entry("K15", "distribution", ("distribution.histogram",)),
    _entry("K16", "distribution", ("distribution.density",)),
    _entry("K17", "distribution", ("distribution.step",)),
    _entry("K18", "xy", ("xy.area",)),
    _entry("K19", "xy", ("xy.datetime_line",)),
    _entry("K20", "matrix", ("matrix.heatmap",), "matrixbook"),
    _entry("K21", "matrix", ("matrix.correlation",), "matrixbook"),
    _entry("K22", "matrix", ("matrix.contour",), "matrixbook"),
    _entry("K24", "facet", ("facet.xy",)),
    _entry("K25", "facet", ("xy.line", "xy.symbol", "xy.error", "xy.band", "xy.area")),
    _entry(
        "S01",
        "special",
        ("special.survival_step", "special.survival_band", "special.risk_table"),
    ),
    _entry("S05", "xy", ("xy.symbol", "xy.line", "xy.band")),
    _entry("S21", "special", ("special.forest_interval", "special.forest_symbol")),
    _entry("S25", "xy", ("xy.spectrum",)),
    _entry("S31", "xy", ("xy.spectrum",)),
    _entry("S34", "xy", ("xy.nyquist",)),
    _entry("S61", "matrix", ("matrix.confusion",), "matrixbook"),
)

ORIGIN_ADAPTERS_BY_ID = {entry.chart_type_id: entry for entry in ORIGIN_ADAPTERS}


def _registry_failure(message: str) -> Never:
    raise RuntimeError(message)


if len(ORIGIN_ADAPTERS) != 31 or len(ORIGIN_ADAPTERS_BY_ID) != 31:
    _registry_failure("the Origin adapter registry must contain exactly 31 unique chart IDs")
if set(ORIGIN_ADAPTERS_BY_ID) != set(RENDER_CHARTS_BY_ID):
    _registry_failure("the Origin registry must exactly match the rendering registry")
for _chart_id, _adapter in ORIGIN_ADAPTERS_BY_ID.items():
    if _adapter.capability != "O1" or _adapter.known_differences:
        _registry_failure(f"{_chart_id} must declare O1 with no known differences")


class OriginAdapterNotFoundError(ValueError):
    code = "CAPABILITY_MISSING"


def get_origin_adapter(chart_type_id: str) -> OriginAdapterRegistration:
    """Return only a frozen v1 adapter; K23, S45, and all other IDs are rejected."""

    try:
        return ORIGIN_ADAPTERS_BY_ID[chart_type_id]  # type: ignore[index]
    except KeyError as error:
        raise OriginAdapterNotFoundError(
            f"{chart_type_id!r} has no qualified v1 Origin O1 adapter"
        ) from error
