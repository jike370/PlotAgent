from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from plotagent.desktop_core.services import RpcServiceError
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
    provider = FakeProvider(responses=[response])
    first = ApplicationHarness(root, provider)
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
                "selected_chart_id": "K01",
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
        assert provider.requests[0].envelope.chart_capabilities.allowed_chart_type_ids == (
            "K01",
        )
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


def test_manual_batch_uses_persisted_plan_and_assembles_authoritative_batch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "planned-batch"
    first = ApplicationHarness(root)
    try:
        project_id, revision = _create_open(first)
        imported = _import(first, project_id, revision, "excel_two_sheets.xlsx", "plan-batch")
        datasets = imported["datasets"]
        described = first.call(
            "datasets.describe",
            {
                "project_id": project_id,
                "source_dataset_id": datasets[0]["source_dataset_id"],
                "source_version": datasets[0]["source_version"],
            },
        )
        numeric = [
            field["field_id"]
            for field in described["dataset"]["fields"]
            if field["logical_type"] == "numeric"
        ]
        created = first.call(
            "agent.plans.create_batch",
            {
                "project_id": project_id,
                "source_datasets": [
                    {
                        "source_dataset_id": dataset["source_dataset_id"],
                        "source_version": dataset["source_version"],
                    }
                    for dataset in datasets
                ],
                "chart_type_id": "K01",
                "field_mapping": {"x": numeric[0], "y": numeric[1]},
                "expected_version": imported["project_version"],
            },
        )
        plan = created["task_plan"]
        assert plan["state"] == "needs_confirmation"
        assert [item["action"]["action_type"] for item in plan["items"]] == [
            "create_plot",
            "create_plot",
            "create_batch",
        ]
        assert [item["expected_objects"][0]["object_id"] for item in plan["items"][:2]] == [
            dataset["source_dataset_id"] for dataset in datasets
        ]
        plan_id = plan["plan_id"]
        first.call(
            "agent.plans.confirm",
            {"project_id": project_id, "plan_id": plan_id, "accept": True},
        )
        executed = first.call(
            "agent.plans.run",
            {"project_id": project_id, "plan_id": plan_id},
        )
        assert executed["task_plan"]["state"] == "succeeded"
        assert executed["completed_item_count"] == 3
        assert [item["attempt_count"] for item in executed["task_plan"]["items"]] == [1, 1, 1]
        batch_output = executed["task_plan"]["items"][-1]["outputs"][0]["object_ref"]
        assert batch_output["object_type"] == "batch"
        stored = first.call(
            "batch.get",
            {"project_id": project_id, "batch_id": batch_output["object_id"]},
        )
        assert [item["state"] for item in stored["batch"]["item_states"]] == [
            "succeeded",
            "succeeded",
        ]
        context = first.call("agent.context.get", {"project_id": project_id})
        assert context["conversation_state"]["current_target"]["object_type"] == "batch"
        project_version = stored["project_version"]
        replayed = first.call(
            "agent.plans.run",
            {"project_id": project_id, "plan_id": plan_id},
        )
        assert replayed["task_plan"]["state"] == "succeeded"
        assert first.call(
            "batch.get",
            {"project_id": project_id, "batch_id": batch_output["object_id"]},
        )["project_version"] == project_version
    finally:
        first.close()

    second = ApplicationHarness(root)
    try:
        second.call("projects.open", {"project_id": project_id})
        restored = second.call(
            "agent.plans.get",
            {"project_id": project_id, "plan_id": plan_id},
        )
        assert restored["state"] == "succeeded"
        stored = second.call(
            "batch.get",
            {"project_id": project_id, "batch_id": batch_output["object_id"]},
        )
        assert len(stored["batch"]["item_states"]) == 2
    finally:
        second.close()


