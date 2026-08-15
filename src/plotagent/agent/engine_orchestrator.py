"""Model decision loop for PlotAgent's bundled Agent Native engine client."""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import TypeAdapter, ValidationError

from plotagent.agent.audit import AuditSink, HashedModelRunAudit, ModelRunAudit
from plotagent.agent.audit.models import AuditTargetRef, AuditUsage
from plotagent.agent.context import AuthoritativeField, ContextBuilder, ContextBuildRequest
from plotagent.agent.engine_client import (
    AgentBindFields,
    AgentCreateCombinedPlot,
    AgentCreatePlot,
    AgentFieldBinding,
    BoundEnginePlan,
    BundledEngineAgentBinder,
    EngineAgentDecision,
    EngineAgentPlan,
)
from plotagent.agent.engine_decisions import InputQuestion, NeedsInput, Unsupported
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
from plotagent.contracts.canonical import JsonValue, canonical_hash, canonical_json
from plotagent.contracts.project_context import ProjectContextSnapshot
from plotagent.engine import EngineActionCodec, EngineCommandError
from plotagent.security import LocalSecurityError, NetworkMode

_DECISION_ADAPTER: TypeAdapter[EngineAgentDecision] = TypeAdapter(EngineAgentDecision)

_NON_NUMERIC_FIELD_ROLES = frozenset(
    {
        "actual",
        "category",
        "column",
        "column_label",
        "component",
        "event",
        "facet",
        "feature",
        "group",
        "item",
        "label",
        "panel",
        "parameter",
        "predicted",
        "row",
        "row_label",
        "series",
        "time",
    }
)

_PROFILE_ALIASES: dict[str, tuple[str, ...]] = {
    "K01": ("折线图", "line graph", "line"),
    "K02": ("线点图", "线符号图", "line and symbol", "line+symbol"),
    "K03": ("散点图", "scatter plot", "scatter"),
    "K04": ("气泡图", "bubble plot", "bubble"),
    "K06": ("点估计与误差棒", "xy误差棒", "point estimate and error bar"),
    "K07": ("误差带", "误差带图", "error ribbon", "error band"),
    "K08": ("柱状图", "column chart", "column"),
    "K09": ("分组柱状图", "grouped column"),
    "K10": ("堆积柱状图", "stacked column"),
    "K11": ("百分比堆积柱状图", "100% stacked column"),
    "K12": ("条带图", "列散点图", "strip plot", "column scatter"),
    "K13": ("箱线图", "box plot"),
    "K14": ("小提琴图", "violin plot"),
    "K15": ("直方图", "histogram"),
    "K18": ("面积图", "area plot", "area chart"),
    "K19": ("时间序列图", "time series"),
    "K20": ("热图", "heatmap", "heat map"),
    "K21": ("相关矩阵图", "correlation matrix"),
    "K22": ("填色等高线图", "filled contour"),
    "K24": ("分面图", "faceted plot", "facet plot"),
    "S34": ("nyquist图", "nyquist plot", "nyquist"),
    "S61": ("混淆矩阵", "confusion matrix"),
    "X02": ("垂线图", "drop line"),
    "X03": ("棒棒糖图", "lollipop"),
    "X05": ("蜂群图", "beeswarm"),
    "X09": ("浮动柱状图", "floating column"),
    "X13": ("人口金字塔", "population pyramid"),
    "X23": ("双y轴折线图", "dual-y line", "dual y line"),
    "X24": ("帕累托图", "pareto"),
    "X35": ("双y轴柱状图", "dual-y column", "dual y column"),
    "X36": ("双y轴柱线图", "dual-y column and line", "dual y column and line"),
    "X38": ("y偏移堆叠线图", "y-offset stacked line", "y offset stacked line"),
    "X39": ("线条序列图", "line series"),
    "X40": ("前后对比图", "before and after"),
}


