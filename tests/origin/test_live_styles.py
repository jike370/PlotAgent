from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

from plotagent.contracts.plots import SafeRichText, SafeTextNode
from plotagent.contracts.styles import (
    PALETTE_IDS,
    SYMBOL_MAPPINGS,
    SymbolInterior,
    SymbolStyle,
    resolve_palette,
)
from plotagent.origin import export_origin
from plotagent.origin.models import OriginExportSuccess
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.rendering import PlotResolver
from tests.rendering.fixture_factory import build_plot_and_store

RUN_LIVE = os.environ.get("PLOTAGENT_RUN_ORIGIN_LIVE_STYLES") == "1"


def _label(text: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=text),))


def _symbol_variants() -> tuple[SymbolStyle, ...]:
    variants: list[SymbolStyle] = []
    for shape in SYMBOL_MAPPINGS:
        interiors = ("solid",) if shape in {"plus", "cross"} else (
            "solid",
            "open",
            "hollow",
        )
        variants.extend(
            SymbolStyle(shape=shape, interior=cast(SymbolInterior, interior))
            for interior in interiors
        )
    return tuple(variants)


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="set PLOTAGENT_RUN_ORIGIN_LIVE_STYLES=1 to run native style readback",
)
def test_all_origin_symbols_and_palettes_survive_fresh_reopen(tmp_path: Path) -> None:
    symbol_plot, symbol_store = build_plot_and_store("K02")
    line_seed, symbol_seed = symbol_plot.series
    symbol_series = tuple(
        symbol_seed.model_copy(
            update={
                "series_id": f"series:style.symbol.{index}",
                "label": _label(f"{variant.shape}/{variant.interior}"),
                "style": symbol_seed.style.model_copy(update={"symbol": variant}),
            }
        )
        for index, variant in enumerate(_symbol_variants())
    )
    symbols = symbol_plot.model_copy(
        update={
            "plot_id": "plot:style.symbols",
            "series": (line_seed, *symbol_series),
        }
    )
    resolved = [PlotResolver().resolve(symbols, symbol_store)]

    palette_plot, palette_store = build_plot_and_store("K20")
    for palette_id in PALETTE_IDS:
        for reverse in (False, True):
            suffix = "reverse" if reverse else "forward"
            series = palette_plot.series[0].model_copy(
                update={
                    "series_id": f"series:style.palette.{palette_id.lower()}.{suffix}",
                    "style": palette_plot.series[0].style.model_copy(
                        update={"palette": resolve_palette(palette_id, reverse=reverse)}
                    ),
                }
            )
            plot = palette_plot.model_copy(
                update={
                    "plot_id": f"plot:style.palette.{palette_id.lower()}.{suffix}",
                    "series": (series,),
                }
            )
            resolved.append(PlotResolver().resolve(plot, palette_store))

    resolved_tuple = tuple(resolved)
    plan = compile_origin_plan(
        resolved_tuple,
        build_origin_export_spec(resolved_tuple, export_id="export:live.styles"),
    )
    target = tmp_path / "origin-styles.opju"

    result = export_origin(plan, target, timeout_seconds=300.0)

    assert isinstance(result, OriginExportSuccess), result.to_dict()
    assert result.build_validation == result.reopen_validation
    assert target.is_file() and target.stat().st_size > 0
