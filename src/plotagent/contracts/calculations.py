"""Closed v1 plot-calculation specification and result unions."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    SCHEMA_VERSION,
    CalculationKind,
    ContentTableRef,
    FieldId,
    MissingPolicy,
    NonNegativeInt,
    PlotCalculationSpecRef,
    PositiveInt,
    PreparedDatasetRef,
    RowExclusion,
    SchemaVersion,
    Sha256,
    StrictModel,
    Token,
    VersionId,
    WarningRecord,
)

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


class ViolinKDESpec(CalculationSpecBase):
    kind: Literal["violin_kde"] = "violin_kde"
    algorithm_id: Literal["gaussian_scott_observed_range"] = "gaussian_scott_observed_range"
    value_field: FieldId
    group_field: FieldId | None = None
    grid_points: Literal[256] = 256


class DensityKDESpec(CalculationSpecBase):
    kind: Literal["density_kde"] = "density_kde"
    algorithm_id: Literal["gaussian_scott_three_bandwidth"] = "gaussian_scott_three_bandwidth"
    value_field: FieldId
    group_field: FieldId | None = None
    grid_points: Literal[256] = 256


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
        return self


class PercentStackSpec(CalculationSpecBase):
    kind: Literal["percent_stack"] = "percent_stack"
    algorithm_id: Literal["category_nonnegative_percent"] = "category_nonnegative_percent"
    category_field: FieldId
    component_field: FieldId
    value_field: FieldId


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
        if self.input_mode == "regular_matrix" and not self.matrix_value_fields:
            raise ValueError("regular_matrix requires matrix_value_fields")
        if self.input_mode == "unique_xy" and (
            self.x_field is None or self.y_field is None or self.z_field is None
        ):
            raise ValueError("unique_xy requires x, y, and z fields")
        return self


class ConfusionCountSpec(CalculationSpecBase):
    kind: Literal["confusion_count"] = "confusion_count"
    algorithm_id: Literal["fixed_confusion_count"] = "fixed_confusion_count"
    actual_field: FieldId
    predicted_field: FieldId
    normalization: ConfusionNormalization = "count"
    category_order: tuple[str, ...] = ()


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
    total_row_count: NonNegativeInt
    included_row_count: NonNegativeInt
    excluded_row_count: NonNegativeInt
    exclusions: tuple[RowExclusion, ...] = ()
    warnings: tuple[WarningRecord, ...] = ()
    producer_build_hash: Sha256

    @model_validator(mode="after")
    def consistent_result(self) -> CalculationResultBase:
        result_kind = getattr(self, "kind", None)
        if result_kind is not None and self.spec_ref.calculation_kind != result_kind:
            raise ValueError("result kind must match its calculation spec reference")
        if self.output_hash != self.output_data_ref.object_hash:
            raise ValueError("output_hash must match output_data_ref")
        if self.included_row_count + self.excluded_row_count != self.total_row_count:
            raise ValueError("included and excluded counts must match total")
        if len(self.exclusions) != self.excluded_row_count:
            raise ValueError("exclusions must enumerate every excluded row")
        return self


class HistogramBinningResult(CalculationResultBase):
    kind: Literal["histogram_binning"] = "histogram_binning"
    algorithm_id: Literal["freedman_diaconis_sturges"] = "freedman_diaconis_sturges"
    bin_count: PositiveInt
    normalization: Literal["count", "density"]


class TukeyBoxResult(CalculationResultBase):
    kind: Literal["tukey_box"] = "tukey_box"
    algorithm_id: Literal["linear_quantile_tukey_1_5_iqr"] = "linear_quantile_tukey_1_5_iqr"
    group_count: PositiveInt


class ViolinKDEResult(CalculationResultBase):
    kind: Literal["violin_kde"] = "violin_kde"
    algorithm_id: Literal["gaussian_scott_observed_range"] = "gaussian_scott_observed_range"
    group_count: PositiveInt
    grid_points: Literal[256] = 256


class DensityKDEResult(CalculationResultBase):
    kind: Literal["density_kde"] = "density_kde"
    algorithm_id: Literal["gaussian_scott_three_bandwidth"] = "gaussian_scott_three_bandwidth"
    group_count: PositiveInt
    grid_points: Literal[256] = 256


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


class MatrixProjectionResult(CalculationResultBase):
    kind: Literal["matrix_projection"] = "matrix_projection"
    algorithm_id: Literal["regular_or_unique_xy_projection"] = "regular_or_unique_xy_projection"
    matrix_rows: PositiveInt
    matrix_columns: PositiveInt


class ConfusionCountResult(CalculationResultBase):
    kind: Literal["confusion_count"] = "confusion_count"
    algorithm_id: Literal["fixed_confusion_count"] = "fixed_confusion_count"
    normalization: ConfusionNormalization
    category_count: PositiveInt


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
