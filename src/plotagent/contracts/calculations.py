"""Closed v1 plot-calculation specification and result unions."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    SCHEMA_VERSION,
    CalculationKind,
    ContentTableRef,
    FieldId,
    FiniteNumber,
    MissingPolicy,
    NonFiniteCounts,
    NonNegativeInt,
    PlotCalculationSpecRef,
    PositiveInt,
    PreparedDatasetRef,
    RowExclusion,
    RowId,
    SchemaVersion,
    Sha256,
    StrictModel,
    Token,
    VersionId,
    WarningRecord,
)
from plotagent.contracts.canonical import canonical_hash

SummaryMethod = Literal[
    "mean_sd",
    "mean_sem",
    "mean_95_t_ci",
    "median_iqr",
    "median_range",
    "direct_bounds",
    "direct_symmetric_error",
]
ConfusionNormalization = Literal["count", "true_class", "predicted_class"]
CalculationCell = str | bool | int | FiniteNumber | None


class CalculationTable(StrictModel):
    """Self-contained renderer geometry with a content-addressed strict shape."""

    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1)]
    rows: tuple[tuple[CalculationCell, ...], ...]

    @model_validator(mode="after")
    def rectangular_unique_table(self) -> CalculationTable:
        if len(set(self.field_ids)) != len(self.field_ids):
            raise ValueError("calculation table field_ids must be unique")
        width = len(self.field_ids)
        if any(len(row) != width for row in self.rows):
            raise ValueError("calculation table rows must match field_ids width")
        return self


class CalculationSpecBase(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    calculation_id: Annotated[
        str,
        StringConstraints(pattern=r"^plotcalc:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    calculation_version: VersionId
    prepared_dataset_ref: PreparedDatasetRef
    algorithm_version: Token
    missing_policy: MissingPolicy
    log10_fields: tuple[FieldId, ...] = ()
    fixed_seed: NonNegativeInt | None = None

    @model_validator(mode="after")
    def unique_log10_fields(self) -> CalculationSpecBase:
        if len(set(self.log10_fields)) != len(self.log10_fields):
            raise ValueError("log10_fields must be unique")
        return self


class HistogramBinningSpec(CalculationSpecBase):
    kind: Literal["histogram_binning"] = "histogram_binning"
    algorithm_id: Literal["freedman_diaconis_sturges"] = "freedman_diaconis_sturges"
    value_field: FieldId
    normalization: Literal["count", "density"] = "count"


class TukeyBoxSpec(CalculationSpecBase):
    kind: Literal["tukey_box"] = "tukey_box"
    algorithm_id: Literal["linear_quantile_tukey_1_5_iqr"] = "linear_quantile_tukey_1_5_iqr"
    value_field: FieldId
    group_field: FieldId | None = None

    @model_validator(mode="after")
    def distinct_fields(self) -> TukeyBoxSpec:
        if self.group_field == self.value_field:
            raise ValueError("group_field must differ from value_field")
        return self


class ViolinKDESpec(CalculationSpecBase):
    kind: Literal["violin_kde"] = "violin_kde"
    algorithm_id: Literal["gaussian_scott_observed_range"] = "gaussian_scott_observed_range"
    value_field: FieldId
    group_field: FieldId | None = None
    grid_points: Literal[256] = 256

    @model_validator(mode="after")
    def distinct_fields(self) -> ViolinKDESpec:
        if self.group_field == self.value_field:
            raise ValueError("group_field must differ from value_field")
        return self


class DensityKDESpec(CalculationSpecBase):
    kind: Literal["density_kde"] = "density_kde"
    algorithm_id: Literal["gaussian_scott_three_bandwidth"] = "gaussian_scott_three_bandwidth"
    value_field: FieldId
    group_field: FieldId | None = None
    grid_points: Literal[256] = 256

    @model_validator(mode="after")
    def distinct_fields(self) -> DensityKDESpec:
        if self.group_field == self.value_field:
            raise ValueError("group_field must differ from value_field")
        return self


class ECDFSpec(CalculationSpecBase):
    kind: Literal["ecdf"] = "ecdf"
    algorithm_id: Literal["right_continuous_empirical_cdf"] = "right_continuous_empirical_cdf"
    value_field: FieldId
    mode: Literal["ecdf", "ccdf"] = "ecdf"


class SummaryErrorSpec(CalculationSpecBase):
    kind: Literal["summary_error"] = "summary_error"
    algorithm_id: Literal["fixed_summary_error"] = "fixed_summary_error"
    method: SummaryMethod
    group_fields: tuple[FieldId, ...] = ()
    value_field: FieldId | None = None
    center_field: FieldId | None = None
    lower_field: FieldId | None = None
    upper_field: FieldId | None = None
    symmetric_error_field: FieldId | None = None

    @model_validator(mode="after")
    def method_fields(self) -> SummaryErrorSpec:
        computed = {"mean_sd", "mean_sem", "mean_95_t_ci", "median_iqr", "median_range"}
        if len(set(self.group_fields)) != len(self.group_fields):
            raise ValueError("group_fields must be unique")
        if self.method in computed and self.value_field is None:
            raise ValueError("computed summaries require value_field")
        if self.method == "direct_bounds" and (
            self.center_field is None or self.lower_field is None or self.upper_field is None
        ):
            raise ValueError("direct_bounds requires center, lower, and upper fields")
        if self.method == "direct_symmetric_error" and (
            self.center_field is None or self.symmetric_error_field is None
        ):
            raise ValueError("direct_symmetric_error requires center and symmetric error fields")
        relevant_fields = {
            field
            for field in (
                self.value_field,
                self.center_field,
                self.lower_field,
                self.upper_field,
                self.symmetric_error_field,
            )
            if field is not None
        }
        if relevant_fields.intersection(self.group_fields):
            raise ValueError("summary value and group fields must be distinct")
        if self.method in computed and any(
            field is not None
            for field in (
                self.center_field,
                self.lower_field,
                self.upper_field,
                self.symmetric_error_field,
            )
        ):
            raise ValueError("computed summaries reject direct-input fields")
        if self.method == "direct_bounds" and (
            self.value_field is not None or self.symmetric_error_field is not None
        ):
            raise ValueError("direct_bounds rejects computed and symmetric-error fields")
        if self.method == "direct_symmetric_error" and any(
            field is not None for field in (self.value_field, self.lower_field, self.upper_field)
        ):
            raise ValueError("direct_symmetric_error rejects computed and bound fields")
        return self


class PercentStackSpec(CalculationSpecBase):
    kind: Literal["percent_stack"] = "percent_stack"
    algorithm_id: Literal["category_nonnegative_percent"] = "category_nonnegative_percent"
    category_field: FieldId
    component_field: FieldId
    value_field: FieldId

    @model_validator(mode="after")
    def distinct_fields(self) -> PercentStackSpec:
        fields = (self.category_field, self.component_field, self.value_field)
        if len(set(fields)) != len(fields):
            raise ValueError("percent-stack fields must be distinct")
        return self


class MatrixProjectionSpec(CalculationSpecBase):
    kind: Literal["matrix_projection"] = "matrix_projection"
    algorithm_id: Literal["regular_or_unique_xy_projection"] = "regular_or_unique_xy_projection"
    input_mode: Literal["regular_matrix", "unique_xy"]
    matrix_value_fields: tuple[FieldId, ...] = ()
    x_field: FieldId | None = None
    y_field: FieldId | None = None
    z_field: FieldId | None = None

    @model_validator(mode="after")
    def input_shape(self) -> MatrixProjectionSpec:
        if self.input_mode == "regular_matrix":
            if not self.matrix_value_fields:
                raise ValueError("regular_matrix requires matrix_value_fields")
            if len(set(self.matrix_value_fields)) != len(self.matrix_value_fields):
                raise ValueError("matrix_value_fields must be unique")
            if any(field is not None for field in (self.x_field, self.y_field, self.z_field)):
                raise ValueError("regular_matrix rejects unique_xy fields")
        if self.input_mode == "unique_xy":
            if self.x_field is None or self.y_field is None or self.z_field is None:
                raise ValueError("unique_xy requires x, y, and z fields")
            if len({self.x_field, self.y_field, self.z_field}) != 3:
                raise ValueError("unique_xy fields must be distinct")
            if self.matrix_value_fields:
                raise ValueError("unique_xy rejects matrix_value_fields")
        return self


class ConfusionCountSpec(CalculationSpecBase):
    kind: Literal["confusion_count"] = "confusion_count"
    algorithm_id: Literal["fixed_confusion_count"] = "fixed_confusion_count"
    actual_field: FieldId
    predicted_field: FieldId
    normalization: ConfusionNormalization = "count"
    category_order: tuple[str, ...] = ()

    @model_validator(mode="after")
    def category_contract(self) -> ConfusionCountSpec:
        if self.actual_field == self.predicted_field:
            raise ValueError("actual_field must differ from predicted_field")
        if len(set(self.category_order)) != len(self.category_order):
            raise ValueError("category_order must be unique")
        return self


PlotCalculationSpec = Annotated[
    HistogramBinningSpec
    | TukeyBoxSpec
    | ViolinKDESpec
    | DensityKDESpec
    | ECDFSpec
    | SummaryErrorSpec
    | PercentStackSpec
    | MatrixProjectionSpec
    | ConfusionCountSpec,
    Field(discriminator="kind"),
]


class CalculationResultBase(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    calculation_id: Annotated[
        str,
        StringConstraints(pattern=r"^plotcalc:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    result_version: VersionId
    spec_ref: PlotCalculationSpecRef
    prepared_dataset_ref: PreparedDatasetRef
    algorithm_version: Token
    missing_policy: MissingPolicy
    input_hash: Sha256
    output_hash: Sha256
    output_data_ref: ContentTableRef
    output_table: CalculationTable
    total_row_count: NonNegativeInt
    included_row_count: NonNegativeInt
    excluded_row_count: NonNegativeInt
    included_row_ids: tuple[RowId, ...]
    exclusions: tuple[RowExclusion, ...] = ()
    nonfinite_counts: NonFiniteCounts = NonFiniteCounts()
    fixed_seed: NonNegativeInt | None = None
    warnings: tuple[WarningRecord, ...] = ()
    producer_build_hash: Sha256

    @model_validator(mode="after")
    def consistent_result(self) -> CalculationResultBase:
        result_kind = getattr(self, "kind", None)
        if result_kind is not None and self.spec_ref.calculation_kind != result_kind:
            raise ValueError("result kind must match its calculation spec reference")
        if self.output_hash != self.output_data_ref.object_hash:
            raise ValueError("output_hash must match output_data_ref")
        if self.output_hash != canonical_hash(self.output_table):
            raise ValueError("output_hash must match the embedded calculation table")
        if self.output_data_ref.row_count != len(self.output_table.rows):
            raise ValueError("output_data_ref row_count must match output_table")
        if self.output_data_ref.field_ids != self.output_table.field_ids:
            raise ValueError("output_data_ref fields must match output_table")
        if self.included_row_count + self.excluded_row_count != self.total_row_count:
            raise ValueError("included and excluded counts must match total")
        if len(self.included_row_ids) != self.included_row_count:
            raise ValueError("included_row_ids must enumerate every included row")
        if len(set(self.included_row_ids)) != len(self.included_row_ids):
            raise ValueError("included_row_ids must be unique")
        if len(self.exclusions) != self.excluded_row_count:
            raise ValueError("exclusions must enumerate every excluded row")
        excluded_ids = tuple(exclusion.row_id for exclusion in self.exclusions)
        if len(set(excluded_ids)) != len(excluded_ids):
            raise ValueError("exclusions must enumerate unique rows")
        if set(excluded_ids).intersection(self.included_row_ids):
            raise ValueError("included and excluded row ids must be disjoint")
        return self


class HistogramBinningResult(CalculationResultBase):
    kind: Literal["histogram_binning"] = "histogram_binning"
    algorithm_id: Literal["freedman_diaconis_sturges"] = "freedman_diaconis_sturges"
    bin_count: PositiveInt
    normalization: Literal["count", "density"]
    binning_rule: Literal["freedman_diaconis", "sturges", "constant"]


class TukeyBoxResult(CalculationResultBase):
    kind: Literal["tukey_box"] = "tukey_box"
    algorithm_id: Literal["linear_quantile_tukey_1_5_iqr"] = "linear_quantile_tukey_1_5_iqr"
    group_count: PositiveInt


class ViolinKDEResult(CalculationResultBase):
    kind: Literal["violin_kde"] = "violin_kde"
    algorithm_id: Literal["gaussian_scott_observed_range"] = "gaussian_scott_observed_range"
    group_count: PositiveInt
    grid_points: Literal[256] = 256
    bandwidths: tuple[FiniteNumber, ...]


class DensityKDEResult(CalculationResultBase):
    kind: Literal["density_kde"] = "density_kde"
    algorithm_id: Literal["gaussian_scott_three_bandwidth"] = "gaussian_scott_three_bandwidth"
    group_count: PositiveInt
    grid_points: Literal[256] = 256
    bandwidths: tuple[FiniteNumber, ...]


class ECDFResult(CalculationResultBase):
    kind: Literal["ecdf"] = "ecdf"
    algorithm_id: Literal["right_continuous_empirical_cdf"] = "right_continuous_empirical_cdf"
    mode: Literal["ecdf", "ccdf"]


class SummaryErrorResult(CalculationResultBase):
    kind: Literal["summary_error"] = "summary_error"
    algorithm_id: Literal["fixed_summary_error"] = "fixed_summary_error"
    method: SummaryMethod
    group_count: PositiveInt


class PercentStackResult(CalculationResultBase):
    kind: Literal["percent_stack"] = "percent_stack"
    algorithm_id: Literal["category_nonnegative_percent"] = "category_nonnegative_percent"
    category_count: PositiveInt
    component_count: PositiveInt


class MatrixProjectionResult(CalculationResultBase):
    kind: Literal["matrix_projection"] = "matrix_projection"
    algorithm_id: Literal["regular_or_unique_xy_projection"] = "regular_or_unique_xy_projection"
    matrix_rows: PositiveInt
    matrix_columns: PositiveInt
    complete_grid: bool


class ConfusionCountResult(CalculationResultBase):
    kind: Literal["confusion_count"] = "confusion_count"
    algorithm_id: Literal["fixed_confusion_count"] = "fixed_confusion_count"
    normalization: ConfusionNormalization
    category_count: PositiveInt
    category_order: tuple[str, ...]


PlotCalculationResult = Annotated[
    HistogramBinningResult
    | TukeyBoxResult
    | ViolinKDEResult
    | DensityKDEResult
    | ECDFResult
    | SummaryErrorResult
    | PercentStackResult
    | MatrixProjectionResult
    | ConfusionCountResult,
    Field(discriminator="kind"),
]


def calculation_kind(spec: PlotCalculationSpec) -> CalculationKind:
    """Return a narrowly typed discriminator for registry validation."""

    return spec.kind
