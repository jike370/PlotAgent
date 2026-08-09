from __future__ import annotations

from pathlib import Path

from plotagent.agent.evaluation import Seq70TaskSet, score_model_result
from scripts.run_seq70_agent_eval import _aggregate, _write_report

TASK_SET = Path(__file__).resolve().parents[1] / "fixtures" / "seq70" / "agent_tasks.json"


def _tasks() -> Seq70TaskSet:
    return Seq70TaskSet.model_validate_json(TASK_SET.read_text(encoding="utf-8"))


def test_frozen_seq70_task_set_has_24_tasks_and_three_repetitions() -> None:
    task_set = _tasks()

    assert task_set.repeats == 3
    assert len(task_set.tasks) == 24
    assert sum(task.layer == "model" for task in task_set.tasks) == 18
    assert sum(task.layer == "runtime" for task in task_set.tasks) == 6
    assert {task.category for task in task_set.tasks}.issuperset(
        {
            "plan_mapping",
            "cross_turn_binding",
            "batch_scope_binding",
            "necessary_question",
            "scope_rejection",
            "batch_completion",
            "partial_failure_recovery",
            "idempotent_replay",
            "stale_rejection",
            "restart_recovery",
        }
    )


def test_model_scorer_accepts_exact_create_mapping() -> None:
    task = next(task for task in _tasks().tasks if task.task_id == "D01")
    result = {
        "accepted": True,
        "decision": {
            "decision_type": "action_plan",
            "actions": [
                {
                    "action_type": "create_plot",
                    "target_alias": "active_target",
                    "chart_type_id": "K01",
                    "field_selections": [
                        {"role": "x", "context_field_alias": "x_field"},
                        {"role": "y", "context_field_alias": "y_field"},
                    ],
                }
            ],
        },
        "task_plan": {"state": "ready"},
    }

    score = score_model_result(task, result)

    assert score.passed is True
    assert score.plan_legal is True
    assert score.field_mapping_correct is True
    assert score.target_binding_correct is True


def test_model_scorer_rejects_silent_substitution_and_invalid_question() -> None:
    task_set = _tasks()
    invalid_chart = next(task for task in task_set.tasks if task.task_id == "D18")
    title = next(task for task in task_set.tasks if task.task_id == "D07")

    substituted = score_model_result(
        invalid_chart,
        {
            "accepted": True,
            "decision": {
                "decision_type": "action_plan",
                "actions": [
                    {
                        "action_type": "create_plot",
                        "target_alias": "active_target",
                        "chart_type_id": "K01",
                        "field_selections": [],
                    }
                ],
            },
            "task_plan": {"state": "ready"},
        },
    )
    over_asked = score_model_result(
        title,
        {
            "accepted": True,
            "decision": {
                "decision_type": "needs_input",
                "questions": [
                    {
                        "question_key": "title",
                        "prompt": "请提供标题",
                        "input_kind": "text",
                        "choices": [],
                    }
                ],
            },
        },
    )

    assert substituted.passed is False
    assert substituted.incorrect_auto_binding is True
    assert over_asked.passed is False
    assert over_asked.invalid_question is True


def test_model_scorer_uses_the_public_axis_scale_field() -> None:
    task = next(task for task in _tasks().tasks if task.task_id == "D09")
    score = score_model_result(
        task,
        {
            "accepted": True,
            "decision": {
                "decision_type": "action_plan",
                "actions": [
                    {
                        "action_type": "patch_plot",
                        "target_alias": "active_target",
                        "patches": [
                            {
                                "operation": "set_axis_scale",
                                "target_alias": "y_axis",
                                "scale": "log10",
                            }
                        ],
                    }
                ],
            },
            "task_plan": {"state": "ready"},
        },
    )

    assert score.passed is True


def test_seq70_aggregate_reports_repair_exhausted_with_null_decision(tmp_path: Path) -> None:
    model_record = {
        "task_id": "D14",
        "repetition": 2,
        "layer": "model",
        "category": "necessary_question",
        "passed": False,
        "latency_seconds": 8.3622,
        "score": {
            "passed": False,
            "schema_accepted": False,
            "expected_plan": False,
            "plan_legal": False,
            "target_binding_applicable": False,
            "target_binding_correct": True,
            "field_mapping_applicable": False,
            "field_mapping_correct": True,
            "necessary_question_applicable": True,
            "necessary_question_correct": False,
            "invalid_question": False,
            "incorrect_auto_binding": False,
            "failures": [
                "decision_rejected:REPAIR_EXHAUSTED",
                "decision_type:None",
                "necessary_question_missing_or_unbounded",
            ],
        },
        "decision": None,
        "error": {
            "code": "REPAIR_EXHAUSTED",
            "message": "The Agent decision was not accepted.",
            "side_effects_committed": False,
        },
    }
    runtime_record = {
        "task_id": "R01",
        "repetition": 1,
        "layer": "runtime",
        "category": "batch_completion",
        "passed": True,
        "latency_seconds": 0.01,
        "details": {"batch_completion": True},
        "error": None,
    }

    task_set = _tasks()
    summary = _aggregate(task_set, [model_record, runtime_record], [])
    report = {
        "generated_at": "2026-08-09T20:45:05+08:00",
        "provider": task_set.provider,
        "summary": summary,
        "runs": [model_record, runtime_record],
    }

    _write_report(tmp_path, report)

    assert summary["qualification"] == "NO_GO"
    assert summary["metrics"]["necessary_question_rate"]["value"] == 0.0
    assert summary["metrics"]["model_task_exact_success_rate"]["value"] == 0.0
    markdown = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert "D14 / 第 2 次" in markdown
    assert "decision_rejected:REPAIR_EXHAUSTED" in markdown
