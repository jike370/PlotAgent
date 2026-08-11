from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.contracts import FieldMapping, PreparedDataset, SourceDataset, canonical_hash
from plotagent.contracts.base import FieldMappingRef, SourceDatasetRef
from plotagent.contracts.datasets import (
    ApplyPlotOrderSpec,
    FieldRoleBinding,
    FieldSnapshot,
    FilterRowsSpec,
    IsomorphicConcatSpec,
    PreparationSpec,
    ProjectMetadataLabelSpec,
    ProjectStructureSpec,
    SelectFieldsSpec,
)
from plotagent.importing import Imported, SourceDatasetArtifact, inspect_source
from plotagent.preparation import ImportedSourceResolver, prepare, semantic_signature
from plotagent.preparation.errors import PreparationErrorCode, PreparationProblem

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def _imported(name: str) -> Imported:
    result = inspect_source(FILES_ROOT / name)
    assert isinstance(result, Imported)
    return result


def _ref(artifact: SourceDatasetArtifact) -> SourceDatasetRef:
    source = artifact.source_dataset
    return SourceDatasetRef(
        source_dataset_id=source.source_dataset_id,
        source_version=source.source_version,
        content_hash=source.content_hash,
    )


def _mapping(artifacts: tuple[SourceDatasetArtifact, ...]) -> FieldMapping:
    first = artifacts[0]
    fields = first.source_dataset.field_schema
    refs = tuple(_ref(artifact) for artifact in artifacts)
    content_hash = canonical_hash(
        {
            "refs": [ref.model_dump(mode="json") for ref in refs],
            "roles": ["x", "y"],
        }
    )
    return FieldMapping(
        field_mapping_id="mapping:test_xy",
        mapping_version=1,
        chart_type_id="K01",
        source_dataset_refs=refs,
        bindings=(
            FieldRoleBinding(
                role="x",
                field=FieldSnapshot(
                    field_id=fields[0].field_id,
                    name=fields[0].name,
                    logical_type=fields[0].logical_type,
                    unit=fields[0].unit,
                    source_dataset_ref=refs[0],
                ),
            ),
            FieldRoleBinding(
                role="y",
                field=FieldSnapshot(
                    field_id=fields[1].field_id,
                    name=fields[1].name,
                    logical_type=fields[1].logical_type,
                    unit=fields[1].unit,
                    source_dataset_ref=refs[0],
                ),
            ),
        ),
        content_hash=content_hash,
    )


def _common(
    kind: str,
    artifacts: tuple[SourceDatasetArtifact, ...],
    mapping: FieldMapping,
) -> dict[str, Any]:
    return {
        "preparation_spec_id": f"preparation:{kind}",
        "preparation_version": 1,
        "input_refs": tuple(_ref(artifact) for artifact in artifacts),
        "field_mapping_ref": FieldMappingRef(
            field_mapping_id=mapping.field_mapping_id,
            mapping_version=mapping.mapping_version,
            content_hash=mapping.content_hash,
        ),
        "compiler_version": "preparation.compiler.v1",
    }


def _prepare(
    artifacts: tuple[SourceDatasetArtifact, ...],
    mapping: FieldMapping,
    spec: PreparationSpec,
):
    return prepare(
        tuple(artifact.source_dataset for artifact in artifacts),
        mapping,
        spec,
        ImportedSourceResolver(artifacts),
    )


def test_select_preserves_zero_false_rows_and_is_deterministic() -> None:
    artifacts = (_imported("excel_two_sheets.xlsx").sources[0],)
    source = artifacts[0].source_dataset
    mapping = _mapping(artifacts)
    spec = SelectFieldsSpec(
        **_common("select", artifacts, mapping),
        field_ids=tuple(field.field_id for field in source.field_schema),
    )

    first = _prepare(artifacts, mapping, spec)
    second = _prepare(artifacts, mapping, spec)

    assert first.rows[0] == (0, 0, False)
    assert first.prepared_dataset.output_hash == second.prepared_dataset.output_hash
    assert first.prepared_dataset.prepared_dataset_id == second.prepared_dataset.prepared_dataset_id


def test_mask_reports_without_mutating_source() -> None:
    artifacts = (_imported("csv_nonfinite.csv").sources[0],)
    original_rows = artifacts[0].rows
    mapping = _mapping(artifacts)
    field_id = artifacts[0].source_dataset.field_schema[1].field_id
    spec = FilterRowsSpec(
        **_common("mask", artifacts, mapping),
        field_ids=(field_id,),
        missing_policy="exclude_with_report",
    )

    prepared = _prepare(artifacts, mapping, spec)

    assert prepared.row_mask == (False, False, False, False)
    assert prepared.prepared_dataset.excluded_row_count == 4
    assert artifacts[0].rows == original_rows

    with pytest.raises(PreparationProblem) as caught:
        _prepare(
            artifacts,
            mapping,
            spec.model_copy(update={"missing_policy": "fail"}),
        )
    assert caught.value.code == PreparationErrorCode.PREPARE_NONFINITE_POLICY_REQUIRED


