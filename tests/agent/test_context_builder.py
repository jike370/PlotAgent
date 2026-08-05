from __future__ import annotations

import dataclasses

import pytest

from plotagent.agent.context import ContextBudget, ContextBuilder, ConversationStateReducer
from plotagent.agent.errors import AgentRuntimeError
from plotagent.contracts.canonical import canonical_json
from tests.agent.helpers import context_request


def test_context_is_deterministic_and_obeys_disclosure_hard_budgets() -> None:
    request = context_request(field_count=250, row_count=40)
    builder = ContextBuilder()

    first = builder.build(request)
    second = builder.build(request)

    assert first == second
    assert first.context_hash == second.context_hash
    assert len(first.selected_context.fields) == 12
    assert len(first.selected_context.sample_rows) == 16
    assert first.data_disclosure.field_count == 12
    assert first.data_disclosure.row_count == 16
    assert first.data_disclosure.scalar_count == 192
    assert "field_249" not in canonical_json(first)


def test_context_byte_budget_trims_rows_without_leaking_full_table() -> None:
    request = context_request(field_count=12, row_count=40)
    huge_rows = tuple(
        dataclasses.replace(
            row,
            values={key: "sensitive-" + "x" * 240 for key in row.values},
        )
        for row in request.project.sample_rows
    )
    request = dataclasses.replace(
        request,
        project=dataclasses.replace(request.project, sample_rows=huge_rows),
    )
    envelope = ContextBuilder(ContextBudget(max_bytes=8_000)).build(request)

    assert len(canonical_json(envelope).encode()) <= 8_000
    assert envelope.data_disclosure.row_count < 16
    assert envelope.data_disclosure.scalar_count <= 200


def test_disclosure_permission_and_retention_are_enforced_before_egress() -> None:
    request = context_request()
    unacknowledged = dataclasses.replace(
        request,
        disclosure_grant=dataclasses.replace(
            request.disclosure_grant, retention_acknowledged=False
        ),
    )
    with pytest.raises(AgentRuntimeError) as captured:
        ContextBuilder().build(unacknowledged)
    assert captured.value.code == "PROVIDER_RETENTION_UNACKNOWLEDGED"

    denied = dataclasses.replace(request, required_categories=frozenset({"sample"}))
    denied = dataclasses.replace(
        denied,
        disclosure_grant=dataclasses.replace(
            denied.disclosure_grant,
            allowed_categories=frozenset({"user_instruction", "chart_capabilities"}),
        ),
    )
    with pytest.raises(AgentRuntimeError) as captured:
        ContextBuilder().build(denied)
    assert captured.value.code == "EGRESS_PERMISSION_DENIED"


def test_conversation_target_changes_only_through_local_reducer() -> None:
    request = context_request()
    reducer = ConversationStateReducer()
    updated_target = request.project.target.model_copy(
        update={"object_version": 2, "content_hash": "b" * 64}
    )

    updated = reducer.select_target(request.conversation_state, updated_target)

    assert updated.current_target == updated_target
    assert updated.state_version == request.conversation_state.state_version + 1
    assert request.conversation_state.current_target.object_version == 1
