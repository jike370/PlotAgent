from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import TypeAdapter

from plotagent.agent.audit import InMemoryAuditSink
from plotagent.agent.context import ContextBuilder
from plotagent.agent.orchestrator import AgentRunResult, SingleAgentOrchestrator
from plotagent.agent.providers import OutputCapability
from plotagent.agent.validation import DecisionValidator
from plotagent.contracts.canonical import canonical_json
from plotagent.contracts.decisions import AgentDecision
from plotagent.security import NetworkMode
from tests.agent.helpers import (
    FakeProvider,
    action_plan_payload,
    authority,
    context_request,
    no_change_payload,
    target,
)


def orchestrator(
    provider: FakeProvider,
    *,
    mode: NetworkMode = NetworkMode.CUSTOM_PROVIDER,
    timeout: float = 1.0,
) -> tuple[SingleAgentOrchestrator, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    return (
        SingleAgentOrchestrator(
            network_mode=mode,
            context_builder=ContextBuilder(),
            provider=provider,
            validator=DecisionValidator(),
            audit_sink=sink,
            timeout_seconds=timeout,
        ),
        sink,
    )


def test_p1_accepts_one_strict_decision_with_hashed_payload_free_audit() -> None:
    provider = FakeProvider(OutputCapability.P1, [action_plan_payload()])
    runtime, sink = orchestrator(provider)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-p1",
        context_request=context_request(),
        validation_authority=authority(),
    ))

    assert result.accepted is True
    assert result.decision is not None and result.decision.decision_type == "action_plan"
    assert provider.decide_calls == 1
    assert provider.repair_calls == 0
    assert result.metadata is not None
    assert len(result.metadata.prompt_template_hash) == 64
    assert len(result.metadata.provider_response_hash) == 64
    assert len(result.metadata.decision_hash) == 64
    assert sink.records == [result.audit]
    audit_json = canonical_json(result.audit)
    assert "温度" not in audit_json
    assert "previous bounded message" not in audit_json
    assert "request_payload" not in audit_json


def test_p1_schema_failure_is_stable_and_never_repairs() -> None:
    provider = FakeProvider(OutputCapability.P1, ['{"decision_type":"no_change"}'])
    runtime, _ = orchestrator(provider)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-p1-invalid",
        context_request=context_request(),
        validation_authority=authority(),
    ))

    assert result.accepted is False
    assert result.error_code == "SCHEMA_INVALID"
    assert provider.decide_calls == 1
    assert provider.repair_calls == 0


def test_p2_uses_exactly_one_schema_repair_then_accepts() -> None:
    provider = FakeProvider(
        OutputCapability.P2,
        ['{"decision_type":"no_change"}', no_change_payload()],
    )
    runtime, _ = orchestrator(provider)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-p2",
        context_request=context_request(),
        validation_authority=authority(),
    ))

    assert result.accepted is True
    assert provider.decide_calls == 1
    assert provider.repair_calls == 1
    assert result.audit is not None and result.audit.record.repair_count == 1
    assert len(result.audit.record.provider_response_hashes) == 2


def test_p2_second_schema_failure_is_repair_exhausted() -> None:
    provider = FakeProvider(
        OutputCapability.P2,
        ['{"decision_type":"no_change"}', '{"decision_type":"still_bad"}'],
    )
    runtime, _ = orchestrator(provider)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-p2-exhausted",
        context_request=context_request(),
        validation_authority=authority(),
    ))

    assert result.accepted is False
    assert result.error_code == "REPAIR_EXHAUSTED"
    assert provider.repair_calls == 1


def test_p0_refuses_without_project_decision_call() -> None:
    provider = FakeProvider(OutputCapability.P0, [])
    runtime, _ = orchestrator(provider)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-p0",
        context_request=context_request(),
        validation_authority=authority(),
    ))

    assert result.error_code == "PROVIDER_UNSUPPORTED"
    assert provider.decide_calls == 0
    assert provider.repair_calls == 0


