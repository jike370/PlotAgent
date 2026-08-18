"""Lifecycle-owned desktop application services for the local plotting slice."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import uuid
from collections.abc import Callable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from plotagent.contracts.agent_tasks import (
    AGENT_YIELD_ADAPTER,
    AgentActivation,
    TaskCompletion,
    TaskEnvelope,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.datasets import (
    SourceDataset,
)
from plotagent.desktop_core.agent_execution import (
    DurableExecutionError,
    DurableTaskExecutionService,
)
from plotagent.desktop_core.agent_foundation import (
    AgentFoundationError,
    DurableAgentCoreHost,
    DurableTaskCoordinator,
)
from plotagent.desktop_core.engine_session import DesktopEngineSession
from plotagent.desktop_core.protocol import JsonValue as RpcJsonValue
from plotagent.desktop_core.services import RpcContext, RpcServiceError, ServiceRegistry
from plotagent.desktop_core.tasks import (
    BoundedWorkerExecutor,
    TaskControlError,
    TaskRegistry,
)
from plotagent.desktop_core.workflow_service import (
    DesktopWorkflowService,
    WorkflowServiceError,
)
from plotagent.engine import (
    EngineVersionConflict,
    PlotEngineAction,
)
from plotagent.engine.backends.origin import preflight_origin
from plotagent.importing.models import Clarification, Rejection
from plotagent.preparation.artifacts import ResolvedSourceTable
from plotagent.preparation.errors import PreparationProblem
from plotagent.security import (
    CredentialStore,
    NetworkMode,
    NetworkPolicyGate,
    create_credential_store,
)
from plotagent.storage import (
    Catalog,
    ImportCommitResult,
    ImportResource,
    ProjectDomainRepository,
    ProjectImportService,
    ProjectPackageService,
    ProjectStore,
    SourceDatasetRecord,
    read_project_revision,
)
from plotagent.storage.errors import StorageProblem
from plotagent.tasking import TaskLedgerRepository
from plotagent.workflows import WorkflowCompileError, WorkflowRepository
from plotagent.workflows.data_ops import WorkflowDataError
from plotagent.workflows.executor import WorkflowExecutionError
from plotagent.workflows.inspection import InspectionError

type ProductHandler = Callable[[RpcContext, RpcJsonValue | None], RpcJsonValue]

_PROVIDER_SETTING_KEY = "agent.provider.active"
_CUSTOM_PROVIDER_CONFIG_ID = "custom.default"


def _preview_scalar(value: object) -> RpcJsonValue:
    """Return a bounded, JSON-safe display value without changing source data."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "∞" if value > 0 else "-∞"
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


@dataclass(slots=True)
class ProjectSession:
    store: ProjectStore
    domain: ProjectDomainRepository
    imports: ProjectImportService
    engine: DesktopEngineSession
    workflow: DesktopWorkflowService
    durable_tasks: TaskLedgerRepository
    task_coordinator: DurableTaskCoordinator
    task_host: DurableAgentCoreHost
    task_execution: DurableTaskExecutionService

    @property
    def project_id(self) -> str:
        return self.store.project_id

    def close(self) -> None:
        self.store.close()