def _explicit_profile_ids(request: ContextBuildRequest) -> tuple[str, ...]:
    allowed = tuple(request.chart_capabilities.allowed_chart_type_ids)
    folded = re.sub(r"\s+", "", request.user_instruction.casefold())
    direct = tuple(profile_id for profile_id in allowed if profile_id.casefold() in folded)
    if direct:
        return direct
    candidates = sorted(
        (
            (re.sub(r"\s+", "", alias.casefold()), profile_id)
            for profile_id in allowed
            for alias in _PROFILE_ALIASES.get(profile_id, ())
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    remaining = folded
    found: list[str] = []
    for alias, profile_id in candidates:
        if alias and alias in remaining:
            if profile_id not in found:
                found.append(profile_id)
            remaining = remaining.replace(alias, "", 1)
    return tuple(profile_id for profile_id in allowed if profile_id in found)


def _prompt_profile_ids(request: ContextBuildRequest) -> tuple[str, ...]:
    allowed = tuple(request.chart_capabilities.allowed_chart_type_ids)
    return _explicit_profile_ids(request) or allowed


def _field_groups(fields: tuple[AuthoritativeField, ...]) -> tuple[tuple[str, ...], ...]:
    grouped: dict[str, list[str]] = {}
    for field in fields:
        match = re.match(r"^(data_\d+)_", field.field_alias)
        key = match.group(1) if match is not None else "active_target"
        grouped.setdefault(key, []).append(field.logical_type)
    return tuple(tuple(logical_types) for logical_types in grouped.values())


def _roles_match_field_types(required_roles: tuple[str, ...], field_types: tuple[str, ...]) -> bool:
    candidates: list[tuple[int, ...]] = []
    for role in required_roles:
        if role == "time":
            matching = tuple(
                index
                for index, logical_type in enumerate(field_types)
                if logical_type == "datetime"
            )
        elif role in _NON_NUMERIC_FIELD_ROLES:
            matching = tuple(range(len(field_types)))
        else:
            matching = tuple(
                index for index, logical_type in enumerate(field_types) if logical_type == "numeric"
            )
        if not matching:
            return False
        candidates.append(matching)

    def assign(position: int, used: frozenset[int]) -> bool:
        if position == len(candidates):
            return True
        return any(
            index not in used and assign(position + 1, used | {index})
            for index in candidates[position]
        )

    candidates.sort(key=len)
    return assign(0, frozenset())


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


def is_removed_composition_request(instruction: str) -> bool:
    """Recognize requests for the removed multi-plot composition product surface."""

    normalized = re.sub(r"\s+", "", instruction.casefold()).replace("_", "").replace("-", "")
    return any(
        marker in normalized
        for marker in (
            "组合图",
            "合并图",
            "图形拼接",
            "拼接图",
            "mergegraph",
            "combineplots",
            "compositefigure",
        )
    )


def is_multi_source_same_chart_request(instruction: str) -> bool:
    """Recognize data concatenation into one grouped chart, not graph composition."""

    normalized = re.sub(r"\s+", "", instruction.casefold()).replace("_", "")
    chinese_same_chart = (
        any(marker in normalized for marker in ("同一张", "同一幅", "同一个"))
        and any(marker in normalized for marker in ("图", "绘制", "画"))
        and any(marker in normalized for marker in ("合并", "放到", "放在", "画到", "画在"))
    )
    return any(
        marker in normalized
        for marker in (
            "同一张图",
            "同一幅图",
            "同图",
            "合在一张图",
            "画在一张图",
            "按数据来源分组",
            "samechart",
            "sameplot",
            "onechart",
            "oneplot",
            "groupedbysource",
        )
    ) or chinese_same_chart


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
        preflight = self.preflight(context_request)
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
        prompt = engine_agent_prompt(self._codec, _prompt_profile_ids(context_request))
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

    def preflight(self, request: ContextBuildRequest) -> NeedsInput | Unsupported | None:
        """Return a deterministic bounded decision before any model runtime is invoked."""
        target = request.project.target
        if is_removed_composition_request(request.user_instruction):
            explanation = (
                "当前产品不提供组合图或图形合并。请编辑单张已选图，或选择受支持的单图图类。"
                if request.locale.casefold().startswith("zh")
                else (
                    "Plot composition and graph merging are not supported. "
                    "Edit one selected plot or choose a supported single-plot chart type."
                )
            )
            return Unsupported(
                target_alias=target.object_alias,
                category="profile_capability",
                explanation=explanation,
            )
        if target.object_type != "source_dataset":
            return None
        if is_multi_source_same_chart_request(request.user_instruction):
            source_count = 1 + sum(
                item.object_type == "source_dataset"
                for item in request.project.selected_objects
            )
            if source_count < 2:
                prompt = (
                    "请至少再选择一个数据表；同图绘制需要 2 至 8 个同构数据源。"
                    if request.locale.casefold().startswith("zh")
                    else (
                        "Select at least one more dataset; a combined plot needs "
                        "2 to 8 isomorphic sources."
                    )
                )
                return NeedsInput(
                    target_alias=target.object_alias,
                    questions=(
                        InputQuestion(
                            question_key="source_datasets",
                            prompt=prompt,
                            input_kind="text",
                        ),
                    ),
                )
        requested_profiles = _explicit_profile_ids(request)
        if not requested_profiles and len(request.chart_capabilities.allowed_chart_type_ids) == 1:
            requested_profiles = request.chart_capabilities.allowed_chart_type_ids
        if requested_profiles:
            manifests = {
                str(item["profile_id"]): item for item in self._codec.profile_manifest()
            }
            source_field_groups = _field_groups(request.project.fields)
            incompatible: list[str] = []
            for profile_id in requested_profiles:
                manifest = manifests.get(profile_id)
                if manifest is None:
                    continue
                required_value = manifest.get("required_roles", ())
                required_roles = (
                    tuple(str(role) for role in required_value)
                    if isinstance(required_value, (tuple, list))
                    else ()
                )
                if required_roles and not any(
                    _roles_match_field_types(required_roles, field_types)
                    for field_types in source_field_groups
                ):
                    if request.locale.casefold().startswith("zh"):
                        aliases = _PROFILE_ALIASES.get(profile_id, ())
                        incompatible.append(aliases[0] if aliases else profile_id)
                    else:
                        incompatible.append(str(manifest.get("display_name", profile_id)))
            if incompatible:
                names = "、".join(incompatible)
                prompt = (
                    f"当前数据字段类型无法满足 {names} 的必填角色。"
                    "请补充兼容字段，或选择适合当前数据的图类。"
                    if request.locale.casefold().startswith("zh")
                    else (
                        f"The current field types cannot satisfy the required roles for {names}. "
                        "Provide compatible fields or choose a chart type that fits this data."
                    )
                )
                return NeedsInput(
                    target_alias=target.object_alias,
                    questions=(
                        InputQuestion(
                            question_key="field_types",
                            prompt=prompt,
                            input_kind="text",
                        ),
                    ),
                )
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

    def prepare_external(
        self, request: ContextBuildRequest
    ) -> tuple[ContextEnvelope, dict[str, object], str]:
        """Build the bounded context and public decision contract for an external runtime.

        The external runtime may deliberate and call its own tools, but the returned
        decision still has to pass :meth:`accept_external` before it can become a
        PlotAgent plan.
        """

        envelope = self._context_builder.build(request)
        schema = _DECISION_ADAPTER.json_schema(mode="validation")
        return envelope, schema, engine_agent_prompt(
            self._codec, _prompt_profile_ids(request)
        ).text

    def accept_external(
        self,
        decision_payload: object,
        *,
        envelope: ContextEnvelope,
        project_context: ProjectContextSnapshot,
        target_profiles: dict[str, str] | None = None,
        client_model_run_id: str,
    ) -> EngineAgentRunResult:
        """Validate and bind a decision produced by Pi or another trusted runtime."""

        try:
            decision = _DECISION_ADAPTER.validate_json(
                canonical_json(cast(JsonValue, decision_payload))
            )
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
        except ValidationError:
            return EngineAgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=False,
                error_code="SCHEMA_INVALID",
            )
        except AgentRuntimeError as error:
            return EngineAgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=False,
                error_code=error.code,
            )
        except EngineCommandError:
            return EngineAgentRunResult(
                client_model_run_id=client_model_run_id,
                accepted=False,
                error_code="ENGINE_PLAN_INVALID",
            )
        return EngineAgentRunResult(
            client_model_run_id=client_model_run_id,
            accepted=True,
            decision=decision,
            bound_plan=bound,
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
            fields = {
                item.field_alias: item.logical_type
                for item in envelope.selected_context.fields
            }
            for action in decision.actions:
                if isinstance(action, (AgentCreatePlot, AgentBindFields)):
                    binding_groups: tuple[tuple[AgentFieldBinding, ...], ...] = (
                        action.bindings,
                    )
                elif isinstance(action, AgentCreateCombinedPlot):
                    binding_groups = tuple(source.bindings for source in action.sources)
                else:
                    continue
                for bindings in binding_groups:
                    for binding in bindings:
                        logical_type = fields.get(binding.field_alias)
                        if logical_type is None:
                            continue
                        if binding.role == "time" and logical_type != "datetime":
                            raise AgentRuntimeError("FIELD_TYPE_INCOMPATIBLE")
                        if (
                            binding.role not in _NON_NUMERIC_FIELD_ROLES
                            and logical_type != "numeric"
                        ):
                            raise AgentRuntimeError("FIELD_TYPE_INCOMPATIBLE")
            if is_multi_source_same_chart_request(envelope.user_instruction):
                create_actions = tuple(
                    action
                    for action in decision.actions
                    if isinstance(action, (AgentCreatePlot, AgentCreateCombinedPlot))
                )
                if not create_actions or any(
                    not isinstance(action, AgentCreateCombinedPlot)
                    for action in create_actions
                ):
                    raise AgentRuntimeError("COMBINED_ACTION_REQUIRED")

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
