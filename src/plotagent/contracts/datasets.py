"""Source, field-mapping, and controlled preparation contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    SCHEMA_VERSION,
    ChartTypeId,
    ContentTableRef,
    FieldId,
    FieldMappingRef,
    MissingPolicy,
    NonNegativeInt,
    PositiveInt,
    PreparationSpecRef,
    PreparedDatasetRef,
    RowId,
    SchemaVersion,
    Sha256,
    SourceDatasetRef,
    StrictModel,
    Token,
    VersionId,
    WarningRecord,
)


class UnitSpec(StrictModel):
    source_text: Annotated[str, StringConstraints(max_length=128, strict=True)]
    canonical_unit: Token | None = None
    dimensionality: Token
    kind: Literal["recognized", "opaque", "dimensionless"]
    registry_version: Token

    @model_validator(mode="after")
    def recognized_has_unit(self) -> UnitSpec:
        if self.kind == "recognized" and self.canonical_unit is None:
            raise ValueError("recognized units require canonical_unit")
        if self.kind == "dimensionless" and self.canonical_unit is not None:
            raise ValueError("dimensionless units cannot define canonical_unit")
        return self


class ExcelSourceCoordinate(StrictModel):
    kind: Literal["excel"] = "excel"
    workbook_hash: Sha256
    sheet_name: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    cell_range: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Z]+[1-9][0-9]*:[A-Z]+[1-9][0-9]*$", strict=True),
    ]
    source_row_id: RowId


class TextSourceCoordinate(StrictModel):
    kind: Literal["text"] = "text"
    byte_start: NonNegativeInt
    byte_end: NonNegativeInt
    line_start: PositiveInt
    line_end: PositiveInt
    block: Token | None = None
    channel: Token | None = None
    sweep: Token | None = None
    source_row_id: RowId

    @model_validator(mode="after")
    def ordered_ranges(self) -> TextSourceCoordinate:
        if self.byte_end < self.byte_start or self.line_end < self.line_start:
            raise ValueError("source coordinate ranges must be ordered")
        return self


SourceCoordinate = Annotated[
    ExcelSourceCoordinate | TextSourceCoordinate,
    Field(discriminator="kind"),
]


class SourceField(StrictModel):
    field_id: FieldId
    name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    logical_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    physical_type: Token
    unit: UnitSpec
    source_column_index: NonNegativeInt
    precision_digits: NonNegativeInt | None = None


class DataQualitySummary(StrictModel):
    total_rows: NonNegativeInt
    valid_rows: NonNegativeInt
    missing_values: NonNegativeInt
    nan_values: NonNegativeInt
    positive_inf_values: NonNegativeInt
    negative_inf_values: NonNegativeInt
    unparseable_values: NonNegativeInt
    warnings: tuple[WarningRecord, ...] = ()

    @model_validator(mode="after")
    def valid_not_greater_than_total(self) -> DataQualitySummary:
        if self.valid_rows > self.total_rows:
            raise ValueError("valid_rows cannot exceed total_rows")
        return self


class SourceDataset(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    source_dataset_id: Annotated[
        str,
        StringConstraints(pattern=r"^source:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    source_version: VersionId
    source_object_hash: Sha256
    content_hash: Sha256
    import_recipe_version: Token
    parser_version: Token
    unicode_normalization_version: Token
    field_schema: Annotated[tuple[SourceField, ...], Field(min_length=1)]
    data_ref: ContentTableRef
    quality: DataQualitySummary
    source_coordinate_samples: tuple[SourceCoordinate, ...] = ()

    @model_validator(mode="after")
    def consistent_schema(self) -> SourceDataset:
        field_ids = tuple(field.field_id for field in self.field_schema)
        if len(set(field_ids)) != len(field_ids):
            raise ValueError("field_schema field ids must be unique")
        if set(field_ids) != set(self.data_ref.field_ids):
            raise ValueError("field_schema and data_ref fields must match")
        if self.quality.total_rows != self.data_ref.row_count:
            raise ValueError("quality total_rows must match data_ref row_count")
        return self


class FieldSnapshot(StrictModel):
    field_id: FieldId
    name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    logical_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    unit: UnitSpec
    source_dataset_ref: SourceDatasetRef


class FieldRoleBinding(StrictModel):
    role: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
    ]
    field: FieldSnapshot


class FieldMapping(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    field_mapping_id: Annotated[
        str,
        StringConstraints(pattern=r"^mapping:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    mapping_version: VersionId
    chart_type_id: ChartTypeId
    source_dataset_refs: Annotated[tuple[SourceDatasetRef, ...], Field(min_length=1)]
    bindings: Annotated[tuple[FieldRoleBinding, ...], Field(min_length=1)]
    content_hash: Sha256

    @model_validator(mode="after")
    def unique_roles_and_sources(self) -> FieldMapping:
        roles = tuple(binding.role for binding in self.bindings)
        if len(set(roles)) != len(roles):
            raise ValueError("field mapping roles must be unique")
        declared = set(self.source_dataset_refs)
        if any(binding.field.source_dataset_ref not in declared for binding in self.bindings):
            raise ValueError("field snapshots must reference a mapped source dataset")
        return self


class PreparationBase(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    preparation_spec_id: Annotated[
        str,
        StringConstraints(pattern=r"^preparation:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    preparation_version: VersionId
    input_refs: Annotated[tuple[SourceDatasetRef, ...], Field(min_length=1)]
    field_mapping_ref: FieldMappingRef
    compiler_version: Token


class SelectFieldsSpec(PreparationBase):
    kind: Literal["select_fields"] = "select_fields"
    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1)]


class ProjectStructureSpec(PreparationBase):
    kind: Literal["project_structure"] = "project_structure"
    input_layout: Literal["wide", "long", "matrix"]
    output_layout: Literal["wide", "long", "matrix"]
    role_fields: Annotated[tuple[FieldId, ...], Field(min_length=1)]


class IsomorphicConcatSpec(PreparationBase):
    kind: Literal["isomorphic_concat"] = "isomorphic_concat"
    source_label_kind: Literal["source_sheet", "source_block"]
    source_label_field_id: FieldId

    @model_validator(mode="after")
    def multiple_inputs(self) -> IsomorphicConcatSpec:
        if len(self.input_refs) < 2:
            raise ValueError("isomorphic_concat requires at least two inputs")
        return self


class ProjectMetadataLabelSpec(PreparationBase):
    kind: Literal["project_metadata_label"] = "project_metadata_label"
    metadata_key: Token
    output_field_id: FieldId


class ApplyPlotOrderSpec(PreparationBase):
    kind: Literal["apply_plot_order"] = "apply_plot_order"
    field_id: FieldId
    ordered_values: Annotated[tuple[str, ...], Field(min_length=1)]


class FilterRowsSpec(PreparationBase):
    """Keep a deterministic subset of rows before calculation or plotting."""

    kind: Literal["filter_rows"] = "filter_rows"
    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1)]
    missing_policy: MissingPolicy


PreparationSpec = Annotated[
    SelectFieldsSpec
    | ProjectStructureSpec
    | IsomorphicConcatSpec
    | ProjectMetadataLabelSpec
    | ApplyPlotOrderSpec
    | FilterRowsSpec,
    Field(discriminator="kind"),
]


class PreparedDatasetProvenance(StrictModel):
    source_coordinate_kinds: Annotated[tuple[Literal["excel", "text"], ...], Field(min_length=1)]
    compiler_build_hash: Sha256


class PreparedDataset(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    prepared_dataset_id: Annotated[
        str,
        StringConstraints(pattern=r"^prepared:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    prepared_version: VersionId
    source_dataset_refs: Annotated[tuple[SourceDatasetRef, ...], Field(min_length=1)]
    field_mapping_ref: FieldMappingRef
    preparation_spec_ref: PreparationSpecRef
    compiler_version: Token
    input_hash: Sha256
    output_hash: Sha256
    data_ref: ContentTableRef
    included_row_count: NonNegativeInt
    excluded_row_count: NonNegativeInt
    provenance: PreparedDatasetProvenance
    warnings: tuple[WarningRecord, ...] = ()

    @model_validator(mode="after")
    def consistent_output(self) -> PreparedDataset:
        if self.output_hash != self.data_ref.object_hash:
            raise ValueError("output_hash must match the data object hash")
        if self.included_row_count + self.excluded_row_count != self.data_ref.row_count:
            raise ValueError("included and excluded counts must match data row count")
        return self

    def as_ref(self) -> PreparedDatasetRef:
        return PreparedDatasetRef(
            prepared_dataset_id=self.prepared_dataset_id,
            prepared_version=self.prepared_version,
            content_hash=self.output_hash,
        )
