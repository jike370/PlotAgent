"""Pure deterministic implementations of the nine frozen v1 plot calculations."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.stats import t as student_t  # type: ignore[import-untyped]

from plotagent.contracts.base import (
    ContentTableRef,
    NonFiniteCounts,
    PlotCalculationSpecRef,
    RowExclusion,
    WarningRecord,
)
from plotagent.contracts.calculations import (
    CalculationResultBase,
    CalculationTable,
    ConfusionCountResult,
    ConfusionCountSpec,
    ECDFResult,
    ECDFSpec,
    HistogramBinningResult,
    HistogramBinningSpec,
    MatrixProjectionResult,
    MatrixProjectionSpec,
    PercentStackResult,
    PercentStackSpec,
    PlotCalculationResult,
    PlotCalculationSpec,
    SummaryErrorResult,
    SummaryErrorSpec,
    TukeyBoxResult,
    TukeyBoxSpec,
    ViolinKDEResult,
    ViolinKDESpec,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.plot_calculations.errors import PlotCalculationError
from plotagent.plot_calculations.inputs import PlotCalculationInput
from plotagent.plot_calculations.kernels import histogram_geometry, scott_kde_geometry

ALGORITHM_VERSION = "1.0.0"
_ROW_ID_PATTERN = re.compile(r"^row:[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_CategoryScalar = str | bool | int | float
_Scalar = _CategoryScalar | None
_CategoryIdentity = tuple[str, str]
_NonFiniteReason = Literal["missing", "nan", "positive_inf", "negative_inf"]


@dataclass(frozen=True, slots=True)
class _FilteredRows:
    included_indices: tuple[int, ...]
    included_row_ids: tuple[str, ...]
    exclusions: tuple[RowExclusion, ...]
    nonfinite_counts: NonFiniteCounts


@dataclass(frozen=True, slots=True)
class _Group:
    values: tuple[_Scalar, ...]
    indices: tuple[int, ...]


def _failure(code: str, message: str, **details: object) -> PlotCalculationError:
    return PlotCalculationError(code, message, details=details)


def _python_scalar(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    return value


def _nonfinite_reason(value: object) -> _NonFiniteReason | None:
    value = _python_scalar(value)
    if value is None:
        return "missing"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "positive_inf" if value > 0 else "negative_inf"
    return None


def _number(value: object, field_id: str) -> float:
    value = _python_scalar(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _failure(
            "PLOTSPEC_CALCULATION_SHAPE_INVALID",
            f"field {field_id} must contain numeric values",
            field_id=field_id,
        )
    number = float(value)
    if not math.isfinite(number):
        raise _failure(
            "PLOTSPEC_CALCULATION_NONFINITE",
            f"field {field_id} contains a non-finite value after masking",
            field_id=field_id,
        )
    return number


def _category(value: object, field_id: str) -> _CategoryScalar:
    value = _python_scalar(value)
    if not isinstance(value, (str, bool, int, float)):
        raise _failure(
            "PLOTSPEC_CALCULATION_SHAPE_INVALID",
            f"field {field_id} must contain scalar category values",
            field_id=field_id,
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise _failure(
            "PLOTSPEC_CALCULATION_NONFINITE",
            f"field {field_id} contains a non-finite category after masking",
            field_id=field_id,
        )
    return value


def _category_identity(value: _CategoryScalar) -> _CategoryIdentity:
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, bool):
        return ("bool", "true" if value else "false")
    if isinstance(value, int):
        return ("int", str(value))
    return ("float", value.hex())


def _category_label(value: _CategoryScalar) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return format(value, ".17g")


def _hashable_scalar(value: object) -> JsonValue:
    value = _python_scalar(value)
    reason = _nonfinite_reason(value)
    if reason is not None:
        return {"nonfinite": reason}
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    raise _failure(
        "PLOTSPEC_CALCULATION_SHAPE_INVALID",
        "calculation input contains an unsupported scalar type",
        value_type=type(value).__name__,
    )


def _validate_input_shape(data: PlotCalculationInput) -> None:
    row_count = len(data.row_ids)
    if len(set(data.row_ids)) != row_count:
        raise _failure(
            "PLOTSPEC_CALCULATION_SHAPE_INVALID",
            "row ids must be unique",
        )
    invalid_row_ids = [
        row_id for row_id in data.row_ids if _ROW_ID_PATTERN.fullmatch(row_id) is None
    ]
    if invalid_row_ids:
        raise _failure(
            "PLOTSPEC_CALCULATION_SHAPE_INVALID",
            "row ids do not satisfy the frozen RowId contract",
            row_ids=tuple(invalid_row_ids),
        )
    for field_id, values in data.columns.items():
        if len(values) != row_count:
            raise _failure(
                "PLOTSPEC_CALCULATION_SHAPE_INVALID",
                f"column {field_id} is not row-aligned",
                field_id=field_id,
                expected=row_count,
                actual=len(values),
            )
        for value in values:
            _hashable_scalar(value)
    if data.matrix is not None:
        if len(data.matrix) != row_count:
            raise _failure(
                "PLOTSPEC_CALCULATION_SHAPE_INVALID",
                "matrix row count must match row ids",
                expected=row_count,
                actual=len(data.matrix),
            )
        widths = {len(row) for row in data.matrix}
        if len(widths) > 1:
            raise _failure(
                "PLOTSPEC_CALCULATION_SHAPE_INVALID",
                "regular matrix rows must have equal width",
            )
        for row in data.matrix:
            for value in row:
                _hashable_scalar(value)


def _input_hash(data: PlotCalculationInput) -> str:
    payload: JsonValue = {
        "row_ids": list(data.row_ids),
        "columns": {
            field_id: [_hashable_scalar(value) for value in values]
            for field_id, values in data.columns.items()
        },
        "matrix": (
            None
            if data.matrix is None
            else [[_hashable_scalar(value) for value in row] for row in data.matrix]
        ),
    }
    return canonical_hash(payload)


def _required_columns(
    data: PlotCalculationInput,
    field_ids: Sequence[str],
    *,
    columns: Mapping[str, Sequence[object]] | None = None,
) -> Mapping[str, Sequence[object]]:
    source = data.columns if columns is None else columns
    for field_id in field_ids:
        if field_id not in source:
            raise _failure(
                "PLOTSPEC_CALCULATION_SHAPE_INVALID",
                f"required field {field_id} is absent",
                field_id=field_id,
            )
        if len(source[field_id]) != len(data.row_ids):
            raise _failure(
                "PLOTSPEC_CALCULATION_SHAPE_INVALID",
                f"required field {field_id} is not row-aligned",
                field_id=field_id,
            )
    return source


def _filter_rows(
    spec: PlotCalculationSpec,
    data: PlotCalculationInput,
    required_fields: Sequence[str],
    numeric_fields: Sequence[str],
    *,
    columns: Mapping[str, Sequence[object]] | None = None,
) -> _FilteredRows:
    fields = tuple(dict.fromkeys((*required_fields, *spec.log10_fields)))
    numeric = set(numeric_fields).union(spec.log10_fields)
    source = _required_columns(data, fields, columns=columns)
    counts = {"missing": 0, "nan": 0, "positive_inf": 0, "negative_inf": 0}
    included_indices: list[int] = []
    exclusions: list[RowExclusion] = []

    for index, row_id in enumerate(data.row_ids):
        primary: tuple[str, _NonFiniteReason] | None = None
        for field_id in fields:
            value = source[field_id][index]
            reason = _nonfinite_reason(value)
            if reason is not None:
                counts[reason] += 1
                if primary is None:
                    primary = (field_id, reason)
                continue
            if field_id in numeric:
                number = _number(value, field_id)
                if field_id in spec.log10_fields and number <= 0:
                    raise _failure(
                        "PLOTSPEC_CALCULATION_LOG10_NONPOSITIVE",
                        f"Log10 field {field_id} contains a non-positive value",
                        field_id=field_id,
                        row_id=row_id,
                        value=number,
                    )
            else:
                _category(value, field_id)
        if primary is None:
            included_indices.append(index)
        else:
            field_id, reason = primary
            exclusions.append(RowExclusion(row_id=row_id, field_id=field_id, reason=reason))

    nonfinite_counts = NonFiniteCounts(**counts)
    if exclusions and spec.missing_policy == "fail":
        raise _failure(
            "PLOTSPEC_CALCULATION_NONFINITE",
            "missing_policy=fail rejects missing or non-finite calculation input",
            excluded_row_ids=tuple(exclusion.row_id for exclusion in exclusions),
            nonfinite_counts=nonfinite_counts.model_dump(mode="json"),
        )
    if not included_indices:
        raise _failure(
            "PLOTSPEC_CALCULATION_INSUFFICIENT_DATA",
            "no valid rows remain for the fixed calculation",
        )
    included = tuple(included_indices)
    return _FilteredRows(
        included_indices=included,
        included_row_ids=tuple(data.row_ids[index] for index in included),
        exclusions=tuple(exclusions),
        nonfinite_counts=nonfinite_counts,
    )


def _groups(
    data: PlotCalculationInput,
    indices: Sequence[int],
    group_fields: Sequence[str],
    *,
    columns: Mapping[str, Sequence[object]] | None = None,
) -> tuple[_Group, ...]:
    if not group_fields:
        return (_Group(values=(), indices=tuple(indices)),)
    source = data.columns if columns is None else columns
    grouped: dict[tuple[_CategoryIdentity, ...], tuple[tuple[_Scalar, ...], list[int]]] = {}
    for index in indices:
        values = tuple(_category(source[field][index], field) for field in group_fields)
        identity = tuple(_category_identity(value) for value in values)
        if identity not in grouped:
            grouped[identity] = (values, [])
        grouped[identity][1].append(index)
    return tuple(
        _Group(values=values, indices=tuple(group_indices))
        for values, group_indices in grouped.values()
    )


def _table(field_ids: Sequence[str], rows: Sequence[Sequence[object]]) -> CalculationTable:
    return CalculationTable.model_validate(
        {
            "field_ids": tuple(field_ids),
            "rows": tuple(tuple(_python_scalar(value) for value in row) for row in rows),
        }
    )


def _base_payload(
    spec: PlotCalculationSpec,
    data: PlotCalculationInput,
    filtered: _FilteredRows,
    table: CalculationTable,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
    warnings: Sequence[WarningRecord] = (),
) -> dict[str, object]:
    output_hash = canonical_hash(table)
    spec_hash = canonical_hash(spec)
    return {
        "schema_version": spec.schema_version,
        "calculation_id": spec.calculation_id,
        "result_version": result_version,
        "spec_ref": PlotCalculationSpecRef(
            calculation_id=spec.calculation_id,
            calculation_version=spec.calculation_version,
            calculation_kind=spec.kind,
            content_hash=spec_hash,
        ),
        "prepared_dataset_ref": spec.prepared_dataset_ref,
        "algorithm_version": spec.algorithm_version,
        "missing_policy": spec.missing_policy,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "output_data_ref": ContentTableRef(
            object_hash=output_hash,
            row_count=len(table.rows),
            field_ids=table.field_ids,
        ),
        "output_table": table,
        "total_row_count": len(data.row_ids),
        "included_row_count": len(filtered.included_indices),
        "excluded_row_count": len(filtered.exclusions),
        "included_row_ids": filtered.included_row_ids,
        "exclusions": filtered.exclusions,
        "nonfinite_counts": filtered.nonfinite_counts,
        "fixed_seed": spec.fixed_seed,
        "warnings": tuple(warnings),
        "producer_build_hash": producer_build_hash,
    }


def _result[ResultT: CalculationResultBase](
    result_type: type[ResultT],
    base: Mapping[str, object],
    **specific: object,
) -> ResultT:
    return result_type.model_validate({**base, **specific})


def _histogram(
    spec: HistogramBinningSpec,
    data: PlotCalculationInput,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
) -> HistogramBinningResult:
    filtered = _filter_rows(spec, data, (spec.value_field,), (spec.value_field,))
    values = np.asarray(
        [
            _number(data.columns[spec.value_field][i], spec.value_field)
            for i in filtered.included_indices
        ],
        dtype=np.float64,
    )
    geometry = histogram_geometry(
        tuple(float(value) for value in values),
        normalization=spec.normalization,
    )
    bin_count = len(geometry.center)
    rows = []
    for index in range(bin_count):
        rows.append(
            (
                index,
                geometry.left[index],
                geometry.right[index],
                geometry.center[index],
                geometry.count[index],
                geometry.height[index],
            )
        )
    table = _table(
        (
            "field:plotcalc.bin_index",
            "field:plotcalc.bin_left",
            "field:plotcalc.bin_right",
            "field:plotcalc.bin_center",
            "field:plotcalc.count",
            "field:plotcalc.value",
        ),
        rows,
    )
    base = _base_payload(
        spec,
        data,
        filtered,
        table,
        input_hash=input_hash,
        producer_build_hash=producer_build_hash,
        result_version=result_version,
    )
    return _result(
        HistogramBinningResult,
        base,
        kind=spec.kind,
        algorithm_id=spec.algorithm_id,
        bin_count=bin_count,
        normalization=spec.normalization,
        binning_rule=geometry.rule,
    )


def _tukey_box(
    spec: TukeyBoxSpec,
    data: PlotCalculationInput,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
) -> TukeyBoxResult:
    required = (
        (spec.value_field,) if spec.group_field is None else (spec.value_field, spec.group_field)
    )
    filtered = _filter_rows(spec, data, required, (spec.value_field,))
    group_fields = () if spec.group_field is None else (spec.group_field,)
    groups = _groups(data, filtered.included_indices, group_fields)
    rows: list[tuple[object, ...]] = []
    for group_index, group in enumerate(groups):
        values = np.asarray(
            [_number(data.columns[spec.value_field][i], spec.value_field) for i in group.indices],
            dtype=np.float64,
        )
        q1, median, q3 = (float(value) for value in np.quantile(values, (0.25, 0.5, 0.75)))
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        inliers = values[(values >= lower_fence) & (values <= upper_fence)]
        whisker_low = float(np.min(inliers))
        whisker_high = float(np.max(inliers))
        group_value = group.values[0] if group.values else None
        rows.append(
            (
                "summary",
                group_index,
                group_value,
                len(group.indices),
                q1,
                median,
                q3,
                iqr,
                lower_fence,
                upper_fence,
                whisker_low,
                whisker_high,
                None,
                None,
            )
        )
        for local_index, value in enumerate(values):
            if value < lower_fence or value > upper_fence:
                source_index = group.indices[local_index]
                rows.append(
                    (
                        "outlier",
                        group_index,
                        group_value,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        float(value),
                        data.row_ids[source_index],
                    )
                )
    table = _table(
        (
            "field:plotcalc.record_kind",
            "field:plotcalc.group_index",
            "field:plotcalc.group",
            "field:plotcalc.n",
            "field:plotcalc.q1",
            "field:plotcalc.median",
            "field:plotcalc.q3",
            "field:plotcalc.iqr",
            "field:plotcalc.lower_fence",
            "field:plotcalc.upper_fence",
            "field:plotcalc.whisker_low",
            "field:plotcalc.whisker_high",
            "field:plotcalc.outlier_value",
            "field:plotcalc.outlier_row_id",
        ),
        rows,
    )
    return _result(
        TukeyBoxResult,
        _base_payload(
            spec,
            data,
            filtered,
            table,
            input_hash=input_hash,
            producer_build_hash=producer_build_hash,
            result_version=result_version,
        ),
        kind=spec.kind,
        algorithm_id=spec.algorithm_id,
        group_count=len(groups),
    )


def _kde(
    spec: ViolinKDESpec,
    data: PlotCalculationInput,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
) -> ViolinKDEResult:
    required = (
        (spec.value_field,) if spec.group_field is None else (spec.value_field, spec.group_field)
    )
    filtered = _filter_rows(spec, data, required, (spec.value_field,))
    group_fields = () if spec.group_field is None else (spec.group_field,)
    groups = _groups(data, filtered.included_indices, group_fields)
    rows: list[tuple[object, ...]] = []
    bandwidths: list[float] = []
    for group_index, group in enumerate(groups):
        if len(group.indices) < 2:
            raise _failure(
                "PLOTSPEC_CALCULATION_INSUFFICIENT_DATA",
                "Scott KDE requires at least two valid observations per group",
                group_index=group_index,
            )
        values = np.asarray(
            [_number(data.columns[spec.value_field][i], spec.value_field) for i in group.indices],
            dtype=np.float64,
        )
        try:
            geometry = scott_kde_geometry(
                tuple(float(value) for value in values),
                grid_points=spec.grid_points,
                extend_bandwidths=0.0,
            )
        except ValueError as error:
            raise _failure(
                "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
                "Scott KDE requires positive sample variance in every group",
                group_index=group_index,
            ) from error
        group_value = group.values[0] if group.values else None
        bandwidths.append(geometry.bandwidth)
        rows.extend(
            (
                group_index,
                group_value,
                grid_index,
                float(x_value),
                float(density_value),
                geometry.bandwidth,
                len(group.indices),
            )
            for grid_index, (x_value, density_value) in enumerate(
                zip(geometry.grid, geometry.density, strict=True)
            )
        )
    table = _table(
        (
            "field:plotcalc.group_index",
            "field:plotcalc.group",
            "field:plotcalc.grid_index",
            "field:plotcalc.x",
            "field:plotcalc.density",
            "field:plotcalc.bandwidth",
            "field:plotcalc.n",
        ),
        rows,
    )
    base = _base_payload(
        spec,
        data,
        filtered,
        table,
        input_hash=input_hash,
        producer_build_hash=producer_build_hash,
        result_version=result_version,
    )
    specific = {
        "kind": spec.kind,
        "algorithm_id": spec.algorithm_id,
        "group_count": len(groups),
        "grid_points": spec.grid_points,
        "bandwidths": tuple(bandwidths),
    }
    return _result(ViolinKDEResult, base, **specific)


def _ecdf(
    spec: ECDFSpec,
    data: PlotCalculationInput,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
) -> ECDFResult:
    filtered = _filter_rows(spec, data, (spec.value_field,), (spec.value_field,))
    values = np.asarray(
        [
            _number(data.columns[spec.value_field][i], spec.value_field)
            for i in filtered.included_indices
        ],
        dtype=np.float64,
    )
    unique, counts = np.unique(values, return_counts=True)
    cumulative = np.cumsum(counts) if spec.mode == "ecdf" else np.cumsum(counts[::-1])[::-1]
    rows = tuple(
        (index, float(value), int(count), float(count / values.size))
        for index, (value, count) in enumerate(zip(unique, cumulative, strict=True))
    )
    table = _table(
        (
            "field:plotcalc.point_index",
            "field:plotcalc.x",
            "field:plotcalc.cumulative_count",
            "field:plotcalc.probability",
        ),
        rows,
    )
    return _result(
        ECDFResult,
        _base_payload(
            spec,
            data,
            filtered,
            table,
            input_hash=input_hash,
            producer_build_hash=producer_build_hash,
            result_version=result_version,
        ),
        kind=spec.kind,
        algorithm_id=spec.algorithm_id,
        mode=spec.mode,
    )


def _summary_bounds(method: str, values: np.ndarray) -> tuple[float, float, float]:
    if values.size < 2:
        raise _failure(
            "PLOTSPEC_CALCULATION_INSUFFICIENT_DATA",
            "computed summaries require at least two valid observations per group",
        )
    if method.startswith("mean_"):
        center = float(np.mean(values))
        standard_deviation = float(np.std(values, ddof=1))
        if method == "mean_sd":
            error = standard_deviation
        elif method == "mean_sem":
            error = standard_deviation / math.sqrt(values.size)
        else:
            critical = float(student_t.ppf(0.975, values.size - 1))
            error = critical * standard_deviation / math.sqrt(values.size)
        return center, center - error, center + error
    center = float(np.quantile(values, 0.5, method="linear"))
    if method == "median_iqr":
        lower, upper = np.quantile(values, (0.25, 0.75), method="linear")
        return center, float(lower), float(upper)
    return center, float(np.min(values)), float(np.max(values))


def _summary_error(
    spec: SummaryErrorSpec,
    data: PlotCalculationInput,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
) -> SummaryErrorResult:
    computed = spec.method in {
        "mean_sd",
        "mean_sem",
        "mean_95_t_ci",
        "median_iqr",
        "median_range",
    }
    required: tuple[str, ...]
    numeric: tuple[str, ...]
    if computed:
        assert spec.value_field is not None
        required = (*spec.group_fields, spec.value_field)
        numeric = (spec.value_field,)
    elif spec.method == "direct_bounds":
        assert spec.center_field is not None
        assert spec.lower_field is not None
        assert spec.upper_field is not None
        required = (*spec.group_fields, spec.center_field, spec.lower_field, spec.upper_field)
        numeric = (spec.center_field, spec.lower_field, spec.upper_field)
    else:
        assert spec.center_field is not None
        assert spec.symmetric_error_field is not None
        required = (*spec.group_fields, spec.center_field, spec.symmetric_error_field)
        numeric = (spec.center_field, spec.symmetric_error_field)
    filtered = _filter_rows(spec, data, required, numeric)
    rows: list[tuple[object, ...]] = []
    if computed:
        groups = _groups(data, filtered.included_indices, spec.group_fields)
        assert spec.value_field is not None
        for group_index, group in enumerate(groups):
            values = np.asarray(
                [
                    _number(data.columns[spec.value_field][i], spec.value_field)
                    for i in group.indices
                ],
                dtype=np.float64,
            )
            try:
                center, lower, upper = _summary_bounds(spec.method, values)
            except PlotCalculationError as calculation_error:
                raise _failure(
                    calculation_error.code,
                    calculation_error.message,
                    group_index=group_index,
                ) from calculation_error
            rows.append(
                (
                    group_index,
                    *group.values,
                    None,
                    len(group.indices),
                    center,
                    lower,
                    upper,
                    center - lower,
                    upper - center,
                )
            )
    else:
        groups = ()
        seen_groups: set[tuple[_CategoryIdentity, ...]] = set()
        for group_index, index in enumerate(filtered.included_indices):
            group_values = tuple(
                _category(data.columns[field][index], field) for field in spec.group_fields
            )
            identity = tuple(_category_identity(value) for value in group_values)
            if spec.group_fields and identity in seen_groups:
                raise _failure(
                    "PLOTSPEC_CALCULATION_DUPLICATE_CELL",
                    "direct summary rows must be unique for their group fields",
                    row_id=data.row_ids[index],
                )
            seen_groups.add(identity)
            assert spec.center_field is not None
            center = _number(data.columns[spec.center_field][index], spec.center_field)
            if spec.method == "direct_bounds":
                assert spec.lower_field is not None
                assert spec.upper_field is not None
                lower = _number(data.columns[spec.lower_field][index], spec.lower_field)
                upper = _number(data.columns[spec.upper_field][index], spec.upper_field)
                if lower > center or center > upper:
                    raise _failure(
                        "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
                        "direct bounds must satisfy lower <= center <= upper",
                        row_id=data.row_ids[index],
                    )
            else:
                assert spec.symmetric_error_field is not None
                symmetric_error = _number(
                    data.columns[spec.symmetric_error_field][index], spec.symmetric_error_field
                )
                if symmetric_error < 0:
                    raise _failure(
                        "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
                        "direct symmetric error must be non-negative",
                        row_id=data.row_ids[index],
                    )
                lower, upper = center - symmetric_error, center + symmetric_error
            rows.append(
                (
                    group_index,
                    *group_values,
                    data.row_ids[index],
                    1,
                    center,
                    lower,
                    upper,
                    center - lower,
                    upper - center,
                )
            )
    table = _table(
        (
            "field:plotcalc.group_index",
            *spec.group_fields,
            "field:plotcalc.source_row_id",
            "field:plotcalc.n",
            "field:plotcalc.center",
            "field:plotcalc.lower",
            "field:plotcalc.upper",
            "field:plotcalc.error_minus",
            "field:plotcalc.error_plus",
        ),
        rows,
    )
    return _result(
        SummaryErrorResult,
        _base_payload(
            spec,
            data,
            filtered,
            table,
            input_hash=input_hash,
            producer_build_hash=producer_build_hash,
            result_version=result_version,
        ),
        kind=spec.kind,
        algorithm_id=spec.algorithm_id,
        method=spec.method,
        group_count=len(rows),
    )


def _percent_stack(
    spec: PercentStackSpec,
    data: PlotCalculationInput,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
) -> PercentStackResult:
    required = (spec.category_field, spec.component_field, spec.value_field)
    filtered = _filter_rows(spec, data, required, (spec.value_field,))
    category_values: dict[_CategoryIdentity, _Scalar] = {}
    component_values: dict[_CategoryIdentity, _Scalar] = {}
    cells: dict[tuple[_CategoryIdentity, _CategoryIdentity], tuple[int, float]] = {}
    totals: dict[_CategoryIdentity, float] = {}
    for index in filtered.included_indices:
        category = _category(data.columns[spec.category_field][index], spec.category_field)
        component = _category(data.columns[spec.component_field][index], spec.component_field)
        value = _number(data.columns[spec.value_field][index], spec.value_field)
        if value < 0:
            raise _failure(
                "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
                "percent-stack components must be non-negative",
                row_id=data.row_ids[index],
                value=value,
            )
        category_id = _category_identity(category)
        component_id = _category_identity(component)
        cell_id = (category_id, component_id)
        if cell_id in cells:
            raise _failure(
                "PLOTSPEC_CALCULATION_DUPLICATE_CELL",
                "percent-stack category/component cells must be unique",
                row_id=data.row_ids[index],
            )
        category_values.setdefault(category_id, category)
        component_values.setdefault(component_id, component)
        cells[cell_id] = (index, value)
        totals[category_id] = totals.get(category_id, 0.0) + value
    zero_categories = [category_values[key] for key, total in totals.items() if total <= 0]
    if zero_categories:
        raise _failure(
            "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
            "every percent-stack category total must be greater than zero",
            categories=tuple(zero_categories),
        )
    rows: list[tuple[object, ...]] = []
    for category_index, category_id in enumerate(category_values):
        total = totals[category_id]
        for component_index, component_id in enumerate(component_values):
            cell = cells.get((category_id, component_id))
            if cell is None:
                continue
            source_index, value = cell
            proportion = value / total
            rows.append(
                (
                    category_index,
                    category_values[category_id],
                    component_index,
                    component_values[component_id],
                    data.row_ids[source_index],
                    value,
                    total,
                    proportion,
                    100.0 * proportion,
                )
            )
    table = _table(
        (
            "field:plotcalc.category_index",
            spec.category_field,
            "field:plotcalc.component_index",
            spec.component_field,
            "field:plotcalc.source_row_id",
            "field:plotcalc.original_value",
            "field:plotcalc.category_total",
            "field:plotcalc.proportion",
            "field:plotcalc.percent",
        ),
        rows,
    )
    return _result(
        PercentStackResult,
        _base_payload(
            spec,
            data,
            filtered,
            table,
            input_hash=input_hash,
            producer_build_hash=producer_build_hash,
            result_version=result_version,
        ),
        kind=spec.kind,
        algorithm_id=spec.algorithm_id,
        category_count=len(category_values),
        component_count=len(component_values),
    )


def _matrix_projection(
    spec: MatrixProjectionSpec,
    data: PlotCalculationInput,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
) -> MatrixProjectionResult:
    rows: list[tuple[object, ...]]
    if spec.input_mode == "regular_matrix":
        if data.matrix is not None:
            expected_width = len(spec.matrix_value_fields)
            if any(len(row) != expected_width for row in data.matrix):
                raise _failure(
                    "PLOTSPEC_CALCULATION_SHAPE_INVALID",
                    "regular matrix width must match matrix_value_fields",
                    expected=expected_width,
                )
            matrix_columns: Mapping[str, Sequence[object]] = {
                field_id: tuple(row[column_index] for row in data.matrix)
                for column_index, field_id in enumerate(spec.matrix_value_fields)
            }
        else:
            matrix_columns = _required_columns(data, spec.matrix_value_fields)
        filtered = _filter_rows(
            spec,
            data,
            spec.matrix_value_fields,
            spec.matrix_value_fields,
            columns=matrix_columns,
        )
        rows = []
        for matrix_row_index, source_index in enumerate(filtered.included_indices):
            for matrix_column_index, field_id in enumerate(spec.matrix_value_fields):
                rows.append(
                    (
                        matrix_row_index,
                        matrix_column_index,
                        data.row_ids[source_index],
                        field_id,
                        _number(matrix_columns[field_id][source_index], field_id),
                    )
                )
        matrix_rows = len(filtered.included_indices)
        matrix_column_count = len(spec.matrix_value_fields)
        complete_grid = True
        table = _table(
            (
                "field:plotcalc.matrix_row_index",
                "field:plotcalc.matrix_column_index",
                "field:plotcalc.source_row_id",
                "field:plotcalc.column_field",
                "field:plotcalc.value",
            ),
            rows,
        )
    else:
        assert spec.x_field is not None
        assert spec.y_field is not None
        assert spec.z_field is not None
        fields = (spec.x_field, spec.y_field, spec.z_field)
        filtered = _filter_rows(spec, data, fields, fields)
        cells: dict[tuple[float, float], tuple[int, float]] = {}
        for index in filtered.included_indices:
            x = _number(data.columns[spec.x_field][index], spec.x_field)
            y = _number(data.columns[spec.y_field][index], spec.y_field)
            z = _number(data.columns[spec.z_field][index], spec.z_field)
            coordinate = (x, y)
            if coordinate in cells:
                raise _failure(
                    "PLOTSPEC_CALCULATION_DUPLICATE_COORDINATE",
                    "heatmap XY coordinates must be unique",
                    row_id=data.row_ids[index],
                    x=x,
                    y=y,
                )
            cells[coordinate] = (index, z)
        x_values = sorted({coordinate[0] for coordinate in cells})
        y_values = sorted({coordinate[1] for coordinate in cells})
        x_index = {value: index for index, value in enumerate(x_values)}
        y_index = {value: index for index, value in enumerate(y_values)}
        rows = [
            (
                y_index[y],
                x_index[x],
                x,
                y,
                z,
                data.row_ids[source_index],
            )
            for (x, y), (source_index, z) in sorted(
                cells.items(), key=lambda cell: (cell[0][1], cell[0][0])
            )
        ]
        matrix_rows = len(y_values)
        matrix_column_count = len(x_values)
        complete_grid = len(cells) == matrix_rows * matrix_column_count
        table = _table(
            (
                "field:plotcalc.matrix_row_index",
                "field:plotcalc.matrix_column_index",
                spec.x_field,
                spec.y_field,
                spec.z_field,
                "field:plotcalc.source_row_id",
            ),
            rows,
        )
    return _result(
        MatrixProjectionResult,
        _base_payload(
            spec,
            data,
            filtered,
            table,
            input_hash=input_hash,
            producer_build_hash=producer_build_hash,
            result_version=result_version,
        ),
        kind=spec.kind,
        algorithm_id=spec.algorithm_id,
        matrix_rows=matrix_rows,
        matrix_columns=matrix_column_count,
        complete_grid=complete_grid,
    )


def _confusion_count(
    spec: ConfusionCountSpec,
    data: PlotCalculationInput,
    *,
    input_hash: str,
    producer_build_hash: str,
    result_version: int,
) -> ConfusionCountResult:
    fields = (
        spec.actual_field,
        spec.predicted_field,
        *((spec.count_field,) if spec.count_field is not None else ()),
    )
    numeric_fields = () if spec.count_field is None else (spec.count_field,)
    filtered = _filter_rows(spec, data, fields, numeric_fields)
    observed_pairs: list[tuple[str, str, int]] = []
    observed_order: dict[str, None] = {}
    for index in filtered.included_indices:
        actual = _category_label(
            _category(data.columns[spec.actual_field][index], spec.actual_field)
        )
        predicted = _category_label(
            _category(data.columns[spec.predicted_field][index], spec.predicted_field)
        )
        count = 1
        if spec.count_field is not None:
            numeric_count = _number(data.columns[spec.count_field][index], spec.count_field)
            if numeric_count < 0 or not numeric_count.is_integer():
                raise _failure(
                    "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
                    "pre-aggregated confusion counts must be non-negative integers",
                    field_id=spec.count_field,
                    row_id=data.row_ids[index],
                    value=numeric_count,
                )
            count = int(numeric_count)
        observed_pairs.append((actual, predicted, count))
        observed_order.setdefault(actual, None)
        observed_order.setdefault(predicted, None)
    if spec.category_order:
        category_order = spec.category_order
        unknown = sorted(set(observed_order).difference(category_order))
        if unknown:
            raise _failure(
                "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
                "explicit confusion category_order omits observed categories",
                categories=tuple(unknown),
            )
    else:
        category_order = tuple(observed_order)
    category_index = {category: index for index, category in enumerate(category_order)}
    counts = np.zeros((len(category_order), len(category_order)), dtype=np.int64)
    for actual, predicted, count in observed_pairs:
        counts[category_index[actual], category_index[predicted]] += count
    row_totals = counts.sum(axis=1)
    column_totals = counts.sum(axis=0)
    zero_denominator = False
    rows = []
    for actual_index, actual in enumerate(category_order):
        for predicted_index, predicted in enumerate(category_order):
            count = int(counts[actual_index, predicted_index])
            if spec.normalization == "count":
                value: int | float = count
            elif spec.normalization == "true_class":
                denominator = int(row_totals[actual_index])
                zero_denominator = zero_denominator or denominator == 0
                value = 0.0 if denominator == 0 else count / denominator
            else:
                denominator = int(column_totals[predicted_index])
                zero_denominator = zero_denominator or denominator == 0
                value = 0.0 if denominator == 0 else count / denominator
            rows.append(
                (
                    actual_index,
                    actual,
                    predicted_index,
                    predicted,
                    count,
                    int(row_totals[actual_index]),
                    int(column_totals[predicted_index]),
                    value,
                )
            )
    warnings = (
        (
            WarningRecord(
                warning_id="plotcalc.zero_normalization_denominator",
                message=(
                    "An explicit confusion category had a zero normalization denominator; "
                    "output is 0."
                ),
            ),
        )
        if zero_denominator
        else ()
    )
    table = _table(
        (
            "field:plotcalc.actual_index",
            "field:plotcalc.actual_category",
            "field:plotcalc.predicted_index",
            "field:plotcalc.predicted_category",
            "field:plotcalc.count",
            "field:plotcalc.actual_total",
            "field:plotcalc.predicted_total",
            "field:plotcalc.value",
        ),
        rows,
    )
    return _result(
        ConfusionCountResult,
        _base_payload(
            spec,
            data,
            filtered,
            table,
            input_hash=input_hash,
            producer_build_hash=producer_build_hash,
            result_version=result_version,
            warnings=warnings,
        ),
        kind=spec.kind,
        algorithm_id=spec.algorithm_id,
        normalization=spec.normalization,
        category_count=len(category_order),
        category_order=category_order,
    )


class PlotCalculationService:
    """Side-effect-free dispatcher for the closed PlotCalculationSpec union."""

    def calculate(
        self,
        spec: PlotCalculationSpec,
        data: PlotCalculationInput,
        *,
        producer_build_hash: str,
        result_version: int = 1,
    ) -> PlotCalculationResult:
        if spec.algorithm_version != ALGORITHM_VERSION:
            raise _failure(
                "PLOTSPEC_CALCULATION_VERSION_UNSUPPORTED",
                "unsupported fixed calculation algorithm version",
                expected=ALGORITHM_VERSION,
                actual=spec.algorithm_version,
            )
        _validate_input_shape(data)
        input_hash = _input_hash(data)
        if isinstance(spec, HistogramBinningSpec):
            return _histogram(
                spec,
                data,
                input_hash=input_hash,
                producer_build_hash=producer_build_hash,
                result_version=result_version,
            )
        if isinstance(spec, TukeyBoxSpec):
            return _tukey_box(
                spec,
                data,
                input_hash=input_hash,
                producer_build_hash=producer_build_hash,
                result_version=result_version,
            )
        if isinstance(spec, ViolinKDESpec):
            return _kde(
                spec,
                data,
                input_hash=input_hash,
                producer_build_hash=producer_build_hash,
                result_version=result_version,
            )
        if isinstance(spec, ECDFSpec):
            return _ecdf(
                spec,
                data,
                input_hash=input_hash,
                producer_build_hash=producer_build_hash,
                result_version=result_version,
            )
        if isinstance(spec, SummaryErrorSpec):
            return _summary_error(
                spec,
                data,
                input_hash=input_hash,
                producer_build_hash=producer_build_hash,
                result_version=result_version,
            )
        if isinstance(spec, PercentStackSpec):
            return _percent_stack(
                spec,
                data,
                input_hash=input_hash,
                producer_build_hash=producer_build_hash,
                result_version=result_version,
            )
        if isinstance(spec, MatrixProjectionSpec):
            return _matrix_projection(
                spec,
                data,
                input_hash=input_hash,
                producer_build_hash=producer_build_hash,
                result_version=result_version,
            )
        if isinstance(spec, ConfusionCountSpec):
            return _confusion_count(
                spec,
                data,
                input_hash=input_hash,
                producer_build_hash=producer_build_hash,
                result_version=result_version,
            )
        raise _failure(
            "PLOTSPEC_CALCULATION_UNSUPPORTED",
            "the calculation kind is outside the frozen v1 union",
        )


def calculate_plot(
    spec: PlotCalculationSpec,
    data: PlotCalculationInput,
    *,
    producer_build_hash: str,
    result_version: int = 1,
) -> PlotCalculationResult:
    """Convenience entry point using the stateless service."""

    return PlotCalculationService().calculate(
        spec,
        data,
        producer_build_hash=producer_build_hash,
        result_version=result_version,
    )
