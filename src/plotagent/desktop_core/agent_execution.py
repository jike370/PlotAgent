"""Confirmed execution and verification for the durable Agent foundation v2 slice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel

from plotagent.contracts.agent_tasks import (
    ExecutionGrant,
    ExecutionScope,
    SideEffectReceipt,
    TaskCompletion,
    TaskError,
    ToolReceipt,
    VerificationClaim,
    VerificationEvidenceRef,
    VerificationReport,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.workflows import CompiledTaskItem
from plotagent.engine import PlotEngineAction, ProjectEngineDataProvider
from plotagent.storage import ProjectDomainRepository, ProjectStore
from plotagent.tasking import TaskLedgerRepository
from plotagent.workflows.data_ops import prepare_task_data
from plotagent.workflows.executor import TaskPlanExecutor

from .engine_session import DesktopEngineSession
from .workflow_service import DesktopWorkflowService


class DurableExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _hashed_model(model: BaseModel) -> str:
    return canonical_hash(
        cast(JsonValue, model.model_dump(mode="json", exclude={"content_hash"}))
    )


@dataclass(slots=True)
class DurableTaskExecutionService:
    store: ProjectStore
    domain: ProjectDomainRepository
    engine: DesktopEngineSession
    workflow: DesktopWorkflowService
    ledger: TaskLedgerRepository

    def plan_view(self, task_id: str) -> dict[str, object]:
        checkpoint = self.ledger.get_task(task_id)
        plan = self.ledger.get_plan(task_id)
        return {
            "task": checkpoint.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "plan_hash": canonical_hash(plan),
            "confirmation_state": (
                "pending"
                if checkpoint.state == "awaiting_confirmation"
                else "confirmed"
                if checkpoint.state
                in {"executing", "verifying", "delivering", "completed_verified"}
                else "rejected"
                if checkpoint.state == "rejected"
                else "unavailable"
            ),
        }

    def confirm(
        self,
        task_id: str,
        *,
        expected_task_version: int,
        user_event_id: str,
        plan_hash: str,
    ) -> dict[str, object]:
        checkpoint = self.ledger.get_task(task_id)
        if checkpoint.task_version != expected_task_version:
            raise DurableExecutionError("TASK_VERSION_CONFLICT", "Task version is stale.")
        plan = self.ledger.get_plan(task_id)
        actual_plan_hash = canonical_hash(plan)
        if plan_hash != actual_plan_hash:
            raise DurableExecutionError(
                "PLAN_CONFIRMATION_STALE", "The confirmation card is no longer current."
            )
        self.domain.require_revision(plan.expected_project_revision)
        intent = checkpoint.intent
        if intent is None:
            raise DurableExecutionError("TASK_INTENT_MISSING", "Task intent is unavailable.")
        grant = ExecutionGrant(
            grant_id=f"grant:{plan.plan_id.removeprefix('plan:')}",
            task_id=task_id,
            task_version=checkpoint.task_version + 1,
            intent=intent,
            expected_project_revision=plan.expected_project_revision,
            permission_phase="p2_confirmed",
            scopes=tuple(self._scope(item) for item in plan.items),
            issued_at=_now(),
            content_hash="0" * 64,
        )
        grant = grant.model_copy(update={"content_hash": _hashed_model(grant)})
        updated = self.ledger.confirm_plan(
            task_id,
            expected_task_version=expected_task_version,
            user_event_id=user_event_id,
            payload_hash=plan_hash,
            grant=grant,
        )
        return {
            "task": updated.model_dump(mode="json"),
            "grant": grant.model_dump(mode="json"),
        }

    def reject(
        self,
        task_id: str,
        *,
        expected_task_version: int,
        user_event_id: str,
        plan_hash: str,
    ) -> dict[str, object]:
        if canonical_hash(self.ledger.get_plan(task_id)) != plan_hash:
            raise DurableExecutionError(
                "PLAN_CONFIRMATION_STALE", "The confirmation card is no longer current."
            )
        updated = self.ledger.record_user_event(
            task_id,
            expected_task_version=expected_task_version,
            action="rejected",
            user_event_id=user_event_id,
            payload_hash=plan_hash,
        )
        return {"task": updated.model_dump(mode="json")}

    def run(self, task_id: str) -> dict[str, object]:
        checkpoint = self.ledger.get_task(task_id)
        if checkpoint.state != "executing":
            raise DurableExecutionError(
                "TASK_NOT_EXECUTABLE", "Only a confirmed task can execute."
            )
        plan = self.ledger.get_plan(task_id)
        grant = self.ledger.get_execution_grant(task_id)
        if (
            grant.task_version != checkpoint.task_version
            or grant.expected_project_revision != checkpoint.project_revision
            or grant.intent != checkpoint.intent
        ):
            raise DurableExecutionError(
                "EXECUTION_GRANT_STALE", "Execution authority no longer matches the task."
            )
        self.domain.require_revision(grant.expected_project_revision)
        if len(plan.items) != 1:
            raise DurableExecutionError(
                "P6_SLICE_UNSUPPORTED", "The first execution slice accepts one task item."
            )
        item = plan.items[0]
        scope = grant.scopes[0]
        if scope.item_id != item.item_id or "create_plot" not in scope.operations:
            raise DurableExecutionError(
                "EXECUTION_SCOPE_INVALID", "Execution grant does not authorize this item."
            )
        running = self.ledger.transition_item(
            task_id,
            expected_task_version=checkpoint.task_version,
            item_id=item.item_id,
            expected_item_state="staged",
            next_state="running",
            reason_code="CONFIRMED_EXECUTION_STARTED",
        )
        before = running.project_revision
        started_at = _now()
        try:
            executor = self._item_executor()
            after, plot_version = executor.execute_compiled_item(item, before)
            stored = self.engine.documents.get(item.plot_id, plot_version)
        except Exception as error:
            return self._fail_item(
                task_id,
                item,
                running.task_version,
                before,
                started_at,
                error,
            )

        receipt = ToolReceipt(
            receipt_id=f"receipt:{item.item_id.removeprefix('item:')}.execute",
            task_id=task_id,
            task_version=running.task_version,
            item_id=item.item_id,
            tool_call_id=f"execute:{item.idempotency_key}",
            tool_name="execute_confirmed_plan_item",
            permission_phase="p2_confirmed",
            outcome="succeeded",
            idempotency_key=item.idempotency_key,
            input_hash=canonical_hash(item),
            output_hash=stored.content_hash,
            project_revision_before=before,
            project_revision_after=after,
            side_effects=(
                SideEffectReceipt(
                    effect_kind="plot_version",
                    object_id=item.plot_id,
                    object_version=plot_version,
                    artifact_hash=stored.content_hash,
                    reversible=True,
                ),
            ),
            started_at=started_at,
            finished_at=_now(),
        )
        self.ledger.record_tool_receipt(receipt)
        succeeded = self.ledger.transition_item(
            task_id,
            expected_task_version=running.task_version,
            item_id=item.item_id,
            expected_item_state="running",
            next_state="succeeded",
            reason_code="CONFIRMED_EXECUTION_SUCCEEDED",
            output_plot_id=item.plot_id,
            output_plot_version=plot_version,
        )
        verifying = self.ledger.advance(
            task_id,
            expected_task_version=succeeded.task_version,
            next_state="verifying",
            reason_code="EXECUTION_FINISHED",
            project_revision=after,
        )
        report = self._verification_report(verifying, item, stored.content_hash)
        self.ledger.record_verification_report(report)
        delivering = self.ledger.advance(
            task_id,
            expected_task_version=verifying.task_version,
            next_state="delivering",
            reason_code="VERIFICATION_PASSED",
        )
        completed = self.ledger.complete_task(
            task_id,
            expected_task_version=delivering.task_version,
            completion=TaskCompletion(
                completed_at=_now(),
                final_project_revision=delivering.project_revision,
                required_report_ids=(report.report_id,),
                artifact_receipt_ids=(receipt.receipt_id,),
            ),
        )
        return {
            "task": completed.model_dump(mode="json"),
            "plot": {
                "plot_id": item.plot_id,
                "plot_version": plot_version,
                "content_hash": stored.content_hash,
            },
            "verification": report.model_dump(mode="json"),
        }

    def _item_executor(self) -> TaskPlanExecutor:
        provider = ProjectEngineDataProvider(self.store)
        return TaskPlanExecutor(
            repository=None,
            catalog=self.engine.catalog,
            prepare_data=lambda item: prepare_task_data(
                item,
                provider,
                self.engine.data_views,
            ),
            execute_action=lambda action, revision: self._execute_action(action, revision),
            validate_prepared_data=self.workflow.validate_prepared_data,
            validate_edit_data=self.workflow.validate_edit_data,
        )

    def _execute_action(self, action: PlotEngineAction, revision: int) -> int:
        self.engine.execute_action(
            action,
            expected_project_revision=revision,
        )
        return self.domain.revision

    def _fail_item(
        self,
        task_id: str,
        item: CompiledTaskItem,
        task_version: int,
        before: int,
        started_at: str,
        error: Exception,
    ) -> dict[str, object]:
        after = self.domain.revision
        code = str(getattr(error, "code", type(error).__name__))[:64]
        message = str(getattr(error, "message", str(error) or "Execution failed."))[:512]
        task_error = TaskError(
            code=code,
            category="deterministic_technical",
            message=message,
            retryable=False,
            requires_user=False,
            side_effect_state="known_applied" if after > before else "known_none",
        )
        side_effects = (
            (
                SideEffectReceipt(
                    effect_kind="project_revision",
                    object_id=item.plot_id,
                    artifact_hash=None,
                    reversible=True,
                ),
            )
            if after > before
            else ()
        )
        receipt = ToolReceipt(
            receipt_id=f"receipt:{item.item_id.removeprefix('item:')}.execute",
            task_id=task_id,
            task_version=task_version,
            item_id=item.item_id,
            tool_call_id=f"execute:{item.idempotency_key}",
            tool_name="execute_confirmed_plan_item",
            permission_phase="p2_confirmed",
            outcome="failed",
            idempotency_key=item.idempotency_key,
            input_hash=canonical_hash(item),
            project_revision_before=before,
            project_revision_after=after,
            side_effects=side_effects,
            error=task_error,
            started_at=started_at,
            finished_at=_now(),
        )
        self.ledger.record_tool_receipt(receipt)
        failed_item = self.ledger.transition_item(
            task_id,
            expected_task_version=task_version,
            item_id=item.item_id,
            expected_item_state="running",
            next_state="failed",
            reason_code="CONFIRMED_EXECUTION_FAILED",
            error=task_error,
        )
        failed = self.ledger.advance(
            task_id,
            expected_task_version=failed_item.task_version,
            next_state="failed",
            reason_code="EXECUTION_FAILED",
            project_revision=after,
        )
        return {
            "task": failed.model_dump(mode="json"),
            "error": task_error.model_dump(mode="json"),
        }

    @staticmethod
    def _scope(item: CompiledTaskItem) -> ExecutionScope:
        operations = (
            "create_plot",
            *(action.operation for action in item.visual_actions),
        )
        return ExecutionScope(
            item_id=item.item_id,
            operations=tuple(dict.fromkeys(operations)),
            target_object_ids=(item.plot_id,),
        )

    @staticmethod
    def _verification_report(
        checkpoint: object,
        item: CompiledTaskItem,
        document_hash: str,
    ) -> VerificationReport:
        from plotagent.contracts.agent_tasks import TaskCheckpoint

        current = TaskCheckpoint.model_validate(checkpoint)
        if current.intent is None:
            raise DurableExecutionError("TASK_INTENT_MISSING", "Task intent is unavailable.")
        report = VerificationReport(
            report_id=f"verification:{item.item_id.removeprefix('item:')}.final",
            task_id=current.task_id,
            task_version=current.task_version,
            intent=current.intent,
            item_id=item.item_id,
            status="passed",
            claims=(
                VerificationClaim(
                    claim_id="native_plot_document_persisted",
                    status="passed",
                    expected=(
                        f"{item.profile_id} with {len(item.bindings)} confirmed field bindings"
                    ),
                    observed=(
                        f"plot {item.plot_id} persisted at project revision "
                        f"{current.project_revision}"
                    ),
                    evidence=(
                        VerificationEvidenceRef(
                            evidence_id=item.plot_id,
                            evidence_kind="plot_document",
                            content_hash=document_hash,
                        ),
                    ),
                ),
            ),
            content_hash="0" * 64,
            verified_at=_now(),
        )
        return report.model_copy(update={"content_hash": _hashed_model(report)})
