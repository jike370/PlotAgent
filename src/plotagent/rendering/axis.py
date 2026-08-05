"""Versioned deterministic axis-domain, autoscale, and tick resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from plotagent.contracts.plots import AxisSpec, SafeRichText, SafeTextNode, ScaleSpec
from plotagent.contracts.rendering import ResolvedAxis, ResolvedTick
from plotagent.rendering.data import Scalar, is_finite_number

AXIS_ALGORITHM_VERSION = "axis.nice.v1"


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _nice_step(span: float, target_intervals: int = 5) -> float:
    raw = span / target_intervals
    exponent = math.floor(math.log10(raw)) if raw > 0 else 0
    fraction = raw / (10**exponent)
    if fraction <= 1:
        nice = 1.0
    elif fraction <= 2:
        nice = 2.0
    elif fraction <= 2.5:
        nice = 2.5
    elif fraction <= 5:
        nice = 5.0
    else:
        nice = 10.0
    return float(nice * (10**exponent))


def _precision(step: float) -> int:
    if step == 0:
        return 0
    return max(
        0,
        min(
            12,
            -math.floor(math.log10(abs(step)))
            + (1 if step / 10 ** math.floor(math.log10(abs(step))) == 2.5 else 0),
        ),
    )


def _number_label(value: float, precision: int) -> str:
    if abs(value) < 0.5 * (10 ** (-precision)):
        value = 0.0
    if abs(value) >= 1e6 or (0 < abs(value) < 1e-4):
        return f"{value:.4g}"
    return f"{value:.{precision}f}"


def _linear_ticks(minimum: float, maximum: float) -> tuple[tuple[ResolvedTick, ...], int]:
    step = _nice_step(maximum - minimum)
    precision = _precision(step)
    start = math.ceil((minimum - step * 1e-12) / step) * step
    stop = math.floor((maximum + step * 1e-12) / step) * step
    count = max(0, int(round((stop - start) / step)) + 1)
    values = tuple(start + index * step for index in range(min(count, 100)))
    return (
        tuple(
            ResolvedTick(value=value, label=_text(_number_label(value, precision)))
            for value in values
        ),
        precision,
    )


def _log_ticks(minimum: float, maximum: float) -> tuple[ResolvedTick, ...]:
    start = math.ceil(math.log10(minimum) - 1e-12)
    stop = math.floor(math.log10(maximum) + 1e-12)
    ticks: list[ResolvedTick] = []
    for exponent in range(start, stop + 1):
        ticks.append(
            ResolvedTick(
                value=10.0**exponent,
                label=SafeRichText(
                    nodes=(
                        SafeTextNode(kind="plain", text="10"),
                        SafeTextNode(kind="sup", text=str(exponent)),
                    )
                ),
            )
        )
    if len(ticks) < 2:
        return (
            ResolvedTick(value=minimum, label=_text(f"{minimum:.4g}")),
            ResolvedTick(value=maximum, label=_text(f"{maximum:.4g}")),
        )
    return tuple(ticks)


_DATETIME_STEPS = (
    1.0,
    5.0,
    15.0,
    60.0,
    300.0,
    900.0,
    3600.0,
    21600.0,
    86400.0,
    604800.0,
    2_592_000.0,
    7_776_000.0,
    31_536_000.0,
)


def _datetime_value(value: Scalar) -> float:
    if is_finite_number(value):
        return float(value)
    if not isinstance(value, str):
        raise ValueError("datetime axes require ISO-8601 strings or epoch seconds")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).timestamp()


def _datetime_ticks(minimum: float, maximum: float) -> tuple[ResolvedTick, ...]:
    span = maximum - minimum
    desired = span / 5
    step = next((item for item in _DATETIME_STEPS if item >= desired), _DATETIME_STEPS[-1])
    start = math.ceil(minimum / step) * step
    values: list[float] = []
    value = start
    while value <= maximum + step * 1e-12 and len(values) < 100:
        values.append(value)
        value += step
    date_format = "%H:%M:%S" if step < 86400 else "%Y-%m-%d"
    return tuple(
        ResolvedTick(
            value=value,
            label=_text(datetime.fromtimestamp(value, tz=UTC).strftime(date_format)),
        )
        for value in values
    )


@dataclass(frozen=True, slots=True)
class AxisResolution:
    axis: ResolvedAxis
    categories: tuple[str, ...] = ()

    def convert(self, value: Scalar) -> float:
        if self.axis.scale == "categorical":
            label = str(value)
            try:
                return float(self.categories.index(label))
            except ValueError as error:
                raise ValueError(f"category {label!r} was not in the resolved domain") from error
        if self.axis.scale == "datetime":
            return _datetime_value(value)
        if not is_finite_number(value):
            raise ValueError("continuous axes require finite numeric values")
        return float(value)


def resolve_axis(
    axis_spec: AxisSpec,
    scale_spec: ScaleSpec,
    values: tuple[Scalar, ...],
    *,
    panel_id: str,
    resolved_axis_id: str,
    include_zero: bool = False,
) -> AxisResolution:
    """Resolve a complete axis from full, unsimplified geometry values."""

    if scale_spec.kind == "categorical":
        categories = tuple(dict.fromkeys(str(value) for value in values if value is not None))
        if not categories:
            categories = ("",)
        minimum = -0.5
        maximum = len(categories) - 0.5
        ticks = tuple(
            ResolvedTick(value=float(index), label=_text(label))
            for index, label in enumerate(categories)
        )
        if scale_spec.axis_range.minimum is not None or scale_spec.axis_range.maximum is not None:
            raise ValueError("categorical axes do not accept numeric fixed bounds")
        return AxisResolution(
            axis=ResolvedAxis(
                axis_id=resolved_axis_id,
                panel_id=panel_id,
                orientation=axis_spec.orientation,
                position=axis_spec.position,
                scale="categorical",
                minimum=minimum,
                maximum=maximum,
                reverse=scale_spec.axis_range.reverse,
                ticks=ticks,
                precision=0,
                label=axis_spec.label,
            ),
            categories=categories,
        )

    if scale_spec.kind == "datetime":
        numeric = tuple(_datetime_value(value) for value in values if value is not None)
    else:
        numeric = tuple(float(value) for value in values if is_finite_number(value))
    if not numeric:
        raise ValueError(f"axis {axis_spec.axis_id} has no finite range candidates")
    raw_minimum = min(numeric)
    raw_maximum = max(numeric)
    if include_zero:
        raw_minimum = min(raw_minimum, 0.0)
        raw_maximum = max(raw_maximum, 0.0)

    if scale_spec.kind == "log10":
        if raw_minimum <= 0:
            raise ValueError("AXIS_LOG_NONPOSITIVE: visible Log10 geometry must be positive")
        low = math.log10(raw_minimum)
        high = math.log10(raw_maximum)
        if low == high:
            padded_low, padded_high = low - 0.5, high + 0.5
        else:
            padding = (high - low) * 0.05
            padded_low, padded_high = low - padding, high + padding
        auto_minimum, auto_maximum = 10**padded_low, 10**padded_high
    else:
        if raw_minimum == raw_maximum:
            delta = 0.5 if raw_minimum == 0 else max(abs(raw_minimum) * 0.05, 1e-12)
            auto_minimum, auto_maximum = raw_minimum - delta, raw_maximum + delta
        else:
            padding = (raw_maximum - raw_minimum) * 0.05
            auto_minimum, auto_maximum = raw_minimum - padding, raw_maximum + padding

    fixed_minimum = scale_spec.axis_range.minimum
    fixed_maximum = scale_spec.axis_range.maximum
    minimum = auto_minimum if fixed_minimum is None else float(fixed_minimum)
    maximum = auto_maximum if fixed_maximum is None else float(fixed_maximum)
    if minimum >= maximum:
        raise ValueError("resolved axis minimum must be lower than maximum")
    if scale_spec.kind == "log10" and minimum <= 0:
        raise ValueError("AXIS_LOG_NONPOSITIVE: fixed Log10 bounds must be positive")

    if scale_spec.kind == "log10":
        ticks = _log_ticks(minimum, maximum)
        precision = 0
    elif scale_spec.kind == "datetime":
        ticks = _datetime_ticks(minimum, maximum)
        precision = 0
    else:
        ticks, precision = _linear_ticks(minimum, maximum)
    return AxisResolution(
        axis=ResolvedAxis(
            axis_id=resolved_axis_id,
            panel_id=panel_id,
            orientation=axis_spec.orientation,
            position=axis_spec.position,
            scale=scale_spec.kind,
            minimum=minimum,
            maximum=maximum,
            reverse=scale_spec.axis_range.reverse,
            ticks=ticks,
            precision=precision,
            label=axis_spec.label,
        )
    )
