from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from plotagent.contracts.agent_tasks import (
    AgentIntentReady,
    TaskBudgetLimits,
    TaskEnvelope,
    TaskIntent,
)
from plotagent.contracts.agent_tools import ToolInvocation
from plotagent.contracts.base import SourceDatasetRef
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.workflows import DraftFieldBinding, TaskDraftItem
from plotagent.desktop_core.agent_foundation import (
    AgentFoundationError,
    DurableAgentCoreHost,
    DurableTaskCoordinator,
)
from plotagent.storage import (
    ImportCommitResult,
    ImportResource,
    ProjectDomainRepository,
    ProjectImportService,
    ProjectStore,
)
from plotagent.tasking import TaskLedgerRepository

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
FILES = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def envelope() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task:test",
        task_version=1,
        project_id="project:test",
        project_revision=0,
        original_instruction="Create one K01 line chart.",
        selected_sources=(
            SourceDatasetRef(
                source_dataset_id="source:test",
                source_version=1,
                content_hash="a" * 64,
            ),
        ),
        selected_profile_ids=("K01",),
        budget=TaskBudgetLimits(),
        created_at="2026-08-18T10:00:00Z",
    )


def intent(
    activation_id: str,
    *,
    task_id: str = "task:test",
    context_hash: str = "a" * 64,
) -> TaskIntent:
    item = TaskDraftItem(
        task_kind="create",
        item_id="item:test.1",
        plot_alias="plot_1",
        profile_id="K01",
        source_aliases=("data_1",),
        bindings=(
            DraftFieldBinding(
                role="x", source_alias="data_1", field_alias="data_1_field_1"
            ),
            DraftFieldBinding(
                role="y", source_alias="data_1", field_alias="data_1_field_2"
            ),
        ),
    )
    draft = TaskIntent(
        intent_id="intent:test",
        intent_version=1,
        task_id=task_id,
        task_version=1,
        created_by_activation_id=activation_id,
        summary="Create one K01 line chart.",
        items=(item,),
        context_hash=context_hash,
        content_hash="0" * 64,
    )
    payload = draft.model_dump(mode="json", exclude={"content_hash"})
    return draft.model_copy(update={"content_hash": canonical_hash(payload)})


def test_next_action_creates_one_idempotent_activation(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)

        first = coordinator.next_action("task:test")
        second = coordinator.next_action("task:test")
        assert first == second
        assert first["kind"] == "run_activation"
        activation = first["activation"]
        assert activation["task_version"] == 1
        assert activation["task_state"] == "created"
        assert activation["permission_phase"] == "p0_read"
        assert activation["activation_budget"]["timeout_ms"] == 35_000
        assert "inspect_source" in cast(list[str], activation["allowed_tools"])
        assert ledger.get_task("task:test").active_activation_id == activation["activation_id"]


def test_context_authority_stays_current_until_yield_then_waits_for_confirmation(
    tmp_path: Path,
) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)
        directive = coordinator.next_action("task:test")
        assert directive["kind"] == "run_activation"
        activation_id = str(directive["activation"]["activation_id"])

        running = ledger.mark_activation_running(activation_id)
        assert running.state == "created"
        assert running.task_version == 1
        staged = ledger.accept_yield(
            AgentIntentReady(
                activation_id=activation_id,
                task_id="task:test",
                task_version=1,
                intent=intent(activation_id),
            )
        )
        assert staged.state == "intent_staged"
        assert staged.task_version == 3

        waiting = coordinator.next_action("task:test")
        assert waiting == {
            "kind": "wait",
            "reason": "awaiting_confirmation",
            "task_state": "awaiting_confirmation",
        }
        assert ledger.get_task("task:test").task_version == 4