def test_isomorphic_concat_is_explicit_and_preserves_sheet_label() -> None:
    artifacts = _imported("excel_two_sheets.xlsx").sources
    mapping = _mapping(artifacts)
    spec = IsomorphicConcatSpec(
        **_common("concat", artifacts, mapping),
        source_label_kind="source_sheet",
        source_label_field_id="field:source_sheet",
    )

    prepared = _prepare(artifacts, mapping, spec)

    assert len(prepared.rows) == 4
    assert prepared.fields[-1].name == "source_sheet"
    assert [row[-1] for row in prepared.rows] == ["Run A", "Run A", "Run B", "Run B"]
    assert semantic_signature(artifacts[0].source_dataset, mapping) == semantic_signature(
        artifacts[1].source_dataset, mapping
    )


def test_non_isomorphic_concat_is_rejected_without_join_fallback() -> None:
    artifacts = (
        _imported("csv_basic.csv").sources[0],
        _imported("excel_two_sheets.xlsx").sources[0],
    )
    mapping = _mapping(artifacts)
    spec = IsomorphicConcatSpec(
        **_common("concat_bad", artifacts, mapping),
        source_label_kind="source_sheet",
        source_label_field_id="field:source_sheet",
    )

    with pytest.raises(PreparationProblem) as caught:
        _prepare(artifacts, mapping, spec)
    assert caught.value.code == PreparationErrorCode.PREPARE_NON_ISOMORPHIC


def test_metadata_label_order_and_structure_projection_are_closed_operations() -> None:
    artifacts = (_imported("txt_metadata.txt").sources[0],)
    source = artifacts[0].source_dataset
    mapping = _mapping(artifacts)
    labeled = _prepare(
        artifacts,
        mapping,
        ProjectMetadataLabelSpec(
            **_common("metadata", artifacts, mapping),
            metadata_key="Instrument",
            output_field_id="field:instrument",
        ),
    )
    assert labeled.rows[0][-1] == "Spectrometer"

    ordered = _prepare(
        artifacts,
        mapping,
        ApplyPlotOrderSpec(
            **_common("order", artifacts, mapping),
            field_id=source.field_schema[0].field_id,
            ordered_values=("1", "0"),
        ),
    )
    assert ordered.rows == artifacts[0].rows
    assert ordered.plot_order == ("1", "0")

    projected = _prepare(
        artifacts,
        mapping,
        ProjectStructureSpec(
            **_common("project", artifacts, mapping),
            input_layout="wide",
            output_layout="long",
            role_fields=(source.field_schema[0].field_id, source.field_schema[1].field_id),
        ),
    )
    assert len(projected.rows) == 2
    assert len(projected.fields) == 3


@pytest.mark.parametrize("kind", ["join", "filter", "dedupe", "unit_conversion", "formula"])
def test_forbidden_transform_kinds_are_not_in_the_union(kind: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(PreparationSpec).validate_python({"kind": kind})


def test_unknown_fields_are_rejected_by_strict_contracts() -> None:
    artifacts = (_imported("csv_basic.csv").sources[0],)
    mapping = _mapping(artifacts)
    with pytest.raises(ValidationError):
        SelectFieldsSpec.model_validate(
            {
                **_common("strict", artifacts, mapping),
                "kind": "select_fields",
                "field_ids": (artifacts[0].source_dataset.field_schema[0].field_id,),
                "filter": "x > 0",
            }
        )


def test_public_import_and_preparation_models_are_w0_contracts() -> None:
    artifacts = (_imported("csv_basic.csv").sources[0],)
    source = artifacts[0].source_dataset
    mapping = _mapping(artifacts)
    spec = SelectFieldsSpec(
        **_common("adapter", artifacts, mapping),
        field_ids=tuple(field.field_id for field in source.field_schema),
    )

    result = _prepare(artifacts, mapping, spec)

    assert isinstance(source, SourceDataset)
    assert isinstance(mapping, FieldMapping)
    assert isinstance(result.prepared_dataset, PreparedDataset)
    assert SourceDataset.__module__ == "plotagent.contracts.datasets"
    assert FieldMapping.__module__ == "plotagent.contracts.datasets"
    assert PreparedDataset.__module__ == "plotagent.contracts.datasets"
