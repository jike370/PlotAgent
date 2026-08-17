from __future__ import annotations

from plotagent.contracts.workflows import (
    WorkflowBudget,
    WorkflowContext,
    WorkflowField,
    WorkflowPlot,
    WorkflowSource,
)
from plotagent.engine import EngineCatalog
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.workflows import DraftCompiler, WorkflowRouter

_HASH = "a" * 64
_CATALOG = EngineCatalog(ENGINE_PROFILES)


def _context(
    profile_id: str,
    instruction: str,
    fields: tuple[tuple[str, str], ...],
    *,
    edit: bool = False,
) -> WorkflowContext:
    source = WorkflowSource(
        source_alias="data_1",
        source_dataset_id="source:test",
        source_version=1,
        content_hash=_HASH,
        display_name="fixture.csv",
        row_count=8,
    )
    workflow_fields = tuple(
        WorkflowField(
            field_alias=f"field_{position}",
            source_alias="data_1",
            field_id=f"field:{position:024x}",
            name=name,
            logical_type=logical_type,  # type: ignore[arg-type]
        )
        for position, (name, logical_type) in enumerate(fields, start=1)
    )
    plots = (
        WorkflowPlot(
            plot_alias="current_plot",
            plot_id="plot:test",
            plot_version=1,
            profile_id=profile_id,
        ),
    ) if edit else ()
    return WorkflowContext(
        workflow_run_id="workflow:natural-language",
        project_id="project:test",
        project_revision=2,
        instruction=instruction,
        sources=(source,),
        fields=workflow_fields,
        plots=plots,
        selected_source_aliases=("data_1",),
        selected_plot_aliases=("current_plot",) if edit else (),
        selected_profile_ids=() if edit else (profile_id,),
        allowed_profile_ids=tuple(profile.profile_id for profile in ENGINE_PROFILES),
        budget=WorkflowBudget(),
    )


def _draft(context: WorkflowContext):  # type: ignore[no-untyped-def]
    decision = WorkflowRouter(_CATALOG).route(context)
    assert decision.route == "deterministic"
    assert decision.deterministic is not None
    assert decision.deterministic.outcome == "draft_ready"
    return decision.deterministic.draft


def test_program_first_parses_line_title_and_marker_goals() -> None:
    line = _draft(
        _context(
            "K01",
            "创建 K01 折线图，X 映射 X，Y 映射 Response；标题设为温度响应，"
            "线条改为 #D62728 红色虚线，宽度 2 pt。",
            (("X", "numeric"), ("Response", "numeric")),
        )
    )
    assert [action.model_dump(exclude_none=True) for action in line.items[0].visual_actions] == [
        {"operation": "set_title", "target_alias": "plot", "text": "温度响应"},
        {
            "operation": "set_series_style",
            "target_alias": "series_1",
            "line_stroke_color": "#D62728",
            "line_width_pt": 2.0,
            "line_style": "dash",
        },
    ]

    scatter = _draft(
        _context(
            "K03",
            "创建 K03 散点图，X 映射 X，Y 映射 Response；点使用蓝色实心圆，"
            "大小 8 pt，边缘宽度 1 pt。",
            (("X", "numeric"), ("Response", "numeric")),
        )
    )
    style = scatter.items[0].visual_actions[0]
    assert style.marker_shape == "circle"
    assert style.marker_size_pt == 8
    assert style.marker_interior == "solid"
    assert style.marker_stroke_width_pt == 1
    assert style.marker_fill_color == "#1F77B4"


