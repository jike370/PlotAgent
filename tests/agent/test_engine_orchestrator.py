from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from plotagent.agent.audit import InMemoryAuditSink
from plotagent.agent.context import ContextBuilder, ContextBuildRequest
from plotagent.agent.engine_client import BundledEngineAgentBinder, EngineAgentPlan
from plotagent.agent.engine_orchestrator import EngineAgentOrchestrator
from plotagent.contracts.agent_context import ChartCapabilities, ContextObjectRef
from plotagent.contracts.project_context import ContextFieldBinding, ProjectContextSnapshot
from plotagent.engine import CreatePlot, EngineActionCodec, EngineCatalog, SetTitle
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.security import NetworkMode
from tests.agent.helpers import FakeProvider, OutputCapability, context_request


def _request_and_snapshot() -> tuple[ContextBuildRequest, ProjectContextSnapshot]:
    request = context_request()
    target = ContextObjectRef(
        object_alias="active_target",
        object_id="source:test",
        object_version=1,
        object_type="source_dataset",
        content_hash="d" * 64,
    )
    request = replace(
        request,
        project=replace(request.project, target=target),
        conversation_state=request.conversation_state.model_copy(
            update={"current_target": target}
        ),
        chart_capabilities=ChartCapabilities(
            capability_version="engine-v1",
            allowed_chart_type_ids=("K01",),
            allowed_action_types=("create_plot",),
        ),
    )
    snapshot = ProjectContextSnapshot(
        snapshot_id="context:engine-test.1.7.aaaaaaaaaaaa",
        snapshot_hash="a" * 64,
        project_id="project:test",
        project_revision=7,
        conversation_id="conversation:engine-test",
        conversation_state=request.conversation_state.project(),
        known_objects=(target,),
        field_bindings=(
            ContextFieldBinding(
                field_alias="x_field",
                field_id="field:f000",
                source_dataset_id="source:test",
                source_version=1,
            ),
            ContextFieldBinding(
                field_alias="y_field",
                field_id="field:f001",
                source_dataset_id="source:test",
                source_version=1,
            ),
        ),
    )
    return request, snapshot


def _runtime(provider: FakeProvider) -> EngineAgentOrchestrator:
    catalog = EngineCatalog(ENGINE_PROFILES)
    return EngineAgentOrchestrator(
        network_mode=NetworkMode.CUSTOM_PROVIDER,
        context_builder=ContextBuilder(),
        provider=provider,
        binder=BundledEngineAgentBinder(catalog),
        codec=EngineActionCodec(catalog),
        audit_sink=InMemoryAuditSink(),
    )


def test_provider_alias_plan_is_bound_to_public_engine_actions() -> None:
    response = json.dumps(
        {
            "schema_version": "engine-agent.v1",
            "decision_type": "action_plan",
            "plan_id": "plan:engine-orchestrator",
            "target_alias": "active_target",
            "actions": [
                {
                    "operation": "create_plot",
                    "action_id": "action:create",
                    "plot_alias": "result",
                    "profile_id": "K01",
                    "source_alias": "active_target",
                    "bindings": [
                        {"role": "x", "field_alias": "x_field"},
                        {"role": "y", "field_alias": "y_field"},
                    ],
                },
                {
                    "operation": "set_title",
                    "action_id": "action:title",
                    "plot_alias": "result",
                    "text": "Temperature response",
                },
            ],
        }
    )
    provider = FakeProvider(OutputCapability.P1, [response])
    request, snapshot = _request_and_snapshot()

    result = asyncio.run(
        _runtime(provider).run(
            client_model_run_id="run:engine",
            context_request=request,
            project_context=snapshot,
        )
    )

    assert result.accepted is True
    assert isinstance(result.decision, EngineAgentPlan)
    assert result.bound_plan is not None
    assert result.bound_plan.expected_project_revision == 7
    assert isinstance(result.bound_plan.actions[0], CreatePlot)
    assert isinstance(result.bound_plan.actions[1], SetTitle)
    assert result.bound_plan.actions[1].expected_plot_version == 1
    prompt = provider.requests[0].prompt_template.text
    assert "TRUSTED_ENGINE_PROFILE_CATALOG" in prompt
    assert '"profile_id":"K01"' in prompt
    assert "PlotSpec" not in prompt
    assert "Matplotlib" not in prompt
    assert "Origin" not in prompt


def test_unspecified_chart_is_asked_locally_without_model_call() -> None:
    provider = FakeProvider(OutputCapability.P1, [])
    request, snapshot = _request_and_snapshot()
    request = replace(
        request,
        user_instruction="画一张图",
        chart_capabilities=ChartCapabilities(
            capability_version="engine-v1",
            allowed_chart_type_ids=("K01", "K08"),
            allowed_action_types=("create_plot",),
        ),
    )

    result = asyncio.run(
        _runtime(provider).run(
            client_model_run_id="run:needs-input",
            context_request=request,
            project_context=snapshot,
        )
    )

    assert result.accepted is True
    assert result.decision is not None
    assert result.decision.decision_type == "needs_input"
    assert provider.resolve_calls == provider.decide_calls == 0


def test_same_chart_request_requires_two_selected_sources_before_model_call() -> None:
    provider = FakeProvider(OutputCapability.P1, [])
    request, _snapshot = _request_and_snapshot()
    request = replace(
        request,
        user_instruction="把数据画在同一张散点图中，并按数据来源分组。",
        chart_capabilities=ChartCapabilities(
            capability_version="engine-v1",
            allowed_chart_type_ids=("K03",),
            allowed_action_types=("create_plot", "create_combined_plot"),
        ),
    )

    decision = _runtime(provider).preflight(request)

    assert decision is not None
    assert decision.decision_type == "needs_input"
    assert decision.questions[0].question_key == "source_datasets"
    assert provider.resolve_calls == provider.decide_calls == 0


