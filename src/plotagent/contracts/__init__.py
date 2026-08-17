"""Stable data, workflow, calculation, and error contracts.

Plotting contracts live in :mod:`plotagent.engine`; this package deliberately
contains no renderer-specific plot specification.
"""

from plotagent.contracts.base import SCHEMA_VERSION
from plotagent.contracts.calculations import PlotCalculationResult, PlotCalculationSpec
from plotagent.contracts.canonical import canonical_hash, canonical_json
from plotagent.contracts.data_preparation import (
    DataPreparationRecipe,
    DataPreparationRun,
    SourceStructureProbe,
)
from plotagent.contracts.datasets import (
    FieldMapping,
    PreparationSpec,
    PreparedDataset,
    SourceDataset,
)
from plotagent.contracts.errors import STABLE_ERROR_REGISTRY, ErrorResponse
from plotagent.contracts.workflows import (
    TaskDraft,
    TaskPlan,
    TaskPlanSnapshot,
    WorkflowContext,
    WorkflowDecision,
    WorkflowRunSnapshot,
)

__all__ = [
    "SCHEMA_VERSION",
    "ErrorResponse",
    "DataPreparationRecipe",
    "DataPreparationRun",
    "FieldMapping",
    "PlotCalculationResult",
    "PlotCalculationSpec",
    "PreparationSpec",
    "PreparedDataset",
    "STABLE_ERROR_REGISTRY",
    "SourceDataset",
    "SourceStructureProbe",
    "TaskDraft",
    "TaskPlan",
    "TaskPlanSnapshot",
    "WorkflowContext",
    "WorkflowDecision",
    "WorkflowRunSnapshot",
    "canonical_hash",
    "canonical_json",
]
