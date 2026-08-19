from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from plotagent.contracts.agent_tasks import (
    AgentBlocked,
    AgentIntentReady,
    AgentNeedsInput,
    SelectedPlotRef,
    TaskBudgetLimits,
    TaskEnvelope,
    TaskIntent,
)
from plotagent.contracts.agent_tools import ToolInvocation
from plotagent.contracts.base import SourceDatasetRef
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.workflows import (
    DraftFieldBinding,
    DraftSetTitle,
    FilterPredicate,
    FilterRows,
    InputQuestion,
    SortKey,
    SortRows,
    TaskDraftItem,
)
from plotagent.desktop_core.agent_foundation import (
    AgentFoundationError,
    DurableAgentCoreHost,
    DurableTaskCoordinator,
)
from plotagent.engine import EngineDataRef, FieldBinding, PlotDocument
from plotagent.storage import (
    ImportCommitResult,
    ImportResource,
    ProjectDomainRepository,
    ProjectImportService,
    ProjectStore,
)
from plotagent.storage.errors import StorageProblem
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
    intent_version: int = 1,
    task_version: int = 1,
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
        intent_version=intent_version,
        task_id=task_id,
        task_version=task_version,
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
        assert activation["activation_budget"]["max_model_turns"] == 10
        assert activation["activation_budget"]["timeout_ms"] is None
        assert activation["deadline"] is None
        assert "inspect_source" in cast(list[str], activation["allowed_tools"])
        assert ledger.get_task("task:test").active_activation_id == activation["activation_id"]


def test_inflight_activation_is_aborted_and_resumed_after_restart(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        first_coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)
        first = first_coordinator.next_action("task:test")
        assert first["kind"] == "run_activation"
        first_id = str(first["activation"]["activation_id"])
        ledger.mark_activation_running(first_id)

        recovered = ledger.recover_inflight_activations()
        assert recovered == ("task:test",)
        restarted = DurableTaskCoordinator(
            ledger, recovered_task_ids=recovered
        ).next_action("task:test")
        assert restarted["kind"] == "run_activation"
        assert restarted["activation"]["reason"] == "resume_after_restart"
        assert restarted["activation"]["activation_id"] != first_id
        _, old_status = ledger.get_activation(first_id)
        assert old_status == "aborted"


def test_blocked_task_resumes_only_after_explicit_external_clear(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)
        first = coordinator.next_action("task:test")
        activation_id = str(first["activation"]["activation_id"])
        ledger.mark_activation_running(activation_id)
        blocked = ledger.accept_yield(
            AgentBlocked(
                activation_id=activation_id,
                task_id="task:test",
                task_version=1,
                blocker_code="ORIGIN_UNAVAILABLE",
                message="Origin is unavailable.",
                resume_condition="Origin becomes available.",
                retryable=True,
            )
        )
        assert blocked.state == "blocked"
        assert coordinator.next_action("task:test")["reason"] == "blocked"

        resumed = ledger.record_user_event(
            "task:test",
            expected_task_version=blocked.task_version,
            action="resumed",
            user_event_id="user-event:resume.1",
            payload_hash="d" * 64,
        )
        assert resumed.state == "investigating"
        continuation = coordinator.next_action("task:test")
        assert continuation["kind"] == "run_activation"
        assert continuation["activation"]["reason"] == "external_blocker_cleared"


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


def test_rejected_intent_is_terminal_and_cannot_be_confirmed(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)
        directive = coordinator.next_action("task:test")
        activation_id = str(directive["activation"]["activation_id"])
        ledger.mark_activation_running(activation_id)
        ledger.accept_yield(
            AgentIntentReady(
                activation_id=activation_id,
                task_id="task:test",
                task_version=1,
                intent=intent(activation_id),
            )
        )
        waiting = coordinator.next_action("task:test")
        assert waiting["reason"] == "awaiting_confirmation"
        pending = ledger.get_task("task:test")

        rejected = ledger.record_user_event(
            "task:test",
            expected_task_version=pending.task_version,
            action="rejected",
            user_event_id="user-event:reject.1",
            payload_hash=pending.intent.content_hash,
        )
        assert rejected.state == "rejected"
        assert rejected.items == pending.items
        assert coordinator.next_action("task:test") == {
            "kind": "wait",
            "reason": "terminal",
            "task_state": "rejected",
        }
        with pytest.raises(StorageProblem):
            ledger.record_user_event(
                "task:test",
                expected_task_version=rejected.task_version,
                action="confirmed",
                user_event_id="user-event:confirm-after-reject.1",
                payload_hash=pending.intent.content_hash,
            )


