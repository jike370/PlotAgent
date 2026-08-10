"""Lifecycle-owned desktop application services for the local plotting slice."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import os
import shutil
import uuid
from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import TypeAdapter, ValidationError

from plotagent import __version__
from plotagent.agent import (
    BundledEngineAgentBinder,
    EngineAgentPlan,
    EngineAgentPlanRepository,
    EngineTaskExecutionError,
    EngineTaskPlanSnapshot,
    PersistentEngineTaskOrchestrator,
    SingleAgentOrchestrator,
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
from plotagent.agent.task_orchestrator import (
    PersistentTaskOrchestrator,
    TaskExecutionError,
)
from plotagent.agent.task_plans import TaskPlanCompiler
from plotagent.agent.validation import DecisionValidator, ValidationAuthority
from plotagent.batch import BatchService
from plotagent.batch.models import (
    BatchSubmission,
    BatchSubmissionRequest,
    BatchTaskRecord,
    BatchTemplate,
    BatchWorkItem,
    OutputKey,
    StagedPlot,
)
from plotagent.batch.protocols import CancellationToken as BatchCancellationToken
from plotagent.charts.registry import (
    ChartRegistryError,
    get_chart,
    patch_operations_for_chart,
)
from plotagent.charts.series_rules import get_series_rule
from plotagent.contracts.agent_context import (
    ChartCapabilities,
    ChartEditCapabilities,
    ContextFieldSummary,
    ContextObjectRef,
    DisclosureCategory,
)
from plotagent.contracts.base import (
    ColorValue,
    FieldMappingRef,
    PhysicalLength,
    PhysicalSize,
    PlotCalculationResultRef,
    PlotSpecRef,
    PreparationSpecRef,
    PreparedDatasetRef,
    SourceDatasetRef,
)
from plotagent.contracts.calculations import (
    ConfusionCountSpec,
    DensityKDESpec,
    ECDFSpec,
    HistogramBinningSpec,
    PercentStackSpec,
    PlotCalculationResult,
    PlotCalculationSpec,
    TukeyBoxSpec,
    ViolinKDESpec,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.datasets import (
    FieldMapping,
    FieldRoleBinding,
    FieldSnapshot,
    SelectFieldsSpec,
    SourceDataset,
)
from plotagent.contracts.decisions import (
    ActionPlan,
    AddAnnotationIntent,
    AxisLabelIntent,
    AxisRangeIntent,
    AxisReverseIntent,
    AxisScaleIntent,
    AxisTicksIntent,
    BarAreaStyleIntent,
    CanvasSizeIntent,
    CategoryColorIntent,
    ChartParametersIntent,
    ColorbarStyleIntent,
    CreateBatchAction,
    CreatePlotAction,
    DualYAxisStyleIntent,
    FacetStyleIntent,
    FontSizeIntent,
    LegendPlacementIntent,
    LegendVisibilityIntent,
    NeedsInput,
    PaletteIntent,
    PatchPlotAction,
    PlotTitleIntent,
    SemanticFieldSelection,
    SeriesStyleIntent,
    UncertaintyStyleIntent,
    Unsupported,
    YOffsetStyleIntent,
)
from plotagent.contracts.plots import (
    AddAnnotationPatch,
    ApplyPublicationProfilePatch,
    AxisScaleKind,
    AxisSpec,
    BatchExecutionSignature,
    BatchItemState,
    BatchPlotOverride,
    BatchSpec,
    CalculatedSeriesData,
    CategoricalFamily,
    DatasetFieldSignature,
    DatasetSignature,
    DistributionFamily,
    DoseResponseFamily,
    FacetFamily,
    FigurePanel,
    FigureSpec,
    ForestFamily,
    MatrixFamily,
    MoveLegendPatch,
    PlotPatch,
    PlotProvenance,
    PlotSpec,
    PrecomputedDataRef,
    PrecomputedSeriesData,
    PreparedSeriesData,
    PublicationProfileSnapshot,
    RemoveAnnotationPatch,
    ResolvedStyleSnapshot,
    SafeRichText,
    SafeTextNode,
    ScaleSpec,
    SeriesSpec,
    SetAxisLabelPatch,
    SetAxisRangePatch,
    SetAxisReversePatch,
    SetAxisScalePatch,
    SetAxisTicksPatch,
    SetBarAreaStylePatch,
    SetCanvasSizePatch,
    SetCategoryColorPatch,
    SetChartParametersPatch,
    SetColorbarStylePatch,
    SetDualYAxisStylePatch,
    SetFacetStylePatch,
    SetFontSizePatch,
    SetLegendVisibilityPatch,
    SetPalettePatch,
    SetPlotTitlePatch,
    SetSeriesStylePatch,
    SetUncertaintyStylePatch,
    SetYOffsetStylePatch,
    SpecialFamily,
    StyleSourceRef,
    SurvivalFamily,
    UpdateAnnotationPatch,
    XYFamily,
)
from plotagent.contracts.project_context import ContextFieldBinding, ProjectContextSnapshot
from plotagent.contracts.registry import (
    CHARTS_BY_ID as CONTRACT_CHARTS_BY_ID,
)
from plotagent.contracts.registry import (
    PRODUCT_CHART_IDS,
    REMOVED_CHART_IDS,
)
from plotagent.contracts.styles import SymbolStyle, resolve_palette
from plotagent.contracts.task_runtime import TaskItemSnapshot, TaskOutputRef, TaskPlanSnapshot
from plotagent.desktop_core.engine_session import DesktopEngineSession
from plotagent.desktop_core.protocol import JsonValue as RpcJsonValue
from plotagent.desktop_core.services import RpcContext, RpcServiceError, ServiceRegistry
from plotagent.desktop_core.tasks import (
    BoundedWorkerExecutor,
    TaskControlError,
    TaskRegistry,
)
from plotagent.engine import EngineVersionConflict, PlotEngineAction
from plotagent.exports import export_png, export_svg
from plotagent.figures import FigureService
from plotagent.figures.models import (
    AxisCompatibilitySignature,
    FigureCreateRequest,
    FigureResult,
    FigureSourceSnapshot,
)
from plotagent.figures.protocols import FigureRepository
from plotagent.importing.models import Clarification, Rejection
from plotagent.origin import (
    build_origin_export_spec,
    compile_origin_plan,
    export_origin,
    preflight_origin,
)
from plotagent.origin.models import OriginExportSuccess
from plotagent.plot_calculations import ALGORITHM_VERSION, PlotCalculationInput, calculate_plot
from plotagent.plots.validation import PlotValidationError, validate_plot_patch
from plotagent.preparation import prepare
from plotagent.preparation.artifacts import PreparedArtifact, SourceTableResolver
from plotagent.rendering import (
    PanelPlan,
    PlotResolver,
    RenderDataStore,
    RenderTable,
    ResolvedPlot,
)
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
    StoredExport,
    StoredPlot,
)
from plotagent.storage.errors import StorageProblem
from plotagent.storage.schema import migrate_catalog_v1_to_v2
from plotagent.workflow_errors import WorkflowFailure

type ProviderFactory = Callable[[NetworkMode, Mapping[str, RpcJsonValue]], ModelProvider]
type ProductHandler = Callable[[RpcContext, RpcJsonValue | None], RpcJsonValue]

_PATCH_ADAPTER: TypeAdapter[PlotPatch] = TypeAdapter(PlotPatch)
_ENGINE_HASH = hashlib.sha256(b"plotagent.desktop-application.v1").hexdigest()
_STYLE_HASH = hashlib.sha256(b"plotagent.default-style.v1").hexdigest()
_PROFILE_HASH = hashlib.sha256(b"plotagent.default-profile.v1").hexdigest()
_PROVIDER_SETTING_KEY = "agent.provider.active"
_CUSTOM_PROVIDER_CONFIG_ID = "custom.default"


@dataclass(slots=True)
class ProjectSession(SourceTableResolver):
    store: ProjectStore
    domain: ProjectDomainRepository
    imports: ProjectImportService
    agent_runtime: AgentRuntimeRepository
    engine: DesktopEngineSession
    engine_agent_plans: EngineAgentPlanRepository

    @property
    def project_id(self) -> str:
        return self.store.project_id

    def resolve(self, source_dataset: SourceDataset):  # type: ignore[no-untyped-def]
        return self.domain.resolve_source(source_dataset)

    def close(self) -> None:
        self.store.close()


@dataclass(slots=True)
class _BatchRuntime:
    session: ProjectSession
    service: BatchService
    repository: _SessionBatchRepository
    executor: _SessionBatchExecutor


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
        self._batch_runtime: dict[str, _BatchRuntime] = {}
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
            "engine.plots.list": self._engine_plots_list,
            "engine.plots.get": self._engine_plots_get,
            "agent.engine.plans.create": self._engine_agent_plan_create,
            "agent.engine.plans.get": self._engine_agent_plan_get,
            "agent.engine.plans.confirm": self._engine_agent_plan_confirm,
            "agent.engine.plans.run": self._engine_agent_plan_run,
            "agent.engine.plans.resume": self._engine_agent_plan_run,
            "plots.create": self._plots_create,
            "plots.patch": self._plots_patch,
            "plots.list": self._plots_list,
            "plots.get": self._plots_get,
            "plots.render": self._plots_render,
            "batch.create": self._batch_create,
            "batch.run": self._batch_run,
            "batch.get": self._batch_get,
            "figures.create": self._figures_create,
            "figures.get": self._figures_get,
            "figures.render": self._figures_render,
            "provider.status": self._provider_status,
            "provider.configure": self._provider_configure,
            "provider.clear": self._provider_clear,
            "origin.status": self._origin_status,
            "agent.context.get": self._agent_context_get,
            "agent.decide": self._agent_decide,
            "agent.plans.create_batch": self._agent_batch_plan_create,
            "agent.plans.get": self._agent_plan_get,
            "agent.plans.list": self._agent_plan_list,
            "agent.plans.confirm": self._agent_plan_confirm,
            "agent.plans.run": self._agent_plan_run,
            "agent.plans.resume": self._agent_plan_resume,
            "agent.plans.events": self._agent_plan_events,
            "exports.png_svg": self._exports_png_svg,
            "exports.origin": self._exports_origin,
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
        task_id = self._begin_task(context, "engine-action")
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
        except Exception:
            self._fail_task(context.tasks, task_id)
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
                "plots": session.engine.list_latest(),
            },
        )

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

    def _engine_agent_plan_confirm(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        stored = session.engine_agent_plans.confirm(_text(values["plan_id"], "plan_id"))
        return self._engine_agent_plan_payload(session, stored)

    def _engine_agent_plan_run(
        self, context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        plan_id = _text(values["plan_id"], "plan_id")
        task_id = self._begin_task(context, "engine-agent-plan")
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
            self._fail_task(context.tasks, task_id)
            raise RpcServiceError(error.code, str(error)) from None
        except Exception:
            self._fail_task(context.tasks, task_id)
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
            except PlotValidationError as error:
                raise RpcServiceError(error.code, error.message) from None
            except WorkflowFailure as error:
                raise RpcServiceError(error.error.code, error.error.message) from None
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
                self._project_summary(item.project_id, item.display_name, item.last_opened_at)
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
                    existing.project_id, existing.display_name, existing.last_opened_at
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
        for task_id, runtime in tuple(self._batch_runtime.items()):
            if runtime.session.project_id == project_id:
                self._batch_runtime.pop(task_id, None)

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
        session.agent_runtime.recover_interrupted()
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
        task_id = self._begin_task(context, "import")
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
                context.tasks.transition(task_id, "failed")
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
        except Exception:
            self._fail_task(context.tasks, task_id)
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

    def _plots_create(
        self,
        context: RpcContext,
        params: RpcJsonValue | None,
        *,
        provenance_origin: Literal["manual", "agent_plan"] = "manual",
        plan_id: str | None = None,
    ) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "plot_id",
                "chart_type_id",
                "source_dataset_id",
                "source_version",
                "field_mapping",
                "idempotency_key",
                "expected_version",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        expected = _integer(values["expected_version"], "expected_version", minimum=0)
        key = _text(values["idempotency_key"], "idempotency_key")
        plot_id = _text(values["plot_id"], "plot_id")
        chart_type_id = _text(values["chart_type_id"], "chart_type_id")
        source_id = _text(values["source_dataset_id"], "source_dataset_id")
        source_version = _integer(values["source_version"], "source_version", minimum=1)
        bindings = _string_mapping(values["field_mapping"], "field_mapping")
        request_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "plot_id": plot_id,
                    "chart_type_id": chart_type_id,
                    "source_dataset_id": source_id,
                    "source_version": source_version,
                    "field_mapping": bindings,
                    "expected_version": expected,
                    "provenance_origin": provenance_origin,
                    "plan_id": plan_id,
                },
            )
        )
        replay = session.domain.replay("plots.create", key, request_hash)
        if replay is not None:
            return {**replay, "replayed": True}
        session.domain.require_revision(expected)
        source = session.domain.source_record(source_id, source_version)
        source_table = session.domain.resolve_source(source)
        task_id = self._begin_task(context, "plot-create")
        try:
            context.tasks.transition(
                task_id,
                "running",
                progress={"completed": 0, "total": source.data_ref.row_count, "unit": "rows"},
            )
            future = context.workers.submit(
                self._compile_plot_bundle,
                plot_id,
                chart_type_id,
                source,
                source_table,
                bindings,
                provenance_origin,
                plan_id,
            )
            (
                mapping,
                preparation_spec,
                prepared,
                plot,
                _resolved,
                render_artifacts,
            ) = future.result()
            self._task_token(context.tasks, task_id).raise_if_cancelled()
            response = self._plot_response(
                session,
                plot,
                prepared.prepared_dataset,
                task_id=task_id,
                project_version=expected + 1,
            )
            context.tasks.transition(
                task_id,
                "committing",
                progress={
                    "completed": source.data_ref.row_count,
                    "total": source.data_ref.row_count,
                    "unit": "rows",
                },
            )
            session.domain.commit_new_plot(
                plot=plot,
                mapping=mapping,
                preparation_spec=preparation_spec,
                prepared=prepared,
                expected_revision=expected,
                operation="plots.create",
                idempotency_key=key,
                request_hash=request_hash,
                response=response,
                render_artifacts=render_artifacts,
            )
            context.tasks.transition(
                task_id,
                "succeeded",
                progress={
                    "completed": source.data_ref.row_count,
                    "total": source.data_ref.row_count,
                    "unit": "rows",
                },
            )
            return response
        except TaskControlError:
            self._cancel_task(context.tasks, task_id)
            raise
        except Exception:
            self._fail_task(context.tasks, task_id)
            raise

    def _plots_patch(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "plot_id",
                "expected_version",
                "idempotency_key",
                "patch",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        plot_id = _text(values["plot_id"], "plot_id")
        expected = _integer(values["expected_version"], "expected_version", minimum=1)
        key = _text(values["idempotency_key"], "idempotency_key")
        patch = _PATCH_ADAPTER.validate_json(json.dumps(values["patch"], ensure_ascii=False))
        request_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "plot_id": plot_id,
                    "expected_version": expected,
                    "patch": patch.model_dump(mode="json"),
                },
            )
        )
        replay = session.domain.replay("plots.patch", key, request_hash)
        if replay is not None:
            return {**replay, "replayed": True}
        previous = session.domain.get_plot(plot_id, expected)
        if session.domain.latest_plot_version(plot_id) != expected:
            raise RpcServiceError("PATCH_VERSION_CONFLICT", "PlotSpec version is stale.")
        task_id = self._begin_task(context, "plot-patch")
        try:
            context.tasks.transition(task_id, "running")
            future = context.workers.submit(self._apply_patch, previous, patch)
            plot = future.result()
            resolved = self._resolve_plot(
                session,
                StoredPlot(
                    plot=plot,
                    field_mapping=previous.field_mapping,
                    preparation_spec=previous.preparation_spec,
                    prepared_dataset=previous.prepared_dataset,
                    render_bindings=previous.render_bindings,
                    content_hash=canonical_hash(plot),
                ),
            )
            del resolved
            self._task_token(context.tasks, task_id).raise_if_cancelled()
            response = self._plot_response(
                session,
                plot,
                previous.prepared_dataset,
                task_id=task_id,
                project_version=session.domain.revision + 1,
            )
            context.tasks.transition(task_id, "committing")
            session.domain.commit_plot_patch(
                previous=previous,
                plot=plot,
                operation="plots.patch",
                idempotency_key=key,
                request_hash=request_hash,
                response=response,
            )
            context.tasks.transition(task_id, "succeeded")
            return response
        except TaskControlError:
            self._cancel_task(context.tasks, task_id)
            raise
        except Exception:
            self._fail_task(context.tasks, task_id)
            raise

    def _plots_get(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "plot_id"},
            optional={"plot_version"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        version = _optional_integer(values.get("plot_version"), "plot_version", minimum=1)
        stored = session.domain.get_plot(_text(values["plot_id"], "plot_id"), version)
        return self._plot_response(
            session,
            stored.plot,
            stored.prepared_dataset,
            project_version=session.domain.revision,
        )

    def _plots_list(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        return {
            "project_id": session.project_id,
            "project_version": session.domain.revision,
            "plots": [
                self._plot_response(
                    session,
                    stored.plot,
                    stored.prepared_dataset,
                    project_version=session.domain.revision,
                )
                for stored in session.domain.list_plots()
            ],
        }

    def _plots_render(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "plot_id", "plot_version"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        stored = session.domain.get_plot(
            _text(values["plot_id"], "plot_id"),
            _integer(values["plot_version"], "plot_version", minimum=1),
        )
        task_id = self._begin_task(context, "plot-render")
        try:
            context.tasks.transition(task_id, "running")
            resolved = self._resolve_plot(session, stored, quality_tier="interactive")
            output_name = f"{stored.plot.plot_id.replace(':', '-')}-v{stored.plot.plot_version}.png"
            path = session.store.cache_root / output_name
            descriptor = context.workers.submit(_render_preview, path, resolved).result()
            self._task_token(context.tasks, task_id).raise_if_cancelled()
            context.tasks.transition(task_id, "committing")
            context.tasks.transition(task_id, "succeeded")
            return {
                "task_id": task_id,
                "plot_id": stored.plot.plot_id,
                "plot_version": stored.plot.plot_version,
                "artifact": descriptor,
            }
        except TaskControlError:
            self._cancel_task(context.tasks, task_id)
            raise
        except Exception:
            self._fail_task(context.tasks, task_id)
            raise

    def _exports_png_svg(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "plot_id",
                "plot_version",
                "format",
                "destination_resource_id",
                "destination_path",
                "idempotency_key",
                "expected_version",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        plot_id = _text(values["plot_id"], "plot_id")
        plot_version = _integer(values["plot_version"], "plot_version", minimum=1)
        expected = _integer(values["expected_version"], "expected_version", minimum=1)
        if expected != plot_version:
            raise RpcServiceError("VERSION_CONFLICT", "The export input version is stale.")
        output_format = _text(values["format"], "format")
        if output_format not in {"png", "svg"}:
            raise RpcServiceError("RENDER_FORMAT_UNSUPPORTED", "Only PNG and SVG are supported.")
        destination = Path(_text(values["destination_path"], "destination_path"))
        resource_id = _text(values["destination_resource_id"], "destination_resource_id")
        key = _text(values["idempotency_key"], "idempotency_key")
        request_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "plot_id": plot_id,
                    "plot_version": plot_version,
                    "format": output_format,
                    "destination_resource_id": resource_id,
                    "destination_path_hash": hashlib.sha256(
                        str(destination).encode("utf-8")
                    ).hexdigest(),
                },
            )
        )
        replay = session.domain.replay("exports.png_svg", key, request_hash)
        if replay is not None:
            return {**replay, "replayed": True}
        stored = session.domain.get_plot(plot_id, plot_version)
        task_id = self._begin_task(context, "export")
        try:
            context.tasks.transition(task_id, "running")
            resolved = self._resolve_plot(session, stored, quality_tier="formal")
            exporter = export_png if output_format == "png" else export_svg
            validation = context.workers.submit(exporter, destination, resolved).result()
            self._task_token(context.tasks, task_id).raise_if_cancelled()
            artifact_hash, artifact_size = _hash_file(destination)
            export_id = "export:" + request_hash[:24]
            response: dict[str, RpcJsonValue] = {
                "task_id": task_id,
                "export_id": export_id,
                "plot_id": plot_id,
                "plot_version": plot_version,
                "format": output_format,
                "artifact": {
                    "resource_id": resource_id,
                    "path": str(destination.resolve()),
                    "content_hash": artifact_hash,
                    "size": artifact_size,
                    "render_plan_hash": validation.render_plan_hash,
                },
            }
            context.tasks.transition(task_id, "committing")
            session.domain.save_export(
                StoredExport(
                    export_id=export_id,
                    plot_id=plot_id,
                    plot_version=plot_version,
                    format=cast(Literal["png", "svg", "opju"], output_format),
                    destination_path=str(destination.resolve()),
                    artifact_hash=artifact_hash,
                    artifact_size=artifact_size,
                    render_plan_hash=validation.render_plan_hash,
                    created_at=_utc_now(),
                ),
                operation="exports.png_svg",
                idempotency_key=key,
                request_hash=request_hash,
                response=response,
            )
            context.tasks.transition(task_id, "succeeded")
            return response
        except TaskControlError:
            self._cancel_task(context.tasks, task_id)
            raise
        except Exception:
            self._fail_task(context.tasks, task_id)
            raise

    def _exports_origin(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "plot_id",
                "plot_version",
                "destination_resource_id",
                "destination_path",
                "idempotency_key",
                "expected_version",
            },
            optional={"target_kind", "expected_existing_sha256"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        target_id = _text(values["plot_id"], "plot_id")
        target_version = _integer(values["plot_version"], "plot_version", minimum=1)
        target_kind = _text(values.get("target_kind", "plot"), "target_kind")
        if target_kind not in {"plot", "batch", "figure"}:
            raise RpcServiceError("INVALID_PARAMS", "Origin export target kind is invalid.")
        expected = _integer(values["expected_version"], "expected_version", minimum=1)
        if target_version != expected:
            raise RpcServiceError("VERSION_CONFLICT", "The export input version is stale.")
        destination = Path(_text(values["destination_path"], "destination_path"))
        resource_id = _text(values["destination_resource_id"], "destination_resource_id")
        key = _text(values["idempotency_key"], "idempotency_key")
        expected_existing_sha256 = values.get("expected_existing_sha256")
        if expected_existing_sha256 is not None:
            expected_existing_sha256 = _text(
                expected_existing_sha256,
                "expected_existing_sha256",
            )
        request_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "target_kind": target_kind,
                    "target_id": target_id,
                    "target_version": target_version,
                    "destination_resource_id": resource_id,
                    "destination_path_hash": hashlib.sha256(
                        str(destination).encode("utf-8")
                    ).hexdigest(),
                    "expected_existing_sha256": expected_existing_sha256,
                },
            )
        )
        replay = session.domain.replay("exports.origin", key, request_hash)
        if replay is not None:
            return {**replay, "replayed": True}
        resolved_plots: tuple[ResolvedPlot, ...]
        target_scope: Literal["current_plot", "batch", "figure"]
        if target_kind == "plot":
            stored = session.domain.get_plot(target_id, target_version)
            resolved_plots = (self._resolve_plot(session, stored, quality_tier="formal"),)
            target_scope = "current_plot"
            record_plot_id = target_id
            record_plot_version = target_version
        elif target_kind == "batch":
            batch, _state = session.domain.get_batch(target_id)
            if batch.batch_version != target_version:
                raise RpcServiceError("VERSION_CONFLICT", "The batch version is stale.")
            refs = tuple(
                item.plot_version_ref
                for item in batch.item_states
                if item.state == "succeeded" and item.plot_version_ref is not None
            )
            if not refs:
                raise RpcServiceError(
                    "BATCH_EXPORT_SCOPE_EMPTY",
                    "The batch contains no succeeded plots to export.",
                )
            resolved_plots = tuple(
                self._resolve_plot(
                    session,
                    session.domain.get_plot(ref.plot_id, ref.plot_version),
                    quality_tier="formal",
                )
                for ref in refs
            )
            target_scope = "batch"
            record_plot_id = refs[0].plot_id
            record_plot_version = refs[0].plot_version
        else:
            figure = session.domain.get_figure(target_id)
            if figure.figure_version != target_version:
                raise RpcServiceError("VERSION_CONFLICT", "The figure version is stale.")
            resolved_plots = (self._resolve_figure(session, figure, quality_tier="formal"),)
            target_scope = "figure"
            record_plot_id = figure.panels[0].plot_version_ref.plot_id
            record_plot_version = figure.panels[0].plot_version_ref.plot_version
        task_id = self._begin_task(context, "origin")
        try:
            context.tasks.transition(task_id, "running")
            export_spec = build_origin_export_spec(
                resolved_plots,
                export_id="export:" + request_hash[:24],
                target_scope=target_scope,
                output_name=destination.name,
            )
            origin_plan = compile_origin_plan(resolved_plots, export_spec)
            token = self._task_token(context.tasks, task_id)
            # A real Origin build plus save/reopen validation routinely exceeds
            # the worker's 30 second smoke-test default even for one graph. Keep
            # the desktop method bounded, but give every native worker the same
            # production budget already covered by the outer 925 second IPC cap.
            timeout_seconds = 300.0
            outcome = context.workers.submit(
                export_origin,
                origin_plan,
                destination,
                expected_existing_sha256=expected_existing_sha256,
                timeout_seconds=timeout_seconds,
                cancel_requested=lambda: token.is_cancelled,
            ).result()
            if not isinstance(outcome, OriginExportSuccess):
                if outcome.error.code.value == "CANCELLED":
                    self._cancel_task(context.tasks, task_id)
                else:
                    context.tasks.transition(task_id, "failed")
                return cast(
                    RpcJsonValue,
                    {
                        "task_id": task_id,
                        "export_id": None,
                        "result": outcome.to_dict(),
                    },
                )
            export_id = "export:" + request_hash[:24]
            response: dict[str, RpcJsonValue] = {
                "task_id": task_id,
                "export_id": export_id,
                "target_kind": target_kind,
                "target_id": target_id,
                "target_version": target_version,
                "target_scope": target_scope,
                "graph_count": len(origin_plan.graph_objects),
                "format": "opju",
                "artifact": {
                    "resource_id": resource_id,
                    "path": str(destination.resolve()),
                    "content_hash": outcome.file_sha256,
                    "size": outcome.file_size,
                    "render_plan_hash": outcome.render_plan_sha256,
                },
            }
            # OriginExportSuccess means the validated OPJU has crossed its atomic
            # publication point. A cancellation racing after that point must finish
            # the authoritative export record instead of leaving an untracked file.
            context.tasks.transition(task_id, "committing")
            session.domain.save_export(
                StoredExport(
                    export_id=export_id,
                    plot_id=record_plot_id,
                    plot_version=record_plot_version,
                    format="opju",
                    destination_path=str(destination.resolve()),
                    artifact_hash=outcome.file_sha256,
                    artifact_size=outcome.file_size,
                    render_plan_hash=outcome.render_plan_sha256,
                    created_at=_utc_now(),
                ),
                operation="exports.origin",
                idempotency_key=key,
                request_hash=request_hash,
                response=response,
            )
            context.tasks.transition(task_id, "succeeded")
            return response
        except TaskControlError:
            self._cancel_task(context.tasks, task_id)
            raise
        except Exception:
            self._fail_task(context.tasks, task_id)
            raise

    def _batch_create(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "task_id",
                "batch_id",
                "source_datasets",
                "chart_type_id",
                "field_mapping",
                "idempotency_key",
                "expected_version",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        expected = _integer(values["expected_version"], "expected_version", minimum=0)
        session.domain.require_revision(expected)
        task_id = _text(values["task_id"], "task_id")
        batch_id = _text(values["batch_id"], "batch_id")
        key = _text(values["idempotency_key"], "idempotency_key")
        chart_type_id = _text(values["chart_type_id"], "chart_type_id")
        bindings = _string_mapping(values["field_mapping"], "field_mapping")
        source_values = _list(values["source_datasets"], "source_datasets")
        if not source_values:
            raise RpcServiceError("INVALID_PARAMS", "A batch requires at least one dataset.")
        sources: list[SourceDataset] = []
        for item in source_values:
            source_ref = _object(
                item,
                required={"source_dataset_id", "source_version"},
            )
            sources.append(
                session.domain.source_record(
                    _text(source_ref["source_dataset_id"], "source_dataset_id"),
                    _integer(source_ref["source_version"], "source_version", minimum=1),
                )
            )
        first_table = session.domain.resolve_source(sources[0])
        mapping, preparation_spec, prepared, template_plot, _resolved, _artifacts = (
            self._compile_plot_bundle(
                f"plot:{batch_id.removeprefix('batch:')}.template",
                chart_type_id,
                sources[0],
                first_table,
                bindings,
                "manual",
                None,
            )
        )
        del prepared
        signatures = tuple(self._dataset_signature(source, bindings) for source in sources)
        work_items = tuple(
            BatchWorkItem(
                item_id=f"item.{index + 1}",
                source_ref=_source_ref(source),
                dataset_signature=signatures[index],
            )
            for index, source in enumerate(sources)
        )
        template = BatchTemplate(
            field_mapping_ref=FieldMappingRef(
                field_mapping_id=mapping.field_mapping_id,
                mapping_version=mapping.mapping_version,
                content_hash=mapping.content_hash,
            ),
            preparation_spec_ref=PreparationSpecRef(
                preparation_spec_id=preparation_spec.preparation_spec_id,
                preparation_version=preparation_spec.preparation_version,
                content_hash=canonical_hash(preparation_spec),
            ),
            plot_calculation_spec_ref=None,
            plot_template=template_plot,
            shared_style=template_plot.resolved_style,
        )
        repository = _SessionBatchRepository(session)
        executor = _SessionBatchExecutor(
            self,
            session,
            bindings,
            batch_id,
            chart_type_id,
            repository,
        )
        service = BatchService(repository, executor)
        submission = service.submit(
            BatchSubmissionRequest(
                task_id=task_id,
                project_id=session.project_id,
                action_id="action:batch",
                idempotency_key=key,
                batch_id=batch_id,
                mapping_confirmed=True,
                items=work_items,
                template=template,
            )
        )
        if isinstance(submission, (NeedsInput, Unsupported)):
            return cast(RpcJsonValue, submission.model_dump(mode="json"))
        assert isinstance(submission, BatchSubmission)
        context.tasks.register(task_id)
        self._batch_runtime[task_id] = _BatchRuntime(
            session=session,
            service=service,
            repository=repository,
            executor=executor,
        )
        return {
            "task_id": task_id,
            "batch_id": batch_id,
            "state": submission.state,
            "project_version": expected,
            "execution_signature": submission.execution_signature.model_dump(mode="json"),
            "replayed": submission.replayed,
        }

    def _batch_run(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "task_id", "idempotency_key", "expected_version"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        task_id = _text(values["task_id"], "task_id")
        key = _text(values["idempotency_key"], "idempotency_key")
        expected = _integer(values["expected_version"], "expected_version", minimum=0)
        request_hash = canonical_hash(
            cast(JsonValue, {"task_id": task_id, "expected_version": expected})
        )
        replay = session.domain.replay("batch.run", key, request_hash)
        if replay is not None:
            return {**replay, "replayed": True}
        session.domain.require_revision(expected)
        runtime = self._batch_runtime.get(task_id)
        if runtime is None or runtime.session is not session:
            raise RpcServiceError("BATCH_NOT_FOUND", "The batch task was not found.")
        try:
            if context.tasks.state(task_id) == "cancelled":
                runtime.service.request_cancel(task_id)
                task = runtime.service.run(task_id)
                return self._batch_task_response(task, session.domain.revision)
            context.tasks.transition(task_id, "preparing")
            if self._task_token(context.tasks, task_id).is_cancelled:
                runtime.service.request_cancel(task_id)
            context.tasks.transition(task_id, "running")
            task = runtime.service.run(task_id)
            if task.batch_spec is None:
                self._fail_task(context.tasks, task_id)
                return self._batch_task_response(task, session.domain.revision)
            response = self._batch_task_response(task, session.domain.revision + 1)
            context.tasks.transition(task_id, "committing")
            session.domain.save_batch(
                task.batch_spec,
                task.state,
                expected_revision=session.domain.revision,
                operation="batch.run",
                idempotency_key=key,
                request_hash=request_hash,
                response=response,
            )
            terminal = "succeeded" if task.state == "succeeded" else "partially_succeeded"
            context.tasks.transition(task_id, terminal)
            return response
        except TaskControlError:
            runtime.service.request_cancel(task_id)
            self._cancel_task(context.tasks, task_id)
            raise
        except Exception:
            self._fail_task(context.tasks, task_id)
            raise

    def _batch_get(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "batch_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        batch, state = session.domain.get_batch(_text(values["batch_id"], "batch_id"))
        return {
            "project_id": session.project_id,
            "project_version": session.domain.revision,
            "state": state,
            "batch": batch.model_dump(mode="json"),
        }

    def _figures_create(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={
                "project_id",
                "figure_id",
                "plot_refs",
                "layout",
                "idempotency_key",
                "expected_version",
            },
            optional={"common_legend", "axis_policy"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        expected = _integer(values["expected_version"], "expected_version", minimum=0)
        session.domain.require_revision(expected)
        figure_id = _text(values["figure_id"], "figure_id")
        layout = _text(values["layout"], "layout")
        key = _text(values["idempotency_key"], "idempotency_key")
        refs = tuple(
            self._plot_ref_value(session, item) for item in _list(values["plot_refs"], "plot_refs")
        )
        request_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "figure_id": figure_id,
                    "layout": layout,
                    "plot_refs": [item.model_dump(mode="json") for item in refs],
                    "common_legend": bool(values.get("common_legend", False)),
                    "axis_policy": values.get("axis_policy", "independent"),
                },
            )
        )
        replay = session.domain.replay("figures.create", key, request_hash)
        if replay is not None:
            return {**replay, "replayed": True}
        repository = _SessionFigureRepository(session)
        result = FigureService(repository).create(
            FigureCreateRequest(
                project_id=session.project_id,
                figure_id=figure_id,
                idempotency_key=key,
                layout=cast(Any, layout),
                plot_refs=refs,
                physical_size=PhysicalSize(
                    width=PhysicalLength(value=178.0, unit="mm"),
                    height=PhysicalLength(value=120.0, unit="mm"),
                ),
                publication_profile=self._profile(178.0, 120.0),
                axis_policy=cast(Any, values.get("axis_policy", "independent")),
                common_legend=bool(values.get("common_legend", False)),
            )
        )
        if isinstance(result, Unsupported):
            return cast(RpcJsonValue, result.model_dump(mode="json"))
        assert isinstance(result, FigureResult)
        response: dict[str, RpcJsonValue] = {
            "project_id": session.project_id,
            "project_version": expected + 1,
            "figure": result.figure.model_dump(mode="json"),
            "replayed": result.replayed,
        }
        session.domain.save_figure(
            result.figure,
            expected_revision=expected,
            operation="figures.create",
            idempotency_key=key,
            request_hash=request_hash,
            response=response,
        )
        return response

    def _figures_get(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "figure_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        figure = session.domain.get_figure(_text(values["figure_id"], "figure_id"))
        return {
            "project_id": session.project_id,
            "project_version": session.domain.revision,
            "figure": figure.model_dump(mode="json"),
        }

    def _figures_render(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "figure_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        figure = session.domain.get_figure(_text(values["figure_id"], "figure_id"))
        task_id = self._begin_task(context, "figure-render")
        try:
            context.tasks.transition(task_id, "running")
            resolved = self._resolve_figure(session, figure)
            path = session.store.cache_root / (
                f"{figure.figure_id.replace(':', '-')}-v{figure.figure_version}.png"
            )
            descriptor = context.workers.submit(_render_preview, path, resolved).result()
            context.tasks.transition(task_id, "committing")
            context.tasks.transition(task_id, "succeeded")
            return {
                "task_id": task_id,
                "figure_id": figure.figure_id,
                "figure_version": figure.figure_version,
                "artifact": descriptor,
            }
        except Exception:
            self._fail_task(context.tasks, task_id)
            raise

    def _agent_context_get(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id"}, optional={"conversation_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        conversation_id = _optional_text(values.get("conversation_id"), "conversation_id")
        if conversation_id is None:
            conversation_id = self._default_conversation_id(session.project_id)
        state = session.agent_runtime.get_conversation_state(conversation_id)
        snapshot = session.agent_runtime.latest_context_snapshot(conversation_id)
        return {
            "conversation_id": conversation_id,
            "exists": state is not None,
            "conversation_state": (
                None if state is None else cast(RpcJsonValue, state.model_dump(mode="json"))
            ),
            "context_snapshot": (
                None if snapshot is None else cast(RpcJsonValue, snapshot.model_dump(mode="json"))
            ),
        }

    def _agent_batch_plan_create(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        """Build the manual batch path as the same persisted plan used by Agent turns."""

        values = _object(
            params,
            required={
                "project_id",
                "source_datasets",
                "chart_type_id",
                "field_mapping",
                "expected_version",
            },
            optional={"conversation_id"},
        )
        session = self._session(_text(values["project_id"], "project_id"))
        expected = _integer(values["expected_version"], "expected_version", minimum=0)
        session.domain.require_revision(expected)
        chart_type_id = _text(values["chart_type_id"], "chart_type_id")
        if chart_type_id in REMOVED_CHART_IDS:
            raise RpcServiceError(
                "CHART_TYPE_REMOVED",
                "The selected chart was removed from the 38-chart product surface.",
            )
        if chart_type_id not in PRODUCT_CHART_IDS or chart_type_id == "K25":
            raise RpcServiceError("INVALID_PARAMS", "The selected chart is unavailable.")
        field_mapping = _string_mapping(values["field_mapping"], "field_mapping")
        if not field_mapping:
            raise RpcServiceError("INVALID_PARAMS", "A confirmed field mapping is required.")
        source_values = _list(values["source_datasets"], "source_datasets")
        if not source_values or len(source_values) > 63:
            raise RpcServiceError(
                "INVALID_PARAMS",
                "A batch plan requires between 1 and 63 source datasets.",
            )
        if len(source_values) * len(field_mapping) > 256:
            raise RpcServiceError(
                "INVALID_PARAMS",
                "The batch field mapping exceeds the 256-binding plan limit.",
            )
        field_roles = tuple(sorted(field_mapping))
        sources: list[SourceDataset] = []
        for value in source_values:
            source_ref = _object(
                value,
                required={"source_dataset_id", "source_version"},
            )
            sources.append(
                session.domain.source_record(
                    _text(source_ref["source_dataset_id"], "source_dataset_id"),
                    _integer(source_ref["source_version"], "source_version", minimum=1),
                )
            )
        source_keys = tuple((source.source_dataset_id, source.source_version) for source in sources)
        if len(set(source_keys)) != len(source_keys):
            raise RpcServiceError(
                "INVALID_PARAMS",
                "A batch plan cannot contain the same dataset version twice.",
            )

        source_objects = tuple(
            ContextObjectRef(
                object_alias=f"dataset_{index}",
                object_id=source.source_dataset_id,
                object_version=source.source_version,
                object_type="source_dataset",
                content_hash=source.content_hash,
            )
            for index, source in enumerate(sources, start=1)
        )
        field_aliases = tuple(
            f"d{index}_{role}" for index in range(1, len(sources) + 1) for role in field_roles
        )
        conversation_id = _optional_text(
            values.get("conversation_id"), "conversation_id"
        ) or self._default_conversation_id(session.project_id)
        persisted = session.agent_runtime.get_conversation_state(conversation_id)
        if persisted is None:
            conversation_state = ConversationState(
                current_target=source_objects[0],
                selected_objects=source_objects,
                confirmed_field_aliases=field_aliases,
            )
            session.agent_runtime.save_conversation_state(
                conversation_id,
                conversation_state.project(),
                expected_state_version=None,
            )
        else:
            conversation_state = ConversationStateReducer().select_target(
                ConversationState.from_projection(persisted),
                source_objects[0],
                selected_objects=source_objects,
            )
            conversation_state = ConversationStateReducer().confirm_fields(
                conversation_state,
                field_aliases,
            )
            session.agent_runtime.save_conversation_state(
                conversation_id,
                conversation_state.project(),
                expected_state_version=persisted.state_version,
            )

        field_bindings = tuple(
            ContextFieldBinding(
                field_alias=f"d{index}_{role}",
                field_id=field_mapping[role],
                source_dataset_id=source.source_dataset_id,
                source_version=source.source_version,
            )
            for index, source in enumerate(sources, start=1)
            for role in field_roles
        )
        snapshot = ProjectContextService().build_snapshot(
            project_id=session.project_id,
            project_revision=expected,
            conversation_id=conversation_id,
            conversation_state=conversation_state.project(),
            known_objects=source_objects,
            field_bindings=field_bindings,
        )
        session.agent_runtime.save_context_snapshot(snapshot)

        create_actions = tuple(
            CreatePlotAction(
                action_id=f"action:item_{index}",
                target_alias=f"plot_{index}",
                chart_type_id=cast(Any, chart_type_id),
                field_selections=tuple(
                    SemanticFieldSelection(
                        role=role,
                        context_field_alias=f"d{index}_{role}",
                    )
                    for role in field_roles
                ),
            )
            for index in range(1, len(sources) + 1)
        )
        batch_action = CreateBatchAction(
            action_id="action:batch",
            depends_on=tuple(action.action_id for action in create_actions),
            target_alias="batch_result",
            chart_type_id=cast(Any, chart_type_id),
            field_selections=create_actions[0].field_selections,
        )
        source_plan = ActionPlan(
            plan_id=f"plan:{uuid.uuid4().hex}",
            target_alias="batch_result",
            actions=(*create_actions, batch_action),
            confirmation="required",
        )
        compiled = TaskPlanCompiler().compile(source_plan, snapshot)
        task_plan = compiled.model_copy(
            update={
                "items": tuple(
                    item.model_copy(update={"expected_objects": (source_objects[index],)})
                    if index < len(source_objects)
                    else item
                    for index, item in enumerate(compiled.items)
                )
            }
        )
        session.agent_runtime.create_plan(task_plan)
        return {
            "project_version": expected,
            "task_plan": cast(RpcJsonValue, task_plan.model_dump(mode="json")),
        }

    def _agent_plan_get(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        plan = session.agent_runtime.get_plan(_text(values["plan_id"], "plan_id"))
        return cast(RpcJsonValue, plan.model_dump(mode="json"))

    def _agent_plan_list(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id"}, optional={"conversation_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        conversation_id = _optional_text(values.get("conversation_id"), "conversation_id")
        if conversation_id is None:
            conversation_id = self._default_conversation_id(session.project_id)
        plans = session.agent_runtime.list_plans(conversation_id)
        return {
            "conversation_id": conversation_id,
            "plans": [cast(RpcJsonValue, plan.model_dump(mode="json")) for plan in plans],
        }

    def _agent_plan_confirm(
        self, _context: RpcContext, params: RpcJsonValue | None
    ) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id", "accept"})
        accept = values["accept"]
        if not isinstance(accept, bool):
            raise RpcServiceError("INVALID_PARAMS", "Plan confirmation must be boolean.")
        session = self._session(_text(values["project_id"], "project_id"))
        plan = session.agent_runtime.confirm_plan(
            _text(values["plan_id"], "plan_id"),
            accept=accept,
        )
        return cast(RpcJsonValue, plan.model_dump(mode="json"))

    def _agent_plan_events(self, _context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        session = self._session(_text(values["project_id"], "project_id"))
        plan_id = _text(values["plan_id"], "plan_id")
        session.agent_runtime.get_plan(plan_id)
        return {
            "plan_id": plan_id,
            "events": [
                {
                    "event_id": event.event_id,
                    "task_item_id": event.task_item_id,
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "created_at": event.created_at,
                }
                for event in session.agent_runtime.list_events(plan_id)
            ],
        }

    def _agent_plan_resume(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(params, required={"project_id", "plan_id"})
        return self._agent_plan_run(
            context,
            cast(
                RpcJsonValue,
                {
                    "project_id": values["project_id"],
                    "plan_id": values["plan_id"],
                    "resume": True,
                },
            ),
        )

    def _agent_plan_run(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
        values = _object(
            params,
            required={"project_id", "plan_id"},
            optional={"resume"},
        )
        resume = values.get("resume", False)
        if not isinstance(resume, bool):
            raise RpcServiceError("INVALID_PARAMS", "Plan resume must be boolean.")
        session = self._session(_text(values["project_id"], "project_id"))
        plan_id = _text(values["plan_id"], "plan_id")
        task_id = self._begin_task(context, "agent-plan")
        try:
            plan = session.agent_runtime.get_plan(plan_id)
            total = len(plan.items)
            context.tasks.transition(
                task_id,
                "running",
                progress={"completed": 0, "total": total, "unit": "steps"},
            )

            def progress(updated: TaskPlanSnapshot) -> None:
                self._task_token(context.tasks, task_id).raise_if_cancelled()
                completed = sum(
                    item.state
                    in {
                        "succeeded",
                        "failed",
                        "blocked",
                        "stale",
                        "skipped",
                        "cancelled",
                    }
                    for item in updated.items
                )
                context.tasks.update_progress(
                    task_id,
                    {"completed": completed, "total": total, "unit": "steps"},
                )

            orchestrator = PersistentTaskOrchestrator(
                session.agent_runtime,
                _DesktopObjectAuthority(session),
            )
            result = orchestrator.run(
                plan_id,
                _DesktopTaskExecutor(self, context, session),
                resume=resume,
                on_progress=progress,
            )
            self._update_conversation_after_plan(session, result)
            completed = sum(item.state in {"succeeded", "skipped"} for item in result.items)
            context.tasks.transition(
                task_id,
                "committing",
                progress={"completed": total, "total": total, "unit": "steps"},
            )
            terminal = (
                "succeeded"
                if result.state == "succeeded"
                else "partially_succeeded"
                if result.state == "partial_success"
                else "interrupted"
                if result.state == "interrupted"
                else "failed"
            )
            context.tasks.transition(
                task_id,
                terminal,
                progress={"completed": total, "total": total, "unit": "steps"},
            )
            return {
                "task_id": task_id,
                "task_plan": cast(RpcJsonValue, result.model_dump(mode="json")),
                "change_set": self._agent_change_set(result),
                "completed_item_count": completed,
                "total_item_count": total,
                "resumable": result.state in {"partial_success", "failed", "interrupted"},
            }
        except TaskControlError:
            current = session.agent_runtime.get_plan(plan_id)
            if current.state in {"running", "partial_success"}:
                session.agent_runtime.transition_plan(plan_id, "interrupted")
            self._cancel_task(context.tasks, task_id)
            raise
        except Exception:
            self._fail_task(context.tasks, task_id)
            raise

    def _agent_decide(self, context: RpcContext, params: RpcJsonValue | None) -> RpcJsonValue:
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
                "execution_mode",
                "selected_chart_id",
                "locale",
                "network_mode",
                "provider",
                "retention_acknowledged",
                "target",
                "scope",
            },
        )
        session = self._session(_text(values["project_id"], "project_id"))
        expected = _integer(values["expected_version"], "expected_version", minimum=0)
        session.domain.require_revision(expected)
        conversation_id = _optional_text(values.get("conversation_id"), "conversation_id")
        if conversation_id is None:
            conversation_id = self._default_conversation_id(session.project_id)
        execution_mode = _optional_text(values.get("execution_mode"), "execution_mode")
        if execution_mode is None:
            execution_mode = "execute"
        if execution_mode not in {"execute", "plan_only"}:
            raise RpcServiceError("INVALID_PARAMS", "The Agent execution mode is invalid.")
        selected_chart_id = _optional_text(values.get("selected_chart_id"), "selected_chart_id")
        if selected_chart_id in REMOVED_CHART_IDS:
            raise RpcServiceError(
                "CHART_TYPE_REMOVED",
                "The selected chart was removed from the 38-chart product surface.",
            )
        if selected_chart_id is not None and (
            selected_chart_id not in PRODUCT_CHART_IDS or selected_chart_id == "K25"
        ):
            raise RpcServiceError("INVALID_PARAMS", "The selected chart is unavailable.")
        enabled_chart_ids = (
            (selected_chart_id,)
            if selected_chart_id is not None
            else tuple(chart_id for chart_id in PRODUCT_CHART_IDS if chart_id != "K25")
        )
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
        if mode is NetworkMode.LOCAL_ONLY:
            return {
                "accepted": False,
                "error": {
                    "code": "NETWORK_BLOCKED_LOCAL_ONLY",
                    "message": "Agent provider calls are disabled in local-only mode.",
                },
            }
        if values.get("provider") is None:
            provider_values = saved_provider or {}
        else:
            provider_values = _object(values["provider"], required=set(), optional=None)
        try:
            provider = self._provider_factory(mode, provider_values)
            identity = provider.identity
        except Exception:
            return {
                "accepted": False,
                "error": {
                    "code": "PROVIDER_NOT_CONFIGURED",
                    "message": "The desktop model provider configuration is incomplete.",
                },
            }
        source = session.domain.source_record(
            _text(values["source_dataset_id"], "source_dataset_id"),
            _integer(values["source_version"], "source_version", minimum=1),
        )
        source_table = session.domain.resolve_source(source)
        persisted_projection = session.agent_runtime.get_conversation_state(conversation_id)
        target_values = dict(values)
        if persisted_projection is not None and values.get("target") is None:
            persistent_target = persisted_projection.current_target
            if persistent_target.object_type in {"plot", "batch", "figure"}:
                target_values["target"] = cast(
                    RpcJsonValue,
                    {"kind": persistent_target.object_type, "id": persistent_target.object_id},
                )
                target_values["scope"] = (
                    "current"
                    if persistent_target.object_type == "plot"
                    else persistent_target.object_type
                )
        target, selected_objects, target_plots, plots_by_alias = self._agent_target(
            session,
            source,
            target_values,
        )
        if persisted_projection is None:
            conversation_state = ConversationState(
                current_target=target,
                selected_objects=selected_objects,
            )
            session.agent_runtime.save_conversation_state(
                conversation_id,
                conversation_state.project(),
                expected_state_version=None,
            )
        else:
            conversation_state = ConversationState.from_projection(persisted_projection)
            if (
                conversation_state.current_target != target
                or conversation_state.selected_objects != selected_objects
            ):
                conversation_state = ConversationStateReducer().select_target(
                    conversation_state,
                    target,
                    selected_objects=selected_objects,
                )
                session.agent_runtime.save_conversation_state(
                    conversation_id,
                    conversation_state.project(),
                    expected_state_version=persisted_projection.state_version,
                )
        fields, alias_to_field = self._agent_fields(source, source_table.rows)
        project_context = ProjectContextService().build_snapshot(
            project_id=session.project_id,
            project_revision=expected,
            conversation_id=conversation_id,
            conversation_state=conversation_state.project(),
            known_objects=(target, *selected_objects),
            field_bindings=tuple(
                ContextFieldBinding(
                    field_alias=alias,
                    field_id=field_id,
                    source_dataset_id=source.source_dataset_id,
                    source_version=source.source_version,
                )
                for alias, field_id in alias_to_field.items()
            ),
        )
        session.agent_runtime.save_context_snapshot(project_context)
        sample_rows = tuple(
            AuthoritativeSampleRow(
                row_id=source_table.coordinates[index].source_row_id,
                values={
                    field.field_id: source_table.rows[index][field_index]
                    for field_index, field in enumerate(fields)
                },
            )
            for index in range(len(source_table.rows))
        )
        if identity.provider_type == "local_only":
            return {
                "accepted": False,
                "error": {
                    "code": "PROVIDER_NOT_CONFIGURED",
                    "message": "A network-capable desktop model provider is required.",
                },
            }
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
                dataset_content_hash=source.content_hash,
                fields=fields,
                sample_rows=sample_rows,
                selected_objects=selected_objects,
                explicit_field_aliases=tuple(alias_to_field),
            ),
            conversation_state=conversation_state,
            chart_capabilities=ChartCapabilities(
                capability_version="desktop-38-v1",
                allowed_chart_type_ids=enabled_chart_ids,
                allowed_action_types=("create_plot", "patch_plot"),
                allowed_patch_operations=(
                    "set_plot_title",
                    "set_axis_range",
                    "set_axis_scale",
                    "set_axis_label",
                    "set_axis_reverse",
                    "set_axis_ticks",
                    "set_font_size",
                    "set_bar_area_style",
                    "set_uncertainty_style",
                    "set_colorbar_style",
                    "set_dual_y_style",
                    "set_facet_style",
                    "set_y_offset_style",
                    "set_chart_parameters",
                    "set_series_style",
                    "set_category_color",
                    "set_palette",
                    "set_legend_visibility",
                    "move_legend",
                    "set_canvas_size",
                    "add_annotation",
                ),
                chart_edit_capabilities=tuple(
                    ChartEditCapabilities(
                        chart_type_id=chart_id,
                        allowed_patch_operations=cast(
                            Any,
                            tuple(
                                operation
                                for operation in patch_operations_for_chart(chart_id)
                                if operation != "apply_publication_profile"
                            ),
                        ),
                    )
                    for chart_id in enabled_chart_ids
                ),
            ),
            disclosure_grant=DisclosureGrant(
                provider_type=identity.provider_type,
                provider_config_id=identity.provider_config_id,
                retention_disclosure_version="retention-v1",
                retention_acknowledged=bool(values.get("retention_acknowledged", True)),
                allowed_categories=categories,
            ),
        )
        authority = ValidationAuthority(
            current_target=target,
            allowed_target_aliases=frozenset(
                {"active_target", *(item.object_alias for item in selected_objects)}
            ),
            allowed_field_aliases=frozenset(alias_to_field),
            allowed_action_types=frozenset({"create_plot", "patch_plot"}),
            allowed_chart_type_ids=frozenset(enabled_chart_ids),
            allowed_patch_operations=frozenset(
                {
                    "set_plot_title",
                    "set_axis_range",
                    "set_axis_scale",
                    "set_axis_label",
                    "set_axis_reverse",
                    "set_axis_ticks",
                    "set_font_size",
                    "set_bar_area_style",
                    "set_uncertainty_style",
                    "set_colorbar_style",
                    "set_dual_y_style",
                    "set_facet_style",
                    "set_y_offset_style",
                    "set_chart_parameters",
                    "set_series_style",
                    "set_category_color",
                    "set_palette",
                    "set_legend_visibility",
                    "move_legend",
                    "set_canvas_size",
                    "add_annotation",
                }
            ),
            permission_grants=frozenset({"create_plot", "patch_plot"}),
            target_chart_type_ids={
                alias: stored.plot.chart_type_id for alias, stored in plots_by_alias.items()
            },
        )
        orchestrator = SingleAgentOrchestrator(
            network_mode=mode,
            context_builder=ContextBuilder(),
            provider=provider,
            validator=DecisionValidator(),
            audit_sink=InMemoryAuditSink(),
        )
        result = asyncio.run(
            orchestrator.run(
                client_model_run_id=_text(values["client_model_run_id"], "client_model_run_id"),
                context_request=context_request,
                validation_authority=authority,
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
        latest_projection = session.agent_runtime.get_conversation_state(conversation_id)
        if latest_projection is None:
            raise RpcServiceError(
                "AGENT_CONTEXT_MISSING",
                "The authoritative conversation context is unavailable.",
            )
        updated_conversation = ConversationStateReducer().record_decision(
            ConversationState.from_projection(latest_projection),
            decision_kind=decision.decision_type,
            unresolved_question_ids=question_ids,
        )
        session.agent_runtime.save_conversation_state(
            conversation_id,
            updated_conversation.project(),
            expected_state_version=latest_projection.state_version,
            context_hash=project_context.snapshot_hash,
        )
        payload: dict[str, RpcJsonValue] = {
            "accepted": True,
            "conversation_id": conversation_id,
            "context_snapshot_id": project_context.snapshot_id,
            "context_hash": project_context.snapshot_hash,
            "decision": decision.model_dump(mode="json"),
        }
        if isinstance(decision, ActionPlan):
            task_plan = TaskPlanCompiler().compile(decision, project_context)
            session.agent_runtime.create_plan(task_plan)
            payload["task_plan"] = cast(RpcJsonValue, task_plan.model_dump(mode="json"))
            if execution_mode == "plan_only" or decision.confirmation == "required":
                return payload
            task_execution = self._agent_plan_run(
                context,
                cast(
                    RpcJsonValue,
                    {
                        "project_id": session.project_id,
                        "plan_id": task_plan.plan_id,
                    },
                ),
            )
            executed_plan = session.agent_runtime.get_plan(task_plan.plan_id)
            payload["task_plan"] = cast(
                RpcJsonValue,
                executed_plan.model_dump(mode="json"),
            )
            payload["task_execution"] = task_execution
            executions = self._agent_legacy_execution_payloads(
                session,
                executed_plan,
                target,
                target_plots,
            )
            payload["executions"] = executions
            if len(executions) == 1:
                payload["execution"] = executions[0]
            if target.object_type in {"batch", "figure"}:
                payload["scope_execution"] = self._agent_scope_execution_summary(
                    session,
                    target,
                    len(target_plots),
                )
                payload["project_version"] = session.domain.revision
            return payload
        return payload

    def _agent_legacy_execution_payloads(
        self,
        session: ProjectSession,
        plan: TaskPlanSnapshot,
        original_target: ContextObjectRef,
        original_plots: tuple[StoredPlot, ...],
    ) -> list[RpcJsonValue]:
        plot_ids: list[str] = []
        if original_target.object_type in {"batch", "figure"}:
            plot_ids.extend(item.plot.plot_id for item in original_plots)
        else:
            plot_ids.extend(
                output.object_ref.object_id
                for item in plan.items
                for output in item.outputs
                if output.object_ref is not None and output.object_ref.object_type == "plot"
            )
        executions: list[RpcJsonValue] = []
        for plot_id in dict.fromkeys(plot_ids):
            stored = session.domain.get_plot(plot_id)
            executions.append(
                cast(
                    RpcJsonValue,
                    self._plot_response(
                        session,
                        stored.plot,
                        stored.prepared_dataset,
                        project_version=session.domain.revision,
                    ),
                )
            )
        return executions

    @staticmethod
    def _agent_scope_execution_summary(
        session: ProjectSession,
        target: ContextObjectRef,
        updated_plot_count: int,
    ) -> RpcJsonValue:
        if target.object_type == "batch":
            batch, _state = session.domain.get_batch(target.object_id)
            return cast(
                RpcJsonValue,
                {
                    "target_kind": "batch",
                    "target_id": batch.batch_id,
                    "target_version": batch.batch_version,
                    "project_version": session.domain.revision,
                    "updated_plot_count": updated_plot_count,
                    "batch": batch.model_dump(mode="json"),
                },
            )
        figure = session.domain.get_figure(target.object_id)
        return cast(
            RpcJsonValue,
            {
                "target_kind": "figure",
                "target_id": figure.figure_id,
                "target_version": figure.figure_version,
                "project_version": session.domain.revision,
                "updated_plot_count": updated_plot_count,
                "figure": figure.model_dump(mode="json"),
            },
        )

    def _execute_agent_task_item(
        self,
        context: RpcContext,
        session: ProjectSession,
        plan: TaskPlanSnapshot,
        item: TaskItemSnapshot,
    ) -> tuple[TaskOutputRef, ...]:
        snapshot = session.agent_runtime.get_context_snapshot(plan.context_snapshot_id)
        action = item.action
        if isinstance(action, CreatePlotAction):
            field_bindings = {binding.field_alias: binding for binding in snapshot.field_bindings}
            selected = [
                field_bindings[selection.context_field_alias]
                for selection in action.field_selections
            ]
            if not selected:
                raise TaskExecutionError(
                    "AGENT_FIELD_BINDING_MISSING",
                    "The persisted plan has no field bindings.",
                )
            source_ids = {
                (binding.source_dataset_id, binding.source_version) for binding in selected
            }
            if len(source_ids) != 1:
                raise TaskExecutionError(
                    "AGENT_FIELD_BINDING_INVALID",
                    "One plot action must bind fields from one source dataset.",
                )
            source_id, source_version = next(iter(source_ids))
            mapping = {
                selection.role: field_bindings[selection.context_field_alias].field_id
                for selection in action.field_selections
            }
            position = next(
                index
                for index, source_action in enumerate(plan.source_plan.actions)
                if source_action.action_id == action.action_id
            )
            plot_id = "plot:agent." + plan.plan_id.removeprefix("plan:") + f".{position + 1}"
            response = self._plots_create(
                context,
                cast(
                    RpcJsonValue,
                    {
                        "project_id": session.project_id,
                        "plot_id": plot_id,
                        "chart_type_id": action.chart_type_id,
                        "source_dataset_id": source_id,
                        "source_version": source_version,
                        "field_mapping": mapping,
                        "idempotency_key": item.idempotency_key,
                        "expected_version": session.domain.revision,
                    },
                ),
                provenance_origin="agent_plan",
                plan_id=plan.plan_id,
            )
            del response
            stored = session.domain.get_plot(plot_id)
            return (
                TaskOutputRef(
                    output_slot="primary",
                    output_kind="object",
                    object_ref=self._stored_plot_context_ref(action.target_alias, stored),
                    summary=f"创建 {action.chart_type_id} 图",
                ),
            )
        if isinstance(action, CreateBatchAction):
            dependency_ids = set(item.depends_on)
            plot_refs = tuple(
                output.object_ref
                for dependency in plan.items
                if dependency.task_item_id in dependency_ids
                for output in dependency.outputs
                if output.object_ref is not None and output.object_ref.object_type == "plot"
            )
            if not plot_refs:
                raise TaskExecutionError(
                    "BATCH_SCOPE_EMPTY",
                    "The batch plan has no completed plot outputs.",
                )
            stored_plots = tuple(
                session.domain.get_plot(plot_ref.object_id, plot_ref.object_version)
                for plot_ref in plot_refs
            )
            if any(plot.plot.chart_type_id != action.chart_type_id for plot in stored_plots):
                raise TaskExecutionError(
                    "BATCH_SIGNATURE_MISMATCH",
                    "Batch members do not share the selected chart type.",
                )
            signatures = tuple(
                self._dataset_signature(
                    session.domain.source_record(
                        plot.field_mapping.source_dataset_refs[0].source_dataset_id,
                        plot.field_mapping.source_dataset_refs[0].source_version,
                    ),
                    {
                        binding.role: binding.field.field_id
                        for binding in plot.field_mapping.bindings
                    },
                )
                for plot in stored_plots
            )
            if any(signature != signatures[0] for signature in signatures[1:]):
                raise TaskExecutionError(
                    "BATCH_INPUT_NOT_ISOMORPHIC",
                    "Batch inputs do not share one confirmed field signature.",
                )
            template = stored_plots[0]
            field_mapping_ref = FieldMappingRef(
                field_mapping_id=template.field_mapping.field_mapping_id,
                mapping_version=template.field_mapping.mapping_version,
                content_hash=template.field_mapping.content_hash,
            )
            preparation_ref = PreparationSpecRef(
                preparation_spec_id=template.preparation_spec.preparation_spec_id,
                preparation_version=template.preparation_spec.preparation_version,
                content_hash=canonical_hash(template.preparation_spec),
            )
            plot_template_ref = PlotSpecRef(
                plot_id=template.plot.plot_id,
                plot_version=template.plot.plot_version,
                content_hash=template.content_hash,
            )
            signature_payload: dict[str, JsonValue] = {
                "dataset_signature": signatures[0].model_dump(mode="json"),
                "field_mapping_hash": field_mapping_ref.content_hash,
                "preparation_spec_hash": preparation_ref.content_hash,
                "plot_calculation_spec_hash": None,
                "chart_type_id": action.chart_type_id,
                "plot_template_hash": plot_template_ref.content_hash,
                "style_hash": canonical_hash(template.plot.resolved_style),
            }
            execution_signature = BatchExecutionSignature(
                dataset_signature=signatures[0],
                field_mapping_hash=field_mapping_ref.content_hash,
                preparation_spec_hash=preparation_ref.content_hash,
                plot_calculation_spec_hash=None,
                chart_type_id=action.chart_type_id,
                plot_template_hash=plot_template_ref.content_hash,
                style_hash=canonical_hash(template.plot.resolved_style),
                content_hash=canonical_hash(signature_payload),
            )
            batch_id = "batch:agent." + plan.plan_id.removeprefix("plan:")
            batch = BatchSpec(
                batch_id=batch_id,
                batch_version=1,
                dataset_signature=signatures[0],
                execution_signature=execution_signature,
                dataset_version_refs=tuple(plot.prepared_dataset.as_ref() for plot in stored_plots),
                shared_field_mapping=field_mapping_ref,
                shared_preparation=preparation_ref,
                shared_plot_calculation=None,
                plot_template_ref=plot_template_ref,
                shared_style=template.plot.resolved_style,
                axis_policy=action.axis_policy,
                plot_overrides=tuple(
                    BatchPlotOverride(
                        item_id=f"item.{index}",
                        prepared_dataset_ref=plot.prepared_dataset.as_ref(),
                    )
                    for index, plot in enumerate(stored_plots, start=1)
                ),
                item_states=tuple(
                    BatchItemState(
                        item_id=f"item.{index}",
                        state="succeeded",
                        plot_version_ref=PlotSpecRef(
                            plot_id=plot.plot.plot_id,
                            plot_version=plot.plot.plot_version,
                            content_hash=plot.content_hash,
                        ),
                    )
                    for index, plot in enumerate(stored_plots, start=1)
                ),
            )
            request_hash = canonical_hash(batch)
            replay = session.domain.replay(
                "agent.batches.assemble",
                item.idempotency_key,
                request_hash,
            )
            if replay is None:
                batch_response: dict[str, JsonValue] = {
                    "batch_id": batch.batch_id,
                    "batch_version": batch.batch_version,
                    "project_version": session.domain.revision + 1,
                    "batch": cast(JsonValue, batch.model_dump(mode="json")),
                }
                session.domain.save_batch(
                    batch,
                    "succeeded",
                    expected_revision=session.domain.revision,
                    operation="agent.batches.assemble",
                    idempotency_key=item.idempotency_key,
                    request_hash=request_hash,
                    response=batch_response,
                )
            stored_batch, _state = session.domain.get_batch(batch_id)
            return (
                TaskOutputRef(
                    output_slot="batch",
                    output_kind="object",
                    object_ref=ContextObjectRef(
                        object_alias=action.target_alias,
                        object_id=stored_batch.batch_id,
                        object_version=stored_batch.batch_version,
                        object_type="batch",
                        content_hash=canonical_hash(stored_batch),
                    ),
                    summary=f"创建 {len(stored_plots)} 张图的批次",
                ),
            )
        if isinstance(action, PatchPlotAction):
            target = self._agent_runtime_target(snapshot, plan, item)
            stored_plots = self._plots_for_context_target(session, target)
            updated: list[StoredPlot] = []
            for index, stored in enumerate(stored_plots):
                updated.append(
                    self._commit_agent_patch_transaction(
                        session,
                        stored,
                        action,
                        idempotency_key=f"{item.idempotency_key}.{index + 1}",
                        plan_id=plan.plan_id,
                    )
                )
            if target.object_type in {"batch", "figure"}:
                self._commit_agent_scope_update(
                    session,
                    target,
                    tuple(updated),
                    session.domain.revision,
                    plan.source_plan,
                )
            primary = updated[0]
            return (
                TaskOutputRef(
                    output_slot="primary",
                    output_kind="object",
                    object_ref=self._stored_plot_context_ref(action.target_alias, primary),
                    summary=f"修改 {len(updated)} 张图",
                ),
                TaskOutputRef(
                    output_slot="change_set",
                    output_kind="result",
                    content_hash=canonical_hash(
                        cast(
                            JsonValue,
                            [
                                {
                                    "plot_id": stored.plot.plot_id,
                                    "plot_version": stored.plot.plot_version,
                                }
                                for stored in updated
                            ],
                        )
                    ),
                    summary=f"{len(action.patches)} 项修改",
                ),
            )
        raise TaskExecutionError(
            "AGENT_CAPABILITY_UNSUPPORTED",
            "The persisted action is outside the enabled desktop surface.",
        )

    def _commit_agent_patch_transaction(
        self,
        session: ProjectSession,
        previous: StoredPlot,
        action: PatchPlotAction,
        *,
        idempotency_key: str,
        plan_id: str,
    ) -> StoredPlot:
        request_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "plot_id": previous.plot.plot_id,
                    "plot_version": previous.plot.plot_version,
                    "patches": [patch.model_dump(mode="json") for patch in action.patches],
                    "plan_id": plan_id,
                },
            )
        )
        replay = session.domain.replay(
            "agent.plots.patch_transaction",
            idempotency_key,
            request_hash,
        )
        if replay is not None:
            return session.domain.get_plot(previous.plot.plot_id)
        working = previous
        for intent in action.patches:
            payload = self._agent_patch_payload(working, intent)
            patch = _PATCH_ADAPTER.validate_json(json.dumps(payload, ensure_ascii=False))
            plot = self._apply_patch(working, patch)
            working = StoredPlot(
                plot=plot,
                field_mapping=working.field_mapping,
                preparation_spec=working.preparation_spec,
                prepared_dataset=working.prepared_dataset,
                render_bindings=working.render_bindings,
                content_hash=canonical_hash(plot),
            )
        final = working.plot.model_copy(
            update={
                "plot_version": previous.plot.plot_version + 1,
                "provenance": working.plot.provenance.model_copy(
                    update={
                        "parent_plot_ref": PlotSpecRef(
                            plot_id=previous.plot.plot_id,
                            plot_version=previous.plot.plot_version,
                            content_hash=previous.content_hash,
                        )
                    }
                ),
            }
        )
        final_stored = StoredPlot(
            plot=final,
            field_mapping=previous.field_mapping,
            preparation_spec=previous.preparation_spec,
            prepared_dataset=previous.prepared_dataset,
            render_bindings=previous.render_bindings,
            content_hash=canonical_hash(final),
        )
        self._resolve_plot(session, final_stored)
        response = self._plot_response(
            session,
            final,
            previous.prepared_dataset,
            project_version=session.domain.revision + 1,
        )
        session.domain.commit_plot_patch(
            previous=previous,
            plot=final,
            operation="agent.plots.patch_transaction",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        return session.domain.get_plot(final.plot_id)

    @staticmethod
    def _stored_plot_context_ref(alias: str, stored: StoredPlot) -> ContextObjectRef:
        return ContextObjectRef(
            object_alias=alias,
            object_id=stored.plot.plot_id,
            object_version=stored.plot.plot_version,
            object_type="plot",
            content_hash=stored.content_hash,
        )

    @staticmethod
    def _agent_runtime_target(
        snapshot: ProjectContextSnapshot,
        plan: TaskPlanSnapshot,
        item: TaskItemSnapshot,
    ) -> ContextObjectRef:
        items = {value.task_item_id: value for value in plan.items}
        for dependency_id in reversed(item.depends_on):
            for output in items[dependency_id].outputs:
                if output.object_ref is not None:
                    return output.object_ref
        action_alias = item.action.target_alias
        known = {
            value.object_alias: value
            for value in (
                snapshot.known_objects
                + snapshot.recent_result_objects
                + (snapshot.conversation_state.current_target,)
            )
        }
        target = known.get(action_alias) or known.get(plan.source_plan.target_alias)
        if target is None:
            raise TaskExecutionError(
                "AGENT_ACTION_SCOPE_INVALID",
                "The persisted action target is unavailable.",
            )
        return target

    @staticmethod
    def _plots_for_context_target(
        session: ProjectSession, target: ContextObjectRef
    ) -> tuple[StoredPlot, ...]:
        if target.object_type == "plot":
            return (session.domain.get_plot(target.object_id),)
        if target.object_type == "batch":
            batch, _state = session.domain.get_batch(target.object_id)
            refs = tuple(
                item.plot_version_ref
                for item in batch.item_states
                if item.state == "succeeded" and item.plot_version_ref is not None
            )
            if not refs:
                raise TaskExecutionError("BATCH_SCOPE_EMPTY", "The batch has no plots.")
            return tuple(session.domain.get_plot(ref.plot_id) for ref in refs)
        if target.object_type == "figure":
            figure = session.domain.get_figure(target.object_id)
            return tuple(
                session.domain.get_plot(panel.plot_version_ref.plot_id) for panel in figure.panels
            )
        raise TaskExecutionError(
            "AGENT_ACTION_SCOPE_INVALID",
            "A patch action requires a plot, batch, or figure target.",
        )

    def _update_conversation_after_plan(
        self, session: ProjectSession, plan: TaskPlanSnapshot
    ) -> None:
        object_outputs = [
            output.object_ref
            for item in plan.items
            for output in item.outputs
            if output.object_ref is not None
        ]
        if not object_outputs:
            return
        projection = session.agent_runtime.get_conversation_state(plan.conversation_id)
        if projection is None:
            return
        updated = ConversationStateReducer().record_execution_result(
            ConversationState.from_projection(projection),
            target=object_outputs[-1],
        )
        session.agent_runtime.save_conversation_state(
            plan.conversation_id,
            updated.project(),
            expected_state_version=projection.state_version,
            context_hash=plan.context_hash,
        )

    @staticmethod
    def _agent_change_set(plan: TaskPlanSnapshot) -> RpcJsonValue:
        return cast(
            RpcJsonValue,
            {
                "plan_id": plan.plan_id,
                "state": plan.state,
                "items": [
                    {
                        "task_item_id": item.task_item_id,
                        "action_id": item.action.action_id,
                        "action_type": item.action.action_type,
                        "state": item.state,
                        "attempt_count": item.attempt_count,
                        "before": [
                            value.model_dump(mode="json") for value in item.expected_objects
                        ],
                        "after": [value.model_dump(mode="json") for value in item.outputs],
                        "failure": (
                            None if item.failure is None else item.failure.model_dump(mode="json")
                        ),
                    }
                    for item in plan.items
                ],
            },
        )

    def _commit_agent_scope_update(
        self,
        session: ProjectSession,
        target: ContextObjectRef,
        updated_plots: tuple[StoredPlot, ...],
        project_revision: int,
        decision: ActionPlan,
    ) -> tuple[RpcJsonValue, int]:
        latest_refs = {
            item.plot.plot_id: PlotSpecRef(
                plot_id=item.plot.plot_id,
                plot_version=item.plot.plot_version,
                content_hash=item.content_hash,
            )
            for item in updated_plots
        }
        idempotency_key = f"{decision.plan_id}:scope-update"
        if target.object_type == "batch":
            batch, state = session.domain.get_batch(target.object_id)
            item_states = tuple(
                BatchItemState.model_validate(
                    {
                        **item.model_dump(mode="python"),
                        "plot_version_ref": (
                            None
                            if item.plot_version_ref is None
                            else latest_refs.get(
                                item.plot_version_ref.plot_id,
                                item.plot_version_ref,
                            )
                        ),
                    }
                )
                for item in batch.item_states
            )
            updated_batch = BatchSpec.model_validate(
                {
                    **batch.model_dump(mode="python"),
                    "batch_version": batch.batch_version + 1,
                    "item_states": item_states,
                }
            )
            request_hash = canonical_hash(updated_batch)
            response: dict[str, RpcJsonValue] = {
                "target_kind": "batch",
                "target_id": updated_batch.batch_id,
                "target_version": updated_batch.batch_version,
                "project_version": project_revision + 1,
                "updated_plot_count": len(updated_plots),
                "batch": updated_batch.model_dump(mode="json"),
            }
            session.domain.save_batch(
                updated_batch,
                state,
                expected_revision=project_revision,
                operation="agent.batch.patch",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
            )
            return cast(RpcJsonValue, response), project_revision + 1
        if target.object_type == "figure":
            figure = session.domain.get_figure(target.object_id)
            panels = tuple(
                FigurePanel.model_validate(
                    {
                        **panel.model_dump(mode="python"),
                        "plot_version_ref": latest_refs.get(
                            panel.plot_version_ref.plot_id,
                            panel.plot_version_ref,
                        ),
                    }
                )
                for panel in figure.panels
            )
            updated_figure = FigureSpec.model_validate(
                {
                    **figure.model_dump(mode="python"),
                    "figure_version": figure.figure_version + 1,
                    "parent_figure_version": figure.figure_version,
                    "panels": panels,
                }
            )
            request_hash = canonical_hash(updated_figure)
            response = {
                "target_kind": "figure",
                "target_id": updated_figure.figure_id,
                "target_version": updated_figure.figure_version,
                "project_version": project_revision + 1,
                "updated_plot_count": len(updated_plots),
                "figure": updated_figure.model_dump(mode="json"),
            }
            session.domain.save_figure(
                updated_figure,
                expected_revision=project_revision,
                operation="agent.figure.patch",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=response,
            )
            return cast(RpcJsonValue, response), project_revision + 1
        raise RpcServiceError(
            "AGENT_ACTION_SCOPE_INVALID",
            "The Agent scope update target is invalid.",
        )

    def _agent_target(
        self,
        session: ProjectSession,
        source: SourceDataset,
        values: Mapping[str, RpcJsonValue],
    ) -> tuple[
        ContextObjectRef,
        tuple[ContextObjectRef, ...],
        tuple[StoredPlot, ...],
        dict[str, StoredPlot],
    ]:
        scope = _optional_text(values.get("scope"), "scope") or "current"
        if scope not in {"current", "selected", "batch", "figure"}:
            raise RpcServiceError("INVALID_PARAMS", "The Agent scope is invalid.")
        target_value = values.get("target")
        if target_value is None:
            if scope not in {"current", "selected"}:
                raise RpcServiceError(
                    "AGENT_ACTION_SCOPE_INVALID",
                    "The requested Agent scope has no matching target object.",
                )
            return (
                ContextObjectRef(
                    object_alias="active_target",
                    object_id=source.source_dataset_id,
                    object_version=source.source_version,
                    object_type="source_dataset",
                    content_hash=source.content_hash,
                ),
                (),
                (),
                {},
            )
        target_input = _object(target_value, required={"kind", "id"})
        kind = _text(target_input["kind"], "target.kind")
        expected_kind = "plot" if scope in {"current", "selected"} else scope
        if kind != expected_kind:
            raise RpcServiceError(
                "AGENT_ACTION_SCOPE_INVALID",
                "The requested Agent scope does not match its target object.",
            )
        target_id = _text(target_input["id"], "target.id")
        stored_plots: tuple[StoredPlot, ...]
        if kind == "plot":
            stored_plots = (session.domain.get_plot(target_id),)
            object_version = stored_plots[0].plot.plot_version
            content_hash = stored_plots[0].content_hash
        elif kind == "batch":
            batch, _state = session.domain.get_batch(target_id)
            refs = tuple(
                item.plot_version_ref
                for item in batch.item_states
                if item.state == "succeeded" and item.plot_version_ref is not None
            )
            if not refs:
                raise RpcServiceError(
                    "BATCH_SCOPE_EMPTY",
                    "The batch contains no succeeded plots to edit.",
                )
            stored_plots = tuple(
                session.domain.get_plot(ref.plot_id, ref.plot_version) for ref in refs
            )
            object_version = batch.batch_version
            content_hash = canonical_hash(batch)
        elif kind == "figure":
            figure = session.domain.get_figure(target_id)
            stored_plots = tuple(
                session.domain.get_plot(
                    panel.plot_version_ref.plot_id,
                    panel.plot_version_ref.plot_version,
                )
                for panel in figure.panels
            )
            object_version = figure.figure_version
            content_hash = canonical_hash(figure)
        else:
            raise RpcServiceError("INVALID_PARAMS", "The Agent target kind is invalid.")
        target = ContextObjectRef(
            object_alias="active_target",
            object_id=target_id,
            object_version=object_version,
            object_type=cast(Any, kind),
            content_hash=content_hash,
        )
        primary = stored_plots[0]
        target_aliases = [
            "x_axis",
            "y_axis",
            *(
                ["right_y_axis"]
                if any(
                    axis.orientation == "y" and axis.position == "right"
                    for axis in primary.plot.axes
                )
                else []
            ),
            *(f"series_{index + 1}" for index, _series in enumerate(primary.plot.series)),
        ]
        aliases: tuple[ContextObjectRef, ...] = tuple(
            ContextObjectRef(
                object_alias=alias,
                object_id=primary.plot.plot_id,
                object_version=primary.plot.plot_version,
                object_type="plot",
                content_hash=primary.content_hash,
            )
            for alias in target_aliases
        )
        plots_by_alias: dict[str, StoredPlot] = {"active_target": primary}
        if len(stored_plots) > 1:
            plot_aliases = tuple(
                ContextObjectRef(
                    object_alias=f"plot_{index + 1}",
                    object_id=item.plot.plot_id,
                    object_version=item.plot.plot_version,
                    object_type="plot",
                    content_hash=item.content_hash,
                )
                for index, item in enumerate(stored_plots[:8])
            )
            aliases += plot_aliases
            plots_by_alias.update(
                {f"plot_{index + 1}": item for index, item in enumerate(stored_plots[:8])}
            )
        return target, aliases, stored_plots, plots_by_alias

    @staticmethod
    def _agent_patch_payload(previous: StoredPlot, intent: Any) -> RpcJsonValue:
        target_by_alias = {
            f"series_{index + 1}": series.series_id
            for index, series in enumerate(previous.plot.series)
        }
        for axis in previous.plot.axes:
            if axis.orientation == "x" and axis.position != "none":
                target_by_alias["x_axis"] = axis.axis_id
            elif axis.orientation == "y" and axis.position == "right":
                target_by_alias["right_y_axis"] = axis.axis_id
            elif axis.orientation == "y":
                target_by_alias["y_axis"] = axis.axis_id
        target_id = target_by_alias.get(intent.target_alias)
        if isinstance(
            intent,
            (
                CanvasSizeIntent,
                PlotTitleIntent,
                FontSizeIntent,
                AddAnnotationIntent,
                BarAreaStyleIntent,
                UncertaintyStyleIntent,
                ColorbarStyleIntent,
                DualYAxisStyleIntent,
                FacetStyleIntent,
                YOffsetStyleIntent,
                ChartParametersIntent,
            ),
        ):
            target_id = previous.plot.plot_id
        elif isinstance(intent, (LegendVisibilityIntent, LegendPlacementIntent)):
            target_id = "legend:main"
        if target_id is None:
            raise RpcServiceError(
                "AGENT_ACTION_SCOPE_INVALID", "The patch target alias is not editable."
            )
        common: dict[str, RpcJsonValue] = {
            "operation": intent.operation,
            "target_id": target_id,
            "expected_plot_version": previous.plot.plot_version,
        }
        if isinstance(intent, PlotTitleIntent):
            common["title"] = (
                None
                if intent.title is None
                else {"nodes": [{"kind": "plain", "text": intent.title}]}
            )
        elif isinstance(intent, AxisRangeIntent):
            common.update({"minimum": intent.minimum, "maximum": intent.maximum})
        elif isinstance(intent, AxisScaleIntent):
            common["scale"] = intent.scale
        elif isinstance(intent, AxisLabelIntent):
            common["label"] = {"nodes": [{"kind": "plain", "text": intent.label}]}
        elif isinstance(intent, AxisReverseIntent):
            common["reverse"] = intent.reverse
        elif isinstance(intent, AxisTicksIntent):
            common["ticks"] = {
                "major_interval": intent.major_interval,
                "number_format": intent.number_format,
                "decimal_places": intent.decimal_places,
            }
        elif isinstance(intent, FontSizeIntent):
            common["size"] = {"value": intent.size_pt, "unit": "pt"}
        elif isinstance(
            intent,
            (
                BarAreaStyleIntent,
                UncertaintyStyleIntent,
                ColorbarStyleIntent,
                DualYAxisStyleIntent,
                FacetStyleIntent,
                YOffsetStyleIntent,
            ),
        ):
            common["style"] = cast(
                RpcJsonValue,
                intent.style.model_dump(mode="json"),
            )
        elif isinstance(intent, ChartParametersIntent):
            common["parameters"] = cast(
                RpcJsonValue,
                intent.parameters.model_dump(mode="json"),
            )
        elif isinstance(intent, SeriesStyleIntent):
            if intent.color is not None:
                common["color"] = cast(RpcJsonValue, intent.color.model_dump(mode="json"))
            if intent.line_width_pt is not None:
                common["line_width"] = {"value": intent.line_width_pt, "unit": "pt"}
            if intent.marker_size_pt is not None:
                common["marker_size"] = {"value": intent.marker_size_pt, "unit": "pt"}
            if intent.line_style is not None:
                common["line_style"] = intent.line_style
            if intent.symbol_shape is not None or intent.symbol_interior is not None:
                target_series = next(
                    series for series in previous.plot.series if series.series_id == target_id
                )
                current = target_series.style.symbol
                common["symbol"] = SymbolStyle(
                    shape=intent.symbol_shape or current.shape,
                    interior=intent.symbol_interior or current.interior,
                ).model_dump(mode="json")
        elif isinstance(intent, CategoryColorIntent):
            common["category"] = intent.category
            common["color"] = cast(RpcJsonValue, intent.color.model_dump(mode="json"))
        elif isinstance(intent, PaletteIntent):
            common.update({"palette_id": intent.palette_id, "reverse": intent.reverse})
        elif isinstance(intent, LegendVisibilityIntent):
            common["visible"] = intent.visible
        elif isinstance(intent, LegendPlacementIntent):
            common.update(
                {
                    "placement": intent.placement,
                    "anchor_x": previous.plot.legend.anchor_x,
                    "anchor_y": previous.plot.legend.anchor_y,
                }
            )
        elif isinstance(intent, CanvasSizeIntent):
            common["physical_size"] = intent.physical_size.model_dump(mode="json")
        elif isinstance(intent, AddAnnotationIntent):
            common["annotation"] = {
                "annotation_id": (
                    f"annotation:agent.{previous.plot.plot_id.removeprefix('plot:')}."
                    f"v{previous.plot.plot_version + 1}"
                ),
                "kind": intent.kind,
                "text": (
                    None
                    if intent.text is None
                    else {"nodes": [{"kind": "plain", "text": intent.text}]}
                ),
                "x": intent.x,
                "y": intent.y,
                "x2": intent.x2,
                "y2": intent.y2,
                "affect_range": intent.affect_range,
            }
        else:
            raise RpcServiceError(
                "PATCH_OPERATION_UNSUPPORTED", "The Agent patch operation is not enabled."
            )
        return cast(RpcJsonValue, common)

    def _compile_plot_bundle(
        self,
        plot_id: str,
        chart_type_id: str,
        source: SourceDataset,
        source_table: Any,
        bindings: dict[str, str],
        provenance_origin: Literal["manual", "agent_plan"],
        plan_id: str | None,
    ) -> tuple[
        FieldMapping,
        SelectFieldsSpec,
        PreparedArtifact,
        PlotSpec,
        ResolvedPlot,
        dict[str, bytes],
    ]:
        try:
            internal_registration = get_chart(chart_type_id)
            registration = CONTRACT_CHARTS_BY_ID[cast(Any, chart_type_id)]
        except ChartRegistryError:
            raise RpcServiceError(
                "CHART_TYPE_UNKNOWN", "The requested chart type is not in the v1 registry."
            ) from None
        if internal_registration.admission != "product":
            if internal_registration.admission == "removed":
                raise RpcServiceError(
                    "CHART_TYPE_REMOVED",
                    "The requested chart type was removed from the 38-chart product surface.",
                )
            raise RpcServiceError(
                "CHART_TYPE_NOT_ADMITTED",
                "The chart adapter is retained for internal regression but is not "
                "product-qualified.",
            )
        if chart_type_id == "K25":
            raise RpcServiceError(
                "CHART_REQUIRES_FIGURE",
                "K25 is created through figures.create from explicit child plots.",
            )
        variadic_series_chart = chart_type_id in {"X03", "X39", "X40"}
        series_roles = _variadic_series_roles(bindings) if variadic_series_chart else ()
        required_roles = {
            role for role in registration.required_roles if not role.startswith("series_")
        }
        if not required_roles.issubset(bindings) or (
            variadic_series_chart and len(series_roles) < 2
        ):
            raise RpcServiceError(
                "MAPPING_ROLE_MISSING",
                "The field mapping does not provide every required chart role.",
            )
        allowed_roles = required_roles | set(registration.optional_roles) | set(series_roles)
        if set(bindings) - allowed_roles:
            raise RpcServiceError(
                "MAPPING_ROLE_UNKNOWN",
                "The field mapping contains a role not declared by the chart registry.",
            )
        fields = {field.field_id: field for field in source.field_schema}
        if not set(bindings.values()).issubset(fields):
            raise RpcServiceError("MAPPING_FIELD_MISSING", "A mapped field was not found.")
        source_ref = _source_ref(source)
        mapping_id = "mapping:" + plot_id.removeprefix("plot:")
        mapping_payload: JsonValue = {
            "plot_id": plot_id,
            "chart_type_id": chart_type_id,
            "source_ref": source_ref.model_dump(mode="json"),
            "bindings": cast(JsonValue, bindings),
        }
        mapping = FieldMapping(
            field_mapping_id=mapping_id,
            mapping_version=1,
            chart_type_id=cast(Any, chart_type_id),
            source_dataset_refs=(source_ref,),
            bindings=tuple(
                FieldRoleBinding(
                    role=role,
                    field=FieldSnapshot(
                        field_id=bindings[role],
                        name=fields[bindings[role]].name,
                        logical_type=fields[bindings[role]].logical_type,
                        unit=fields[bindings[role]].unit,
                        source_dataset_ref=source_ref,
                    ),
                )
                for role in (
                    tuple(role for role in registration.required_roles if role in bindings)
                    + tuple(
                        role for role in series_roles if role not in registration.required_roles
                    )
                    + tuple(role for role in registration.optional_roles if role in bindings)
                )
            ),
            content_hash=canonical_hash(mapping_payload),
        )
        preparation_spec = SelectFieldsSpec(
            preparation_spec_id="preparation:" + plot_id.removeprefix("plot:"),
            preparation_version=1,
            input_refs=(source_ref,),
            field_mapping_ref=FieldMappingRef(
                field_mapping_id=mapping.field_mapping_id,
                mapping_version=mapping.mapping_version,
                content_hash=mapping.content_hash,
            ),
            compiler_version="preparation.compiler.v1",
            field_ids=tuple(dict.fromkeys(bindings.values())),
        )
        prepared = prepare(
            (source,),
            mapping,
            preparation_spec,
            _FixedSourceResolver(source_table),
        )
        prepared_ref = prepared.prepared_dataset.as_ref()
        prepared_columns = {
            field.field_id: tuple(row[index] for row in prepared.rows)
            for index, field in enumerate(prepared.fields)
        }
        calculation_result: PlotCalculationResult | None = None
        calculation_table: RenderTable | None = None
        calculation_payload: bytes | None = None
        if registration.required_calculations:
            calculation_spec = self._calculation_spec(
                chart_type_id,
                plot_id,
                prepared_ref,
                bindings,
            )
            calculation_input = PlotCalculationInput(
                row_ids=tuple(item.source_row_id for item in prepared.coordinates),
                columns=prepared_columns,
            )
            calculation_result = calculate_plot(
                calculation_spec,
                calculation_input,
                producer_build_hash=_ENGINE_HASH,
            )
            calculated_columns = _calculation_columns(chart_type_id, calculation_result)
            calculation_table = RenderTable.from_columns(calculated_columns)
            calculation_payload = _columns_to_parquet(calculated_columns)

        precomputed_ref: PrecomputedDataRef | None = None
        if registration.required_precomputed:
            precomputed_ref = PrecomputedDataRef(
                precomputed_id="precomputed:" + plot_id.removeprefix("plot:"),
                precomputed_version=1,
                precomputed_kind=registration.required_precomputed[0],
                content_hash=canonical_hash(
                    cast(
                        JsonValue,
                        {
                            "plot_id": plot_id,
                            "kind": registration.required_precomputed[0],
                            "field_ids": list(prepared_columns),
                        },
                    )
                ),
                data_ref_hash=prepared.prepared_dataset.output_hash,
                field_ids=tuple(prepared_columns),
            )

        series_specs: list[SeriesSpec] = []
        data_store: dict[str, RenderTable] = {
            prepared_ref.content_hash: RenderTable.from_columns(prepared_columns)
        }
        calculation_ref: PlotCalculationResultRef | None = None
        if calculation_result is not None and calculation_table is not None:
            calculation_ref = PlotCalculationResultRef(
                calculation_id=calculation_result.calculation_id,
                result_version=calculation_result.result_version,
                calculation_kind=calculation_result.kind,
                content_hash=calculation_result.output_hash,
            )
            data_store[calculation_ref.content_hash] = calculation_table
        if precomputed_ref is not None:
            data_store[precomputed_ref.data_ref_hash] = RenderTable.from_columns(prepared_columns)

        for index, geometry in enumerate(registration.geometries):
            roles: tuple[str, ...] | None = None
            rule = get_series_rule(cast(Any, chart_type_id), geometry)
            if "calculated" in rule.data_kinds and calculation_ref is not None:
                assert calculation_table is not None
                role_fields = _calculated_role_fields(
                    chart_type_id,
                    rule.role_signatures,
                    calculation_table.field_ids,
                )
                data: Any = CalculatedSeriesData(
                    calculation_result_ref=calculation_ref,
                    role_fields=role_fields,
                )
            elif "precomputed" in rule.data_kinds and precomputed_ref is not None:
                roles = (
                    (("category",) if chart_type_id == "X03" else ()) + series_roles
                    if variadic_series_chart
                    else _matching_roles(rule.role_signatures, bindings)
                )
                if roles is None:
                    continue
                data = PrecomputedSeriesData(
                    precomputed_data_ref=precomputed_ref,
                    role_fields=tuple(bindings[role] for role in roles),
                )
            elif "prepared" in rule.data_kinds:
                roles = (
                    (("category",) if chart_type_id == "X03" else ()) + series_roles
                    if variadic_series_chart
                    else _matching_roles(rule.role_signatures, bindings)
                )
                if chart_type_id == "K06" and geometry == "symbol" and roles is None:
                    roles = ("x", "center")
                    prepared_columns["field:plotagent.row_index"] = tuple(range(len(prepared.rows)))
                    data_store[prepared_ref.content_hash] = RenderTable.from_columns(
                        prepared_columns
                    )
                if roles is None:
                    continue
                role_fields = tuple(
                    "field:plotagent.row_index"
                    if role == "x" and role not in bindings
                    else bindings[role]
                    for role in roles
                )
                data = PreparedSeriesData(
                    prepared_dataset_ref=prepared_ref,
                    role_fields=role_fields,
                )
            else:
                continue
            series_specs.append(
                SeriesSpec(
                    series_id=f"series:{plot_id.removeprefix('plot:')}.{index}",
                    geometry=geometry,
                    data=data,
                    label=_default_series_label(roles or (), bindings, fields),
                )
            )
        if not series_specs:
            raise RpcServiceError(
                "MAPPING_SHAPE_UNSUPPORTED",
                "The supplied fields cannot satisfy a qualified series shape for this chart.",
            )

        x_label, y_label = _axis_labels(
            chart_type_id,
            registration.required_roles,
            bindings,
            fields,
        )
        if chart_type_id == "X13":
            x_label = f"{fields[bindings['left']].name} / {fields[bindings['right']].name}"
            y_label = fields[bindings["category"]].name
        if chart_type_id == "X03":
            x_label = "Value"
            y_label = fields[bindings["category"]].name
        elif chart_type_id in {"X39", "X40"}:
            x_label = "Series"
            y_label = "Value"
        x_scale_kind, y_scale_kind = _axis_scale_kinds(chart_type_id, bindings, fields)
        dual_axis = chart_type_id in {"X23", "X24", "X35", "X36", "X37"}
        scales: tuple[ScaleSpec, ...] = (
            ScaleSpec(scale_id="scale:x", kind=x_scale_kind),
            ScaleSpec(scale_id="scale:y", kind=y_scale_kind),
        )
        axes: tuple[AxisSpec, ...] = (
            AxisSpec(
                axis_id="axis:x",
                scale_id="scale:x",
                orientation="x",
                position="bottom",
                label=_rich_text(x_label),
            ),
            AxisSpec(
                axis_id="axis:y",
                scale_id="scale:y",
                orientation="y",
                position="left",
                label=_rich_text(y_label),
            ),
        )
        if dual_axis:
            right_label = (
                "Cumulative (%)" if chart_type_id == "X24" else fields[bindings["right"]].name
            )
            scales += (ScaleSpec(scale_id="scale:y_right", kind="linear"),)
            axes += (
                AxisSpec(
                    axis_id="axis:y_right",
                    scale_id="scale:y_right",
                    orientation="y",
                    position="right",
                    label=_rich_text(right_label),
                ),
            )
        plot = PlotSpec(
            plot_id=plot_id,
            plot_version=1,
            chart_type_id=cast(Any, chart_type_id),
            family=_plot_family(registration.family, tuple(item.geometry for item in series_specs)),
            prepared_data_refs=(prepared_ref,),
            precomputed_data_refs=(() if precomputed_ref is None else (precomputed_ref,)),
            plot_calculation_refs=(() if calculation_ref is None else (calculation_ref,)),
            scales=scales,
            axes=axes,
            series=tuple(series_specs),
            style_sources=(
                StyleSourceRef(
                    source_kind="project",
                    source_id="style.default",
                    source_version=1,
                    content_hash=_STYLE_HASH,
                ),
            ),
            resolved_style=self._style(),
            publication_profile=self._profile(89.0, 60.0),
            provenance=PlotProvenance(
                origin=provenance_origin,
                plan_id=plan_id,
                engine_build_hash=_ENGINE_HASH,
            ),
        )
        resolved = PlotResolver().resolve(
            plot,
            RenderDataStore(data_store),
            quality_tier="formal",
        )
        render_artifacts: dict[str, bytes] = {}
        if prepared_columns.keys() != {field.field_id for field in prepared.fields}:
            render_artifacts[prepared_ref.content_hash] = _columns_to_parquet(prepared_columns)
        if calculation_ref is not None and calculation_payload is not None:
            render_artifacts[calculation_ref.content_hash] = calculation_payload
        return mapping, preparation_spec, prepared, plot, resolved, render_artifacts

    @staticmethod
    def _calculation_spec(
        chart_type_id: str,
        plot_id: str,
        prepared_ref: PreparedDatasetRef,
        bindings: Mapping[str, str],
    ) -> PlotCalculationSpec:
        common: dict[str, Any] = {
            "calculation_id": "plotcalc:" + plot_id.removeprefix("plot:"),
            "calculation_version": 1,
            "prepared_dataset_ref": prepared_ref,
            "algorithm_version": ALGORITHM_VERSION,
            "missing_policy": "exclude_with_report",
        }
        if chart_type_id == "K11":
            return PercentStackSpec(
                **common,
                category_field=bindings["category"],
                component_field=bindings["component"],
                value_field=bindings["value"],
            )
        if chart_type_id == "K13":
            return TukeyBoxSpec(
                **common,
                value_field=bindings["value"],
                group_field=bindings.get("group"),
            )
        if chart_type_id == "K14":
            return ViolinKDESpec(
                **common,
                value_field=bindings["value"],
                group_field=bindings.get("group"),
            )
        if chart_type_id == "K15":
            return HistogramBinningSpec(**common, value_field=bindings["value"])
        if chart_type_id == "K16":
            return DensityKDESpec(
                **common,
                value_field=bindings["value"],
                group_field=bindings.get("group"),
            )
        if chart_type_id == "K17":
            return ECDFSpec(**common, value_field=bindings["value"])
        if chart_type_id == "S61":
            return ConfusionCountSpec(
                **common,
                actual_field=bindings["actual"],
                predicted_field=bindings["predicted"],
                count_field=bindings.get("count"),
            )
        raise RpcServiceError(
            "CALCULATION_UNSUPPORTED",
            "The chart's required fixed calculation is not implemented.",
        )

    def _apply_patch(self, previous: StoredPlot, patch: PlotPatch) -> PlotSpec:
        plot = previous.plot
        validate_plot_patch(plot, patch)
        update: dict[str, Any] = {}
        if isinstance(patch, SetPlotTitlePatch):
            update["title"] = patch.title
        elif isinstance(patch, SetAxisScalePatch):
            axis = next(axis for axis in plot.axes if axis.axis_id == patch.target_id)
            update["scales"] = tuple(
                scale.model_copy(update={"kind": patch.scale})
                if scale.scale_id == axis.scale_id
                else scale
                for scale in plot.scales
            )
        elif isinstance(patch, SetAxisRangePatch):
            axis = next(axis for axis in plot.axes if axis.axis_id == patch.target_id)
            update["scales"] = tuple(
                scale.model_copy(
                    update={
                        "axis_range": scale.axis_range.model_copy(
                            update={"minimum": patch.minimum, "maximum": patch.maximum}
                        )
                    }
                )
                if scale.scale_id == axis.scale_id
                else scale
                for scale in plot.scales
            )
        elif isinstance(patch, SetAxisReversePatch):
            axis = next(axis for axis in plot.axes if axis.axis_id == patch.target_id)
            update["scales"] = tuple(
                scale.model_copy(
                    update={
                        "axis_range": scale.axis_range.model_copy(update={"reverse": patch.reverse})
                    }
                )
                if scale.scale_id == axis.scale_id
                else scale
                for scale in plot.scales
            )
        elif isinstance(patch, SetAxisTicksPatch):
            axis = next(axis for axis in plot.axes if axis.axis_id == patch.target_id)
            update["scales"] = tuple(
                scale.model_copy(update={"ticks": patch.ticks})
                if scale.scale_id == axis.scale_id
                else scale
                for scale in plot.scales
            )
        elif isinstance(patch, SetAxisLabelPatch):
            update["axes"] = tuple(
                axis.model_copy(update={"label": patch.label})
                if axis.axis_id == patch.target_id
                else axis
                for axis in plot.axes
            )
        elif isinstance(patch, SetFontSizePatch):
            update["resolved_style"] = plot.resolved_style.model_copy(
                update={"font_size": patch.size}
            )
        elif isinstance(patch, SetBarAreaStylePatch):
            update["specialist"] = plot.specialist.model_copy(update={"bar_area": patch.style})
        elif isinstance(patch, SetUncertaintyStylePatch):
            update["specialist"] = plot.specialist.model_copy(update={"uncertainty": patch.style})
        elif isinstance(patch, SetColorbarStylePatch):
            update["specialist"] = plot.specialist.model_copy(update={"colorbar": patch.style})
        elif isinstance(patch, SetDualYAxisStylePatch):
            update["specialist"] = plot.specialist.model_copy(update={"dual_y": patch.style})
        elif isinstance(patch, SetFacetStylePatch):
            update["specialist"] = plot.specialist.model_copy(update={"facet": patch.style})
        elif isinstance(patch, SetYOffsetStylePatch):
            update["specialist"] = plot.specialist.model_copy(update={"y_offset": patch.style})
        elif isinstance(patch, SetChartParametersPatch):
            update["specialist"] = plot.specialist.model_copy(
                update={"chart_parameters": patch.parameters}
            )
        elif isinstance(patch, SetSeriesStylePatch):
            style_update = {
                key: value
                for key, value in {
                    "color": patch.color,
                    "line_width": patch.line_width,
                    "marker_size": patch.marker_size,
                    "line_style": patch.line_style,
                    "symbol": patch.symbol,
                }.items()
                if value is not None
            }
            update["series"] = tuple(
                series.model_copy(update={"style": series.style.model_copy(update=style_update)})
                if series.series_id == patch.target_id
                else series
                for series in plot.series
            )
        elif isinstance(patch, SetPalettePatch):
            resolved_palette = resolve_palette(patch.palette_id, reverse=patch.reverse)
            update["series"] = tuple(
                series.model_copy(
                    update={"style": series.style.model_copy(update={"palette": resolved_palette})}
                )
                if series.series_id == patch.target_id
                else series
                for series in plot.series
            )
        elif isinstance(patch, SetCategoryColorPatch):
            update["series"] = tuple(
                series.model_copy(
                    update={
                        "style": series.style.model_copy(
                            update={
                                "category_colors": {
                                    **series.style.category_colors,
                                    patch.category: patch.color,
                                }
                            }
                        )
                    }
                )
                if series.series_id == patch.target_id
                else series
                for series in plot.series
            )
        elif isinstance(patch, SetLegendVisibilityPatch):
            update["legend"] = plot.legend.model_copy(update={"visible": patch.visible})
        elif isinstance(patch, MoveLegendPatch):
            update["legend"] = plot.legend.model_copy(
                update={
                    "placement": patch.placement,
                    "anchor_x": patch.anchor_x,
                    "anchor_y": patch.anchor_y,
                }
            )
        elif isinstance(patch, AddAnnotationPatch):
            update["annotations"] = (*plot.annotations, patch.annotation)
        elif isinstance(patch, UpdateAnnotationPatch):
            update["annotations"] = tuple(
                patch.annotation
                if annotation.annotation_id == patch.annotation.annotation_id
                else annotation
                for annotation in plot.annotations
            )
        elif isinstance(patch, RemoveAnnotationPatch):
            update["annotations"] = tuple(
                annotation
                for annotation in plot.annotations
                if annotation.annotation_id != patch.annotation_id
            )
        elif isinstance(patch, ApplyPublicationProfilePatch):
            update["publication_profile"] = patch.profile
        elif isinstance(patch, SetCanvasSizePatch):
            update["publication_profile"] = plot.publication_profile.model_copy(
                update={"physical_size": patch.physical_size}
            )
        else:
            raise RpcServiceError(
                "PATCH_OPERATION_UNSUPPORTED",
                "The current desktop slice does not execute this patch operation.",
            )
        update["plot_version"] = plot.plot_version + 1
        update["provenance"] = plot.provenance.model_copy(
            update={
                "parent_plot_ref": PlotSpecRef(
                    plot_id=plot.plot_id,
                    plot_version=plot.plot_version,
                    content_hash=previous.content_hash,
                )
            }
        )
        return plot.model_copy(update=update)

    def _resolve_plot(
        self,
        session: ProjectSession,
        stored: StoredPlot,
        *,
        quality_tier: Literal["interactive", "formal"] = "formal",
    ) -> ResolvedPlot:
        tables = {
            binding_hash: RenderTable.from_columns(columns)
            for binding_hash, columns in session.domain.render_tables(stored).items()
        }
        return PlotResolver().resolve(
            stored.plot,
            RenderDataStore(tables),
            quality_tier=quality_tier,
        )

    def _resolve_figure(
        self,
        session: ProjectSession,
        figure: FigureSpec,
        *,
        quality_tier: Literal["interactive", "formal"] = "interactive",
    ) -> ResolvedPlot:
        if len(figure.panels) > 4:
            raise RpcServiceError(
                "FIGURE_LAYOUT_UNSUPPORTED",
                "The current desktop renderer supports up to four Figure panels.",
            )
        stored = tuple(
            session.domain.get_plot(
                panel.plot_version_ref.plot_id,
                panel.plot_version_ref.plot_version,
            )
            for panel in figure.panels
        )
        children = tuple(
            self._resolve_plot(session, item, quality_tier=quality_tier) for item in stored
        )
        first = stored[0]
        placeholder = first.prepared_dataset.as_ref()
        parent = PlotSpec(
            plot_id=f"plot:figure.{figure.figure_id.removeprefix('figure:')}",
            plot_version=figure.figure_version,
            chart_type_id="K25",
            family=FacetFamily(geometry=("panel",)),
            prepared_data_refs=(placeholder,),
            scales=first.plot.scales,
            axes=first.plot.axes,
            series=(
                SeriesSpec(
                    series_id="series:figure.panels",
                    geometry="panel",
                    data=PreparedSeriesData(
                        prepared_dataset_ref=placeholder,
                        role_fields=("field:panel",),
                    ),
                ),
            ),
            style_sources=first.plot.style_sources,
            resolved_style=first.plot.resolved_style,
            publication_profile=figure.publication_profile.model_copy(
                update={"physical_size": figure.physical_size}
            ),
            provenance=PlotProvenance(origin="manual", engine_build_hash=_ENGINE_HASH),
        )
        placements = self._figure_placements(figure, children)
        return PlotResolver().resolve_panel_plans(
            parent,
            placements,
            quality_tier=quality_tier,
        )

    def _figure_placements(
        self, figure: FigureSpec, children: tuple[ResolvedPlot, ...]
    ) -> tuple[PanelPlan, ...]:
        rows_text, columns_text = figure.layout.split("x", maxsplit=1)
        rows, columns = int(rows_text), int(columns_text)
        width = figure.physical_size.width.value
        height = figure.physical_size.height.value
        margin = 5.0
        gap = 3.0
        panel_width = (width - margin * 2 - gap * (columns - 1)) / columns
        panel_height = (height - margin * 2 - gap * (rows - 1)) / rows
        return tuple(
            PanelPlan(
                panel_id=panel.panel_id,
                resolved_plot=children[index],
                left_mm=margin + (index % columns) * (panel_width + gap),
                top_mm=margin + (index // columns) * (panel_height + gap),
                width_mm=panel_width,
                height_mm=panel_height,
                panel_label=panel.panel_label,
            )
            for index, panel in enumerate(figure.panels)
        )

    def _agent_fields(
        self, source: SourceDataset, rows: tuple[tuple[Any, ...], ...]
    ) -> tuple[tuple[AuthoritativeField, ...], dict[str, str]]:
        aliases: dict[str, str] = {}
        fields: list[AuthoritativeField] = []
        for index, field in enumerate(source.field_schema):
            alias = "x_field" if index == 0 else "y_field" if index == 1 else f"field_{index}"
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
                    name=field.name,
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

    def _dataset_signature(
        self, source: SourceDataset, bindings: dict[str, str]
    ) -> DatasetSignature:
        fields = {field.field_id: field for field in source.field_schema}
        signature_fields = tuple(
            DatasetFieldSignature(
                field_id=field_id,
                logical_type=fields[field_id].logical_type,
                unit_hash=canonical_hash(fields[field_id].unit),
                semantic_role=role,
            )
            for role, field_id in sorted(bindings.items())
        )
        return DatasetSignature(
            fields=signature_fields,
            semantic_hash=canonical_hash(
                cast(
                    JsonValue,
                    [item.model_dump(mode="json") for item in signature_fields],
                )
            ),
        )

    def _plot_ref_value(self, session: ProjectSession, value: Any) -> PlotSpecRef:
        values = _object(
            cast(RpcJsonValue, value),
            required={"plot_id", "plot_version"},
        )
        session_plot_id = _text(values["plot_id"], "plot_id")
        version = _integer(values["plot_version"], "plot_version", minimum=1)
        try:
            stored = session.domain.get_plot(session_plot_id, version)
        except StorageProblem as error:
            raise RpcServiceError(
                "PLOT_NOT_FOUND", "The Figure source plot was not found."
            ) from error
        return PlotSpecRef(
            plot_id=session_plot_id,
            plot_version=version,
            content_hash=stored.content_hash,
        )

    @staticmethod
    def _style() -> ResolvedStyleSnapshot:
        return ResolvedStyleSnapshot(
            font_family="Arial",
            font_size=PhysicalLength(value=8.0, unit="pt"),
            line_width=PhysicalLength(value=0.8, unit="pt"),
            marker_size=PhysicalLength(value=4.0, unit="pt"),
            colors=tuple(
                ColorValue(value=value)
                for value in (
                    "#2A6FDB",
                    "#D64545",
                    "#2A9D6F",
                    "#E69F00",
                    "#7B61A8",
                    "#56B4E9",
                    "#8C6D31",
                    "#6B7280",
                )
            ),
        )

    @staticmethod
    def _profile(width: float, height: float) -> PublicationProfileSnapshot:
        return PublicationProfileSnapshot(
            profile_id="profile.desktop-default",
            profile_version=1,
            content_hash=_PROFILE_HASH,
            physical_size=PhysicalSize(
                width=PhysicalLength(value=width, unit="mm"),
                height=PhysicalLength(value=height, unit="mm"),
            ),
            dpi=300,
        )

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
        self, project_id: str, display_name: str | None, last_opened_at: str
    ) -> dict[str, RpcJsonValue]:
        return {
            "project_id": project_id,
            "resource_id": "resource:project." + project_id.removeprefix("project:"),
            "display_name": display_name,
            "last_opened_at": last_opened_at,
            "is_open": project_id in self._sessions,
        }

    def _session_summary(
        self, session: ProjectSession, *, replayed: bool
    ) -> dict[str, RpcJsonValue]:
        return {
            "project_id": session.project_id,
            "resource_id": "resource:project." + session.project_id.removeprefix("project:"),
            "project_version": session.domain.revision,
            "dataset_count": len(session.store.list_source_datasets()),
            "plot_count": len(session.domain.list_plots()),
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

    def _plot_response(
        self,
        session: ProjectSession,
        plot: PlotSpec,
        prepared: Any,
        *,
        project_version: int,
        task_id: str | None = None,
    ) -> dict[str, RpcJsonValue]:
        plot_content_hash = canonical_hash(plot)
        return {
            **({"task_id": task_id} if task_id is not None else {}),
            "project_id": session.project_id,
            "project_version": project_version,
            "plot_id": plot.plot_id,
            "plot_version": plot.plot_version,
            "plot_content_hash": plot_content_hash,
            "plot_ref": PlotSpecRef(
                plot_id=plot.plot_id,
                plot_version=plot.plot_version,
                content_hash=plot_content_hash,
            ).model_dump(mode="json"),
            "chart_type_id": plot.chart_type_id,
            "prepared_dataset_id": prepared.prepared_dataset_id,
            "prepared_version": prepared.prepared_version,
            "spec": plot.model_dump(mode="json"),
            "replayed": False,
        }

    def _batch_task_response(
        self, task: BatchTaskRecord, project_version: int
    ) -> dict[str, RpcJsonValue]:
        return {
            "task_id": task.request.task_id,
            "batch_id": task.request.batch_id,
            "state": task.state,
            "project_version": project_version,
            "items": [
                {
                    "item_id": item.work_item.item_id,
                    "state": item.phase,
                    "plot_ref": (
                        None if item.plot_ref is None else item.plot_ref.model_dump(mode="json")
                    ),
                    "error": None if item.error is None else item.error.model_dump(mode="json"),
                }
                for item in task.items
            ],
            "batch": None if task.batch_spec is None else task.batch_spec.model_dump(mode="json"),
            "replayed": False,
        }

    @staticmethod
    def _begin_task(context: RpcContext, prefix: str) -> str:
        suffix = hashlib.sha256(
            f"{prefix}\0{context.request_id}\0{uuid.uuid4().hex}".encode()
        ).hexdigest()[:24]
        task_id = f"task:{suffix}"
        context.tasks.register(task_id)
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
    def _fail_task(tasks: TaskRegistry, task_id: str) -> None:
        state = tasks.state(task_id)
        if state in {"preparing", "running", "committing"}:
            tasks.transition(task_id, "failed")


class _FixedSourceResolver(SourceTableResolver):
    def __init__(self, table: Any) -> None:
        self._table = table

    def resolve(self, source_dataset: SourceDataset):  # type: ignore[no-untyped-def]
        if self._table.source_dataset != source_dataset:
            raise KeyError("SourceDataset table is unavailable")
        return self._table


@dataclass(frozen=True, slots=True)
class _DesktopObjectAuthority:
    session: ProjectSession

    def current(self, expected: ContextObjectRef) -> ContextObjectRef | None:
        try:
            if expected.object_type == "source_dataset":
                records = tuple(
                    record.source_dataset
                    for record in self.session.store.list_source_datasets()
                    if record.source_dataset.source_dataset_id == expected.object_id
                )
                if not records:
                    return None
                source = max(records, key=lambda value: value.source_version)
                return ContextObjectRef(
                    object_alias=expected.object_alias,
                    object_id=source.source_dataset_id,
                    object_version=source.source_version,
                    object_type="source_dataset",
                    content_hash=source.content_hash,
                )
            if expected.object_type == "plot":
                stored = self.session.domain.get_plot(expected.object_id)
                return DesktopApplication._stored_plot_context_ref(
                    expected.object_alias,
                    stored,
                )
            if expected.object_type == "batch":
                batch, _state = self.session.domain.get_batch(expected.object_id)
                return ContextObjectRef(
                    object_alias=expected.object_alias,
                    object_id=batch.batch_id,
                    object_version=batch.batch_version,
                    object_type="batch",
                    content_hash=canonical_hash(batch),
                )
            if expected.object_type == "figure":
                figure = self.session.domain.get_figure(expected.object_id)
                return ContextObjectRef(
                    object_alias=expected.object_alias,
                    object_id=figure.figure_id,
                    object_version=figure.figure_version,
                    object_type="figure",
                    content_hash=canonical_hash(figure),
                )
            if expected.object_type == "project":
                return ContextObjectRef(
                    object_alias=expected.object_alias,
                    object_id=self.session.project_id,
                    object_version=self.session.domain.revision + 1,
                    object_type="project",
                )
        except StorageProblem:
            return None
        return None


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
class _DesktopTaskExecutor:
    application: DesktopApplication
    context: RpcContext
    session: ProjectSession

    def execute(self, plan: TaskPlanSnapshot, item: TaskItemSnapshot) -> tuple[TaskOutputRef, ...]:
        try:
            return self.application._execute_agent_task_item(  # noqa: SLF001
                self.context,
                self.session,
                plan,
                item,
            )
        except TaskExecutionError:
            raise
        except RpcServiceError as error:
            raise TaskExecutionError(
                error.code,
                error.message,
                retryable=error.code in {"ORIGIN_BUSY", "WORKER_CAPACITY_EXHAUSTED"},
            ) from error
        except StorageProblem as error:
            raise TaskExecutionError(str(error.code), error.message) from error


class _SessionBatchRepository:
    def __init__(self, session: ProjectSession) -> None:
        self.session = session
        self.tasks: dict[str, BatchTaskRecord] = {}
        self.keys: dict[tuple[str, str], str] = {}
        self.item_outputs: dict[OutputKey, PlotSpecRef] = {}
        self.batch_outputs: dict[OutputKey, BatchSpec] = {}
        self.executor: _SessionBatchExecutor | None = None

    def find_task_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> BatchTaskRecord | None:
        task_id = self.keys.get((project_id, idempotency_key))
        return None if task_id is None else self.tasks[task_id]

    def add_task(self, task: BatchTaskRecord) -> None:
        self.tasks[task.request.task_id] = task
        self.keys[(task.request.project_id, task.request.idempotency_key)] = task.request.task_id

    def get_task(self, task_id: str) -> BatchTaskRecord:
        return self.tasks[task_id]

    def save_task(self, task: BatchTaskRecord) -> None:
        self.tasks[task.request.task_id] = task

    def commit_item(self, key: OutputKey, item_id: str, staged: StagedPlot) -> PlotSpecRef:
        existing = self.item_outputs.get(key)
        if existing is not None:
            return existing
        if self.executor is None:
            raise RuntimeError("batch executor is unavailable")
        (
            mapping,
            preparation_spec,
            prepared,
            plot,
            _resolved,
            render_artifacts,
        ) = self.executor.bundle(staged.staging_id)
        request_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "task_id": key.task_id,
                    "action_id": key.action_id,
                    "output_slot": key.output_slot,
                    "plot_hash": canonical_hash(plot),
                },
            )
        )
        project_version = self.session.domain.revision + 1
        response: dict[str, JsonValue] = {
            "plot_id": plot.plot_id,
            "plot_version": plot.plot_version,
            "content_hash": canonical_hash(plot),
            "project_version": project_version,
        }
        self.session.domain.commit_new_plot(
            plot=plot,
            mapping=mapping,
            preparation_spec=preparation_spec,
            prepared=prepared,
            expected_revision=self.session.domain.revision,
            operation="batch.item",
            idempotency_key=f"{key.task_id}:{key.action_id}:{key.output_slot}",
            request_hash=request_hash,
            response=response,
            render_artifacts=render_artifacts,
        )
        reference = PlotSpecRef(
            plot_id=plot.plot_id,
            plot_version=plot.plot_version,
            content_hash=canonical_hash(plot),
        )
        self.item_outputs[key] = reference
        return reference

    def commit_batch(self, key: OutputKey, batch: BatchSpec) -> BatchSpec:
        existing = self.batch_outputs.get(key)
        if existing is not None:
            return existing
        self.batch_outputs[key] = batch
        return batch


class _SessionBatchExecutor:
    def __init__(
        self,
        application: DesktopApplication,
        session: ProjectSession,
        bindings: dict[str, str],
        batch_id: str,
        chart_type_id: str,
        repository: _SessionBatchRepository,
    ) -> None:
        self.application = application
        self.session = session
        self.bindings = bindings
        self.batch_id = batch_id
        self.chart_type_id = chart_type_id
        self.repository = repository
        repository.executor = self
        self._bundles: dict[
            str,
            tuple[
                FieldMapping,
                SelectFieldsSpec,
                PreparedArtifact,
                PlotSpec,
                ResolvedPlot,
                dict[str, bytes],
            ],
        ] = {}
        self._item_staging: dict[str, str] = {}

    def prepare_item(
        self,
        item: BatchWorkItem,
        _template: BatchTemplate,
        cancellation: BatchCancellationToken,
    ) -> PreparedDatasetRef:
        if cancellation.cancelled:
            raise TaskControlError("TASK_CANCELLED", "The task was cancelled.")
        source = self.session.domain.source_record(
            item.source_ref.source_dataset_id,
            item.source_ref.source_version,
        )
        table = self.session.domain.resolve_source(source)
        plot_id = (
            f"plot:{self.batch_id.removeprefix('batch:')}.{item.item_id.removeprefix('item.')}"
        )
        bundle = self.application._compile_plot_bundle(
            plot_id,
            self.chart_type_id,
            source,
            table,
            self.bindings,
            "manual",
            None,
        )
        staging_id = f"stage.{item.item_id}"
        self._bundles[staging_id] = bundle
        self._item_staging[item.item_id] = staging_id
        return bundle[2].prepared_dataset.as_ref()

    def stage_plot(
        self,
        item: BatchWorkItem,
        _prepared_ref: PreparedDatasetRef,
        _template: BatchTemplate,
        signature: BatchExecutionSignature,
        cancellation: BatchCancellationToken,
    ) -> StagedPlot:
        if cancellation.cancelled:
            raise TaskControlError("TASK_CANCELLED", "The task was cancelled.")
        staging_id = self._item_staging[item.item_id]
        return StagedPlot(
            staging_id=staging_id,
            plot_spec=self._bundles[staging_id][3],
            execution_signature_hash=signature.content_hash,
        )

    def discard_staged(self, staged: StagedPlot) -> None:
        self._bundles.pop(staged.staging_id, None)

    def bundle(
        self, staging_id: str
    ) -> tuple[
        FieldMapping,
        SelectFieldsSpec,
        PreparedArtifact,
        PlotSpec,
        ResolvedPlot,
        dict[str, bytes],
    ]:
        return self._bundles[staging_id]


class _SessionFigureRepository(FigureRepository):
    def __init__(self, session: ProjectSession) -> None:
        self.session = session
        self.figures: dict[str, FigureSpec] = {}
        self.keys: dict[tuple[str, str], tuple[str, FigureSpec]] = {}

    def get_plot_snapshot(self, plot_ref: PlotSpecRef) -> FigureSourceSnapshot:
        stored = self.session.domain.get_plot(plot_ref.plot_id, plot_ref.plot_version)
        mapping = {binding.role: binding.field for binding in stored.field_mapping.bindings}
        axes = {axis.orientation: axis for axis in stored.plot.axes}
        scales = {scale.scale_id: scale for scale in stored.plot.scales}

        def axis_signature(orientation: Literal["x", "y"]) -> AxisCompatibilitySignature | None:
            field = mapping.get(orientation)
            if field is None:
                return None
            axis = axes[orientation]
            return AxisCompatibilitySignature(
                scales[axis.scale_id].kind,
                canonical_hash(field.unit),
            )

        return FigureSourceSnapshot(
            plot_ref=plot_ref,
            numeric_only=True,
            x_axis=axis_signature("x"),
            y_axis=axis_signature("y"),
        )

    def get_latest_plot_ref(self, plot_id: str) -> PlotSpecRef:
        stored = self.session.domain.get_plot(plot_id)
        return PlotSpecRef(
            plot_id=plot_id,
            plot_version=stored.plot.plot_version,
            content_hash=stored.content_hash,
        )

    def get_figure(self, figure_id: str) -> FigureSpec:
        return self.figures.get(figure_id) or self.session.domain.get_figure(figure_id)

    def find_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> tuple[str, FigureSpec] | None:
        return self.keys.get((project_id, idempotency_key))

    def commit_figure(
        self,
        project_id: str,
        idempotency_key: str,
        request_hash: str,
        figure: FigureSpec,
        expected_version: int | None,
    ) -> FigureSpec:
        existing = self.figures.get(figure.figure_id)
        if expected_version is None and existing is not None:
            raise ValueError("Figure already exists")
        if expected_version is not None and (
            existing is None or existing.figure_version != expected_version
        ):
            raise ValueError("Figure version conflict")
        self.figures[figure.figure_id] = figure
        self.keys[(project_id, idempotency_key)] = (request_hash, figure)
        return figure


def _plot_family(family: str, geometries: tuple[str, ...]) -> Any:
    unique = tuple(dict.fromkeys(geometries))
    families: dict[str, type[Any]] = {
        "xy": XYFamily,
        "categorical": CategoricalFamily,
        "distribution": DistributionFamily,
        "matrix": MatrixFamily,
        "survival": SurvivalFamily,
        "dose_response": DoseResponseFamily,
        "forest": ForestFamily,
        "facet": FacetFamily,
        "special": SpecialFamily,
    }
    return families[family](geometry=unique)


def _axis_scale_kinds(
    chart_type_id: str, bindings: Mapping[str, str], fields: Mapping[str, Any]
) -> tuple[AxisScaleKind, AxisScaleKind]:
    if chart_type_id in {"K08", "K09", "K10", "K11", "K12", "K13", "K14"}:
        return "categorical", "linear"
    if chart_type_id == "X13":
        return "linear", "categorical"
    if chart_type_id in {
        "X05",
        "X09",
        "X11",
        "X12",
        "X24",
        "X35",
        "X36",
        "X37",
        "X39",
        "X40",
    }:
        return "categorical", "linear"
    if chart_type_id == "X03":
        return "linear", "categorical"
    if chart_type_id in {"K20", "K21", "S61"}:
        return "categorical", "categorical"
    if chart_type_id == "S21":
        return "linear", "categorical"
    if chart_type_id == "S05":
        return "log10", "linear"
    if chart_type_id == "K19":
        time_field = fields[bindings["time"]]
        return ("datetime" if time_field.logical_type == "datetime" else "linear"), "linear"
    return "linear", "linear"


def _matching_roles(
    signatures: tuple[tuple[str, ...], ...], bindings: Mapping[str, str]
) -> tuple[str, ...] | None:
    matches = [roles for roles in signatures if set(roles).issubset(bindings)]
    return max(matches, key=len) if matches else None


def _variadic_series_roles(bindings: Mapping[str, str]) -> tuple[str, ...]:
    indexed: list[tuple[int, str]] = []
    for role in bindings:
        if not role.startswith("series_"):
            continue
        suffix = role.removeprefix("series_")
        if not suffix.isdigit() or int(suffix) < 1:
            raise RpcServiceError(
                "MAPPING_ROLE_UNKNOWN",
                "Variadic series roles must use consecutive series_N names.",
            )
        indexed.append((int(suffix), role))
    indexed.sort()
    expected = list(range(1, len(indexed) + 1))
    if [index for index, _role in indexed] != expected:
        raise RpcServiceError(
            "MAPPING_ROLE_MISSING",
            "Variadic series roles must be consecutive from series_1.",
        )
    return tuple(role for _index, role in indexed)


def _default_series_label(
    roles: tuple[str, ...],
    bindings: Mapping[str, str],
    fields: Mapping[str, Any],
) -> SafeRichText | None:
    """Keep source-facing names on structural series instead of opaque field IDs."""
    series_roles = tuple(role for role in roles if role.startswith("series_"))
    if not series_roles:
        return None
    return SafeRichText(
        nodes=tuple(
            SafeTextNode(kind="plain", text=fields[bindings[role]].name) for role in series_roles
        )
    )


_CALCULATED_FIELDS: dict[str, dict[str, str]] = {
    "K11": {
        "category": "__binding_category__",
        "component": "__binding_component__",
        "value": "field:plotcalc.proportion",
    },
    "K13": {
        "group": "field:plotcalc.group",
        "q1": "field:plotcalc.q1",
        "median": "field:plotcalc.median",
        "q3": "field:plotcalc.q3",
        "whisker_low": "field:plotcalc.whisker_low",
        "whisker_high": "field:plotcalc.whisker_high",
    },
    "K14": {
        "group": "field:plotcalc.group",
        "grid": "field:plotcalc.x",
        "density": "field:plotcalc.density",
    },
    "K15": {
        "left": "field:plotcalc.bin_left",
        "right": "field:plotcalc.bin_right",
        "height": "field:plotcalc.value",
    },
    "K16": {
        "grid": "field:plotcalc.x",
        "density": "field:plotcalc.density",
        "group": "field:plotcalc.group",
    },
    "K17": {
        "x": "field:plotcalc.x",
        "probability": "field:plotcalc.probability",
    },
    "S61": {
        "actual": "field:plotcalc.actual_category",
        "predicted": "field:plotcalc.predicted_category",
        "value": "field:plotcalc.value",
    },
}


def _calculated_role_fields(
    chart_type_id: str,
    signatures: tuple[tuple[str, ...], ...],
    available_fields: tuple[str, ...],
) -> tuple[str, ...]:
    available = set(available_fields)
    mapping = dict(_CALCULATED_FIELDS[chart_type_id])
    if chart_type_id == "K11":
        source_fields = tuple(
            field_id for field_id in available_fields if not field_id.startswith("field:plotcalc.")
        )
        if len(source_fields) != 2:
            raise RpcServiceError(
                "CALCULATION_OUTPUT_INVALID",
                "Percent-stack output did not retain category and component fields.",
            )
        mapping["category"], mapping["component"] = source_fields
    matches = [
        tuple(mapping[role] for role in roles)
        for roles in signatures
        if all(mapping.get(role) in available for role in roles)
    ]
    if not matches:
        raise RpcServiceError(
            "CALCULATION_OUTPUT_INVALID",
            "The fixed calculation did not produce a qualified chart geometry.",
        )
    return max(matches, key=len)


def _calculation_columns(
    chart_type_id: str, result: PlotCalculationResult
) -> dict[str, tuple[object, ...]]:
    field_ids = result.output_table.field_ids
    rows = result.output_table.rows
    if chart_type_id == "K13":
        record_index = field_ids.index("field:plotcalc.record_kind")
        rows = tuple(row for row in rows if row[record_index] == "summary")
    columns: dict[str, tuple[object, ...]] = {
        field_id: tuple(row[index] for row in rows) for index, field_id in enumerate(field_ids)
    }
    return columns


def _axis_labels(
    chart_type_id: str,
    required_roles: tuple[str, ...],
    bindings: Mapping[str, str],
    fields: Mapping[str, Any],
) -> tuple[str, str]:
    if chart_type_id in {"K20", "K21"}:
        column_role = "column" if "column" in bindings else "column_label"
        row_role = "row" if "row" in bindings else "row_label"
        return fields[bindings[column_role]].name, fields[bindings[row_role]].name
    if chart_type_id == "S61":
        return fields[bindings["predicted"]].name, fields[bindings["actual"]].name
    if chart_type_id == "S07":
        significance = "q" if "qvalue" in bindings else "p"
        return fields[bindings["log2fc"]].name, f"-log10({significance})"
    x_roles = (
        "x",
        "time",
        "category",
        "value",
        "row",
        "row_label",
        "dose",
        "label",
        "spectral_axis",
        "angle",
        "z_real",
        "actual",
        "facet",
    )
    y_roles = (
        "y",
        "center",
        "value",
        "column",
        "column_label",
        "survival",
        "response",
        "effect",
        "intensity",
        "z_imaginary",
        "predicted",
        "base_y",
    )
    x_role = next((role for role in x_roles if role in bindings), required_roles[0])
    y_role = next(
        (role for role in y_roles if role in bindings and role != x_role),
        required_roles[min(1, len(required_roles) - 1)],
    )
    return fields[bindings[x_role]].name, fields[bindings[y_role]].name


def _columns_to_parquet(columns: Mapping[str, tuple[object, ...]]) -> bytes:
    table = pa.table({field_id: pa.array(values) for field_id, values in columns.items()})
    output = io.BytesIO()
    pq.write_table(
        table,
        output,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
        data_page_version="2.0",
        version="2.6",
    )
    return output.getvalue()


def _source_ref(source: SourceDataset) -> SourceDatasetRef:
    return SourceDatasetRef(
        source_dataset_id=source.source_dataset_id,
        source_version=source.source_version,
        content_hash=source.content_hash,
    )


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
        for registration in CONTRACT_CHARTS_BY_ID.values()
        for role in (*registration.required_roles, *registration.optional_roles)
    }
    if normalized in declared_roles or normalized.startswith("series_"):
        return normalized
    return None


def _rich_text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


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


def _string_mapping(value: RpcJsonValue | None, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()
    ):
        raise RpcServiceError("INVALID_PARAMS", f"{name} was invalid.")
    return cast(dict[str, str], value)


def _list(value: RpcJsonValue | None, name: str) -> list[RpcJsonValue]:
    if not isinstance(value, list):
        raise RpcServiceError("INVALID_PARAMS", f"{name} was invalid.")
    return value


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _float_value(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("K01 Origin data must be numeric")
    return float(value)


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _render_preview(path: Path, resolved: ResolvedPlot) -> dict[str, RpcJsonValue]:
    from plotagent.rendering.matplotlib import MatplotlibRenderer

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    figure = MatplotlibRenderer().build_figure(resolved)
    try:
        figure.savefig(
            temporary,
            format="png",
            dpi=resolved.plan.dpi,
            facecolor=resolved.plan.background.value,
            edgecolor="none",
        )
        os.replace(temporary, path)
    finally:
        figure.clear()
        temporary.unlink(missing_ok=True)
    content_hash, size = _hash_file(path)
    return {
        "resource_id": "resource:preview." + content_hash[:24],
        "path": str(path.resolve()),
        "content_hash": content_hash,
        "size": size,
        "render_plan_hash": resolved.render_plan_hash,
        "quality_tier": resolved.plan.quality_tier,
        "full_row_count": resolved.plan.data_integrity.total_rows,
        "displayed_row_count": resolved.plan.data_integrity.visible_rows,
    }
