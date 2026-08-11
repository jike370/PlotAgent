from __future__ import annotations

from datetime import datetime, timedelta

from plotagent.engine.backends.origin.readback import (
    axis_scale_matches,
    datetime_values_match,
)


def test_axis_scale_readback_accepts_origin_native_codes_and_symbolic_doubles() -> None:
    assert axis_scale_matches(1, "linear")
    assert axis_scale_matches(2, "log10")
    assert axis_scale_matches("linear", "linear")
    assert axis_scale_matches("log10", "log10")
    assert not axis_scale_matches(2, "linear")
    assert not axis_scale_matches(1, "log10")


def test_datetime_readback_accepts_only_native_julian_rounding_noise() -> None:
    expected = (datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 9))
    assert datetime_values_match(
        (expected[0] + timedelta(microseconds=14), expected[1]),
        expected,
    )
    assert not datetime_values_match(
        (expected[0] + timedelta(milliseconds=1), expected[1]),
        expected,
    )
    assert not datetime_values_match(expected[:1], expected)