def test_user_correction_creates_next_intent_version_and_requires_reconfirmation(
    tmp_path: Path,
) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        ledger = TaskLedgerRepository(project)
        ledger.create_task(envelope())
        coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)
        first = coordinator.next_action("task:test")
        assert first["kind"] == "run_activation"
        first_id = str(first["activation"]["activation_id"])
        ledger.mark_activation_running(first_id)
        ledger.accept_yield(
            AgentIntentReady(
                activation_id=first_id,
                task_id="task:test",
                task_version=1,
                intent=intent(first_id),
            )
        )
        waiting = coordinator.next_action("task:test")
        assert waiting["reason"] == "awaiting_confirmation"
        checkpoint = ledger.get_task("task:test")
        corrected = ledger.record_user_event(
            "task:test",
            expected_task_version=checkpoint.task_version,
            action="corrected",
            user_event_id="user-event:correct.1",
            payload_hash="b" * 64,
            message="Use the third numeric field for Y.",
        )
        assert corrected.state == "investigating"

        continuation = coordinator.next_action("task:test")
        assert continuation["kind"] == "run_activation"
        activation = continuation["activation"]
        assert activation["reason"] == "user_corrected"
        assert activation["current_user_message"] == "Use the third numeric field for Y."
        assert activation["confirmed_intent"]["intent_version"] == 1
        continuation_id = str(activation["activation_id"])
        ledger.mark_activation_running(continuation_id)
        ledger.accept_yield(
            AgentIntentReady(
                activation_id=continuation_id,
                task_id="task:test",
                task_version=int(activation["task_version"]),
                intent=intent(
                    continuation_id,
                    intent_version=2,
                    task_version=int(activation["task_version"]),
                ),
            )
        )
        reconfirm = coordinator.next_action("task:test")
        assert reconfirm == {
            "kind": "wait",
            "reason": "awaiting_reconfirmation",
            "task_state": "awaiting_reconfirmation",
        }
        assert ledger.get_intent("task:test").intent_version == 2


