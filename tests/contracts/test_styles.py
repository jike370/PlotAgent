from __future__ import annotations

import pytest
from pydantic import ValidationError

from plotagent.contracts.styles import (
    ORIGIN_INTERIOR_CODES,
    PALETTE_IDS,
    SYMBOL_MAPPINGS,
    SymbolStyle,
    resolve_palette,
)


def test_origin_style_catalog_is_closed_and_stable() -> None:
    assert len(PALETTE_IDS) == len(set(PALETTE_IDS)) == 16
    assert len(SYMBOL_MAPPINGS) == 12
    assert tuple(ORIGIN_INTERIOR_CODES) == ("solid", "open", "hollow")
    assert resolve_palette("GrayScale").source_hash == (
        "9bafc5fca3adfdc8270b9f132e09c66ef9d7df6d6c42109009e11aa6208d05fc"
    )
    assert resolve_palette("ColorBlindSafe8").origin_asset_kind == "color_list"
    assert resolve_palette("Viridis").origin_asset_kind == "palette"


@pytest.mark.parametrize("palette_id", PALETTE_IDS)
def test_every_palette_has_a_deterministic_reverse(palette_id: str) -> None:
    forward = resolve_palette(palette_id)  # type: ignore[arg-type]
    reverse = resolve_palette(palette_id, reverse=True)  # type: ignore[arg-type]
    assert reverse.colors == tuple(reversed(forward.colors))
    assert reverse.source_hash == forward.source_hash
    assert reverse.resolved_rgb_hash != forward.resolved_rgb_hash


@pytest.mark.parametrize("shape", tuple(SYMBOL_MAPPINGS))
def test_symbol_interior_contract_matches_enclosed_geometry(shape: str) -> None:
    SymbolStyle(shape=shape, interior="solid")  # type: ignore[arg-type]
    if shape in {"plus", "cross"}:
        for interior in ("open", "hollow"):
            with pytest.raises(ValidationError):
                SymbolStyle(shape=shape, interior=interior)  # type: ignore[arg-type]
    else:
        SymbolStyle(shape=shape, interior="open")  # type: ignore[arg-type]
        SymbolStyle(shape=shape, interior="hollow")  # type: ignore[arg-type]
