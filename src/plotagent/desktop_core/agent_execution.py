"""Confirmed execution and verification for the durable Agent foundation v2 slice."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel

from plotagent.contracts.agent_tasks import (
    ExecutionGrant,
    ExecutionScope,
    SideEffectReceipt,
    TaskCheckpoint,
    TaskCompletion,
    TaskError,
    TaskItemState,
    TaskState,
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

_TaskErrorCategory = Literal[
    "transient_external",
    "deterministic_technical",
    "semantic_conflict",
    "stale_or_concurrent",
    "unsupported",
    "safety_or_permission",
    "budget",
    "runtime",
]

_PLAN_REVISION_REQUIRED_CODES = frozenset(
    {
        "WORKFLOW_BINDING_OUTPUT_MISSING",
        "WORKFLOW_SOURCES_NOT_COMBINED",
        "WORKFLOW_SOURCE_UNUSED",
    }
)


class DurableExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class ControlledExecutionFaults:
    """One-shot failure hook for formal desktop UI fault-path qualification.

    The hook is inert unless both environment variables are present.  It is
    intentionally evaluated once per opened project session so an explicit
    retry can prove recovery without changing source code during a black-box run.
    """

    profile_id: str | None = None
    remaining: int = 0

    @classmethod
    def from_environment(cls) -> ControlledExecutionFaults:
        enabled = os.environ.get("PLOTAGENT_ENABLE_UI_TEST_FAULTS") == "1"
        profile_id = os.environ.get("PLOTAGENT_UI_TEST_FAIL_PROFILE_ONCE", "").strip()
        return cls(profile_id=profile_id if enabled and profile_id else None, remaining=1)

    def before_item(self, item: CompiledTaskItem) -> None:
        if self.remaining < 1 or self.profile_id != item.profile_id:
            return
        self.remaining -= 1
        raise DurableExecutionError(
            "UI_TEST_RENDERER_FAILURE",
            f"受控 UI 测试故障：{item.profile_id} 本次执行在提交前失败。",
        )


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
    controlled_faults: ControlledExecutionFaults = field(
        default_factory=ControlledExecutionFaults.from_environment
    )

    def plan_view(self, task_id: str) -> dict[str, object]:
        checkpoint = self.ledger.get_task(task_id)
        plan = self.ledger.get_plan(task_id)
        return {
            "task": checkpoint.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "plan_hash": canonical_hash(plan),
            "confirmation_state": (
                "pending"
                if checkpoint.state
                in {"awaiting_confirmation", "awaiting_reconfirmation"}
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

    def run(
        self,
        task_id: str,
        *,
        max_items: int | None = None,
    ) -> dict[str, object]:
        if max_items is not None and max_items < 1:
            raise ValueError("max_items must be positive")
        lease = self.ledger.acquire_lease(
            task_id,
            holder_id=f"execution:{uuid.uuid4().hex}",
            ttl_seconds=1800,
        )
        try:
            return self._run_with_lease(task_id, max_items=max_items)
        finally:
            self.ledger.release_lease(task_id, lease_token=lease)

    def _run_with_lease(
        self,
        task_id: str,
        *,
        max_items: int | None,
    ) -> dict[str, object]:
        checkpoint = self.ledger.get_task(task_id)
        if checkpoint.state == "cancelling":
            if not any(item.state == "running" for item in checkpoint.items):
                return self._finalize_cancel(task_id, checkpoint, reports=[])
            plan = self.ledger.get_plan(task_id)
            reconciled = self._reconcile_interrupted_items(
                task_id,
                checkpoint,
                plan.items,
            )
            return self._finalize_cancel(task_id, reconciled, reports=[])
        if checkpoint.state in {"verifying", "delivering"}:
            return self._complete_verified_task(task_id, checkpoint)
        if checkpoint.state != "executing":
            raise DurableExecutionError(
                "TASK_NOT_EXECUTABLE", "Only a confirmed task can execute."
            )
        plan = self.ledger.get_plan(task_id)
        checkpoint = self._reconcile_interrupted_items(task_id, checkpoint, plan.items)
        if checkpoint.state == "partial":
            return {
                "task": checkpoint.model_dump(mode="json"),
                "plots": self._completed_plots(checkpoint),
                "verifications": [],
                "failures": [
                    {
                        "item_id": item.item_id,
                        "error": item.last_error.model_dump(mode="json"),
                    }
                    for item in checkpoint.items
                    if item.state == "repairable_failed" and item.last_error is not None
                ],
            }
        grant = self.ledger.get_execution_grant(task_id)
        reconciled_all = bool(checkpoint.items) and all(
            item.state == "succeeded" for item in checkpoint.items
        )
        execution_started = any(
            item.attempt_count > 0
            or item.state in {"succeeded", "repairable_failed", "failed", "blocked"}
            for item in checkpoint.items
        )
        if (
            grant.intent != checkpoint.intent
            or grant.task_version > checkpoint.task_version
            or (not execution_started and grant.task_version != checkpoint.task_version)
        ):
            raise DurableExecutionError(
                "EXECUTION_GRANT_STALE", "Execution authority no longer matches the task."
            )
        if (
            not reconciled_all
            and (
                grant.expected_project_revision > checkpoint.project_revision
                or (
                    not execution_started
                    and grant.expected_project_revision != checkpoint.project_revision
                )
            )
        ):
            raise DurableExecutionError(
                "EXECUTION_GRANT_STALE", "Execution authority no longer matches the project."
            )
        self.domain.require_revision(checkpoint.project_revision)
        scopes = {scope.item_id: scope for scope in grant.scopes}
        if not reconciled_all and tuple(scopes) != tuple(
            item.item_id for item in plan.items
        ):
            raise DurableExecutionError(
                "EXECUTION_SCOPE_INVALID", "Execution grant does not match the batch plan."
            )

        executor = self._item_executor()
        plots: list[dict[str, object]] = []
        reports: list[VerificationReport] = []
        receipts: list[ToolReceipt] = []
        failures: list[dict[str, object]] = []
        attempted_items = 0
        # During an initial confirmed batch, a repairable failure from an earlier
        # step must not be retried implicitly while untouched items remain. Once
        # the task is explicitly returned from ``partial`` to ``executing``, no
        # staged items remain and the scoped repairable item becomes eligible.
        has_staged_items = any(item.state == "staged" for item in checkpoint.items)
        for item in plan.items:
            current = self.ledger.get_task(task_id)
            if current.state == "cancelling":
                return self._finalize_cancel(task_id, current, reports=reports)
            snapshot = next(entry for entry in current.items if entry.item_id == item.item_id)
            if snapshot.state in {"succeeded", "failed", "blocked", "cancelled"}:
                continue
            if snapshot.state == "repairable_failed" and has_staged_items:
                continue
            scope = scopes[item.item_id]
            if "create_plot" not in scope.operations:
                raise DurableExecutionError(
                    "EXECUTION_SCOPE_INVALID", "Execution grant does not authorize this item."
                )
            if snapshot.state not in {"staged", "repairable_failed"}:
                raise DurableExecutionError(
                    "TASK_ITEM_STATE_INVALID", "A batch item was not ready to execute."
                )
            running = self.ledger.transition_item(
                task_id,
                expected_task_version=current.task_version,
                item_id=item.item_id,
                expected_item_state=snapshot.state,
                next_state="running",
                reason_code="CONFIRMED_EXECUTION_STARTED",
            )
            running_item = next(
                entry for entry in running.items if entry.item_id == item.item_id
            )
            before = running.project_revision
            started_at = _now()
            try:
                self.controlled_faults.before_item(item)
                after, plot_version = executor.execute_compiled_item(item, before)
                stored = self.engine.documents.get(item.plot_id, plot_version)
            except Exception as error:
                attempted_items += 1
                latest = self.ledger.get_task(task_id)
                failure, report, receipt = self._record_item_failure(
                    task_id,
                    item,
                    latest.task_version,
                    running_item.attempt_count,
                    before,
                    started_at,
                    error,
                )
                failures.append(failure)
                reports.append(report)
                receipts.append(receipt)
                latest = self.ledger.get_task(task_id)
                if latest.state == "cancelling":
                    return self._finalize_cancel(task_id, latest, reports=reports)
                if self._should_yield_execution_step(
                    latest,
                    attempted_items=attempted_items,
                    max_items=max_items,
                ):
                    return self._execution_progress(latest, reports=reports)
                continue

            latest = self.ledger.get_task(task_id)
            receipt = ToolReceipt(
                receipt_id=self._execution_receipt_id(item, running_item.attempt_count),
                task_id=task_id,
                task_version=latest.task_version,
                item_id=item.item_id,
                tool_call_id=f"execute:{item.idempotency_key}:{running_item.attempt_count}",
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
            receipted = self.ledger.record_tool_receipt(receipt)
            succeeded = self.ledger.transition_item(
                task_id,
                expected_task_version=receipted.task_version,
                item_id=item.item_id,
                expected_item_state="running",
                next_state="succeeded",
                reason_code="CONFIRMED_EXECUTION_SUCCEEDED",
                output_plot_id=item.plot_id,
                output_plot_version=plot_version,
            )
            report = self._verification_report(
                succeeded,
                item,
                stored.content_hash,
                attempt_count=running_item.attempt_count,
            )
            self.ledger.record_verification_report(report)
            receipts.append(receipt)
            reports.append(report)
            plots.append(
                {
                    "item_id": item.item_id,
                    "plot_id": item.plot_id,
                    "plot_version": plot_version,
                    "content_hash": stored.content_hash,
                }
            )
            attempted_items += 1
            latest = self.ledger.get_task(task_id)
            if latest.state == "cancelling":
                return self._finalize_cancel(task_id, latest, reports=reports)
            if self._should_yield_execution_step(
                latest,
                attempted_items=attempted_items,
                max_items=max_items,
            ):
                return self._execution_progress(latest, reports=reports)

        current = self.ledger.get_task(task_id)
        plots = self._completed_plots(current)
        failures = self._current_failures(current)
        if failures:
            retryable_failure = any(
                item.state == "repairable_failed" for item in current.items
            )
            target_state: TaskState = (
                "partial" if plots or retryable_failure else "failed"
            )
            stopped = self.ledger.advance(
                task_id,
                expected_task_version=current.task_version,
                next_state=target_state,
                reason_code=(
                    "BATCH_PARTIALLY_SUCCEEDED" if plots else "BATCH_EXECUTION_FAILED"
                ),
                project_revision=current.project_revision,
            )
            return {
                "task": stopped.model_dump(mode="json"),
                "plots": plots,
                "verifications": [report.model_dump(mode="json") for report in reports],
                "failures": failures,
            }

        if any(item.state != "succeeded" for item in current.items):
            stopped = self.ledger.advance(
                task_id,
                expected_task_version=current.task_version,
                next_state="partial",
                reason_code="BATCH_REPAIR_INCOMPLETE",
                project_revision=current.project_revision,
            )
            return {
                "task": stopped.model_dump(mode="json"),
                "plots": plots,
                "verifications": [report.model_dump(mode="json") for report in reports],
                "failures": failures,
            }

        verifying = self.ledger.advance(
            task_id,
            expected_task_version=current.task_version,
            next_state="verifying",
            reason_code="EXECUTION_FINISHED",
            project_revision=current.project_revision,
        )
        return self._complete_verified_task(task_id, verifying)

    @staticmethod
    def _should_yield_execution_step(
        checkpoint: TaskCheckpoint,
        *,
        attempted_items: int,
        max_items: int | None,
    ) -> bool:
        """Return control between atomic items so queued cancellation can be handled."""

        if max_items is None or attempted_items < max_items:
            return False
        # A repairable failure is not an implicit retry. Yield only when another
        # untouched item remains in the confirmed batch.
        return any(item.state == "staged" for item in checkpoint.items)

    def _execution_progress(
        self,
        checkpoint: TaskCheckpoint,
        *,
        reports: list[VerificationReport],
    ) -> dict[str, object]:
        return {
            "task": checkpoint.model_dump(mode="json"),
            "plots": self._completed_plots(checkpoint),
            "verifications": [report.model_dump(mode="json") for report in reports],
            "failures": self._current_failures(checkpoint),
            "execution_pending": True,
        }

    @staticmethod
    def _current_failures(checkpoint: TaskCheckpoint) -> list[dict[str, object]]:
        return [
            {
                "item_id": item.item_id,
                "error": item.last_error.model_dump(mode="json"),
            }
            for item in checkpoint.items
            if item.state in {"repairable_failed", "failed", "blocked"}
            and item.last_error is not None
        ]

    def _complete_verified_task(
        self,
        task_id: str,
        checkpoint: TaskCheckpoint,
    ) -> dict[str, object]:
        """Finish a fully verified task, including after a process restart."""

        current = checkpoint
        if not current.items or any(item.state != "succeeded" for item in current.items):
            raise DurableExecutionError(
                "VERIFICATION_CHECKPOINT_INVALID",
                "A verifying task must retain only succeeded task items.",
            )
        required_report_ids = tuple(
            item.verification_report_ids[-1]
            for item in current.items
            if item.verification_report_ids
        )
        if len(required_report_ids) != len(current.items):
            raise DurableExecutionError(
                "VERIFICATION_EVIDENCE_MISSING",
                "A verified task item is missing its durable verification report.",
            )
        if current.state == "verifying":
            current = self.ledger.advance(
                task_id,
                expected_task_version=current.task_version,
                next_state="delivering",
                reason_code="VERIFICATION_PASSED",
            )
        if current.state != "delivering":
            raise DurableExecutionError(
                "DELIVERY_CHECKPOINT_INVALID",
                "Only a verifying or delivering task can finish verified delivery.",
            )
        completed = self.ledger.complete_task(
            task_id,
            expected_task_version=current.task_version,
            completion=TaskCompletion(
                completed_at=_now(),
                final_project_revision=current.project_revision,
                required_report_ids=required_report_ids,
                artifact_receipt_ids=tuple(
                    item.receipt_ids[-1] for item in current.items if item.receipt_ids
                ),
            ),
        )
        plots = self._completed_plots(completed)
        reports = [
            self.ledger.get_verification_report(report_id)
            for report_id in required_report_ids
        ]
        result: dict[str, object] = {
            "task": completed.model_dump(mode="json"),
            "plots": plots,
            "verifications": [report.model_dump(mode="json") for report in reports],
        }
        if len(plots) == 1:
            result["plot"] = plots[0]
            result["verification"] = reports[0].model_dump(mode="json")
        return result

    def _finalize_cancel(
        self,
        task_id: str,
        checkpoint: TaskCheckpoint,
        *,
        reports: list[VerificationReport],
    ) -> dict[str, object]:
        """Finish cancellation only after the current atomic item is durably projected."""

        cancelled = self.ledger.finalize_cancel(
            task_id,
            expected_task_version=checkpoint.task_version,
        )
        return {
            "task": cancelled.model_dump(mode="json"),
            "plots": self._completed_plots(cancelled),
            "verifications": [report.model_dump(mode="json") for report in reports],
            "failures": [],
        }

    def _reconcile_interrupted_items(
        self,
        task_id: str,
        checkpoint: object,
        plan_items: tuple[CompiledTaskItem, ...],
    ) -> TaskCheckpoint:
        """Recover an item interrupted between atomic engine commit and ledger projection."""

        current = TaskCheckpoint.model_validate(checkpoint)
        by_id = {item.item_id: item for item in plan_items}
        interrupted = False
        for snapshot in tuple(current.items):
            if snapshot.state != "running":
                continue
            interrupted = True
            item = by_id[snapshot.item_id]
            stored_version = self.engine.documents.latest_version(item.plot_id)
            if stored_version is None:
                _failure, report, _receipt = self._record_item_failure(
                    task_id,
                    item,
                    current.task_version,
                    snapshot.attempt_count,
                    current.project_revision,
                    _now(),
                    DurableExecutionError(
                        "EXECUTION_INTERRUPTED",
                        "Execution stopped before an atomic plot result was committed.",
                    ),
                )
                current = self.ledger.get_task(task_id)
                continue

            stored = self.engine.documents.get(item.plot_id, stored_version)
            if snapshot.receipt_ids:
                receipt = self.ledger.get_tool_receipt(snapshot.receipt_ids[-1])
                if receipt.outcome != "succeeded":
                    raise DurableExecutionError(
                        "RECEIPT_RECONCILE_CONFLICT",
                        "An interrupted item has a non-success receipt and a committed plot.",
                    )
            else:
                receipt = ToolReceipt(
                    receipt_id=self._execution_receipt_id(item, snapshot.attempt_count),
                    task_id=task_id,
                    task_version=current.task_version,
                    item_id=item.item_id,
                    tool_call_id=(
                        f"execute:{item.idempotency_key}:{snapshot.attempt_count}"
                    ),
                    tool_name="execute_confirmed_plan_item",
                    permission_phase="p2_confirmed",
                    outcome="succeeded",
                    idempotency_key=item.idempotency_key,
                    input_hash=canonical_hash(item),
                    output_hash=stored.content_hash,
                    project_revision_before=current.project_revision,
                    project_revision_after=self.domain.revision,
                    side_effects=(
                        SideEffectReceipt(
                            effect_kind="plot_version",
                            object_id=item.plot_id,
                            object_version=stored_version,
                            artifact_hash=stored.content_hash,
                            reversible=True,
                        ),
                    ),
                    started_at=_now(),
                    finished_at=_now(),
                )
                current = self.ledger.record_tool_receipt(receipt)
            succeeded = self.ledger.transition_item(
                task_id,
                expected_task_version=current.task_version,
                item_id=item.item_id,
                expected_item_state="running",
                next_state="succeeded",
                reason_code="INTERRUPTED_COMMIT_RECONCILED",
                output_plot_id=item.plot_id,
                output_plot_version=stored_version,
            )
            report = self._verification_report(
                succeeded,
                item,
                stored.content_hash,
                attempt_count=snapshot.attempt_count,
            )
            current = self.ledger.record_verification_report(report)
        if current.state != "cancelling" and interrupted and any(
            item.state == "repairable_failed" for item in current.items
        ):
            current = self.ledger.advance(
                task_id,
                expected_task_version=current.task_version,
                next_state="partial",
                reason_code="INTERRUPTED_EXECUTION_REQUIRES_REPAIR",
                project_revision=current.project_revision,
            )
        return current

    def _completed_plots(self, checkpoint: object) -> list[dict[str, object]]:
        from plotagent.contracts.agent_tasks import TaskCheckpoint

        current = TaskCheckpoint.model_validate(checkpoint)
        completed: list[dict[str, object]] = []
        for item in current.items:
            if (
                item.state != "succeeded"
                or item.output_plot_id is None
                or item.output_plot_version is None
            ):
                continue
            stored = self.engine.documents.get(item.output_plot_id, item.output_plot_version)
            completed.append(
                {
                    "item_id": item.item_id,
                    "plot_id": item.output_plot_id,
                    "plot_version": item.output_plot_version,
                    "content_hash": stored.content_hash,
                }
            )
        return completed

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

    def _record_item_failure(
        self,
        task_id: str,
        item: CompiledTaskItem,
        task_version: int,
        attempt_count: int,
        before: int,
        started_at: str,
        error: Exception,
    ) -> tuple[dict[str, object], VerificationReport, ToolReceipt]:
        after = self.domain.revision
        code = str(getattr(error, "code", type(error).__name__))[:64]
        message = str(getattr(error, "message", str(error) or "Execution failed."))[:512]
        category, retryable, requires_user = self._classify_failure(code)
        task_error = TaskError(
            code=code,
            category=category,
            message=message,
            retryable=retryable,
            requires_user=requires_user,
            side_effect_state="known_applied" if after > before else "known_none",
            diagnostic_id=(
                f"diag:{task_id.removeprefix('task:')}."
                f"{item.item_id.removeprefix('item:')}.a{attempt_count}"
            )[:128],
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
            receipt_id=self._execution_receipt_id(item, attempt_count),
            task_id=task_id,
            task_version=task_version,
            item_id=item.item_id,
            tool_call_id=f"execute:{item.idempotency_key}:{attempt_count}",
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
        item_state: TaskItemState = (
            "repairable_failed" if retryable or requires_user else "failed"
        )
        failed_item = self.ledger.transition_item(
            task_id,
            expected_task_version=task_version,
            item_id=item.item_id,
            expected_item_state="running",
            next_state=item_state,
            reason_code="CONFIRMED_EXECUTION_FAILED",
            error=task_error,
        )
        report = self._failure_verification_report(
            failed_item,
            item,
            receipt,
            task_error,
            attempt_count=attempt_count,
        )
        self.ledger.record_verification_report(report)
        return (
            {
                "item_id": item.item_id,
                "error": task_error.model_dump(mode="json"),
                "verification_report_id": report.report_id,
            },
            report,
            receipt,
        )

    @staticmethod
    def _classify_failure(code: str) -> tuple[_TaskErrorCategory, bool, bool]:
        normalized = code.upper()
        if normalized in _PLAN_REVISION_REQUIRED_CODES:
            # These failures prove that the confirmed structured plan is invalid.
            # Re-running the immutable plan cannot help: the Agent must stage a
            # corrected intent and the user must reconfirm it.
            return "semantic_conflict", False, True
        if any(token in normalized for token in ("TIMEOUT", "UNAVAILABLE", "DISCONNECT")):
            return "transient_external", True, False
        if any(token in normalized for token in ("STALE", "REVISION", "CONFLICT")):
            return "stale_or_concurrent", False, False
        if "UNSUPPORTED" in normalized:
            return "unsupported", False, False
        if any(token in normalized for token in ("PERMISSION", "AUTHORITY", "SCOPE")):
            return "safety_or_permission", False, True
        if any(
            token in normalized
            for token in (
                "VALUEERROR",
                "INVALID_ARGUMENT",
                "INVALID_PARAMS",
                "BINDING",
                "FIELD",
                "DATA_TYPE",
                "DATA_SHAPE",
                "CONTRACT",
            )
        ):
            return "semantic_conflict", False, True
        return "deterministic_technical", True, False

    @staticmethod
    def _execution_receipt_id(item: CompiledTaskItem, attempt_count: int) -> str:
        suffix = "execute" if attempt_count == 1 else f"execute.{attempt_count}"
        return f"receipt:{item.item_id.removeprefix('item:')}.{suffix}"

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
        *,
        attempt_count: int,
    ) -> VerificationReport:
        from plotagent.contracts.agent_tasks import TaskCheckpoint

        current = TaskCheckpoint.model_validate(checkpoint)
        if current.intent is None:
            raise DurableExecutionError("TASK_INTENT_MISSING", "Task intent is unavailable.")
        report = VerificationReport(
            report_id=(
                f"verification:{item.item_id.removeprefix('item:')}.attempt-{attempt_count}"
            ),
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

    @staticmethod
    def _failure_verification_report(
        checkpoint: object,
        item: CompiledTaskItem,
        receipt: ToolReceipt,
        error: TaskError,
        *,
        attempt_count: int,
    ) -> VerificationReport:
        from plotagent.contracts.agent_tasks import TaskCheckpoint

        current = TaskCheckpoint.model_validate(checkpoint)
        if current.intent is None:
            raise DurableExecutionError("TASK_INTENT_MISSING", "Task intent is unavailable.")
        report = VerificationReport(
            report_id=(
                f"verification:{item.item_id.removeprefix('item:')}.attempt-{attempt_count}"
            ),
            task_id=current.task_id,
            task_version=current.task_version,
            intent=current.intent,
            item_id=item.item_id,
            status="failed",
            claims=(
                VerificationClaim(
                    claim_id="confirmed_item_execution",
                    status="failed",
                    expected=f"{item.profile_id} executes within the confirmed item scope",
                    observed=error.message,
                    evidence=(
                        VerificationEvidenceRef(
                            evidence_id=receipt.receipt_id,
                            evidence_kind="tool_receipt",
                            content_hash=canonical_hash(receipt),
                        ),
                    ),
                    repair_scope=(
                        (item.item_id, "execute_confirmed_plan_item")
                        if error.retryable
                        else ()
                    ),
                    error=error,
                ),
            ),
            content_hash="0" * 64,
            verified_at=_now(),
        )
        return report.model_copy(update={"content_hash": _hashed_model(report)})
