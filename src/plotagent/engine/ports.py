"""Backend ports for the agent-native plotting engine."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from plotagent.contracts.base import Sha256, StrictModel, Token
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
        field_ids: tuple[str, ...],
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


class PlotBackend(Protocol):
    """Minimal backend surface; implementations may not expose script execution."""

    @property
    def backend_id(self) -> Literal["matplotlib", "origin"]: ...

    def create(self, document: PlotDocument, data: EngineDataView) -> EngineReadback: ...

    def apply(
        self,
        document: PlotDocument,
        action: PlotEngineAction,
        data: EngineDataView,
    ) -> EngineReadback: ...

    def readback(self, document: PlotDocument) -> EngineReadback: ...

    def export(self, document: PlotDocument, destination: Path, format: str) -> EngineArtifact: ...