def test_same_chart_request_rejects_a_single_source_create_plan() -> None:
    provider = FakeProvider(OutputCapability.P1, [])
    request, snapshot = _request_and_snapshot()
    second = request.project.target.model_copy(
        update={
            "object_alias": "data_2",
            "object_id": "source:second",
            "content_hash": "e" * 64,
        }
    )
    request = replace(
        request,
        user_instruction="Plot both datasets on the same chart, grouped by source.",
        project=replace(request.project, selected_objects=(second,)),
        chart_capabilities=ChartCapabilities(
            capability_version="engine-v1",
            allowed_chart_type_ids=("K03",),
            allowed_action_types=("create_plot", "create_combined_plot"),
        ),
    )
    snapshot = snapshot.model_copy(
        update={"known_objects": (*snapshot.known_objects, second)}
    )
    runtime = _runtime(provider)
    envelope = ContextBuilder().build(request)

    result = runtime.accept_external(
        {
            "schema_version": "engine-agent.v1",
            "decision_type": "action_plan",
            "plan_id": "plan:wrong-single-source",
            "target_alias": "active_target",
            "actions": [
                {
                    "operation": "create_plot",
                    "action_id": "action:create",
                    "plot_alias": "result",
                    "profile_id": "K03",
                    "source_alias": "active_target",
                    "bindings": [
                        {"role": "x", "field_alias": "x_field"},
                        {"role": "y", "field_alias": "y_field"},
                    ],
                }
            ],
        },
        envelope=envelope,
        project_context=snapshot,
        client_model_run_id="run:wrong-single-source",
    )

    assert result.accepted is False
    assert result.error_code == "COMBINED_ACTION_REQUIRED"


def test_removed_plot_composition_is_rejected_locally_without_model_call() -> None:
    provider = FakeProvider(OutputCapability.P1, [])
    request, snapshot = _request_and_snapshot()
    request = replace(request, user_instruction="把当前图和另一张图创建成多面板组合图")

    result = asyncio.run(
        _runtime(provider).run(
            client_model_run_id="run:removed-composition",
            context_request=request,
            project_context=snapshot,
        )
    )

    assert result.accepted is True
    assert result.decision is not None
    assert result.decision.decision_type == "unsupported"
    assert result.decision.category == "profile_capability"
    assert "组合图" in result.decision.explanation
    assert provider.resolve_calls == provider.decide_calls == 0


def test_external_pi_decision_accepts_json_arrays_under_strict_contract() -> None:
    provider = FakeProvider(OutputCapability.P1, [])
    request, snapshot = _request_and_snapshot()
    request = replace(
        request,
        user_instruction="画一张图。",
        chart_capabilities=ChartCapabilities(
            capability_version="engine-v1",
            allowed_chart_type_ids=("K01", "K08"),
            allowed_action_types=("create_plot",),
        ),
    )
    runtime = _runtime(provider)
    decision = runtime.preflight(request)
    assert decision is not None

    accepted = runtime.accept_external(
        decision.model_dump(mode="json"),
        envelope=ContextBuilder().build(request),
        project_context=snapshot,
        client_model_run_id="run:external-json",
    )

    assert accepted.accepted is True
    assert accepted.decision is not None
    assert accepted.decision.decision_type == "needs_input"


def test_external_pi_action_plan_binds_nested_json_arrays() -> None:
    provider = FakeProvider(OutputCapability.P1, [])
    request, snapshot = _request_and_snapshot()
    runtime = _runtime(provider)
    payload = {
        "schema_version": "engine-agent.v1",
        "decision_type": "action_plan",
        "plan_id": "plan:external-json",
        "target_alias": "active_target",
        "actions": [
            {
                "operation": "create_plot",
                "action_id": "action:create",
                "plot_alias": "result",
                "profile_id": "K01",
                "source_alias": "active_target",
                "bindings": [
                    {"role": "x", "field_alias": "x_field"},
                    {"role": "y", "field_alias": "y_field"},
                ],
            }
        ],
    }

    accepted = runtime.accept_external(
        payload,
        envelope=ContextBuilder().build(request),
        project_context=snapshot,
        client_model_run_id="run:external-plan-json",
    )

    assert accepted.accepted is True
    assert accepted.bound_plan is not None
    assert isinstance(accepted.bound_plan.actions[0], CreatePlot)


def test_profile_outside_local_capability_is_rejected_without_binding() -> None:
    response = json.dumps(
        {
            "schema_version": "engine-agent.v1",
            "decision_type": "action_plan",
            "plan_id": "plan:denied",
            "target_alias": "active_target",
            "actions": [
                {
                    "operation": "create_plot",
                    "action_id": "action:create",
                    "plot_alias": "result",
                    "profile_id": "K08",
                    "source_alias": "active_target",
                    "bindings": [{"role": "category", "field_alias": "x_field"}],
                }
            ],
        }
    )
    provider = FakeProvider(OutputCapability.P1, [response])
    request, snapshot = _request_and_snapshot()

    result = asyncio.run(
        _runtime(provider).run(
            client_model_run_id="run:denied",
            context_request=request,
            project_context=snapshot,
        )
    )

    assert result.accepted is False
    assert result.error_code == "CHART_CAPABILITY_DENIED"
