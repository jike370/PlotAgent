"""Runtime-only table materialization around authoritative W0 contracts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from plotagent.contracts.base import RowExclusion
from plotagent.contracts.datasets import (
    PreparedDataset,
    SourceCoordinate,
    SourceDataset,
    SourceField,
)
from plotagent.importing.models import Scalar, SourceDatasetArtifact


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ResolvedSourceTable(StrictModel):
    source_dataset: SourceDataset
    rows: tuple[tuple[Scalar, ...], ...]
    coordinates: tuple[SourceCoordinate, ...]
    instrument_metadata: dict[str, str]


class SourceTableResolver(Protocol):
    def resolve(self, source_dataset: SourceDataset) -> ResolvedSourceTable:
        """Resolve immutable table bytes without changing the public contract."""


class ImportedSourceResolver:
    """Resolve W0 datasets from import artifacts before they enter project storage."""

    def __init__(self, artifacts: Iterable[SourceDatasetArtifact]) -> None:
        self._artifacts = {
            (
                artifact.source_dataset.source_dataset_id,
                artifact.source_dataset.source_version,
                artifact.source_dataset.content_hash,
            ): artifact
            for artifact in artifacts
        }

    def resolve(self, source_dataset: SourceDataset) -> ResolvedSourceTable:
        key = (
            source_dataset.source_dataset_id,
            source_dataset.source_version,
            source_dataset.content_hash,
        )
        artifact = self._artifacts.get(key)
        if artifact is None:
            raise KeyError(
                f"SourceDataset table is unavailable: {source_dataset.source_dataset_id}"
            )
        return ResolvedSourceTable(
            source_dataset=source_dataset,
            rows=artifact.rows,
            coordinates=artifact.coordinates,
            instrument_metadata=artifact.instrument_metadata,
        )


class PreparedArtifact(StrictModel):
    """Non-authoritative materialization paired with a W0 PreparedDataset."""

    prepared_dataset: PreparedDataset
    fields: tuple[SourceField, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    coordinates: tuple[SourceCoordinate, ...]
    row_mask: tuple[bool, ...]
    exclusions: tuple[RowExclusion, ...] = ()
    plot_order: tuple[str, ...] = ()
    parquet_bytes: bytes
