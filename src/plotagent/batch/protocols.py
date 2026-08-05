"""Adapter boundaries used by the pure batch service."""

from __future__ import annotations

from typing import Protocol

from plotagent.batch.models import (
    BatchTaskRecord,
    BatchTemplate,
    BatchWorkItem,
    OutputKey,
    StagedPlot,
)
from plotagent.contracts.base import PlotSpecRef, PreparedDatasetRef
from plotagent.contracts.plots import BatchExecutionSignature, BatchSpec


class CancellationToken(Protocol):
    @property
    def cancelled(self) -> bool: ...


class BatchExecutor(Protocol):
    def prepare_item(
        self,
        item: BatchWorkItem,
        template: BatchTemplate,
        cancellation: CancellationToken,
    ) -> PreparedDatasetRef: ...

    def stage_plot(
        self,
        item: BatchWorkItem,
        prepared_ref: PreparedDatasetRef,
        template: BatchTemplate,
        signature: BatchExecutionSignature,
        cancellation: CancellationToken,
    ) -> StagedPlot: ...

    def discard_staged(self, staged: StagedPlot) -> None: ...


class BatchRepository(Protocol):
    def find_task_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> BatchTaskRecord | None: ...

    def add_task(self, task: BatchTaskRecord) -> None: ...

    def get_task(self, task_id: str) -> BatchTaskRecord: ...

    def save_task(self, task: BatchTaskRecord) -> None: ...

    def commit_item(
        self, key: OutputKey, item_id: str, staged: StagedPlot
    ) -> PlotSpecRef: ...

    def commit_batch(self, key: OutputKey, batch: BatchSpec) -> BatchSpec: ...
