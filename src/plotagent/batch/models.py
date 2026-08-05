"""Internal immutable records for batch orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from plotagent.contracts.base import (
    FieldMappingRef,
    PlotCalculationSpecRef,
    PlotSpecRef,
    PreparationSpecRef,
    PreparedDatasetRef,
    SourceDatasetRef,
)
from plotagent.contracts.errors import ErrorResponse
from plotagent.contracts.plots import (
    BatchExecutionSignature,
    BatchSpec,
    DatasetSignature,
    PlotSpec,
    ResolvedStyleSnapshot,
)

type ExecutionTaskState = Literal[
    "queued",
    "preparing",
    "running",
    "committing",
    "succeeded",
    "cancelling",
    "cancelled",
    "failed",
    "partially_succeeded",
    "interrupted",
]
type BatchItemPhase = Literal[
    "queued", "preparing", "running", "committing", "succeeded", "failed", "cancelled"
]
type ReviewState = Literal["unconfirmed", "confirmed", "excluded"]
type ExportScope = Literal["selected", "all"]


@dataclass(frozen=True, slots=True)
class BatchWorkItem:
    item_id: str
    source_ref: SourceDatasetRef
    dataset_signature: DatasetSignature


@dataclass(frozen=True, slots=True)
class BatchTemplate:
    field_mapping_ref: FieldMappingRef
    preparation_spec_ref: PreparationSpecRef
    plot_calculation_spec_ref: PlotCalculationSpecRef | None
    plot_template: PlotSpec
    shared_style: ResolvedStyleSnapshot
    axis_policy: Literal["per_plot", "unified"] = "per_plot"


@dataclass(frozen=True, slots=True)
class BatchSubmissionRequest:
    task_id: str
    project_id: str
    action_id: str
    idempotency_key: str
    batch_id: str
    mapping_confirmed: bool
    items: tuple[BatchWorkItem, ...]
    template: BatchTemplate

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("batch submission requires at least one item")
        item_ids = tuple(item.item_id for item in self.items)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("batch item ids must be unique")


@dataclass(frozen=True, slots=True)
class StagedPlot:
    staging_id: str
    plot_spec: PlotSpec
    execution_signature_hash: str


@dataclass(frozen=True, slots=True)
class OutputKey:
    task_id: str
    action_id: str
    output_slot: str


@dataclass(frozen=True, slots=True)
class BatchItemRecord:
    work_item: BatchWorkItem
    phase: BatchItemPhase = "queued"
    prepared_ref: PreparedDatasetRef | None = None
    plot_ref: PlotSpecRef | None = None
    error: ErrorResponse | None = None
    review_state: ReviewState = "unconfirmed"


@dataclass(frozen=True, slots=True)
class BatchTaskRecord:
    request: BatchSubmissionRequest
    request_hash: str
    execution_signature: BatchExecutionSignature
    state: ExecutionTaskState
    sequence: int
    items: tuple[BatchItemRecord, ...]
    history: tuple[ExecutionTaskState, ...]
    batch_spec: BatchSpec | None = None

    def item(self, item_id: str) -> BatchItemRecord:
        return next(item for item in self.items if item.work_item.item_id == item_id)

    def replace_item(self, updated: BatchItemRecord) -> BatchTaskRecord:
        return replace(
            self,
            items=tuple(
                updated if item.work_item.item_id == updated.work_item.item_id else item
                for item in self.items
            ),
        )


@dataclass(frozen=True, slots=True)
class BatchSubmission:
    task_id: str
    state: ExecutionTaskState
    execution_signature: BatchExecutionSignature
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class ExportExclusion:
    item_id: str
    reason: Literal["not_selected", "failed", "cancelled", "unconfirmed", "excluded"]


@dataclass(frozen=True, slots=True)
class BatchExportSelection:
    scope: ExportScope
    target_refs: tuple[PlotSpecRef, ...]
    excluded: tuple[ExportExclusion, ...]
