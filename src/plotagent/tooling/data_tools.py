"""P0/P1 Agent tools for immutable, task-scoped staged data."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import BaseModel, Field

from plotagent.contracts.agent_data import (
    DataViewHandle,
    DataViewHandleId,
    DataViewOperation,
    DataViewPreview,
)
from plotagent.contracts.agent_tasks import SideEffectReceipt, TaskId, TaskItemIdV2, TaskState
from plotagent.contracts.agent_tools import ToolProvenance
from plotagent.contracts.base import FieldId, StrictModel
from plotagent.engine.contracts import EngineDataRef
from plotagent.engine.ports import EngineDataProvider
from plotagent.tooling.data_workspace import StagedDataWorkspace
from plotagent.tooling.data_workspace_ops import DataWorkspaceError
from plotagent.tooling.gateway import (
    ToolExecutionOutput,
    ToolExecutionProblem,
    ToolGateway,
    ToolHandler,
)

_DATA_STATES: tuple[TaskState, ...] = ("created", "investigating", "repairing")


class StageSourceDataInput(StrictModel):
    source: EngineDataRef
    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1, max_length=128)]


class ApplyDataViewOperationInput(StrictModel):
    operation: DataViewOperation


class InspectDataViewInput(StrictModel):
    handle_id: DataViewHandleId


class PreviewDataViewInput(StrictModel):
    handle_id: DataViewHandleId
    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1, max_length=24)]
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=40)] = 5


class DataWorkspaceToolService:
    """Activation-scoped authority over one task's selected immutable sources."""

    def __init__(
        self,
        *,
        workspace: StagedDataWorkspace,
        provider: EngineDataProvider,
        task_id: TaskId,
        task_version: int,
        allowed_sources: tuple[EngineDataRef, ...],
        item_id: TaskItemIdV2 | None = None,
    ) -> None:
        if any(source.kind != "source" for source in allowed_sources):
            raise ValueError("data workspace tools accept only source authorities")
        identities = tuple(
            (source.dataset_id, source.version, source.content_hash) for source in allowed_sources
        )
        if len(identities) != len(set(identities)):
            raise ValueError("authorized data sources must be unique")
        self.workspace = workspace
        self.provider = provider
        self.task_id = task_id
        self.task_version = task_version
        self.allowed_sources = allowed_sources
        self.item_id = item_id

    def stage_source(self, item: StageSourceDataInput) -> ToolExecutionOutput:
        if item.source not in self.allowed_sources:
            raise ToolExecutionProblem(
                code="DATA_SOURCE_NOT_AUTHORIZED",
                category="FATAL",
                message="The source revision is outside this task's selected data.",
                retryable=False,
                requires_user=False,
            )
        try:
            handle = self.workspace.stage_source(
                task_id=self.task_id,
                task_version=self.task_version,
                item_id=self.item_id,
                source=item.source,
                field_ids=item.field_ids,
                provider=self.provider,
            )
        except DataWorkspaceError as error:
            raise _workspace_problem(error) from error
        return _staged_output(handle, "Staged one immutable source view.")

    def apply(self, item: ApplyDataViewOperationInput) -> ToolExecutionOutput:
        try:
            handle = self.workspace.apply(
                task_id=self.task_id,
                task_version=self.task_version,
                item_id=self.item_id,
                operation=item.operation,
            )
        except DataWorkspaceError as error:
            raise _workspace_problem(error) from error
        return _staged_output(
            handle,
            f"Applied {item.operation.kind} to immutable staged data.",
        )

    def inspect(self, item: InspectDataViewInput) -> ToolExecutionOutput:
        try:
            handle = self.workspace.inspect(
                item.handle_id,
                task_id=self.task_id,
                task_version=self.task_version,
                item_id=self.item_id,
            )
        except DataWorkspaceError as error:
            raise _workspace_problem(error) from error
        return ToolExecutionOutput(
            payload=handle,
            summary="Inspected one staged data handle without disclosing row values.",
            output_handle=handle.handle_id,
            provenance=_provenance(handle),
            side_effect="none",
            disclosed_field_count=len(handle.fields),
        )

    def preview(self, item: PreviewDataViewInput) -> ToolExecutionOutput:
        try:
            preview = self.workspace.preview(
                item.handle_id,
                task_id=self.task_id,
                task_version=self.task_version,
                item_id=self.item_id,
                field_ids=item.field_ids,
                offset=item.offset,
                limit=item.limit,
            )
        except DataWorkspaceError as error:
            raise _workspace_problem(error) from error
        return ToolExecutionOutput(
            payload=preview,
            summary=f"Previewed {len(preview.rows)} bounded staged data row(s).",
            output_handle=preview.handle.handle_id,
            provenance=_provenance(preview.handle),
            side_effect="none",
            disclosed_field_count=len(preview.field_ids),
            disclosed_row_count=len(preview.rows),
            disclosed_scalar_count=len(preview.field_ids) * len(preview.rows),
        )


