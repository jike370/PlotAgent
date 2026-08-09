"""Internal models for project storage and atomic import registration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
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
    display_name: str | None = None
    source_file_name: str | None = None
    sheet_name: str | None = None
    source_block: str | None = None


class ImportCommitResult(StrictModel):
    kind: Literal["committed"] = "committed"
    session_id: str
    datasets: tuple[SourceDatasetRecord, ...]


class CatalogProject(StrictModel):
    project_id: str
    workspace_path: str
    display_name: str | None = None
    source_project_id: str | None = None
    package_sha256: str | None = None
    created_at: str
    last_opened_at: str


class ProjectPackageType(StrEnum):
    FULL = "full"
    RESULT = "result"


class ProjectPackageObject(StrictModel):
    path: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    media_type: str


class ProjectPackageManifest(StrictModel):
    package_format: Literal["plotagent-project"] = "plotagent-project"
    package_format_version: int
    project_schema_version: int
    project_id: str
    snapshot_transaction_id: str
    package_type: ProjectPackageType
    created_at: str
    created_by: str
    objects: tuple[ProjectPackageObject, ...]
    omitted_objects: tuple[str, ...] = ()
    unavailable_capabilities: tuple[str, ...] = ()


class ProjectPackageExportResult(StrictModel):
    destination_path: str
    package_sha256: str
    project_id: str
    object_count: int


class ProjectPackageImportResult(StrictModel):
    project_id: str
    source_project_id: str
    workspace_path: str
    package_sha256: str
    reused: bool
    as_new_copy: bool


type ProjectImportOutcome = Annotated[
    ImportCommitResult | Clarification | Rejection,
    Field(discriminator="kind"),
]
