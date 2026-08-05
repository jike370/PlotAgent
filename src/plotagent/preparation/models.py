"""Strict closed-union models for FieldMapping and PreparationSpec."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from plotagent.importing.models import FieldSchema, Scalar, SourceCoordinate


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingAssignment(StrictModel):
    role: str
    field_id: str
    semantic: str


class FieldMapping(StrictModel):
    schema_version: Literal["field-mapping-v1"] = "field-mapping-v1"
    mapping_id: str
    assignments: tuple[MappingAssignment, ...]


class SelectFieldsSpec(StrictModel):
    kind: Literal["select_fields"] = "select_fields"
    field_ids: tuple[str, ...]


class ProjectStructureSpec(StrictModel):
    kind: Literal["project_structure"] = "project_structure"
    orientation: Literal["identity", "wide_to_long"]
    field_ids: tuple[str, ...]
    index_field_id: str | None = None
    value_field_ids: tuple[str, ...] = ()
    variable_field_name: str = "variable"
    value_field_name: str = "value"


class IsomorphicConcatSpec(StrictModel):
    kind: Literal["isomorphic_concat"] = "isomorphic_concat"
    source_label_field: Literal["source_sheet", "source_block"]


class ProjectMetadataLabelSpec(StrictModel):
    kind: Literal["project_metadata_label"] = "project_metadata_label"
    metadata_key: str
    output_field_name: str


class ApplyPlotOrderSpec(StrictModel):
    kind: Literal["apply_plot_order"] = "apply_plot_order"
    field_id: str
    ordered_values: tuple[Scalar, ...]


class MaskForPlotSpec(StrictModel):
    kind: Literal["mask_for_plot"] = "mask_for_plot"
    field_ids: tuple[str, ...]
    missing_policy: Literal["fail", "exclude_with_report"]


type PreparationSpec = Annotated[
    SelectFieldsSpec
    | ProjectStructureSpec
    | IsomorphicConcatSpec
    | ProjectMetadataLabelSpec
    | ApplyPlotOrderSpec
    | MaskForPlotSpec,
    Field(discriminator="kind"),
]
PREPARATION_SPEC_ADAPTER: TypeAdapter[PreparationSpec] = TypeAdapter(PreparationSpec)


class RowExclusion(StrictModel):
    row_index: int
    source_row_id: str
    reasons: tuple[str, ...]


class PreparedDataset(StrictModel):
    schema_version: Literal["prepared-dataset-v1"] = "prepared-dataset-v1"
    prepared_dataset_id: str
    source_dataset_ids: tuple[str, ...]
    field_mapping: FieldMapping
    preparation_spec: PreparationSpec
    compiler_version: Literal["preparation-compiler-v1"] = "preparation-compiler-v1"
    fields: tuple[FieldSchema, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    coordinates: tuple[SourceCoordinate, ...]
    row_mask: tuple[bool, ...]
    exclusions: tuple[RowExclusion, ...] = ()
    included_count: int
    excluded_count: int
    plot_order: tuple[Scalar, ...] = ()
    input_hash: str
    output_hash: str
    semantic_signature: str
