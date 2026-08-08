from __future__ import annotations

import json
from pathlib import Path

from tests.desktop_core.test_application import (
    ApplicationHarness,
    FakeProvider,
    _create_open,
    _import,
)


def test_plan_only_persists_context_and_confirmation_across_restart(tmp_path: Path) -> None:
    response = json.dumps(
        {
            "schema_version": "1.0",
            "decision_type": "action_plan",
            "plan_id": "plan:persistent-title",
            "target_alias": "active_target",
            "confirmation": "required",
            "actions": [
                {
                    "action_type": "patch_plot",
                    "action_id": "action:title",
                    "target_alias": "active_target",
                    "patches": [
                        {
                            "operation": "set_plot_title",
                            "target_alias": "active_target",
                            "title": "Planned title",
                        }
                    ],
                }
            ],
        }
    )
    root = tmp_path / "persistent-agent"
    first = ApplicationHarness(root, FakeProvider(responses=[response]))
    try:
        project_id, revision = _create_open(first)
        imported = _import(first, project_id, revision, "excel_two_sheets.xlsx", "persistent")
        dataset = imported["datasets"][0]
        described = first.call(
            "datasets.describe",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
            },
        )
        numeric = [
            item["field_id"]
            for item in described["dataset"]["fields"]
            if item["logical_type"] == "numeric"
        ]
        created = first.call(
            "plots.create",
            {
                "project_id": project_id,
                "plot_id": "plot:persistent",
                "chart_type_id": "K01",
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "field_mapping": {"x": numeric[0], "y": numeric[1]},
                "idempotency_key": "persistent-plot",
                "expected_version": imported["project_version"],
            },
        )
        planned = first.call(
            "agent.decide",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "user_instruction": "把标题改成 Planned title",
                "client_model_run_id": "model-run:persistent",
                "expected_version": created["project_version"],
                "target": {"kind": "plot", "id": "plot:persistent"},
                "scope": "current",
                "execution_mode": "plan_only",
                "network_mode": "custom_provider",
                "provider": {},
                "retention_acknowledged": True,
            },
        )
        assert planned["task_plan"]["state"] == "needs_confirmation"
        assert "execution" not in planned
        context = first.call("agent.context.get", {"project_id": project_id})
        assert context["conversation_state"]["current_target"]["object_id"] == ("plot:persistent")
        unchanged = first.call(
            "plots.get", {"project_id": project_id, "plot_id": "plot:persistent"}
        )
        assert unchanged["spec"]["title"] is None
    finally:
        first.close()

    second = ApplicationHarness(root)
    try:
        second.call("projects.open", {"project_id": project_id})
        stored = second.call(
            "agent.plans.get",
            {"project_id": project_id, "plan_id": "plan:persistent-title"},
        )
        assert stored["state"] == "needs_confirmation"
        confirmed = second.call(
            "agent.plans.confirm",
            {
                "project_id": project_id,
                "plan_id": "plan:persistent-title",
                "accept": True,
            },
        )
        assert confirmed["state"] == "ready"
        assert confirmed["confirmation_state"] == "confirmed"
        executed = second.call(
            "agent.plans.run",
            {
                "project_id": project_id,
                "plan_id": "plan:persistent-title",
            },
        )
        assert executed["task_plan"]["state"] == "succeeded"
        assert executed["completed_item_count"] == 1
        assert executed["change_set"]["items"][0]["after"][0]["object_ref"]["object_version"] == 2
        events = second.call(
            "agent.plans.events",
            {"project_id": project_id, "plan_id": "plan:persistent-title"},
        )
        assert events["plan_id"] == "plan:persistent-title"
        event_types = [event["event_type"] for event in events["events"]]
        assert event_types[0:2] == ["plan.created", "plan.confirmed"]
        assert "item.attempt_started" in event_types
        assert "item.attempt_finished" in event_types
        changed = second.call("plots.get", {"project_id": project_id, "plot_id": "plot:persistent"})
        assert changed["spec"]["title"]["nodes"][0]["text"] == "Planned title"
        context = second.call("agent.context.get", {"project_id": project_id})
        assert context["conversation_state"]["current_target"]["object_version"] == 2
    finally:
        second.close()


