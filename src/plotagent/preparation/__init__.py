"""Closed, auditable preparation using the authoritative W0 contracts."""

from plotagent.contracts.datasets import (
    ApplyPlotOrderSpec,
    FieldMapping,
    FilterRowsSpec,
    IsomorphicConcatSpec,
    PreparationSpec,
    PreparedDataset,
    ProjectMetadataLabelSpec,
    ProjectStructureSpec,
    SelectFieldsSpec,
)
from plotagent.preparation.artifacts import (
    ImportedSourceResolver,
    PreparedArtifact,
    ResolvedSourceTable,
    SourceTableResolver,
)
from plotagent.preparation.service import prepare, semantic_signature

__all__ = [
    "ApplyPlotOrderSpec",
    "FieldMapping",
    "ImportedSourceResolver",
    "IsomorphicConcatSpec",
    "FilterRowsSpec",
    "PreparationSpec",
    "PreparedArtifact",
    "PreparedDataset",
    "ProjectMetadataLabelSpec",
    "ProjectStructureSpec",
    "ResolvedSourceTable",
    "SelectFieldsSpec",
    "SourceTableResolver",
    "prepare",
    "semantic_signature",
]
