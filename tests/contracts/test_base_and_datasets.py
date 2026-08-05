from __future__ import annotations

import json
import math

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.contracts.base import ContentTableRef, FieldMappingRef, SourceDatasetRef
from plotagent.contracts.canonical import canonical_hash, canonical_json
from plotagent.contracts.datasets import (
    DataQualitySummary,
    FieldMapping,
    FieldRoleBinding,
    FieldSnapshot,
    PreparationSpec,
    PreparedDataset,
    PreparedDatasetProvenance,
    SourceDataset,
    SourceField,
    UnitSpec,
)

from .helpers import HASH_A, HASH_B, HASH_C


def source_ref() -> SourceDatasetRef:
    return SourceDatasetRef(
        source_dataset_id="source:test",
        source_version=1,
        content_hash=HASH_A,
    )


def unit() -> UnitSpec:
    return UnitSpec(
        source_text="mV",
        canonical_unit="mV",
        dimensionality="voltage",
        kind="recognized",
        registry_version="units.v1",
    )


def test_strict_ref_rejects_unknown_fields_and_coercion() -> None:
    payload = {
        "source_dataset_id": "source:test",
        "source_version": 1,
        "content_hash": HASH_A,
    }
    assert SourceDatasetRef.model_validate(payload).source_version == 1

    with pytest.raises(ValidationError):
        SourceDatasetRef.model_validate({**payload, "unexpected": True})
    with pytest.raises(ValidationError):
        SourceDatasetRef.model_validate({**payload, "source_version": "1"})
    with pytest.raises(ValidationError):
        SourceDatasetRef.model_validate({**payload, "content_hash": "A" * 64})


def test_canonical_json_and_hash_are_order_independent_and_finite() -> None:
    left = {"β": [2, 1], "a": {"y": False, "x": 0}}
    right = {"a": {"x": 0, "y": False}, "β": [2, 1]}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_hash(left) == canonical_hash(right)
    assert len(canonical_hash(left)) == 64
    with pytest.raises(ValueError):
        canonical_json({"value": math.nan})


def test_source_dataset_round_trip_and_invariants() -> None:
    source = SourceDataset(
        source_dataset_id="source:test",
        source_version=1,
        source_object_hash=HASH_A,
        content_hash=HASH_B,
        import_recipe_version="import.v1",
        parser_version="parser.v1",
        unicode_normalization_version="unicode.nfc.v1",
        field_schema=(
            SourceField(
                field_id="field:value",
                name="Value",
                logical_type="numeric",
                physical_type="float64",
                unit=unit(),
                source_column_index=0,
            ),
        ),
        data_ref=ContentTableRef(
            object_hash=HASH_B,
            row_count=1,
            field_ids=("field:value",),
        ),
        quality=DataQualitySummary(
            total_rows=1,
            valid_rows=1,
            missing_values=0,
            nan_values=0,
            positive_inf_values=0,
            negative_inf_values=0,
            unparseable_values=0,
        ),
    )
    encoded = source.model_dump_json()
    assert SourceDataset.model_validate_json(encoded) == source
    assert canonical_hash(source) == canonical_hash(json.loads(encoded))

    with pytest.raises(ValidationError, match="field_schema and data_ref"):
        SourceDataset.model_validate(
            {
                **source.model_dump(),
                "data_ref": ContentTableRef(
                    object_hash=HASH_B,
                    row_count=1,
                    field_ids=("field:other",),
                ),
            }
        )


def test_field_mapping_is_unique_and_source_bound() -> None:
    ref = source_ref()
    snapshot = FieldSnapshot(
        field_id="field:value",
        name="Value",
        logical_type="numeric",
        unit=unit(),
        source_dataset_ref=ref,
    )
    mapping = FieldMapping(
        field_mapping_id="mapping:test",
        mapping_version=1,
        chart_type_id="K01",
        source_dataset_refs=(ref,),
        bindings=(FieldRoleBinding(role="x", field=snapshot),),
        content_hash=HASH_B,
    )
    assert mapping.bindings[0].role == "x"
    with pytest.raises(ValidationError, match="roles must be unique"):
        FieldMapping.model_validate(
            {**mapping.model_dump(), "bindings": (mapping.bindings[0], mapping.bindings[0])}
        )


@pytest.mark.parametrize(
    ("kind", "specific"),
    [
        ("select_fields", {"field_ids": ["field:value"]}),
        (
            "project_structure",
            {
                "input_layout": "wide",
                "output_layout": "long",
                "role_fields": ["field:value"],
            },
        ),
        (
            "isomorphic_concat",
            {
                "source_label_kind": "source_sheet",
                "source_label_field_id": "field:sheet",
            },
        ),
        (
            "project_metadata_label",
            {"metadata_key": "sample", "output_field_id": "field:sample"},
        ),
        (
            "apply_plot_order",
            {"field_id": "field:value", "ordered_values": ["control", "treated"]},
        ),
        (
            "mask_for_plot",
            {"field_ids": ["field:value"], "missing_policy": "exclude_with_report"},
        ),
    ],
)
def test_all_preparation_variants_are_closed(kind: str, specific: dict[str, object]) -> None:
    refs = [source_ref().model_dump(mode="json")]
    if kind == "isomorphic_concat":
        refs.append(
            SourceDatasetRef(
                source_dataset_id="source:second",
                source_version=1,
                content_hash=HASH_C,
            ).model_dump(mode="json")
        )
    payload = {
        "schema_version": "1.0",
        "preparation_spec_id": f"preparation:{kind}",
        "preparation_version": 1,
        "input_refs": refs,
        "field_mapping_ref": {
            "field_mapping_id": "mapping:test",
            "mapping_version": 1,
            "content_hash": HASH_B,
        },
        "compiler_version": "compiler.v1",
        "kind": kind,
        **specific,
    }
    adapter = TypeAdapter(PreparationSpec)
    assert adapter.validate_json(json.dumps(payload)).kind == kind
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps({**payload, "pipeline": []}))


def test_prepared_dataset_hash_and_counts_are_bound() -> None:
    prepared = PreparedDataset(
        prepared_dataset_id="prepared:test",
        prepared_version=1,
        source_dataset_refs=(source_ref(),),
        field_mapping_ref=FieldMappingRef(
            field_mapping_id="mapping:test",
            mapping_version=1,
            content_hash=HASH_A,
        ),
        preparation_spec_ref={
            "preparation_spec_id": "preparation:test",
            "preparation_version": 1,
            "content_hash": HASH_B,
        },
        compiler_version="compiler.v1",
        input_hash=HASH_A,
        output_hash=HASH_C,
        data_ref=ContentTableRef(
            object_hash=HASH_C,
            row_count=3,
            field_ids=("field:value",),
        ),
        included_row_count=2,
        excluded_row_count=1,
        provenance=PreparedDatasetProvenance(
            source_coordinate_kinds=("excel",),
            compiler_build_hash=HASH_B,
        ),
    )
    assert prepared.as_ref().content_hash == HASH_C
    with pytest.raises(ValidationError, match="output_hash"):
        PreparedDataset.model_validate({**prepared.model_dump(), "output_hash": HASH_A})
