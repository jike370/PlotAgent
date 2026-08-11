"""Stable data, context, calculation, and error contracts.

Plotting contracts live in :mod:`plotagent.engine`; this package deliberately
contains no renderer-specific plot specification.
"""

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
from plotagent.contracts.errors import STABLE_ERROR_REGISTRY, ErrorResponse
from plotagent.contracts.project_context import ProjectContextSnapshot, TargetResolution

__all__ = [
    "SCHEMA_VERSION",
    "ContextEnvelope",
    "ErrorResponse",
    "FieldMapping",
    "PlotCalculationResult",
    "PlotCalculationSpec",
    "PreparationSpec",
    "PreparedDataset",
    "ProjectContextSnapshot",
    "STABLE_ERROR_REGISTRY",
    "SourceDataset",
    "TargetResolution",
    "canonical_hash",
    "canonical_json",
]
