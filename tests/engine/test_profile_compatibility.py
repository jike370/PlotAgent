from __future__ import annotations

from plotagent.contracts.base import ContentTableRef
from plotagent.contracts.datasets import (
    DataQualitySummary,
    SourceDataset,
    SourceField,
    UnitSpec,
)
from plotagent.engine.compatibility import profile_compatibility
from plotagent.engine.profiles import ENGINE_PROFILES

HASH_A = "a" * 64
HASH_B = "b" * 64
PROFILES = {profile.profile_id: profile for profile in ENGINE_PROFILES}


def _source(*logical_types: str, rows: int = 4) -> SourceDataset:
    fields = tuple(
        SourceField(
            field_id=f"field:f{index}",
            name=f"Field {index}",
            logical_type=logical_type,  # type: ignore[arg-type]
            physical_type="float64" if logical_type == "numeric" else "string",
            unit=UnitSpec(
                source_text="",
                canonical_unit=None,
                dimensionality="dimensionless",
                kind="dimensionless",
                registry_version="units.v1",
            ),
            source_column_index=index,
        )
        for index, logical_type in enumerate(logical_types, start=1)
    )
    return SourceDataset(
        source_dataset_id="source:compatibility",
        source_version=1,
        source_object_hash=HASH_A,
        content_hash=HASH_B,
        import_recipe_version="import.v1",
        parser_version="parser.v1",
        unicode_normalization_version="unicode.nfc.v1",
        field_schema=fields,
        data_ref=ContentTableRef(
            object_hash=HASH_B,
            row_count=rows,
            field_ids=tuple(field.field_id for field in fields),
        ),
        quality=DataQualitySummary(
            total_rows=rows,
            valid_rows=rows,
            missing_values=0,
            nan_values=0,
            positive_inf_values=0,
            negative_inf_values=0,
            unparseable_values=0,
        ),
    )


def test_compatibility_proves_mechanical_feasibility_without_binding_fields() -> None:
    result = profile_compatibility(PROFILES["K09"], _source("categorical", "text", "numeric"))

    assert result.status == "compatible"
    assert [item.role for item in result.requirements] == ["category", "group", "value"]
    assert "field:" not in result.model_dump_json()


def test_compatibility_uses_injective_role_assignment() -> None:
    result = profile_compatibility(
        PROFILES["K06"],
        _source("numeric", "numeric", "numeric", "numeric", "numeric"),
    )

    assert result.status == "incompatible"
    assert result.reason_codes == ("REQUIRED_ROLE_TYPES_UNAVAILABLE",)


def test_time_role_accepts_datetime_and_numeric_series() -> None:
    result = profile_compatibility(PROFILES["K19"], _source("datetime", "numeric"))

    assert result.status == "compatible"


def test_empty_dataset_is_incompatible_even_when_field_types_fit() -> None:
    result = profile_compatibility(PROFILES["K01"], _source("numeric", "numeric", rows=0))

    assert result.status == "incompatible"
    assert result.reason_codes == ("DATASET_EMPTY",)
