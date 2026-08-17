from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from plotagent.contracts.agent_plots import SandboxPlotHandle
from plotagent.contracts.agent_tasks import (
    ActivationBudget,
    AgentActivation,
    TaskBudgetLimits,
    TaskBudgetSnapshot,
    TaskCheckpoint,
)
from plotagent.contracts.agent_tools import ToolInvocation
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine import (
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
)
from plotagent.storage.project import ProjectStore
from plotagent.tooling import (
    SandboxPlotToolService,
    SandboxPlotWorkspace,
    StagedDataWorkspace,
    ToolGateway,
    register_sandbox_plot_tools,
)

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
NOW_TEXT = "2026-08-18T10:00:00Z"
HASH = "a" * 64
TOOLS = (
    "preview_plot",
    "preview_origin_plot",
    "apply_plot_edits",
    "apply_origin_plot_edits",
    "inspect_plot",
)


class Provider:
    def __init__(self, view: EngineDataView) -> None:
        self.view = view

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[str, ...],
    ) -> EngineDataView:
        columns = {column.field.field_id: column for column in self.view.columns}
        return self.view.model_copy(
            update={"columns": tuple(columns[field_id] for field_id in field_ids)}
        )


def source_view() -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="source",
            dataset_id="source:gateway-plot",
            version=1,
            content_hash=HASH,
        ),
        row_ids=("row:1", "row:2", "row:3"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:x",
                    name="Time",
                    logical_type="numeric",
                ),
                values=(1.0, 2.0, 3.0),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:y",
                    name="Response",
                    logical_type="numeric",
                ),
                values=(2.0, 3.0, 5.0),
            ),
        ),
    )


def activation() -> AgentActivation:
    return AgentActivation(
        activation_id="activation:plot",
        task_id="task:plot",
        task_version=1,
        reason="new_task",
        task_state="created",
        original_instruction="Create a line plot and inspect it.",
        allowed_tools=TOOLS,
        permission_phase="p1_staged",
        activation_budget=ActivationBudget(max_tool_calls=10, max_disclosed_scalars=0),
        task_budget=TaskBudgetSnapshot(
            limits=TaskBudgetLimits(max_tool_calls=10, max_disclosed_scalars=1)
        ),
        deadline="2026-08-18T10:05:00Z",
        created_at=NOW_TEXT,
    )


def checkpoint(current: AgentActivation) -> TaskCheckpoint:
    return TaskCheckpoint(
        checkpoint_id="checkpoint:plot",
        task_id=current.task_id,
        task_version=current.task_version,
        state=current.task_state,
        project_revision=0,
        last_event_sequence=1,
        active_activation_id=current.activation_id,
        budget=current.task_budget,
        updated_at=NOW_TEXT,
        content_hash=HASH,
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
    staged = phase == "p1_staged"
    call = ToolInvocation(
        tool_call_id=f"toolcall:{tool_name}.{sequence}",
        task_id=current.task_id,
        task_version=current.task_version,
        activation_id=current.activation_id,
        tool_name=tool_name,
        permission_phase=phase,  # type: ignore[arg-type]
        idempotency_key=f"idem:{tool_name}.{sequence}" if staged else None,
        arguments_hash=canonical_hash(arguments),
        activation_tool_calls_before=sequence - 1,
        activation_disclosed_scalars_before=0,
        expected_project_revision=0,
        deadline=("2026-08-18T10:01:00Z" if staged else "2026-08-18T10:00:05Z"),
    )
    return gateway.invoke(
        invocation=call,
        arguments=arguments,
        activation=current,
        checkpoint=current_checkpoint,
    )


def test_plot_tools_preview_edit_and_inspect_through_permission_gateway(
    tmp_path: Path,
) -> None:
    view = source_view()
    current = activation()
    current_checkpoint = checkpoint(current)
    with (
        ProjectStore.create(tmp_path / "project", project_id="project:test") as project,
        StagedDataWorkspace(project, clock=lambda: NOW) as data_workspace,
    ):
        data_handle = data_workspace.stage_source(
            task_id=current.task_id,
            task_version=current.task_version,
            item_id=None,
            source=view.data,
            field_ids=("field:x", "field:y"),
            provider=Provider(view),
        )
        with SandboxPlotWorkspace(
            project,
            data_workspace,
            task_id=current.task_id,
            task_version=current.task_version,
            item_id=None,
            clock=lambda: NOW,
        ) as plot_workspace:
            service = SandboxPlotToolService(workspace=plot_workspace)
            gateway = ToolGateway(clock=lambda: NOW)
            assert register_sandbox_plot_tools(gateway, service) == TOOLS

            preview_arguments: JsonValue = {
                "data_view_handle_id": data_handle.handle_id,
                "profile_id": "K01",
                "bindings": [
                    FieldBinding(role="x", field_id="field:x").model_dump(mode="json"),
                    FieldBinding(role="y", field_id="field:y").model_dump(mode="json"),
                ],
            }
            previewed = invoke(
                gateway,
                current,
                current_checkpoint,
                tool_name="preview_plot",
                arguments=preview_arguments,
                phase="p1_staged",
                sequence=1,
            )
            assert previewed.status == "succeeded", previewed.error
            assert previewed.side_effect == "staged"
            assert previewed.side_effects[0].effect_kind == "staged_plot"
            assert previewed.provenance[0].source_id == view.data.dataset_id
            preview = SandboxPlotHandle.model_validate_json(json.dumps(previewed.payload))

            edit_arguments: JsonValue = {
                "handle_id": preview.handle_id,
                "edit": {
                    "operation": "set_title",
                    "action_id": "action:gateway-title",
                    "target": preview.document.plot_id,
                    "expected_plot_version": 1,
                    "text": "Gateway title",
                },
            }
            edited_result = invoke(
                gateway,
                current,
                current_checkpoint,
                tool_name="apply_plot_edits",
                arguments=edit_arguments,
                phase="p1_staged",
                sequence=2,
            )
            assert edited_result.status == "succeeded", edited_result
            edited = SandboxPlotHandle.model_validate_json(json.dumps(edited_result.payload))
            assert edited.document.plot_version == 2

            inspected = invoke(
                gateway,
                current,
                current_checkpoint,
                tool_name="inspect_plot",
                arguments={"handle_id": edited.handle_id},
                phase="p0_read",
                sequence=3,
            )
            assert inspected.status == "succeeded", inspected
            assert inspected.side_effect == "none"
            assert inspected.disclosed_scalar_count == 0
            assert inspected.output_handle == edited.handle_id

            wrong_phase = invoke(
                gateway,
                current,
                current_checkpoint,
                tool_name="preview_plot",
                arguments=preview_arguments,
                phase="p0_read",
                sequence=4,
            )
            assert wrong_phase.status == "failed"
            assert wrong_phase.error is not None
            assert wrong_phase.error.code == "TOOL_PERMISSION_DENIED"
