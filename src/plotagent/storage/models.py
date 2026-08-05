"""Internal models for project storage and atomic import registration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from plotagent.contracts.datasets import SourceDataset
from plotagent.importing.models import Clarification, Rejection, SourceDatasetArtifact


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


@dataclass(frozen=True)
class StagedObject:
    token: str
    path: Path
    content_hash: str
    size: int
    media_type: str
    task_dir: Path


@dataclass(frozen=True)
class DatasetRegistration:
    logical_source_id: str
    source_dataset: SourceDataset
    artifact: SourceDatasetArtifact
    table_object: StagedObject


@dataclass(frozen=True)
class ImportResource:
    resource_id: str
    path: Path


class SourceDatasetRecord(StrictModel):
    source_dataset: SourceDataset
    logical_source_id: str
    import_recipe_id: str
    created_at: str


class ImportCommitResult(StrictModel):
    kind: Literal["committed"] = "committed"
    session_id: str
    datasets: tuple[SourceDatasetRecord, ...]


class CatalogProject(StrictModel):
    project_id: str
    workspace_path: str
    display_name: str | None = None
    created_at: str
    last_opened_at: str


type ProjectImportOutcome = Annotated[
    ImportCommitResult | Clarification | Rejection,
    Field(discriminator="kind"),
]
