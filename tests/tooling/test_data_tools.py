from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from plotagent.contracts.agent_data import DataViewHandle, RenameFieldOperation
from plotagent.contracts.agent_tasks import (
    ActivationBudget,
    AgentActivation,
    TaskBudgetLimits,
    TaskBudgetSnapshot,
    TaskCheckpoint,
)
from plotagent.contracts.agent_tools import ToolInvocation
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import EngineColumn, EngineDataRef, EngineDataView, EngineField
from plotagent.storage.project import ProjectStore
from plotagent.tooling import (
    DataWorkspaceToolService,
    StagedDataWorkspace,
    ToolGateway,
    register_data_workspace_tools,
)

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
NOW_TEXT = "2026-08-18T10:00:00Z"
HASH_A = "a" * 64
HASH_B = "b" * 64
TOOLS = (
    "stage_source_data",
    "apply_data_view_operation",
    "inspect_data_view",
    "preview_data_view",
)


class Provider:
    def __init__(self, source_view: EngineDataView) -> None:
        self.source_view = source_view

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[str, ...],
    ) -> EngineDataView:
        assert data == self.source_view.data
        by_id = {column.field.field_id: column for column in self.source_view.columns}
        return self.source_view.model_copy(
            update={"columns": tuple(by_id[field_id] for field_id in field_ids)}
        )


def source_view() -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="source",
            dataset_id="source:test",
            version=1,
            content_hash=HASH_A,
        ),
        row_ids=("row:1", "row:2", "row:3"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:x",
                    name="Time",
                    logical_type="numeric",
                    unit_label="s",
                ),
                values=(1.0, 2.0, 3.0),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:y",
                    name="Response",
                    logical_type="numeric",
                    unit_label="mV",
                ),
                values=(4.0, 5.0, 6.0),
            ),
        ),
    )


def activation() -> AgentActivation:
    return AgentActivation(
        activation_id="activation:data",
        task_id="task:data",
        task_version=1,
        reason="new_task",
        task_state="created",
        original_instruction="Prepare the selected source for plotting.",
        allowed_tools=TOOLS,
        permission_phase="p1_staged",
        activation_budget=ActivationBudget(
            max_tool_calls=20,
            max_disclosed_scalars=100,
        ),
        task_budget=TaskBudgetSnapshot(
            limits=TaskBudgetLimits(
                max_tool_calls=20,
                max_disclosed_scalars=100,
            )
        ),
        deadline="2026-08-18T10:01:00Z",
        created_at=NOW_TEXT,
    )


def checkpoint(current: AgentActivation) -> TaskCheckpoint:
    return TaskCheckpoint(
        checkpoint_id="checkpoint:data",
        task_id=current.task_id,
        task_version=current.task_version,
        state=current.task_state,
        project_revision=0,
        last_event_sequence=1,
        active_activation_id=current.activation_id,
        budget=current.task_budget,
        updated_at=NOW_TEXT,
        content_hash=HASH_A,
    )


def invocation(
    tool_name: str,
    arguments: JsonValue,
    *,
    phase: str,
    sequence: int,
) -> ToolInvocation:
    staged = phase == "p1_staged"
    return ToolInvocation(
        tool_call_id=f"toolcall:{tool_name}.{sequence}",
        task_id="task:data",
        task_version=1,
        activation_id="activation:data",
        tool_name=tool_name,
        permission_phase=phase,  # type: ignore[arg-type]
        idempotency_key=f"idem:{tool_name}.{sequence}" if staged else None,
        arguments_hash=canonical_hash(arguments),
        activation_tool_calls_before=sequence - 1,
        activation_disclosed_scalars_before=0,
        expected_project_revision=0,
        deadline=("2026-08-18T10:00:30Z" if staged else "2026-08-18T10:00:10Z"),
    )


def invoke(
    gateway: ToolGateway,
    current: AgentActivation,
    current_checkpoint: TaskCheckpoint,
    *,
    tool_name: str,
    arguments: JsonValue,
    phase: str,
    sequence: int,
):
    call = invocation(tool_name, arguments, phase=phase, sequence=sequence)
    result = gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=current,
        checkpoint=current_checkpoint,
    )
    return call, result


