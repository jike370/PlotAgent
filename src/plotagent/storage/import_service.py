"""Temp-first import orchestration with one atomic project registration."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from plotagent.contracts.base import ContentTableRef
from plotagent.contracts.data_preparation import (
    DataPreparationRun,
    ParseSourceStep,
    RecipeCandidateEvaluation,
)
from plotagent.data_preparation.recipes import (
    evaluate_saved_recipes,
    probe_source,
    validate_recipe_output,
)
from plotagent.importing import Imported, inspect_source
from plotagent.importing.models import (
    Clarification,
    ClarificationOption,
    Rejection,
    SourceDatasetArtifact,
)
from plotagent.importing.normalize import sha256_bytes
from plotagent.importing.serialization import table_to_parquet_bytes
from plotagent.storage.data_preparation_repository import DataPreparationRepository
from plotagent.storage.models import (
    DatasetRegistration,
    ImportResource,
    ProjectImportOutcome,
)
from plotagent.storage.project import FaultInjector, ImportResponseFactory, ProjectStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _logical_source_id(resource_id: str, artifact: SourceDatasetArtifact) -> str:
    recipe = artifact.recipe
    if recipe.sheet is not None:
        partition = f"sheet:{recipe.sheet}"
    elif recipe.block is not None:
        partition = f"block:{recipe.block}"
    else:
        partition = "table:1"
    return f"{resource_id}/{partition}"


class ProjectImportService:
    def __init__(
        self,
        project: ProjectStore,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self._project = project
        self._fault_injector = fault_injector

    def import_resource(
        self,
        resource: ImportResource,
        *,
        encoding: str | None = None,
        delimiter: str | None = None,
        decimal_mark: str | None = None,
        header_row: int | None = None,
        sheet: str | None = None,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
        response_factory: ImportResponseFactory | None = None,
        before_commit: Callable[[], None] | None = None,
        selected_recipe_id: str | None = None,
        selected_recipe_version: int | None = None,
        agent_assisted: bool = False,
        model_turn_count: int = 0,
        tool_call_count: int = 0,
        input_token_count: int = 0,
        output_token_count: int = 0,
    ) -> ProjectImportOutcome:
        """Copy, inspect, serialize, and atomically register one authorized resource."""

        staged_source = self._project.stage_source(Path(resource.path))
        repository: DataPreparationRepository | None = None
        pending_run: DataPreparationRun | None = None
        try:
            started = time.perf_counter()
            generic_outcome = inspect_source(
                staged_source.path,
                encoding=encoding,
                delimiter=delimiter,
                decimal_mark=decimal_mark,
                header_row=header_row,
                sheet=sheet,
            )
            probe = probe_source(staged_source.path, generic_outcome)
            repository = DataPreparationRepository(self._project)
            saved_recipes = (
                () if agent_assisted else repository.candidates(probe.source_format)
            )
            evaluations, accepted = evaluate_saved_recipes(
                path=staged_source.path,
                probe=probe,
                recipes=saved_recipes,
            )
            selected_recipe = None
            outcome = generic_outcome
            route: Literal["generic_parser", "saved_recipe", "agent_assisted"] = (
                "agent_assisted" if agent_assisted else "generic_parser"
            )
            executed_steps: tuple[ParseSourceStep, ...] = (
                ParseSourceStep(
                    source_format=probe.source_format,
                    encoding=encoding,
                    delimiter=delimiter,
                    decimal_mark=cast(Literal[".", ","] | None, decimal_mark),
                    header_row=header_row,
                    sheet=sheet,
                ),
            )
            if selected_recipe_id is not None:
                selected_recipe = repository.get_recipe(selected_recipe_id, selected_recipe_version)
                explicit = tuple(
                    pair
                    for pair in accepted
                    if pair[0].recipe_id == selected_recipe.recipe_id
                    and pair[0].recipe_version == selected_recipe.recipe_version
                )
                if not explicit:
                    run_id = f"data-run:{uuid.uuid4().hex}"
                    now = _utc_now()
                    repository.save_run(
                        DataPreparationRun(
                            run_id=run_id,
                            project_id=self._project.project_id,
                            resource_id=resource.resource_id,
                            source_object_hash=probe.source_object_hash,
                            probe=probe,
                            state="failed",
                            route="saved_recipe",
                            selected_recipe_id=selected_recipe.recipe_id,
                            selected_recipe_version=selected_recipe.recipe_version,
                            executed_steps=selected_recipe.steps,
                            candidates=evaluations,
                            local_duration_ms=int((time.perf_counter() - started) * 1_000),
                            created_at=now,
                            updated_at=now,
                            failure_code="DATA_RECIPE_SELECTION_INVALID",
                            failure_message="所选 Recipe 未通过当前来源的结构校验。",
                        )
                    )
                    self._project.cleanup_staged_task(staged_source.task_dir)
                    return Rejection(
                        code="DATA_RECIPE_SELECTION_INVALID",
                        message="所选数据整理 Recipe 未通过当前来源的结构校验。",
                        remediation="请选择其他候选或交给 Agent 重新整理。",
                        trace=generic_outcome.trace,
                        preparation_run_id=run_id,
                    )
                outcome = explicit[0][1]
                route = "saved_recipe"
                executed_steps = selected_recipe.steps
            elif accepted:
                highest = max(pair[0].match_contract.specificity for pair in accepted)
                highest_pairs = tuple(
                    pair for pair in accepted if pair[0].match_contract.specificity == highest
                )
                if len(highest_pairs) > 1:
                    run_id = f"data-run:{uuid.uuid4().hex}"
                    now = _utc_now()
                    repository.save_run(
                        DataPreparationRun(
                            run_id=run_id,
                            project_id=self._project.project_id,
                            resource_id=resource.resource_id,
                            source_object_hash=probe.source_object_hash,
                            probe=probe,
                            state="awaiting_recipe_selection",
                            candidates=evaluations,
                            local_duration_ms=int((time.perf_counter() - started) * 1_000),
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    self._project.cleanup_staged_task(staged_source.task_dir)
                    return Clarification(
                        code="DATA_RECIPE_SELECTION_REQUIRED",
                        question=(
                            "多个数据整理 Recipe 同样匹配，请选择一个，或交给 Agent 重新整理。"
                        ),
                        options=tuple(
                            ClarificationOption(
                                value=f"{recipe.recipe_id}@{recipe.recipe_version}",
                                label=f"{recipe.display_name} · v{recipe.recipe_version}",
                            )
                            for recipe, _imported in highest_pairs
                        ),
                        trace=generic_outcome.trace,
                        preparation_run_id=run_id,
                    )
                selected_recipe, outcome = highest_pairs[0]
                route = "saved_recipe"
                executed_steps = selected_recipe.steps

            if not isinstance(outcome, Imported):
                run_id = f"data-run:{uuid.uuid4().hex}"
                now = _utc_now()
                repository.save_run(
                    DataPreparationRun(
                        run_id=run_id,
                        project_id=self._project.project_id,
                        resource_id=resource.resource_id,
                        source_object_hash=probe.source_object_hash,
                        probe=probe,
                        state="failed" if agent_assisted else "agent_required",
                        route=route,
                        executed_steps=executed_steps,
                        candidates=evaluations,
                        local_duration_ms=int((time.perf_counter() - started) * 1_000),
                        model_turn_count=model_turn_count,
                        tool_call_count=tool_call_count,
                        input_token_count=input_token_count,
                        output_token_count=output_token_count,
                        created_at=now,
                        updated_at=now,
                        failure_code=outcome.code if agent_assisted else None,
                        failure_message=(
                            (
                                outcome.question
                                if isinstance(outcome, Clarification)
                                else outcome.message
                            )
                            if agent_assisted
                            else None
                        ),
                    )
                )
                self._project.cleanup_staged_task(staged_source.task_dir)
                return outcome.model_copy(update={"preparation_run_id": run_id})
            if outcome.source_object_hash != staged_source.content_hash:
                raise ValueError("staged source changed during deterministic inspection")

            if selected_recipe is not None:
                valid, reason = validate_recipe_output(selected_recipe, outcome)
                if not valid:
                    repository.record_recipe_structural_failure(selected_recipe)
                    run_id = f"data-run:{uuid.uuid4().hex}"
                    now = _utc_now()
                    repository.save_run(
                        DataPreparationRun(
                            run_id=run_id,
                            project_id=self._project.project_id,
                            resource_id=resource.resource_id,
                            source_object_hash=probe.source_object_hash,
                            probe=probe,
                            state="failed",
                            route="saved_recipe",
                            selected_recipe_id=selected_recipe.recipe_id,
                            selected_recipe_version=selected_recipe.recipe_version,
                            executed_steps=selected_recipe.steps,
                            candidates=evaluations,
                            local_duration_ms=int((time.perf_counter() - started) * 1_000),
                            created_at=now,
                            updated_at=now,
                            failure_code=reason,
                            failure_message="Recipe 输出未通过冻结结构合同。",
                        )
                    )
                    self._project.cleanup_staged_task(staged_source.task_dir)
                    return Rejection(
                        code=reason,
                        message="数据整理 Recipe 的输出未通过冻结结构合同。",
                        remediation="交给 Agent 检查来源结构，原 Recipe 不会被自动放宽。",
                        trace=outcome.trace,
                        preparation_run_id=run_id,
                    )

            if selected_recipe is None:
                evaluations = evaluations + (
                    RecipeCandidateEvaluation(
                        candidate_kind="generic_parser",
                        display_name="内置通用解析",
                        specificity=0,
                        state="selected",
                        duration_ms=int((time.perf_counter() - started) * 1_000),
                        reason_code="DATA_GENERIC_PARSE_VALID",
                        output_hashes=tuple(
                            source.source_dataset.content_hash for source in outcome.sources
                        ),
                    ),
                )
            else:
                evaluations = tuple(
                    item.model_copy(
                        update={"state": "selected"}
                        if item.recipe_id == selected_recipe.recipe_id
                        and item.recipe_version == selected_recipe.recipe_version
                        else {}
                    )
                    for item in evaluations
                )

            run_id = f"data-run:{uuid.uuid4().hex}"
            now = _utc_now()
            pending_run = DataPreparationRun(
                run_id=run_id,
                project_id=self._project.project_id,
                resource_id=resource.resource_id,
                source_object_hash=probe.source_object_hash,
                probe=probe,
                state="validating",
                route=route,
                selected_recipe_id=(
                    selected_recipe.recipe_id if selected_recipe is not None else None
                ),
                selected_recipe_version=(
                    selected_recipe.recipe_version if selected_recipe is not None else None
                ),
                executed_steps=executed_steps,
                candidates=evaluations,
                local_duration_ms=int((time.perf_counter() - started) * 1_000),
                model_turn_count=model_turn_count,
                tool_call_count=tool_call_count,
                input_token_count=input_token_count,
                output_token_count=output_token_count,
                created_at=now,
                updated_at=now,
            )
            repository.save_run(pending_run)

            registrations: list[DatasetRegistration] = []
            for artifact in outcome.sources:
                logical_id = _logical_source_id(resource.resource_id, artifact)
                source_dataset_id = self._project.stable_source_dataset_id(logical_id)
                source_version = self._project.next_source_version(logical_id)
                source = artifact.source_dataset
                parquet_bytes = table_to_parquet_bytes(
                    source_dataset_id=source_dataset_id,
                    source_object_hash=staged_source.content_hash,
                    fields=source.field_schema,
                    rows=artifact.rows,
                    coordinates=artifact.coordinates,
                    recipe=artifact.recipe,
                    quality=source.quality,
                )
                content_hash = sha256_bytes(parquet_bytes)
                stored_source = source.model_copy(
                    update={
                        "source_dataset_id": source_dataset_id,
                        "source_version": source_version,
                        "source_object_hash": staged_source.content_hash,
                        "content_hash": content_hash,
                        "data_ref": ContentTableRef(
                            object_hash=content_hash,
                            row_count=len(artifact.rows),
                            field_ids=tuple(field.field_id for field in source.field_schema),
                        ),
                    }
                )
                stored_artifact = artifact.model_copy(
                    update={
                        "source_dataset": stored_source,
                        "parquet_bytes": parquet_bytes,
                    }
                )
                table_object = self._project.stage_bytes(
                    parquet_bytes,
                    media_type="application/vnd.apache.parquet",
                    task_dir=staged_source.task_dir,
                )
                registrations.append(
                    DatasetRegistration(
                        logical_source_id=logical_id,
                        source_dataset=stored_source,
                        artifact=stored_artifact,
                        table_object=table_object,
                    )
                )
            if before_commit is not None:
                before_commit()
            result = self._project.commit_import(
                resource_id=resource.resource_id,
                preparation_run_id=run_id,
                source_object=staged_source,
                registrations=registrations,
                fault_injector=self._fault_injector,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_factory=response_factory,
                advance_project_revision=not agent_assisted,
            )
            repository.save_run(
                pending_run.model_copy(
                    update={
                        "state": "awaiting_confirmation" if agent_assisted else "committed",
                        "output_source_ids": tuple(
                            record.source_dataset.source_dataset_id for record in result.datasets
                        ),
                        "output_content_hashes": tuple(
                            record.source_dataset.content_hash for record in result.datasets
                        ),
                        "local_duration_ms": int((time.perf_counter() - started) * 1_000),
                        "updated_at": _utc_now(),
                    }
                )
            )
            if selected_recipe is not None:
                repository.record_recipe_success(selected_recipe)
            return result
        except Exception as exc:
            if repository is not None and pending_run is not None:
                repository.save_run(
                    pending_run.model_copy(
                        update={
                            "state": "failed",
                            "failure_code": "DATA_PREPARATION_COMMIT_FAILED",
                            "failure_message": str(exc)[:512] or "数据整理提交失败。",
                            "updated_at": _utc_now(),
                        }
                    )
                )
            self._project.cleanup_staged_task(staged_source.task_dir)
            raise
