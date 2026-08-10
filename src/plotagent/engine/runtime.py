"""Transaction coordinator for PlotDocument state and backend-native artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from plotagent.engine.contracts import EngineDataView, PlotDocument, PlotEngineAction
from plotagent.engine.ports import (
    EngineComponentInput,
    EngineDataProvider,
    EngineReadback,
    EngineRenderSource,
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

    def execute(
        self,
        action: PlotEngineAction,
        *,
        expected_project_revision: int | None = None,
    ) -> RuntimeResult:
        replay = self.service.replay(action)
        if replay is not None:
            return RuntimeResult(
                document=replay,
                readbacks=tuple(backend.readback(replay) for backend in self.backends),
            )
        transition = self.service.prepare(action)
        source = self._materialize(transition.after)
        prior_actions = tuple(
            record.action for record in self.service.repository.actions(transition.after.plot_id)
        )
        actions = prior_actions + (action,)
        if tuple(item.action_id for item in actions) != transition.after.applied_action_ids:
            raise PlotRuntimeError("backend action replay differs from the plot document history")
        changes: list[PlotBackendChange] = []
        published: list[PlotBackendChange] = []
        try:
            for backend in self.backends:
                change = backend.stage(transition.after, actions, source)
                self._validate_readback(change.readback, transition.after, source)
                changes.append(change)
            for change in changes:
                change.publish()
                published.append(change)
            document = self.service.commit(
                transition,
                expected_project_revision=expected_project_revision,
            )
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

    def _materialize(self, document: PlotDocument) -> EngineRenderSource:
        if document.components:
            components: list[EngineComponentInput] = []
            for reference in document.components:
                stored = self.service.repository.get(reference.plot_id, reference.plot_version)
                if stored.content_hash != reference.content_hash:
                    raise PlotRuntimeError(
                        f"component plot content hash differs from {reference.plot_id}"
                    )
                child = stored.document
                child_data = self._materialize_data(child)
                components.append(
                    EngineComponentInput(
                        document=child,
                        actions=tuple(
                            record.action
                            for record in self.service.repository.actions(child.plot_id)
                            if record.action.action_id in set(child.applied_action_ids)
                        ),
                        data=child_data,
                    )
                )
            return EngineRenderSource(components=tuple(components))
        return EngineRenderSource(data=self._materialize_data(document))

    def _materialize_data(self, document: PlotDocument) -> EngineDataView:
        if document.data is None:
            raise PlotRuntimeError("a data-backed component has no immutable data source")
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
        source: EngineRenderSource,
    ) -> None:
        if readback.document != document_ref(document):
            raise PlotRuntimeError("backend readback does not identify the staged plot document")
        if readback.data_hash != source.source_hash():
            raise PlotRuntimeError("backend readback source hash differs from the input revision")
