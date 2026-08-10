"""Backend ports for the agent-native plotting engine."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from plotagent.contracts.base import FieldId, Sha256, StrictModel, Token
from plotagent.engine.contracts import (
    EngineDataRef,
    EngineDataView,
    PlotDocument,
    PlotDocumentRef,
    PlotEngineAction,
    SemanticObjectId,
)


class EngineDataProvider(Protocol):
    """Adapter from project data storage to a bounded engine data view."""

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[FieldId, ...],
    ) -> EngineDataView: ...


class EngineObjectRef(StrictModel):
    """Read-only semantic link to a backend-native editable object."""

    semantic_id: SemanticObjectId
    backend: Literal["matplotlib", "origin"]
    object_kind: Token
    native_ref: Token


class EngineReadback(StrictModel):
    document: PlotDocumentRef
    backend: Literal["matplotlib", "origin"]
    objects: tuple[EngineObjectRef, ...]
    data_hash: Sha256
    style_hash: Sha256


class EngineArtifact(StrictModel):
    backend: Literal["matplotlib", "origin"]
    format: Literal["png", "svg", "opju"]
    artifact_hash: Sha256
    artifact_size: int


class PlotBackendChange(Protocol):
    """Reversible staged backend mutation used by the local transaction coordinator."""

    @property
    def readback(self) -> EngineReadback: ...

    def publish(self) -> None: ...

    def revert(self) -> None: ...

    def finalize(self) -> None: ...

    def discard(self) -> None: ...


class PlotBackend(Protocol):
    """Backend surface; implementations may not expose arbitrary script execution."""

    @property
    def backend_id(self) -> Literal["matplotlib", "origin"]: ...

    def stage_create(
        self,
        document: PlotDocument,
        data: EngineDataView,
    ) -> PlotBackendChange: ...

    def stage_apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> PlotBackendChange: ...

    def readback(self, document: PlotDocument) -> EngineReadback: ...

    def export(self, document: PlotDocument, destination: Path, format: str) -> EngineArtifact: ...