class DesktopApplication:
    """Own the catalog and all active project single-writer sessions."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self.root = self._default_root() if root is None else Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.projects_root = self.root / "projects"
        self.projects_root.mkdir(exist_ok=True)
        catalog_path = self.root / "catalog.sqlite3"
        self.catalog = (
            Catalog.open(catalog_path) if catalog_path.is_file() else Catalog.create(catalog_path)
        )
        self._sessions: dict[str, ProjectSession] = {}
        self._packages = ProjectPackageService(self.catalog, self.projects_root)
        self._credential_store = credential_store or create_credential_store()
        self._closed = False

    @staticmethod
    def _default_root() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).resolve() / "PlotAgent"
        return Path.home().resolve() / "AppData" / "Local" / "PlotAgent"

    def configure_services(
        self,
        registry: ServiceRegistry,
        _tasks: TaskRegistry,
        _workers: BoundedWorkerExecutor,
    ) -> None:
        handlers: dict[str, ProductHandler] = {
            "projects.list": self._projects_list,
            "projects.create": self._projects_create,
            "projects.rename": self._projects_rename,
            "projects.delete": self._projects_delete,
            "projects.open": self._projects_open,
            "projects.close": self._projects_close,
            "datasets.import": self._datasets_import,
            "datasets.list": self._datasets_list,
            "datasets.describe": self._datasets_describe,
            "engine.catalog.get": self._engine_catalog_get,
            "engine.actions.execute": self._engine_actions_execute,
            "engine.exports.execute": self._engine_exports_execute,
            "engine.plots.list": self._engine_plots_list,
            "engine.plots.get": self._engine_plots_get,
            "workflow.prepare": self._workflow_prepare,
            "workflow.submit_draft": self._workflow_submit_draft,
            "workflow.inspect": self._workflow_inspect,
            "workflow.preview_operation": self._workflow_preview_operation,
            "workflow.ask_user": self._workflow_ask_user,
            "workflow.report_unsupported": self._workflow_report_unsupported,
            "workflow.plans.get": self._workflow_plan_get,
            "workflow.plans.list": self._workflow_plan_list,
            "workflow.plans.confirm": self._workflow_plan_confirm,
            "workflow.plans.reject": self._workflow_plan_reject,
            "workflow.plans.run": self._workflow_plan_run,
            "workflow.plans.resume": self._workflow_plan_run,
            "workflow.recipes.save": self._workflow_recipe_save,
            "workflow.recipes.list": self._workflow_recipe_list,
            "agent.tasks.create": self._agent_task_create,
            "agent.tasks.get": self._agent_task_get,
            "agent.tasks.list": self._agent_task_list,
            "agent.tasks.events": self._agent_task_events,
            "agent.tasks.advance": self._agent_task_advance,
            "agent.tasks.pump.next": self._agent_task_pump_next,
            "agent.tasks.complete": self._agent_task_complete,
            "agent.tasks.activation.start": self._agent_activation_start,
            "agent.tasks.activation.running": self._agent_activation_running,
            "agent.activations.prepare": self._agent_activation_prepare,
            "agent.tools.invoke": self._agent_tool_invoke,
            "agent.yields.validate": self._agent_yield_validate,
            "agent.tasks.yield.accept": self._agent_yield_accept,
            "agent.tasks.user_event": self._agent_task_user_event,
            "agent.tasks.plan.get": self._agent_task_plan_get,
            "agent.tasks.plan.confirm": self._agent_task_plan_confirm,
            "agent.tasks.plan.reject": self._agent_task_plan_reject,
            "agent.tasks.execute": self._agent_task_execute,
            "agent.tasks.cancel": self._agent_task_cancel,
            "provider.status": self._provider_status,
            "provider.runtime.get": self._provider_runtime_get,
            "provider.configure": self._provider_configure,
            "provider.clear": self._provider_clear,
            "origin.status": self._origin_status,
        }
        for method, handler in handlers.items():
            registry.register(method, self._guard(handler))

    def _agent_task_create(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "envelope"})
        session = self._session(_text(values["project_id"], "project_id"))
        checkpoint = session.durable_tasks.create_task(
            TaskEnvelope.model_validate_json(json.dumps(values["envelope"]))
        )
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _agent_task_get(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "task_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        checkpoint = session.durable_tasks.get_task(_text(values["task_id"], "task_id"))
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _agent_task_list(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id"}, optional={"state", "limit"})
        session = self._session(_text(values["project_id"], "project_id"))
        state = _optional_text(values.get("state"), "state")
        raw_limit = values.get("limit", 100)
        if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
            raise RpcServiceError("INVALID_PARAMS", "Task list limit was invalid.")
        tasks = session.durable_tasks.list_tasks(
            state=cast(Any, state),
            limit=raw_limit,
        )
        return {"tasks": [cast(RpcJsonValue, item.model_dump(mode="json")) for item in tasks]}

    def _agent_task_events(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "task_id"},
            optional={"after_sequence"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        after = values.get("after_sequence", 0)
        if isinstance(after, bool) or not isinstance(after, int) or after < 0:
            raise RpcServiceError("INVALID_PARAMS", "Task event cursor was invalid.")
        events = session.durable_tasks.list_events(
            _text(values["task_id"], "task_id"), after_sequence=after
        )
        return {"events": [cast(RpcJsonValue, item.model_dump(mode="json")) for item in events]}

    def _agent_task_advance(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "task_id",
                "expected_task_version",
                "next_state",
                "reason_code",
            },
            optional={"project_revision"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        expected = _integer(values["expected_task_version"], "expected_task_version", minimum=1)
        revision = values.get("project_revision")
        if revision is not None and (
            isinstance(revision, bool) or not isinstance(revision, int) or revision < 0
        ):
            raise RpcServiceError("INVALID_PARAMS", "Project revision was invalid.")
        checkpoint = session.durable_tasks.advance(
            _text(values["task_id"], "task_id"),
            expected_task_version=expected,
            next_state=cast(Any, _text(values["next_state"], "next_state")),
            reason_code=_text(values["reason_code"], "reason_code"),
            project_revision=revision,
        )
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _agent_task_pump_next(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "task_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.task_coordinator.next_action(_text(values["task_id"], "task_id")),
        )

    def _agent_activation_start(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "activation"})
        session = self._session(_text(values["project_id"], "project_id"))
        checkpoint = session.durable_tasks.start_activation(
            AgentActivation.model_validate_json(json.dumps(values["activation"]))
        )
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _agent_task_complete(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "task_id",
                "expected_task_version",
                "completion",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        completion = TaskCompletion.model_validate_json(json.dumps(values["completion"]))
        checkpoint = session.durable_tasks.complete_task(
            _text(values["task_id"], "task_id"),
            expected_task_version=_integer(
                values["expected_task_version"], "expected_task_version", minimum=1
            ),
            completion=completion,
        )
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _agent_activation_running(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "activation_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        checkpoint = session.durable_tasks.mark_activation_running(
            _text(values["activation_id"], "activation_id")
        )
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _agent_activation_prepare(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "activation_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.task_host.prepare(_text(values["activation_id"], "activation_id")),
        )

    def _agent_tool_invoke(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "invocation", "arguments"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        invocation = values["invocation"]
        arguments = values["arguments"]
        if not isinstance(invocation, dict) or not isinstance(arguments, dict):
            raise RpcServiceError("INVALID_PARAMS", "Tool invocation was invalid.")
        result = session.task_host.invoke(
            invocation_value=cast(dict[str, object], invocation),
            arguments=cast(JsonValue, arguments),
        )
        return cast(RpcJsonValue, result.model_dump(mode="json"))

    def _agent_yield_validate(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "activation_id", "yield"})
        session = self._session(_text(values["project_id"], "project_id"))
        candidate = values["yield"]
        if not isinstance(candidate, dict):
            raise RpcServiceError("INVALID_PARAMS", "Agent yield was invalid.")
        yielded = session.task_host.validate_yield(
            _text(values["activation_id"], "activation_id"),
            cast(JsonValue, candidate),
        )
        return cast(RpcJsonValue, yielded.model_dump(mode="json"))

    def _agent_yield_accept(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "yield"})
        session = self._session(_text(values["project_id"], "project_id"))
        yielded = AGENT_YIELD_ADAPTER.validate_json(json.dumps(values["yield"]))
        checkpoint = session.task_host.accept_yield(yielded)
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _agent_task_user_event(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "task_id",
                "expected_task_version",
                "action",
                "user_event_id",
                "payload_hash",
            },
            optional={"message"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        checkpoint = session.durable_tasks.record_user_event(
            _text(values["task_id"], "task_id"),
            expected_task_version=_integer(
                values["expected_task_version"], "expected_task_version", minimum=1
            ),
            action=cast(Any, _text(values["action"], "action")),
            user_event_id=_text(values["user_event_id"], "user_event_id"),
            payload_hash=_text(values["payload_hash"], "payload_hash"),
            message=_optional_text(values.get("message"), "message"),
        )
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _agent_task_plan_get(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "task_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.task_execution.plan_view(_text(values["task_id"], "task_id")),
        )

    def _agent_task_plan_confirm(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "task_id",
                "expected_task_version",
                "user_event_id",
                "plan_hash",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.task_execution.confirm(
                _text(values["task_id"], "task_id"),
                expected_task_version=_integer(
                    values["expected_task_version"], "expected_task_version", minimum=1
                ),
                user_event_id=_text(values["user_event_id"], "user_event_id"),
                plan_hash=_text(values["plan_hash"], "plan_hash"),
            ),
        )

    def _agent_task_plan_reject(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "task_id",
                "expected_task_version",
                "user_event_id",
                "plan_hash",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.task_execution.reject(
                _text(values["task_id"], "task_id"),
                expected_task_version=_integer(
                    values["expected_task_version"], "expected_task_version", minimum=1
                ),
                user_event_id=_text(values["user_event_id"], "user_event_id"),
                plan_hash=_text(values["plan_hash"], "plan_hash"),
            ),
        )

    def _agent_task_execute(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "task_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.task_execution.run(_text(values["task_id"], "task_id")),
        )

    def _agent_task_cancel(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "task_id",
                "expected_task_version",
                "user_event_id",
                "payload_hash",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        checkpoint = session.durable_tasks.cancel(
            _text(values["task_id"], "task_id"),
            expected_task_version=_integer(
                values["expected_task_version"], "expected_task_version", minimum=1
            ),
            user_event_id=_text(values["user_event_id"], "user_event_id"),
            payload_hash=_text(values["payload_hash"], "payload_hash"),
        )
        return cast(RpcJsonValue, checkpoint.model_dump(mode="json"))

    def _origin_status(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        _object(params, required=set())
        probe_target = self.root / ".origin-environment-probe.opju"
        return cast(RpcJsonValue, preflight_origin(probe_target).to_dict())

    def _engine_catalog_get(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(RpcJsonValue, session.engine.catalog_payload())

    def _workflow_prepare(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "expected_project_version",
                "instruction",
                "selected_sources",
            },
            optional={
                "selected_profile_id",
                "selected_profile_ids",
                "selected_plot_ids",
                "selected_recipe_id",
                "continuation_workflow_run_id",
                "locale",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(RpcJsonValue, session.workflow.prepare(cast(dict[str, object], values)))

    def _workflow_submit_draft(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "workflow_run_id", "task_draft"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.submit_draft(
                _text(values["workflow_run_id"], "workflow_run_id"),
                values["task_draft"],
            ),
        )

    def _workflow_inspect(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "workflow_run_id", "tool_name", "arguments"},
        )
        arguments = values["arguments"]
        if not isinstance(arguments, dict):
            raise RpcServiceError("INVALID_PARAMS", "Inspection arguments must be an object.")
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.inspect(
                _text(values["workflow_run_id"], "workflow_run_id"),
                _text(values["tool_name"], "tool_name"),
                cast(dict[str, object], arguments),
            ),
        )

    def _workflow_plan_get(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.repository.get_plan(_text(values["plan_id"], "plan_id")).model_dump(
                mode="json"
            ),
        )

    def _workflow_plan_list(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return {
            "task_plans": [
                item.model_dump(mode="json") for item in session.workflow.repository.list_plans()
            ]
        }

    def _workflow_plan_confirm(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.confirm(_text(values["plan_id"], "plan_id"), True),
        )

    def _workflow_plan_reject(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.confirm(_text(values["plan_id"], "plan_id"), False),
        )

    def _workflow_plan_run(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.run(_text(values["plan_id"], "plan_id")),
        )

    def _workflow_recipe_save(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "plan_id", "display_name", "export_hash"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.save_recipe(
                plan_id=_text(values["plan_id"], "plan_id"),
                display_name=_text(values["display_name"], "display_name"),
                export_hash=_text(values["export_hash"], "export_hash"),
            ),
        )

    def _workflow_recipe_list(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return {
            "workflow_recipes": [
                item.model_dump(mode="json") for item in session.workflow.repository.list_recipes()
            ]
        }

    def _workflow_ask_user(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "workflow_run_id", "questions"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.ask_user(
                _text(values["workflow_run_id"], "workflow_run_id"),
                values["questions"],
            ),
        )

    def _workflow_report_unsupported(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "workflow_run_id", "reason_code", "message"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            session.workflow.report_unsupported(
                _text(values["workflow_run_id"], "workflow_run_id"),
                _text(values["reason_code"], "reason_code"),
                _text(values["message"], "message"),
            ),
        )

    def _workflow_preview_operation(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "workflow_run_id", "operation"},
            optional={"limit"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        limit = values.get("limit", 5)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise RpcServiceError("INVALID_PARAMS", "limit must be an integer.")
        return cast(
            RpcJsonValue,
            session.workflow.preview_operation(
                _text(values["workflow_run_id"], "workflow_run_id"),
                values["operation"],
                limit=limit,
            ),
        )

    def _engine_actions_execute(
        self, context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "action", "expected_project_version"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        action = values["action"]
        if not isinstance(action, dict):
            raise RpcServiceError("INVALID_PARAMS", "Engine action must be an object.")
        task_id = self._begin_task(context, "engine-action", label="绘图任务")
        try:
            context.tasks.transition(task_id, "running")
            payload = session.engine.execute(
                cast(dict[str, object], action),
                expected_project_revision=_integer(
                    values["expected_project_version"],
                    "expected_project_version",
                    minimum=0,
                ),
            )
            context.tasks.transition(task_id, "committing")
            context.tasks.transition(task_id, "succeeded")
            return cast(
                RpcJsonValue,
                {
                    "task_id": task_id,
                    "project_id": session.project_id,
                    "project_version": session.domain.revision,
                    **payload,
                },
            )
        except Exception as error:
            self._fail_task(context.tasks, task_id, error)
            raise

    def _engine_plots_list(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            {
                "project_id": session.project_id,
                "project_version": session.domain.revision,
                "plots": session.engine.list_latest(),
            },
        )

    def _engine_exports_execute(
        self, context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "action",
                "destination_resource_id",
                "destination_path",
            },
            optional={"expected_existing_sha256"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        action = values["action"]
        if not isinstance(action, dict):
            raise RpcServiceError("INVALID_PARAMS", "Engine export action must be an object.")
        destination = Path(_text(values["destination_path"], "destination_path")).resolve()
        resource_id = _text(values["destination_resource_id"], "destination_resource_id")
        export_format = _optional_text(action.get("format"), "format")
        install_dir: Path | None = None
        if export_format == "opju":
            preflight = preflight_origin(
                destination,
                expected_existing_sha256=_optional_text(
                    values.get("expected_existing_sha256"),
                    "expected_existing_sha256",
                ),
            )
            if preflight.status != "ready":
                raise RpcServiceError(preflight.error.code.value, preflight.error.message)
            install_dir = Path(preflight.environment.install_dir)
        task_id = self._begin_task(
            context,
            "engine-export",
            label=f"导出 {destination.name}",
        )
        try:
            context.tasks.transition(task_id, "running")
            try:
                payload = session.engine.export(
                    cast(dict[str, object], action),
                    destination,
                    origin_install_dir=install_dir,
                )
            except Exception as error:
                if export_format != "opju":
                    raise
                raise RpcServiceError(
                    "ORIGIN_EXPORT_FAILED",
                    "Origin 原生项目生成失败，未写出文件。请重新检测 Origin 后再试一次。",
                ) from error
            artifact = cast(dict[str, object], payload.pop("artifact"))
            session.workflow.record_export(
                _text(cast(RpcJsonValue, artifact["artifact_hash"]), "artifact_hash"),
                _text(cast(RpcJsonValue, payload["plot_id"]), "plot_id"),
                _integer(
                    cast(RpcJsonValue, payload["plot_version"]),
                    "plot_version",
                    minimum=1,
                ),
            )
            context.tasks.transition(task_id, "committing")
            context.tasks.transition(task_id, "succeeded")
            return cast(
                RpcJsonValue,
                {
                    "task_id": task_id,
                    "export_id": "export:engine." + uuid.uuid4().hex,
                    "project_id": session.project_id,
                    "project_version": session.domain.revision,
                    "destination_name": destination.name,
                    "artifact": {
                        "backend": artifact["backend"],
                        "format": artifact["format"],
                        "resource_id": resource_id,
                        "path": str(destination),
                        "content_hash": artifact["artifact_hash"],
                        "size": artifact["artifact_size"],
                    },
                    **payload,
                },
            )
        except Exception as error:
            self._fail_task(context.tasks, task_id, error)
            raise

    def _engine_plots_get(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "plot_id"},
            optional={"plot_version"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        version = _optional_integer(values.get("plot_version"), "plot_version", minimum=1)
        return cast(
            RpcJsonValue,
            {
                "project_id": session.project_id,
                "project_version": session.domain.revision,
                **session.engine.get(_text(values["plot_id"], "plot_id"), version),
            },
        )

    def _provider_status(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        _object(params, required=set())
        config = self._saved_provider_config()
        if config is None:
            return {
                "mode": NetworkMode.LOCAL_ONLY.value,
                "configured": False,
                "retention_acknowledged": False,
            }
        config_id = _text(config["provider_config_id"], "provider_config_id")
        return {
            "mode": NetworkMode.CUSTOM_PROVIDER.value,
            "configured": self._credential_store.get_custom_api_key(config_id) is not None,
            "provider_config_id": config_id,
            "endpoint_origin": _text(config["base_url"], "base_url"),
            "model_id": _text(config["model_id"], "model_id"),
            "model_profile": _optional_text(config.get("model_profile"), "model_profile")
            or "custom-fixed",
            "retention_acknowledged": bool(config.get("retention_acknowledged", False)),
        }

    def _provider_runtime_get(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        """Return provider material only to the trusted desktop main process.

        This RPC is intentionally not exposed through the preload bridge.  It lets
        the Pi runtime reuse the credential already protected by the platform
        credential store without copying it into renderer state or a second file.
        """

        _object(params, required=set())
        config = self._saved_provider_config()
        if config is None:
            raise RpcServiceError(
                "PROVIDER_NOT_CONFIGURED", "A custom model provider is not configured."
            )
        config_id = _text(config["provider_config_id"], "provider_config_id")
        api_key = self._credential_store.get_custom_api_key(config_id)
        if api_key is None:
            raise RpcServiceError(
                "PROVIDER_NOT_CONFIGURED", "A custom model provider API key is required."
            )
        return {
            "provider_config_id": config_id,
            "base_url": _text(config["base_url"], "base_url"),
            "model_id": _text(config["model_id"], "model_id"),
            "api_key": api_key,
        }

    def _provider_configure(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "mode",
                "provider_config_id",
                "base_url",
                "model_id",
                "retention_acknowledged",
            },
            optional={"api_key", "model_profile"},
        )
        if _text(values["mode"], "mode") != NetworkMode.CUSTOM_PROVIDER.value:
            raise RpcServiceError(
                "INVALID_PARAMS", "Only a custom provider can be configured locally."
            )
        config_id = _text(values["provider_config_id"], "provider_config_id")
        if config_id != _CUSTOM_PROVIDER_CONFIG_ID:
            raise RpcServiceError("INVALID_PARAMS", "The provider config ID is not allowed.")
        if values["retention_acknowledged"] is not True:
            raise RpcServiceError(
                "PROVIDER_RETENTION_UNACKNOWLEDGED",
                "The provider retention disclosure must be acknowledged.",
            )
        config: dict[str, RpcJsonValue] = {
            "provider_config_id": config_id,
            "base_url": _text(values["base_url"], "base_url"),
            "model_id": _text(values["model_id"], "model_id"),
            "model_profile": _optional_text(values.get("model_profile"), "model_profile")
            or "custom-fixed",
            "retention_acknowledged": True,
        }
        # Validate exactly the endpoint policy used by the Pi runtime before any
        # non-secret configuration is persisted.
        api_key = _optional_text(values.get("api_key"), "api_key")
        if api_key is not None:
            self._credential_store.set_custom_api_key(config_id, api_key)
        if self._credential_store.get_custom_api_key(config_id) is None:
            raise RpcServiceError(
                "PROVIDER_NOT_CONFIGURED", "A custom provider API key is required."
            )
        try:
            NetworkPolicyGate(
                NetworkMode.CUSTOM_PROVIDER,
                custom_endpoint=_text(config["base_url"], "base_url"),
            )
        except Exception:
            if api_key is not None:
                self._credential_store.delete_custom_api_key(config_id)
            raise RpcServiceError(
                "PROVIDER_NOT_CONFIGURED", "The custom provider configuration is invalid."
            ) from None
        self.catalog.set_setting(
            _PROVIDER_SETTING_KEY,
            json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        return self._provider_status(_context, {})

    def _provider_clear(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        _object(params, required=set())
        config = self._saved_provider_config()
        if config is not None:
            config_id = _text(config["provider_config_id"], "provider_config_id")
            self._credential_store.delete_custom_api_key(config_id)
        self.catalog.delete_setting(_PROVIDER_SETTING_KEY)
        return self._provider_status(_context, {})

    def _saved_provider_config(self) -> dict[str, RpcJsonValue] | None:
        encoded = self.catalog.get_setting(_PROVIDER_SETTING_KEY)
        if encoded is None:
            return None
        try:
            parsed = json.loads(encoded)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
            return None
        return cast(dict[str, RpcJsonValue], parsed)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for session in tuple(self._sessions.values()):
            session.close()
        self._sessions.clear()
        self.catalog.close()

    def _guard(self, handler: ProductHandler) -> ProductHandler:
        def guarded(context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
            try:
                return handler(context, params)
            except RpcServiceError:
                raise
            except StorageProblem as error:
                raise RpcServiceError(str(error.code), error.message) from None
            except EngineVersionConflict as error:
                raise RpcServiceError("ENGINE_VERSION_CONFLICT", str(error)) from None
            except PreparationProblem as error:
                raise RpcServiceError(str(error.code), error.message) from None
            except (
                AgentFoundationError,
                DurableExecutionError,
                WorkflowServiceError,
                WorkflowCompileError,
                WorkflowDataError,
                WorkflowExecutionError,
                InspectionError,
            ) as error:
                raise RpcServiceError(error.code, error.message) from None
            except ValidationError:
                raise RpcServiceError(
                    "INVALID_PARAMS", "The request parameters were invalid."
                ) from None
            except (KeyError, TypeError, ValueError):
                raise RpcServiceError(
                    "INVALID_PARAMS", "The request parameters were invalid."
                ) from None

        return guarded

    def _projects_list(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        _object(params, required=set())
        return {
            "projects": [
                self._project_summary(
                    item.project_id,
                    item.display_name,
                    item.last_opened_at,
                    project_version=(
                        self._sessions[item.project_id].domain.revision
                        if item.project_id in self._sessions
                        else read_project_revision(item.workspace_path)
                    ),
                )
                for item in self.catalog.list_projects()
            ]
        }

    def _projects_create(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"idempotency_key"}, optional={"display_name"})
        key = _text(values["idempotency_key"], "idempotency_key")
        display_name = _optional_text(values.get("display_name"), "display_name")
        suffix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        project_id = f"project:{suffix}"
        workspace = self.projects_root / suffix
        try:
            existing = self.catalog.get_project(project_id)
        except StorageProblem:
            existing = None
        if existing is not None:
            if existing.display_name != display_name:
                raise RpcServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "The idempotency key was already used for a different project request.",
                )
            return {
                **self._project_summary(
                    existing.project_id,
                    existing.display_name,
                    existing.last_opened_at,
                    project_version=read_project_revision(existing.workspace_path),
                ),
                "replayed": True,
            }
        store = ProjectStore.create(workspace, project_id=project_id)
        store.close()
        catalog_project = self.catalog.register_project(
            project_id=project_id,
            workspace_path=workspace,
            display_name=display_name,
        )
        return {
            **self._project_summary(
                catalog_project.project_id,
                catalog_project.display_name,
                catalog_project.last_opened_at,
                project_version=0,
            ),
            "replayed": False,
        }

    def _projects_rename(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "display_name"})
        project_id = _text(values["project_id"], "project_id")
        display_name = _text(values["display_name"], "display_name").strip()
        if not display_name or len(display_name) > 120:
            raise RpcServiceError("INVALID_PARAMS", "Project display name was invalid.")
        renamed = self.catalog.rename_project(project_id, display_name)
        return self._project_summary(
            renamed.project_id,
            renamed.display_name,
            renamed.last_opened_at,
            project_version=(
                self._sessions[project_id].domain.revision
                if project_id in self._sessions
                else read_project_revision(renamed.workspace_path)
            ),
        )

    def _projects_delete(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        project_id = _text(values["project_id"], "project_id")
        catalog_project = self.catalog.get_project(project_id)
        workspace = Path(catalog_project.workspace_path).resolve()
        projects_root = self.projects_root.resolve()
        try:
            relative_workspace = workspace.relative_to(projects_root)
        except ValueError:
            raise RpcServiceError(
                "PROJECT_DELETE_UNSAFE",
                "Project workspace was outside the managed projects directory.",
            ) from None
        if (
            workspace == projects_root
            or len(relative_workspace.parts) != 1
            or not workspace.is_dir()
        ):
            raise RpcServiceError(
                "PROJECT_DELETE_UNSAFE",
                "Project workspace was not a removable managed directory.",
            )

        session = self._sessions.pop(project_id, None)
        if session is not None:
            session.close()

        quarantine_root = projects_root / ".trash"
        quarantine_root.mkdir(exist_ok=True)
        quarantine = quarantine_root / f"{workspace.name}.{uuid.uuid4().hex}.deleting"
        os.replace(workspace, quarantine)
        try:
            self.catalog.delete_project(project_id)
        except Exception:
            os.replace(quarantine, workspace)
            raise

        cleanup_pending = False
        try:
            shutil.rmtree(quarantine)
        except OSError:
            cleanup_pending = True
        return {
            "project_id": project_id,
            "status": "deleted",
            "cleanup_pending": cleanup_pending,
        }

    def _open_project_id(self, project_id: str, *, replayed: bool = False) -> RpcJsonValue:
        existing = self._sessions.get(project_id)
        if existing is not None:
            return self._session_summary(existing, replayed=True)
        catalog_project = self.catalog.get_project(project_id)
        store = ProjectStore.open(catalog_project.workspace_path)
        domain = ProjectDomainRepository(store)
        engine = DesktopEngineSession.open(store)
        workflow_repository = WorkflowRepository(store)
        durable_tasks = TaskLedgerRepository(store)
        workflow = DesktopWorkflowService(
            store=store,
            domain=domain,
            engine=engine,
            repository=workflow_repository,
        )
        task_host = DurableAgentCoreHost(
            store,
            domain,
            durable_tasks,
            catalog=engine.catalog,
        )
        session = ProjectSession(
            store=store,
            domain=domain,
            imports=ProjectImportService(store),
            engine=engine,
            workflow=workflow,
            durable_tasks=durable_tasks,
            task_coordinator=DurableTaskCoordinator(
                durable_tasks,
                plan_stager=task_host.ensure_plan,
            ),
            task_host=task_host,
            task_execution=DurableTaskExecutionService(
                store=store,
                domain=domain,
                engine=engine,
                workflow=workflow,
                ledger=durable_tasks,
            ),
        )
        self._sessions[project_id] = session
        self.catalog.touch_project(project_id)
        return self._session_summary(session, replayed=replayed)

    def _projects_open(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required=set(),
            optional={"project_id", "resource_id", "source_path", "as_new_copy"},
        )
        if "project_id" in values:
            if set(values) != {"project_id"}:
                raise RpcServiceError(
                    "INVALID_PARAMS", "Catalog project open accepts only project_id."
                )
            return self._open_project_id(_text(values["project_id"], "project_id"))
        if set(values) - {"resource_id", "source_path", "as_new_copy"} or not {
            "resource_id",
            "source_path",
        }.issubset(values):
            raise RpcServiceError(
                "INVALID_PARAMS",
                "Project package open requires an authorized resource and source path.",
            )
        # ``resource_id`` is retained in the request/audit boundary while the Main-owned
        # resource registry remains authoritative for the path. Core still revalidates the
        # package bytes, manifest, archive entries, checksums, SQLite and CAS before import.
        _text(values["resource_id"], "resource_id")
        source_path = Path(_text(values["source_path"], "source_path"))
        as_new_copy = values.get("as_new_copy", False)
        if not isinstance(as_new_copy, bool):
            raise RpcServiceError("INVALID_PARAMS", "as_new_copy was invalid.")
        imported = self._packages.import_package(source_path, as_new_copy=as_new_copy)
        opened = self._open_project_id(imported.project_id, replayed=imported.reused)
        if not isinstance(opened, dict):
            raise RpcServiceError("INTERNAL_ERROR", "Project session response was invalid.")
        return {
            **opened,
            "package": {
                "package_sha256": imported.package_sha256,
                "source_project_id": imported.source_project_id,
                "reused": imported.reused,
                "as_new_copy": imported.as_new_copy,
            },
        }

    def _projects_close(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        project_id = _text(values["project_id"], "project_id")
        session = self._sessions.pop(project_id, None)
        if session is None:
            raise RpcServiceError("PROJECT_NOT_OPEN", "The project is not open.")
        session.close()
        return {"project_id": project_id, "status": "closed"}

    def _datasets_import(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "resource_id",
                "source_path",
                "idempotency_key",
                "expected_version",
            },
            optional={"options"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        resource_id = _text(values["resource_id"], "resource_id")
        source_path = Path(_text(values["source_path"], "source_path"))
        key = _text(values["idempotency_key"], "idempotency_key")
        expected = _integer(values["expected_version"], "expected_version", minimum=0)
        options = _object(
            values.get("options"),
            required=set(),
            optional={"encoding", "delimiter", "decimal_mark", "header_row", "sheet"},
        )
        request_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "resource_id": resource_id,
                    "source_path_hash": hashlib.sha256(str(source_path).encode()).hexdigest(),
                    "expected_version": expected,
                    "options": options,
                },
            )
        )
        replay = session.domain.replay("datasets.import", key, request_hash)
        if replay is not None:
            return {**replay, "replayed": True}
        # Import is append-only. Rebase queued file selections onto the latest
        # committed revision so fast consecutive imports are not dropped as stale.
        commit_revision = session.domain.revision
        if expected > commit_revision:
            session.domain.require_revision(expected)
        task_id = self._begin_task(context, "import", label=f"导入 {source_path.name}")
        try:
            context.workers.submit(source_path.stat).result()
            context.tasks.transition(
                task_id, "running", progress={"completed": 0, "total": 1, "unit": "files"}
            )

            def response_factory(result: ImportCommitResult, revision: int) -> dict[str, Any]:
                return self._import_response(result, revision, task_id, requested_revision=expected)

            def before_commit() -> None:
                token = self._task_token(context.tasks, task_id)
                token.raise_if_cancelled()
                context.tasks.transition(
                    task_id,
                    "committing",
                    progress={"completed": 1, "total": 1, "unit": "files"},
                )

            outcome = session.imports.import_resource(
                ImportResource(resource_id=resource_id, path=source_path),
                encoding=_optional_text(options.get("encoding"), "encoding"),
                delimiter=_optional_text(options.get("delimiter"), "delimiter"),
                decimal_mark=_optional_text(options.get("decimal_mark"), "decimal_mark"),
                header_row=_optional_integer(options.get("header_row"), "header_row", minimum=0),
                sheet=_optional_text(options.get("sheet"), "sheet"),
                expected_revision=commit_revision,
                idempotency_key=key,
                request_hash=request_hash,
                response_factory=response_factory,
                before_commit=before_commit,
            )
            if isinstance(outcome, (Clarification, Rejection)):
                context.tasks.fail(
                    task_id,
                    code=outcome.code,
                    message=(
                        outcome.question if isinstance(outcome, Clarification) else outcome.message
                    ),
                )
                return cast(
                    RpcJsonValue,
                    {
                        **outcome.model_dump(mode="json"),
                        "task_id": task_id,
                        "project_version": commit_revision,
                    },
                )
            context.tasks.transition(
                task_id,
                "succeeded",
                progress={"completed": 1, "total": 1, "unit": "files"},
            )
            return cast(
                RpcJsonValue,
                self._import_response(
                    outcome,
                    commit_revision + 1,
                    task_id,
                    requested_revision=expected,
                ),
            )
        except TaskControlError:
            self._cancel_task(context.tasks, task_id)
            raise
        except Exception as error:
            self._fail_task(context.tasks, task_id, error)
            raise

    def _datasets_list(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return {
            "project_id": session.project_id,
            "project_version": session.domain.revision,
            "datasets": [
                self._dataset_summary(record) for record in session.store.list_source_datasets()
            ],
        }

    def _datasets_describe(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "source_dataset_id", "source_version"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        source = session.domain.source_record(
            _text(values["source_dataset_id"], "source_dataset_id"),
            _integer(values["source_version"], "source_version", minimum=1),
        )
        record = next(
            (
                item
                for item in session.store.list_source_datasets()
                if item.source_dataset.source_dataset_id == source.source_dataset_id
                and item.source_dataset.source_version == source.source_version
            ),
            source,
        )
        resolved = session.domain.resolve_source(source)
        summary = self._dataset_summary(record)
        summary["sample_rows"] = [
            [_preview_scalar(value) for value in row] for row in resolved.rows[:5]
        ]
        return {
            "project_id": session.project_id,
            "project_version": session.domain.revision,
            "dataset": summary,
        }

    def _session(self, project_id: str) -> ProjectSession:
        session = self._sessions.get(project_id)
        if session is None:
            raise RpcServiceError("PROJECT_NOT_OPEN", "The project is not open.")
        return session

    def _project_summary(
        self,
        project_id: str,
        display_name: str | None,
        last_opened_at: str,
        *,
        project_version: int,
    ) -> dict[str, RpcJsonValue]:
        return {
            "project_id": project_id,
            "resource_id": "resource:project." + project_id.removeprefix("project:"),
            "display_name": display_name,
            "last_opened_at": last_opened_at,
            "is_open": project_id in self._sessions,
            "project_version": project_version,
        }

    def _session_summary(
        self, session: ProjectSession, *, replayed: bool
    ) -> dict[str, RpcJsonValue]:
        return {
            "project_id": session.project_id,
            "resource_id": "resource:project." + session.project_id.removeprefix("project:"),
            "project_version": session.domain.revision,
            "dataset_count": len(session.store.list_source_datasets()),
            "plot_count": len(session.engine.documents.list_latest()),
            "status": "open",
            "replayed": replayed,
        }

    def _dataset_summary(
        self, record: SourceDataset | SourceDatasetRecord
    ) -> dict[str, RpcJsonValue]:
        if isinstance(record, SourceDatasetRecord):
            source = record.source_dataset
            identity: dict[str, RpcJsonValue] = {
                "display_name": record.display_name or source.source_dataset_id,
                "source_file_name": record.source_file_name,
                "sheet_name": record.sheet_name,
                "source_block": record.source_block,
                "instrument_metadata": cast(dict[str, RpcJsonValue], record.instrument_metadata),
            }
        else:
            source = record
            identity = {"display_name": source.source_dataset_id}
        return {
            **identity,
            "source_dataset_id": source.source_dataset_id,
            "source_version": source.source_version,
            "content_hash": source.content_hash,
            "row_count": source.data_ref.row_count,
            "field_count": len(source.field_schema),
            "fields": [
                {
                    "field_id": field.field_id,
                    "name": field.name,
                    "logical_type": field.logical_type,
                    "physical_type": field.physical_type,
                    "unit": field.unit.model_dump(mode="json"),
                }
                for field in source.field_schema
            ],
            "quality": source.quality.model_dump(mode="json"),
            "source_coordinate_kinds": list(
                dict.fromkeys(item.kind for item in source.source_coordinate_samples)
            ),
        }

    def _import_response(
        self,
        result: ImportCommitResult,
        revision: int,
        task_id: str,
        *,
        requested_revision: int | None = None,
    ) -> dict[str, RpcJsonValue]:
        return {
            "kind": "committed",
            "task_id": task_id,
            "session_id": result.session_id,
            "project_version": revision,
            "rebased": requested_revision is not None and requested_revision != revision - 1,
            "datasets": [self._dataset_summary(record) for record in result.datasets],
            "replayed": False,
        }

    @staticmethod
    def _begin_task(context: RpcContext, prefix: str, *, label: str | None = None) -> str:
        suffix = hashlib.sha256(
            f"{prefix}\0{context.request_id}\0{uuid.uuid4().hex}".encode()
        ).hexdigest()[:24]
        task_id = f"task:{suffix}"
        context.tasks.register(task_id, kind=prefix, label=label)
        context.tasks.transition(task_id, "preparing")
        return task_id

    @staticmethod
    def _task_token(tasks: TaskRegistry, task_id: str):  # type: ignore[no-untyped-def]
        return tasks.token(task_id)

    @staticmethod
    def _cancel_task(tasks: TaskRegistry, task_id: str) -> None:
        state = tasks.state(task_id)
        if state in {"queued", "preparing", "running"}:
            tasks.cancel(task_id)
            state = tasks.state(task_id)
        if state == "cancelling":
            tasks.transition(task_id, "cancelled")

    @staticmethod
    def _fail_task(tasks: TaskRegistry, task_id: str, error: Exception) -> None:
        state = tasks.state(task_id)
        if state in {"preparing", "running", "committing"}:
            code = getattr(error, "code", "TASK_FAILED")
            message = getattr(error, "message", "任务未完成，请检查输入后重试。")
            if not isinstance(code, str) or not code or len(code) > 64:
                code = "TASK_FAILED"
            if not isinstance(message, str) or not message or len(message) > 240:
                message = "任务未完成，请检查输入后重试。"
            tasks.fail(task_id, code=code, message=message)


@dataclass(frozen=True, slots=True)
class _DesktopEngineActionExecutor:
    session: ProjectSession

    def execute_action(
        self,
        action: PlotEngineAction,
        *,
        expected_project_revision: int,
    ) -> int:
        self.session.engine.execute_action(
            action,
            expected_project_revision=expected_project_revision,
        )
        return self.session.domain.revision


@dataclass(frozen=True, slots=True)
class _DomainSourceResolver:
    domain: ProjectDomainRepository

    def resolve(self, source_dataset: SourceDataset) -> ResolvedSourceTable:
        return self.domain.resolve_source(source_dataset)


def _object(
    value: RpcJsonValue | None,
    *,
    required: set[str],
    optional: AbstractSet[str] | None = frozenset(),
) -> dict[str, RpcJsonValue]:
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise RpcServiceError("INVALID_PARAMS", "The request parameters were invalid.")
    keys = set(value)
    if not required.issubset(keys) or (optional is not None and keys - required - set(optional)):
        raise RpcServiceError("INVALID_PARAMS", "The request parameters were invalid.")
    return value


def _text(value: RpcJsonValue | None, name: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RpcServiceError("INVALID_PARAMS", f"{name} was invalid.")
    return value


def _optional_text(value: RpcJsonValue | None, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _integer(value: RpcJsonValue | None, name: str, *, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise RpcServiceError("INVALID_PARAMS", f"{name} was invalid.")
    return value


def _optional_integer(value: RpcJsonValue | None, name: str, *, minimum: int) -> int | None:
    return None if value is None else _integer(value, name, minimum=minimum)
