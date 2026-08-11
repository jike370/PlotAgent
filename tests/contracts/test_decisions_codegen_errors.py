from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.agent.engine_client import EngineAgentDecision
from plotagent.contracts.codegen import check_outputs, repository_root
from plotagent.contracts.errors import ERRORS_BY_CODE, STABLE_ERROR_REGISTRY, ErrorResponse


def _decision_adapter() -> TypeAdapter[EngineAgentDecision]:
    return TypeAdapter(EngineAgentDecision)


@pytest.mark.parametrize(
    "payload",
    (
        {
            "schema_version": "engine-agent.v1",
            "decision_type": "action_plan",
            "plan_id": "plan:test",
            "target_alias": "active_target",
            "actions": (
                {
                    "operation": "create_plot",
                    "action_id": "action:create",
                    "plot_alias": "result",
                    "profile_id": "K01",
                    "source_alias": "active_target",
                    "bindings": (
                        {"role": "x", "field_alias": "selected_x"},
                        {"role": "y", "field_alias": "selected_y"},
                    ),
                },
            ),
        },
        {
            "schema_version": "engine-agent.v1",
            "decision_type": "needs_input",
            "target_alias": "active_target",
            "questions": (
                {
                    "question_key": "choose_y",
                    "prompt": "请选择 Y 字段",
                    "input_kind": "single_choice",
                    "choices": (
                        {"value": "field_a", "label": "A"},
                        {"value": "field_b", "label": "B"},
                    ),
                },
            ),
        },
        {
            "schema_version": "engine-agent.v1",
            "decision_type": "unsupported",
            "target_alias": "active_target",
            "category": "profile_capability",
            "explanation": "该操作不属于引擎公开能力。",
        },
        {
            "schema_version": "engine-agent.v1",
            "decision_type": "no_change",
            "target_alias": "active_target",
            "explanation": "当前状态已经满足请求。",
        },
    ),
)
def test_engine_agent_decisions_are_closed_and_valid(payload: dict[str, object]) -> None:
    decision = _decision_adapter().validate_python(payload)
    assert decision.decision_type == payload["decision_type"]


def test_agent_plan_rejects_unknown_fields_and_invalid_action_count() -> None:
    payload: dict[str, object] = {
        "schema_version": "engine-agent.v1",
        "decision_type": "action_plan",
        "plan_id": "plan:test",
        "target_alias": "active_target",
        "actions": [
            {
                "operation": "set_title",
                "action_id": "action:title",
                "plot_alias": "active_plot",
                "text": "Result",
            }
        ],
    }
    with pytest.raises(ValidationError):
        _decision_adapter().validate_python({**payload, "tool": "filesystem"})
    with pytest.raises(ValidationError):
        _decision_adapter().validate_python({**payload, "actions": []})


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


def test_agent_schema_has_no_backend_code_or_path_escape_hatches() -> None:
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
        "native_ref",
        "resource_id",
    }
    assert _property_names(_decision_adapter().json_schema()).isdisjoint(forbidden)


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


def test_checked_in_agent_native_schemas_and_types_are_in_sync() -> None:
    root = repository_root()
    assert check_outputs(root) == []
    manifest = json.loads((root / "schemas" / "manifest.json").read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in manifest["files"]}
    assert "schemas/plot-engine-action.schema.json" in paths
    assert "schemas/plot-document.schema.json" in paths
    assert "schemas/engine-agent-decision.schema.json" in paths
    assert all("plot-spec" not in path for path in paths)
