"""Temp-first import orchestration with one atomic project registration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from plotagent.contracts.base import ContentTableRef
from plotagent.importing import Imported, inspect_source
from plotagent.importing.models import SourceDatasetArtifact
from plotagent.importing.normalize import sha256_bytes
from plotagent.importing.serialization import table_to_parquet_bytes
from plotagent.storage.models import (
    DatasetRegistration,
    ImportResource,
    ProjectImportOutcome,
)
from plotagent.storage.project import FaultInjector, ImportResponseFactory, ProjectStore


def _logical_source_id(resource_id: str, artifact: SourceDatasetArtifact) -> str:
    recipe = artifact.recipe
    if recipe.sheet is not None:
        partition = f"sheet:{recipe.sheet}"
        if recipe.block is not None:
            partition += f"/block:{recipe.block}"
    elif recipe.block is not None:
        partition = f"block:{recipe.block}"
    else:
        partition = "table:1"
    return f"{resource_id}/{partition}"


class ProjectImportService:
    def __init__(
        self,
        project: ProjectStore,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self._project = project
        self._fault_injector = fault_injector

    def import_resource(
        self,
        resource: ImportResource,
        *,
        encoding: str | None = None,
        delimiter: str | None = None,
        decimal_mark: str | None = None,
        header_row: int | None = None,
        header_rows: Mapping[str, int] | None = None,
        sheet: str | None = None,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
        response_factory: ImportResponseFactory | None = None,
        before_commit: Callable[[], None] | None = None,
    ) -> ProjectImportOutcome:
        """Copy, inspect, serialize, and atomically register one authorized resource."""

        staged_source = self._project.stage_source(Path(resource.path))
        try:
            outcome = inspect_source(
                staged_source.path,
                encoding=encoding,
                delimiter=delimiter,
                decimal_mark=decimal_mark,
                header_row=header_row,
                header_rows=header_rows,
                sheet=sheet,
            )
            if not isinstance(outcome, Imported):
                self._project.cleanup_staged_task(staged_source.task_dir)
                return outcome
            if outcome.source_object_hash != staged_source.content_hash:
                raise ValueError("staged source changed during deterministic inspection")

            registrations: list[DatasetRegistration] = []
            for artifact in outcome.sources:
                logical_id = _logical_source_id(resource.resource_id, artifact)
                source_dataset_id = self._project.stable_source_dataset_id(logical_id)
                source_version = self._project.next_source_version(logical_id)
                source = artifact.source_dataset
                parquet_bytes = table_to_parquet_bytes(
                    source_dataset_id=source_dataset_id,
                    source_object_hash=staged_source.content_hash,
                    fields=source.field_schema,
                    rows=artifact.rows,
                    coordinates=artifact.coordinates,
                    recipe=artifact.recipe,
                    quality=source.quality,
                )
                content_hash = sha256_bytes(parquet_bytes)
                stored_source = source.model_copy(
                    update={
                        "source_dataset_id": source_dataset_id,
                        "source_version": source_version,
                        "source_object_hash": staged_source.content_hash,
                        "content_hash": content_hash,
                        "data_ref": ContentTableRef(
                            object_hash=content_hash,
                            row_count=len(artifact.rows),
                            field_ids=tuple(field.field_id for field in source.field_schema),
                        ),
                    }
                )
                stored_artifact = artifact.model_copy(
                    update={
                        "source_dataset": stored_source,
                        "parquet_bytes": parquet_bytes,
                    }
                )
                table_object = self._project.stage_bytes(
                    parquet_bytes,
                    media_type="application/vnd.apache.parquet",
                    task_dir=staged_source.task_dir,
                )
                registrations.append(
                    DatasetRegistration(
                        logical_source_id=logical_id,
                        source_dataset=stored_source,
                        artifact=stored_artifact,
                        table_object=table_object,
                    )
                )
            if before_commit is not None:
                before_commit()
            return self._project.commit_import(
                resource_id=resource.resource_id,
                source_object=staged_source,
                registrations=registrations,
                fault_injector=self._fault_injector,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_factory=response_factory,
            )
        except Exception:
            self._project.cleanup_staged_task(staged_source.task_dir)
            raise
