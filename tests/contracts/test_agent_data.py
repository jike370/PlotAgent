from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.contracts.agent_data import (
    ConvertTypeOperation,
    DataViewOperation,
    DeduplicateRowsOperation,
    ReshapeWideToLongOperation,
)


def test_operation_union_uses_the_published_discriminator() -> None:
    operation = TypeAdapter(DataViewOperation).validate_json(
        """{
          "kind": "deduplicate_rows",
          "input_handle_id": "view:source",
          "key_field_ids": ["field:id"],
          "keep": "last"
        }"""
    )
    assert isinstance(operation, DeduplicateRowsOperation)
    assert operation.keep == "last"


def test_parsing_options_are_explicit_and_unambiguous() -> None:
    with pytest.raises(ValidationError, match="decimal separator"):
        ConvertTypeOperation(
            input_handle_id="view:source",
            field_id="field:value",
            target_type="numeric",
            output_field_id="field:number",
            output_name="Number",
        )
    with pytest.raises(ValidationError, match="must be disjoint"):
        ConvertTypeOperation(
            input_handle_id="view:source",
            field_id="field:value",
            target_type="boolean",
            output_field_id="field:flag",
            output_name="Flag",
            true_values=("yes",),
            false_values=("YES",),
        )


def test_reshape_contract_rejects_implicit_field_overwrite() -> None:
    with pytest.raises(ValidationError, match="new and distinct"):
        ReshapeWideToLongOperation(
            input_handle_id="view:source",
            id_field_ids=("field:id",),
            value_field_ids=("field:before", "field:after"),
            output_name_field_id="field:id",
            output_name="Condition",
            output_value_field_id="field:value",
            output_value_name="Value",
        )