def test_first_intent_after_clarification_is_grounded_in_the_user_answer(
    tmp_path: Path,
) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        imported = ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:basic", path=FILES / "csv_basic.csv")
        )
        assert isinstance(imported, ImportCommitResult)
        source = imported.datasets[0].source_dataset
        domain = ProjectDomainRepository(project)
        ledger = TaskLedgerRepository(project)
        task_envelope = TaskEnvelope(
            task_id="task:clarified-profile",
            task_version=1,
            project_id="project:test",
            project_revision=domain.revision,
            original_instruction="用这张表画一张合适的图。",
            selected_sources=(
                SourceDatasetRef(
                    source_dataset_id=source.source_dataset_id,
                    source_version=source.source_version,
                    content_hash=source.content_hash,
                ),
            ),
            budget=TaskBudgetLimits(),
            created_at="2026-08-18T10:00:00Z",
        )
        ledger.create_task(task_envelope)
        coordinator = DurableTaskCoordinator(ledger, clock=lambda: NOW)
        first = coordinator.next_action(task_envelope.task_id)
        first_id = str(first["activation"]["activation_id"])
        ledger.mark_activation_running(first_id)
        first_host = DurableAgentCoreHost(project, domain, ledger)
        first_host.prepare(first_id)
        needs_input = AgentNeedsInput(
            activation_id=first_id,
            task_id=task_envelope.task_id,
            task_version=1,
            questions=(
                InputQuestion(
                    question_key="chart_type",
                    prompt="请选择图表类型。",
                    answer_kind="profile",
                    choices=("K01", "K03"),
                ),
            ),
        )
        awaiting = first_host.accept_yield(needs_input)
        assert awaiting.state == "awaiting_input"

        answered = ledger.record_user_event(
            task_envelope.task_id,
            expected_task_version=awaiting.task_version,
            action="answered",
            user_event_id="user-event:clarified-profile.1",
            payload_hash="b" * 64,
            message="创建 K01 折线图，time 作为 X，信号作为 Y。",
        )
        assert answered.state == "investigating"
        continuation = coordinator.next_action(task_envelope.task_id)
        continuation_id = str(continuation["activation"]["activation_id"])
        continuation_version = int(continuation["activation"]["task_version"])
        ledger.mark_activation_running(continuation_id)
        continuation_host = DurableAgentCoreHost(project, domain, ledger)
        environment = continuation_host.prepare(continuation_id)
        context = cast(dict[str, object], environment["context"])
        clarified_intent = intent(
            continuation_id,
            task_id=task_envelope.task_id,
            task_version=continuation_version,
            context_hash=cast(str, context["content_hash"]),
        )
        candidate = AgentIntentReady(
            activation_id=continuation_id,
            task_id=task_envelope.task_id,
            task_version=continuation_version,
            intent=clarified_intent,
        )
        validated = continuation_host.validate_yield(
            continuation_id,
            cast(JsonValue, candidate.model_dump(mode="json")),
        )
        staged = continuation_host.accept_yield(validated)
        assert staged.state == "intent_staged"
        assert ledger.get_plan(task_envelope.task_id).items[0].profile_id == "K01"


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
        assert "Preserve every explicit Field-to-role mapping exactly" in system_prompt
        assert "Every source_alias and field_alias is an opaque Core identifier" in system_prompt
        assert "never use a display name such as X or Response" in system_prompt
        assert "emit concatenate_sources directly" in system_prompt
        assert "call compare_schemas only when those sequences differ" in system_prompt
        assert "represent palette identity and reverse as independent fields" in system_prompt
        assert "Core derives that integrity field" in system_prompt
        assert "perform a completeness check against the original instruction" in system_prompt
        assert "Never silently omit one requested change" in system_prompt
        assert "requires both a filter_rows predicate" in system_prompt
        assert "a following sort_rows key" in system_prompt
        assert "a draft containing only x/y bindings is incomplete" in system_prompt
        assert "never use needs_input to ask the user to confirm a plan" in system_prompt
        assert "product's confirmation card request authorization" in system_prompt
        assert "Never return cancelled from submit_agent_yield" in system_prompt
        yield_schema = cast(dict[str, object], environment["yield_schema"])
        definitions = cast(dict[str, object], yield_schema["$defs"])
        assert "AgentCancelled" not in definitions
        discriminator = cast(dict[str, object], yield_schema["discriminator"])
        mapping = cast(dict[str, object], discriminator["mapping"])
        assert "cancelled" not in mapping
        assert all(
            cast(dict[str, object], variant).get("$ref") != "#/$defs/AgentCancelled"
            for variant in cast(list[object], yield_schema["oneOf"])
        )
        intent_schema = cast(dict[str, object], definitions["TaskIntent"])
        assert "content_hash" not in cast(dict[str, object], intent_schema["properties"])
        assert "content_hash" not in cast(list[str], intent_schema["required"])
        binding_schema = cast(dict[str, object], definitions["DraftFieldBinding"])
        binding_properties = cast(dict[str, object], binding_schema["properties"])
        field_alias_schema = cast(dict[str, object], binding_properties["field_alias"])
        assert "never a display name" in cast(str, field_alias_schema["description"])
        concatenate_schema = cast(dict[str, object], definitions["ConcatenateSources"])
        concatenate_properties = cast(dict[str, object], concatenate_schema["properties"])
        source_label_schema = cast(dict[str, object], concatenate_properties["source_label_field"])
        assert "downstream bindings" in cast(str, source_label_schema["description"])
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

        with pytest.raises(AgentFoundationError) as cancellation:
            host.validate_yield(
                activation_id,
                {
                    "outcome": "cancelled",
                    "activation_id": activation_id,
                    "task_id": task_envelope.task_id,
                    "task_version": 1,
                    "message": "Cancel this activation.",
                },
            )
        assert cancellation.value.code == "MODEL_CANCELLATION_FORBIDDEN"

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
        model_candidate = candidate.model_dump(mode="json")
        model_intent = cast(dict[str, object], model_candidate["intent"])
        model_intent.pop("content_hash")
        # Real providers commonly omit fields whose value is the schema default.  Core
        # must hash the normalized intent, not the pre-validation JSON shape.
        model_intent.pop("semantic_decisions")
        model_item = cast(list[dict[str, object]], model_intent["items"])[0]
        model_item.pop("target_plot_alias")
        model_item.pop("data_operations")
        model_item.pop("visual_actions")
        validated = host.validate_yield(activation_id, cast(JsonValue, model_candidate))
        assert validated.outcome == "intent_ready"
        assert validated.intent.content_hash == canonical_hash(
            validated.intent.model_dump(mode="json", exclude={"content_hash"})
        )
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


def test_unselected_chart_choice_requires_a_literal_user_anchor() -> None:
    assert DurableAgentCoreHost._instruction_explicitly_names_profile(
        "请创建一个折线图。", "K01"
    )
    assert DurableAgentCoreHost._instruction_explicitly_names_profile(
        "Create a Line Graph from this table.", "K01"
    )
    assert DurableAgentCoreHost._instruction_explicitly_names_profile(
        "请创建 K01。", "K01"
    )
    assert not DurableAgentCoreHost._instruction_explicitly_names_profile(
        "用这张表画一张图。", "K01"
    )


