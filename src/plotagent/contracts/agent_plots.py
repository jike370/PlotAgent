"""Task-scoped sandbox plot handles exposed to the Agent runtime."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.agent_data import DataViewHandleId
from plotagent.contracts.agent_tasks import IsoTimestamp, TaskId, TaskItemIdV2
from plotagent.contracts.base import PositiveInt, Sha256, StrictModel, Token, VersionId
from plotagent.engine.contracts import (
    ActionId,
    AddAnnotation,
    AddCallout,
    AddReferenceLine,
    EngineDataRef,
    PlotDocument,
    PlotDocumentRef,
    SemanticObjectId,
    SetAxis,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetObservationOverlay,
    SetPointMarkerMap,
    SetSeriesStyle,
    SetTitle,
)

SandboxPlotHandleId = Annotated[
    str,
    StringConstraints(
        pattern=r"^plotview:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
SandboxArtifactId = Annotated[
    str,
    StringConstraints(
        pattern=r"^artifact:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
SandboxBackend = Literal["matplotlib", "origin"]


class SandboxPlotObject(StrictModel):
    """Backend-neutral object projection; native references stay inside Core."""

    semantic_id: SemanticObjectId
    object_kind: Token


class SandboxPlotReadback(StrictModel):
    backend: SandboxBackend
    document: PlotDocumentRef
    objects: Annotated[tuple[SandboxPlotObject, ...], Field(max_length=512)]
    data_hash: Sha256
    style_hash: Sha256

    @model_validator(mode="after")
    def semantic_objects_are_unique(self) -> SandboxPlotReadback:
        identities = tuple((item.semantic_id, item.object_kind) for item in self.objects)
        if len(identities) != len(set(identities)):
            raise ValueError("sandbox readback objects must be unique")
        return self


class SandboxPlotArtifact(StrictModel):
    artifact_id: SandboxArtifactId
    backend: SandboxBackend
    format: Literal["png", "svg", "opju"]
    content_hash: Sha256
    size: PositiveInt

    @model_validator(mode="after")
    def format_matches_backend(self) -> SandboxPlotArtifact:
        if self.backend == "matplotlib" and self.format not in {"png", "svg"}:
            raise ValueError("Matplotlib sandbox artifacts must be PNG or SVG")
        if self.backend == "origin" and self.format != "opju":
            raise ValueError("Origin sandbox artifacts must be OPJU")
        return self


class SandboxPlotLineageStep(StrictModel):
    step_id: Token
    operation: Literal["preview_plot", "apply_plot_edits"]
    input_handle_id: SandboxPlotHandleId | None = None
    action_ids: Annotated[tuple[ActionId, ...], Field(min_length=1, max_length=32)]
    action_hash: Sha256
    output_document: PlotDocumentRef
    artifact_hashes: Annotated[tuple[Sha256, ...], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def lineage_shape_matches_operation(self) -> SandboxPlotLineageStep:
        if self.operation == "preview_plot" and self.input_handle_id is not None:
            raise ValueError("initial sandbox render cannot have a parent plot handle")
        if self.operation == "apply_plot_edits" and self.input_handle_id is None:
            raise ValueError("sandbox edits require a parent plot handle")
        if len(self.action_ids) != len(set(self.action_ids)):
            raise ValueError("sandbox lineage action ids must be unique")
        return self


class SandboxPlotHandle(StrictModel):
    schema_version: Literal["sandbox-plot-handle.v2"] = "sandbox-plot-handle.v2"
    handle_id: SandboxPlotHandleId
    handle_version: VersionId = 1
    task_id: TaskId
    task_version: VersionId
    item_id: TaskItemIdV2 | None = None
    parent_handle_id: SandboxPlotHandleId | None = None
    data_view_handle_id: DataViewHandleId
    root_sources: Annotated[tuple[EngineDataRef, ...], Field(min_length=1, max_length=32)]
    staged_data_hash: Sha256
    document: PlotDocument
    backends: Annotated[tuple[SandboxBackend, ...], Field(min_length=1, max_length=2)]
    readbacks: Annotated[tuple[SandboxPlotReadback, ...], Field(min_length=1, max_length=2)]
    artifacts: Annotated[tuple[SandboxPlotArtifact, ...], Field(min_length=1, max_length=3)]
    lineage: Annotated[tuple[SandboxPlotLineageStep, ...], Field(min_length=1, max_length=32)]
    created_at: IsoTimestamp
    expires_at: IsoTimestamp

    @model_validator(mode="after")
    def immutable_sandbox_identity_is_consistent(self) -> SandboxPlotHandle:
        if self.expires_at <= self.created_at:
            raise ValueError("sandbox plot expiry must follow creation")
        if len(self.backends) != len(set(self.backends)):
            raise ValueError("sandbox plot backends must be unique")
        if any(source.kind != "source" for source in self.root_sources):
            raise ValueError("sandbox plot roots must be immutable source revisions")
        source_keys = tuple(
            (source.dataset_id, source.version, source.content_hash) for source in self.root_sources
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("sandbox plot roots must be unique")
        if tuple(item.backend for item in self.readbacks) != self.backends:
            raise ValueError("sandbox readbacks must align with requested backends")
        if any(item.document != self.readbacks[0].document for item in self.readbacks):
            raise ValueError("sandbox backend readbacks must identify one document")
        if self.readbacks[0].document.plot_id != self.document.plot_id or (
            self.readbacks[0].document.plot_version != self.document.plot_version
        ):
            raise ValueError("sandbox handle document must match backend readback")
        artifact_pairs = tuple((item.backend, item.format) for item in self.artifacts)
        if len(artifact_pairs) != len(set(artifact_pairs)):
            raise ValueError("sandbox artifacts must be unique per backend and format")
        artifact_ids = tuple(item.artifact_id for item in self.artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("sandbox artifact identities must be unique")
        expected_formats = {
            "matplotlib": {"png", "svg"},
            "origin": {"opju"},
        }
        for backend in self.backends:
            observed = {item.format for item in self.artifacts if item.backend == backend}
            if observed != expected_formats[backend]:
                raise ValueError("sandbox artifacts are incomplete for one backend")
        if self.lineage[-1].output_document != self.readbacks[0].document:
            raise ValueError("sandbox handle must match its terminal lineage step")
        if tuple(item.content_hash for item in self.artifacts) != (
            self.lineage[-1].artifact_hashes
        ):
            raise ValueError("sandbox artifact hashes must match terminal lineage")
        if (self.parent_handle_id is None) != (len(self.lineage) == 1):
            raise ValueError("sandbox parent identity must match its lineage depth")
        if self.parent_handle_id != self.lineage[-1].input_handle_id:
            raise ValueError("sandbox parent must match its terminal lineage step")
        return self


SandboxPlotEdit = Annotated[
    SetTitle
    | SetAxis
    | SetSeriesStyle
    | SetPointMarkerMap
    | SetObservationOverlay
    | SetLegend
    | SetColorMap
    | SetChartParameter
    | SetErrorStyle
    | SetDataLabels
    | AddAnnotation
    | AddCallout
    | AddReferenceLine,
    Field(discriminator="operation"),
]
