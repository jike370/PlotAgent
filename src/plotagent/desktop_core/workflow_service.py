"""Desktop boundary for the goal-driven PlotAgent workflow runtime.

This is the only orchestration surface exposed by Desktop Core.  It accepts a
bounded goal context, produces a user-confirmable TaskDraft/TaskPlan, and runs
confirmed items through the public plotting engine.  Renderer objects, SQL,
paths and executable expressions never cross this boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, cast

from plotagent.contracts.canonical import canonical_json
from plotagent.contracts.workflows import (
    TaskDraft,
    WorkflowBudget,
    WorkflowContext,
    WorkflowField,
    WorkflowPlot,
    WorkflowRecipe,
    WorkflowSource,
)
from plotagent.engine import ProjectEngineDataProvider
from plotagent.storage import ProjectDomainRepository, ProjectStore
from plotagent.workflows import (
    DraftCompiler,
    WorkflowRepository,
    WorkflowRouter,
    build_recipe,
    goal_signature,
    profile_contract_hash,
    replay_recipe,
    structure_fingerprint,
)
from plotagent.workflows.data_ops import prepare_task_data
from plotagent.workflows.executor import TaskPlanExecutor
from plotagent.workflows.inspection import DataInspectionService

from .engine_session import DesktopEngineSession


class WorkflowServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class _InspectionRows:
    rows_by_alias: dict[str, tuple[tuple[object, ...], ...]]

    def rows(self, source_alias: str):  # type: ignore[no-untyped-def]
        try:
            return self.rows_by_alias[source_alias]
        except KeyError as error:
            raise WorkflowServiceError("SOURCE_ALIAS_INVALID", "数据表别名不可用。") from error


@dataclass(slots=True)
class DesktopWorkflowService:
    store: ProjectStore
    domain: ProjectDomainRepository
    engine: DesktopEngineSession
    repository: WorkflowRepository
    _inspections: dict[str, DataInspectionService] = field(default_factory=dict)
    _export_receipts: dict[str, tuple[str, int]] = field(default_factory=dict)

    def prepare(self, values: dict[str, object]) -> dict[str, object]:
        expected = self._integer(values.get("expected_project_version"), "expected_project_version")
        self.domain.require_revision(expected)
        instruction = self._text(values.get("instruction"), "instruction")
        run_id = f"workflow:{uuid.uuid4().hex}"
        source_requests = self._source_requests(values)
        records = {
            (item.source_dataset.source_dataset_id, item.source_dataset.source_version): item
            for item in self.store.list_source_datasets()
        }
        sources: list[WorkflowSource] = []
        fields: list[WorkflowField] = []
        rows: dict[str, tuple[tuple[object, ...], ...]] = {}
        for source_position, (dataset_id, version) in enumerate(source_requests, start=1):
            source = self.domain.source_record(dataset_id, version)
            table = self.domain.resolve_source(source)
            source_alias = f"data_{source_position}"
            record = records.get((dataset_id, version))
            display_name = (
                record.display_name
                if record is not None and record.display_name
                else table.display_name or dataset_id
            )
            sources.append(
                WorkflowSource(
                    source_alias=source_alias,
                    source_dataset_id=dataset_id,
                    source_version=version,
                    content_hash=source.content_hash,
                    display_name=display_name,
                    row_count=len(table.rows),
                )
            )
            rows[source_alias] = cast(Any, table.rows)
            for field_position, source_field in enumerate(source.field_schema, start=1):
                fields.append(
                    WorkflowField(
                        field_alias=f"data_{source_position}_field_{field_position}",
                        source_alias=source_alias,
                        field_id=source_field.field_id,
                        name=source_field.name,
                        logical_type=source_field.logical_type,
                        unit_label=(
                            source_field.unit.source_text.strip()
                            or source_field.unit.canonical_unit
                            or None
                        ),
                    )
                )
        selected_profiles = self._string_tuple(values.get("selected_profile_ids"))
        if not selected_profiles:
            selected = values.get("selected_profile_id")
            if selected is not None:
                selected_profiles = (self._text(selected, "selected_profile_id"),)
        allowed = tuple(profile.profile_id for profile in self.engine.catalog.profiles())
        if not set(selected_profiles) <= set(allowed):
            raise WorkflowServiceError("PROFILE_NOT_ALLOWED", "选择的图形类型不可用。")
        plots: list[WorkflowPlot] = []
        selected_plot_aliases: list[str] = []
        for position, plot_id in enumerate(
            self._string_tuple(values.get("selected_plot_ids")), start=1
        ):
            document = self.engine.documents.get(plot_id).document
            alias = f"plot_{position}"
            plots.append(
                WorkflowPlot(
                    plot_alias=alias,
                    plot_id=document.plot_id,
                    plot_version=document.plot_version,
                    profile_id=document.profile_id,
                )
            )
            selected_plot_aliases.append(alias)
        context = WorkflowContext(
            workflow_run_id=run_id,
            project_id=self.store.project_id,
            project_revision=expected,
            instruction=instruction,
            locale=cast(Any, values.get("locale", "zh-CN")),
            sources=tuple(sources),
            fields=tuple(fields),
            plots=tuple(plots),
            selected_source_aliases=tuple(source.source_alias for source in sources),
            selected_plot_aliases=tuple(selected_plot_aliases),
            selected_profile_ids=selected_profiles,
            allowed_profile_ids=allowed,
            budget=WorkflowBudget(),
        )
        self.repository.create_run(context)
        self._inspections[run_id] = DataInspectionService(context, _InspectionRows(rows))
        recipe = self._matching_recipe(context)
        if recipe is not None:
            draft = self.repository.save_draft(replay_recipe(recipe, context))
            plan = DraftCompiler(self.engine.catalog).compile(draft, context)
            snapshot = self.repository.save_plan(plan)
            return {
                "outcome": "draft_ready",
                "route": "recipe_replay",
                "recipe_id": recipe.recipe_id,
                "recipe_version": recipe.recipe_version,
                "draft": draft.model_dump(mode="json"),
                "task_plan": snapshot.model_dump(mode="json"),
            }
        routed = WorkflowRouter(self.engine.catalog).route(context)
        route_state = {
            "deterministic": "deterministic_attempt",
            "recipe_replay": "recipe_replay",
            "agent_single_turn": "agent_single_turn",
            "agent_exploration": "agent_exploration",
            "needs_input": "needs_input",
            "unsupported": "failed",
        }[routed.route]
        self.repository.transition_run(run_id, state=route_state, route=routed.route)
        if routed.deterministic is not None:
            decision = routed.deterministic
            if decision.outcome == "draft_ready":
                draft = self.repository.save_draft(decision.draft)
                plan = DraftCompiler(self.engine.catalog).compile(draft, context)
                snapshot = self.repository.save_plan(plan)
                return {
                    "outcome": "draft_ready",
                    "route": routed.route,
                    "draft": draft.model_dump(mode="json"),
                    "task_plan": snapshot.model_dump(mode="json"),
                }
            return {"route": routed.route, **decision.model_dump(mode="json")}
        return {
            "outcome": "agent_required",
            "route": routed.route,
            "workflow_run_id": run_id,
            "workflow_context": context.model_dump(mode="json"),
            "task_draft_schema": TaskDraft.model_json_schema(),
            "system_prompt": self._system_prompt(routed.route),
        }

    def submit_draft(self, workflow_run_id: str, raw_draft: object) -> dict[str, object]:
        context = self.repository.get_context(workflow_run_id)
        self.domain.require_revision(context.project_revision)
        # The desktop boundary receives JSON arrays; validating from canonical
        # JSON preserves strict scalar semantics while materializing tuple fields.
        draft = TaskDraft.model_validate_json(canonical_json(cast(Any, raw_draft)))
        if draft.workflow_run_id != workflow_run_id:
            raise WorkflowServiceError("WORKFLOW_CONTEXT_MISMATCH", "草稿不属于当前任务。")
        plan = DraftCompiler(self.engine.catalog).compile(draft, context)
        self.repository.save_draft(draft)
        snapshot = self.repository.save_plan(plan)
        return {
            "outcome": "draft_ready",
            "draft": draft.model_dump(mode="json"),
            "task_plan": snapshot.model_dump(mode="json"),
        }

    def inspect(
        self,
        workflow_run_id: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        service = self._inspection(workflow_run_id)
        result: Any
        if tool_name == "inspect_source":
            result = service.inspect_source(
                self._text(arguments.get("source_alias"), "source_alias")
            )
        elif tool_name == "preview_rows":
            result = service.preview_rows(
                self._text(arguments.get("source_alias"), "source_alias"),
                self._string_tuple(arguments.get("field_aliases")),
                offset=self._integer(arguments.get("offset", 0), "offset"),
                limit=self._integer(arguments.get("limit", 5), "limit"),
            )
        elif tool_name == "profile_field":
            result = service.profile_field(
                self._text(arguments.get("source_alias"), "source_alias"),
                self._text(arguments.get("field_alias"), "field_alias"),
            )
        elif tool_name == "compare_schemas":
            result = service.compare_schemas(self._string_tuple(arguments.get("source_aliases")))
        else:
            raise WorkflowServiceError("WORKFLOW_TOOL_UNKNOWN", "数据检查工具不可用。")
        return {
            "result": result.model_dump(mode="json"),
            "audit": service.audits[-1].model_dump(mode="json"),
        }

    def confirm(self, plan_id: str, accept: bool) -> dict[str, object]:
        snapshot = self.repository.confirm(plan_id) if accept else self.repository.reject(plan_id)
        return cast(dict[str, object], snapshot.model_dump(mode="json"))

    def run(self, plan_id: str) -> dict[str, object]:
        source_provider = ProjectEngineDataProvider(self.store)
        executor = TaskPlanExecutor(
            repository=self.repository,
            catalog=self.engine.catalog,
            prepare_data=lambda item: prepare_task_data(
                item, source_provider, self.engine.data_views
            ),
            execute_action=self._execute_action,
        )
        return executor.run(plan_id).model_dump(mode="json")

    def save_recipe(
        self,
        *,
        plan_id: str,
        display_name: str,
        export_hash: str,
    ) -> dict[str, object]:
        snapshot = self.repository.get_plan(plan_id)
        if snapshot.state != "succeeded":
            raise WorkflowServiceError(
                "WORKFLOW_RECIPE_PLAN_INCOMPLETE",
                "只有完整成功并已导出的任务可以固化为流程。",
            )
        exported_plot = self._export_receipts.get(export_hash)
        completed_plots = {
            (item.output_plot_id, item.output_plot_version)
            for item in snapshot.item_progress
            if item.state == "succeeded"
        }
        if exported_plot is None or exported_plot not in completed_plots:
            raise WorkflowServiceError(
                "WORKFLOW_RECIPE_EXPORT_UNVERIFIED",
                "没有找到该任务的成功导出凭据，不能固化流程。",
            )
        run = self.repository.get_run(snapshot.plan.workflow_run_id)
        if run.draft_id is None:
            raise WorkflowServiceError("WORKFLOW_DRAFT_MISSING", "任务草稿不可用。")
        context = self.repository.get_context(snapshot.plan.workflow_run_id)
        draft = self.repository.get_draft(run.draft_id)
        recipe = build_recipe(
            context=context,
            draft=draft,
            catalog=self.engine.catalog,
            plan_id=plan_id,
            display_name=display_name,
            export_hash=export_hash,
        )
        return self.repository.save_recipe(recipe).model_dump(mode="json")

    def record_export(self, artifact_hash: str, plot_id: str, plot_version: int) -> None:
        """Record a successful export receipt for explicit recipe provenance."""

        self._export_receipts[artifact_hash] = (plot_id, plot_version)

    def _matching_recipe(self, context: WorkflowContext) -> WorkflowRecipe | None:
        matches = self.repository.find_recipes(
            structure_fingerprint(context), goal_signature(context)
        )
        for recipe in matches:
            profile_ids = tuple(item.profile_id for item in recipe.draft_template.items)
            current_hash = profile_contract_hash(self.engine.catalog, profile_ids)
            if (
                recipe.engine_profile_hash == current_hash
                and recipe.renderer_contract_hash == current_hash
            ):
                self.repository.transition_run(
                    context.workflow_run_id,
                    state="recipe_replay",
                    route="recipe_replay",
                )
                return recipe
        return None

    def _execute_action(self, action, revision: int) -> int:  # type: ignore[no-untyped-def]
        self.engine.execute_action(action, expected_project_revision=revision)
        return self.domain.revision

    def _inspection(self, workflow_run_id: str) -> DataInspectionService:
        cached = self._inspections.get(workflow_run_id)
        if cached is not None:
            return cached
        context = self.repository.get_context(workflow_run_id)
        rows: dict[str, tuple[tuple[object, ...], ...]] = {}
        for source in context.sources:
            stored = self.domain.source_record(source.source_dataset_id, source.source_version)
            rows[source.source_alias] = cast(Any, self.domain.resolve_source(stored).rows)
        service = DataInspectionService(context, _InspectionRows(rows))
        self._inspections[workflow_run_id] = service
        return service

    @staticmethod
    def _source_requests(values: dict[str, object]) -> tuple[tuple[str, int], ...]:
        raw = values.get("selected_sources")
        if not isinstance(raw, list):
            raise WorkflowServiceError("SOURCE_INVALID", "数据表选择无效。")
        if not raw:
            selected_plots = values.get("selected_plot_ids")
            if isinstance(selected_plots, (list, tuple)) and selected_plots:
                return ()
            raise WorkflowServiceError("SOURCE_REQUIRED", "至少选择一个数据表或一张已有图形。")
        if len(raw) > 8:
            raise WorkflowServiceError("SOURCE_LIMIT_EXCEEDED", "一次最多选择八个数据表。")
        result: list[tuple[str, int]] = []
        for item in raw:
            if not isinstance(item, dict):
                raise WorkflowServiceError("SOURCE_INVALID", "数据表选择无效。")
            dataset_id = DesktopWorkflowService._text(item.get("dataset_id"), "dataset_id")
            version = DesktopWorkflowService._integer(item.get("source_version"), "source_version")
            result.append((dataset_id, version))
        if len(result) != len(set(result)):
            raise WorkflowServiceError("SOURCE_DUPLICATED", "数据表选择不能重复。")
        return tuple(result)

    @staticmethod
    def _system_prompt(route: str) -> str:
        turn_note = (
            "可先调用只读检查工具理解数据。"
            if route == "agent_exploration"
            else "优先直接提交任务草稿。"
        )
        return (
            "你是 PlotAgent 的任务编排 Agent。根据 workflow_context 生成一个 TaskDraft。"
            "只能使用上下文中的别名、允许的图类、封闭数据操作和视觉动作；"
            "不得输出代码、SQL、文件路径或 renderer 参数。"
            "不要猜测数据内容；需要事实时调用只读检查工具。"
            "每个任务项必须明确数据来源、字段角色、图类和用户要求的视觉动作。"
            f"{turn_note} 最后调用 submit_task_draft；不得直接执行或导出。"
        )

    @staticmethod
    def _text(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise WorkflowServiceError("INVALID_PARAMS", f"{name} 无效。")
        return value.strip()

    @staticmethod
    def _integer(value: object, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise WorkflowServiceError("INVALID_PARAMS", f"{name} 无效。")
        return value

    @staticmethod
    def _string_tuple(value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise WorkflowServiceError("INVALID_PARAMS", "字符串列表无效。")
        result = tuple(DesktopWorkflowService._text(item, "list item") for item in value)
        if len(result) != len(set(result)):
            raise WorkflowServiceError("INVALID_PARAMS", "字符串列表不能重复。")
        return result
