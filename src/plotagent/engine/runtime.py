"""Transaction coordinator for PlotDocument state and backend-native artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from plotagent.engine.contracts import (
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import (
    EngineDataProvider,
    EngineReadback,
    PlotBackend,
    PlotBackendChange,
)
from plotagent.engine.repository import document_ref
from plotagent.engine.service import PlotEngineService


class PlotRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    document: PlotDocument
    readbacks: tuple[EngineReadback, ...]


class PlotEngineRuntime:
    """Apply one public action to all configured backends as one local saga.

    Backends stage changes in private files or objects.  Only after every
    backend has produced valid readback are changes published and the domain
    version committed.  A failed publish or repository commit reverts already
    published backend changes.
    """

    def __init__(
        self,
        service: PlotEngineService,
        data_provider: EngineDataProvider,
        backends: tuple[PlotBackend, ...],
    ) -> None:
        if not backends:
            raise ValueError("the plotting runtime requires at least one backend")
        backend_ids = tuple(backend.backend_id for backend in backends)
        if len(backend_ids) != len(set(backend_ids)):
            raise ValueError("plotting runtime backend ids must be unique")
        self.service = service
        self.data_provider = data_provider
        self.backends = backends

    def execute(self, action: PlotEngineAction) -> RuntimeResult:
        transition = self.service.prepare(action)
        data = self._materialize(transition.after)
        changes: list[PlotBackendChange] = []
        published: list[PlotBackendChange] = []
        try:
            for backend in self.backends:
                change = (
                    backend.stage_create(transition.after, data)
                    if isinstance(action, CreatePlot)
                    else backend.stage_apply(transition.after, action, data)
                )
                self._validate_readback(change.readback, transition.after, data)
                changes.append(change)
            for change in changes:
                change.publish()
                published.append(change)
            document = self.service.commit(transition)
        except Exception:
            for change in reversed(published):
                change.revert()
            for change in changes[len(published) :]:
                change.discard()
            raise
        for change in changes:
            change.finalize()
        return RuntimeResult(
            document=document,
            readbacks=tuple(change.readback for change in changes),
        )

    def _materialize(self, document: PlotDocument) -> EngineDataView:
        field_ids = tuple(binding.field_id for binding in document.bindings)
        view = self.data_provider.materialize(document.data, field_ids)
        if view.data != document.data:
            raise PlotRuntimeError("data provider returned a different immutable data revision")
        returned = {column.field.field_id for column in view.columns}
        if returned != set(field_ids):
            raise PlotRuntimeError("data provider did not return exactly the bound fields")
        return view

    @staticmethod
    def _validate_readback(
        readback: EngineReadback,
        document: PlotDocument,
        data: EngineDataView,
    ) -> None:
        if readback.document != document_ref(document):
            raise PlotRuntimeError("backend readback does not identify the staged plot document")
        if readback.data_hash != data.data.content_hash:
            raise PlotRuntimeError("backend readback data hash differs from the input revision")
