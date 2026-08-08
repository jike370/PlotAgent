"""Persistent, bounded task-plan runtime contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.agent_context import ContextObjectRef
from plotagent.contracts.base import SCHEMA_VERSION, SchemaVersion, Sha256, StrictModel, Token
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import ActionPlan, BusinessAction
from plotagent.contracts.project_context import ContextSnapshotId, ConversationId

TaskItemId = Annotated[
    str,
    StringConstraints(
        pattern=r"^taskitem:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
TaskAttemptId = Annotated[
    str,
    StringConstraints(
        pattern=r"^attempt:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
TaskItemState = Literal[
    "pending",
    "ready",
    "running",
    "committing",
    "succeeded",
    "failed",
    "interrupted",
    "blocked",
    "stale",
    "skipped",
    "cancelled",
]
TaskPlanState = Literal[
    "draft",
    "needs_confirmation",
    "ready",
    "running",
    "partial_success",
    "succeeded",
    "failed",
    "interrupted",
    "needs_input",
    "stale",
    "cancelled",
]
ConfirmationState = Literal["not_required", "pending", "confirmed", "rejected"]


class TaskFailure(StrictModel):
    code: Token
    message: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    retryable: bool
    details_hash: Sha256 | None = None


class TaskOutputRef(StrictModel):
    output_slot: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,63}$", strict=True),
    ]
    output_kind: Literal["object", "artifact", "result"]
    object_ref: ContextObjectRef | None = None
    content_hash: Sha256 | None = None
    summary: Annotated[str, StringConstraints(max_length=256, strict=True)] = ""

    @model_validator(mode="after")
    def output_has_authoritative_identity(self) -> TaskOutputRef:
        if self.output_kind == "object" and self.object_ref is None:
            raise ValueError("object outputs require an object_ref")
        if self.output_kind == "artifact" and self.content_hash is None:
            raise ValueError("artifact outputs require a content_hash")
        return self


class TaskItemSnapshot(StrictModel):
    task_item_id: TaskItemId
    action: BusinessAction
    state: TaskItemState = "pending"
    depends_on: tuple[TaskItemId, ...] = ()
    expected_objects: tuple[ContextObjectRef, ...] = ()
    idempotency_key: Token
    output_slots: Annotated[tuple[str, ...], Field(min_length=1, max_length=8)]
    outputs: tuple[TaskOutputRef, ...] = ()
    attempt_count: Annotated[int, Field(ge=0, le=32)] = 0
    failure: TaskFailure | None = None

    @model_validator(mode="after")
    def item_payload_is_consistent(self) -> TaskItemSnapshot:
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("task dependencies must be unique")
        if len(set(self.output_slots)) != len(self.output_slots):
            raise ValueError("task output slots must be unique")
        output_slots = tuple(item.output_slot for item in self.outputs)
        if len(set(output_slots)) != len(output_slots):
            raise ValueError("task outputs must be unique by slot")
        if not set(output_slots).issubset(self.output_slots):
            raise ValueError("task output must use a declared slot")
        if self.state == "succeeded" and self.failure is not None:
            raise ValueError("succeeded task item cannot retain a failure")
        if self.state == "failed" and self.failure is None:
            raise ValueError("failed task item requires a failure")
        return self


class TaskPlanSnapshot(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    plan_id: Annotated[
        str,
        StringConstraints(pattern=r"^plan:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    conversation_id: ConversationId
    context_snapshot_id: ContextSnapshotId
    context_hash: Sha256
    project_revision: Annotated[int, Field(ge=0)]
    source_plan: ActionPlan
    source_plan_hash: Sha256
    state: TaskPlanState
    confirmation_state: ConfirmationState
    items: Annotated[tuple[TaskItemSnapshot, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def plan_matches_source_and_dependencies(self) -> TaskPlanSnapshot:
        if self.plan_id != self.source_plan.plan_id:
            raise ValueError("runtime plan id must match the source plan")
        if self.source_plan_hash != canonical_hash(self.source_plan):
            raise ValueError("source plan hash must match the source plan")
        if len(self.items) != len(self.source_plan.actions):
            raise ValueError("runtime plan must contain one item per source action")
        item_ids = tuple(item.task_item_id for item in self.items)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("task item ids must be unique")
        seen: set[str] = set()
        for item, action in zip(self.items, self.source_plan.actions, strict=True):
            if item.action != action:
                raise ValueError("task item action must preserve source-plan order")
            if any(dependency not in seen for dependency in item.depends_on):
                raise ValueError("task items may depend only on earlier items")
            seen.add(item.task_item_id)
        if self.source_plan.confirmation == "required":
            if self.confirmation_state == "not_required":
                raise ValueError("required confirmation cannot be marked not_required")
        elif self.confirmation_state != "not_required":
            raise ValueError("non-required confirmation must remain not_required")
        return self


class TaskAttemptSnapshot(StrictModel):
    attempt_id: TaskAttemptId
    task_item_id: TaskItemId
    attempt_number: Annotated[int, Field(ge=1, le=32)]
    state: Literal["running", "succeeded", "failed", "interrupted", "cancelled"]
    started_at: Token
    ended_at: Token | None = None
    failure: TaskFailure | None = None


class TaskCheckpoint(StrictModel):
    plan_id: Annotated[
        str,
        StringConstraints(pattern=r"^plan:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    task_item_id: TaskItemId
    checkpoint_key: Token
    payload_hash: Sha256
    created_at: Token
