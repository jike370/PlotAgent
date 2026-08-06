"""Pure orchestration for strictly isomorphic batch execution."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from plotagent.batch.models import (
    BatchExportSelection,
    BatchItemPhase,
    BatchItemRecord,
    BatchSubmission,
    BatchSubmissionRequest,
    BatchTaskRecord,
    ExecutionTaskState,
    ExportExclusion,
    ExportScope,
    OutputKey,
    ReviewState,
    StagedPlot,
)
from plotagent.batch.protocols import BatchExecutor, BatchRepository, CancellationToken
from plotagent.contracts.base import PlotSpecRef, PreparedDatasetRef
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.decisions import InputQuestion, NeedsInput, Unsupported
from plotagent.contracts.plots import (
    BatchExecutionSignature,
    BatchItemState,
    BatchPlotOverride,
    BatchSpec,
    DatasetSignature,
)
from plotagent.workflow_errors import WorkflowFailure, workflow_error

_ALLOWED_TASK_TRANSITIONS = {
    "queued": {"preparing", "cancelling", "interrupted"},
    "preparing": {"running", "cancelling", "failed", "interrupted"},
    "running": {"committing", "cancelling", "failed", "interrupted"},
    "committing": {"succeeded", "failed", "partially_succeeded", "interrupted"},
    "cancelling": {"cancelled", "committing", "interrupted"},
    "succeeded": set(),
    "cancelled": set(),
    "failed": set(),
    "partially_succeeded": set(),
    "interrupted": set(),
}

_ALLOWED_ITEM_TRANSITIONS = {
    "queued": {"preparing", "cancelled"},
    "preparing": {"running", "failed", "cancelled"},
    "running": {"committing", "failed", "cancelled"},
    "committing": {"succeeded", "failed"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
}


class _TaskCancellationToken(CancellationToken):
    def __init__(self, repository: BatchRepository, task_id: str) -> None:
        self._repository = repository
        self._task_id = task_id

    @property
    def cancelled(self) -> bool:
        return self._repository.get_task(self._task_id).state == "cancelling"


class BatchService:
    def __init__(self, repository: BatchRepository, executor: BatchExecutor) -> None:
        self._repository = repository
        self._executor = executor

    def submit(self, request: BatchSubmissionRequest) -> BatchSubmission | NeedsInput | Unsupported:
        request_hash = self._request_hash(request)
        existing = self._repository.find_task_by_idempotency(
            request.project_id, request.idempotency_key
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise WorkflowFailure(
                    workflow_error(
                        "BATCH_IDEMPOTENCY_CONFLICT",
                        "The idempotency key already belongs to a different batch submission.",
                    )
                )
            return BatchSubmission(
                task_id=existing.request.task_id,
                state=existing.state,
                execution_signature=existing.execution_signature,
                replayed=True,
            )

        if not request.mapping_confirmed:
            return NeedsInput(
                target_alias="active_target",
                questions=(
                    InputQuestion(
                        question_key="confirm_mapping",
                        prompt="Confirm the single field mapping for every batch item.",
                        input_kind="text",
                    ),
                ),
            )

        dataset_signature = request.items[0].dataset_signature
        if any(item.dataset_signature != dataset_signature for item in request.items[1:]):
            return Unsupported(
                target_alias="active_target",
                category="v1_scope",
                explanation=(
                    "Batch inputs are not isomorphic. Split them into separate batches; "
                    "v1 does not join, concatenate, normalize, or apply per-item exceptions."
                ),
            )

        signature = self._execution_signature(request, dataset_signature)
        task = BatchTaskRecord(
            request=request,
            request_hash=request_hash,
            execution_signature=signature,
            state="queued",
            sequence=0,
            items=tuple(BatchItemRecord(work_item=item) for item in request.items),
            history=("queued",),
        )
        self._repository.add_task(task)
        return BatchSubmission(
            task_id=request.task_id,
            state="queued",
            execution_signature=signature,
        )

    def run(self, task_id: str) -> BatchTaskRecord:
        task = self._repository.get_task(task_id)
        if task.state in {"succeeded", "partially_succeeded", "failed", "cancelled"}:
            return task
        if task.state == "cancelling":
            return self._finish_cancel_without_outputs(task)
        if task.state != "queued":
            raise RuntimeError(f"task cannot run from {task.state}")

        task = self._transition_task(task, "preparing")
        self._repository.save_task(task)
        prepared: dict[str, PreparedDatasetRef] = {}
        token = _TaskCancellationToken(self._repository, task_id)

        for record in task.items:
            task = self._repository.get_task(task_id)
            if task.state == "cancelling":
                break
            record = self._transition_item(task.item(record.work_item.item_id), "preparing")
            task = task.replace_item(record)
            self._repository.save_task(task)
            try:
                prepared_ref = self._executor.prepare_item(
                    record.work_item, task.request.template, token
                )
                prepared[record.work_item.item_id] = prepared_ref
                task = self._repository.get_task(task_id).replace_item(
                    replace(record, prepared_ref=prepared_ref)
                )
                self._repository.save_task(task)
            except WorkflowFailure as failure:
                task = self._repository.get_task(task_id).replace_item(
                    replace(
                        self._transition_item(record, "failed"),
                        error=failure.error,
                    )
                )
                self._repository.save_task(task)
            except Exception as exc:
                task = self._repository.get_task(task_id).replace_item(
                    replace(
                        self._transition_item(record, "failed"),
                        error=workflow_error(
                            "BATCH_ITEM_EXECUTION_FAILED", f"Preparation failed: {exc}"
                        ),
                    )
                )
                self._repository.save_task(task)

        task = self._repository.get_task(task_id)
        if task.state == "cancelling":
            return self._finish_cancel(task)
        if not prepared:
            task = self._transition_task(task, "failed")
            self._repository.save_task(task)
            return task

        task = self._transition_task(task, "running")
        self._repository.save_task(task)
        for item_id, prepared_ref in prepared.items():
            task = self._repository.get_task(task_id)
            if task.state == "cancelling":
                break
            record = task.item(item_id)
            if record.phase == "failed":
                continue
            record = self._transition_item(record, "running")
            task = task.replace_item(record)
            self._repository.save_task(task)
            staged: StagedPlot | None = None
            try:
                staged = self._executor.stage_plot(
                    record.work_item,
                    prepared_ref,
                    task.request.template,
                    task.execution_signature,
                    token,
                )
                self._validate_staged(task, record, staged)
                if token.cancelled:
                    self._executor.discard_staged(staged)
                    task = self._repository.get_task(task_id).replace_item(
                        self._transition_item(record, "cancelled")
                    )
                    self._repository.save_task(task)
                    break
                record = self._transition_item(record, "committing")
                task = self._repository.get_task(task_id).replace_item(record)
                self._repository.save_task(task)
                plot_ref = self._repository.commit_item(
                    OutputKey(task_id, task.request.action_id, item_id), item_id, staged
                )
                record = replace(
                    self._transition_item(record, "succeeded"),
                    plot_ref=plot_ref,
                    review_state="unconfirmed",
                )
                task = self._repository.get_task(task_id).replace_item(record)
                self._repository.save_task(task)
            except WorkflowFailure as failure:
                if staged is not None:
                    self._executor.discard_staged(staged)
                current = self._repository.get_task(task_id).item(item_id)
                failed = replace(self._transition_item(current, "failed"), error=failure.error)
                task = self._repository.get_task(task_id).replace_item(failed)
                self._repository.save_task(task)
            except Exception as exc:
                if staged is not None:
                    self._executor.discard_staged(staged)
                current = self._repository.get_task(task_id).item(item_id)
                failed = replace(
                    self._transition_item(current, "failed"),
                    error=workflow_error(
                        "BATCH_ITEM_EXECUTION_FAILED", f"Batch item failed: {exc}"
                    ),
                )
                task = self._repository.get_task(task_id).replace_item(failed)
                self._repository.save_task(task)

        task = self._repository.get_task(task_id)
        if task.state == "cancelling":
            return self._finish_cancel(task)
        return self._finalize(task)

    def request_cancel(self, task_id: str) -> bool:
        task = self._repository.get_task(task_id)
        if task.state not in {"queued", "preparing", "running"}:
            return False
        task = self._transition_task(task, "cancelling")
        self._repository.save_task(task)
        if task.history[-2] == "queued":
            self._finish_cancel_without_outputs(task)
        return True

    def set_review_state(
        self, task_id: str, item_ids: tuple[str, ...], review_state: ReviewState
    ) -> BatchTaskRecord:
        task = self._repository.get_task(task_id)
        known = {item.work_item.item_id for item in task.items}
        if not set(item_ids).issubset(known):
            raise KeyError("unknown batch item")
        for item_id in item_ids:
            item = task.item(item_id)
            if item.phase != "succeeded":
                continue
            task = task.replace_item(replace(item, review_state=review_state))
        self._repository.save_task(task)
        return task

    def resolve_export_scope(
        self,
        task_id: str,
        scope: ExportScope,
        selected_item_ids: tuple[str, ...] = (),
    ) -> BatchExportSelection:
        task = self._repository.get_task(task_id)
        known = {item.work_item.item_id for item in task.items}
        if scope == "selected" and (
            not selected_item_ids or not set(selected_item_ids).issubset(known)
        ):
            raise KeyError("selected export scope contains no items or unknown items")
        selected = set(selected_item_ids)
        targets: list[PlotSpecRef] = []
        exclusions: list[ExportExclusion] = []
        for item in task.items:
            item_id = item.work_item.item_id
            if scope == "selected" and item_id not in selected:
                exclusions.append(ExportExclusion(item_id, "not_selected"))
            elif item.phase == "failed":
                exclusions.append(ExportExclusion(item_id, "failed"))
            elif item.phase == "cancelled":
                exclusions.append(ExportExclusion(item_id, "cancelled"))
            elif item.review_state == "excluded":
                exclusions.append(ExportExclusion(item_id, "excluded"))
            elif item.phase != "succeeded" or item.review_state != "confirmed":
                exclusions.append(ExportExclusion(item_id, "unconfirmed"))
            elif item.plot_ref is not None:
                targets.append(item.plot_ref)
        if not targets:
            raise WorkflowFailure(
                workflow_error(
                    "BATCH_EXPORT_SCOPE_EMPTY",
                    "The export scope contains no succeeded, confirmed batch items.",
                )
            )
        return BatchExportSelection(scope, tuple(targets), tuple(exclusions))

    def retry_failed(
        self, task_id: str, new_task_id: str, idempotency_key: str
    ) -> BatchSubmission | NeedsInput | Unsupported:
        previous = self._repository.get_task(task_id)
        failed = tuple(item.work_item for item in previous.items if item.phase == "failed")
        if not failed:
            raise ValueError("batch has no failed items to retry")
        request = replace(
            previous.request,
            task_id=new_task_id,
            idempotency_key=idempotency_key,
            batch_id=f"{previous.request.batch_id}.retry",
            items=failed,
            mapping_confirmed=True,
        )
        return self.submit(request)

    def _finalize(self, task: BatchTaskRecord) -> BatchTaskRecord:
        succeeded = tuple(item for item in task.items if item.phase == "succeeded")
        if not succeeded:
            task = self._transition_task(task, "failed")
            self._repository.save_task(task)
            return task
        task = self._transition_task(task, "committing")
        self._repository.save_task(task)
        try:
            batch = self._build_batch_spec(task)
            batch = self._repository.commit_batch(
                OutputKey(task.request.task_id, task.request.action_id, "batch"), batch
            )
        except Exception as exc:
            task = self._transition_task(self._repository.get_task(task.request.task_id), "failed")
            self._repository.save_task(task)
            raise WorkflowFailure(
                workflow_error("BATCH_COMMIT_FAILED", f"Batch commit failed: {exc}")
            ) from exc
        task = replace(self._repository.get_task(task.request.task_id), batch_spec=batch)
        terminal = (
            "succeeded"
            if all(item.phase == "succeeded" for item in task.items)
            else "partially_succeeded"
        )
        task = self._transition_task(task, terminal)
        self._repository.save_task(task)
        return task

    def _finish_cancel_without_outputs(self, task: BatchTaskRecord) -> BatchTaskRecord:
        for item in task.items:
            if item.phase not in {"succeeded", "failed", "cancelled"}:
                task = task.replace_item(replace(item, phase="cancelled"))
        if task.state != "cancelling":
            task = self._transition_task(task, "cancelling")
        task = self._transition_task(task, "cancelled")
        self._repository.save_task(task)
        return task

    def _finish_cancel(self, task: BatchTaskRecord) -> BatchTaskRecord:
        for item in task.items:
            if item.phase not in {"succeeded", "failed", "cancelled"}:
                task = task.replace_item(replace(item, phase="cancelled"))
        self._repository.save_task(task)
        if any(item.phase == "succeeded" for item in task.items):
            task = self._transition_task(task, "committing")
            self._repository.save_task(task)
            try:
                batch = self._repository.commit_batch(
                    OutputKey(task.request.task_id, task.request.action_id, "batch"),
                    self._build_batch_spec(task),
                )
            except Exception as exc:
                task = self._transition_task(
                    self._repository.get_task(task.request.task_id), "failed"
                )
                self._repository.save_task(task)
                raise WorkflowFailure(
                    workflow_error("BATCH_COMMIT_FAILED", f"Cancelled batch commit failed: {exc}")
                ) from exc
            task = replace(self._repository.get_task(task.request.task_id), batch_spec=batch)
            task = self._transition_task(task, "partially_succeeded")
        else:
            task = self._transition_task(task, "cancelled")
        self._repository.save_task(task)
        return task

    def _build_batch_spec(self, task: BatchTaskRecord) -> BatchSpec:
        succeeded = tuple(item for item in task.items if item.phase == "succeeded")
        return BatchSpec(
            batch_id=task.request.batch_id,
            batch_version=1,
            dataset_signature=task.execution_signature.dataset_signature,
            execution_signature=task.execution_signature,
            dataset_version_refs=tuple(
                cast("PreparedDatasetRef", item.prepared_ref) for item in succeeded
            ),
            shared_field_mapping=task.request.template.field_mapping_ref,
            shared_preparation=task.request.template.preparation_spec_ref,
            shared_plot_calculation=task.request.template.plot_calculation_spec_ref,
            plot_template_ref=PlotSpecRef(
                plot_id=task.request.template.plot_template.plot_id,
                plot_version=task.request.template.plot_template.plot_version,
                content_hash=canonical_hash(task.request.template.plot_template),
            ),
            shared_style=task.request.template.shared_style,
            axis_policy=task.request.template.axis_policy,
            plot_overrides=tuple(
                BatchPlotOverride(
                    item_id=item.work_item.item_id,
                    prepared_dataset_ref=cast("PreparedDatasetRef", item.prepared_ref),
                )
                for item in succeeded
            ),
            item_states=tuple(
                BatchItemState(
                    item_id=item.work_item.item_id,
                    state=item.phase,
                    error_code=None if item.error is None else item.error.code,
                    plot_version_ref=item.plot_ref,
                    review_state=item.review_state,
                )
                for item in task.items
            ),
        )

    def _execution_signature(
        self,
        request: BatchSubmissionRequest,
        dataset_signature: DatasetSignature,
    ) -> BatchExecutionSignature:
        template = request.template
        if template.plot_template.resolved_style != template.shared_style:
            raise WorkflowFailure(
                workflow_error(
                    "BATCH_SIGNATURE_MISMATCH",
                    "The plot template and shared batch style differ.",
                )
            )
        payload: dict[str, JsonValue] = {
            "dataset_signature": dataset_signature.model_dump(mode="json"),
            "field_mapping_hash": template.field_mapping_ref.content_hash,
            "preparation_spec_hash": template.preparation_spec_ref.content_hash,
            "plot_calculation_spec_hash": (
                None
                if template.plot_calculation_spec_ref is None
                else template.plot_calculation_spec_ref.content_hash
            ),
            "chart_type_id": template.plot_template.chart_type_id,
            "plot_template_hash": canonical_hash(template.plot_template),
            "style_hash": canonical_hash(template.shared_style),
        }
        return BatchExecutionSignature(
            dataset_signature=dataset_signature,
            field_mapping_hash=template.field_mapping_ref.content_hash,
            preparation_spec_hash=template.preparation_spec_ref.content_hash,
            plot_calculation_spec_hash=(
                None
                if template.plot_calculation_spec_ref is None
                else template.plot_calculation_spec_ref.content_hash
            ),
            chart_type_id=template.plot_template.chart_type_id,
            plot_template_hash=canonical_hash(template.plot_template),
            style_hash=canonical_hash(template.shared_style),
            content_hash=canonical_hash(payload),
        )

    def _validate_staged(
        self, task: BatchTaskRecord, item: BatchItemRecord, staged: StagedPlot
    ) -> None:
        if staged.execution_signature_hash != task.execution_signature.content_hash:
            raise WorkflowFailure(
                workflow_error("BATCH_SIGNATURE_MISMATCH", "Executor changed the batch signature.")
            )
        plot = staged.plot_spec
        prepared_ref = item.prepared_ref
        if (
            plot.chart_type_id != task.execution_signature.chart_type_id
            or plot.resolved_style != task.request.template.shared_style
            or prepared_ref is None
            or prepared_ref not in plot.prepared_data_refs
        ):
            raise WorkflowFailure(
                workflow_error(
                    "BATCH_SIGNATURE_MISMATCH",
                    "Staged output changed chart, style, or prepared input identity.",
                )
            )

    def _transition_task(self, task: BatchTaskRecord, state: str) -> BatchTaskRecord:
        allowed = _ALLOWED_TASK_TRANSITIONS[task.state]
        if state not in allowed:
            raise RuntimeError(f"illegal task transition {task.state} -> {state}")
        return replace(
            task,
            state=cast("ExecutionTaskState", state),
            sequence=task.sequence + 1,
            history=(*task.history, cast("ExecutionTaskState", state)),
        )

    def _transition_item(self, item: BatchItemRecord, phase: str) -> BatchItemRecord:
        if phase not in _ALLOWED_ITEM_TRANSITIONS[item.phase]:
            raise RuntimeError(f"illegal item transition {item.phase} -> {phase}")
        return replace(item, phase=cast("BatchItemPhase", phase))

    def _request_hash(self, request: BatchSubmissionRequest) -> str:
        return canonical_hash(
            {
                "task_id": request.task_id,
                "project_id": request.project_id,
                "action_id": request.action_id,
                "batch_id": request.batch_id,
                "mapping_confirmed": request.mapping_confirmed,
                "items": [
                    {
                        "item_id": item.item_id,
                        "source_ref": item.source_ref.model_dump(mode="json"),
                        "dataset_signature": item.dataset_signature.model_dump(mode="json"),
                    }
                    for item in request.items
                ],
                "template": {
                    "field_mapping_ref": request.template.field_mapping_ref.model_dump(mode="json"),
                    "preparation_spec_ref": (
                        request.template.preparation_spec_ref.model_dump(mode="json")
                    ),
                    "plot_calculation_spec_ref": (
                        None
                        if request.template.plot_calculation_spec_ref is None
                        else request.template.plot_calculation_spec_ref.model_dump(mode="json")
                    ),
                    "plot_template": request.template.plot_template.model_dump(mode="json"),
                    "shared_style": request.template.shared_style.model_dump(mode="json"),
                    "axis_policy": request.template.axis_policy,
                },
            }
        )
