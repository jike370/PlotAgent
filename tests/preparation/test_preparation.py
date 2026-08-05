from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from plotagent.importing import Imported, inspect_source
from plotagent.preparation.errors import PreparationErrorCode, PreparationProblem
from plotagent.preparation.models import (
    PREPARATION_SPEC_ADAPTER,
    ApplyPlotOrderSpec,
    FieldMapping,
    IsomorphicConcatSpec,
    MappingAssignment,
    MaskForPlotSpec,
    ProjectMetadataLabelSpec,
    ProjectStructureSpec,
    SelectFieldsSpec,
)
from plotagent.preparation.service import prepare, semantic_signature

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def _imported(name: str) -> Imported:
    result = inspect_source(FILES_ROOT / name)
    assert isinstance(result, Imported)
    return result


def _mapping(candidate: object) -> FieldMapping:
    fields = candidate.fields
    return FieldMapping(
        mapping_id="map_xy_v1",
        assignments=(
            MappingAssignment(role="x", field_id=fields[0].field_id, semantic="independent"),
            MappingAssignment(role="y", field_id=fields[1].field_id, semantic="dependent"),
        ),
    )


def test_select_preserves_zero_false_rows_and_is_deterministic() -> None:
    candidate = _imported("excel_two_sheets.xlsx").candidates[0]
    mapping = _mapping(candidate)
    spec = SelectFieldsSpec(field_ids=tuple(field.field_id for field in candidate.fields))

    first = prepare((candidate,), mapping, spec)
    second = prepare((candidate,), mapping, spec)

    assert first.rows[0] == (0, 0, False)
    assert first.output_hash == second.output_hash
    assert first.prepared_dataset_id == second.prepared_dataset_id


def test_mask_reports_without_mutating_source() -> None:
    candidate = _imported("csv_nonfinite.csv").candidates[0]
    original_rows = candidate.rows
    mapping = _mapping(candidate)
    spec = MaskForPlotSpec(
        field_ids=(candidate.fields[1].field_id,), missing_policy="exclude_with_report"
    )

    prepared = prepare((candidate,), mapping, spec)

    assert prepared.row_mask == (False, False, False, False)
    assert prepared.excluded_count == 4
    assert candidate.rows == original_rows

    with pytest.raises(PreparationProblem) as caught:
        prepare(
            (candidate,),
            mapping,
            spec.model_copy(update={"missing_policy": "fail"}),
        )
    assert caught.value.code == PreparationErrorCode.PREPARE_NONFINITE


def test_isomorphic_concat_is_explicit_and_preserves_sheet_label() -> None:
    candidates = _imported("excel_two_sheets.xlsx").candidates
    mapping = _mapping(candidates[0])

    prepared = prepare(
        candidates,
        mapping,
        IsomorphicConcatSpec(source_label_field="source_sheet"),
    )

    assert len(prepared.rows) == 4
    assert prepared.fields[-1].normalized_name == "source_sheet"
    assert [row[-1] for row in prepared.rows] == ["Run A", "Run A", "Run B", "Run B"]
    assert semantic_signature(candidates[0], mapping) == semantic_signature(candidates[1], mapping)


def test_non_isomorphic_concat_is_rejected_without_join_fallback() -> None:
    first = _imported("csv_basic.csv").candidates[0]
    second = _imported("excel_two_sheets.xlsx").candidates[0]
    empty_mapping = FieldMapping(mapping_id="empty", assignments=())

    with pytest.raises(PreparationProblem) as caught:
        prepare(
            (first, second),
            empty_mapping,
            IsomorphicConcatSpec(source_label_field="source_sheet"),
        )
    assert caught.value.code == PreparationErrorCode.PREPARE_NON_ISOMORPHIC


def test_metadata_label_order_and_structure_projection_are_closed_operations() -> None:
    metadata_candidate = _imported("txt_metadata.txt").candidates[0]
    mapping = _mapping(metadata_candidate)
    labeled = prepare(
        (metadata_candidate,),
        mapping,
        ProjectMetadataLabelSpec(metadata_key="Instrument", output_field_name="instrument"),
    )
    assert labeled.rows[0][-1] == "Spectrometer"

    ordered = prepare(
        (metadata_candidate,),
        mapping,
        ApplyPlotOrderSpec(
            field_id=metadata_candidate.fields[0].field_id,
            ordered_values=(1, 0),
        ),
    )
    assert ordered.rows == metadata_candidate.rows
    assert ordered.plot_order == (1, 0)

    projected = prepare(
        (metadata_candidate,),
        mapping,
        ProjectStructureSpec(
            orientation="wide_to_long",
            field_ids=(),
            index_field_id=metadata_candidate.fields[0].field_id,
            value_field_ids=(metadata_candidate.fields[1].field_id,),
        ),
    )
    assert len(projected.rows) == 2
    assert len(projected.fields) == 3


@pytest.mark.parametrize("kind", ["join", "filter", "dedupe", "unit_conversion", "formula"])
def test_forbidden_transform_kinds_are_not_in_the_union(kind: str) -> None:
    with pytest.raises(ValidationError):
        PREPARATION_SPEC_ADAPTER.validate_python({"kind": kind})


def test_unknown_fields_are_rejected_by_strict_models() -> None:
    with pytest.raises(ValidationError):
        SelectFieldsSpec.model_validate(
            {"kind": "select_fields", "field_ids": (), "filter": "x > 0"}
        )
