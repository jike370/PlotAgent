"""Normalizers for values returned by Origin's native automation API."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta


def axis_scale_matches(
    observed: object,
    expected: str,
) -> bool:
    """Compare a scale with Origin's native readback representation.

    Origin accepts symbolic strings when assigning ``axis.scale`` but returns
    LabTalk code 1 (linear) or 2 (base-10 logarithmic) after project reopen.
    """

    native_codes = {"linear": 1, "log10": 2}
    return observed == expected or observed == native_codes.get(expected)


def datetime_values_match(
    observed: Sequence[datetime],
    expected: Sequence[datetime],
    *,
    tolerance: timedelta = timedelta(microseconds=50),
) -> bool:
    """Compare timestamps after Origin's Julian-double round trip.

    Origin stores dates as floating-point Julian day values.  Around current
    dates that representation can differ from the source by roughly 10–15
    microseconds after a fresh reopen.  The tolerance is deliberately far
    below the smallest public K19 input resolution (one millisecond), while
    still accepting that native serialization noise.
    """

    return len(observed) == len(expected) and all(
        abs(actual - wanted) <= tolerance
        for actual, wanted in zip(observed, expected, strict=True)
    )
