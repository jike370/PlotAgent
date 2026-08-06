"""Closed, renderer-neutral style identifiers qualified against Origin 2024 SR1.

Palette definitions below freeze the renderer-neutral sRGB truth extracted from
the build-pinned Origin install.  Matplotlib consumes those values directly.
Native Origin export may use only the matching asset in the qualified Origin
installation after its SHA-256 has been verified; user or modified palette files
are never accepted as substitutes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from plotagent.contracts.base import ColorValue, Sha256, StrictModel
from plotagent.contracts.canonical import JsonValue, canonical_hash

SymbolShape = Literal[
    "square",
    "circle",
    "triangle_up",
    "triangle_down",
    "diamond",
    "plus",
    "cross",
    "triangle_left",
    "triangle_right",
    "hexagon",
    "star",
    "pentagon",
]
SymbolInterior = Literal["solid", "open", "hollow"]
LineStyle = Literal["solid", "dashed", "dotted", "dash_dot"]
PaletteKind = Literal["qualitative", "sequential", "diverging", "special", "grayscale"]
PaletteId = Literal[
    "ColorBlindSafe8",
    "ColorBlindSafe15",
    "BlueOrange",
    "OrangeNavy",
    "RedPurple",
    "Viridis",
    "Plasma",
    "Inferno",
    "Magma",
    "GreyBlue",
    "YellowBlue",
    "YellowGreen",
    "YellowPurple",
    "Fire",
    "Rainbow_Modified",
    "GrayScale",
]

_ORIGIN_SOURCE_HASHES: dict[PaletteId, Sha256] = {
    "ColorBlindSafe8": "75467337f5b50e454ea58110b08530f577c64572a157c743e52c9ab9c333e2b4",
    "ColorBlindSafe15": "8c73a90799825a641b20b70a837736fca801be5d22b6990f6c8ff348cea3889a",
    "BlueOrange": "bb87fea2bcf7ad77e8f9a5d4e3b7ef4d5ef545c581253e1b04592de90ce21f0a",
    "OrangeNavy": "45fecff859a1d85b6ab21e8aa4791b3d6ba76e31c559929368a16927b2ae4d8f",
    "RedPurple": "316031644e3a999e826fd87e0335a3bb476cb931fa4bc71658e514ad3e22a0b2",
    "Viridis": "984a67597f612bb61340544255233934bb0f75a95b4fa7799e7ffba0181e7c2e",
    "Plasma": "d7713aafdd18d3c7af75993e4e852182ecbbfdfd6aa55307505477fe2cfee8b6",
    "Inferno": "cf5a01013eba8e7d8ba321d8c0c2611456d96218d038f440fe928c2b7aa4dfbf",
    "Magma": "2c5fff8c4511d24c516ebbc3c53c0c1b1e3b27b390bc4ec2cf0ae73cef54b2f0",
    "GreyBlue": "f8e59056df561e234e6995b19df5c9511a8a7bbf2aeffb4961ada15a44f89ea2",
    "YellowBlue": "20551dd2746d9f4c227fdaaea2805a1e57653b3e389e5b8a04a6311dce62dc92",
    "YellowGreen": "dfeb1bfcb05e64676b1cbef069ad9e471c37dcd312f6f5d7fc7d2bd2dc5276c9",
    "YellowPurple": "2f03f86db99dd3b4206111f63428e3aa0d3898afb802ebdd848efbc8dab2e354",
    "Fire": "d3a7522b18d28aa14f3898afd601f931de454e41953728b74098f35ab2e6ad8c",
    "Rainbow_Modified": "3346e6e22ef8fd347500ea9d2427ed3fbd329d6005009875bfcfd6a1ba61e47f",
    "GrayScale": "9bafc5fca3adfdc8270b9f132e09c66ef9d7df6d6c42109009e11aa6208d05fc",
}


class SymbolStyle(StrictModel):
    shape: SymbolShape = "circle"
    interior: SymbolInterior = "solid"

    @model_validator(mode="after")
    def interior_matches_shape(self) -> SymbolStyle:
        if self.shape in {"plus", "cross"} and self.interior != "solid":
            raise ValueError("plus and cross have no enclosed interior in either renderer")
        return self


class ResolvedPalette(StrictModel):
    palette_id: PaletteId
    origin_source_name: str
    origin_asset_kind: Literal["color_list", "palette"]
    kind: PaletteKind
    colors: Annotated[tuple[ColorValue, ...], Field(min_length=2)]
    reverse: bool = False
    source_version: Literal["Origin2024 SR1 10.10.178"] = "Origin2024 SR1 10.10.178"
    source_hash: Sha256
    resolved_rgb_hash: Sha256

    @model_validator(mode="after")
    def canonical_source_hash(self) -> ResolvedPalette:
        if self.source_hash != _ORIGIN_SOURCE_HASHES[self.palette_id]:
            raise ValueError("palette source_hash does not match the pinned Origin asset")
        seed = _PALETTES_BY_ID[self.palette_id]
        expected_colors = tuple(reversed(seed.colors)) if self.reverse else seed.colors
        if (
            self.origin_source_name != seed.origin_source_name
            or self.origin_asset_kind != seed.origin_asset_kind
            or self.kind != seed.kind
            or self.source_version != seed.source_version
            or self.colors != expected_colors
        ):
            raise ValueError("palette metadata or sRGB sequence differs from the frozen asset")
        rgb_payload: JsonValue = {
            "palette_id": self.palette_id,
            "colors": [color.value.upper() for color in self.colors],
            "reverse": self.reverse,
        }
        if canonical_hash(rgb_payload) != self.resolved_rgb_hash:
            raise ValueError("resolved_rgb_hash does not match the frozen sRGB sequence")
        return self


class _PaletteSeed(StrictModel):
    palette_id: PaletteId
    origin_source_name: str
    origin_asset_kind: Literal["color_list", "palette"] = "palette"
    kind: PaletteKind
    colors: tuple[ColorValue, ...]
    source_version: Literal["Origin2024 SR1 10.10.178"] = "Origin2024 SR1 10.10.178"


def _colors(*values: str) -> tuple[ColorValue, ...]:
    return tuple(ColorValue(value=value) for value in values)


# Qualitative lists are the complete Origin Color Theme payload. Continuous
# palettes are nine deterministic samples (indices 0,32,...,224,255) from the
# 256-entry RIFF PAL shipped by the pinned Origin build.
_PALETTE_SEEDS: tuple[_PaletteSeed, ...] = (
    _PaletteSeed(
        palette_id="ColorBlindSafe8",
        origin_source_name="ColorBlindSafe8.oth",
        origin_asset_kind="color_list",
        kind="qualitative",
        colors=_colors(
            "#000000",
            "#E69F00",
            "#56B4E9",
            "#009E73",
            "#F0E442",
            "#0072B2",
            "#D55E00",
            "#CC79A7",
        ),
    ),
    _PaletteSeed(
        palette_id="ColorBlindSafe15",
        origin_source_name="ColorBlindSafe15.oth",
        origin_asset_kind="color_list",
        kind="qualitative",
        colors=_colors(
            "#000000",
            "#004949",
            "#009292",
            "#FF6DB6",
            "#FFB6DB",
            "#490092",
            "#006DDB",
            "#B66DFF",
            "#6DB6FF",
            "#B6DBFF",
            "#920000",
            "#924900",
            "#D16D00",
            "#24FF24",
            "#FFFF6D",
        ),
    ),
    _PaletteSeed(
        palette_id="BlueOrange",
        origin_source_name="BlueOrange.PAL",
        kind="diverging",
        colors=_colors(
            "#01756D",
            "#019A8F",
            "#02BFB1",
            "#81DCCC",
            "#FEF8E6",
            "#FEBA78",
            "#FC7D0D",
            "#CB6206",
            "#9C4900",
        ),
    ),
    _PaletteSeed(
        palette_id="OrangeNavy",
        origin_source_name="OrangeNavy.PAL",
        kind="diverging",
        colors=_colors(
            "#9A221C",
            "#CF2E25",
            "#F3764C",
            "#FDC17B",
            "#EEE9C5",
            "#C1DEEC",
            "#7CAAD0",
            "#416EAA",
            "#2C4B75",
        ),
    ),
    _PaletteSeed(
        palette_id="RedPurple",
        origin_source_name="RedPurple.PAL",
        kind="diverging",
        colors=_colors(
            "#43001C",
            "#AC1045",
            "#E45548",
            "#FA9E59",
            "#FDFEBE",
            "#94D1B2",
            "#4AA3B1",
            "#545BA7",
            "#292247",
        ),
    ),
    _PaletteSeed(
        palette_id="Viridis",
        origin_source_name="Viridis.PAL",
        kind="sequential",
        colors=_colors(
            "#FDE724",
            "#AADB32",
            "#5BC862",
            "#27AD80",
            "#208F8C",
            "#2C718E",
            "#3B518A",
            "#472B7A",
            "#440154",
        ),
    ),
    _PaletteSeed(
        palette_id="Plasma",
        origin_source_name="Plasma.PAL",
        kind="sequential",
        colors=_colors(
            "#EFF821",
            "#FDC328",
            "#F79341",
            "#E56B5C",
            "#CA4678",
            "#A82296",
            "#7C02A7",
            "#4A02A0",
            "#0C0786",
        ),
    ),
    _PaletteSeed(
        palette_id="Inferno",
        origin_source_name="Inferno.PAL",
        kind="sequential",
        colors=_colors(
            "#FCFEA4",
            "#F8C931",
            "#F98C09",
            "#E35832",
            "#BA3655",
            "#88216A",
            "#550F6D",
            "#1F0C47",
            "#000003",
        ),
    ),
    _PaletteSeed(
        palette_id="Magma",
        origin_source_name="Magma.PAL",
        kind="sequential",
        colors=_colors(
            "#FBFCBF",
            "#FEC286",
            "#FB8660",
            "#E55063",
            "#B53679",
            "#812581",
            "#4F117B",
            "#1B1044",
            "#000003",
        ),
    ),
    _PaletteSeed(
        palette_id="GreyBlue",
        origin_source_name="GreyBlue.PAL",
        kind="sequential",
        colors=_colors(
            "#ECE7DF",
            "#DED5C7",
            "#D0C3B1",
            "#ADB4B8",
            "#89A5BF",
            "#668CAE",
            "#43739C",
            "#375F81",
            "#2C4C67",
        ),
    ),
    _PaletteSeed(
        palette_id="YellowBlue",
        origin_source_name="YellowBlue.PAL",
        kind="sequential",
        colors=_colors(
            "#F4EC7D",
            "#B8DC97",
            "#51CCA0",
            "#00BBA6",
            "#00A4B5",
            "#007EB2",
            "#1255A9",
            "#203494",
            "#18276F",
        ),
    ),
    _PaletteSeed(
        palette_id="YellowGreen",
        origin_source_name="YellowGreen.PAL",
        kind="sequential",
        colors=_colors(
            "#EEEE99",
            "#EDE570",
            "#E0DA66",
            "#C1CB87",
            "#8EA47E",
            "#5B796B",
            "#385156",
            "#1E3745",
            "#0C2538",
        ),
    ),
    _PaletteSeed(
        palette_id="YellowPurple",
        origin_source_name="YellowPurple.PAL",
        kind="diverging",
        colors=_colors(
            "#F5F0AF",
            "#E8DD92",
            "#DCCB77",
            "#D79E7C",
            "#D17281",
            "#AB4B78",
            "#852570",
            "#771B71",
            "#691173",
        ),
    ),
    _PaletteSeed(
        palette_id="Fire",
        origin_source_name="Fire.pal",
        kind="special",
        colors=_colors(
            "#300000",
            "#9A0000",
            "#FF0200",
            "#FF4300",
            "#FF8200",
            "#FFC200",
            "#FFFF04",
            "#FFFF85",
            "#FFFFFF",
        ),
    ),
    _PaletteSeed(
        palette_id="Rainbow_Modified",
        origin_source_name="Rainbow_Modified.PAL",
        kind="special",
        colors=_colors(
            "#641216",
            "#D85105",
            "#E39107",
            "#CCC741",
            "#D7ECD0",
            "#81CCAF",
            "#4BA3B1",
            "#3571A7",
            "#3F356F",
        ),
    ),
    _PaletteSeed(
        palette_id="GrayScale",
        origin_source_name="GrayScale.PAL",
        kind="grayscale",
        colors=_colors(
            "#000000",
            "#202020",
            "#404040",
            "#606060",
            "#808080",
            "#A0A0A0",
            "#C0C0C0",
            "#E0E0E0",
            "#FFFFFF",
        ),
    ),
)

PALETTE_IDS: tuple[PaletteId, ...] = tuple(seed.palette_id for seed in _PALETTE_SEEDS)
_PALETTES_BY_ID = {seed.palette_id: seed for seed in _PALETTE_SEEDS}

SYMBOL_MAPPINGS: dict[SymbolShape, tuple[int, str]] = {
    "square": (1, "s"),
    "circle": (2, "o"),
    "triangle_up": (3, "^"),
    "triangle_down": (4, "v"),
    "diamond": (5, "D"),
    "plus": (6, "+"),
    "cross": (7, "x"),
    "triangle_left": (15, "<"),
    "triangle_right": (16, ">"),
    "hexagon": (17, "h"),
    "star": (18, "*"),
    "pentagon": (19, "p"),
}

# originpro's symbol_interior property is the LabTalk interior code plus one.
ORIGIN_INTERIOR_CODES: dict[SymbolInterior, int] = {"solid": 1, "open": 2, "hollow": 4}


def resolve_palette(palette_id: PaletteId, *, reverse: bool = False) -> ResolvedPalette:
    seed = _PALETTES_BY_ID[palette_id]
    payload = seed.model_dump(mode="json")
    colors = tuple(reversed(seed.colors)) if reverse else seed.colors
    return ResolvedPalette.model_validate(
        {
            **payload,
            "colors": tuple(colors),
            "reverse": reverse,
            "source_hash": _ORIGIN_SOURCE_HASHES[palette_id],
            "resolved_rgb_hash": canonical_hash(
                {
                    "palette_id": palette_id,
                    "colors": [color.value.upper() for color in colors],
                    "reverse": reverse,
                }
            ),
        }
    )


def origin_symbol_code(shape: SymbolShape) -> int:
    return SYMBOL_MAPPINGS[shape][0]


def matplotlib_marker(shape: SymbolShape) -> str:
    return SYMBOL_MAPPINGS[shape][1]


def origin_interior_code(interior: SymbolInterior) -> int:
    return ORIGIN_INTERIOR_CODES[interior]