def test_create_then_patch_plan_uses_predecessor_output_as_cross_step_target(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        responses=[
            json.dumps(
                {
                    "schema_version": "1.0",
                    "decision_type": "action_plan",
                    "plan_id": "plan:create-and-title",
                    "target_alias": "active_target",
                    "actions": [
                        {
                            "action_type": "create_plot",
                            "action_id": "action:create",
                            "target_alias": "active_target",
                            "chart_type_id": "K01",
                            "field_selections": [
                                {"role": "x", "context_field_alias": "x_field"},
                                {"role": "y", "context_field_alias": "y_field"},
                            ],
                        },
                        {
                            "action_type": "patch_plot",
                            "action_id": "action:title",
                            "depends_on": ["action:create"],
                            "target_alias": "active_target",
                            "patches": [
                                {
                                    "operation": "set_plot_title",
                                    "target_alias": "active_target",
                                    "title": "Created and titled",
                                }
                            ],
                        },
                    ],
                }
            ),
            json.dumps(
                {
                    "schema_version": "1.0",
                    "decision_type": "no_change",
                    "target_alias": "active_target",
                    "explanation": "标题已经符合要求。",
                }
            ),
        ]
    )
    app = ApplicationHarness(tmp_path / "two-step", provider)
    try:
        project_id, revision = _create_open(app)
        imported = _import(app, project_id, revision, "excel_two_sheets.xlsx", "two-step")
        dataset = imported["datasets"][0]
        planned = app.call(
            "agent.decide",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "user_instruction": "画图并设置标题",
                "client_model_run_id": "model-run:two-step",
                "expected_version": imported["project_version"],
                "execution_mode": "plan_only",
                "network_mode": "custom_provider",
                "provider": {},
                "retention_acknowledged": True,
            },
        )
        assert [item["state"] for item in planned["task_plan"]["items"]] == [
            "ready",
            "pending",
        ]
        executed = app.call(
            "agent.plans.run",
            {"project_id": project_id, "plan_id": "plan:create-and-title"},
        )
        assert executed["task_plan"]["state"] == "succeeded"
        assert [item["attempt_count"] for item in executed["task_plan"]["items"]] == [1, 1]
        stored = app.call(
            "plots.get",
            {"project_id": project_id, "plot_id": "plot:agent.create-and-title.1"},
        )
        assert stored["plot_version"] == 2
        assert stored["spec"]["title"]["nodes"][0]["text"] == "Created and titled"
        follow_up = app.call(
            "agent.decide",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "user_instruction": "这个标题保持不变",
                "client_model_run_id": "model-run:follow-up",
                "expected_version": stored["project_version"],
                "execution_mode": "plan_only",
                "network_mode": "custom_provider",
                "provider": {},
                "retention_acknowledged": True,
            },
        )
        assert follow_up["decision"]["decision_type"] == "no_change"
        assert provider.requests[-1].envelope.target_snapshot.object_id == (
            "plot:agent.create-and-title.1"
        )
        assert provider.requests[-1].envelope.target_snapshot.object_version == 2
    finally:
        app.close()


def test_needs_input_is_persisted_as_bounded_conversation_state(tmp_path: Path) -> None:
    provider = FakeProvider(
        responses=[
            json.dumps(
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
                                {"value": "y_field", "label": "信号"},
                                {"value": "value_field", "label": "数值"},
                            ],
                        }
                    ],
                }
            )
        ]
    )
    app = ApplicationHarness(tmp_path / "needs-input", provider)
    try:
        project_id, revision = _create_open(app)
        imported = _import(app, project_id, revision, "excel_two_sheets.xlsx", "needs-input")
        dataset = imported["datasets"][0]
        result = app.call(
            "agent.decide",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "user_instruction": "画一张图",
                "client_model_run_id": "model-run:needs-input",
                "expected_version": imported["project_version"],
                "execution_mode": "plan_only",
                "network_mode": "custom_provider",
                "provider": {},
                "retention_acknowledged": True,
            },
        )
        assert result["decision"]["decision_type"] == "needs_input"
        context = app.call("agent.context.get", {"project_id": project_id})
        assert context["conversation_state"]["unresolved_question_ids"] == ["choose_y"]
        assert context["conversation_state"]["recent_result_kinds"] == ["needs_input"]
        assert context["context_snapshot"]["field_bindings"]
    finally:
        app.close()


def test_plan_stops_as_stale_when_target_changes_before_execution(tmp_path: Path) -> None:
    provider = FakeProvider(
        responses=[
            json.dumps(
                {
                    "schema_version": "1.0",
                    "decision_type": "action_plan",
                    "plan_id": "plan:stale-title",
                    "target_alias": "active_target",
                    "actions": [
                        {
                            "action_type": "patch_plot",
                            "action_id": "action:title",
                            "target_alias": "active_target",
                            "patches": [
                                {
                                    "operation": "set_plot_title",
                                    "target_alias": "active_target",
                                    "title": "Agent title",
                                }
                            ],
                        }
                    ],
                }
            )
        ]
    )
    app = ApplicationHarness(tmp_path / "stale", provider)
    try:
        project_id, revision = _create_open(app)
        imported = _import(app, project_id, revision, "excel_two_sheets.xlsx", "stale")
        dataset = imported["datasets"][0]
        described = app.call(
            "datasets.describe",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
            },
        )
        numeric = [
            item["field_id"]
            for item in described["dataset"]["fields"]
            if item["logical_type"] == "numeric"
        ]
        created = app.call(
            "plots.create",
            {
                "project_id": project_id,
                "plot_id": "plot:stale",
                "chart_type_id": "K01",
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "field_mapping": {"x": numeric[0], "y": numeric[1]},
                "idempotency_key": "stale-create",
                "expected_version": imported["project_version"],
            },
        )
        app.call(
            "agent.decide",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "user_instruction": "改标题",
                "client_model_run_id": "model-run:stale",
                "expected_version": created["project_version"],
                "target": {"kind": "plot", "id": "plot:stale"},
                "scope": "current",
                "execution_mode": "plan_only",
                "network_mode": "custom_provider",
                "provider": {},
                "retention_acknowledged": True,
            },
        )
        app.call(
            "plots.patch",
            {
                "project_id": project_id,
                "plot_id": "plot:stale",
                "expected_version": 1,
                "idempotency_key": "manual-wins",
                "patch": {
                    "operation": "set_plot_title",
                    "target_id": "plot:stale",
                    "expected_plot_version": 1,
                    "title": {"nodes": [{"kind": "plain", "text": "Manual title"}]},
                },
            },
        )

        result = app.call(
            "agent.plans.run",
            {"project_id": project_id, "plan_id": "plan:stale-title"},
        )

        assert result["task_plan"]["state"] == "stale"
        assert result["task_plan"]["items"][0]["attempt_count"] == 0
        stored = app.call("plots.get", {"project_id": project_id, "plot_id": "plot:stale"})
        assert stored["spec"]["title"]["nodes"][0]["text"] == "Manual title"
    finally:
        app.close()
