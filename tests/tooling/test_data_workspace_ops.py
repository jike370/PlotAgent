from __future__ import annotations

import pytest

from plotagent.contracts.agent_data import (
    AggregateMetric,
    AggregateOperation,
    ConcatenateOperation,
    ConvertTypeOperation,
    ConvertUnitOperation,
    DataFilterPredicate,
    DataJoinKey,
    DataSortKey,
    DeduplicateRowsOperation,
    DeriveColumnOperation,
    FilterRowsOperation,
    KeyedJoinOperation,
    LongToWideOutput,
    ReshapeLongToWideOperation,
    ReshapeWideToLongOperation,
    SelectFieldsOperation,
    SortRowsOperation,
)
from plotagent.engine.contracts import EngineColumn, EngineDataRef, EngineDataView, EngineField
from plotagent.tooling.data_workspace_ops import DataWorkspaceError, apply_data_view_operation

HASH_A = "a" * 64


def view(
    *,
    dataset: str = "source:test",
    rows: tuple[str, ...] = ("row:1", "row:2", "row:3", "row:4"),
    columns: tuple[EngineColumn, ...] | None = None,
) -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="source",
            dataset_id=dataset,
            version=1,
            content_hash=HASH_A,
        ),
        row_ids=rows,
        columns=columns
        or (
            EngineColumn(
                field=EngineField(
                    field_id="field:group",
                    name="Group",
                    logical_type="categorical",
                ),
                values=("B", "A", "A", "A"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:value",
                    name="Value",
                    logical_type="numeric",
                    unit_label="s",
                ),
                values=(3.0, 1.0, 1.0, 2.0),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:text_number",
                    name="Text Number",
                    logical_type="text",
                ),
                values=("3,0", "1,0", "1,0", "2,0"),
            ),
        ),
    )


def test_closed_operations_chain_without_mutating_the_input() -> None:
    original = view()
    converted = apply_data_view_operation(
        ConvertTypeOperation(
            input_handle_id="view:source",
            field_id="field:text_number",
            target_type="numeric",
            output_field_id="field:parsed",
            output_name="Parsed",
            decimal_separator=",",
        ),
        (original,),
    )
    assert converted.columns[-1].values == (3.0, 1.0, 1.0, 2.0)
    assert tuple(column.field.field_id for column in original.columns) == (
        "field:group",
        "field:value",
        "field:text_number",
    )

    milliseconds = apply_data_view_operation(
        ConvertUnitOperation(
            input_handle_id="view:converted",
            field_id="field:value",
            target_unit="ms",
            output_field_id="field:value_ms",
            output_name="Value (ms)",
        ),
        (converted,),
    )
    assert milliseconds.columns[-1].values == (3000.0, 1000.0, 1000.0, 2000.0)

    derived = apply_data_view_operation(
        DeriveColumnOperation(
            input_handle_id="view:milliseconds",
            input_field_ids=("field:value_ms",),
            operator="multiply",
            scalar=2,
            output_field_id="field:double_ms",
            output_name="Double (ms)",
        ),
        (milliseconds,),
    )
    filtered = apply_data_view_operation(
        FilterRowsOperation(
            input_handle_id="view:derived",
            predicates=(
                DataFilterPredicate(
                    field_id="field:double_ms",
                    operator="greater_or_equal",
                    value=2000.0,
                ),
            ),
        ),
        (derived,),
    )
    sorted_view = apply_data_view_operation(
        SortRowsOperation(
            input_handle_id="view:filtered",
            keys=(DataSortKey(field_id="field:double_ms", direction="ascending"),),
        ),
        (filtered,),
    )
    deduplicated = apply_data_view_operation(
        DeduplicateRowsOperation(
            input_handle_id="view:sorted",
            key_field_ids=("field:group", "field:double_ms"),
        ),
        (sorted_view,),
    )
    assert deduplicated.row_ids == ("row:2", "row:4", "row:1")
    assert deduplicated.columns[-1].values == (2000.0, 4000.0, 6000.0)


def test_filter_rows_distinguishes_missing_from_nonfinite_numeric_values() -> None:
    original = view(
        rows=("row:finite", "row:nan", "row:positive-inf", "row:negative-inf"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:value",
                    name="Value",
                    logical_type="numeric",
                ),
                values=(1.0, float("nan"), float("inf"), float("-inf")),
            ),
        ),
    )
    finite = apply_data_view_operation(
        FilterRowsOperation(
            input_handle_id="view:source",
            predicates=(DataFilterPredicate(field_id="field:value", operator="is_finite"),),
        ),
        (original,),
    )
    nonfinite = apply_data_view_operation(
        FilterRowsOperation(
            input_handle_id="view:source",
            predicates=(DataFilterPredicate(field_id="field:value", operator="is_not_finite"),),
        ),
        (original,),
    )

    assert finite.row_ids == ("row:finite",)
    assert nonfinite.row_ids == ("row:nan", "row:positive-inf", "row:negative-inf")


