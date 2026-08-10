from __future__ import annotations

from pathlib import Path

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine import (
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineDataViewRepository,
    EngineField,
    RoutedEngineDataProvider,
)
from plotagent.engine.data import EngineDataError
from plotagent.storage import ProjectStore


def _view() -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="calculated",
            dataset_id="plotcalc:persisted",
            version=1,
            content_hash="a" * 64,
        ),
        row_ids=("row:one", "row:two"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:x",
                    name="Time",
                    logical_type="numeric",
                    unit_label="s",
                ),
                values=(0, 1),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:y",
                    name="Signal",
                    logical_type="numeric",
                    unit_label="a.u.",
                ),
                values=(1.5, 2.5),
            ),
        ),
    )


def test_derived_view_persists_in_project_cas_and_survives_reopen(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    expected = _view()
    with ProjectStore.create(workspace) as project:
        repository = EngineDataViewRepository(project)
        assert repository.register(expected) == expected
        assert repository.register(expected) == expected
        assert project.verify_registered_objects()
        assert project.state_counts()["objects"] == 1

    with ProjectStore.open(workspace) as project:
        repository = EngineDataViewRepository(project)
        actual = repository.get(expected.data)
        projected = repository.materialize(expected.data, ("field:y",))

        assert canonical_hash(actual) == canonical_hash(expected)
        assert tuple(column.field.field_id for column in projected.columns) == ("field:y",)
        assert projected.columns[0].values == (1.5, 2.5)


def test_routed_provider_does_not_fall_back_between_data_kinds() -> None:
    class Provider:
        def __init__(self, expected_kind: str) -> None:
            self.expected_kind = expected_kind

        def materialize(self, data, field_ids):
            if data.kind != self.expected_kind:
                raise EngineDataError("wrong provider")
            return _view().model_copy(update={"data": data})

    router = RoutedEngineDataProvider(Provider("source"), Provider("calculated"))
    calculated = _view().data
    source = calculated.model_copy(update={"kind": "source", "dataset_id": "source:routed"})

    assert router.materialize(calculated, ("field:x",)).data.kind == "calculated"
    assert router.materialize(source, ("field:x",)).data.kind == "source"
