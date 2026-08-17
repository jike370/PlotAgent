from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from plotagent.contracts.agent_tasks import (
    AGENT_YIELD_ADAPTER,
    TASK_EVENT_ADAPTER,
    AgentActivation,
    AgentIntentReady,
    AgentRuntimeFailed,
    ExecutionGrant,
    ExecutionScope,
    IntentRef,
    SelectedPlotRef,
    SideEffectReceipt,
    TaskBudgetLimits,
    TaskBudgetSnapshot,
    TaskBudgetUsage,
    TaskCheckpoint,
    TaskCompletion,
    TaskEnvelope,
    TaskError,
    TaskIntent,
    TaskItemSnapshot,
    TaskStateTransitionEvent,
    ToolReceipt,
    VerificationClaim,
    VerificationReport,
    is_legal_task_item_transition,
    is_legal_task_transition,
)
from plotagent.contracts.base import ResourceRef
from plotagent.contracts.workflows import DraftFieldBinding, TaskDraftItem

HASH_A = "a" * 64
HASH_B = "b" * 64
NOW = "2026-08-18T10:00:00Z"
LATER = "2026-08-18T10:05:00Z"


def budget() -> TaskBudgetSnapshot:
    return TaskBudgetSnapshot(limits=TaskBudgetLimits(max_estimated_cost=10))


def intent() -> TaskIntent:
    item = TaskDraftItem(
        task_kind="create",
        item_id="item:test.1",
        plot_alias="plot_1",
        profile_id="K01",
        source_aliases=("data_1",),
        bindings=(
            DraftFieldBinding(
                role="x",
                source_alias="data_1",
                field_alias="data_1_field_1",
            ),
            DraftFieldBinding(
                role="y",
                source_alias="data_1",
                field_alias="data_1_field_2",
            ),
        ),
    )
    return TaskIntent(
        intent_id="intent:test",
        intent_version=1,
        task_id="task:test",
        task_version=1,
        created_by_activation_id="activation:test",
        summary="Create one line chart.",
        items=(item,),
        context_hash=HASH_A,
        content_hash=HASH_B,
    )


def intent_ref() -> IntentRef:
    return IntentRef(intent_id="intent:test", intent_version=1, content_hash=HASH_B)


def technical_error(*, retryable: bool = True) -> TaskError:
    return TaskError(
        code="RENDER_READBACK_MISMATCH",
        category="deterministic_technical",
        message="The native source binding did not match.",
        retryable=retryable,
        requires_user=False,
        side_effect_state="known_applied",
    )


def passed_report() -> VerificationReport:
    return VerificationReport(
        report_id="verification:test",
        task_id="task:test",
        task_version=1,
        intent=intent_ref(),
        item_id="item:test.1",
        status="passed",
        claims=(
            VerificationClaim(
                claim_id="binding.source",
                status="passed",
                expected="The plot uses the confirmed source fields.",
                observed="The native readback uses fields X and Y.",
            ),
        ),
        content_hash=HASH_A,
        verified_at=NOW,
    )


def test_task_envelope_requires_real_selection_and_unique_identity() -> None:
    envelope = TaskEnvelope(
        task_id="task:test",
        task_version=1,
        project_id="project:test",
        project_revision=0,
        original_instruction="Create a line chart.",
        selected_source_ids=("source:test",),
        selected_plots=(SelectedPlotRef(plot_id="plot:test", plot_version=1, profile_id="K01"),),
        authorized_resources=(
            ResourceRef(resource_id="resource:output", resource_kind="authorized_directory"),
        ),
        budget=TaskBudgetLimits(),
        created_at=NOW,
    )
    assert envelope.schema_version == "task-envelope.v2"

    with pytest.raises(ValidationError, match="at least one selected source or plot"):
        TaskEnvelope.model_validate(
            {
                **envelope.model_dump(),
                "selected_source_ids": (),
                "selected_plots": (),
            }
        )
    with pytest.raises(ValidationError, match="selections must be unique"):
        TaskEnvelope.model_validate(
            {**envelope.model_dump(), "selected_source_ids": ("source:test", "source:test")}
        )


