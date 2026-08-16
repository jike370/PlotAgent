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
from plotagent.workflows.router import named_source_aliases

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


def test_explicit_visual_goal_uses_the_program_first_route_without_dropping_style() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(
        _context("用这个数据画 K01 折线图，线条改成 #D62728 红色虚线，宽度 2 pt")
    )

    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    draft = decision.deterministic.draft
    style = draft.items[0].visual_actions[0]
    assert style.operation == "set_series_style"
    assert style.line_stroke_color == "#D62728"
    assert style.line_style == "dash"
    assert style.line_width_pt == 2


def test_explicit_filter_and_sort_use_field_aliases_on_the_program_first_route() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(
        _context(
            "用这个数据画 K01 折线图，只保留 Response 大于 2 的行，按 Time 降序排列"
        )
    )

    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    operations = decision.deterministic.draft.items[0].data_operations
    assert [operation.operation for operation in operations] == ["filter_rows", "sort_rows"]
    assert operations[0].predicates[0].field_alias == "data_1_response"
    assert operations[1].keys[0].field_alias == "data_1_time"


def test_multi_source_batch_goal_builds_independent_items_without_a_model() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(
        _context(
            "数据A画折线图，数据B画散点图",
            selected_sources=("data_1", "data_2"),
        )
    )
    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    assert decision.deterministic.outcome == "draft_ready"
    assert [
        (item.source_aliases, item.profile_id)
        for item in decision.deterministic.draft.items
    ] == [(('data_1',), 'K01'), (('data_2',), 'K03')]


def test_isomorphic_concat_uses_the_program_first_route_and_preserves_source_identity() -> None:
    context = _context(
        "把 data_1 和 data_2 纵向拼接，在同一张 K03 散点图中绘制；Time 为 x，Response 为 y。",
        selected_sources=("data_1", "data_2"),
    )
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(context)

    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    draft = decision.deterministic.draft
    item = draft.items[0]
    assert item.source_aliases == ("data_1", "data_2")
    assert item.data_operations[0].operation == "concatenate_sources"
    assert item.data_operations[0].source_labels == ()
    assert item.bindings[-1].role == "group"
    assert item.bindings[-1].field_alias == "source_group"
    assert DraftCompiler(EngineCatalog(ENGINE_PROFILES)).validate(draft, context).valid


def test_k01_multi_source_goal_uses_source_identity_as_the_group() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(
        _context(
            "把 data_1 和 data_2 一起画在同一张 K01 折线图中。",
            selected_sources=("data_1", "data_2"),
        )
    )

    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    item = decision.deterministic.draft.items[0]
    assert item.source_aliases == ("data_1", "data_2")
    assert item.data_operations[0].operation == "concatenate_sources"
    assert item.bindings[-1].role == "group"
    assert item.bindings[-1].field_alias == "source_group"


def test_same_chart_wording_uses_program_first_concat_without_extra_join_keyword() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(
        _context(
            "将已提供的 2 个数据表画在同一张 K01 折线图中；各表 Time 绑定 x，Response 绑定 y。",
            selected_sources=("data_1", "data_2"),
        )
    )

    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    item = decision.deterministic.draft.items[0]
    assert item.source_aliases == ("data_1", "data_2")
    assert item.data_operations[0].operation == "concatenate_sources"
    assert item.bindings[-1].role == "group"