def test_reshape_round_trip_and_explicit_aggregate() -> None:
    wide = view(
        rows=("row:1", "row:2"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:id",
                    name="Subject",
                    logical_type="categorical",
                ),
                values=("S1", "S2"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:before",
                    name="Before",
                    logical_type="numeric",
                    unit_label="mV",
                ),
                values=(1.0, 2.0),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:after",
                    name="After",
                    logical_type="numeric",
                    unit_label="mV",
                ),
                values=(1.5, 2.5),
            ),
        ),
    )
    long = apply_data_view_operation(
        ReshapeWideToLongOperation(
            input_handle_id="view:wide",
            id_field_ids=("field:id",),
            value_field_ids=("field:before", "field:after"),
            output_name_field_id="field:condition",
            output_name="Condition",
            output_value_field_id="field:measurement",
            output_value_name="Measurement",
        ),
        (wide,),
    )
    assert len(long.row_ids) == 4
    assert all(row_id.startswith("row:long.") for row_id in long.row_ids)
    assert long.columns[-2].values == ("Before", "After", "Before", "After")

    restored = apply_data_view_operation(
        ReshapeLongToWideOperation(
            input_handle_id="view:long",
            index_field_ids=("field:id",),
            name_field_id="field:condition",
            value_field_id="field:measurement",
            outputs=(
                LongToWideOutput(value="Before", field_id="field:b2", name="Before"),
                LongToWideOutput(value="After", field_id="field:a2", name="After"),
            ),
        ),
        (long,),
    )
    assert restored.columns[-2].values == (1.0, 2.0)
    assert restored.columns[-1].values == (1.5, 2.5)

    aggregate = apply_data_view_operation(
        AggregateOperation(
            input_handle_id="view:long",
            group_field_ids=("field:condition",),
            metrics=(
                AggregateMetric(
                    operator="mean",
                    input_field_id="field:measurement",
                    output_field_id="field:mean",
                    output_name="Mean",
                ),
                AggregateMetric(
                    operator="count",
                    output_field_id="field:n",
                    output_name="N",
                ),
            ),
        ),
        (long,),
    )
    assert aggregate.columns[0].values == ("Before", "After")
    assert aggregate.columns[1].values == (1.5, 2.0)
    assert aggregate.columns[2].values == (2, 2)


def test_concatenate_and_keyed_join_preserve_declared_relationships() -> None:
    first = view(
        dataset="source:first",
        rows=("row:first.1", "row:first.2"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:id",
                    name="ID",
                    logical_type="categorical",
                ),
                values=("A", "B"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:value",
                    name="Value",
                    logical_type="numeric",
                ),
                values=(1.0, 2.0),
            ),
        ),
    )
    second = view(
        dataset="source:second",
        rows=("row:second.1", "row:second.2"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:other_id",
                    name="ID",
                    logical_type="categorical",
                ),
                values=("C", "D"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:other_value",
                    name="Value",
                    logical_type="numeric",
                ),
                values=(3.0, 4.0),
            ),
        ),
    )
    concatenated = apply_data_view_operation(
        ConcatenateOperation(
            input_handle_ids=("view:first", "view:second"),
            source_labels=("First", "Second"),
            source_label_field_id="field:source",
        ),
        (first, second),
    )
    assert concatenated.columns[0].values == ("A", "B", "C", "D")
    assert concatenated.columns[-1].values == ("First", "First", "Second", "Second")

    metadata = view(
        dataset="source:metadata",
        rows=("row:meta.1", "row:meta.2"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:key",
                    name="ID",
                    logical_type="categorical",
                ),
                values=("A", "B"),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:label",
                    name="Label",
                    logical_type="text",
                ),
                values=("Alpha", "Beta"),
            ),
        ),
    )
    joined = apply_data_view_operation(
        KeyedJoinOperation(
            left_handle_id="view:first",
            right_handle_id="view:metadata",
            keys=(DataJoinKey(left_field_id="field:id", right_field_id="field:key"),),
            how="left",
            expected_relationship="one_to_one",
            right_field_prefix="meta",
        ),
        (first, metadata),
    )
    assert joined.columns[-1].field.name == "meta.Label"
    assert joined.columns[-1].values == ("Alpha", "Beta")

    duplicate_metadata = metadata.model_copy(
        update={
            "row_ids": ("row:meta.1", "row:meta.2", "row:meta.3"),
            "columns": tuple(
                column.model_copy(update={"values": (*column.values, column.values[0])})
                for column in metadata.columns
            ),
        }
    )
    with pytest.raises(DataWorkspaceError, match="cardinality"):
        apply_data_view_operation(
            KeyedJoinOperation(
                left_handle_id="view:first",
                right_handle_id="view:metadata",
                keys=(DataJoinKey(left_field_id="field:id", right_field_id="field:key"),),
                expected_relationship="one_to_one",
            ),
            (first, duplicate_metadata),
        )


def test_select_rejects_unknown_fields_without_partial_output() -> None:
    with pytest.raises(DataWorkspaceError) as caught:
        apply_data_view_operation(
            SelectFieldsOperation(
                input_handle_id="view:source",
                field_ids=("field:missing",),
            ),
            (view(),),
        )
    assert caught.value.code == "DATA_FIELD_NOT_FOUND"


def test_join_requires_explicitly_repaired_nonmissing_keys() -> None:
    left = view(
        dataset="source:left",
        rows=("row:left.1", "row:left.2"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:id",
                    name="ID",
                    logical_type="categorical",
                ),
                values=("A", None),
            ),
        ),
    )
    right = view(
        dataset="source:right",
        rows=("row:right.1",),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:key",
                    name="ID",
                    logical_type="categorical",
                ),
                values=("A",),
            ),
        ),
    )
    with pytest.raises(DataWorkspaceError) as caught:
        apply_data_view_operation(
            KeyedJoinOperation(
                left_handle_id="view:left",
                right_handle_id="view:right",
                keys=(DataJoinKey(left_field_id="field:id", right_field_id="field:key"),),
                expected_relationship="one_to_one",
            ),
            (left, right),
        )
    assert caught.value.code == "DATA_JOIN_KEY_MISSING"
