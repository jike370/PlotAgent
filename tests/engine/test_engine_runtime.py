from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineProfile,
    EngineReadback,
    FieldBinding,
    PlotBackendChange,
    PlotDocumentRepository,
    PlotEngineRuntime,
    PlotEngineService,
    RestorePlotVersion,
    SetTitle,
)
from plotagent.engine.repository import document_ref
from plotagent.engine.service import EngineCatalog
from plotagent.storage.project import ProjectStore

HASH = "d" * 64
STYLE_HASH = "e" * 64


class FakeDataProvider:
    def __init__(self) -> None:
        self.requested: tuple[str, ...] = ()

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[str, ...],
    ) -> EngineDataView:
        self.requested = field_ids
        return EngineDataView(
            data=data,
            row_ids=("row:1", "row:2"),
            columns=tuple(
                EngineColumn(
                    field=EngineField(
                        field_id=field_id,
                        name=field_id.removeprefix("field:"),
                        logical_type="numeric",
                    ),
                    values=(1.0, 2.0),
                )
                for field_id in field_ids
            ),
        )


@dataclass
class FakeChange:
    readback: EngineReadback
    fail_publish: bool = False
    published: bool = False
    reverted: bool = False
    finalized: bool = False
    discarded: bool = False

    def publish(self) -> None:
        if self.fail_publish:
            raise RuntimeError("publish failed")
        self.published = True

    def revert(self) -> None:
        self.reverted = True

    def finalize(self) -> None:
        self.finalized = True

    def discard(self) -> None:
        self.discarded = True


class FakeBackend:
    def __init__(
        self,
        backend_id: Literal["matplotlib", "origin"],
        *,
        fail_stage: bool = False,
        fail_publish: bool = False,
    ) -> None:
        self._backend_id = backend_id
        self.fail_stage = fail_stage
        self.fail_publish = fail_publish
        self.changes: list[FakeChange] = []
        self.readbacks: dict[int, EngineReadback] = {}
        self.staged_action_ids: list[tuple[str, ...]] = []

    @property
    def backend_id(self) -> Literal["matplotlib", "origin"]:
        return self._backend_id

    def stage(self, document, actions, source) -> PlotBackendChange:
        if self.fail_stage:
            raise RuntimeError("stage failed")
        change = FakeChange(
            readback=EngineReadback(
                document=document_ref(document),
                backend=self.backend_id,
                objects=(),
                data_hash=source.source_hash(),
                style_hash=STYLE_HASH,
            ),
            fail_publish=self.fail_publish,
        )
        self.changes.append(change)
        self.readbacks[document.plot_version] = change.readback
        self.staged_action_ids.append(tuple(action.action_id for action in actions))
        return change

    def stage_restore(self, document, source_document) -> PlotBackendChange:
        source_readback = self.readbacks[source_document.plot_version]
        change = FakeChange(
            readback=source_readback.model_copy(update={"document": document_ref(document)}),
            fail_publish=self.fail_publish,
        )
        self.changes.append(change)
        self.readbacks[document.plot_version] = change.readback
        self.staged_action_ids.append(())
        return change

    def readback(self, document):
        if document.plot_version not in self.readbacks:
            raise FileNotFoundError(document.plot_id)
        readback = self.readbacks[document.plot_version]
        assert readback.document == document_ref(document)
        return readback

    def export(self, document, destination, format):  # pragma: no cover
        raise NotImplementedError


class CurrentStateBackend(FakeBackend):
    def requires_previous_version(self, document) -> bool:
        return False


def _runtime(tmp_path: Path, backends: tuple[FakeBackend, ...]):
    project = ProjectStore.create(tmp_path / "project", project_id="project:runtime")
    catalog = EngineCatalog(
        (
            EngineProfile(
                profile_id="profile.line",
                display_name="Line",
                required_roles=("x", "y"),
                capabilities=(
                    {"operation": "create_plot"},
                    {"operation": "set_title", "parameters": ("text",)},
                ),
            ),
        )
    )
    service = PlotEngineService(catalog, PlotDocumentRepository(project))
    provider = FakeDataProvider()
    return project, provider, PlotEngineRuntime(service, provider, backends)


def _create() -> CreatePlot:
    return CreatePlot(
        action_id="action:create",
        plot_id="plot:demo",
        profile_id="profile.line",
        data=EngineDataRef(
            kind="source",
            dataset_id="dataset.demo",
            version=1,
            content_hash=HASH,
        ),
        bindings=(
            FieldBinding(role="x", field_id="field:x"),
            FieldBinding(role="y", field_id="field:y"),
        ),
    )


def test_runtime_publishes_both_backends_before_committing_domain_state(tmp_path: Path) -> None:
    matplotlib = FakeBackend("matplotlib")
    origin = FakeBackend("origin")
    project, provider, runtime = _runtime(tmp_path, (matplotlib, origin))
    with project:
        result = runtime.execute(_create())

        assert result.document.plot_version == 1
        assert provider.requested == ("field:x", "field:y")
        assert all(
            change.published and change.finalized
            for change in (*matplotlib.changes, *origin.changes)
        )
        assert runtime.service.repository.latest_version("plot:demo") == 1


def test_runtime_discards_staged_work_when_a_backend_cannot_stage(tmp_path: Path) -> None:
    matplotlib = FakeBackend("matplotlib")
    origin = FakeBackend("origin", fail_stage=True)
    project, _provider, runtime = _runtime(tmp_path, (matplotlib, origin))
    with project, pytest.raises(RuntimeError, match="stage failed"):
        runtime.execute(_create())

    assert matplotlib.changes[0].discarded is True
    assert matplotlib.changes[0].published is False