def test_data_tools_stage_transform_inspect_and_preview_through_gateway(
    tmp_path: Path,
) -> None:
    source = source_view()
    current = activation()
    current_checkpoint = checkpoint(current)
    with (
        ProjectStore.create(tmp_path / "project", project_id="project:test") as project,
        StagedDataWorkspace(project, clock=lambda: NOW) as workspace,
    ):
        service = DataWorkspaceToolService(
            workspace=workspace,
            provider=Provider(source),
            task_id=current.task_id,
            task_version=current.task_version,
            allowed_sources=(source.data,),
        )
        gateway = ToolGateway(clock=lambda: NOW)
        assert register_data_workspace_tools(gateway, service) == TOOLS

        stage_arguments: JsonValue = {
            "source": source.data.model_dump(mode="json"),
            "field_ids": ["field:x", "field:y"],
        }
        stage_call, staged = invoke(
            gateway,
            current,
            current_checkpoint,
            tool_name="stage_source_data",
            arguments=stage_arguments,
            phase="p1_staged",
            sequence=1,
        )
        assert staged.status == "succeeded", staged
        assert staged.side_effect == "staged"
        assert len(staged.side_effects) == 1
        assert staged.side_effects[0].effect_kind == "staged_data_view"
        staged_handle = DataViewHandle.model_validate_json(json.dumps(staged.payload))

        operation = RenameFieldOperation(
            input_handle_id=staged_handle.handle_id,
            field_id="field:y",
            output_name="Signal",
        )
        _apply_call, applied = invoke(
            gateway,
            current,
            current_checkpoint,
            tool_name="apply_data_view_operation",
            arguments={"operation": operation.model_dump(mode="json")},
            phase="p1_staged",
            sequence=2,
        )
        assert applied.status == "succeeded", applied
        applied_handle = DataViewHandle.model_validate_json(json.dumps(applied.payload))
        assert tuple(field.name for field in applied_handle.fields) == ("Time", "Signal")
        assert applied_handle.parent_handle_ids == (staged_handle.handle_id,)

        _inspect_call, inspected = invoke(
            gateway,
            current,
            current_checkpoint,
            tool_name="inspect_data_view",
            arguments={"handle_id": applied_handle.handle_id},
            phase="p0_read",
            sequence=3,
        )
        assert inspected.status == "succeeded", inspected
        assert inspected.side_effect == "none"
        assert inspected.disclosed_scalar_count == 0

        _preview_call, previewed = invoke(
            gateway,
            current,
            current_checkpoint,
            tool_name="preview_data_view",
            arguments={
                "handle_id": applied_handle.handle_id,
                "field_ids": ["field:y"],
                "offset": 1,
                "limit": 2,
            },
            phase="p0_read",
            sequence=4,
        )
        assert previewed.status == "succeeded", previewed
        assert previewed.payload is not None
        assert previewed.payload["rows"] == [[5.0], [6.0]]
        assert previewed.disclosed_row_count == 2
        assert previewed.disclosed_scalar_count == 2
        assert previewed.provenance[0].source_id == source.data.dataset_id

        receipt = gateway.build_receipt(
            invocation=stage_call,
            result=staged,
            checkpoint=current_checkpoint,
        )
        assert receipt.permission_phase == "p1_staged"
        assert receipt.project_revision_after == receipt.project_revision_before
        assert receipt.side_effects == staged.side_effects


def test_data_tools_reject_sources_outside_task_authority(tmp_path: Path) -> None:
    source = source_view()
    current = activation()
    current_checkpoint = checkpoint(current)
    with (
        ProjectStore.create(tmp_path / "project", project_id="project:test") as project,
        StagedDataWorkspace(project, clock=lambda: NOW) as workspace,
    ):
        gateway = ToolGateway(clock=lambda: NOW)
        register_data_workspace_tools(
            gateway,
            DataWorkspaceToolService(
                workspace=workspace,
                provider=Provider(source),
                task_id=current.task_id,
                task_version=current.task_version,
                allowed_sources=(source.data,),
            ),
        )
        unauthorized = source.data.model_copy(
            update={"dataset_id": "source:other", "content_hash": HASH_B}
        )
        _call, result = invoke(
            gateway,
            current,
            current_checkpoint,
            tool_name="stage_source_data",
            arguments={
                "source": unauthorized.model_dump(mode="json"),
                "field_ids": ["field:x"],
            },
            phase="p1_staged",
            sequence=1,
        )
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "DATA_SOURCE_NOT_AUTHORIZED"
        assert result.side_effect == "none"
