from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from plotagent.contracts.workflows import (
    ConcatenateSources,
    DraftFieldBinding,
    DraftSetAxis,
    DraftSetTitle,
    TaskDraft,
    TaskDraftItem,
    WorkflowBudget,
    WorkflowContext,
    WorkflowField,
    WorkflowSource,
)
from plotagent.engine import EngineCatalog
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.workflows import DataInspectionService, DraftCompiler, WorkflowRouter
from plotagent.workflows.inspection import InspectionError

_HASH = "a" * 64


def _context(
    instruction: str = "用这个数据画折线图",
    *,
    selected_sources: tuple[str, ...] = ("data_1",),
    max_preview_rows: int = 40,
) -> WorkflowContext:
    sources = (
        WorkflowSource(
            source_alias="data_1",
            source_dataset_id="source:one",
            source_version=1,
            content_hash=_HASH,
            display_name="input.xlsx > Sheet1",
            row_count=3,
        ),
        WorkflowSource(
            source_alias="data_2",
            source_dataset_id="source:two",
            source_version=1,
            content_hash="b" * 64,
            display_name="input.xlsx > Sheet2",
            row_count=3,
        ),
    )
    fields = tuple(
        WorkflowField(
            field_alias=alias,
            source_alias=source_alias,
            field_id=f"field:{alias}",
            name=name,
            logical_type="numeric",
        )
        for source_alias, alias, name in (
            ("data_1", "data_1_time", "Time"),
            ("data_1", "data_1_response", "Response"),
            ("data_2", "data_2_time", "Time"),
            ("data_2", "data_2_response", "Response"),
        )
    )
    return WorkflowContext(
        workflow_run_id="workflow:test",
        project_id="project:test",
        project_revision=4,
        instruction=instruction,
        sources=sources,
        fields=fields,
        selected_source_aliases=selected_sources,
        selected_profile_ids=(),
        allowed_profile_ids=tuple(profile.profile_id for profile in ENGINE_PROFILES),
        budget=WorkflowBudget(max_preview_rows=max_preview_rows),
    )


def test_deterministic_route_builds_confirmable_draft_without_a_model() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(_context())

    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    assert decision.deterministic.outcome == "draft_ready"
    draft = decision.deterministic.draft
    assert draft.route == "deterministic"
    assert draft.items[0].profile_id == "K01"
    assert [(item.role, item.field_alias) for item in draft.items[0].bindings] == [
        ("x", "data_1_time"),
        ("y", "data_1_response"),
    ]


def test_unspecified_chart_is_a_local_question_not_an_agent_guess() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(_context("用这个数据画一张图"))

    assert decision.route == "needs_input"
    assert decision.deterministic is not None
    assert decision.deterministic.outcome == "needs_input"
    assert decision.deterministic.questions[0].question_key == "chart_type"


def test_multi_source_batch_goal_routes_to_bounded_exploration() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(
        _context(
            "数据A画折线图，数据B画散点图",
            selected_sources=("data_1", "data_2"),
        )
    )
    assert decision.route == "agent_exploration"


def test_compiler_resolves_aliases_and_rejects_unknown_targets() -> None:
    context = _context()
    draft = TaskDraft(
        draft_id="draft:test",
        workflow_run_id=context.workflow_run_id,
        route="agent_single_turn",
        summary="创建一张折线图",
        confidence=0.9,
        items=(
            TaskDraftItem(
                task_kind="create",
                item_id="item:test.1",
                plot_alias="plot_1",
                profile_id="K01",
                source_aliases=("data_1",),
                bindings=(
                    DraftFieldBinding(role="x", source_alias="data_1", field_alias="data_1_time"),
                    DraftFieldBinding(
                        role="y", source_alias="data_1", field_alias="data_1_response"
                    ),
                ),
                visual_actions=(
                    DraftSetTitle(text="响应曲线"),
                    DraftSetAxis(target_alias="y_axis", scale="log10"),
                ),
            ),
        ),
    )
    plan = DraftCompiler(EngineCatalog(ENGINE_PROFILES)).compile(draft, context)
    assert plan.expected_project_revision == 4
    assert plan.items[0].plot_id == "plot:workflow.test.1"
    assert [binding.field_id for binding in plan.items[0].bindings] == [
        "field:data_1_time",
        "field:data_1_response",
    ]

    invalid = draft.model_copy(
        update={
            "items": (
                draft.items[0].model_copy(
                    update={
                        "visual_actions": (DraftSetAxis(target_alias="imaginary_axis", label="No"),)
                    }
                ),
            )
        }
    )
    validation = DraftCompiler(EngineCatalog(ENGINE_PROFILES)).validate(invalid, context)
    assert not validation.valid
    assert validation.error_code == "TARGET_ALIAS_INVALID"


def test_task_draft_rejects_binding_outside_declared_sources() -> None:
    with pytest.raises(ValidationError):
        TaskDraftItem(
            task_kind="create",
            item_id="item:test.1",
            plot_alias="plot_1",
            profile_id="K01",
            source_aliases=("data_1",),
            bindings=(
                DraftFieldBinding(role="x", source_alias="data_2", field_alias="data_2_time"),
            ),
        )


def test_concat_operation_preserves_explicit_source_order() -> None:
    operation = ConcatenateSources(source_aliases=("data_2", "data_1"))
    assert operation.source_aliases == ("data_2", "data_1")


@dataclass(frozen=True)
class _Rows:
    values: dict[str, tuple[tuple[object, ...], ...]]

    def rows(self, source_alias: str):  # type: ignore[no-untyped-def]
        return self.values[source_alias]


def test_inspection_is_read_only_bounded_and_audited() -> None:
    service = DataInspectionService(
        _context(max_preview_rows=2),
        _Rows(
            {
                "data_1": ((1.0, 2.0), (2.0, 3.0), (3.0, 5.0)),
                "data_2": ((1.0, 4.0), (2.0, 6.0), (3.0, 8.0)),
            }
        ),
    )
    page = service.preview_rows("data_1", ("data_1_time", "data_1_response"), limit=2)
    assert page.rows == ((1.0, 2.0), (2.0, 3.0))
    assert page.has_more
    assert service.audits[-1].disclosed_scalar_count == 4

    with pytest.raises(InspectionError) as captured:
        service.preview_rows("data_1", ("data_1_time",), offset=2, limit=1)
    assert captured.value.code == "INSPECTION_BUDGET_EXCEEDED"