def test_task_budget_rejects_usage_beyond_any_limit() -> None:
    assert budget().usage.tool_calls == 0
    with pytest.raises(ValidationError, match="usage cannot exceed"):
        TaskBudgetSnapshot(
            limits=TaskBudgetLimits(max_tool_calls=2),
            usage=TaskBudgetUsage(tool_calls=3),
        )


def test_intent_ready_yield_is_strictly_bound_to_activation() -> None:
    yielded = AgentIntentReady(
        activation_id="activation:test",
        task_id="task:test",
        task_version=1,
        intent=intent(),
    )
    decoded = AGENT_YIELD_ADAPTER.validate_json(yielded.model_dump_json())
    assert decoded.outcome == "intent_ready"

    with pytest.raises(ValidationError, match="must match"):
        AgentIntentReady(
            activation_id="activation:other",
            task_id="task:test",
            task_version=1,
            intent=intent(),
        )


def test_activation_requires_reason_specific_evidence_and_unique_tools() -> None:
    activation = AgentActivation(
        activation_id="activation:test",
        task_id="task:test",
        task_version=1,
        reason="verification_failed",
        task_state="repairing",
        original_instruction="Create a line chart.",
        confirmed_intent=intent_ref(),
        verification_report_ids=("verification:test",),
        allowed_tools=("inspect_source", "repair_plot"),
        permission_phase="p2_confirmed",
        activation_budget={"max_model_turns": 4},
        task_budget=budget(),
        deadline=LATER,
        created_at=NOW,
    )
    assert activation.reason == "verification_failed"

    with pytest.raises(ValidationError, match="need a verification report"):
        AgentActivation.model_validate(
            {**activation.model_dump(), "verification_report_ids": ()}
        )
    with pytest.raises(ValidationError, match="must be unique"):
        AgentActivation.model_validate(
            {**activation.model_dump(), "allowed_tools": ("inspect_source", "inspect_source")}
        )


def test_execution_grant_has_unique_narrow_item_scopes() -> None:
    scope = ExecutionScope(item_id="item:test.1", operations=("create_plot", "bind_fields"))
    grant = ExecutionGrant(
        grant_id="grant:test",
        task_id="task:test",
        task_version=1,
        intent=intent_ref(),
        expected_project_revision=3,
        permission_phase="p2_confirmed",
        scopes=(scope,),
        issued_at=NOW,
        expires_at=LATER,
        content_hash=HASH_A,
    )
    assert grant.scopes[0].operations == ("create_plot", "bind_fields")

    with pytest.raises(ValidationError, match="item scopes must be unique"):
        ExecutionGrant.model_validate({**grant.model_dump(), "scopes": (scope, scope)})


def test_tool_receipt_enforces_permissions_idempotency_and_outcome() -> None:
    receipt = ToolReceipt(
        receipt_id="receipt:test",
        task_id="task:test",
        task_version=1,
        activation_id="activation:test",
        item_id="item:test.1",
        tool_call_id="call.test",
        tool_name="create_plot",
        permission_phase="p2_confirmed",
        outcome="succeeded",
        idempotency_key="idem.test",
        input_hash=HASH_A,
        output_hash=HASH_B,
        project_revision_before=2,
        project_revision_after=3,
        side_effects=(
            SideEffectReceipt(
                effect_kind="plot_version",
                object_id="plot:test",
                object_version=1,
            ),
        ),
        started_at=NOW,
        finished_at=LATER,
    )
    assert receipt.side_effects[0].object_version == 1

    with pytest.raises(ValidationError, match="require an idempotency key"):
        ToolReceipt.model_validate({**receipt.model_dump(), "idempotency_key": None})
    with pytest.raises(ValidationError, match="cannot change the project revision"):
        ToolReceipt.model_validate({**receipt.model_dump(), "permission_phase": "p0_read"})
    with pytest.raises(ValidationError, match="require output_hash"):
        ToolReceipt.model_validate({**receipt.model_dump(), "output_hash": None})
    with pytest.raises(ValidationError, match="must advance project revision"):
        ToolReceipt.model_validate(
            {**receipt.model_dump(), "project_revision_after": 2}
        )
    with pytest.raises(ValidationError, match="require concrete effects"):
        ToolReceipt.model_validate({**receipt.model_dump(), "side_effects": ()})