def test_core_host_authorizes_an_existing_plot_edit_without_a_source(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        domain = ProjectDomainRepository(project)
        ledger = TaskLedgerRepository(project)
        task_envelope = TaskEnvelope(
            task_id="task:edit-existing",
            task_version=1,
            project_id="project:test",
            project_revision=domain.revision,
            original_instruction="Set the selected plot title to Temperature response.",
            selected_plots=(
                SelectedPlotRef(
                    plot_id="plot:existing",
                    plot_version=3,
                    profile_id="K01",
                ),
            ),
            budget=TaskBudgetLimits(),
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        ledger.create_task(task_envelope)
        coordinator = DurableTaskCoordinator(ledger)
        directive = coordinator.next_action(task_envelope.task_id)
        activation_id = str(directive["activation"]["activation_id"])
        ledger.mark_activation_running(activation_id)
        host = DurableAgentCoreHost(
            project,
            domain,
            ledger,
            plot_lookup=lambda plot_id: PlotDocument(
                plot_id=plot_id,
                plot_version=3,
                parent_version=2,
                profile_id="K01",
                data=EngineDataRef(
                    kind="source",
                    dataset_id="source:not-selected",
                    version=1,
                    content_hash="f" * 64,
                ),
                bindings=(FieldBinding(role="x", field_id="field:not-selected"),),
            ),
        )
        prepared = host.prepare(activation_id)
        context = cast(dict[str, object], prepared["context"])
        assert directive["activation"]["allowed_tools"] == []
        assert prepared["tools"] == []
        assert context["selected_sources"] == []
        assert context["selected_plots"] == [
            {
                "plot_id": "plot:existing",
                "plot_version": 3,
                "profile_id": "K01",
            }
        ]
        assert context["selected_plot_contexts"] == [
            {
                "plot_alias": "plot_1",
                "plot_id": "plot:existing",
                "plot_version": 3,
                "profile_id": "K01",
                "source_aliases": [],
                "bindings": [],
            }
        ]
        source_contexts = cast(list[dict[str, object]], context["source_contexts"])
        assert source_contexts == []
        chart_catalog = cast(list[dict[str, object]], context["chart_catalog"])
        assert [item["profile_id"] for item in chart_catalog] == ["K01"]
        assert "Do not inspect sources or search the chart catalog" in cast(
            str, prepared["system_prompt"]
        )
        assert "use plot for set_title" in cast(str, prepared["system_prompt"])
        assert "use that alias only for TaskDraftItem.target_plot_alias" in cast(
            str, prepared["system_prompt"]
        )

        item = TaskDraftItem(
            task_kind="edit",
            item_id="item:edit-existing.1",
            plot_alias="plot_result",
            profile_id="K01",
            target_plot_alias="plot_1",
            visual_actions=(DraftSetTitle(text="Temperature response"),),
        )
        draft = TaskIntent(
            intent_id="intent:edit-existing",
            intent_version=1,
            task_id=task_envelope.task_id,
            task_version=1,
            created_by_activation_id=activation_id,
            summary="Update the selected plot title.",
            items=(item,),
            context_hash=cast(str, context["content_hash"]),
            content_hash="0" * 64,
        )
        draft = draft.model_copy(
            update={
                "content_hash": canonical_hash(
                    draft.model_dump(mode="json", exclude={"content_hash"})
                )
            }
        )
        candidate = AgentIntentReady(
            activation_id=activation_id,
            task_id=task_envelope.task_id,
            task_version=1,
            intent=draft,
        )
        validated = host.validate_yield(
            activation_id,
            cast(JsonValue, candidate.model_dump(mode="json")),
        )
        checkpoint = host.accept_yield(validated)
        assert checkpoint.state == "intent_staged"
        plan = ledger.get_plan(task_envelope.task_id)
        assert plan.items[0].task_kind == "edit"
        assert plan.items[0].target_plot_id == "plot:existing"
        assert plan.items[0].target_plot_version == 3
        assert plan.items[0].visual_actions[0].operation == "set_title"


def test_current_plot_context_preserves_bindings_for_data_update(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:test") as project:
        imported = ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:basic", path=FILES / "csv_basic.csv")
        )
        assert isinstance(imported, ImportCommitResult)
        source = imported.datasets[0].source_dataset
        x_field, y_field = source.field_schema
        domain = ProjectDomainRepository(project)
        ledger = TaskLedgerRepository(project)
        plot_document = PlotDocument(
            plot_id="plot:existing",
            plot_version=1,
            profile_id="K01",
            data=EngineDataRef(
                kind="source",
                dataset_id=source.source_dataset_id,
                version=source.source_version,
                content_hash=source.content_hash,
            ),
            bindings=(
                FieldBinding(role="x", field_id=x_field.field_id),
                FieldBinding(role="y", field_id=y_field.field_id),
            ),
        )
        task_envelope = TaskEnvelope(
            task_id="task:update-existing",
            task_version=1,
            project_id="project:test",
            project_revision=domain.revision,
            original_instruction=(
                "Exclude signal values greater than or equal to 2, sort time ascending, "
                "and set the title to Filtered."
            ),
            selected_sources=(
                SourceDatasetRef(
                    source_dataset_id=source.source_dataset_id,
                    source_version=source.source_version,
                    content_hash=source.content_hash,
                ),
            ),
            selected_plots=(
                SelectedPlotRef(plot_id="plot:existing", plot_version=1, profile_id="K01"),
            ),
            budget=TaskBudgetLimits(),
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        ledger.create_task(task_envelope)
        directive = DurableTaskCoordinator(ledger).next_action(task_envelope.task_id)
        activation_id = str(directive["activation"]["activation_id"])
        ledger.mark_activation_running(activation_id)
        host = DurableAgentCoreHost(
            project,
            domain,
            ledger,
            plot_lookup=lambda _plot_id: plot_document,
        )

        prepared = host.prepare(activation_id)
        context = cast(dict[str, object], prepared["context"])
        assert context["selected_plot_contexts"] == [
            {
                "plot_alias": "plot_1",
                "plot_id": "plot:existing",
                "plot_version": 1,
                "profile_id": "K01",
                "source_aliases": ["data_1"],
                "bindings": [
                    {
                        "role": "x",
                        "source_alias": "data_1",
                        "field_alias": "data_1_field_1",
                    },
                    {
                        "role": "y",
                        "source_alias": "data_1",
                        "field_alias": "data_1_field_2",
                    },
                ],
            }
        ]
        prompt = cast(str, prepared["system_prompt"])
        assert "task_kind=update_data" in prompt
        assert "filter_rows keeps rows that match" in prompt
        assert "exclude values >= 100" in prompt

        item = TaskDraftItem(
            task_kind="update_data",
            item_id="item:update-existing.1",
            plot_alias="plot_result",
            profile_id="K01",
            target_plot_alias="plot_1",
            source_aliases=("data_1",),
            data_operations=(
                FilterRows(
                    source_alias="data_1",
                    predicates=(
                        FilterPredicate(
                            field_alias="data_1_field_2",
                            operator="less_than",
                            value=2,
                        ),
                    ),
                ),
                SortRows(
                    source_alias="data_1",
                    keys=(SortKey(field_alias="data_1_field_1", direction="ascending"),),
                ),
            ),
            bindings=(
                DraftFieldBinding(
                    role="x", source_alias="data_1", field_alias="data_1_field_1"
                ),
                DraftFieldBinding(
                    role="y", source_alias="data_1", field_alias="data_1_field_2"
                ),
            ),
            visual_actions=(DraftSetTitle(text="Filtered"),),
        )
        intent_value = TaskIntent(
            intent_id="intent:update-existing",
            intent_version=1,
            task_id=task_envelope.task_id,
            task_version=1,
            created_by_activation_id=activation_id,
            summary="Filter and sort the selected plot data, then update its title.",
            items=(item,),
            context_hash=cast(str, context["content_hash"]),
            content_hash="0" * 64,
        )
        intent_value = intent_value.model_copy(
            update={
                "content_hash": canonical_hash(
                    intent_value.model_dump(mode="json", exclude={"content_hash"})
                )
            }
        )
        candidate = AgentIntentReady(
            activation_id=activation_id,
            task_id=task_envelope.task_id,
            task_version=1,
            intent=intent_value,
        )
        validated = host.validate_yield(
            activation_id, cast(JsonValue, candidate.model_dump(mode="json"))
        )
        checkpoint = host.accept_yield(validated)
        assert checkpoint.state == "intent_staged"
        plan = ledger.get_plan(task_envelope.task_id)
        assert plan.items[0].task_kind == "update_data"
        assert [operation.operation for operation in plan.items[0].data_operations] == [
            "filter_rows",
            "sort_rows",
        ]
        assert plan.items[0].visual_actions[0].operation == "set_title"
