"""P0/P1 Agent tools for sandbox rendering and public plot edits."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, model_validator

from plotagent.contracts.agent_data import DataViewHandleId
from plotagent.contracts.agent_plots import (
    SandboxBackend,
    SandboxPlotEdit,
    SandboxPlotHandle,
    SandboxPlotHandleId,
)
from plotagent.contracts.agent_tasks import SideEffectReceipt, TaskState
from plotagent.contracts.agent_tools import ToolCostClass, ToolProvenance, ToolWarning
from plotagent.contracts.base import StrictModel, Token
from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import FieldBinding
from plotagent.tooling.data_workspace_ops import DataWorkspaceError
from plotagent.tooling.gateway import (
    ToolExecutionOutput,
    ToolExecutionProblem,
    ToolGateway,
    ToolHandler,
)
from plotagent.tooling.plot_workspace import SandboxPlotError, SandboxPlotWorkspace

_PLOT_STATES: tuple[TaskState, ...] = ("created", "investigating", "repairing")


class PreviewPlotInput(StrictModel):
    data_view_handle_id: DataViewHandleId
    profile_id: Token
    bindings: tuple[FieldBinding, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def roles_are_unique(self) -> PreviewPlotInput:
        roles = tuple(binding.role for binding in self.bindings)
        if len(roles) != len(set(roles)):
            raise ValueError("sandbox plot binding roles must be unique")
        return self


class ApplyPlotEditInput(StrictModel):
    handle_id: SandboxPlotHandleId
    edit: SandboxPlotEdit


class InspectPlotInput(StrictModel):
    handle_id: SandboxPlotHandleId


class SandboxPlotToolService:
    def __init__(
        self,
        *,
        workspace: SandboxPlotWorkspace,
    ) -> None:
        self.workspace = workspace

    def preview_matplotlib(self, item: PreviewPlotInput) -> ToolExecutionOutput:
        return self._preview(item, backend="matplotlib")

    def preview_origin(self, item: PreviewPlotInput) -> ToolExecutionOutput:
        return self._preview(item, backend="origin")

    def edit_matplotlib(self, item: ApplyPlotEditInput) -> ToolExecutionOutput:
        return self._edit(item, backend="matplotlib")

    def edit_origin(self, item: ApplyPlotEditInput) -> ToolExecutionOutput:
        return self._edit(item, backend="origin")

    def inspect(self, item: InspectPlotInput) -> ToolExecutionOutput:
        try:
            handle = self.workspace.get(item.handle_id)
        except SandboxPlotError as error:
            raise _plot_problem(error) from error
        return ToolExecutionOutput(
            payload=handle,
            summary="Inspected one sandbox plot without exposing backend scripts or native refs.",
            output_handle=handle.handle_id,
            provenance=self._provenance(handle),
            side_effect="none",
        )

    def _preview(self, item: PreviewPlotInput, *, backend: SandboxBackend) -> ToolExecutionOutput:
        try:
            handle = self.workspace.preview(
                data_view_handle_id=item.data_view_handle_id,
                profile_id=item.profile_id,
                bindings=item.bindings,
                backends=(backend,),
            )
        except (SandboxPlotError, DataWorkspaceError) as error:
            raise _plot_problem(error) from error
        return self._staged_output(handle, backend=backend, operation="previewed")

    def _edit(self, item: ApplyPlotEditInput, *, backend: SandboxBackend) -> ToolExecutionOutput:
        try:
            handle = self.workspace.apply_edit(
                item.handle_id,
                edit=item.edit,
                expected_backend=backend,
            )
        except SandboxPlotError as error:
            raise _plot_problem(error) from error
        return self._staged_output(handle, backend=backend, operation="edited")

    def _staged_output(
        self,
        handle: SandboxPlotHandle,
        *,
        backend: SandboxBackend,
        operation: str,
    ) -> ToolExecutionOutput:
        side_effects = [
            SideEffectReceipt(
                effect_kind="staged_plot",
                object_id=handle.handle_id,
                object_version=handle.document.plot_version,
                artifact_hash=canonical_hash(handle),
            )
        ]
        if backend == "origin":
            side_effects.append(
                SideEffectReceipt(
                    effect_kind="origin_session",
                    object_id=handle.handle_id,
                    reversible=False,
                )
            )
        warnings = (
            (
                ToolWarning(
                    code="SANDBOX_ORIGIN_PREVIEW_IMAGE_UNAVAILABLE",
                    message=(
                        "The Origin sandbox returned editable OPJU and native readback; "
                        "use the Matplotlib sandbox for an inline image preview."
                    ),
                ),
            )
            if backend == "origin"
            else ()
        )
        return ToolExecutionOutput(
            payload=handle,
            summary=(
                f"Sandbox {operation} with {backend}; artifacts and mechanical readback verified."
            ),
            output_handle=handle.handle_id,
            provenance=self._provenance(handle),
            warnings=warnings,
            side_effect="staged",
            side_effects=tuple(side_effects),
        )

    def _provenance(self, handle: SandboxPlotHandle) -> tuple[ToolProvenance, ...]:
        return tuple(
            ToolProvenance(
                source_id=source.dataset_id,
                source_version=source.version,
                content_hash=source.content_hash,
                coordinate=handle.handle_id,
            )
            for source in handle.root_sources
        )


def _plot_problem(error: SandboxPlotError | DataWorkspaceError) -> ToolExecutionProblem:
    fatal_codes = {
        "DATA_HANDLE_CORRUPT",
        "DATA_HANDLE_NOT_FOUND",
        "DATA_SOURCE_IDENTITY_MISMATCH",
        "SANDBOX_HANDLE_IDEMPOTENCY_CONFLICT",
        "SANDBOX_PLOT_CORRUPT",
        "SANDBOX_WORKSPACE_CLOSED",
        "SANDBOX_WORKSPACE_PATH_INVALID",
        "SANDBOX_WORKSPACE_THREAD_INVALID",
    }
    unsupported = error.code == "SANDBOX_ORIGIN_UNAVAILABLE"
    fatal = error.code in fatal_codes
    staged = isinstance(error, SandboxPlotError) and error.staged_side_effect
    return ToolExecutionProblem(
        code=error.code,
        category=("UNSUPPORTED" if unsupported else "FATAL" if fatal else "AGENT_REPAIRABLE"),
        message=error.message,
        retryable=not (unsupported or fatal),
        requires_user=False,
        repair_hint=(
            None
            if unsupported or fatal
            else "Inspect the current data/plot handle and correct only the rejected public input."
        ),
        side_effect_state="staged" if staged else "none",
    )


def register_sandbox_plot_tools(
    gateway: ToolGateway,
    service: SandboxPlotToolService,
) -> tuple[str, ...]:
    registrations: tuple[
        tuple[
            str,
            str,
            str,
            str,
            type[BaseModel],
            ToolCostClass,
            int,
            bool,
        ],
        ...,
    ] = (
        (
            "tool:preview_plot",
            "preview_plot",
            "Render a Matplotlib sandbox preview from one immutable staged data handle.",
            "preview_matplotlib",
            PreviewPlotInput,
            "moderate",
            120_000,
            False,
        ),
        (
            "tool:preview_origin_plot",
            "preview_origin_plot",
            "Create an editable Origin sandbox project and return public native readback.",
            "preview_origin",
            PreviewPlotInput,
            "expensive",
            900_000,
            True,
        ),
        (
            "tool:apply_plot_edits",
            "apply_plot_edits",
            "Apply one public cross-backend visual action to a Matplotlib sandbox plot.",
            "edit_matplotlib",
            ApplyPlotEditInput,
            "moderate",
            120_000,
            False,
        ),
        (
            "tool:apply_origin_plot_edits",
            "apply_origin_plot_edits",
            "Apply one public cross-backend visual action to an Origin sandbox plot.",
            "edit_origin",
            ApplyPlotEditInput,
            "expensive",
            900_000,
            True,
        ),
        (
            "tool:inspect_plot",
            "inspect_plot",
            "Inspect a sandbox plot's public document, artifacts and native structure summary.",
            "inspect",
            InspectPlotInput,
            "cheap",
            10_000,
            False,
        ),
    )
    names: list[str] = []
    for (
        contract_id,
        tool_name,
        description,
        handler_name,
        input_model,
        cost_class,
        timeout_ms,
        uses_origin,
    ) in registrations:
        staged = tool_name != "inspect_plot"
        gateway.register(
            contract_id=contract_id,
            contract_version=1,
            tool_name=tool_name,
            description=description,
            permission_phase="p1_staged" if staged else "p0_read",
            side_effect="staged" if staged else "none",
            allowed_task_states=_PLOT_STATES,
            input_model=input_model,
            output_model=SandboxPlotHandle,
            cost_class=cost_class,
            timeout_ms=timeout_ms,
            max_disclosed_scalars=0,
            uses_origin=uses_origin,
            handler=cast(ToolHandler, getattr(service, handler_name)),
        )
        names.append(tool_name)
    return tuple(names)
