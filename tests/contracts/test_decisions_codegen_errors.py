from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.contracts.codegen import check_outputs, repository_root
from plotagent.contracts.decisions import AgentDecision
from plotagent.contracts.errors import ERRORS_BY_CODE, STABLE_ERROR_REGISTRY, ErrorResponse


def _decision_adapter() -> TypeAdapter[AgentDecision]:
    return TypeAdapter(AgentDecision)


@pytest.mark.parametrize(
    "payload",
    (
        {
            "schema_version": "1.0",
            "decision_type": "action_plan",
            "plan_id": "plan:test",
            "target_alias": "active_target",
            "actions": [
                {
                    "action_type": "create_plot",
                    "action_id": "action:create",
                    "target_alias": "active_target",
                    "chart_type_id": "K01",
                    "field_selections": [
                        {"role": "x", "context_field_alias": "selected_x"},
                        {"role": "y", "context_field_alias": "selected_y"},
                    ],
                }
            ],
        },
        {
            "schema_version": "1.0",
            "decision_type": "needs_input",
            "target_alias": "active_target",
            "questions": [
                {
                    "question_key": "choose_y",
                    "prompt": "请选择 Y 字段",
                    "input_kind": "single_choice",
                    "choices": [
                        {"value": "field_a", "label": "A"},
                        {"value": "field_b", "label": "B"},
                    ],
                }
            ],
        },
        {
            "schema_version": "1.0",
            "decision_type": "needs_input",
            "target_alias": "active_target",
            "data_request": {
                "dataset_alias": "active_target",
                "expected_version": 1,
                "field_aliases": ["selected_x", "selected_y"],
                "requested_categories": ["sample"],
                "estimated_field_count": 2,
                "estimated_row_count": 10,
                "estimated_scalar_count": 20,
                "purpose": "Disambiguate the selected field roles.",
                "default_context_insufficient_reason": "The summary has tied candidates.",
                "smaller_scope_possible": False,
                "authorization_scope": "this_run",
            },
        },
        {
            "schema_version": "1.0",
            "decision_type": "unsupported",
            "target_alias": "active_target",
            "category": "v1_scope",
            "explanation": "该请求超出 v1 范围。",
        },
        {
            "schema_version": "1.0",
            "decision_type": "no_change",
            "target_alias": "active_target",
            "explanation": "当前状态已经满足请求。",
        },
    ),
)
def test_four_agent_decisions_are_valid(payload: dict[str, Any]) -> None:
    decision = _decision_adapter().validate_json(json.dumps(payload, ensure_ascii=False))
    assert decision.decision_type == payload["decision_type"]


def test_action_plan_limit_dependencies_and_unknown_fields() -> None:
    action = {
        "action_type": "patch_batch",
        "action_id": "action:first",
        "target_alias": "active_target",
        "axis_policy": "unified",
    }
    base = {
        "schema_version": "1.0",
        "decision_type": "action_plan",
        "plan_id": "plan:test",
        "target_alias": "active_target",
        "actions": [action],
    }
    with pytest.raises(ValidationError):
        _decision_adapter().validate_json(json.dumps({**base, "tool": "filesystem"}))
    with pytest.raises(ValidationError, match="earlier actions"):
        _decision_adapter().validate_json(
            json.dumps(
                {
                    **base,
                    "actions": [{**action, "depends_on": ["action:later"]}],
                }
            )
        )
    with pytest.raises(ValidationError):
        _decision_adapter().validate_json(
            json.dumps(
                {
                    **base,
                    "actions": [
                        {**action, "action_id": f"action:item{index}"} for index in range(9)
                    ],
                }
            )
        )


def test_agent_category_color_intent_is_closed_and_typed() -> None:
    payload = {
        "schema_version": "1.0",
        "decision_type": "action_plan",
        "plan_id": "plan:category-color",
        "target_alias": "active_target",
        "actions": [
            {
                "action_type": "patch_plot",
                "action_id": "action:category-color",
                "target_alias": "active_target",
                "patches": [
                    {
                        "operation": "set_category_color",
                        "target_alias": "series_1",
                        "category": "Treated",
                        "color": {"value": "#123456"},
                    }
                ],
            }
        ],
    }

    decision = _decision_adapter().validate_json(json.dumps(payload))

    assert decision.decision_type == "action_plan"
    with pytest.raises(ValidationError):
        _decision_adapter().validate_json(
            json.dumps(
                {
                    **payload,
                    "actions": [
                        {
                            **payload["actions"][0],
                            "patches": [
                                {
                                    **payload["actions"][0]["patches"][0],
                                    "color": {"value": "red"},
                                }
                            ],
                        }
                    ],
                }
            )
        )


def test_agent_specialist_intent_is_closed_and_typed() -> None:
    payload = {
        "schema_version": "1.0",
        "decision_type": "action_plan",
        "plan_id": "plan:specialist",
        "target_alias": "active_target",
        "actions": [
            {
                "action_type": "patch_plot",
                "action_id": "action:specialist",
                "target_alias": "active_target",
                "patches": [
                    {
                        "operation": "set_chart_parameters",
                        "target_alias": "active_target",
                        "parameters": {
                            "step_where": "post",
                            "lollipop_baseline": 0,
                            "volcano_absolute_log2_fold_change": 1.5,
                            "volcano_pvalue": 0.01,
                            "pareto_reference_percent": 80,
                        },
                    }
                ],
            }
        ],
    }

    decision = _decision_adapter().validate_json(json.dumps(payload))

    assert decision.decision_type == "action_plan"
    invalid = json.loads(json.dumps(payload))
    invalid["actions"][0]["patches"][0]["parameters"]["origin_property"] = "layer.x"
    with pytest.raises(ValidationError):
        _decision_adapter().validate_python(invalid)


def _property_names(schema: object) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            names.update(str(name) for name in properties)
        for value in schema.values():
            names.update(_property_names(value))
    elif isinstance(schema, list):
        for value in schema:
            names.update(_property_names(value))
    return names


def test_agent_schema_has_no_tool_path_code_or_internal_execution_fields() -> None:
    schema = _decision_adapter().json_schema()
    forbidden = {
        "tool",
        "tools",
        "path",
        "url",
        "script",
        "command",
        "python",
        "sql",
        "table_id",
        "object_id",
        "resource_id",
        "preparation_spec",
        "calculation_kind",
    }
    assert _property_names(schema).isdisjoint(forbidden)


def test_error_registry_is_unique_and_response_shape_is_stable() -> None:
    assert len(ERRORS_BY_CODE) == len(STABLE_ERROR_REGISTRY.errors)
    response = ErrorResponse(
        code="SCHEMA_INVALID",
        severity="blocked",
        retryable=False,
        message="Invalid contract payload.",
    )
    assert response.code == "SCHEMA_INVALID"
    with pytest.raises(ValidationError, match="not registered"):
        ErrorResponse(
            code="UNREGISTERED_ERROR",
            severity="blocked",
            retryable=False,
            message="Unknown.",
        )


def test_checked_in_schema_and_types_are_in_sync() -> None:
    root = repository_root()
    assert check_outputs(root) == []
    manifest = json.loads((root / "schemas" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert manifest["json_schema_draft"].endswith("2020-12/schema")
    assert Path(root / "src/shared/generated/contracts.ts").is_file()
