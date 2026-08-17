"""P0 ToolGateway adapters over the existing bounded inspection service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal, cast

from pydantic import BaseModel, Field

from plotagent.contracts.agent_tasks import TaskState
from plotagent.contracts.agent_tools import ToolProvenance
from plotagent.contracts.base import StrictModel
from plotagent.contracts.workflows import (
    FieldProfile,
    InstrumentMetadata,
    RowPage,
    SchemaComparison,
    SourceInspection,
    SourceList,
    ValueSearchResult,
    WorkflowAlias,
    WorkflowScalar,
)
from plotagent.tooling.gateway import (
    ToolExecutionOutput,
    ToolExecutionProblem,
    ToolGateway,
    ToolHandler,
)
from plotagent.workflows.inspection import DataInspectionService, InspectionError

_READ_STATES: tuple[TaskState, ...] = ("created", "investigating", "repairing")


class ListSourcesInput(StrictModel):
    pass


class InspectSourceInput(StrictModel):
    source_alias: WorkflowAlias


class PreviewRowsInput(StrictModel):
    source_alias: WorkflowAlias
    field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=1, max_length=24)]
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=40)] = 5


class SampleRowsInput(StrictModel):
    source_alias: WorkflowAlias
    field_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=1, max_length=24)]
    limit: Annotated[int, Field(ge=1, le=40)] = 5


class ProfileFieldInput(StrictModel):
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias


class SearchValuesInput(StrictModel):
    source_alias: WorkflowAlias
    field_alias: WorkflowAlias
    mode: Literal["equal", "contains", "prefix"]
    query: WorkflowScalar
    limit: Annotated[int, Field(ge=1, le=40)] = 20


class CompareSchemasInput(StrictModel):
    source_aliases: Annotated[tuple[WorkflowAlias, ...], Field(min_length=2, max_length=8)]


class InspectInstrumentMetadataInput(StrictModel):
    source_alias: WorkflowAlias


def _inspection_problem(error: InspectionError) -> ToolExecutionProblem:
    if error.code == "INSPECTION_SOURCE_REQUIRED":
        return ToolExecutionProblem(
            code=error.code,
            category="USER_INPUT_REQUIRED",
            message=error.message,
            retryable=False,
            requires_user=True,
            repair_hint="Ask the user to upload or select a data source.",
        )
    if error.code == "INSPECTION_BUDGET_EXCEEDED":
        return ToolExecutionProblem(
            code=error.code,
            category="FATAL",
            message=error.message,
            retryable=False,
            requires_user=False,
        )
    return ToolExecutionProblem(
        code=error.code,
        category="AGENT_REPAIRABLE",
        message=error.message,
        retryable=True,
        requires_user=False,
        repair_hint="Use exposed source and field aliases, then retry within the published bounds.",
    )


def _handler(
    service: DataInspectionService,
    execute: Callable[[BaseModel], BaseModel],
) -> ToolHandler:
    def run(input_model: BaseModel) -> ToolExecutionOutput:
        try:
            payload = execute(input_model)
        except InspectionError as error:
            raise _inspection_problem(error) from error
        audit = service.audits[-1]
        by_alias = {source.source_alias: source for source in service.context.sources}
        provenance = tuple(
            ToolProvenance(
                source_id=by_alias[source_alias].source_dataset_id,
                source_version=by_alias[source_alias].source_version,
                content_hash=by_alias[source_alias].content_hash,
                coordinate=source_alias,
            )
            for source_alias in audit.source_aliases
        )
        return ToolExecutionOutput(
            payload=payload,
            summary=(
                f"{audit.tool_name} inspected {len(audit.source_aliases)} authorized source(s)."
            ),
            provenance=provenance,
            side_effect="none",
            disclosed_field_count=audit.disclosed_field_count,
            disclosed_row_count=audit.disclosed_row_count,
            disclosed_scalar_count=audit.disclosed_scalar_count,
        )

    return run


def register_inspection_tools(
    gateway: ToolGateway,
    service: DataInspectionService,
) -> tuple[str, ...]:
    """Bind the stateful legacy inspection implementation to v2 P0 contracts."""

    registrations: tuple[
        tuple[
            str,
            str,
            str,
            type[BaseModel],
            type[BaseModel],
            int,
            Callable[[BaseModel], BaseModel],
        ],
        ...,
    ] = (
        (
            "tool:list_sources",
            "list_sources",
            "List the authorized source tables without disclosing cell values.",
            ListSourcesInput,
            SourceList,
            0,
            lambda _input: service.list_sources(),
        ),
        (
            "tool:inspect_source",
            "inspect_source",
            "Inspect one authorized source schema and row count without modifying it.",
            InspectSourceInput,
            SourceInspection,
            0,
            lambda item: service.inspect_source(cast(InspectSourceInput, item).source_alias),
        ),
        (
            "tool:preview_rows",
            "preview_rows",
            "Read one bounded, contiguous page from explicitly selected source fields.",
            PreviewRowsInput,
            RowPage,
            960,
            lambda item: service.preview_rows(
                cast(PreviewRowsInput, item).source_alias,
                cast(PreviewRowsInput, item).field_aliases,
                offset=cast(PreviewRowsInput, item).offset,
                limit=cast(PreviewRowsInput, item).limit,
            ),
        ),
        (
            "tool:sample_rows",
            "sample_rows",
            "Read an evenly spaced bounded sample from explicitly selected source fields.",
            SampleRowsInput,
            RowPage,
            960,
            lambda item: service.sample_rows(
                cast(SampleRowsInput, item).source_alias,
                cast(SampleRowsInput, item).field_aliases,
                limit=cast(SampleRowsInput, item).limit,
            ),
        ),
        (
            "tool:profile_field",
            "profile_field",
            "Profile one authorized field with bounded examples and numeric range facts.",
            ProfileFieldInput,
            FieldProfile,
            8,
            lambda item: service.profile_field(
                cast(ProfileFieldInput, item).source_alias,
                cast(ProfileFieldInput, item).field_alias,
            ),
        ),
        (
            "tool:search_values",
            "search_values",
            "Search one authorized field with an exact, contains, or prefix predicate.",
            SearchValuesInput,
            ValueSearchResult,
            40,
            lambda item: service.search_values(
                cast(SearchValuesInput, item).source_alias,
                cast(SearchValuesInput, item).field_alias,
                mode=cast(SearchValuesInput, item).mode,
                query=cast(SearchValuesInput, item).query,
                limit=cast(SearchValuesInput, item).limit,
            ),
        ),
        (
            "tool:compare_schemas",
            "compare_schemas",
            "Compare the field-name structure of two to eight authorized sources.",
            CompareSchemasInput,
            SchemaComparison,
            0,
            lambda item: service.compare_schemas(
                cast(CompareSchemasInput, item).source_aliases
            ),
        ),
        (
            "tool:inspect_instrument_metadata",
            "inspect_instrument_metadata",
            "Read bounded instrument metadata attached to one authorized source.",
            InspectInstrumentMetadataInput,
            InstrumentMetadata,
            2_000,
            lambda item: service.inspect_instrument_metadata(
                cast(InspectInstrumentMetadataInput, item).source_alias
            ),
        ),
    )
    names: list[str] = []
    for (
        contract_id,
        tool_name,
        description,
        input_model,
        output_model,
        max_disclosed_scalars,
        execute,
    ) in registrations:
        gateway.register(
            contract_id=contract_id,
            contract_version=1,
            tool_name=tool_name,
            description=description,
            permission_phase="p0_read",
            side_effect="none",
            allowed_task_states=_READ_STATES,
            input_model=input_model,
            output_model=output_model,
            cost_class="cheap",
            timeout_ms=10_000,
            max_disclosed_scalars=max_disclosed_scalars,
            uses_origin=False,
            handler=_handler(service, execute),
        )
        names.append(tool_name)
    return tuple(names)
