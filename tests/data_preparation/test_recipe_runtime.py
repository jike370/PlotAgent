from __future__ import annotations

from pathlib import Path

from plotagent.contracts.canonical import canonical_hash
from plotagent.data_preparation.recipes import (
    build_data_preparation_recipe,
    probe_source,
)
from plotagent.importing import Clarification, Rejection
from plotagent.storage import ImportResource, ProjectImportService, ProjectStore
from plotagent.storage.data_preparation_repository import DataPreparationRepository

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def _save_recipe(
    repository: DataPreparationRepository,
    run_id: str,
    *,
    display_name: str = "双列仪器导出",
):  # type: ignore[no-untyped-def]
    run = repository.get_run(run_id)
    recipe = build_data_preparation_recipe(
        run=run,
        display_name=display_name,
        parse_step=run.executed_steps[0],
    )
    return repository.save_recipe(recipe)


def test_generic_success_can_freeze_only_mechanical_preparation_and_reuse_it(
    tmp_path: Path,
) -> None:
    first_source = tmp_path / "first.csv"
    first_source.write_text("time,signal\n0,1.5\n1,2.5\n", encoding="utf-8")
    second_source = tmp_path / "second.csv"
    second_source.write_text("time,signal\n5,9.5\n6,10.5\n7,11.5\n", encoding="utf-8")

    with ProjectStore.create(tmp_path / "project", project_id="project:recipes") as project:
        service = ProjectImportService(project)
        first = service.import_resource(
            ImportResource(resource_id="resource:first", path=first_source)
        )
        assert first.kind == "committed"
        repository = DataPreparationRepository(project)
        first_run = repository.get_run(first.datasets[0].preparation_run_id)
        assert first_run.route == "generic_parser"
        assert first_run.model_turn_count == 0

        recipe = _save_recipe(repository, first_run.run_id)
        payload = recipe.model_dump(mode="json")
        assert "profile_id" not in str(payload)
        assert "field_mapping" not in str(payload)
        assert "visual" not in str(payload)

        second = service.import_resource(
            ImportResource(resource_id="resource:second", path=second_source)
        )
        assert second.kind == "committed"
        second_run = repository.get_run(second.datasets[0].preparation_run_id)
        assert second_run.route == "saved_recipe"
        assert second_run.selected_recipe_id == recipe.recipe_id
        assert second_run.model_turn_count == 0
        assert second.datasets[0].source_dataset.data_ref.row_count == 3


def test_similar_but_structurally_different_source_does_not_auto_match(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.csv"
    base.write_text("time,signal\n0,1\n1,2\n", encoding="utf-8")
    drifted = tmp_path / "drifted.csv"
    drifted.write_text("time,response,quality\n0,1,ok\n1,2,ok\n", encoding="utf-8")

    with ProjectStore.create(tmp_path / "project", project_id="project:drift") as project:
        service = ProjectImportService(project)
        first = service.import_resource(ImportResource(resource_id="resource:base", path=base))
        assert first.kind == "committed"
        repository = DataPreparationRepository(project)
        recipe = _save_recipe(repository, first.datasets[0].preparation_run_id)

        result = service.import_resource(
            ImportResource(resource_id="resource:drifted", path=drifted)
        )
        assert result.kind == "committed"
        run = repository.get_run(result.datasets[0].preparation_run_id)
        assert run.route == "generic_parser"
        evaluation = next(item for item in run.candidates if item.recipe_id == recipe.recipe_id)
        assert evaluation.state == "filtered"
        assert evaluation.reason_code == "DATA_RECIPE_HARD_FILTER_MISMATCH"


def test_equal_specificity_candidates_require_user_selection(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("time,signal\n0,1\n1,2\n", encoding="utf-8")

    with ProjectStore.create(tmp_path / "project", project_id="project:tie") as project:
        service = ProjectImportService(project)
        first = service.import_resource(ImportResource(resource_id="resource:first", path=source))
        assert first.kind == "committed"
        repository = DataPreparationRepository(project)
        first_recipe = _save_recipe(repository, first.datasets[0].preparation_run_id)
        repository.save_recipe(
            first_recipe.model_copy(
                update={
                    "recipe_id": "data-recipe:second",
                    "display_name": "另一条严格整理流程",
                }
            )
        )

        outcome = service.import_resource(
            ImportResource(resource_id="resource:second", path=source)
        )
        assert isinstance(outcome, Clarification)
        assert outcome.code == "DATA_RECIPE_SELECTION_REQUIRED"
        assert len(outcome.options) == 2
        assert outcome.preparation_run_id is not None
        run = repository.get_run(outcome.preparation_run_id)
        assert run.state == "awaiting_recipe_selection"
        assert len(run.candidates) == 2


def test_generic_parser_failure_is_audited_as_agent_required(tmp_path: Path) -> None:
    source = FILES_ROOT / "reject_ragged.csv"

    with ProjectStore.create(tmp_path / "project", project_id="project:agent") as project:
        result = ProjectImportService(project).import_resource(
            ImportResource(resource_id="resource:ragged", path=source)
        )

        assert isinstance(result, Rejection)
        assert result.preparation_run_id is not None
        run = DataPreparationRepository(project).get_run(result.preparation_run_id)
        assert run.state == "agent_required"
        assert run.route == "generic_parser"
        assert run.model_turn_count == 0


def test_repeated_structural_failures_remove_recipe_from_auto_matching(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("time,signal\n0,1\n1,2\n", encoding="utf-8")

    with ProjectStore.create(tmp_path / "project", project_id="project:health") as project:
        service = ProjectImportService(project)
        imported = service.import_resource(
            ImportResource(resource_id="resource:first", path=source)
        )
        assert imported.kind == "committed"
        repository = DataPreparationRepository(project)
        recipe = _save_recipe(repository, imported.datasets[0].preparation_run_id)

        for _ in range(3):
            repository.record_recipe_structural_failure(recipe)

        assert recipe not in repository.candidates("csv")
        assert recipe in repository.list_recipes()


def test_probe_and_output_are_deterministic_for_the_same_bytes(tmp_path: Path) -> None:
    source = tmp_path / "stable.csv"
    source.write_text("time,signal\n0,1\n1,2\n", encoding="utf-8")
    first = probe_source(source)
    second = probe_source(source)
    assert first == second
    assert first.probe_hash == canonical_hash(
        {
            **first.model_dump(mode="json", exclude={"probe_hash"}),
        }
    )
