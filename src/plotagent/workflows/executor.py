"""Persistent, item-scoped execution of confirmed workflow task plans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from plotagent.contracts.errors import ERRORS_BY_CODE
from plotagent.contracts.workflows import (
    CompiledTaskItem,
    DraftAddAnnotation,
    DraftSetAxis,
    DraftSetChartParameter,
    DraftSetColorMap,
    DraftSetDataLabels,
    DraftSetErrorStyle,
    DraftSetLegend,
    DraftSetSeriesStyle,
    DraftSetTitle,
    TaskPlanSnapshot,
)
from plotagent.engine import (
    AddAnnotation,
    BindFields,
    CreatePlot,
    EngineCatalog,
    EngineDataRef,
    FieldBinding,
    PlotEngineAction,
    SetAxis,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)

from .repository import WorkflowRepository


class WorkflowExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


type PrepareTaskData = Callable[[CompiledTaskItem], tuple[EngineDataRef, tuple[FieldBinding, ...]]]
type ExecuteEngineAction = Callable[[PlotEngineAction, int], int]
type ValidatePreparedData = Callable[
    [CompiledTaskItem, EngineDataRef, tuple[FieldBinding, ...]],
    None,
]
type ValidateEditData = Callable[[CompiledTaskItem], None]
type ResolveSeriesTargets = Callable[[CompiledTaskItem], tuple[str, ...]]


@dataclass(slots=True)
class TaskPlanExecutor:
    repository: WorkflowRepository | None
    catalog: EngineCatalog
    prepare_data: PrepareTaskData
    execute_action: ExecuteEngineAction
    validate_prepared_data: ValidatePreparedData
    validate_edit_data: ValidateEditData
    resolve_series_targets: ResolveSeriesTargets | None = None

    def run(self, plan_id: str) -> TaskPlanSnapshot:
        if self.repository is None:
            raise WorkflowExecutionError(
                "WORKFLOW_REPOSITORY_REQUIRED",
                "Legacy workflow-plan execution requires its repository.",
            )
        repository = self.repository
        snapshot = repository.get_plan(plan_id)
        if snapshot.state not in {"ready", "running", "partially_succeeded", "failed"}:
            raise WorkflowExecutionError(
                "WORKFLOW_PLAN_NOT_RUNNABLE",
                "任务计划尚未确认或已经结束。",
            )
        if snapshot.state == "ready" and (
            snapshot.current_project_revision != snapshot.plan.expected_project_revision
        ):
            raise WorkflowExecutionError(
                "PROJECT_VERSION_CONFLICT",
                "项目在确认后发生了变化，请重新生成任务计划。",
            )
        snapshot = repository.set_plan_state(plan_id, "running")
        repository.transition_run(snapshot.plan.workflow_run_id, state="executing")
        failed_ids = {
            progress.item_id
            for progress in snapshot.item_progress
            if progress.state in {"failed", "blocked"}
        }
        for item, progress in zip(snapshot.plan.items, snapshot.item_progress, strict=True):
            if progress.state == "succeeded":
                continue
            if set(item.depends_on) & failed_ids:
                snapshot = repository.set_item_state(
                    plan_id,
                    item.item_id,
                    "blocked",
                    error_code="UPSTREAM_TASK_ITEM_FAILED",
                    error_message="前置任务未完成，因此本任务尚未执行。",
                    error_retryable=True,
                )
                failed_ids.add(item.item_id)
                continue
            snapshot = repository.set_item_state(
                plan_id,
                item.item_id,
                "running",
                increment_attempt=True,
            )
            try:
                revision, plot_version = self._execute_item(item, snapshot.current_project_revision)
                snapshot = repository.set_item_state(
                    plan_id,
                    item.item_id,
                    "succeeded",
                    output_plot_id=item.plot_id,
                    output_plot_version=plot_version,
                )
                snapshot = repository.set_plan_state(
                    plan_id, "running", project_revision=revision
                )
                failed_ids.discard(item.item_id)
            except Exception as error:
                code = getattr(error, "code", type(error).__name__)
                code_text = str(code)
                snapshot = repository.set_item_state(
                    plan_id,
                    item.item_id,
                    "failed",
                    error_code=code_text,
                    error_message=self._failure_message(error),
                    error_retryable=self._failure_retryable(error, code_text),
                )
                failed_ids.add(item.item_id)
        snapshot = repository.get_plan(plan_id)
        failures = tuple(
            progress
            for progress in snapshot.item_progress
            if progress.state in {"failed", "blocked"}
        )
        successes = tuple(
            progress for progress in snapshot.item_progress if progress.state == "succeeded"
        )
        state = "succeeded" if not failures else "partially_succeeded" if successes else "failed"
        snapshot = repository.set_plan_state(
            plan_id,
            state,
            project_revision=snapshot.current_project_revision,
        )
        repository.transition_run(
            snapshot.plan.workflow_run_id,
            state=(
                "completed"
                if state == "succeeded"
                else "partially_succeeded"
                if state == "partially_succeeded"
                else "failed"
            ),
        )
        return snapshot

    def execute_compiled_item(
        self, item: CompiledTaskItem, revision: int
    ) -> tuple[int, int]:
        """Execute one already compiled item without reading legacy plan state."""

        return self._execute_item(item, revision)

    @staticmethod
    def _failure_message(error: Exception) -> str:
        explicit = getattr(error, "message", None)
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()[:512]
        if isinstance(error, (ValueError, RuntimeError)):
            rendered = str(error).strip()
            if rendered:
                return rendered[:512]
        return "任务未完成；项目没有发生未确认的变化。"

    @staticmethod
    def _failure_retryable(error: Exception, code: str) -> bool:
        response = getattr(error, "error", None)
        response_retryable = getattr(response, "retryable", None)
        if isinstance(response_retryable, bool):
            return response_retryable
        direct = getattr(error, "retryable", None)
        if isinstance(direct, bool):
            return direct
        definition = ERRORS_BY_CODE.get(code)
        return False if definition is None else definition.retryable

    def _execute_item(self, item: CompiledTaskItem, revision: int) -> tuple[int, int]:
        current_revision = revision
        if item.task_kind == "create":
            data, bindings = self.prepare_data(item)
            self.validate_prepared_data(item, data, bindings)
            create = CreatePlot(
                action_id=f"action:{item.item_id.removeprefix('item:')}.create",
                plot_id=item.plot_id,
                profile_id=item.profile_id,
                data=data,
                bindings=bindings,
            )
            self.catalog.validate_create(create)
            current_revision = self.execute_action(create, revision)
            plot_version = 1
        elif item.task_kind == "edit":
            if item.target_plot_id is None or item.target_plot_version is None:
                raise WorkflowExecutionError(
                    "WORKFLOW_EDIT_TARGET_INVALID", "待编辑图形目标不完整。"
                )
            plot_version = item.target_plot_version
            self.validate_edit_data(item)
        else:
            if item.target_plot_id is None or item.target_plot_version is None:
                raise WorkflowExecutionError(
                    "WORKFLOW_EDIT_TARGET_INVALID", "待更新图形目标不完整。"
                )
            data, bindings = self.prepare_data(item)
            self.validate_prepared_data(item, data, bindings)
            rebind = BindFields(
                action_id=f"action:{item.item_id.removeprefix('item:')}.bind",
                target=item.target_plot_id,
                expected_plot_version=item.target_plot_version,
                data=data,
                bindings=bindings,
            )
            self.catalog.validate_action(self.catalog.get(item.profile_id), rebind)
            current_revision = self.execute_action(rebind, revision)
            plot_version = item.target_plot_version + 1
        for position, draft in enumerate(item.visual_actions, start=1):
            action_id = f"action:{item.item_id.removeprefix('item:')}.edit{position}"
            action: PlotEngineAction
            if isinstance(draft, DraftSetSeriesStyle) and draft.scope == "all_series":
                if self.resolve_series_targets is None:
                    raise WorkflowExecutionError(
                        "SERIES_SCOPE_UNAVAILABLE",
                        "当前执行环境无法解析图形中的全部系列。",
                    )
                targets = self.resolve_series_targets(item)
                if not targets:
                    raise WorkflowExecutionError(
                        "SERIES_SCOPE_EMPTY",
                        "当前图形没有可编辑的数据系列。",
                    )
                for target_position, target in enumerate(targets, start=1):
                    scoped_action = SetSeriesStyle(
                        action_id=f"{action_id}.{target_position}",
                        target=target,
                        expected_plot_version=plot_version,
                        **draft.model_dump(
                            exclude={"operation", "target_alias", "scope"}
                        ),
                    )
                    self.catalog.validate_action(
                        self.catalog.get(item.profile_id), scoped_action
                    )
                    current_revision = self.execute_action(scoped_action, current_revision)
                    plot_version += 1
                continue
            if isinstance(draft, DraftSetTitle):
                action = SetTitle(
                    action_id=action_id,
                    target=item.plot_id,
                    expected_plot_version=plot_version,
                    **draft.model_dump(exclude={"operation", "target_alias"}),
                )
            elif isinstance(draft, DraftSetAxis):
                action = SetAxis(
                    action_id=action_id,
                    target=self._target(item, draft.target_alias, "axis"),
                    expected_plot_version=plot_version,
                    **draft.model_dump(exclude={"operation", "target_alias"}),
                )
            elif isinstance(draft, DraftSetSeriesStyle):
                assert draft.target_alias is not None
                action = SetSeriesStyle(
                    action_id=action_id,
                    target=self._target(item, draft.target_alias, "series"),
                    expected_plot_version=plot_version,
                    **draft.model_dump(exclude={"operation", "target_alias", "scope"}),
                )
            elif isinstance(draft, DraftSetLegend):
                action = SetLegend(
                    action_id=action_id,
                    target=self._target(item, draft.target_alias, "legend"),
                    expected_plot_version=plot_version,
                    **draft.model_dump(exclude={"operation", "target_alias"}),
                )
            elif isinstance(draft, DraftSetColorMap):
                action = SetColorMap(
                    action_id=action_id,
                    target=self._target(item, draft.target_alias, "series"),
                    expected_plot_version=plot_version,
                    **draft.model_dump(exclude={"operation", "target_alias"}),
                )
            elif isinstance(draft, DraftSetErrorStyle):
                action = SetErrorStyle(
                    action_id=action_id,
                    target=self._target(item, draft.target_alias, "series"),
                    expected_plot_version=plot_version,
                    **draft.model_dump(exclude={"operation", "target_alias"}),
                )
            elif isinstance(draft, DraftSetDataLabels):
                action = SetDataLabels(
                    action_id=action_id,
                    target=self._target(item, draft.target_alias, "series"),
                    expected_plot_version=plot_version,
                    **draft.model_dump(exclude={"operation", "target_alias"}),
                )
            elif isinstance(draft, DraftSetChartParameter):
                action = SetChartParameter(
                    action_id=action_id,
                    target=item.plot_id,
                    expected_plot_version=plot_version,
                    parameter=draft.parameter,
                    value=draft.value,
                )
            elif isinstance(draft, DraftAddAnnotation):
                token = item.plot_id.removeprefix("plot:")
                action = AddAnnotation(
                    action_id=action_id,
                    target=item.plot_id,
                    expected_plot_version=plot_version,
                    annotation_id=f"annotation:{token}.{draft.annotation_alias}",
                    text=draft.text,
                    x=draft.x,
                    y=draft.y,
                    coordinate_system=draft.coordinate_system,
                    font_family=draft.font_family,
                    font_size_pt=draft.font_size_pt,
                    font_weight=draft.font_weight,
                    italic=draft.italic,
                    color=draft.color,
                    rotation_deg=draft.rotation_deg,
                )
            else:
                raise AssertionError("unknown workflow visual action")
            self.catalog.validate_action(self.catalog.get(item.profile_id), action)
            current_revision = self.execute_action(action, current_revision)
            plot_version += 1
        return current_revision, plot_version

    def _target(self, item: CompiledTaskItem, alias: str, expected_kind: str) -> str:
        profile = self.catalog.get(item.profile_id)
        fixed = next(
            (candidate for candidate in profile.objects if candidate.object_alias == alias),
            None,
        )
        if fixed is not None:
            if fixed.object_kind != expected_kind:
                raise WorkflowExecutionError("TARGET_KIND_INVALID", "任务目标类型与操作不匹配。")
            return fixed.instantiate(item.plot_id)
        for repeatable in profile.repeatable_objects:
            prefix = repeatable.object_alias_prefix + "_"
            ordinal = alias.removeprefix(prefix)
            if (
                alias.startswith(prefix)
                and ordinal.isdigit()
                and int(ordinal) >= 1
                and repeatable.object_kind == expected_kind
            ):
                return repeatable.instantiate(item.plot_id, int(ordinal))
        raise WorkflowExecutionError("TARGET_ALIAS_INVALID", "任务目标在图类中不可用。")
