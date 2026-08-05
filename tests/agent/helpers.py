from __future__ import annotations

import json
from dataclasses import dataclass, field

from plotagent.agent.context import (
    AuthoritativeField,
    AuthoritativeProjectContext,
    AuthoritativeSampleRow,
    ContextBuildRequest,
    ConversationState,
    DisclosureGrant,
)
from plotagent.agent.providers import (
    OutputCapability,
    ProviderCapabilities,
    ProviderDecisionRequest,
    ProviderIdentity,
    ProviderProtocol,
    ProviderUsage,
    ProviderWireResponse,
)
from plotagent.agent.validation import ValidationAuthority
from plotagent.contracts.agent_context import (
    ChartCapabilities,
    ContextFieldSummary,
    ContextMessage,
    ContextObjectRef,
)


def no_change_payload(explanation: str = "当前状态已满足 mixed scientific request.") -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "decision_type": "no_change",
            "target_alias": "active_target",
            "explanation": explanation,
        },
        ensure_ascii=False,
    )


def action_plan_payload(*, include_unsupported: bool = False) -> str:
    actions: list[dict[str, object]] = [
        {
            "action_type": "create_plot",
            "action_id": "action:create",
            "target_alias": "active_target",
            "chart_type_id": "K01",
            "field_selections": [
                {"role": "x", "context_field_alias": "x_field"},
                {"role": "y", "context_field_alias": "y_field"},
            ],
        }
    ]
    if include_unsupported:
        actions.append(
            {
                "action_type": "export_artifact",
                "action_id": "action:export",
                "depends_on": ["action:create"],
                "target_alias": "active_target",
                "format": "opju",
                "target_scope": "figure",
                "output_name": "result",
            }
        )
    return json.dumps(
        {
            "schema_version": "1.0",
            "decision_type": "action_plan",
            "plan_id": "plan:test",
            "target_alias": "active_target",
            "actions": actions,
        }
    )


def target(*, version: int = 1) -> ContextObjectRef:
    return ContextObjectRef(
        object_alias="active_target",
        object_id="project:test",
        object_version=version,
        object_type="project",
        content_hash=("a" if version == 1 else "b") * 64,
    )


def context_request(*, field_count: int = 2, row_count: int = 25) -> ContextBuildRequest:
    current = target()
    fields = tuple(
        AuthoritativeField(
            field_alias=(
                "x_field" if index == 0 else "y_field" if index == 1 else f"field_{index}"
            ),
            field_id=f"field:f{index:03d}",
            name=("Time" if index == 0 else "温度" if index == 1 else f"signal_{index}"),
            logical_type="numeric",
            unit_text="s" if index == 0 else "K",
            semantic_role="x" if index == 0 else "y" if index == 1 else None,
            summary=ContextFieldSummary(
                valid_count=row_count,
                missing_count=0,
                numeric_minimum=0.0,
                numeric_maximum=float(max(0, row_count - 1)),
            ),
        )
        for index in range(field_count)
    )
    rows = tuple(
        AuthoritativeSampleRow(
            row_id=f"row-{row}",
            values={field.field_id: float(row + index) for index, field in enumerate(fields)},
        )
        for row in range(row_count)
    )
    return ContextBuildRequest(
        user_instruction="请 plot 温度 versus Time，keep scientific terms in English.",
        locale="zh-CN",
        project=AuthoritativeProjectContext(
            target=current,
            dataset_content_hash="d" * 64,
            fields=fields,
            sample_rows=rows,
            message_window=(
                ContextMessage(role="user", text="previous bounded message"),
            ),
            explicit_field_aliases=("x_field", "y_field"),
        ),
        conversation_state=ConversationState(current_target=current),
        chart_capabilities=ChartCapabilities(
            capability_version="charts-v1",
            allowed_chart_type_ids=("K01",),
            allowed_action_types=("create_plot", "patch_plot", "export_artifact"),
            allowed_patch_operations=("set_axis_scale",),
            export_formats=("png",),
        ),
        disclosure_grant=DisclosureGrant(
            provider_type="custom",
            provider_config_id="custom-test",
            retention_disclosure_version="retention-v1",
            retention_acknowledged=True,
            allowed_categories=frozenset(
                {
                    "user_instruction",
                    "field_metadata",
                    "statistics",
                    "sample",
                    "message_window",
                    "chart_capabilities",
                }
            ),
        ),
    )


def authority(*, current: ContextObjectRef | None = None) -> ValidationAuthority:
    return ValidationAuthority(
        current_target=current or target(),
        allowed_target_aliases=frozenset({"active_target"}),
        allowed_field_aliases=frozenset({"x_field", "y_field"}),
        allowed_action_types=frozenset({"create_plot", "patch_plot"}),
        allowed_chart_type_ids=frozenset({"K01"}),
        allowed_patch_operations=frozenset({"set_axis_scale"}),
        allowed_export_formats=frozenset({"png"}),
        allowed_export_scopes=frozenset({"current_plot"}),
        permission_grants=frozenset({"create_plot", "patch_plot"}),
    )


@dataclass
class FakeProvider:
    capability: OutputCapability
    responses: list[str]
    delay_seconds: float = 0.0
    decide_calls: int = 0
    repair_calls: int = 0
    cancel_calls: int = 0
    requests: list[ProviderDecisionRequest] = field(default_factory=list)

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider_type="custom",
            provider_config_id="custom-test",
            endpoint_origin="https://models.example.test:443",
            model_id="synthetic-model",
            model_profile="fixed-test",
        )

    async def resolve_capabilities(self) -> ProviderCapabilities:
        protocol = (
            ProviderProtocol.NONE
            if self.capability is OutputCapability.P0
            else ProviderProtocol.CHAT_COMPLETIONS
        )
        return ProviderCapabilities(self.capability, protocol)

    async def decide(self, request: ProviderDecisionRequest) -> ProviderWireResponse:
        import asyncio

        self.decide_calls += 1
        self.requests.append(request)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return ProviderWireResponse(
            provider_request_id=f"request-{self.decide_calls}",
            output_text=self.responses.pop(0),
            usage=ProviderUsage(10, 5, "provider"),
        )

    async def repair(
        self,
        request: ProviderDecisionRequest,
        *,
        invalid_candidate: str,
        schema_error_categories: tuple[str, ...],
    ) -> ProviderWireResponse:
        del invalid_candidate, schema_error_categories
        self.repair_calls += 1
        self.requests.append(request)
        return ProviderWireResponse(
            provider_request_id=f"repair-{self.repair_calls}",
            output_text=self.responses.pop(0),
            usage=ProviderUsage(4, 3, "provider"),
        )

    async def cancel(self, client_model_run_id: str) -> None:
        del client_model_run_id
        self.cancel_calls += 1
