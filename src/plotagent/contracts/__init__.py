"""PlotAgent v1 strict domain contracts."""

from plotagent.contracts.agent_context import ContextEnvelope
from plotagent.contracts.base import SCHEMA_VERSION
from plotagent.contracts.calculations import PlotCalculationResult, PlotCalculationSpec
from plotagent.contracts.canonical import canonical_hash, canonical_json
from plotagent.contracts.datasets import (
    FieldMapping,
    PreparationSpec,
    PreparedDataset,
    SourceDataset,
)
from plotagent.contracts.decisions import AgentDecision
from plotagent.contracts.errors import STABLE_ERROR_REGISTRY, ErrorResponse
from plotagent.contracts.plots import (
    BatchSpec,
    FigureSpec,
    PatchTransaction,
    PlotPatch,
    PlotSpec,
)
from plotagent.contracts.project_context import ProjectContextSnapshot, TargetResolution
from plotagent.contracts.registry import V1_CHART_REGISTRY
from plotagent.contracts.rendering import ExportSpec, OriginExportPlan, ResolvedRenderPlan
from plotagent.contracts.task_runtime import TaskPlanSnapshot

__all__ = [
    "SCHEMA_VERSION",
    "AgentDecision",
    "BatchSpec",
    "ContextEnvelope",
    "ErrorResponse",
    "ExportSpec",
    "FieldMapping",
    "FigureSpec",
    "OriginExportPlan",
    "PatchTransaction",
    "PlotCalculationResult",
    "PlotCalculationSpec",
    "PlotPatch",
    "PlotSpec",
    "ProjectContextSnapshot",
    "PreparationSpec",
    "PreparedDataset",
    "ResolvedRenderPlan",
    "STABLE_ERROR_REGISTRY",
    "SourceDataset",
    "TargetResolution",
    "TaskPlanSnapshot",
    "V1_CHART_REGISTRY",
    "canonical_hash",
    "canonical_json",
]
