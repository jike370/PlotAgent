from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import pytest

from plotagent.contracts.base import Sha256
from plotagent.contracts.styles import resolve_palette
from plotagent.origin._origin_backend import NativeOriginError, OriginProBackend


def _backend(install_dir: Path) -> OriginProBackend:
    backend = cast(OriginProBackend, object.__new__(OriginProBackend))
    backend._install_dir = install_dir
    return backend


def test_qualified_palette_source_must_match_the_frozen_hash(tmp_path: Path) -> None:
    palette_dir = tmp_path / "Palettes"
    palette_dir.mkdir()
    asset = palette_dir / "GrayScale.PAL"
    frozen_bytes = b"plotagent-frozen-palette"
    asset.write_bytes(frozen_bytes)
    frozen_hash = cast(Sha256, hashlib.sha256(frozen_bytes).hexdigest())
    palette = resolve_palette("GrayScale").model_copy(update={"source_hash": frozen_hash})
    backend = _backend(tmp_path)

    backend._assert_palette_asset(palette)
    asset.write_bytes(b"locally-modified-palette")

    with pytest.raises(NativeOriginError, match="asset hash differs"):
        backend._assert_palette_asset(palette)


def test_palette_asset_lookup_is_closed_to_the_qualified_origin_folders(
    tmp_path: Path,
) -> None:
    palette = resolve_palette("ColorBlindSafe8")

    with pytest.raises(NativeOriginError, match="asset is missing"):
        _backend(tmp_path)._assert_palette_asset(palette)
