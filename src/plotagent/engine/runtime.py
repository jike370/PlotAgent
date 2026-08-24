"""Transaction coordinator for PlotDocument state and backend-native artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from plotagent.engine.contracts import (
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    RestorePlotVersion,
)
from plotagent.engine.ports import (
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
        prior_actions = (
            () if transition.before is None else self.render_actions(transition.before)
        )
        actions = prior_actions + (action,)
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

    def restore(
        self,
        action: RestorePlotVersion,
        *,
        expected_project_revision: int | None = None,
    ) -> RuntimeResult:
        """Clone an earlier native snapshot into the next linear plot version."""

        replay = self.service.replay(action)
        if replay is not None:
            return RuntimeResult(
                document=replay,
                readbacks=tuple(backend.readback(replay) for backend in self.backends),
            )
        transition = self.service.prepare_restore(action)
        source_document = self.service.repository.get(
            action.target, action.source_plot_version
        ).document
        source = self._materialize(transition.after)
        changes: list[PlotBackendChange] = []
        published: list[PlotBackendChange] = []
        try:
            for backend in self.backends:
                self.materialize_backend(backend, source_document)
                change = backend.stage_restore(transition.after, source_document)
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

    def materialize_backend(
        self,
        backend: PlotBackend,
        document: PlotDocument,
    ) -> EngineReadback:
        """Create one backend-native version lazily without changing PlotDocument state."""

        try:
            return backend.readback(document)
        except (FileNotFoundError, NotADirectoryError):
            pass
        if document.plot_version > 1:
            previous = self.service.repository.get(
                document.plot_id,
                document.plot_version - 1,
            ).document
            self.materialize_backend(backend, previous)
        source = self._materialize(document)
        restore_record = next(
            (
                record for record in self.service.repository.actions(document.plot_id)
                if record.document_after.plot_version == document.plot_version
                and isinstance(record.action, RestorePlotVersion)
            ),
            None,
        )
        if restore_record is not None:
            restore_action = cast(RestorePlotVersion, restore_record.action)
            restored_source = self.service.repository.get(
                document.plot_id, restore_action.source_plot_version
            ).document
            self.materialize_backend(backend, restored_source)
            change = backend.stage_restore(document, restored_source)
        else:
            actions = self.render_actions(document)
            change = backend.stage(document, actions, source)
        self._validate_readback(change.readback, document, source)
        try:
            change.publish()
        except Exception:
            change.discard()
            raise
        change.finalize()
        return change.readback

    def render_actions(self, document: PlotDocument) -> tuple[PlotEngineAction, ...]:
        """Resolve the current render branch, skipping history-only restores."""

        actions: list[PlotEngineAction] = []
        for record in self.service.repository.actions(document.plot_id):
            if record.document_after.plot_version > document.plot_version:
                continue
            if isinstance(record.action, RestorePlotVersion):
                source = self.service.repository.get(
                    document.plot_id, record.action.source_plot_version
                ).document
                actions = list(self.render_actions(source))
                continue
            actions.append(record.action)
        if not actions or not isinstance(actions[0], CreatePlot):
            raise PlotRuntimeError("backend render history does not start with create_plot")
        return tuple(actions)

    def _materialize(self, document: PlotDocument) -> EngineRenderSource:
        return EngineRenderSource(data=self._materialize_data(document))

    def _materialize_data(self, document: PlotDocument) -> EngineDataView:
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
