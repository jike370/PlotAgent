"""Contracts and deterministic scoring for the frozen SEQ-70 Agent evaluation set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import StrictModel

EvalTaskId = Annotated[
    str,
    StringConstraints(pattern=r"^[DR][0-9]{2}$", strict=True),
]


class ModelExpectation(StrictModel):
    decision_types: Annotated[tuple[str, ...], Field(min_length=1)]
    action_type: str | None = None
    chart_type_id: str | None = None
    field_mapping: dict[str, str] = {}
    operations: tuple[str, ...] = ()
    action_target_aliases: tuple[str, ...] = ()
    patch_target_aliases: tuple[str, ...] = ()
    exact_title: str | None = None
    exact_axis_label: str | None = None
    exact_axis_scale: Literal["linear", "log10", "datetime", "categorical"] | None = None
    exact_legend_placement: Literal["inside", "outside_right", "outside_bottom"] | None = None
    exact_reference_y: float | None = None
    no_extra_patches: bool = False
    max_questions: Annotated[int, Field(ge=0, le=3)] = 0
    forbidden_action_plan: bool = False

    @model_validator(mode="after")
    def checks_match_decision_kind(self) -> ModelExpectation:
        if self.forbidden_action_plan and "action_plan" in self.decision_types:
            raise ValueError("forbidden action plans cannot be an expected decision type")
        if self.field_mapping and self.action_type != "create_plot":
            raise ValueError("field mapping checks require a create_plot action")
        return self


class EvalTask(StrictModel):
    task_id: EvalTaskId
    layer: Literal["model", "runtime"]
    category: str
    fixture: str | None = None
    setup: str
    instruction: str | None = None
    precondition_instruction: str | None = None
    expectation: ModelExpectation | None = None
    scenario: str | None = None

    @model_validator(mode="after")
    def layer_payload_is_complete(self) -> EvalTask:
        if self.layer == "model":
            if self.instruction is None or self.expectation is None or self.scenario is not None:
                raise ValueError("model tasks require instruction and expectation only")
        elif self.scenario is None or self.expectation is not None or self.instruction is not None:
            raise ValueError("runtime tasks require one scenario and no model expectation")
        return self


class Seq70TaskSet(StrictModel):
    schema_version: Literal["seq70-agent-eval-v1"]
    repeats: Annotated[int, Field(ge=1, le=10)]
    provider: dict[str, str]
    pricing_cny_per_million_tokens: dict[str, float]
    pricing_source: str
    thresholds: dict[str, float]
    tasks: Annotated[tuple[EvalTask, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def frozen_shape(self) -> Seq70TaskSet:
        ids = tuple(task.task_id for task in self.tasks)
        if len(ids) != len(set(ids)):
            raise ValueError("SEQ-70 task ids must be unique")
        if len(self.tasks) != 24:
            raise ValueError("SEQ-70 v1 freezes exactly 24 tasks")
        if sum(task.layer == "model" for task in self.tasks) != 18:
            raise ValueError("SEQ-70 v1 freezes exactly 18 model tasks")
        if sum(task.layer == "runtime" for task in self.tasks) != 6:
            raise ValueError("SEQ-70 v1 freezes exactly 6 runtime tasks")
        return self


@dataclass(frozen=True, slots=True)
class DecisionScore:
    passed: bool
    schema_accepted: bool
    expected_plan: bool
    plan_legal: bool
    target_binding_applicable: bool
    target_binding_correct: bool
    field_mapping_applicable: bool
    field_mapping_correct: bool
    necessary_question_applicable: bool
    necessary_question_correct: bool
    invalid_question: bool
    incorrect_auto_binding: bool
    failures: tuple[str, ...]


def score_model_result(task: EvalTask, result: dict[str, Any]) -> DecisionScore:
    """Score one accepted/rejected desktop Agent result without heuristic text grading."""

    expectation = task.expectation
    if task.layer != "model" or expectation is None:
        raise ValueError("score_model_result requires a model task")
    accepted = result.get("accepted") is True and isinstance(result.get("decision"), dict)
    decision = result.get("decision") if accepted else {}
    assert isinstance(decision, dict)
    decision_type = decision.get("decision_type")
    failures: list[str] = []
    if not accepted:
        error = result.get("error")
        code = error.get("code") if isinstance(error, dict) else "UNKNOWN"
        failures.append(f"decision_rejected:{code}")
    if decision_type not in expectation.decision_types:
        failures.append(f"decision_type:{decision_type!s}")
    if expectation.forbidden_action_plan and decision_type == "action_plan":
        failures.append("forbidden_action_plan")

    actions_value = decision.get("actions") if decision_type == "action_plan" else []
    actions = actions_value if isinstance(actions_value, list) else []
    expected_plan = "action_plan" in expectation.decision_types
    plan_legal = bool(
        accepted and decision_type == "action_plan" and isinstance(result.get("task_plan"), dict)
    )
    if expected_plan and not plan_legal:
        failures.append("candidate_task_plan_not_compiled")

    relevant_actions = [
        action
        for action in actions
        if isinstance(action, dict)
        and (
            expectation.action_type is None or action.get("action_type") == expectation.action_type
        )
    ]
    if expectation.action_type is not None and not relevant_actions:
        failures.append(f"missing_action:{expectation.action_type}")
    if expectation.chart_type_id is not None and not any(
        action.get("chart_type_id") == expectation.chart_type_id for action in relevant_actions
    ):
        failures.append(f"chart_type:{expectation.chart_type_id}")

    field_mapping_applicable = bool(expectation.field_mapping)
    field_mapping_correct = not field_mapping_applicable
    if field_mapping_applicable:
        actual_mapping: dict[str, str] = {}
        if relevant_actions:
            selections = relevant_actions[0].get("field_selections", [])
            if isinstance(selections, list):
                actual_mapping = {
                    str(item.get("role")): str(item.get("context_field_alias"))
                    for item in selections
                    if isinstance(item, dict)
                }
        field_mapping_correct = actual_mapping == expectation.field_mapping
        if not field_mapping_correct:
            failures.append(f"field_mapping:{actual_mapping!r}")

    patches = [
        patch
        for action in relevant_actions
        for patch in (action.get("patches", []) if isinstance(action.get("patches"), list) else [])
        if isinstance(patch, dict)
    ]
    actual_operations = tuple(str(patch.get("operation")) for patch in patches)
    if expectation.operations:
        expected_operations = tuple(expectation.operations)
        if expectation.no_extra_patches:
            operation_ok = sorted(actual_operations) == sorted(expected_operations)
        else:
            operation_ok = set(expected_operations).issubset(actual_operations)
        if not operation_ok:
            failures.append(f"operations:{actual_operations!r}")

    action_targets = tuple(
        str(action.get("target_alias")) for action in relevant_actions if "target_alias" in action
    )
    patch_targets = tuple(
        str(patch.get("target_alias")) for patch in patches if "target_alias" in patch
    )
    target_binding_applicable = bool(
        expectation.action_target_aliases or expectation.patch_target_aliases
    )
    target_binding_correct = not target_binding_applicable
    if target_binding_applicable:
        action_ok = not expectation.action_target_aliases or sorted(action_targets) == sorted(
            expectation.action_target_aliases
        )
        patch_ok = not expectation.patch_target_aliases or sorted(patch_targets) == sorted(
            expectation.patch_target_aliases
        )
        target_binding_correct = action_ok and patch_ok
        if not target_binding_correct:
            failures.append(f"target_binding:actions={action_targets!r},patches={patch_targets!r}")

    if expectation.exact_title is not None and not any(
        patch.get("operation") == "set_plot_title" and patch.get("title") == expectation.exact_title
        for patch in patches
    ):
        failures.append("exact_title_mismatch")
    if expectation.exact_axis_label is not None and not any(
        patch.get("operation") == "set_axis_label"
        and patch.get("label") == expectation.exact_axis_label
        for patch in patches
    ):
        failures.append("axis_label_mismatch")
    if expectation.exact_axis_scale is not None and not any(
        patch.get("operation") == "set_axis_scale"
        and patch.get("scale") == expectation.exact_axis_scale
        for patch in patches
    ):
        failures.append("axis_scale_mismatch")
    if expectation.exact_legend_placement is not None and not any(
        patch.get("operation") == "move_legend"
        and patch.get("placement") == expectation.exact_legend_placement
        for patch in patches
    ):
        failures.append("legend_placement_mismatch")
    if expectation.exact_reference_y is not None and not any(
        patch.get("operation") == "add_annotation"
        and patch.get("kind") == "reference_line"
        and patch.get("y") == expectation.exact_reference_y
        for patch in patches
    ):
        failures.append("reference_line_mismatch")

    questions_value = decision.get("questions") if decision_type == "needs_input" else []
    questions = questions_value if isinstance(questions_value, list) else []
    necessary_question_applicable = expectation.decision_types == ("needs_input",)
    necessary_question_correct = not necessary_question_applicable
    if necessary_question_applicable:
        necessary_question_correct = decision_type == "needs_input" and 0 < len(questions) <= max(
            1, expectation.max_questions
        )
        if not necessary_question_correct:
            failures.append("necessary_question_missing_or_unbounded")
    invalid_question = decision_type == "needs_input" and not necessary_question_applicable
    if invalid_question:
        failures.append("invalid_question")
    incorrect_auto_binding = decision_type == "action_plan" and expectation.forbidden_action_plan

    return DecisionScore(
        passed=not failures,
        schema_accepted=accepted,
        expected_plan=expected_plan,
        plan_legal=plan_legal,
        target_binding_applicable=target_binding_applicable,
        target_binding_correct=target_binding_correct,
        field_mapping_applicable=field_mapping_applicable,
        field_mapping_correct=field_mapping_correct,
        necessary_question_applicable=necessary_question_applicable,
        necessary_question_correct=necessary_question_correct,
        invalid_question=invalid_question,
        incorrect_auto_binding=incorrect_auto_binding,
        failures=tuple(failures),
    )