def test_manual_batch_resumes_only_transiently_failed_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = ApplicationHarness(tmp_path / "resumable-batch")
    try:
        project_id, revision = _create_open(app)
        imported = _import(app, project_id, revision, "excel_two_sheets.xlsx", "resume-batch")
        datasets = imported["datasets"]
        described = app.call(
            "datasets.describe",
            {
                "project_id": project_id,
                "source_dataset_id": datasets[0]["source_dataset_id"],
                "source_version": datasets[0]["source_version"],
            },
        )
        numeric = [
            field["field_id"]
            for field in described["dataset"]["fields"]
            if field["logical_type"] == "numeric"
        ]
        created = app.call(
            "agent.plans.create_batch",
            {
                "project_id": project_id,
                "source_datasets": [
                    {
                        "source_dataset_id": dataset["source_dataset_id"],
                        "source_version": dataset["source_version"],
                    }
                    for dataset in datasets
                ],
                "chart_type_id": "K01",
                "field_mapping": {"x": numeric[0], "y": numeric[1]},
                "expected_version": imported["project_version"],
            },
        )
        plan_id = created["task_plan"]["plan_id"]
        app.call(
            "agent.plans.confirm",
            {"project_id": project_id, "plan_id": plan_id, "accept": True},
        )
        original = app.application._plots_create  # noqa: SLF001
        failed_once = False

        def flaky_create(
            context: Any,
            params: Any,
            *,
            provenance_origin: str = "manual",
            plan_id: str | None = None,
        ) -> Any:
            nonlocal failed_once
            second_item = isinstance(params, dict) and str(
                params.get("plot_id", "")
            ).endswith(".2")
            if not failed_once and second_item:
                failed_once = True
                raise RpcServiceError(
                    "WORKER_CAPACITY_EXHAUSTED",
                    "The local worker is temporarily busy.",
                )
            return original(
                context,
                params,
                provenance_origin=provenance_origin,  # type: ignore[arg-type]
                plan_id=plan_id,
            )

        monkeypatch.setattr(app.application, "_plots_create", flaky_create)
        partial = app.call(
            "agent.plans.run",
            {"project_id": project_id, "plan_id": plan_id},
        )
        assert partial["task_plan"]["state"] == "partial_success"
        assert [item["state"] for item in partial["task_plan"]["items"]] == [
            "succeeded",
            "failed",
            "blocked",
        ]
        assert partial["resumable"] is True

        completed = app.call(
            "agent.plans.resume",
            {"project_id": project_id, "plan_id": plan_id},
        )
        assert completed["task_plan"]["state"] == "succeeded"
        assert [item["attempt_count"] for item in completed["task_plan"]["items"]] == [
            1,
            2,
            1,
        ]
        batch_output = completed["task_plan"]["items"][-1]["outputs"][0]["object_ref"]
        stored = app.call(
            "batch.get",
            {"project_id": project_id, "batch_id": batch_output["object_id"]},
        )
        assert len(stored["batch"]["item_states"]) == 2
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
                "user_instruction": "请用 K01 绘制折线图，但先确认 Y 字段",
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


def test_unspecified_source_chart_preflight_asks_without_model_or_project_change(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(responses=[])
    app = ApplicationHarness(tmp_path / "unspecified-chart", provider)
    try:
        project_id, revision = _create_open(app)
        imported = _import(app, project_id, revision, "excel_two_sheets.xlsx", "unspecified")
        dataset = imported["datasets"][0]

        result = app.call(
            "agent.decide",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "user_instruction": "画一张图。",
                "client_model_run_id": "model-run:unspecified-chart",
                "expected_version": imported["project_version"],
                "execution_mode": "execute",
                "network_mode": "custom_provider",
                "provider": {},
                "retention_acknowledged": True,
            },
        )
        listed = app.call("datasets.list", {"project_id": project_id})
        context = app.call("agent.context.get", {"project_id": project_id})
    finally:
        app.close()

    assert result["accepted"] is True
    assert result["decision"] == {
        "schema_version": "1.0",
        "decision_type": "needs_input",
        "target_alias": "active_target",
        "questions": [
            {
                "question_key": "chart_type",
                "prompt": "请选择要绘制的图形类型。",
                "input_kind": "text",
                "choices": [],
            }
        ],
        "data_request": None,
    }
    assert "task_plan" not in result and "execution" not in result
    assert provider.requests == []
    assert listed["project_version"] == imported["project_version"]
    assert context["conversation_state"]["unresolved_question_ids"] == ["chart_type"]


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