def test_verification_report_status_is_derived_from_required_claims() -> None:
    assert passed_report().status == "passed"
    failed_claim = VerificationClaim(
        claim_id="binding.source",
        status="failed",
        expected="The source binding is preserved.",
        observed="The source binding differs.",
        repair_scope=("plot_1",),
        error=technical_error(),
    )
    with pytest.raises(ValidationError, match="must match its required claims"):
        VerificationReport.model_validate(
            {
                **passed_report().model_dump(),
                "claims": (failed_claim,),
                "status": "passed",
            }
        )


def test_completed_checkpoint_requires_every_item_and_verification_evidence() -> None:
    checkpoint = TaskCheckpoint(
        checkpoint_id="checkpoint:test",
        task_id="task:test",
        task_version=1,
        state="completed_verified",
        project_revision=4,
        last_event_sequence=9,
        intent=intent_ref(),
        items=(
            TaskItemSnapshot(
                item_id="item:test.1",
                state="succeeded",
                output_plot_id="plot:test",
                output_plot_version=1,
                verification_report_ids=("verification:test",),
            ),
        ),
        budget=budget(),
        completion=TaskCompletion(
            completed_at=LATER,
            final_project_revision=4,
            required_report_ids=("verification:test",),
        ),
        updated_at=LATER,
        content_hash=HASH_A,
    )
    assert checkpoint.completion is not None

    with pytest.raises(ValidationError, match="every task item to succeed"):
        TaskCheckpoint.model_validate(
            {
                **checkpoint.model_dump(),
                "items": (
                    TaskItemSnapshot(
                        item_id="item:test.1",
                        state="failed",
                        last_error=technical_error(retryable=False),
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="Only completed tasks|only completed tasks"):
        TaskCheckpoint.model_validate({**checkpoint.model_dump(), "state": "partial"})


def test_state_transition_tables_close_terminal_states_and_allow_repair() -> None:
    assert is_legal_task_transition("verifying", "repairing")
    assert is_legal_task_transition("partial", "executing")
    assert not is_legal_task_transition("completed_verified", "executing")
    assert is_legal_task_item_transition("repairable_failed", "running")
    assert not is_legal_task_item_transition("succeeded", "running")


def test_task_event_union_rejects_illegal_transition_and_wrong_discriminator() -> None:
    event = TaskStateTransitionEvent(
        event_id="event:test",
        task_id="task:test",
        task_version=1,
        sequence=1,
        occurred_at=NOW,
        previous_state="created",
        next_state="investigating",
        reason_code="TASK_STARTED",
    )
    decoded = TASK_EVENT_ADAPTER.validate_json(event.model_dump_json())
    assert decoded.event_type == "task_state_transition"

    with pytest.raises(ValidationError, match="illegal task state transition"):
        TaskStateTransitionEvent.model_validate(
            {**event.model_dump(), "previous_state": "completed_verified"}
        )
    with pytest.raises(ValidationError):
        TASK_EVENT_ADAPTER.validate_json(
            json.dumps({**event.model_dump(mode="json"), "event_type": "unknown"})
        )


def test_runtime_failed_yield_requires_runtime_category() -> None:
    runtime_error = TaskError(
        code="PROVIDER_DISCONNECTED",
        category="runtime",
        message="The provider connection closed.",
        retryable=True,
        requires_user=False,
        side_effect_state="known_none",
    )
    assert AgentRuntimeFailed(
        activation_id="activation:test",
        task_id="task:test",
        task_version=1,
        error=runtime_error,
    ).outcome == "runtime_failed"

    with pytest.raises(ValidationError, match="runtime error"):
        AgentRuntimeFailed(
            activation_id="activation:test",
            task_id="task:test",
            task_version=1,
            error=technical_error(),
        )
