"""Strict protocol boundary for importing while the W0 contracts package is absent."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type Scalar = str | int | float | bool | date | datetime | None
type TraceDetail = str | int | bool


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TraceEvent(StrictModel):
    stage: Literal["sniff", "detect", "parse", "validate", "serialize", "commit"]
    code: str
    details: dict[str, TraceDetail] = Field(default_factory=dict)


class UnitSuggestion(StrictModel):
    source_text: str
    canonical_unit: str | None = None
    dimensionality: str | None = None
    kind: Literal["recognized", "opaque"] = "opaque"
    registry_version: str = "units-v1"


class FieldQuality(StrictModel):
    field_id: str
    missing_count: int = 0
    nan_count: int = 0
    positive_inf_count: int = 0
    negative_inf_count: int = 0


class FieldSchema(StrictModel):
    field_id: str
    source_name: str
    normalized_name: str
    logical_type: Literal["numeric", "boolean", "datetime", "text", "mixed"]
    physical_types: tuple[str, ...]
    numeric_precision: Literal["integer", "binary64"] | None = None
    unit: UnitSuggestion | None = None


class SourceCoordinate(StrictModel):
    source_row_id: str
    source_row: int
    workbook: str | None = None
    sheet: str | None = None
    cell_range: str | None = None
    block: str | None = None
    channel: str | None = None
    sweep: str | None = None
    line: int | None = None
    byte_start: int | None = None
    byte_end: int | None = None


class ProvenanceMarker(StrictModel):
    kind: Literal["cached_formula_value", "formula_uncached", "macro_ignored", "external_link"]
    coordinate: str


class QualitySummary(StrictModel):
    row_count: int
    column_count: int
    missing_count: int
    nan_count: int
    positive_inf_count: int
    negative_inf_count: int
    unparseable_count: int
    duplicate_headers: tuple[str, ...] = ()
    fields: tuple[FieldQuality, ...] = ()


class ImportRecipe(StrictModel):
    schema_version: Literal["import-recipe-v1"] = "import-recipe-v1"
    parser_name: Literal["plotagent-text", "openpyxl", "xlrd"]
    parser_version: str
    source_format: Literal["csv", "tsv", "txt", "dat", "xlsx", "xlsm", "xls"]
    encoding: str | None = None
    delimiter: str | None = None
    decimal_mark: Literal[".", ","] | None = None
    header_row: int | None = None
    data_start_row: int
    data_end_row: int
    preamble_start_line: int | None = None
    preamble_end_line: int | None = None
    postamble_start_line: int | None = None
    postamble_end_line: int | None = None
    workbook: str | None = None
    sheet: str | None = None
    cell_range: str | None = None
    block: str | None = None
    column_names: tuple[str, ...]
    unicode_normalization_version: Literal["NFC-v1"] = "NFC-v1"


class DatasetCandidate(StrictModel):
    candidate_id: str
    display_name: str
    source_object_hash: str
    recipe: ImportRecipe
    fields: tuple[FieldSchema, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    coordinates: tuple[SourceCoordinate, ...]
    instrument_metadata: dict[str, str] = Field(default_factory=dict)
    postamble: tuple[str, ...] = ()
    quality: QualitySummary
    provenance: tuple[ProvenanceMarker, ...] = ()
    trace: tuple[TraceEvent, ...]


class ClarificationOption(StrictModel):
    value: str
    label: str


class Imported(StrictModel):
    kind: Literal["imported"] = "imported"
    source_object_hash: str
    candidates: tuple[DatasetCandidate, ...]
    trace: tuple[TraceEvent, ...]


class Clarification(StrictModel):
    kind: Literal["clarification"] = "clarification"
    code: str
    question: str
    options: tuple[ClarificationOption, ...]
    trace: tuple[TraceEvent, ...]


class Rejection(StrictModel):
    kind: Literal["rejection"] = "rejection"
    code: str
    message: str
    remediation: str
    trace: tuple[TraceEvent, ...]


type ImportResponse = Annotated[
    Imported | Clarification | Rejection,
    Field(discriminator="kind"),
]