def test_program_first_parses_column_heatmap_and_error_styles() -> None:
    column = _draft(
        _context(
            "K08",
            "创建 K08 柱状图，Category 映射 category，Value 映射 value；"
            "柱填充 #4C78A8，边框 #1F4E79，边框宽 1.5 pt，并显示数据标签。",
            (("Category", "categorical"), ("Value", "numeric")),
        )
    )
    style, labels = column.items[0].visual_actions
    assert style.fill_color == "#4C78A8"
    assert style.fill_stroke_color == "#1F4E79"
    assert style.fill_stroke_width_pt == 1.5
    assert labels.operation == "set_data_labels" and labels.visible

    heatmap = _draft(
        _context(
            "K20",
            "创建 K20 热图，Row 映射 row，Column 映射 column，Value 映射 value；"
            "使用 RdBu 色板并反转，范围 -3 到 9，中点 0，色标标题设为表达量。",
            (("Row", "categorical"), ("Column", "categorical"), ("Value", "numeric")),
        )
    )
    color = heatmap.items[0].visual_actions[0]
    assert color.palette == "red_white_blue"
    assert color.reverse and (color.minimum, color.maximum, color.midpoint) == (-3, 9, 0)
    assert color.colorbar_title == "表达量"
    assert DraftCompiler(_CATALOG).validate(
        heatmap,
        _context(
            "K20",
            "创建 K20 热图，Row 映射 row，Column 映射 column，Value 映射 value；"
            "使用 RdBu 色板并反转，范围 -3 到 9，中点 0，色标标题设为表达量。",
            (("Row", "categorical"), ("Column", "categorical"), ("Value", "numeric")),
        ),
    ).valid

    error = _draft(
        _context(
            "K06",
            "创建 K06 双向误差棒图：X→x，Mean→center，XLower→x_lower，"
            "XUpper→x_upper，Lower→lower，Upper→upper。"
            "误差棒颜色 #B63848、宽 1.5 pt、端帽 6 pt。",
            (
                ("X", "numeric"),
                ("Mean", "numeric"),
                ("XLower", "numeric"),
                ("XUpper", "numeric"),
                ("Lower", "numeric"),
                ("Upper", "numeric"),
            ),
        )
    )
    error_style = error.items[0].visual_actions[0]
    assert (error_style.bar_color, error_style.bar_width_pt, error_style.cap_size_pt) == (
        "#B63848",
        1.5,
        6,
    )
    assert error_style.target_alias == "series_1"


def test_program_first_parses_existing_plot_edits_and_connector_style() -> None:
    edited = _draft(
        _context(
            "K01",
            "把当前图标题改为实验结果，并把 y 轴标题改为响应值，其他保持不变。",
            (("X", "numeric"), ("Response", "numeric")),
            edit=True,
        )
    )
    assert edited.items[0].task_kind == "edit"
    assert edited.items[0].target_plot_alias == "current_plot"
    assert [action.operation for action in edited.items[0].visual_actions] == [
        "set_title",
        "set_axis",
    ]

    before_after = _draft(
        _context(
            "X40",
            "创建 X40 前后对比图：Subject→label，Before→series_1，After→series_2，"
            "Group→group；连接线用 #7A7A7A、宽 1.5 pt，标题为干预前后。",
            (
                ("Subject", "categorical"),
                ("Before", "numeric"),
                ("After", "numeric"),
                ("Group", "categorical"),
            ),
        )
    )
    title, connector = before_after.items[0].visual_actions
    assert title.text == "干预前后"
    assert connector.target_alias == "connector"
    assert connector.line_stroke_color == "#7A7A7A"
    assert connector.line_width_pt == 1.5


def test_program_first_preserves_log_marker_and_exact_legend_corner() -> None:
    edited = _draft(
        _context(
            "K03",
            "把当前图标题改为复测结果，y 轴改为 log10，点改为红色实心方形，"
            "图例放在左下角。",
            (("X", "numeric"), ("Response", "numeric")),
            edit=True,
        )
    )

    assert [action.model_dump(exclude_none=True) for action in edited.items[0].visual_actions] == [
        {"operation": "set_title", "target_alias": "plot", "text": "复测结果"},
        {"operation": "set_axis", "target_alias": "y_axis", "scale": "log10"},
        {
            "operation": "set_series_style",
            "target_alias": "series_1",
            "marker_shape": "square",
            "marker_interior": "solid",
            "marker_fill_color": "#D62728",
            "marker_stroke_color": "#D62728",
        },
        {
            "operation": "set_legend",
            "target_alias": "legend",
            "visible": True,
            "anchor": "inside_bottom_left",
        },
    ]