def test_explicit_file_names_limit_same_chart_sources_before_schema_comparison() -> None:
    base = _context(
        "将 series_A.xlsx、series_B.xlsx、series_C.xlsx 三个数据表画在同一张 K19 时间序列图中；"
        "各表 Time 绑定 time，Signal 绑定 series_1；保留 A、B、C 数据来源身份作为系列名称。",
        selected_sources=("data_1", "data_2"),
    )
    sources = tuple(
        WorkflowSource(
            source_alias=f"data_{position}",
            source_dataset_id=f"source:{position}",
            source_version=1,
            content_hash=f"{position}" * 64,
            display_name=(
                f"series_{letter}.xlsx > Data"
                if position < 4
                else "unrelated.xlsx > K19"
            ),
            row_count=3,
        )
        for position, letter in enumerate(("A", "B", "C", "D"), start=1)
    )
    fields = tuple(
        WorkflowField(
            field_alias=f"data_{position}_{name.casefold()}",
            source_alias=f"data_{position}",
            field_id=f"field:{position}.{name.casefold()}",
            name=name,
            logical_type=logical_type,
        )
        for position in range(1, 5)
        for name, logical_type in (
            (("Time", "datetime"), ("Signal", "numeric"))
            if position < 4
            else (("Timestamp", "datetime"), ("Value", "numeric"))
        )
    )
    context = base.model_copy(
        update={
            "sources": sources,
            "fields": fields,
            "selected_source_aliases": ("data_1", "data_2", "data_3", "data_4"),
            "selected_profile_ids": ("K19",),
        }
    )
    assert named_source_aliases(context) == ("data_1", "data_2", "data_3")

    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(context)

    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    item = decision.deterministic.draft.items[0]
    assert item.source_aliases == ("data_1", "data_2", "data_3")
    assert item.data_operations[0].operation == "concatenate_sources"
    assert item.data_operations[0].source_labels == ("A", "B", "C")


def test_multi_source_profile_without_group_support_fails_closed() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(
        _context(
            "把 data_1 和 data_2 一起画在同一张 K04 气泡图中。",
            selected_sources=("data_1", "data_2"),
        )
    )

    assert decision.route == "unsupported"
    assert decision.deterministic is not None
    assert decision.deterministic.outcome == "unsupported"
    assert decision.deterministic.reason_code == "MULTI_SOURCE_PROFILE_UNSUPPORTED"


def test_full_worksheet_name_wins_over_a_shared_file_name() -> None:
    assert named_source_aliases(
        _context(
            "使用 input.xlsx > Sheet2 创建 K01 折线图。",
            selected_sources=("data_1", "data_2"),
        )
    ) == ("data_2",)
    assert named_source_aliases(
        _context(
            "使用 input.xlsx 创建 K01 折线图。",
            selected_sources=("data_1", "data_2"),
        )
    ) == ()


def test_isomorphic_batch_with_explicit_titles_uses_the_program_first_route() -> None:
    decision = WorkflowRouter(EngineCatalog(ENGINE_PROFILES)).route(
        _context(
            "先比较 data_1 与 data_2 的结构；如果同构，就分别创建 K01 折线图，"
            "标题分别为数据一和数据二。",
            selected_sources=("data_1", "data_2"),
        )
    )

    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    draft = decision.deterministic.draft
    assert [item.visual_actions[0].text for item in draft.items] == ["数据一", "数据二"]


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
    operation = ConcatenateSources(
        source_aliases=("data_2", "data_1"),
        source_labels=("Second", "First"),
    )
    assert operation.source_aliases == ("data_2", "data_1")
    assert operation.source_labels == ("Second", "First")


def test_compiler_accepts_the_concatenate_source_identity_field() -> None:
    context = _context(selected_sources=("data_1", "data_2"))
    draft = TaskDraft(
        draft_id="draft:concat",
        workflow_run_id=context.workflow_run_id,
        route="agent_exploration",
        summary="拼接同构数据",
        confidence=1,
        items=(
            TaskDraftItem(
                task_kind="create",
                item_id="item:concat.1",
                plot_alias="plot_1",
                profile_id="K02",
                source_aliases=("data_1", "data_2"),
                data_operations=(
                    ConcatenateSources(
                        source_aliases=("data_1", "data_2"),
                        source_label_field="source_group",
                        source_labels=("Sheet1", "Sheet2"),
                    ),
                ),
                bindings=(
                    DraftFieldBinding(
                        role="x",
                        source_alias="data_1",
                        field_alias="data_1_time",
                    ),
                    DraftFieldBinding(
                        role="y",
                        source_alias="data_1",
                        field_alias="data_1_response",
                    ),
                    DraftFieldBinding(
                        role="group",
                        source_alias="data_1",
                        field_alias="source_group",
                    ),
                ),
            ),
        ),
    )

    plan = DraftCompiler(EngineCatalog(ENGINE_PROFILES)).compile(draft, context)
    assert plan.items[0].data_operations[0].operation == "concatenate_sources"
    assert plan.items[0].bindings[-1].field_id.startswith("field:workflow_")


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
