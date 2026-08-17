"""Project persistence for immutable preparation recipes and auditable runs."""

from __future__ import annotations

from datetime import UTC, datetime

from plotagent.contracts.canonical import canonical_hash, canonical_json
from plotagent.contracts.data_preparation import DataPreparationRecipe, DataPreparationRun
from plotagent.data_preparation.recipes import MAX_SANDBOX_CANDIDATES
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class DataPreparationRepository:
    """Single-writer persistence for immutable recipes and auditable runs."""

    def __init__(self, project: ProjectStore) -> None:
        self.project = project

    @property
    def _connection(self):  # type: ignore[no-untyped-def]
        return self.project._assert_writer()  # noqa: SLF001

    def save_recipe(self, recipe: DataPreparationRecipe) -> DataPreparationRecipe:
        now = _utc_now()
        payload = recipe.model_dump(mode="json")
        self._connection.execute(
            """
            INSERT INTO data_preparation_recipes (
                recipe_id, recipe_version, source_format, specificity,
                parser_contract_version, recipe_hash, recipe_json, status,
                consecutive_structural_failures, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?)
            """,
            (
                recipe.recipe_id,
                recipe.recipe_version,
                recipe.steps[0].source_format,
                recipe.match_contract.specificity,
                recipe.match_contract.parser_contract_version,
                canonical_hash(payload),
                canonical_json(payload),
                now,
                now,
            ),
        )
        return recipe

    def candidates(self, source_format: str) -> tuple[DataPreparationRecipe, ...]:
        rows = self._connection.execute(
            """
            SELECT recipe_json FROM data_preparation_recipes
            WHERE source_format = ? AND status = 'active'
            ORDER BY specificity DESC, recipe_id, recipe_version DESC
            LIMIT ?
            """,
            (source_format, MAX_SANDBOX_CANDIDATES),
        ).fetchall()
        return tuple(DataPreparationRecipe.model_validate_json(str(row[0])) for row in rows)

    def list_recipes(self) -> tuple[DataPreparationRecipe, ...]:
        rows = self._connection.execute(
            """
            SELECT recipe_json FROM data_preparation_recipes
            WHERE status != 'archived'
            ORDER BY created_at DESC, recipe_id, recipe_version DESC
            """
        ).fetchall()
        return tuple(DataPreparationRecipe.model_validate_json(str(row[0])) for row in rows)

    def get_recipe(
        self, recipe_id: str, recipe_version: int | None = None
    ) -> DataPreparationRecipe:
        sql = "SELECT recipe_json FROM data_preparation_recipes WHERE recipe_id = ?"
        parameters: tuple[object, ...] = (recipe_id,)
        if recipe_version is not None:
            sql += " AND recipe_version = ?"
            parameters = (recipe_id, recipe_version)
        sql += " AND status != 'archived' ORDER BY recipe_version DESC LIMIT 1"
        row = self._connection.execute(sql, parameters).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "数据整理 Recipe 不存在。")
        return DataPreparationRecipe.model_validate_json(str(row[0]))

    def record_recipe_success(self, recipe: DataPreparationRecipe) -> None:
        """Reset transient health after a fully validated preparation."""

        self._connection.execute(
            """
            UPDATE data_preparation_recipes
            SET consecutive_structural_failures = 0, updated_at = ?
            WHERE recipe_id = ? AND recipe_version = ? AND status = 'active'
            """,
            (_utc_now(), recipe.recipe_id, recipe.recipe_version),
        )

    def record_recipe_structural_failure(self, recipe: DataPreparationRecipe) -> None:
        """Fail closed after repeated output-contract drift without mutating the recipe."""

        self._connection.execute(
            """
            UPDATE data_preparation_recipes
            SET
                consecutive_structural_failures = consecutive_structural_failures + 1,
                status = CASE
                    WHEN consecutive_structural_failures + 1 >= 3 THEN 'needs_review'
                    ELSE status
                END,
                updated_at = ?
            WHERE recipe_id = ? AND recipe_version = ? AND status = 'active'
            """,
            (_utc_now(), recipe.recipe_id, recipe.recipe_version),
        )

    def save_run(self, run: DataPreparationRun) -> DataPreparationRun:
        payload = canonical_json(run.model_dump(mode="json"))
        self._connection.execute(
            """
            INSERT INTO data_preparation_runs (
                run_id, resource_id, source_object_hash, probe_hash, state, route,
                selected_recipe_id, selected_recipe_version, run_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                state=excluded.state,
                route=excluded.route,
                selected_recipe_id=excluded.selected_recipe_id,
                selected_recipe_version=excluded.selected_recipe_version,
                run_json=excluded.run_json,
                updated_at=excluded.updated_at
            """,
            (
                run.run_id,
                run.resource_id,
                run.source_object_hash,
                run.probe.probe_hash,
                run.state,
                run.route,
                run.selected_recipe_id,
                run.selected_recipe_version,
                payload,
                run.created_at,
                run.updated_at,
            ),
        )
        return run

    def get_run(self, run_id: str) -> DataPreparationRun:
        row = self._connection.execute(
            "SELECT run_json FROM data_preparation_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "数据整理运行不存在。")
        return DataPreparationRun.model_validate_json(str(row[0]))

    def confirm_run(self, run_id: str, *, accept: bool) -> DataPreparationRun:
        run = self.get_run(run_id)
        if run.state != "awaiting_confirmation":
            raise StorageProblem(
                StorageErrorCode.COMMIT_FAILED,
                "数据整理运行当前不等待确认。",
            )
        updated = run.model_copy(
            update={
                "state": "committed" if accept else "cancelled",
                "updated_at": _utc_now(),
            }
        )
        return self.save_run(updated)
