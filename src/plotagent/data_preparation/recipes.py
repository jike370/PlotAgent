"""Pure structure matching and bounded execution for preparation recipes."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Literal, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.data_preparation import (
    DataPreparationMatchContract,
    DataPreparationOutputContract,
    DataPreparationRecipe,
    DataPreparationRun,
    DataPreparationTableContract,
    ParseSourceStep,
    ProbedTable,
    RecipeCandidateEvaluation,
    SourceFormat,
    SourceStructureProbe,
)
from plotagent.importing import inspect_source
from plotagent.importing.models import (
    Clarification,
    Imported,
    ImportResponse,
    Rejection,
    SourceDatasetArtifact,
)

PARSER_CONTRACT_VERSION = "plotagent-import-v1"
MAX_SANDBOX_CANDIDATES = 8


def _source_format(path: Path) -> SourceFormat:
    suffix = path.suffix.casefold().removeprefix(".")
    if suffix not in {"csv", "tsv", "txt", "dat", "xlsx", "xlsm", "xls"}:
        raise ValueError(f"unsupported source format: {suffix}")
    return cast(SourceFormat, suffix)


def _table_key(source: SourceDatasetArtifact, position: int) -> str:
    recipe = source.recipe
    if recipe.sheet is not None:
        return f"sheet:{recipe.sheet}"
    if recipe.block is not None:
        return f"block:{recipe.block}"
    return f"table:{position}"


def _table_structure_payload(source: SourceDatasetArtifact, position: int) -> dict[str, JsonValue]:
    dataset = source.source_dataset
    fields = dataset.field_schema
    return {
        "table_key": _table_key(source, position),
        "column_names": [field.name for field in fields],
        "logical_types": [field.logical_type for field in fields],
        # Scientific unit spelling remains case-sensitive.
        "unit_labels": [field.unit.source_text or None for field in fields],
    }


def probe_source(path: Path, outcome: ImportResponse | None = None) -> SourceStructureProbe:
    """Produce a deterministic non-semantic probe from one authorized file."""

    if outcome is None:
        outcome = inspect_source(path)
    raw = path.read_bytes()
    # Import uses the ordinary SHA-256 of bytes.  Keep both paths identical.
    import hashlib

    source_hash = hashlib.sha256(raw).hexdigest()
    tables: list[ProbedTable] = []
    if isinstance(outcome, Imported):
        for position, source in enumerate(outcome.sources, start=1):
            payload = _table_structure_payload(source, position)
            fields = source.source_dataset.field_schema
            tables.append(
                ProbedTable(
                    table_key=cast(str, payload["table_key"]),
                    display_name=source.display_name,
                    row_count=len(source.rows),
                    column_count=len(fields),
                    column_names=tuple(field.name for field in fields),
                    logical_types=tuple(field.logical_type for field in fields),
                    unit_labels=tuple(field.unit.source_text or None for field in fields),
                    structure_hash=canonical_hash(payload),
                )
            )
        generic_outcome: Literal["imported", "clarification", "rejection"] = "imported"
        generic_code = None
    elif isinstance(outcome, Clarification):
        generic_outcome = "clarification"
        generic_code = outcome.code
    else:
        generic_outcome = "rejection"
        generic_code = outcome.code
    without_hash: dict[str, JsonValue] = {
        "schema_version": "source-structure-probe.v1",
        "source_object_hash": source_hash,
        "source_format": _source_format(path),
        "byte_size": len(raw),
        "generic_parser_outcome": generic_outcome,
        "generic_parser_code": generic_code,
        "tables": [table.model_dump(mode="json") for table in tables],
        "marker_hashes": [],
    }
    return SourceStructureProbe(
        source_object_hash=source_hash,
        source_format=_source_format(path),
        byte_size=len(raw),
        generic_parser_outcome=generic_outcome,
        generic_parser_code=generic_code,
        tables=tuple(tables),
        marker_hashes=(),
        probe_hash=canonical_hash(without_hash),
    )


def output_contract_from_probe(probe: SourceStructureProbe) -> DataPreparationOutputContract:
    if not probe.tables:
        raise ValueError("a recipe requires at least one validated output table")
    return DataPreparationOutputContract(
        tables=tuple(
            DataPreparationTableContract(
                table_key=table.table_key,
                column_names=table.column_names,
                logical_types=table.logical_types,
                unit_labels=table.unit_labels,
                minimum_rows=1 if table.row_count else 0,
                structure_hash=table.structure_hash,
            )
            for table in probe.tables
        )
    )


def build_data_preparation_recipe(
    *,
    run: DataPreparationRun,
    display_name: str,
    parse_step: ParseSourceStep,
    scope: str = "personal",
) -> DataPreparationRecipe:
    """Freeze only a successful mechanical source-to-table trace."""

    if run.state != "committed":
        raise ValueError("only a committed preparation run can become a recipe")
    probe = run.probe
    return DataPreparationRecipe(
        recipe_id=f"data-recipe:{uuid.uuid4().hex}",
        recipe_version=1,
        display_name=display_name,
        scope=cast(Literal["personal", "project"], scope),
        match_contract=DataPreparationMatchContract(
            source_formats=(probe.source_format,),
            table_count=len(probe.tables),
            table_structure_hashes=tuple(table.structure_hash for table in probe.tables),
            required_marker_hashes=probe.marker_hashes,
            parser_contract_version=PARSER_CONTRACT_VERSION,
            specificity=700,
        ),
        steps=(parse_step,),
        output_contract=output_contract_from_probe(probe),
        created_from_run_id=run.run_id,
        created_from_source_hash=run.source_object_hash,
    )


def recipe_hard_matches(recipe: DataPreparationRecipe, probe: SourceStructureProbe) -> bool:
    contract = recipe.match_contract
    if probe.source_format not in contract.source_formats:
        return False
    if not set(contract.required_marker_hashes) <= set(probe.marker_hashes):
        return False
    # If generic parsing yielded structure, use it as a cheap fail-closed index.
    return not probe.tables or (
        len(probe.tables) == contract.table_count
        and tuple(table.structure_hash for table in probe.tables) == contract.table_structure_hashes
    )


def execute_recipe(path: Path, recipe: DataPreparationRecipe) -> ImportResponse:
    """Execute the v1 whitelist.  No expressions, plugins, or scripts are accepted."""

    step = recipe.steps[0]
    if _source_format(path) != step.source_format:
        return Rejection(
            code="DATA_RECIPE_FORMAT_MISMATCH",
            message="数据整理 Recipe 与来源格式不兼容。",
            remediation="请选择其他 Recipe 或交给 Agent 整理。",
            trace=(),
        )
    return inspect_source(
        path,
        encoding=step.encoding,
        delimiter=step.delimiter,
        decimal_mark=step.decimal_mark,
        header_row=step.header_row,
        sheet=step.sheet,
    )


def validate_recipe_output(
    recipe: DataPreparationRecipe, outcome: ImportResponse
) -> tuple[bool, str]:
    if not isinstance(outcome, Imported):
        return False, outcome.code
    probe = probe_source_from_imported(outcome)
    expected = recipe.output_contract.tables
    if len(probe) != len(expected):
        return False, "DATA_RECIPE_TABLE_COUNT_MISMATCH"
    for observed, contract in zip(probe, expected, strict=True):
        if observed.table_key != contract.table_key:
            return False, "DATA_RECIPE_TABLE_IDENTITY_MISMATCH"
        if observed.row_count < contract.minimum_rows:
            return False, "DATA_RECIPE_TOO_FEW_ROWS"
        if observed.structure_hash != contract.structure_hash:
            return False, "DATA_RECIPE_STRUCTURE_MISMATCH"
    return True, "DATA_RECIPE_OUTPUT_VALID"


def probe_source_from_imported(outcome: Imported) -> tuple[ProbedTable, ...]:
    tables: list[ProbedTable] = []
    for position, source in enumerate(outcome.sources, start=1):
        payload = _table_structure_payload(source, position)
        fields = source.source_dataset.field_schema
        tables.append(
            ProbedTable(
                table_key=_table_key(source, position),
                display_name=source.display_name,
                row_count=len(source.rows),
                column_count=len(fields),
                column_names=tuple(field.name for field in fields),
                logical_types=tuple(field.logical_type for field in fields),
                unit_labels=tuple(field.unit.source_text or None for field in fields),
                structure_hash=canonical_hash(payload),
            )
        )
    return tuple(tables)


def evaluate_saved_recipes(
    *, path: Path, probe: SourceStructureProbe, recipes: tuple[DataPreparationRecipe, ...]
) -> tuple[
    tuple[RecipeCandidateEvaluation, ...],
    tuple[tuple[DataPreparationRecipe, Imported], ...],
]:
    evaluations: list[RecipeCandidateEvaluation] = []
    accepted: list[tuple[DataPreparationRecipe, Imported]] = []
    for recipe in recipes[:MAX_SANDBOX_CANDIDATES]:
        started = time.perf_counter()
        if not recipe_hard_matches(recipe, probe):
            evaluations.append(
                RecipeCandidateEvaluation(
                    recipe_id=recipe.recipe_id,
                    recipe_version=recipe.recipe_version,
                    candidate_kind="saved_recipe",
                    display_name=recipe.display_name,
                    specificity=recipe.match_contract.specificity,
                    state="filtered",
                    duration_ms=int((time.perf_counter() - started) * 1_000),
                    reason_code="DATA_RECIPE_HARD_FILTER_MISMATCH",
                )
            )
            continue
        outcome = execute_recipe(path, recipe)
        passed, reason = validate_recipe_output(recipe, outcome)
        duration = int((time.perf_counter() - started) * 1_000)
        if passed:
            imported = cast(Imported, outcome)
            output_hashes = tuple(source.source_dataset.content_hash for source in imported.sources)
            evaluations.append(
                RecipeCandidateEvaluation(
                    recipe_id=recipe.recipe_id,
                    recipe_version=recipe.recipe_version,
                    candidate_kind="saved_recipe",
                    display_name=recipe.display_name,
                    specificity=recipe.match_contract.specificity,
                    state="sandbox_passed",
                    duration_ms=duration,
                    reason_code=reason,
                    output_hashes=output_hashes,
                )
            )
            accepted.append((recipe, imported))
        else:
            evaluations.append(
                RecipeCandidateEvaluation(
                    recipe_id=recipe.recipe_id,
                    recipe_version=recipe.recipe_version,
                    candidate_kind="saved_recipe",
                    display_name=recipe.display_name,
                    specificity=recipe.match_contract.specificity,
                    state="sandbox_failed",
                    duration_ms=duration,
                    reason_code=reason,
                )
            )
    return tuple(evaluations), tuple(accepted)