def _workspace_problem(error: DataWorkspaceError) -> ToolExecutionProblem:
    fatal = error.code in {
        "DATA_HANDLE_CORRUPT",
        "DATA_HANDLE_IDEMPOTENCY_CONFLICT",
        "DATA_SOURCE_NOT_AUTHORIZED",
        "DATA_SOURCE_IDENTITY_MISMATCH",
        "DATA_SOURCE_MATERIALIZATION_INVALID",
        "DATA_WORKSPACE_CLOSED",
        "DATA_WORKSPACE_THREAD_INVALID",
    }
    return ToolExecutionProblem(
        code=error.code,
        category="FATAL" if fatal else "AGENT_REPAIRABLE",
        message=error.message,
        retryable=not fatal,
        requires_user=False,
        repair_hint=(
            None
            if fatal
            else "Inspect the current handle fields and lineage, then correct the operation."
        ),
    )


def _provenance(handle: DataViewHandle) -> tuple[ToolProvenance, ...]:
    return tuple(
        ToolProvenance(
            source_id=source.dataset_id,
            source_version=source.version,
            content_hash=source.content_hash,
            coordinate=handle.handle_id,
        )
        for source in handle.root_sources
    )


def _staged_output(handle: DataViewHandle, summary: str) -> ToolExecutionOutput:
    return ToolExecutionOutput(
        payload=handle,
        summary=summary,
        output_handle=handle.handle_id,
        provenance=_provenance(handle),
        side_effect="staged",
        side_effects=(
            SideEffectReceipt(
                effect_kind="staged_data_view",
                object_id=handle.handle_id,
                object_version=handle.handle_version,
                artifact_hash=handle.artifact_hash,
            ),
        ),
        disclosed_field_count=len(handle.fields),
    )


def register_data_workspace_tools(
    gateway: ToolGateway,
    service: DataWorkspaceToolService,
) -> tuple[str, ...]:
    registrations: tuple[
        tuple[
            str,
            str,
            str,
            str,
            type[BaseModel],
            type[BaseModel],
            int,
        ],
        ...,
    ] = (
        (
            "tool:stage_source_data",
            "stage_source_data",
            "Create an immutable task-scoped handle for explicitly selected source fields.",
            "stage_source",
            StageSourceDataInput,
            DataViewHandle,
            0,
        ),
        (
            "tool:apply_data_view_operation",
            "apply_data_view_operation",
            "Apply one typed deterministic operation and return a new immutable data handle.",
            "apply",
            ApplyDataViewOperationInput,
            DataViewHandle,
            0,
        ),
        (
            "tool:inspect_data_view",
            "inspect_data_view",
            "Inspect staged fields, lineage and provenance without reading row values.",
            "inspect",
            InspectDataViewInput,
            DataViewHandle,
            0,
        ),
        (
            "tool:preview_data_view",
            "preview_data_view",
            "Read a bounded page from explicitly selected staged fields.",
            "preview",
            PreviewDataViewInput,
            DataViewPreview,
            960,
        ),
    )
    names: list[str] = []
    for (
        contract_id,
        tool_name,
        description,
        handler_name,
        input_model,
        output_model,
        disclosed,
    ) in registrations:
        staged = tool_name in {"stage_source_data", "apply_data_view_operation"}
        gateway.register(
            contract_id=contract_id,
            contract_version=1,
            tool_name=tool_name,
            description=description,
            permission_phase="p1_staged" if staged else "p0_read",
            side_effect="staged" if staged else "none",
            allowed_task_states=_DATA_STATES,
            input_model=input_model,
            output_model=output_model,
            cost_class="moderate" if staged else "cheap",
            timeout_ms=30_000 if staged else 10_000,
            max_disclosed_scalars=disclosed,
            uses_origin=False,
            handler=cast(ToolHandler, getattr(service, handler_name)),
        )
        names.append(tool_name)
    return tuple(names)