def test_core_host_prepares_exact_source_tools_and_validates_intent(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        imported = ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:basic", path=FILES / "csv_basic.csv")
        )
        assert isinstance(imported, ImportCommitResult)
        source = imported.datasets[0].source_dataset
        domain = ProjectDomainRepository(project)
        ledger = TaskLedgerRepository(project)
        task_envelope = TaskEnvelope(
            task_id="task:host-test",
            task_version=1,
            project_id="project:test",
            project_revision=domain.revision,
            original_instruction="Create one K01 line chart.",
            selected_sources=(
                SourceDatasetRef(
                    source_dataset_id=source.source_dataset_id,
                    source_version=source.source_version,
                    content_hash=source.content_hash,
                ),
            ),
            selected_profile_ids=("K01",),
            budget=TaskBudgetLimits(),
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        ledger.create_task(task_envelope)
        coordinator = DurableTaskCoordinator(ledger)
        directive = coordinator.next_action(task_envelope.task_id)
        assert directive["kind"] == "run_activation"
        activation_id = str(directive["activation"]["activation_id"])
        ledger.mark_activation_running(activation_id)

        host = DurableAgentCoreHost(project, domain, ledger)
        environment = host.prepare(activation_id)
        system_prompt = cast(str, environment["system_prompt"])
        assert "bind them directly without calling inspection tools" in system_prompt
        assert "Inspect rows only when unresolved data shape" in system_prompt
        context = cast(dict[str, object], environment["context"])
        selected_sources = cast(list[dict[str, object]], context["selected_sources"])
        assert selected_sources == [
            {
                "source_dataset_id": source.source_dataset_id,
                "source_version": source.source_version,
                "content_hash": source.content_hash,
            }
        ]
        source_contexts = cast(list[dict[str, object]], context["source_contexts"])
        assert source_contexts[0]["preview"] is None
        tool_names: set[object] = set()
        for item in cast(list[object], environment["tools"]):
            definition = cast(dict[str, object], item)
            contract = cast(dict[str, object], definition["contract"])
            tool_names.add(contract["tool_name"])
        activation = directive["activation"]
        assert tool_names == set(cast(list[str], activation["allowed_tools"]))

        arguments: JsonValue = {"source_alias": "data_1"}
        now = datetime.now(UTC)
        invocation = ToolInvocation(
            tool_call_id="toolcall:inspect-source",
            task_id=task_envelope.task_id,
            task_version=1,
            activation_id=activation_id,
            tool_name="inspect_source",
            permission_phase="p0_read",
            arguments_hash=canonical_hash(arguments),
            activation_tool_calls_before=0,
            activation_disclosed_scalars_before=0,
            expected_project_revision=domain.revision,
            deadline=(now + timedelta(seconds=3)).isoformat().replace("+00:00", "Z"),
        )
        result = host.invoke(
            invocation_value=invocation.model_dump(mode="json"),
            arguments=arguments,
        )
        assert result.status == "succeeded"
        assert result.provenance[0].content_hash == source.content_hash
        assert ledger.get_task(task_envelope.task_id).budget.usage.tool_calls == 1

        context_hash = cast(str, context["content_hash"])
        candidate = AgentIntentReady(
            activation_id=activation_id,
            task_id=task_envelope.task_id,
            task_version=1,
            intent=intent(
                activation_id,
                task_id=task_envelope.task_id,
                context_hash=context_hash,
            ),
        )
        intent_payload = candidate.intent.model_dump(mode="json", exclude={"content_hash"})
        candidate = candidate.model_copy(
            update={
                "intent": candidate.intent.model_copy(
                    update={"content_hash": canonical_hash(intent_payload)}
                )
            }
        )
        validated = host.validate_yield(
            activation_id, cast(JsonValue, candidate.model_dump(mode="json"))
        )
        assert validated.outcome == "intent_ready"
        staged = host.accept_yield(validated)
        assert staged.state == "intent_staged"
        plan = ledger.get_plan(task_envelope.task_id)
        assert plan.expected_project_revision == task_envelope.project_revision
        assert plan.items[0].profile_id == "K01"
        assert tuple(binding.role for binding in plan.items[0].bindings) == ("x", "y")
        assert domain.revision == task_envelope.project_revision

        stale = candidate.model_dump(mode="json")
        cast(dict[str, object], stale["intent"])["context_hash"] = "f" * 64
        with pytest.raises(AgentFoundationError) as caught:
            host.validate_yield(activation_id, cast(JsonValue, stale))
        assert caught.value.code == "YIELD_CONTEXT_STALE"


def test_core_host_rejects_invalid_intent_before_confirmation(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        imported = ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:basic", path=FILES / "csv_basic.csv")
        )
        assert isinstance(imported, ImportCommitResult)
        source = imported.datasets[0].source_dataset
        domain = ProjectDomainRepository(project)
        ledger = TaskLedgerRepository(project)
        task_envelope = TaskEnvelope(
            task_id="task:invalid-intent",
            task_version=1,
            project_id="project:test",
            project_revision=domain.revision,
            original_instruction="Create one K01 line chart.",
            selected_sources=(
                SourceDatasetRef(
                    source_dataset_id=source.source_dataset_id,
                    source_version=source.source_version,
                    content_hash=source.content_hash,
                ),
            ),
            selected_profile_ids=("K01",),
            budget=TaskBudgetLimits(),
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        ledger.create_task(task_envelope)
        coordinator = DurableTaskCoordinator(ledger)
        directive = coordinator.next_action(task_envelope.task_id)
        assert directive["kind"] == "run_activation"
        activation_id = str(directive["activation"]["activation_id"])
        ledger.mark_activation_running(activation_id)
        host = DurableAgentCoreHost(project, domain, ledger)
        prepared = host.prepare(activation_id)
        context = cast(dict[str, object], prepared["context"])
        candidate = AgentIntentReady(
            activation_id=activation_id,
            task_id=task_envelope.task_id,
            task_version=1,
            intent=intent(
                activation_id,
                task_id=task_envelope.task_id,
                context_hash=cast(str, context["content_hash"]),
            ),
        )
        bad_item = candidate.intent.items[0].model_copy(
            update={
                "bindings": (
                    DraftFieldBinding(
                        role="x",
                        source_alias="data_1",
                        field_alias="data_1_field_999",
                    ),
                    candidate.intent.items[0].bindings[1],
                )
            }
        )
        bad_intent = candidate.intent.model_copy(
            update={"items": (bad_item,), "content_hash": "0" * 64}
        )
        bad_intent = bad_intent.model_copy(
            update={
                "content_hash": canonical_hash(
                    bad_intent.model_dump(mode="json", exclude={"content_hash"})
                )
            }
        )
        bad = candidate.model_copy(update={"intent": bad_intent})
        with pytest.raises(AgentFoundationError) as caught:
            host.validate_yield(
                activation_id,
                cast(JsonValue, bad.model_dump(mode="json")),
            )
        assert caught.value.code == "FIELD_ALIAS_INVALID"
        assert ledger.get_task(task_envelope.task_id).state == "created"
        assert domain.revision == task_envelope.project_revision
