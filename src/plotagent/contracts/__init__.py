"""Stable data, workflow, calculation, and error contracts.

Plotting contracts live in :mod:`plotagent.engine`; this package deliberately
contains no renderer-specific plot specification.
"""

from plotagent.contracts.agent_tasks import (
    AgentActivation,
    AgentYield,
    ExecutionGrant,
    TaskCheckpoint,
    TaskEnvelope,
    TaskEvent,
    TaskIntent,
    ToolReceipt,
    VerificationReport,
)
from plotagent.contracts.base import SCHEMA_VERSION
from plotagent.contracts.calculations import PlotCalculationResult, PlotCalculationSpec
from plotagent.contracts.canonical import canonical_hash, canonical_json
from plotagent.contracts.datasets import (
    FieldMapping,
    PreparationSpec,
    PreparedDataset,
    SourceDataset,
)
from plotagent.contracts.errors import STABLE_ERROR_REGISTRY, ErrorResponse
from plotagent.contracts.workflows import (
    PreparedDataPreview,
    TaskDraft,
    TaskPlan,
    TaskPlanSnapshot,
    WorkflowContext,
    WorkflowDecision,
    WorkflowRecipe,
    WorkflowRunSnapshot,
)

__all__ = [
    "SCHEMA_VERSION",
    "AgentActivation",
    "AgentYield",
    "ErrorResponse",
    "ExecutionGrant",
    "FieldMapping",
    "PlotCalculationResult",
    "PlotCalculationSpec",
    "PreparationSpec",
    "PreparedDataPreview",
    "PreparedDataset",
    "STABLE_ERROR_REGISTRY",
    "SourceDataset",
    "TaskCheckpoint",
    "TaskDraft",
    "TaskEnvelope",
    "TaskEvent",
    "TaskIntent",
    "TaskPlan",
    "TaskPlanSnapshot",
    "WorkflowContext",
    "WorkflowDecision",
    "WorkflowRecipe",
    "WorkflowRunSnapshot",
    "ToolReceipt",
    "VerificationReport",
    "canonical_hash",
    "canonical_json",
]
