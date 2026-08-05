from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from plotagent.contracts import SourceDataset
from plotagent.importing import Clarification, Rejection
from plotagent.storage import Catalog, ImportResource, ProjectImportService, ProjectStore
from plotagent.storage.errors import StorageErrorCode, StorageProblem

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def test_project_layout_wal_single_writer_lock_and_minimal_catalog(
    storage_root: Path,
) -> None:
    workspace = storage_root / "project"
    catalog_path = storage_root / "catalog.sqlite3"
    with ProjectStore.create(workspace, project_id="project:test") as project:
        assert project.journal_mode().casefold() == "wal"
        assert project.database_path.is_file()
        assert project.objects_root.is_dir()
        assert project.cache_root.is_dir()
        assert project.tmp_root.is_dir()
        with pytest.raises(StorageProblem) as caught:
            ProjectStore.open(workspace)
        assert caught.value.code == StorageErrorCode.PROJECT_ALREADY_OPEN

        with Catalog.create(catalog_path) as catalog:
            entry = catalog.register_project(
                project_id=project.project_id,
                workspace_path=workspace,
                display_name="Test project",
            )
            assert catalog.list_projects() == (entry,)

    with ProjectStore.open(workspace) as reopened:
        assert reopened.project_id == "project:test"

    connection = sqlite3.connect(catalog_path)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert tables == {"schema_info", "projects", "settings"}


def test_correct_import_registers_contracts_and_immutable_cas(storage_root: Path) -> None:
    with ProjectStore.create(storage_root / "project") as project:
        result = ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:basic", path=FILES_ROOT / "csv_basic.csv")
        )

        assert result.kind == "committed"
        assert len(result.datasets) == 1
        record = result.datasets[0]
        assert isinstance(record.source_dataset, SourceDataset)
        assert record.source_dataset.source_version == 1
        assert project.state_counts() == {
            "objects": 2,
            "object_refs": 2,
            "import_recipes": 1,
            "import_sessions": 1,
            "source_dataset_versions": 1,
        }
        assert project.verify_registered_objects()
        assert all(project.object_path(value).is_file() for value in project.object_hashes())
        assert not tuple(project.tmp_root.iterdir())


def test_multi_sheet_import_registers_independent_source_datasets(storage_root: Path) -> None:
    with ProjectStore.create(storage_root / "project") as project:
        result = ProjectImportService(project).import_resource(
            ImportResource(
                resource_id="resource:workbook",
                path=FILES_ROOT / "excel_two_sheets.xlsx",
            )
        )

        assert result.kind == "committed"
        assert len(result.datasets) == 2
        assert {record.logical_source_id.rsplit("/", 1)[-1] for record in result.datasets} == {
            "sheet:Run A",
            "sheet:Run B",
        }
        assert len({record.source_dataset.source_dataset_id for record in result.datasets}) == 2
        assert project.state_counts()["source_dataset_versions"] == 2


def test_reimport_changed_content_creates_new_version_without_overwrite(
    storage_root: Path,
) -> None:
    source = storage_root / "authorized.csv"
    source.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    resource = ImportResource(resource_id="resource:changing", path=source)
    with ProjectStore.create(storage_root / "project") as project:
        first = ProjectImportService(project).import_resource(resource)
        source.write_text("x,y\n0,10\n1,20\n", encoding="utf-8")
        second = ProjectImportService(project).import_resource(resource)

        assert first.kind == second.kind == "committed"
        first_source = first.datasets[0].source_dataset
        second_source = second.datasets[0].source_dataset
        assert first_source.source_dataset_id == second_source.source_dataset_id
        assert (first_source.source_version, second_source.source_version) == (1, 2)
        assert first_source.source_object_hash != second_source.source_object_hash
        assert first_source.content_hash != second_source.content_hash
        records = project.list_source_datasets(first.datasets[0].logical_source_id)
        assert [record.source_dataset.source_version for record in records] == [1, 2]
        assert project.state_counts()["source_dataset_versions"] == 2
        assert project.verify_registered_objects()


@pytest.mark.parametrize(
    ("file_name", "outcome_type"),
    [
        ("clarify_header.csv", Clarification),
        ("reject_duplicate.csv", Rejection),
    ],
)
def test_question_and_rejection_leave_no_formal_state(
    storage_root: Path,
    file_name: str,
    outcome_type: type[Clarification] | type[Rejection],
) -> None:
    with ProjectStore.create(storage_root / "project") as project:
        before = project.state_counts()
        outcome = ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:invalid", path=FILES_ROOT / file_name)
        )

        assert isinstance(outcome, outcome_type)
        assert project.state_counts() == before
        assert project.object_hashes() == ()
        assert not tuple(project.objects_root.rglob("*"))
        assert not tuple(project.tmp_root.iterdir())


@pytest.mark.parametrize(
    "fault_stage",
    ["after_promote", "after_object_rows", "after_dataset_rows", "before_commit"],
)
def test_faults_before_commit_leave_database_and_cas_unpolluted(
    storage_root: Path,
    fault_stage: str,
) -> None:
    def inject(stage: str) -> None:
        if stage == fault_stage:
            raise RuntimeError(f"injected at {stage}")

    with ProjectStore.create(storage_root / "project") as project:
        before = project.state_counts()
        service = ProjectImportService(project, fault_injector=inject)

        with pytest.raises(StorageProblem) as caught:
            service.import_resource(
                ImportResource(resource_id="resource:fault", path=FILES_ROOT / "csv_basic.csv")
            )

        assert caught.value.code == StorageErrorCode.COMMIT_FAILED
        assert project.state_counts() == before
        assert project.object_hashes() == ()
        assert not tuple(path for path in project.objects_root.rglob("*") if path.is_file())
        assert not tuple(project.tmp_root.iterdir())


def test_project_mutation_is_rejected_from_another_thread(storage_root: Path) -> None:
    with ProjectStore.create(storage_root / "project") as project:
        errors: list[StorageProblem] = []

        def write_from_worker() -> None:
            try:
                project.next_source_version("resource:x/table:1")
            except StorageProblem as exc:
                errors.append(exc)

        worker = threading.Thread(target=write_from_worker)
        worker.start()
        worker.join()

        assert len(errors) == 1
        assert errors[0].code == StorageErrorCode.PROJECT_WRITER_THREAD
