"""Small deterministic contract fixtures."""

from __future__ import annotations

from plotagent.contracts.base import (
    ColorValue,
    ContentTableRef,
    PhysicalLength,
    PhysicalSize,
    PreparedDatasetRef,
)
from plotagent.contracts.plots import (
    AxisSpec,
    PlotProvenance,
    PlotSpec,
    PreparedSeriesData,
    PublicationProfileSnapshot,
    ResolvedStyleSnapshot,
    SafeRichText,
    SafeTextNode,
    ScaleSpec,
    SeriesSpec,
    StyleSourceRef,
    XYFamily,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def prepared_ref() -> PreparedDatasetRef:
    return PreparedDatasetRef(
        prepared_dataset_id="prepared:test",
        prepared_version=1,
        content_hash=HASH_A,
    )


def table_ref(*fields: str, rows: int = 4, object_hash: str = HASH_B) -> ContentTableRef:
    return ContentTableRef(object_hash=object_hash, row_count=rows, field_ids=fields)


def rich_text(text: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=text),))


def physical_size() -> PhysicalSize:
    return PhysicalSize(
        width=PhysicalLength(value=89.0, unit="mm"),
        height=PhysicalLength(value=60.0, unit="mm"),
    )


def style() -> ResolvedStyleSnapshot:
    return ResolvedStyleSnapshot(
        font_family="Arial",
        font_size=PhysicalLength(value=8.0, unit="pt"),
        line_width=PhysicalLength(value=0.8, unit="pt"),
        marker_size=PhysicalLength(value=4.0, unit="pt"),
        colors=(ColorValue(value="#1F77B4"),),
    )


def profile() -> PublicationProfileSnapshot:
    return PublicationProfileSnapshot(
        profile_id="profile.nature",
        profile_version=1,
        content_hash=HASH_B,
        physical_size=physical_size(),
        dpi=300,
    )


def minimal_plot() -> PlotSpec:
    prepared = prepared_ref()
    return PlotSpec(
        plot_id="plot:test",
        plot_version=1,
        chart_type_id="K01",
        family=XYFamily(geometry=("line",)),
        prepared_data_refs=(prepared,),
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
                label=rich_text("X"),
            ),
            AxisSpec(
                axis_id="axis:y",
                scale_id="scale:y",
                orientation="y",
                position="left",
                label=rich_text("Y"),
            ),
        ),
        series=(
            SeriesSpec(
                series_id="series:main",
                geometry="line",
                data=PreparedSeriesData(
                    prepared_dataset_ref=prepared,
                    role_fields=("field:x", "field:y"),
                ),
            ),
        ),
        style_sources=(
            StyleSourceRef(
                source_kind="project",
                source_id="style.default",
                source_version=1,
                content_hash=HASH_A,
            ),
        ),
        resolved_style=style(),
        publication_profile=profile(),
        provenance=PlotProvenance(origin="manual", engine_build_hash=HASH_C),
    )
