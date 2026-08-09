"""Single-run orchestrator: context -> one decision -> local validation."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import TypeAdapter

from plotagent.agent.audit import (
    AuditSink,
    HashedModelRunAudit,
    ModelRunAudit,
)
from plotagent.agent.audit.models import AuditTargetRef, AuditUsage
from plotagent.agent.context import ContextBuilder, ContextBuildRequest
from plotagent.agent.decisions import DecisionCandidate, DecisionParseError, parse_decision
from plotagent.agent.errors import AgentRuntimeError
from plotagent.agent.providers import (
    ModelProvider,
    OutputCapability,
    ProviderCapabilities,
    ProviderDecisionRequest,
    ProviderProtocol,
    ProviderUsage,
    ProviderWireResponse,
)
from plotagent.agent.providers.prompt import AGENT_PROMPT
from plotagent.agent.validation import (
    DecisionValidator,
    ValidationAuthority,
    is_unspecified_chart_request,
)
from plotagent.contracts.agent_context import ContextEnvelope
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import AgentDecision, InputQuestion, NeedsInput
from plotagent.security import LocalSecurityError, NetworkMode

_DECISION_ADAPTER: TypeAdapter[AgentDecision] = TypeAdapter(AgentDecision)


@dataclass(frozen=True, slots=True)
class DecisionMetadata:
    context_hash: str
    prompt_template_hash: str
    decision_schema_hash: str
    provider_response_hash: str
    decision_hash: str


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    client_model_run_id: str
    accepted: bool
    decision: AgentDecision | None = None
    error_code: str | None = None
    metadata: DecisionMetadata | None = None
    audit: HashedModelRunAudit | None = None


class SingleAgentOrchestrator:
    def __init__(
        self,
        *,
        network_mode: NetworkMode,
        context_builder: ContextBuilder,
        provider: ModelProvider,
        validator: DecisionValidator,
        audit_sink: AuditSink,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._network_mode = network_mode
        self._context_builder = context_builder
        self._provider = provider
        self._validator = validator
        self._audit_sink = audit_sink
        self._timeout_seconds = timeout_seconds

    async def run(
        self,
        *,
        client_model_run_id: str,
        context_request: ContextBuildRequest,
        validation_authority: ValidationAuthority,
    ) -> AgentRunResult:
        preflight = _preflight_decision(context_request, validation_authority)
        if preflight is not None:
            return AgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=True,
                decision=preflight,
            )
        if self._network_mode is NetworkMode.LOCAL_ONLY:
            return AgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=False,
                error_code="NETWORK_BLOCKED_LOCAL_ONLY",
            )

        started_at = datetime.now(UTC)
        started_clock = time.perf_counter()
        envelope: ContextEnvelope | None = None
        capabilities = ProviderCapabilities(OutputCapability.P0, ProviderProtocol.NONE)
        response: ProviderWireResponse | None = None
        repaired_response: ProviderWireResponse | None = None
        candidate: DecisionCandidate | None = None
        error_code: str | None = None
        repair_count = 0
        status: Literal["completed", "failed", "cancelled"] = "failed"

        try:
            envelope = self._context_builder.build(context_request)
            decision_schema = _DECISION_ADAPTER.json_schema(mode="validation")
            schema_hash = canonical_hash(decision_schema)
            provider_request = ProviderDecisionRequest(
                client_model_run_id=client_model_run_id,
                envelope=envelope,
                decision_schema=decision_schema,
                decision_schema_hash=schema_hash,
                prompt_template=AGENT_PROMPT,
            )
            async with asyncio.timeout(self._timeout_seconds):
                capabilities = await self._provider.resolve_capabilities()
                if capabilities.output_capability is OutputCapability.P0:
                    raise AgentRuntimeError("PROVIDER_UNSUPPORTED")
                response = await self._provider.decide(provider_request)
                try:
                    candidate = parse_decision(response.output_text)
                except DecisionParseError as first_error:
                    if capabilities.output_capability is OutputCapability.P1:
                        raise AgentRuntimeError(
                            "SCHEMA_INVALID", categories=first_error.categories
                        ) from None
                    repair_count = 1
                    repaired_response = await self._provider.repair(
                        provider_request,
                        invalid_candidate=response.output_text,
                        schema_error_categories=first_error.categories,
                    )
                    try:
                        candidate = parse_decision(repaired_response.output_text)
                    except DecisionParseError:
                        raise AgentRuntimeError("REPAIR_EXHAUSTED") from None
            assert candidate is not None
            decision = self._validator.validate(
                candidate.decision,
                envelope,
                validation_authority,
            )
            status = "completed"
            audit = self._audit(
                client_model_run_id=client_model_run_id,
                envelope=envelope,
                capabilities=capabilities,
                response=response,
                repaired_response=repaired_response,
                candidate=candidate,
                error_code=None,
                status=status,
                repair_count=repair_count,
                started_at=started_at,
                started_clock=started_clock,
                decision_schema_hash=schema_hash,
            )
            return AgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=True,
                decision=decision,
                metadata=DecisionMetadata(
                    context_hash=envelope.context_hash,
                    prompt_template_hash=AGENT_PROMPT.prompt_hash,
                    decision_schema_hash=schema_hash,
                    provider_response_hash=candidate.provider_response_hash,
                    decision_hash=candidate.decision_hash,
                ),
                audit=audit,
            )
        except TimeoutError:
            error_code = "REQUEST_TIMEOUT"
            await self._cancel_safely(client_model_run_id)
        except asyncio.CancelledError:
            error_code = "REQUEST_CANCELLED"
            status = "cancelled"
            await self._cancel_safely(client_model_run_id)
        except (AgentRuntimeError, LocalSecurityError) as error:
            error_code = error.code
        except Exception:
            error_code = "PROVIDER_CONNECTION_FAILED"

        if envelope is None:
            return AgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=False,
                error_code=error_code,
            )
        decision_schema_hash = canonical_hash(_DECISION_ADAPTER.json_schema(mode="validation"))
        audit = self._audit(
            client_model_run_id=client_model_run_id,
            envelope=envelope,
            capabilities=capabilities,
            response=response,
            repaired_response=repaired_response,
            candidate=candidate,
            error_code=error_code,
            status=status,
            repair_count=repair_count,
            started_at=started_at,
            started_clock=started_clock,
            decision_schema_hash=decision_schema_hash,
        )
        return AgentRunResult(
            client_model_run_id=client_model_run_id,
            accepted=False,
            error_code=error_code,
            audit=audit,
        )

    def validate_manual_decision(
        self,
        decision: AgentDecision,
        envelope: ContextEnvelope,
        authority: ValidationAuthority,
    ) -> AgentDecision:
        """Manual UI plans use the same validator even in strict local_only mode."""

        return self._validator.validate(decision, envelope, authority)

    async def _cancel_safely(self, client_model_run_id: str) -> None:
        with contextlib.suppress(BaseException):
            await asyncio.shield(self._provider.cancel(client_model_run_id))

    def _audit(
        self,
        *,
        client_model_run_id: str,
        envelope: ContextEnvelope,
        capabilities: ProviderCapabilities,
        response: ProviderWireResponse | None,
        repaired_response: ProviderWireResponse | None,
        candidate: DecisionCandidate | None,
        error_code: str | None,
        status: Literal["completed", "failed", "cancelled"],
        repair_count: int,
        started_at: datetime,
        started_clock: float,
        decision_schema_hash: str,
    ) -> HashedModelRunAudit:
        identity = self._provider.identity
        primary_usage = response.usage if response is not None else ProviderUsage()
        repair_usage = repaired_response.usage if repaired_response is not None else ProviderUsage()
        usage_sources = {primary_usage.source, repair_usage.source} - {"unavailable"}
        usage_source: Literal["provider", "unavailable", "mixed"]
        if usage_sources == {"provider"}:
            usage_source = "provider"
        elif usage_sources:
            usage_source = "mixed"
        else:
            usage_source = "unavailable"
        finished_at = datetime.now(UTC)
        request_ids = tuple(
            item.provider_request_id
            for item in (response, repaired_response)
            if item is not None and item.provider_request_id is not None
        )
        record = ModelRunAudit(
            client_model_run_id=client_model_run_id,
            provider_type=identity.provider_type,
            provider_config_id=identity.provider_config_id,
            endpoint_origin=identity.endpoint_origin,
            model_id=identity.model_id,
            model_profile=identity.model_profile,
            deployment_id=identity.deployment_id,
            protocol=capabilities.protocol.value,
            output_capability=capabilities.output_capability.value,
            prompt_template_version=AGENT_PROMPT.version,
            prompt_template_hash=AGENT_PROMPT.prompt_hash,
            context_schema_version=envelope.schema_version,
            decision_schema_version="1.0",
            decision_schema_hash=decision_schema_hash,
            context_hash=envelope.context_hash,
            disclosure_hash=envelope.data_disclosure.disclosure_hash,
            disclosure_categories=envelope.data_disclosure.categories,
            disclosure_field_count=envelope.data_disclosure.field_count,
            disclosure_row_count=envelope.data_disclosure.row_count,
            disclosure_scalar_count=envelope.data_disclosure.scalar_count,
            target_ref=AuditTargetRef(
                object_id=envelope.target_snapshot.object_id,
                object_version=envelope.target_snapshot.object_version,
                content_hash=envelope.target_snapshot.content_hash,
            ),
            provider_request_ids=request_ids,
            provider_response_hashes=tuple(
                item.response_hash for item in (response, repaired_response) if item is not None
            ),
            decision_hash=candidate.decision_hash if candidate is not None else None,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=max(0, round((time.perf_counter() - started_clock) * 1000)),
            usage=AuditUsage(
                input_tokens=primary_usage.input_tokens,
                output_tokens=primary_usage.output_tokens,
                repair_input_tokens=repair_usage.input_tokens,
                repair_output_tokens=repair_usage.output_tokens,
                source=usage_source,
            ),
            status=status,
            error_code=error_code,
            repair_count=repair_count,
        )
        audit = HashedModelRunAudit.create(record)
        self._audit_sink.record(audit)
        return audit


def _preflight_decision(
    request: ContextBuildRequest,
    authority: ValidationAuthority,
) -> NeedsInput | None:
    """Ask locally when a source request does not identify a chart type."""

    target = request.project.target
    if target != request.conversation_state.current_target:
        return None
    if target != authority.current_target:
        return None
    if target.object_type != "source_dataset":
        return None
    if (
        "create_plot" not in request.chart_capabilities.allowed_action_types
        or "create_plot" not in authority.allowed_action_types
        or "create_plot" not in authority.permission_grants
    ):
        return None
    eligible_charts = set(request.chart_capabilities.allowed_chart_type_ids) & set(
        authority.allowed_chart_type_ids
    )
    if len(eligible_charts) <= 1:
        return None
    if not is_unspecified_chart_request(request.user_instruction):
        return None
    prompt = (
        "请选择要绘制的图形类型。"
        if request.locale.casefold().startswith("zh")
        else "Which chart type should I draw?"
    )
    return NeedsInput(
        target_alias=target.object_alias,
        questions=(
            InputQuestion(
                question_key="chart_type",
                prompt=prompt,
                input_kind="text",
            ),
        ),
    )
