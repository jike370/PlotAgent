"""Lifecycle-owned desktop application services for the local plotting slice."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import shutil
import uuid
from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from plotagent import __version__
from plotagent.agent import (
    AgentCreatePlot,
    AgentFieldBinding,
    BoundEnginePlan,
    BundledEngineAgentBinder,
    EngineAgentOrchestrator,
    EngineAgentPlan,
    EngineAgentPlanRepository,
    EngineTaskExecutionError,
    EngineTaskPlanSnapshot,
    PersistentEngineTaskOrchestrator,
)
from plotagent.agent.audit import InMemoryAuditSink
from plotagent.agent.context import (
    AuthoritativeField,
    AuthoritativeProjectContext,
    AuthoritativeSampleRow,
    ContextBuilder,
    ContextBuildRequest,
    ConversationState,
    ConversationStateReducer,
    DisclosureGrant,
)
from plotagent.agent.project_context import ProjectContextService
from plotagent.agent.providers import (
    BuiltinProviderConfig,
    CustomProviderConfig,
    ModelProvider,
    create_provider,
)
from plotagent.contracts.agent_context import (
    ChartCapabilities,
    ContextFieldSummary,
    ContextObjectRef,
    DisclosureCategory,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.datasets import SourceDataset
from plotagent.contracts.project_context import ContextFieldBinding, ProjectContextSnapshot
from plotagent.desktop_core.engine_session import DesktopEngineSession
from plotagent.desktop_core.protocol import JsonValue as RpcJsonValue
from plotagent.desktop_core.services import RpcContext, RpcServiceError, ServiceRegistry
from plotagent.desktop_core.tasks import (
    BoundedWorkerExecutor,
    TaskControlError,
    TaskRegistry,
)
from plotagent.engine import (
    CreatePlot,
    EngineDataRef,
    EngineVersionConflict,
    FieldBinding,
    PlotEngineAction,
)
from plotagent.engine.backends.origin import preflight_origin
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.importing.models import Clarification, Rejection
from plotagent.security import CredentialStore, NetworkMode, create_credential_store
from plotagent.storage import (
    AgentRuntimeRepository,
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
from plotagent.storage.schema import migrate_catalog_v1_to_v2

type ProviderFactory = Callable[[NetworkMode, Mapping[str, RpcJsonValue]], ModelProvider]
type ProductHandler = Callable[[RpcContext, RpcJsonValue | None], RpcJsonValue]

_PROVIDER_SETTING_KEY = "agent.provider.active"
_CUSTOM_PROVIDER_CONFIG_ID = "custom.default"


@dataclass(slots=True)
class ProjectSession:
    store: ProjectStore
    domain: ProjectDomainRepository
    imports: ProjectImportService
    agent_runtime: AgentRuntimeRepository
    engine: DesktopEngineSession
    engine_agent_plans: EngineAgentPlanRepository

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
        provider_factory: ProviderFactory | None = None,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self.root = self._default_root() if root is None else Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.projects_root = self.root / "projects"
        self.projects_root.mkdir(exist_ok=True)
        catalog_path = self.root / "catalog.sqlite3"
        if catalog_path.is_file():
            try:
                self.catalog = Catalog.open(catalog_path)
            except StorageProblem as error:
                if str(error.code) != "SCHEMA_VERSION_UNSUPPORTED":
                    raise
                migrate_catalog_v1_to_v2(catalog_path)
                self.catalog = Catalog.open(catalog_path)
        else:
            self.catalog = Catalog.create(catalog_path)
        self._sessions: dict[str, ProjectSession] = {}
        self._packages = ProjectPackageService(self.catalog, self.projects_root)
        self._credential_store = credential_store or create_credential_store()
        self._provider_factory = provider_factory or self._create_production_provider
        self._production_provider_cache: dict[tuple[str, ...], ModelProvider] = {}
        self._closed = False

    @staticmethod
    def _default_root() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).resolve() / "PlotAgent"
        return Path.home().resolve() / "AppData" / "Local" / "PlotAgent"

    def _create_production_provider(
        self, mode: NetworkMode, params: Mapping[str, RpcJsonValue]
    ) -> ModelProvider:
        values = dict(params)
        if mode is NetworkMode.BUILTIN_PROXY:
            config_values = _object(
                cast(RpcJsonValue, values),
                required={
                    "provider_config_id",
                    "endpoint_origin",
                    "model_profile_id",
                    "model_id",
                    "deployment_id",
                },
                optional={"protocol_version"},
            )
            builtin_config = BuiltinProviderConfig(
                provider_config_id=_text(config_values["provider_config_id"], "provider_config_id"),
                endpoint_origin=_text(config_values["endpoint_origin"], "endpoint_origin"),
                model_profile_id=_text(config_values["model_profile_id"], "model_profile_id"),
                model_id=_text(config_values["model_id"], "model_id"),
                deployment_id=_text(config_values["deployment_id"], "deployment_id"),
                protocol_version=_optional_text(
                    config_values.get("protocol_version"), "protocol_version"
                )
                or "1",
            )
            return create_provider(
                mode,
                credential_store=self._credential_store,
                app_build=__version__,
                builtin_config=builtin_config,
            )
        if mode is NetworkMode.CUSTOM_PROVIDER:
            config_values = _object(
                cast(RpcJsonValue, values),
                required={"provider_config_id", "base_url", "model_id"},
                optional={"model_profile", "retention_acknowledged"},
            )
            custom_config = CustomProviderConfig(
                provider_config_id=_text(config_values["provider_config_id"], "provider_config_id"),
                base_url=_text(config_values["base_url"], "base_url"),
                model_id=_text(config_values["model_id"], "model_id"),
                model_profile=_optional_text(config_values.get("model_profile"), "model_profile")
                or "custom-fixed",
            )
            cache_key = (
                mode.value,
                custom_config.provider_config_id,
                custom_config.base_url,
                custom_config.model_id,
                custom_config.model_profile,
            )
            cached = self._production_provider_cache.get(cache_key)
            if cached is not None:
                return cached
            provider = create_provider(
                mode,
                credential_store=self._credential_store,
                app_build=__version__,
                custom_config=custom_config,
            )
            self._production_provider_cache[cache_key] = provider
            return provider
        return create_provider(
            mode,
            credential_store=self._credential_store,
            app_build=__version__,
        )

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
            "agent.engine.plans.create": self._engine_agent_plan_create,
            "agent.engine.plans.create_batch": self._engine_agent_batch_plan_create,
            "agent.engine.plans.get": self._engine_agent_plan_get,
            "agent.engine.plans.list": self._engine_agent_plan_list,
            "agent.engine.plans.confirm": self._engine_agent_plan_confirm,
            "agent.engine.plans.cancel": self._engine_agent_plan_cancel,
            "agent.engine.plans.run": self._engine_agent_plan_run,
            "agent.engine.plans.resume": self._engine_agent_plan_run,
            "provider.status": self._provider_status,
            "provider.configure": self._provider_configure,
            "provider.clear": self._provider_clear,
            "origin.status": self._origin_status,
            "agent.engine.decide": self._agent_engine_decide,
        }
        for method, handler in handlers.items():
            registry.register(method, self._guard(handler))

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

    def _engine_plots_list(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
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
            payload = session.engine.export(
                cast(dict[str, object], action),
                destination,
                origin_install_dir=install_dir,
            )
            artifact = cast(dict[str, object], payload.pop("artifact"))
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

    def _engine_plots_get(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
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

    def _engine_agent_plan_create(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "context_snapshot_id", "proposal"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        snapshot = session.agent_runtime.get_context_snapshot(
            _text(values["context_snapshot_id"], "context_snapshot_id")
        )
        if snapshot.project_id != session.project_id:
            raise RpcServiceError("INVALID_PARAMS", "The context belongs to another project.")
        session.domain.require_revision(snapshot.project_revision)
        proposal = EngineAgentPlan.model_validate(values["proposal"])
        target_profiles = self._engine_agent_target_profiles(session, snapshot)
        bound = BundledEngineAgentBinder(session.engine.catalog).bind(
            proposal,
            snapshot,
            target_profiles=target_profiles,
        )
        stored = session.engine_agent_plans.create(proposal, bound)
        return self._engine_agent_plan_payload(session, stored)

    def _engine_agent_plan_get(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        stored = session.engine_agent_plans.get(_text(values["plan_id"], "plan_id"))
        return self._engine_agent_plan_payload(session, stored)

    def _engine_agent_batch_plan_create(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        """Persist a batch as ordinary, independently resumable create_plot actions."""

        values = _object(
            params,
            required={"project_id", "profile_id", "datasets", "expected_project_version"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        expected = _integer(
            values["expected_project_version"], "expected_project_version", minimum=0
        )
        session.domain.require_revision(expected)
        profile_id = _text(values["profile_id"], "profile_id")
        session.engine.catalog.get(profile_id)
        datasets_value = values["datasets"]
        if not isinstance(datasets_value, list) or not 1 <= len(datasets_value) <= 64:
            raise RpcServiceError(
                "INVALID_PARAMS", "A batch plan requires between 1 and 64 datasets."
            )

        batch_token = uuid.uuid4().hex
        plan_id = f"plan:batch.{batch_token}"
        proposals: list[AgentCreatePlot] = []
        actions: list[PlotEngineAction] = []
        seen_sources: set[tuple[str, int]] = set()
        for index, item_value in enumerate(datasets_value, start=1):
            item = _object(
                item_value,
                required={"dataset_id", "version", "content_hash", "bindings"},
            )
            dataset_id = _text(item["dataset_id"], "dataset_id")
            version = _integer(item["version"], "version", minimum=1)
            source_key = (dataset_id, version)
            if source_key in seen_sources:
                raise RpcServiceError("INVALID_PARAMS", "Batch datasets must be unique.")
            seen_sources.add(source_key)
            source = session.domain.source_record(dataset_id, version)
            content_hash = _text(item["content_hash"], "content_hash")
            if source.content_hash != content_hash:
                raise RpcServiceError(
                    "SOURCE_VERSION_CONFLICT",
                    "A batch dataset changed after the mapping was confirmed.",
                )
            binding_values = item["bindings"]
            if not isinstance(binding_values, dict) or not binding_values:
                raise RpcServiceError("INVALID_PARAMS", "Each batch dataset needs bindings.")
            bindings = tuple(
                FieldBinding(role=_text(role, "role"), field_id=_text(field_id, "field_id"))
                for role, field_id in sorted(binding_values.items())
            )
            action_id = f"action:batch.{batch_token}.{index}"
            plot_id = f"plot:batch.{batch_token}.{index}"
            action = CreatePlot(
                action_id=action_id,
                plot_id=plot_id,
                profile_id=profile_id,
                data=EngineDataRef(
                    kind="source",
                    dataset_id=dataset_id,
                    version=version,
                    content_hash=content_hash,
                ),
                bindings=bindings,
            )
            session.engine.catalog.validate_create(action)
            proposals.append(
                AgentCreatePlot(
                    action_id=action_id,
                    plot_alias=f"plot_{index}",
                    profile_id=profile_id,
                    source_alias=f"source_{index}",
                    bindings=tuple(
                        AgentFieldBinding(role=binding.role, field_alias=f"field_{position}")
                        for position, binding in enumerate(bindings, start=1)
                    ),
                )
            )
            actions.append(action)

        proposal = EngineAgentPlan(
            plan_id=plan_id,
            target_alias="batch_plots",
            actions=tuple(proposals),
        )
        stored = session.engine_agent_plans.create(
            proposal,
            BoundEnginePlan(
                plan_id=plan_id,
                expected_project_revision=expected,
                actions=tuple(actions),
            ),
        )
        return self._engine_agent_plan_payload(session, stored)

    def _engine_agent_plan_list(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return cast(
            RpcJsonValue,
            {
                "project_id": session.project_id,
                "project_version": session.domain.revision,
                "plans": tuple(
                    self._engine_agent_plan_payload(session, stored)
                    for stored in session.engine_agent_plans.list_all()
                ),
            },
        )

    def _engine_agent_plan_confirm(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        stored = session.engine_agent_plans.confirm(_text(values["plan_id"], "plan_id"))
        return self._engine_agent_plan_payload(session, stored)

    def _engine_agent_plan_cancel(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        plan_id = _text(values["plan_id"], "plan_id")
        stored = session.engine_agent_plans.cancel(plan_id)
        return self._engine_agent_plan_payload(session, stored)

    def _engine_agent_plan_run(
        self, context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        plan_id = _text(values["plan_id"], "plan_id")
        task_id = self._begin_task(context, "engine-agent-plan", label="执行绘图计划")
        try:
            context.tasks.transition(task_id, "running")
            stored = PersistentEngineTaskOrchestrator(
                session.engine_agent_plans,
                _DesktopEngineActionExecutor(session),
            ).run(plan_id)
            context.tasks.transition(task_id, "committing")
            context.tasks.transition(
                task_id,
                (
                    "succeeded"
                    if stored.state == "succeeded"
                    else "partially_succeeded"
                    if stored.next_action_index > 0
                    else "failed"
                ),
            )
            payload = cast(
                dict[str, RpcJsonValue],
                self._engine_agent_plan_payload(session, stored),
            )
            return {
                "task_id": task_id,
                **payload,
            }
        except EngineTaskExecutionError as error:
            self._fail_task(context.tasks, task_id, error)
            raise RpcServiceError(error.code, str(error)) from None
        except Exception as error:
            self._fail_task(context.tasks, task_id, error)
            raise

    @staticmethod
    def _engine_agent_target_profiles(
        session: ProjectSession,
        snapshot: ProjectContextSnapshot,
    ) -> dict[str, str]:
        objects = (
            snapshot.known_objects
            + snapshot.recent_result_objects
            + (snapshot.conversation_state.current_target,)
        )
        profiles: dict[str, str] = {}
        for item in objects:
            if item.object_type != "plot":
                continue
            try:
                stored = session.engine.documents.get(item.object_id, item.object_version)
            except KeyError:
                continue
            profiles[item.object_alias] = stored.document.profile_id
        return profiles

    @staticmethod
    def _engine_agent_plan_payload(
        session: ProjectSession,
        snapshot: EngineTaskPlanSnapshot,
    ) -> RpcJsonValue:
        return cast(
            RpcJsonValue,
            {
                "project_id": session.project_id,
                "project_version": session.domain.revision,
                "plan_id": snapshot.proposal.plan_id,
                "state": snapshot.state,
                "confirmation_state": snapshot.confirmation_state,
                "next_action_index": snapshot.next_action_index,
                "current_project_revision": snapshot.current_project_revision,
                "error_code": snapshot.error_code,
                "proposal": snapshot.proposal.model_dump(mode="json"),
                "bound_plan": snapshot.bound.model_dump(mode="json"),
                "created_at": snapshot.created_at,
                "updated_at": snapshot.updated_at,
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
        # Constructing the adapter performs the same endpoint-origin validation used
        # at request time, before either the non-secret config or credential is saved.
        api_key = _optional_text(values.get("api_key"), "api_key")
        if api_key is not None:
            self._credential_store.set_custom_api_key(config_id, api_key)
            self._production_provider_cache.clear()
        if self._credential_store.get_custom_api_key(config_id) is None:
            raise RpcServiceError(
                "PROVIDER_NOT_CONFIGURED", "A custom provider API key is required."
            )
        try:
            self._create_production_provider(
                NetworkMode.CUSTOM_PROVIDER,
                {
                    "provider_config_id": config["provider_config_id"],
                    "base_url": config["base_url"],
                    "model_id": config["model_id"],
                    "model_profile": config["model_profile"],
                },
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
        self._production_provider_cache.clear()
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
        session = ProjectSession(
            store=store,
            domain=ProjectDomainRepository(store),
            imports=ProjectImportService(store),
            agent_runtime=AgentRuntimeRepository(store),
            engine=DesktopEngineSession.open(store),
            engine_agent_plans=EngineAgentPlanRepository(store),
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
                header_row=_optional_integer(options.get("header_row"), "header_row", minimum=1),
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
                        outcome.question
                        if isinstance(outcome, Clarification)
                        else outcome.message
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
        return {
            "project_id": session.project_id,
            "project_version": session.domain.revision,
            "dataset": self._dataset_summary(
                next(
                    (
                        record
                        for record in session.store.list_source_datasets()
                        if record.source_dataset.source_dataset_id == source.source_dataset_id
                        and record.source_dataset.source_version == source.source_version
                    ),
                    source,
                )
            ),
        }

    def _agent_engine_decide(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        """Run the bundled model against the public engine action vocabulary."""

        values = _object(
            params,
            required={
                "project_id",
                "source_dataset_id",
                "source_version",
                "user_instruction",
                "client_model_run_id",
                "expected_version",
            },
            optional={
                "conversation_id",
                "selected_profile_id",
                "locale",
                "network_mode",
                "provider",
                "retention_acknowledged",
                "selected_source_datasets",
                "target_plot_id",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        expected = _integer(values["expected_version"], "expected_version", minimum=0)
        session.domain.require_revision(expected)
        source = session.domain.source_record(
            _text(values["source_dataset_id"], "source_dataset_id"),
            _integer(values["source_version"], "source_version", minimum=1),
        )
        source_table = session.domain.resolve_source(source)
        selected_sources: list[SourceDataset] = [source]
        selected_value = values.get("selected_source_datasets")
        if selected_value is not None:
            if not isinstance(selected_value, list) or not 1 <= len(selected_value) <= 8:
                raise RpcServiceError(
                    "INVALID_PARAMS", "Selected datasets must contain one to eight items."
                )
            selected_sources = []
            selected_keys: set[tuple[str, int]] = set()
            for item in selected_value:
                selected_item = _object(
                    item,
                    required={"source_dataset_id", "source_version"},
                )
                selected_source = session.domain.source_record(
                    _text(selected_item["source_dataset_id"], "source_dataset_id"),
                    _integer(
                        selected_item["source_version"],
                        "source_version",
                        minimum=1,
                    ),
                )
                selected_key = (
                    selected_source.source_dataset_id,
                    selected_source.source_version,
                )
                if selected_key in selected_keys:
                    raise RpcServiceError(
                        "INVALID_PARAMS", "Selected datasets must be unique."
                    )
                selected_keys.add(selected_key)
                selected_sources.append(selected_source)
            primary_key = (source.source_dataset_id, source.source_version)
            if primary_key not in selected_keys:
                raise RpcServiceError(
                    "INVALID_PARAMS", "The active dataset must be selected."
                )
            selected_sources.sort(key=lambda item: (item != source, item.source_dataset_id))

        source_records = {
            (
                record.source_dataset.source_dataset_id,
                record.source_dataset.source_version,
            ): record
            for record in session.store.list_source_datasets()
        }
        multi_source = len(selected_sources) > 1
        source_refs = tuple(
            ContextObjectRef(
                object_alias=("active_data" if not multi_source else f"data_{index}"),
                object_id=item.source_dataset_id,
                object_version=item.source_version,
                object_type="source_dataset",
                content_hash=item.content_hash,
            )
            for index, item in enumerate(selected_sources, start=1)
        )
        source_ref = source_refs[0]
        target_plot_id = _optional_text(values.get("target_plot_id"), "target_plot_id")
        target_profiles: dict[str, str] = {}
        if target_plot_id is None:
            target = source_ref.model_copy(update={"object_alias": "active_target"})
            selected_objects = source_refs[1:]
        else:
            stored = session.engine.documents.get(target_plot_id)
            target = ContextObjectRef(
                object_alias="active_target",
                object_id=stored.document.plot_id,
                object_version=stored.document.plot_version,
                object_type="plot",
                content_hash=stored.content_hash,
            )
            selected_objects = source_refs
            target_profiles["active_target"] = stored.document.profile_id

        selected_profile = _optional_text(
            values.get("selected_profile_id"), "selected_profile_id"
        )
        enabled_profiles: tuple[str, ...]
        if target_plot_id is not None:
            enabled_profiles = (target_profiles["active_target"],)
            if selected_profile is not None and selected_profile not in enabled_profiles:
                raise RpcServiceError(
                    "INVALID_PARAMS", "The selected profile differs from the target plot."
                )
        elif selected_profile is not None:
            session.engine.catalog.get(selected_profile)
            enabled_profiles = (selected_profile,)
        else:
            enabled_profiles = tuple(
                profile.profile_id for profile in session.engine.catalog.profiles()
            )

        conversation_id = _optional_text(values.get("conversation_id"), "conversation_id")
        if conversation_id is None:
            conversation_id = self._default_conversation_id(session.project_id)
        persisted = session.agent_runtime.get_conversation_state(conversation_id)
        if persisted is None:
            conversation = ConversationState(
                current_target=target,
                selected_objects=selected_objects,
            )
            session.agent_runtime.save_conversation_state(
                conversation_id,
                conversation.project(),
                expected_state_version=None,
            )
        else:
            conversation = ConversationState.from_projection(persisted)
            if (
                conversation.current_target != target
                or conversation.selected_objects != selected_objects
            ):
                conversation = ConversationStateReducer().select_target(
                    conversation,
                    target,
                    selected_objects=selected_objects,
                )
                session.agent_runtime.save_conversation_state(
                    conversation_id,
                    conversation.project(),
                    expected_state_version=persisted.state_version,
                )

        all_fields: list[AuthoritativeField] = []
        all_aliases: list[tuple[str, str, SourceDataset]] = []
        all_rows: list[AuthoritativeSampleRow] = []
        for source_index, selected_source in enumerate(selected_sources, start=1):
            table = (
                source_table
                if selected_source == source
                else session.domain.resolve_source(selected_source)
            )
            record = source_records.get(
                (selected_source.source_dataset_id, selected_source.source_version)
            )
            display_name = (
                record.display_name
                if record is not None and record.display_name
                else selected_source.source_dataset_id
            )
            fields, alias_to_field = self._agent_fields(
                selected_source,
                table.rows,
                alias_prefix=f"data_{source_index}_" if multi_source else "",
                display_prefix=f"{display_name} / " if multi_source else "",
            )
            all_fields.extend(fields)
            all_aliases.extend(
                (alias, field_id, selected_source)
                for alias, field_id in alias_to_field.items()
            )
            if not multi_source:
                all_rows.extend(
                    AuthoritativeSampleRow(
                        row_id=f"row:context.{source_index}.{row_index + 1}",
                        values={
                            field.field_id: table.rows[row_index][field_index]
                            for field_index, field in enumerate(fields)
                        },
                    )
                    for row_index in range(len(table.rows))
                )
        fields = tuple(all_fields)
        known_objects = (target, *selected_objects)
        project_context = ProjectContextService().build_snapshot(
            project_id=session.project_id,
            project_revision=expected,
            conversation_id=conversation_id,
            conversation_state=conversation.project(),
            known_objects=known_objects,
            field_bindings=tuple(
                ContextFieldBinding(
                    field_alias=alias,
                    field_id=field_id,
                    source_dataset_id=field_source.source_dataset_id,
                    source_version=field_source.source_version,
                )
                for alias, field_id, field_source in all_aliases
            ),
        )
        session.agent_runtime.save_context_snapshot(project_context)
        sample_rows = tuple(all_rows)

        saved_provider = self._saved_provider_config()
        mode_value = values.get("network_mode")
        if mode_value is None:
            mode = (
                NetworkMode.CUSTOM_PROVIDER
                if saved_provider is not None
                else NetworkMode.LOCAL_ONLY
            )
        else:
            try:
                mode = NetworkMode(_text(mode_value, "network_mode"))
            except ValueError:
                raise RpcServiceError("INVALID_PARAMS", "The network mode was invalid.") from None
        if values.get("provider") is None:
            provider_values = saved_provider or {}
        else:
            provider_values = _object(values["provider"], required=set(), optional=None)
        try:
            provider = self._provider_factory(mode, provider_values)
            identity = provider.identity
        except Exception:
            return _agent_failure_payload("PROVIDER_NOT_CONFIGURED")
        if identity.provider_type == "local_only":
            return _agent_failure_payload("PROVIDER_NOT_CONFIGURED")

        categories: frozenset[DisclosureCategory] = frozenset(
            {
                "user_instruction",
                "field_metadata",
                "statistics",
                "sample",
                "chart_capabilities",
            }
        )
        context_request = ContextBuildRequest(
            user_instruction=_text(values["user_instruction"], "user_instruction"),
            locale=_optional_text(values.get("locale"), "locale") or "zh-CN",
            project=AuthoritativeProjectContext(
                target=target,
                dataset_content_hash=canonical_hash(
                    cast(JsonValue, [item.content_hash for item in selected_sources])
                ),
                fields=fields,
                sample_rows=sample_rows,
                selected_objects=selected_objects,
                explicit_field_aliases=tuple(alias for alias, _, _ in all_aliases),
            ),
            conversation_state=conversation,
            chart_capabilities=ChartCapabilities(
                capability_version="agent-native-engine-v1",
                allowed_chart_type_ids=cast(Any, enabled_profiles),
                allowed_action_types=(
                    "create_plot",
                    "bind_fields",
                    "set_title",
                    "set_axis",
                    "set_series_style",
                    "set_legend",
                    "set_chart_parameter",
                    "add_annotation",
                    "export_plot",
                ),
                export_formats=("png", "svg", "opju"),
            ),
            disclosure_grant=DisclosureGrant(
                provider_type=identity.provider_type,
                provider_config_id=identity.provider_config_id,
                retention_disclosure_version="retention-v1",
                retention_acknowledged=bool(values.get("retention_acknowledged", True)),
                allowed_categories=categories,
            ),
        )
        result = asyncio.run(
            EngineAgentOrchestrator(
                network_mode=mode,
                context_builder=ContextBuilder(),
                provider=provider,
                binder=BundledEngineAgentBinder(session.engine.catalog),
                codec=session.engine.codec,
                audit_sink=InMemoryAuditSink(),
            ).run(
                client_model_run_id=_text(
                    values["client_model_run_id"], "client_model_run_id"
                ),
                context_request=context_request,
                project_context=project_context,
                target_profiles=target_profiles,
            )
        )
        if not result.accepted or result.decision is None:
            return _agent_failure_payload(result.error_code)
        decision = result.decision
        question_ids = (
            tuple(question.question_key for question in decision.questions)
            if decision.decision_type == "needs_input"
            else ()
        )
        latest = session.agent_runtime.get_conversation_state(conversation_id)
        if latest is None:
            raise RpcServiceError("AGENT_CONTEXT_MISSING", "The Agent context is unavailable.")
        updated = ConversationStateReducer().record_decision(
            ConversationState.from_projection(latest),
            decision_kind=decision.decision_type,
            unresolved_question_ids=question_ids,
        )
        session.agent_runtime.save_conversation_state(
            conversation_id,
            updated.project(),
            expected_state_version=latest.state_version,
            context_hash=project_context.snapshot_hash,
        )
        payload: dict[str, RpcJsonValue] = {
            "accepted": True,
            "conversation_id": conversation_id,
            "context_snapshot_id": project_context.snapshot_id,
            "context_hash": project_context.snapshot_hash,
            "decision": cast(RpcJsonValue, decision.model_dump(mode="json")),
        }
        if isinstance(decision, EngineAgentPlan):
            if result.bound_plan is None:
                raise RpcServiceError("ENGINE_PLAN_INVALID", "The engine plan was not bound.")
            stored_plan = session.engine_agent_plans.create(
                decision,
                result.bound_plan,
                confirmation_required=True,
            )
            payload["task_plan"] = self._engine_agent_plan_payload(session, stored_plan)
        return payload

    def _agent_fields(
        self,
        source: SourceDataset,
        rows: tuple[tuple[Any, ...], ...],
        *,
        alias_prefix: str = "",
        display_prefix: str = "",
    ) -> tuple[tuple[AuthoritativeField, ...], dict[str, str]]:
        aliases: dict[str, str] = {}
        fields: list[AuthoritativeField] = []
        for index, field in enumerate(source.field_schema):
            base_alias = (
                "x_field" if index == 0 else "y_field" if index == 1 else f"field_{index}"
            )
            alias = alias_prefix + base_alias
            aliases[alias] = field.field_id
            finite = [
                float(row[index])
                for row in rows
                if isinstance(row[index], (int, float))
                and not isinstance(row[index], bool)
                and math.isfinite(float(row[index]))
            ]
            fields.append(
                AuthoritativeField(
                    field_alias=cast(Any, alias),
                    field_id=field.field_id,
                    name=display_prefix + field.name,
                    logical_type=field.logical_type,
                    unit_text=field.unit.source_text,
                    semantic_role=_semantic_role_from_field_name(field.name),
                    summary=ContextFieldSummary(
                        valid_count=len(finite),
                        missing_count=sum(row[index] is None for row in rows),
                        numeric_minimum=min(finite) if finite else None,
                        numeric_maximum=max(finite) if finite else None,
                    ),
                )
            )
        return tuple(fields), aliases

    def _session(self, project_id: str) -> ProjectSession:
        session = self._sessions.get(project_id)
        if session is None:
            raise RpcServiceError("PROJECT_NOT_OPEN", "The project is not open.")
        return session

    @staticmethod
    def _default_conversation_id(project_id: str) -> str:
        suffix = project_id.removeprefix("project:")
        return f"conversation:{suffix}.main"

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


def _agent_failure_payload(error_code: str | None) -> dict[str, RpcJsonValue]:
    code = error_code or "PROVIDER_CONNECTION_FAILED"
    retryable = code in {
        "PROVIDER_CONNECTION_FAILED",
        "REQUEST_CANCELLED",
        "REQUEST_TIMEOUT",
    }
    return {
        "accepted": False,
        "error": {
            "code": code,
            "message": "The Agent decision was not accepted.",
            "side_effects_committed": False,
            "retry": {
                "allowed": retryable,
                "automatic": False,
                "requires_new_client_model_run_id": retryable,
            },
        },
    }


def _semantic_role_from_field_name(name: str) -> str | None:
    """Expose an exact scientific role only when the source header declares it."""

    normalized = name.strip().casefold().replace("-", "_").replace(" ", "_").replace(".", "_")
    normalized = normalized.removeprefix("field:")
    aliases = {
        "p_value": "pvalue",
        "p_val": "pvalue",
        "q_value": "qvalue",
        "q_val": "qvalue",
        "log2fc": "log2fc",
        "fold_change": "log2fc",
    }
    normalized = aliases.get(normalized, normalized)
    declared_roles = {
        role
        for profile in ENGINE_PROFILES
        for role in (*profile.required_roles, *profile.optional_roles)
    }
    if normalized in declared_roles or normalized.startswith("series_"):
        return normalized
    return None


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
