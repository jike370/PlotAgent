"""Immutable staged data contracts exposed to the PlotAgent runtime."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.agent_tasks import IsoTimestamp, TaskId, TaskItemIdV2
from plotagent.contracts.base import (
    FieldId,
    FiniteNumber,
    NonNegativeInt,
    PositiveInt,
    Sha256,
    StrictModel,
    Token,
    VersionId,
)
from plotagent.engine.contracts import EngineDataRef, EngineField, EngineScalar

DataViewHandleId = Annotated[
    str,
    StringConstraints(
        pattern=r"^view:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
DataOperationKind = Literal[
    "source",
    "select_fields",
    "rename_field",
    "convert_type",
    "filter_rows",
    "sort_rows",
    "deduplicate_rows",
    "derive_column",
    "convert_unit",
    "reshape_wide_to_long",
    "reshape_long_to_wide",
    "concatenate",
    "keyed_join",
    "aggregate",
]
DataScalar = bool | int | float | str | date | datetime | None


class DataViewLineageStep(StrictModel):
    step_id: Token
    operation_kind: DataOperationKind
    input_handle_ids: Annotated[tuple[DataViewHandleId, ...], Field(max_length=8)] = ()
    input_data_hashes: Annotated[tuple[Sha256, ...], Field(max_length=8)] = ()
    parameters_hash: Sha256
    output_data_hash: Sha256

    @model_validator(mode="after")
    def inputs_are_aligned(self) -> DataViewLineageStep:
        if len(self.input_handle_ids) != len(self.input_data_hashes):
            raise ValueError("lineage input handles and hashes must align")
        if len(self.input_handle_ids) != len(set(self.input_handle_ids)):
            raise ValueError("lineage input handles must be unique")
        return self


class DataViewHandle(StrictModel):
    schema_version: Literal["data-view-handle.v2"] = "data-view-handle.v2"
    handle_id: DataViewHandleId
    handle_version: VersionId = 1
    task_id: TaskId
    task_version: VersionId
    item_id: TaskItemIdV2 | None = None
    parent_handle_ids: Annotated[tuple[DataViewHandleId, ...], Field(max_length=8)] = ()
    root_sources: Annotated[tuple[EngineDataRef, ...], Field(min_length=1, max_length=8)]
    data: EngineDataRef
    operation_kind: DataOperationKind
    operation_hash: Sha256
    data_hash: Sha256
    artifact_hash: Sha256
    row_count: PositiveInt
    fields: Annotated[tuple[EngineField, ...], Field(min_length=1, max_length=256)]
    lineage: Annotated[tuple[DataViewLineageStep, ...], Field(min_length=1, max_length=64)]
    created_at: IsoTimestamp
    expires_at: IsoTimestamp

    @model_validator(mode="after")
    def immutable_identity_is_consistent(self) -> DataViewHandle:
        if self.expires_at <= self.created_at:
            raise ValueError("staged data expiry must follow creation")
        if any(source.kind != "source" for source in self.root_sources):
            raise ValueError("staged data roots must be immutable source revisions")
        source_keys = tuple(
            (source.dataset_id, source.version, source.content_hash) for source in self.root_sources
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("staged data roots must be unique")
        if len(self.parent_handle_ids) != len(set(self.parent_handle_ids)):
            raise ValueError("parent data handles must be unique")
        field_ids = tuple(field.field_id for field in self.fields)
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("staged data fields must be unique")
        step_ids = tuple(step.step_id for step in self.lineage)
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("staged data lineage steps must be unique")
        current = self.lineage[-1]
        if (
            current.operation_kind != self.operation_kind
            or current.output_data_hash != self.data_hash
            or current.input_handle_ids != self.parent_handle_ids
        ):
            raise ValueError("staged data handle must match its terminal lineage step")
        if self.operation_kind == "source" and self.parent_handle_ids:
            raise ValueError("source data handles cannot have parents")
        if self.operation_kind != "source" and not self.parent_handle_ids:
            raise ValueError("derived data handles require at least one parent")
        if self.operation_kind == "source":
            if self.data.kind != "source" or self.data not in self.root_sources:
                raise ValueError("source handles must expose their immutable source revision")
        elif self.data.kind != "prepared" or self.data.content_hash != self.data_hash:
            raise ValueError("derived handles must expose their staged prepared-data identity")
        return self


class DataViewPreview(StrictModel):
    handle: DataViewHandle
    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1, max_length=24)]
    offset: NonNegativeInt
    rows: Annotated[tuple[tuple[EngineScalar, ...], ...], Field(max_length=40)]
    has_more: bool

    @model_validator(mode="after")
    def preview_is_rectangular(self) -> DataViewPreview:
        if any(len(row) != len(self.field_ids) for row in self.rows):
            raise ValueError("data preview rows must match selected fields")
        if self.offset + len(self.rows) > self.handle.row_count:
            raise ValueError("data preview exceeds the staged row count")
        return self


class SelectFieldsOperation(StrictModel):
    kind: Literal["select_fields"] = "select_fields"
    input_handle_id: DataViewHandleId
    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def fields_are_unique(self) -> SelectFieldsOperation:
        if len(self.field_ids) != len(set(self.field_ids)):
            raise ValueError("selected fields must be unique")
        return self


class RenameFieldOperation(StrictModel):
    kind: Literal["rename_field"] = "rename_field"
    input_handle_id: DataViewHandleId
    field_id: FieldId
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]


class ConvertTypeOperation(StrictModel):
    kind: Literal["convert_type"] = "convert_type"
    input_handle_id: DataViewHandleId
    field_id: FieldId
    target_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    output_field_id: FieldId
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    decimal_separator: Literal[".", ","] | None = None
    thousands_separator: Literal[",", ".", " "] | None = None
    datetime_format: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=64, strict=True),
        ]
        | None
    ) = None
    true_values: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    false_values: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    case_sensitive: bool = False

    @model_validator(mode="after")
    def conversion_options_match_target(self) -> ConvertTypeOperation:
        if self.output_field_id == self.field_id:
            raise ValueError("type conversion must create a new field identity")
        if (
            self.decimal_separator is not None
            and self.decimal_separator == self.thousands_separator
        ):
            raise ValueError("decimal and thousands separators must differ")
        if self.target_type == "numeric":
            if self.decimal_separator is None:
                raise ValueError("numeric conversion requires an explicit decimal separator")
            if self.datetime_format or self.true_values or self.false_values:
                raise ValueError("numeric conversion cannot carry non-numeric options")
        elif self.target_type == "datetime":
            if self.datetime_format is None:
                raise ValueError("datetime conversion requires an explicit format")
            if self.decimal_separator or self.thousands_separator:
                raise ValueError("datetime conversion cannot carry numeric separators")
        elif self.target_type == "boolean":
            if not self.true_values or not self.false_values:
                raise ValueError("boolean conversion requires true and false values")
            normalized_true = tuple(
                value if self.case_sensitive else value.casefold() for value in self.true_values
            )
            normalized_false = tuple(
                value if self.case_sensitive else value.casefold() for value in self.false_values
            )
            if set(normalized_true) & set(normalized_false):
                raise ValueError("boolean true and false values must be disjoint")
            if self.datetime_format or self.decimal_separator or self.thousands_separator:
                raise ValueError("boolean conversion cannot carry numeric or datetime options")
        elif any(
            (
                self.decimal_separator,
                self.thousands_separator,
                self.datetime_format,
                self.true_values,
                self.false_values,
            )
        ):
            raise ValueError("text and categorical conversion do not accept parsing options")
        return self


class DataFilterPredicate(StrictModel):
    field_id: FieldId
    operator: Literal[
        "equal",
        "not_equal",
        "less_than",
        "less_or_equal",
        "greater_than",
        "greater_or_equal",
        "is_missing",
        "is_not_missing",
        "in_values",
    ]
    value: DataScalar | tuple[DataScalar, ...] = None

    @model_validator(mode="after")
    def value_matches_operator(self) -> DataFilterPredicate:
        if self.operator in {"is_missing", "is_not_missing"}:
            if self.value is not None:
                raise ValueError("missing predicates do not accept a value")
        elif self.operator == "in_values":
            if not isinstance(self.value, tuple) or not self.value:
                raise ValueError("in_values requires a non-empty tuple")
        elif self.value is None or isinstance(self.value, tuple):
            raise ValueError("comparison predicates require one scalar")
        return self


class FilterRowsOperation(StrictModel):
    kind: Literal["filter_rows"] = "filter_rows"
    input_handle_id: DataViewHandleId
    predicates: Annotated[tuple[DataFilterPredicate, ...], Field(min_length=1, max_length=16)]
    combine: Literal["all", "any"] = "all"


class DataSortKey(StrictModel):
    field_id: FieldId
    direction: Literal["ascending", "descending"] = "ascending"
    missing: Literal["first", "last"] = "last"


class SortRowsOperation(StrictModel):
    kind: Literal["sort_rows"] = "sort_rows"
    input_handle_id: DataViewHandleId
    keys: Annotated[tuple[DataSortKey, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def sort_fields_are_unique(self) -> SortRowsOperation:
        fields = tuple(key.field_id for key in self.keys)
        if len(fields) != len(set(fields)):
            raise ValueError("sort fields must be unique")
        return self


class DeduplicateRowsOperation(StrictModel):
    kind: Literal["deduplicate_rows"] = "deduplicate_rows"
    input_handle_id: DataViewHandleId
    key_field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1, max_length=16)]
    keep: Literal["first", "last"] = "first"

    @model_validator(mode="after")
    def key_fields_are_unique(self) -> DeduplicateRowsOperation:
        if len(self.key_field_ids) != len(set(self.key_field_ids)):
            raise ValueError("deduplication key fields must be unique")
        return self


class DeriveColumnOperation(StrictModel):
    kind: Literal["derive_column"] = "derive_column"
    input_handle_id: DataViewHandleId
    input_field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1, max_length=2)]
    operator: Literal[
        "add",
        "subtract",
        "multiply",
        "divide",
        "absolute",
        "negate",
        "log10",
        "ln",
        "sqrt",
    ]
    scalar: FiniteNumber | None = None
    output_field_id: FieldId
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]

    @model_validator(mode="after")
    def operands_match_operator(self) -> DeriveColumnOperation:
        unary = self.operator in {"absolute", "negate", "log10", "ln", "sqrt"}
        if unary and (len(self.input_field_ids) != 1 or self.scalar is not None):
            raise ValueError("unary derivation requires exactly one field")
        if not unary:
            fields = len(self.input_field_ids) == 2 and self.scalar is None
            field_scalar = len(self.input_field_ids) == 1 and self.scalar is not None
            if not (fields or field_scalar):
                raise ValueError("binary derivation requires two fields or one field and scalar")
        if self.output_field_id in self.input_field_ids:
            raise ValueError("derived output must use a new field identity")
        return self


class ConvertUnitOperation(StrictModel):
    kind: Literal["convert_unit"] = "convert_unit"
    input_handle_id: DataViewHandleId
    field_id: FieldId
    target_unit: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    output_field_id: FieldId
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]

    @model_validator(mode="after")
    def conversion_creates_a_field(self) -> ConvertUnitOperation:
        if self.output_field_id == self.field_id:
            raise ValueError("unit conversion must create a new field identity")
        return self


class ReshapeWideToLongOperation(StrictModel):
    kind: Literal["reshape_wide_to_long"] = "reshape_wide_to_long"
    input_handle_id: DataViewHandleId
    id_field_ids: Annotated[tuple[FieldId, ...], Field(max_length=8)] = ()
    value_field_ids: Annotated[tuple[FieldId, ...], Field(min_length=2, max_length=64)]
    output_name_field_id: FieldId
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    output_value_field_id: FieldId
    output_value_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=256, strict=True),
    ]

    @model_validator(mode="after")
    def reshape_fields_are_distinct(self) -> ReshapeWideToLongOperation:
        inputs = (*self.id_field_ids, *self.value_field_ids)
        outputs = (self.output_name_field_id, self.output_value_field_id)
        if len(inputs) != len(set(inputs)):
            raise ValueError("wide-to-long input fields must be unique")
        if len(outputs) != len(set(outputs)) or set(inputs) & set(outputs):
            raise ValueError("wide-to-long output fields must be new and distinct")
        return self


class LongToWideOutput(StrictModel):
    value: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    field_id: FieldId
    name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]


class ReshapeLongToWideOperation(StrictModel):
    kind: Literal["reshape_long_to_wide"] = "reshape_long_to_wide"
    input_handle_id: DataViewHandleId
    index_field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1, max_length=8)]
    name_field_id: FieldId
    value_field_id: FieldId
    outputs: Annotated[tuple[LongToWideOutput, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def outputs_are_unique(self) -> ReshapeLongToWideOperation:
        inputs = (*self.index_field_ids, self.name_field_id, self.value_field_id)
        if len(inputs) != len(set(inputs)):
            raise ValueError("long-to-wide input fields must be unique")
        groups = (
            tuple(output.value for output in self.outputs),
            tuple(output.field_id for output in self.outputs),
            tuple(output.name for output in self.outputs),
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("long-to-wide output values, fields and names must be unique")
        if set(inputs) & set(groups[1]):
            raise ValueError("long-to-wide output fields must be new")
        return self


class ConcatenateOperation(StrictModel):
    kind: Literal["concatenate"] = "concatenate"
    input_handle_ids: Annotated[tuple[DataViewHandleId, ...], Field(min_length=2, max_length=8)]
    source_labels: Annotated[tuple[str, ...], Field(min_length=2, max_length=8)]
    source_label_field_id: FieldId
    source_label_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=256, strict=True),
    ] = "Source"

    @model_validator(mode="after")
    def sources_and_labels_align(self) -> ConcatenateOperation:
        if len(self.input_handle_ids) != len(set(self.input_handle_ids)):
            raise ValueError("concatenated handles must be unique")
        if len(self.input_handle_ids) != len(self.source_labels):
            raise ValueError("source labels must align with concatenated handles")
        if len(self.source_labels) != len(set(self.source_labels)):
            raise ValueError("source labels must be unique")
        return self


class DataJoinKey(StrictModel):
    left_field_id: FieldId
    right_field_id: FieldId


class KeyedJoinOperation(StrictModel):
    kind: Literal["keyed_join"] = "keyed_join"
    left_handle_id: DataViewHandleId
    right_handle_id: DataViewHandleId
    keys: Annotated[tuple[DataJoinKey, ...], Field(min_length=1, max_length=8)]
    how: Literal["inner", "left", "right"] = "inner"
    expected_relationship: Literal["one_to_one", "one_to_many", "many_to_one"]
    right_field_prefix: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,23}$", strict=True),
    ] = "right"

    @model_validator(mode="after")
    def join_handles_differ(self) -> KeyedJoinOperation:
        if self.left_handle_id == self.right_handle_id:
            raise ValueError("keyed join requires two distinct handles")
        left_fields = tuple(key.left_field_id for key in self.keys)
        right_fields = tuple(key.right_field_id for key in self.keys)
        if len(left_fields) != len(set(left_fields)) or len(right_fields) != len(set(right_fields)):
            raise ValueError("join key fields must be unique on each side")
        return self


class AggregateMetric(StrictModel):
    operator: Literal["count", "count_nonmissing", "sum", "mean", "min", "max", "median"]
    input_field_id: FieldId | None = None
    output_field_id: FieldId
    output_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]

    @model_validator(mode="after")
    def input_matches_operator(self) -> AggregateMetric:
        if self.operator == "count" and self.input_field_id is not None:
            raise ValueError("row count does not accept an input field")
        if self.operator != "count" and self.input_field_id is None:
            raise ValueError("aggregate metric requires an input field")
        return self


class AggregateOperation(StrictModel):
    kind: Literal["aggregate"] = "aggregate"
    input_handle_id: DataViewHandleId
    group_field_ids: Annotated[tuple[FieldId, ...], Field(max_length=8)] = ()
    metrics: Annotated[tuple[AggregateMetric, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def aggregate_outputs_are_unique(self) -> AggregateOperation:
        fields = (*self.group_field_ids, *(metric.output_field_id for metric in self.metrics))
        if len(fields) != len(set(fields)):
            raise ValueError("aggregate input groups and outputs must be unique")
        return self


DataViewOperation = Annotated[
    SelectFieldsOperation
    | RenameFieldOperation
    | ConvertTypeOperation
    | FilterRowsOperation
    | SortRowsOperation
    | DeduplicateRowsOperation
    | DeriveColumnOperation
    | ConvertUnitOperation
    | ReshapeWideToLongOperation
    | ReshapeLongToWideOperation
    | ConcatenateOperation
    | KeyedJoinOperation
    | AggregateOperation,
    Field(discriminator="kind"),
]


def operation_input_handles(operation: DataViewOperation) -> tuple[DataViewHandleId, ...]:
    if isinstance(operation, ConcatenateOperation):
        return operation.input_handle_ids
    if isinstance(operation, KeyedJoinOperation):
        return (operation.left_handle_id, operation.right_handle_id)
    return (operation.input_handle_id,)