def test_datetime_alias_selects_k19_and_ambiguous_time_fields_require_input() -> None:
    explicit = _draft(
        _context(
            "K19",
            "创建日期时间折线图，Time 映射 time，Response 映射 series_1。",
            (("Time", "datetime"), ("Response", "numeric")),
        )
    )
    assert explicit.items[0].profile_id == "K19"

    ambiguous = WorkflowRouter(_CATALOG).route(
        _context(
            "K19",
            "创建日期时间折线图。",
            (
                ("Time", "datetime"),
                ("Time Local", "datetime"),
                ("Response", "numeric"),
            ),
        )
    )
    assert ambiguous.route == "needs_input"
    assert ambiguous.deterministic is not None
    assert ambiguous.deterministic.outcome == "needs_input"
    assert ambiguous.deterministic.questions[0].question_key == "field_time"


def test_explicit_unsupported_role_fails_closed_instead_of_being_dropped() -> None:
    decision = WorkflowRouter(_CATALOG).route(
        _context(
            "K04",
            "创建 K04 气泡图：X→x，Y→y，BubbleSize→size，ColorValue→color，Group→group。",
            (
                ("X", "numeric"),
                ("Y", "numeric"),
                ("BubbleSize", "numeric"),
                ("ColorValue", "numeric"),
                ("Group", "categorical"),
            ),
        )
    )
    assert decision.route == "unsupported"
    assert decision.deterministic is not None
    assert decision.deterministic.outcome == "unsupported"
    assert decision.deterministic.reason_code == "ROLE_UNAVAILABLE"


def test_binding_word_is_treated_as_an_explicit_field_role_operator() -> None:
    draft = _draft(
        _context(
            "K03",
            "在当前数据表绘制 K03 散点图，X 绑定 X，Y 绑定 Y，分组绑定 分组。",
            (("X", "numeric"), ("Y", "numeric"), ("分组", "categorical")),
        )
    )

    assert [(binding.role, binding.field_alias) for binding in draft.items[0].bindings] == [
        ("x", "field_1"),
        ("y", "field_2"),
        ("group", "field_3"),
    ]


def test_mapping_to_role_preserves_an_explicit_underscored_field_name() -> None:
    draft = _draft(
        _context(
            "K01",
            "创建 K01 折线图，将 Frequency_Hz 映射为 x，将 Zimag_Ohm 映射为 y。",
            (
                ("Frequency_Hz", "numeric"),
                ("Zreal_Ohm", "numeric"),
                ("Zimag_Ohm", "numeric"),
            ),
        )
    )

    assert [(binding.role, binding.field_alias) for binding in draft.items[0].bindings] == [
        ("x", "field_1"),
        ("y", "field_3"),
    ]


def test_localized_role_binding_resolves_an_unambiguous_source_field() -> None:
    draft = _draft(
        _context(
            "K03",
            "在当前数据表绘制 K03 散点图，X 绑定 X，Y 绑定 Y，分组绑定 分组。",
            (("X", "numeric"), ("Y", "numeric"), ("Group", "text")),
        )
    )

    assert [(binding.role, binding.field_alias) for binding in draft.items[0].bindings] == [
        ("x", "field_1"),
        ("y", "field_2"),
        ("group", "field_3"),
    ]


def test_visual_labels_remove_natural_language_quotation_marks() -> None:
    draft = _draft(
        _context(
            "K03",
            "创建 K03 散点图，X 映射 X，Y 映射 Y，标题改为“验证散点图”，"
            "横轴标题改为‘时间’。",
            (("X", "numeric"), ("Y", "numeric")),
        )
    )

    title, axis = draft.items[0].visual_actions
    assert title.text == "验证散点图"
    assert axis.label == "时间"


def test_unhandled_explicit_goal_escalates_instead_of_dropping_parameters() -> None:
    context = _context(
        "K01",
        "创建 K01 折线图，X 映射 X，Y 映射 Response；字体改成 Comic Sans。",
        (("X", "numeric"), ("Response", "numeric")),
    )
    decision = WorkflowRouter(_CATALOG).route(context)
    assert decision.route == "agent_single_turn"
    assert decision.deterministic is None


def test_vague_visual_request_asks_for_the_visual_element_locally() -> None:
    decision = WorkflowRouter(_CATALOG).route(
        _context(
            "K01",
            "美化一下",
            (("X", "numeric"), ("Response", "numeric")),
            edit=True,
        )
    )

    assert decision.route == "needs_input"
    assert decision.deterministic is not None
    assert decision.deterministic.outcome == "needs_input"
    assert decision.deterministic.questions[0].question_key == "visual_change"
