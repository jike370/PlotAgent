"""Model decision loop for PlotAgent's bundled Agent Native engine client."""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from plotagent.agent.audit import AuditSink, HashedModelRunAudit, ModelRunAudit
from plotagent.agent.audit.models import AuditTargetRef, AuditUsage
from plotagent.agent.context import ContextBuilder, ContextBuildRequest
from plotagent.agent.engine_client import (
    BoundEnginePlan,
    BundledEngineAgentBinder,
    EngineAgentDecision,
    EngineAgentPlan,
)
from plotagent.agent.engine_decisions import InputQuestion, NeedsInput
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
from plotagent.agent.providers.engine_prompt import engine_agent_prompt
from plotagent.contracts.agent_context import ContextEnvelope
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.project_context import ProjectContextSnapshot
from plotagent.engine import EngineActionCodec, EngineCommandError
from plotagent.security import LocalSecurityError, NetworkMode

_DECISION_ADAPTER: TypeAdapter[EngineAgentDecision] = TypeAdapter(EngineAgentDecision)


@dataclass(frozen=True, slots=True)
class DecisionMetadata:
    context_hash: str
    prompt_template_hash: str
    decision_schema_hash: str
    provider_response_hash: str
    decision_hash: str


def is_unspecified_chart_request(instruction: str) -> bool:
    normalized = re.sub(r"[^\w]+", "", instruction.casefold()).replace("_", "")
    return normalized in {
        "画图",
        "画一个图",
        "画一张图",
        "请画图",
        "请画一个图",
        "请画一张图",
        "帮我画图",
        "绘图",
        "绘制一个图",
        "绘制一张图",
        "用这些数据画图",
        "用这个数据画图",
        "drawchart",
        "drawachart",
        "drawit",
        "makeaplot",
        "makeachart",
        "plot",
        "plotachart",
        "plotit",
    }


@dataclass(frozen=True, slots=True)
class EngineAgentRunResult:
    client_model_run_id: str
    accepted: bool
    decision: EngineAgentDecision | None = None
    bound_plan: BoundEnginePlan | None = None
    error_code: str | None = None
    metadata: DecisionMetadata | None = None
    audit: HashedModelRunAudit | None = None


