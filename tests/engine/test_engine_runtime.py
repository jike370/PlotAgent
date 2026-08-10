from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from plotagent.contracts.canonical import canonical_hash
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

    @property
    def backend_id(self) -> Literal["matplotlib", "origin"]:
        return self._backend_id

    def stage(self, document, actions, data) -> PlotBackendChange:
        if self.fail_stage:
            raise RuntimeError("stage failed")
        change = FakeChange(
            readback=EngineReadback(
                document=document_ref(document),
                backend=self.backend_id,
                objects=(),
                data_hash=canonical_hash(data),
                style_hash=STYLE_HASH,
            ),
            fail_publish=self.fail_publish,
        )
        self.changes.append(change)
        return change

    def readback(self, document):
        assert self.changes[-1].readback.document == document_ref(document)
        return self.changes[-1].readback

    def export(self, document, destination, format):  # pragma: no cover
        raise NotImplementedError


def _runtime(tmp_path: Path, backends: tuple[FakeBackend, ...]):
    project = ProjectStore.create(tmp_path / "project", project_id="project:runtime")
    catalog = EngineCatalog(
        (
            EngineProfile(
                profile_id="profile.line",
                display_name="Line",
                required_roles=("x", "y"),
                capabilities=({"operation": "create_plot"},),
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
