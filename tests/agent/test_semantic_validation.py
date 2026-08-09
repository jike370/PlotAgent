from __future__ import annotations

from dataclasses import replace

import pytest

from plotagent.agent.context import ContextBuilder
from plotagent.agent.errors import AgentRuntimeError
from plotagent.agent.validation import DecisionValidator, ValidationAuthority
from plotagent.contracts.agent_context import ChartCapabilities, ContextObjectRef
from plotagent.contracts.decisions import (
    ActionPlan,
    AxisLabelIntent,
    CreatePlotAction,
    PatchPlotAction,
    SemanticFieldSelection,
)
from tests.agent.helpers import context_request


def test_axis_patch_cannot_bind_to_the_plot_object() -> None:
    request = context_request()
    x_axis = ContextObjectRef(
        object_alias="x_axis",
        object_id="plot:test",
        object_version=1,
        object_type="plot",
        content_hash="b" * 64,
    )
    request = replace(
        request,
        project=replace(request.project, selected_objects=(x_axis,)),
        chart_capabilities=ChartCapabilities(
            capability_version="charts-v1",
            allowed_chart_type_ids=("K01",),
            allowed_action_types=("patch_plot",),
            allowed_patch_operations=("set_axis_label",),
        ),
    )
    envelope = ContextBuilder().build(request)
    decision = ActionPlan(
        plan_id="plan:wrong-axis-target",
        target_alias="active_target",
        actions=(
            PatchPlotAction(
                action_id="action:axis",
                target_alias="active_target",
                patches=(AxisLabelIntent(target_alias="active_target", label="Time (s)"),),
            ),
        ),
    )
    authority = ValidationAuthority(
        current_target=request.project.target,
        allowed_target_aliases=frozenset({"active_target", "x_axis"}),
        allowed_field_aliases=frozenset({"x_field", "y_field"}),
        allowed_action_types=frozenset({"patch_plot"}),
        allowed_chart_type_ids=frozenset({"K01"}),
        allowed_patch_operations=frozenset({"set_axis_label"}),
        permission_grants=frozenset({"patch_plot"}),
        target_chart_type_ids={"active_target": "K01"},
    )

    with pytest.raises(AgentRuntimeError, match="AGENT_TARGET_INVALID"):
        DecisionValidator().validate(decision, envelope, authority)


def test_k06_explicit_roles_cannot_be_relabelled() -> None:
    request = context_request(field_count=6)
    roles = ("x", "center", "x_lower", "x_upper", "lower", "upper")
    fields = tuple(
        replace(field, name=role, semantic_role=role)
        for field, role in zip(request.project.fields, roles, strict=True)
    )
    request = replace(
        request,
        user_instruction=("Create K06 with x, center, x_lower, x_upper, lower, and upper fields."),
        project=replace(request.project, fields=fields),
        chart_capabilities=ChartCapabilities(
            capability_version="charts-v1",
            allowed_chart_type_ids=("K06",),
            allowed_action_types=("create_plot",),
        ),
    )
    envelope = ContextBuilder().build(request)
    decision = ActionPlan(
        plan_id="plan:wrong-k06-role",
        target_alias="active_target",
        actions=(
            CreatePlotAction(
                action_id="action:create",
                target_alias="active_target",
                chart_type_id="K06",
                field_selections=tuple(
                    SemanticFieldSelection(
                        role=("y" if role == "center" else role),
                        context_field_alias=field.field_alias,
                    )
                    for field, role in zip(fields, roles, strict=True)
                ),
            ),
        ),
    )
    authority = ValidationAuthority(
        current_target=request.project.target,
        allowed_target_aliases=frozenset({"active_target"}),
        allowed_field_aliases=frozenset(field.field_alias for field in fields),
        allowed_action_types=frozenset({"create_plot"}),
        allowed_chart_type_ids=frozenset({"K06"}),
        allowed_patch_operations=frozenset(),
        permission_grants=frozenset({"create_plot"}),
    )

    with pytest.raises(AgentRuntimeError) as captured:
        DecisionValidator().validate(decision, envelope, authority)

    assert "AGENT_FIELD_ROLE_INVALID" in captured.value.categories


def test_unspecified_chart_request_cannot_execute_a_guessed_plot() -> None:
    request = context_request()
    request = replace(
        request,
        user_instruction="画一张图。",
        chart_capabilities=ChartCapabilities(
            capability_version="charts-v1",
            allowed_chart_type_ids=("K01", "K02"),
            allowed_action_types=("create_plot",),
        ),
    )
    envelope = ContextBuilder().build(request)
    decision = ActionPlan(
        plan_id="plan:guessed-chart",
        target_alias="active_target",
        actions=(
            CreatePlotAction(
                action_id="action:create",
                target_alias="active_target",
                chart_type_id="K01",
                field_selections=(
                    SemanticFieldSelection(role="x", context_field_alias="x_field"),
                    SemanticFieldSelection(role="y", context_field_alias="y_field"),
                ),
            ),
        ),
    )
    authority = ValidationAuthority(
        current_target=request.project.target,
        allowed_target_aliases=frozenset({"active_target"}),
        allowed_field_aliases=frozenset({"x_field", "y_field"}),
        allowed_action_types=frozenset({"create_plot"}),
        allowed_chart_type_ids=frozenset({"K01", "K02"}),
        allowed_patch_operations=frozenset(),
        permission_grants=frozenset({"create_plot"}),
    )

    with pytest.raises(AgentRuntimeError) as captured:
        DecisionValidator().validate(decision, envelope, authority)

    assert captured.value.code == "CHART_TYPE_REQUIRED"