class EngineAgentOrchestrator:
    """Ask a model for aliases, then bind locally to the public engine contract."""

    def __init__(
        self,
        *,
        network_mode: NetworkMode,
        context_builder: ContextBuilder,
        provider: ModelProvider,
        binder: BundledEngineAgentBinder,
        codec: EngineActionCodec,
        audit_sink: AuditSink,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._network_mode = network_mode
        self._context_builder = context_builder
        self._provider = provider
        self._binder = binder
        self._codec = codec
        self._audit_sink = audit_sink
        self._timeout_seconds = timeout_seconds

    async def run(
        self,
        *,
        client_model_run_id: str,
        context_request: ContextBuildRequest,
        project_context: ProjectContextSnapshot,
        target_profiles: dict[str, str] | None = None,
    ) -> EngineAgentRunResult:
        preflight = self._preflight(context_request)
        if preflight is not None:
            return EngineAgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=True,
                decision=preflight,
            )
        if self._network_mode is NetworkMode.LOCAL_ONLY:
            return EngineAgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=False,
                error_code="NETWORK_BLOCKED_LOCAL_ONLY",
            )

        started_at = datetime.now(UTC)
        started_clock = time.perf_counter()
        envelope: ContextEnvelope | None = None
        capabilities = ProviderCapabilities(OutputCapability.P0, ProviderProtocol.NONE)
        response: ProviderWireResponse | None = None
        repaired: ProviderWireResponse | None = None
        decision: EngineAgentDecision | None = None
        error_code: str | None = None
        repair_count = 0
        status: Literal["completed", "failed", "cancelled"] = "failed"
        prompt = engine_agent_prompt(self._codec)
        schema = _DECISION_ADAPTER.json_schema(mode="validation")
        schema_hash = canonical_hash(schema)

        try:
            envelope = self._context_builder.build(context_request)
            request = ProviderDecisionRequest(
                client_model_run_id=client_model_run_id,
                envelope=envelope,
                decision_schema=schema,
                decision_schema_hash=schema_hash,
                prompt_template=prompt,
            )
            async with asyncio.timeout(self._timeout_seconds):
                capabilities = await self._provider.resolve_capabilities()
                if capabilities.output_capability is OutputCapability.P0:
                    raise AgentRuntimeError("PROVIDER_UNSUPPORTED")
                response = await self._provider.decide(request)
                try:
                    decision = _DECISION_ADAPTER.validate_json(response.output_text)
                except ValidationError as first_error:
                    if capabilities.output_capability is OutputCapability.P1:
                        raise AgentRuntimeError(
                            "SCHEMA_INVALID",
                            categories=_validation_categories(first_error),
                        ) from None
                    repair_count = 1
                    repaired = await self._provider.repair(
                        request,
                        invalid_candidate=response.output_text,
                        schema_error_categories=_validation_categories(first_error),
                    )
                    try:
                        decision = _DECISION_ADAPTER.validate_json(repaired.output_text)
                    except ValidationError:
                        raise AgentRuntimeError("REPAIR_EXHAUSTED") from None
            assert decision is not None
            self._validate_decision(decision, envelope)
            bound = (
                self._binder.bind(
                    decision,
                    project_context,
                    target_profiles=target_profiles,
                )
                if isinstance(decision, EngineAgentPlan)
                else None
            )
            status = "completed"
            audit = self._audit(
                client_model_run_id=client_model_run_id,
                envelope=envelope,
                capabilities=capabilities,
                response=response,
                repaired=repaired,
                decision=decision,
                error_code=None,
                status=status,
                repair_count=repair_count,
                started_at=started_at,
                started_clock=started_clock,
                schema_hash=schema_hash,
                prompt_hash=prompt.prompt_hash,
            )
            return EngineAgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=True,
                decision=decision,
                bound_plan=bound,
                metadata=DecisionMetadata(
                    context_hash=envelope.context_hash,
                    prompt_template_hash=prompt.prompt_hash,
                    decision_schema_hash=schema_hash,
                    provider_response_hash=(repaired or response).response_hash,
                    decision_hash=canonical_hash(decision),
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
        except EngineCommandError:
            error_code = "ENGINE_PLAN_INVALID"
        except Exception:
            error_code = "PROVIDER_CONNECTION_FAILED"

        failure_audit: HashedModelRunAudit | None = None
        if envelope is not None:
            failure_audit = self._audit(
                client_model_run_id=client_model_run_id,
                envelope=envelope,
                capabilities=capabilities,
                response=response,
                repaired=repaired,
                decision=decision,
                error_code=error_code,
                status=status,
                repair_count=repair_count,
                started_at=started_at,
                started_clock=started_clock,
                schema_hash=schema_hash,
                prompt_hash=prompt.prompt_hash,
            )
        return EngineAgentRunResult(
            client_model_run_id=client_model_run_id,
            accepted=False,
            error_code=error_code,
            audit=failure_audit,
        )

    def _preflight(self, request: ContextBuildRequest) -> NeedsInput | None:
        target = request.project.target
        if target.object_type != "source_dataset":
            return None
        profiles = request.chart_capabilities.allowed_chart_type_ids
        if len(profiles) <= 1 or not is_unspecified_chart_request(request.user_instruction):
            return None
        prompt = (
            "请选择要绘制的图形类型。"
            if request.locale.casefold().startswith("zh")
            else "Which chart type should I draw?"
        )
        return NeedsInput(
            target_alias=target.object_alias,
            questions=(InputQuestion(question_key="chart_type", prompt=prompt, input_kind="text"),),
        )

    @staticmethod
    def _validate_decision(decision: EngineAgentDecision, envelope: ContextEnvelope) -> None:
        aliases = {
            envelope.target_snapshot.object_alias,
            *(item.object_alias for item in envelope.selected_context.selected_objects),
        }
        if decision.target_alias not in aliases:
            raise AgentRuntimeError("TARGET_INVALID")
        if isinstance(decision, EngineAgentPlan):
            allowed_profiles = set(envelope.chart_capabilities.allowed_chart_type_ids)
            if any(
                action.profile_id not in allowed_profiles
                for action in decision.actions
                if action.operation == "create_plot"
            ):
                raise AgentRuntimeError("CHART_CAPABILITY_DENIED")

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
        repaired: ProviderWireResponse | None,
        decision: EngineAgentDecision | None,
        error_code: str | None,
        status: Literal["completed", "failed", "cancelled"],
        repair_count: int,
        started_at: datetime,
        started_clock: float,
        schema_hash: str,
        prompt_hash: str,
    ) -> HashedModelRunAudit:
        identity = self._provider.identity
        primary = response.usage if response is not None else ProviderUsage()
        repair_usage = repaired.usage if repaired is not None else ProviderUsage()
        sources = {primary.source, repair_usage.source} - {"unavailable"}
        usage_source: Literal["provider", "unavailable", "mixed"] = (
            "provider" if sources == {"provider"} else "mixed" if sources else "unavailable"
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
            prompt_template_version="engine-agent-v1",
            prompt_template_hash=prompt_hash,
            context_schema_version=envelope.schema_version,
            decision_schema_version="engine-agent.v1",
            decision_schema_hash=schema_hash,
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
            provider_request_ids=tuple(
                item.provider_request_id
                for item in (response, repaired)
                if item is not None and item.provider_request_id is not None
            ),
            provider_response_hashes=tuple(
                item.response_hash for item in (response, repaired) if item is not None
            ),
            decision_hash=None if decision is None else canonical_hash(decision),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            latency_ms=max(0, round((time.perf_counter() - started_clock) * 1000)),
            usage=AuditUsage(
                input_tokens=primary.input_tokens,
                output_tokens=primary.output_tokens,
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


def _validation_categories(error: ValidationError) -> tuple[str, ...]:
    return tuple(sorted({str(item["type"]) for item in error.errors()}))