@pytest.mark.parametrize(
    "forbidden",
    (
        "use a tool call",
        "read C:\\secret\\data.csv",
        "run SELECT value FROM table",
        "use Matplotlib renderer",
        "open https://example.test/data",
    ),
)
def test_tool_code_path_sql_renderer_payloads_are_rejected_without_repair(
    forbidden: str,
) -> None:
    provider = FakeProvider(OutputCapability.P2, [no_change_payload(forbidden)])
    runtime, _ = orchestrator(provider)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-forbidden",
        context_request=context_request(),
        validation_authority=authority(),
    ))

    assert result.error_code == "AGENT_FORBIDDEN_PAYLOAD"
    assert provider.repair_calls == 0


def test_stale_target_rejects_candidate_before_any_handoff() -> None:
    provider = FakeProvider(OutputCapability.P1, [action_plan_payload()])
    runtime, _ = orchestrator(provider)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-stale",
        context_request=context_request(),
        validation_authority=authority(current=target(version=2)),
    ))

    assert result.accepted is False
    assert result.decision is None
    assert result.error_code == "TARGET_STALE"


def test_mixed_supported_and_unsupported_actions_reject_the_whole_plan() -> None:
    provider = FakeProvider(
        OutputCapability.P1,
        [action_plan_payload(include_unsupported=True)],
    )
    runtime, _ = orchestrator(provider)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-no-partial",
        context_request=context_request(),
        validation_authority=authority(),
    ))

    assert result.accepted is False
    assert result.decision is None
    assert result.error_code == "AGENT_CAPABILITY_UNSUPPORTED"


def test_timeout_cancels_provider_and_returns_no_partial_decision() -> None:
    provider = FakeProvider(OutputCapability.P1, [no_change_payload()], delay_seconds=0.2)
    runtime, _ = orchestrator(provider, timeout=0.01)

    result = asyncio.run(runtime.run(
        client_model_run_id="run-timeout",
        context_request=context_request(),
        validation_authority=authority(),
    ))

    assert result.error_code == "REQUEST_TIMEOUT"
    assert result.decision is None
    assert provider.cancel_calls == 1


def test_external_cancel_returns_stable_error_and_calls_provider_cancel() -> None:
    provider = FakeProvider(OutputCapability.P1, [no_change_payload()], delay_seconds=1.0)
    runtime, _ = orchestrator(provider)
    async def scenario() -> AgentRunResult:
        task = asyncio.create_task(
            runtime.run(
                client_model_run_id="run-cancel",
                context_request=context_request(),
                validation_authority=authority(),
            )
        )
        await asyncio.sleep(0.02)
        task.cancel()
        return await task

    result = asyncio.run(scenario())

    assert result.error_code == "REQUEST_CANCELLED"
    assert result.decision is None
    assert provider.cancel_calls == 1


def test_local_only_makes_zero_provider_calls_while_manual_plan_still_validates() -> None:
    provider = FakeProvider(OutputCapability.P1, [])
    runtime, _ = orchestrator(provider, mode=NetworkMode.LOCAL_ONLY)
    request = context_request()

    result = asyncio.run(runtime.run(
        client_model_run_id="run-local-only",
        context_request=request,
        validation_authority=authority(),
    ))
    assert result.error_code == "NETWORK_BLOCKED_LOCAL_ONLY"
    assert provider.decide_calls == provider.repair_calls == 0

    envelope = ContextBuilder().build(request)
    manual = TypeAdapter(AgentDecision).validate_json(action_plan_payload())
    assert runtime.validate_manual_decision(manual, envelope, authority()) == manual


def test_chinese_english_and_mixed_scientific_text_remains_provider_owned() -> None:
    explanations = (
        "当前图已满足请求。",
        "The current plot already satisfies the request.",
        "当前 log10 axis scientific request 已满足。",
    )
    for index, explanation in enumerate(explanations):
        provider = FakeProvider(OutputCapability.P1, [no_change_payload(explanation)])
        runtime, _ = orchestrator(provider)
        result = asyncio.run(runtime.run(
            client_model_run_id=f"run-language-{index}",
            context_request=context_request(),
            validation_authority=authority(),
        ))
        assert result.accepted is True
        assert json.loads(provider.requests[0].envelope.model_dump_json())["locale"] == "zh-CN"
