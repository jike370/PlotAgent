"""Contracts for deterministic, reusable source-file preparation.

These contracts stop at a regular, Agent-readable table.  They deliberately
cannot represent chart selection, field binding, unit conversion, plotting
parameters, renderer actions, exports, or arbitrary executable code.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import Sha256, StrictModel, Token, VersionId

DataPreparationRecipeId = Annotated[
    str,
    StringConstraints(
        pattern=r"^data-recipe:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
DataPreparationRunId = Annotated[
    str,
    StringConstraints(
        pattern=r"^data-run:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
SourceFormat = Literal["csv", "tsv", "txt", "dat", "xlsx", "xlsm", "xls"]
LogicalType = Literal["numeric", "categorical", "datetime", "boolean", "text"]


class ProbedTable(StrictModel):
    """Non-semantic structure facts observed for one candidate table."""

    table_key: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    row_count: Annotated[int, Field(ge=0)]
    column_count: Annotated[int, Field(ge=1)]
    column_names: tuple[Annotated[str, StringConstraints(max_length=256, strict=True)], ...]
    logical_types: tuple[LogicalType, ...]
    unit_labels: tuple[Annotated[str, StringConstraints(max_length=128, strict=True)] | None, ...]
    structure_hash: Sha256

    @model_validator(mode="after")
    def columns_align(self) -> ProbedTable:
        lengths = (len(self.column_names), len(self.logical_types), len(self.unit_labels))
        if lengths != (self.column_count, self.column_count, self.column_count):
            raise ValueError("probed table column metadata must align")
        return self


class SourceStructureProbe(StrictModel):
    schema_version: Literal["source-structure-probe.v1"] = "source-structure-probe.v1"
    source_object_hash: Sha256
    source_format: SourceFormat
    byte_size: Annotated[int, Field(ge=0)]
    generic_parser_outcome: Literal["imported", "clarification", "rejection"]
    generic_parser_code: Token | None = None
    tables: tuple[ProbedTable, ...] = ()
    marker_hashes: tuple[Sha256, ...] = ()
    probe_hash: Sha256


class DataPreparationMatchContract(StrictModel):
    """Strict structural preconditions; never natural-language intent."""

    source_formats: Annotated[tuple[SourceFormat, ...], Field(min_length=1)]
    table_count: Annotated[int, Field(ge=1)]
    table_structure_hashes: Annotated[tuple[Sha256, ...], Field(min_length=1)]
    required_marker_hashes: tuple[Sha256, ...] = ()
    parser_contract_version: Annotated[
        str, StringConstraints(min_length=1, max_length=64, strict=True)
    ]
    specificity: Annotated[int, Field(ge=1, le=1_000)] = 500

    @model_validator(mode="after")
    def table_contract_aligns(self) -> DataPreparationMatchContract:
        if len(self.table_structure_hashes) != self.table_count:
            raise ValueError("table structure hashes must match table_count")
        if len(self.source_formats) != len(set(self.source_formats)):
            raise ValueError("source formats must be unique")
        return self


class ParseSourceStep(StrictModel):
    """The bounded parser choice proven by a successful preparation run."""

    operation: Literal["parse_source"] = "parse_source"
    source_format: SourceFormat
    encoding: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)] | None = (
        None
    )
    delimiter: Annotated[str, StringConstraints(min_length=1, max_length=4, strict=True)] | None = (
        None
    )
    decimal_mark: Literal[".", ","] | None = None
    header_row: Annotated[int, Field(ge=0)] | None = None
    sheet: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)] | None = (
        None
    )


class DataPreparationTableContract(StrictModel):
    table_key: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    column_names: tuple[Annotated[str, StringConstraints(max_length=256, strict=True)], ...]
    logical_types: tuple[LogicalType, ...]
    unit_labels: tuple[Annotated[str, StringConstraints(max_length=128, strict=True)] | None, ...]
    minimum_rows: Annotated[int, Field(ge=0)]
    structure_hash: Sha256

    @model_validator(mode="after")
    def columns_align(self) -> DataPreparationTableContract:
        if not self.column_names:
            raise ValueError("prepared table must contain at least one column")
        if not (len(self.column_names) == len(self.logical_types) == len(self.unit_labels)):
            raise ValueError("prepared table column metadata must align")
        return self


class DataPreparationOutputContract(StrictModel):
    tables: Annotated[tuple[DataPreparationTableContract, ...], Field(min_length=1)]
    preserve_source_order: Literal[True] = True
    preserve_source_coordinates: Literal[True] = True
    allow_additional_tables: Literal[False] = False

    @model_validator(mode="after")
    def unique_table_keys(self) -> DataPreparationOutputContract:
        keys = tuple(table.table_key for table in self.tables)
        if len(keys) != len(set(keys)):
            raise ValueError("prepared table keys must be unique")
        return self


class DataPreparationRecipe(StrictModel):
    schema_version: Literal["data-preparation-recipe.v1"] = "data-preparation-recipe.v1"
    recipe_id: DataPreparationRecipeId
    recipe_version: VersionId
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    scope: Literal["personal", "project"] = "personal"
    match_contract: DataPreparationMatchContract
    steps: Annotated[tuple[ParseSourceStep, ...], Field(min_length=1, max_length=16)]
    output_contract: DataPreparationOutputContract
    created_from_run_id: DataPreparationRunId
    created_from_source_hash: Sha256

    @model_validator(mode="after")
    def single_parse_source_step(self) -> DataPreparationRecipe:
        if len(self.steps) != 1:
            raise ValueError("v1 recipes contain exactly one proven parse_source step")
        if self.steps[0].source_format not in self.match_contract.source_formats:
            raise ValueError("parse step format must be allowed by match contract")
        return self


class RecipeCandidateEvaluation(StrictModel):
    recipe_id: DataPreparationRecipeId | None = None
    recipe_version: VersionId | None = None
    candidate_kind: Literal["saved_recipe", "generic_parser"]
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]
    specificity: Annotated[int, Field(ge=0, le=1_000)]
    state: Literal["filtered", "sandbox_passed", "sandbox_failed", "selected"]
    duration_ms: Annotated[int, Field(ge=0)]
    reason_code: Token | None = None
    output_hashes: tuple[Sha256, ...] = ()

    @model_validator(mode="after")
    def saved_candidate_has_identity(self) -> RecipeCandidateEvaluation:
        if self.candidate_kind == "saved_recipe" and (
            self.recipe_id is None or self.recipe_version is None
        ):
            raise ValueError("saved recipe candidates require recipe identity")
        if self.candidate_kind == "generic_parser" and (
            self.recipe_id is not None or self.recipe_version is not None
        ):
            raise ValueError("generic parser candidate cannot carry recipe identity")
        return self


class DataPreparationRun(StrictModel):
    schema_version: Literal["data-preparation-run.v1"] = "data-preparation-run.v1"
    run_id: DataPreparationRunId
    project_id: Token
    resource_id: Token
    source_object_hash: Sha256
    probe: SourceStructureProbe
    state: Literal[
        "probing",
        "matching",
        "awaiting_recipe_selection",
        "agent_required",
        "validating",
        "committed",
        "failed",
        "cancelled",
    ]
    route: Literal["generic_parser", "saved_recipe", "agent_assisted"] | None = None
    selected_recipe_id: DataPreparationRecipeId | None = None
    selected_recipe_version: VersionId | None = None
    executed_steps: tuple[ParseSourceStep, ...] = ()
    candidates: tuple[RecipeCandidateEvaluation, ...] = ()
    output_source_ids: tuple[Token, ...] = ()
    output_content_hashes: tuple[Sha256, ...] = ()
    model_turn_count: Annotated[int, Field(ge=0, le=8)] = 0
    tool_call_count: Annotated[int, Field(ge=0, le=32)] = 0
    input_token_count: Annotated[int, Field(ge=0)] = 0
    output_token_count: Annotated[int, Field(ge=0)] = 0
    local_duration_ms: Annotated[int, Field(ge=0)] = 0
    created_at: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]
    updated_at: Annotated[str, StringConstraints(min_length=1, max_length=64, strict=True)]
    failure_code: Token | None = None
    failure_message: (
        Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)] | None
    ) = None

    @model_validator(mode="after")
    def state_metadata_aligns(self) -> DataPreparationRun:
        if (self.selected_recipe_id is None) != (self.selected_recipe_version is None):
            raise ValueError("selected recipe id and version must appear together")
        if self.route == "saved_recipe" and self.selected_recipe_id is None:
            raise ValueError("saved recipe route requires selected recipe")
        if self.state == "committed" and not self.output_source_ids:
            raise ValueError("committed preparation runs require outputs")
        if self.state == "failed" and (self.failure_code is None or self.failure_message is None):
            raise ValueError("failed preparation runs require failure metadata")
        if self.state != "failed" and (
            self.failure_code is not None or self.failure_message is not None
        ):
            raise ValueError("non-failed preparation runs cannot retain failure metadata")
        return self
