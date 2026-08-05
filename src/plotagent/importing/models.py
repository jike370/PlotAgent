"""Import-only envelopes around the authoritative W0 SourceDataset contract."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from plotagent.contracts.datasets import SourceCoordinate, SourceDataset

type Scalar = str | int | float | bool | date | datetime | None
type TraceDetail = str | int | bool


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TraceEvent(StrictModel):
    stage: Literal["sniff", "detect", "parse", "validate", "serialize", "commit"]
    code: str
    details: dict[str, TraceDetail] = Field(default_factory=dict)


class ProvenanceMarker(StrictModel):
    kind: Literal["cached_formula_value", "formula_uncached", "macro_ignored", "external_link"]
    coordinate: str


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


class SourceDatasetArtifact(StrictModel):
    """A contract SourceDataset plus non-authoritative in-memory import artifacts."""

    display_name: str
    source_dataset: SourceDataset
    recipe: ImportRecipe
    rows: tuple[tuple[Scalar, ...], ...]
    coordinates: tuple[SourceCoordinate, ...]
    instrument_metadata: dict[str, str] = Field(default_factory=dict)
    postamble: tuple[str, ...] = ()
    provenance: tuple[ProvenanceMarker, ...] = ()
    parquet_bytes: bytes
    trace: tuple[TraceEvent, ...]


class ClarificationOption(StrictModel):
    value: str
    label: str


class Imported(StrictModel):
    kind: Literal["imported"] = "imported"
    source_object_hash: str
    sources: tuple[SourceDatasetArtifact, ...]
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
