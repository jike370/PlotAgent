"""Case-sensitive unit registry for import evidence and workflow tools."""

from __future__ import annotations

from dataclasses import dataclass

from plotagent.contracts.datasets import UnitSpec


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    symbol: str
    dimensionality: str
    scale_to_base: float
    offset_to_base: float = 0.0


_DEFINITIONS = (
    UnitDefinition("s", "time", 1.0),
    UnitDefinition("ms", "time", 1e-3),
    UnitDefinition("µs", "time", 1e-6),
    UnitDefinition("ns", "time", 1e-9),
    UnitDefinition("min", "time", 60.0),
    UnitDefinition("h", "time", 3600.0),
    UnitDefinition("V", "voltage", 1.0),
    UnitDefinition("mV", "voltage", 1e-3),
    UnitDefinition("µV", "voltage", 1e-6),
    UnitDefinition("kV", "voltage", 1e3),
    UnitDefinition("Hz", "frequency", 1.0),
    UnitDefinition("kHz", "frequency", 1e3),
    UnitDefinition("MHz", "frequency", 1e6),
    UnitDefinition("Ω", "resistance", 1.0),
    UnitDefinition("mΩ", "resistance", 1e-3),
    UnitDefinition("kΩ", "resistance", 1e3),
    UnitDefinition("MΩ", "resistance", 1e6),
    UnitDefinition("m", "length", 1.0),
    UnitDefinition("cm", "length", 1e-2),
    UnitDefinition("mm", "length", 1e-3),
    UnitDefinition("µm", "length", 1e-6),
    UnitDefinition("nm", "length", 1e-9),
    UnitDefinition("g", "mass", 1.0),
    UnitDefinition("kg", "mass", 1e3),
    UnitDefinition("mg", "mass", 1e-3),
    UnitDefinition("µg", "mass", 1e-6),
    UnitDefinition("Pa", "pressure", 1.0),
    UnitDefinition("kPa", "pressure", 1e3),
    UnitDefinition("MPa", "pressure", 1e6),
    UnitDefinition("K", "temperature", 1.0),
    UnitDefinition("°C", "temperature", 1.0, 273.15),
    UnitDefinition("°F", "temperature", 5.0 / 9.0, 255.3722222222222),
)

_BY_SYMBOL = {item.symbol: item for item in _DEFINITIONS}
_ALIASES = _BY_SYMBOL | {
    "us": _BY_SYMBOL["µs"],
    "μs": _BY_SYMBOL["µs"],
    "uV": _BY_SYMBOL["µV"],
    "μV": _BY_SYMBOL["µV"],
    "ohm": _BY_SYMBOL["Ω"],
    "mohm": _BY_SYMBOL["mΩ"],
    "kohm": _BY_SYMBOL["kΩ"],
    "Mohm": _BY_SYMBOL["MΩ"],
    "um": _BY_SYMBOL["µm"],
    "μm": _BY_SYMBOL["µm"],
    "ug": _BY_SYMBOL["µg"],
    "μg": _BY_SYMBOL["µg"],
}

# Contract canonical_unit is a stable identifier token, while source_text and
# UnitDefinition.symbol preserve the scientific display spelling.
_CANONICAL_TOKENS = {
    "µs": "us",
    "µV": "uV",
    "Ω": "ohm",
    "mΩ": "mohm",
    "kΩ": "kohm",
    "MΩ": "Mohm",
    "µm": "um",
    "µg": "ug",
    "°C": "degC",
    "°F": "degF",
}

# Single-letter suffixes are ambiguous in ordinary field names. Explicit
# bracket/parenthesis declarations may still use them.
SAFE_HEADER_SUFFIX_UNITS = frozenset(
    alias for alias in _ALIASES if alias not in {"h", "m", "g", "K"}
)


def resolve_unit(text: str) -> UnitDefinition | None:
    """Resolve an exact spelling; SI prefix case is scientifically significant."""

    return _ALIASES.get(text.strip())


def unit_spec(source_text: str) -> UnitSpec:
    definition = resolve_unit(source_text)
    if definition is None:
        return UnitSpec(
            source_text=source_text,
            dimensionality="opaque",
            kind="opaque",
            registry_version="units.v1",
        )
    return UnitSpec(
        source_text=source_text,
        canonical_unit=_CANONICAL_TOKENS.get(definition.symbol, definition.symbol),
        dimensionality=definition.dimensionality,
        kind="recognized",
        registry_version="units.v1",
    )


def convert_value(value: float, source_unit: str, target_unit: str) -> float:
    source = resolve_unit(source_unit)
    target = resolve_unit(target_unit)
    if source is None or target is None:
        raise ValueError("unit is not registered")
    if source.dimensionality != target.dimensionality:
        raise ValueError("units have incompatible dimensionality")
    base = value * source.scale_to_base + source.offset_to_base
    return (base - target.offset_to_base) / target.scale_to_base
