"""Deterministic font selection for Agent Native Matplotlib renderers."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from matplotlib import font_manager
from matplotlib.ft2font import FT2Font

_CJK_FAMILIES = (
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "SimHei",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "Arial Unicode MS",
)


def _is_cjk(codepoint: int) -> bool:
    return (
        0x2E80 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x2FA1F
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )


def _supports(path: Path, codepoints: frozenset[int]) -> bool:
    try:
        face = FT2Font(path)
    except (OSError, RuntimeError):
        return False
    return all(face.get_char_index(codepoint) != 0 for codepoint in codepoints)


def resolve_font_family(texts: Iterable[str]) -> str:
    """Return the first installed family that covers every visible CJK glyph."""

    codepoints = frozenset(
        ord(character)
        for text in texts
        for character in text
        if _is_cjk(ord(character))
    )
    preferred = (
        (*_CJK_FAMILIES, "DejaVu Sans")
        if codepoints
        else ("Arial", "Microsoft YaHei", "DejaVu Sans")
    )
    for family in dict.fromkeys(preferred):
        try:
            path = Path(
                font_manager.findfont(
                    font_manager.FontProperties(family=[family]),
                    fallback_to_default=False,
                )
            )
        except ValueError:
            continue
        if path.is_file() and _supports(path, codepoints):
            return family
    requirement = "CJK-capable " if codepoints else ""
    raise RuntimeError(f"no {requirement}font is available for Matplotlib rendering")