def test_runtime_reverts_published_work_when_later_publish_fails(tmp_path: Path) -> None:
    matplotlib = FakeBackend("matplotlib")
    origin = FakeBackend("origin", fail_publish=True)
    project, _provider, runtime = _runtime(tmp_path, (matplotlib, origin))
    with project:
        with pytest.raises(RuntimeError, match="publish failed"):
            runtime.execute(_create())
        assert runtime.service.repository.latest_version("plot:demo") is None

    assert matplotlib.changes[0].reverted is True
    assert origin.changes[0].discarded is True


def test_runtime_replays_one_action_id_without_rendering_or_committing_twice(
    tmp_path: Path,
) -> None:
    matplotlib = FakeBackend("matplotlib")
    project, _provider, runtime = _runtime(tmp_path, (matplotlib,))
    action = _create()
    with project:
        first = runtime.execute(action)
        replay = runtime.execute(action)

        assert replay == first
        assert len(matplotlib.changes) == 1
        assert len(runtime.service.repository.actions("plot:demo")) == 1


def test_runtime_commits_the_project_revision_with_the_document(tmp_path: Path) -> None:
    matplotlib = FakeBackend("matplotlib")
    project, _provider, runtime = _runtime(tmp_path, (matplotlib,))
    with project:
        runtime.execute(_create(), expected_project_revision=0)
        revision = project._assert_writer().execute(  # noqa: SLF001
            "SELECT revision FROM project_meta"
        ).fetchone()
        assert revision == (1,)


def test_runtime_reverts_artifacts_when_the_project_revision_is_stale(tmp_path: Path) -> None:
    matplotlib = FakeBackend("matplotlib")
    project, _provider, runtime = _runtime(tmp_path, (matplotlib,))
    with project:
        with pytest.raises(ValueError, match="project version is stale"):
            runtime.execute(_create(), expected_project_revision=1)
        assert runtime.service.repository.latest_version("plot:demo") is None

    assert matplotlib.changes[0].reverted is True


def test_runtime_lazily_materializes_every_native_version_without_domain_mutation(
    tmp_path: Path,
) -> None:
    matplotlib = FakeBackend("matplotlib")
    origin = FakeBackend("origin")
    project, _provider, runtime = _runtime(tmp_path, (matplotlib,))
    with project:
        created = runtime.execute(_create()).document
        edited = runtime.execute(
            SetTitle(
                action_id="action:title",
                target=created.plot_id,
                expected_plot_version=created.plot_version,
                text="Edited",
            )
        ).document
        revision_before = project._assert_writer().execute(  # noqa: SLF001
            "SELECT revision FROM project_meta"
        ).fetchone()

        readback = runtime.materialize_backend(origin, edited)

        assert readback.document == document_ref(edited)
        assert [change.readback.document.plot_version for change in origin.changes] == [1, 2]
        assert all(change.published and change.finalized for change in origin.changes)
        assert (
            project._assert_writer().execute(  # noqa: SLF001
                "SELECT revision FROM project_meta"
            ).fetchone()
            == revision_before
        )
        assert runtime.service.repository.latest_version(created.plot_id) == 2


def test_runtime_can_materialize_a_full_history_backend_at_only_the_requested_version(
    tmp_path: Path,
) -> None:
    matplotlib = FakeBackend("matplotlib")
    origin = CurrentStateBackend("origin")
    project, _provider, runtime = _runtime(tmp_path, (matplotlib,))
    with project:
        created = runtime.execute(_create()).document
        edited = runtime.execute(
            SetTitle(
                action_id="action:title-current-state",
                target=created.plot_id,
                expected_plot_version=created.plot_version,
                text="Edited",
            )
        ).document

        readback = runtime.materialize_backend(origin, edited)

        assert readback.document == document_ref(edited)
        assert [change.readback.document.plot_version for change in origin.changes] == [2]
        assert origin.staged_action_ids == [("action:create", "action:title-current-state")]


def test_runtime_restores_an_exact_snapshot_then_appends_new_edits_to_that_state(
    tmp_path: Path,
) -> None:
    matplotlib = FakeBackend("matplotlib")
    project, _provider, runtime = _runtime(tmp_path, (matplotlib,))
    with project:
        created = runtime.execute(_create()).document
        edited = runtime.execute(
            SetTitle(
                action_id="action:title-old",
                target=created.plot_id,
                expected_plot_version=1,
                text="Old edit",
            )
        ).document
        restored = runtime.restore(
            RestorePlotVersion(
                action_id="action:undo",
                target=created.plot_id,
                expected_plot_version=edited.plot_version,
                source_plot_version=created.plot_version,
            )
        ).document
        final = runtime.execute(
            SetTitle(
                action_id="action:title-new",
                target=created.plot_id,
                expected_plot_version=restored.plot_version,
                text="New edit",
            )
        ).document

        assert restored.plot_version == 3
        assert restored.applied_action_ids == (
            "action:create",
            "action:title-old",
            "action:undo",
        )
        assert final.plot_version == 4
        assert runtime.render_actions(final)[-1].action_id == "action:title-new"
        assert matplotlib.staged_action_ids == [
            ("action:create",),
            ("action:create", "action:title-old"),
            (),
            ("action:create", "action:title-new"),
        ]
