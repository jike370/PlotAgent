from __future__ import annotations

from dataclasses import dataclass

import pytest

from plotagent.contracts.workflows import (
    AlignSourcesOnX,
    BucketizeNumeric,
    CompiledTaskItem,
    ConcatenateSources,
    ConvertType,
    ConvertUnit,
    DropEmptyFields,
    ExcludeRows,
    ResolvedFieldBinding,
    ResolvedWorkflowField,
    SelectFields,
    WorkflowOutputField,
    WorkflowSource,
)
from plotagent.engine import EngineColumn, EngineDataRef, EngineDataView, EngineField
from plotagent.workflows.data_ops import WorkflowDataError, prepare_task_data


@dataclass(frozen=True)
class _Provider:
    views: dict[str, EngineDataView]

    def materialize(self, data: EngineDataRef, field_ids: tuple[str, ...]) -> EngineDataView:
        view = self.views[data.dataset_id]
        columns = {column.field.field_id: column for column in view.columns}
        selected = tuple(columns[field_id] for field_id in field_ids)
        return view.model_copy(update={"columns": selected})


@dataclass
class _Registrar:
    registered: EngineDataView | None = None

    def register(self, view: EngineDataView) -> EngineDataView:
        self.registered = view
        return view


def _view(
    dataset_id: str,
    prefix: str,
    values: tuple[tuple[float, float], ...],
    *,
    signal_unit: str | None = None,
) -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="source",
            dataset_id=dataset_id,
            version=1,
            content_hash=("a" if prefix == "one" else "b") * 64,
        ),
        row_ids=tuple(f"row:{prefix}.{position}" for position in range(1, len(values) + 1)),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id=f"field:{prefix}_time",
                    name="Time",
                    logical_type="numeric",
                ),
                values=tuple(row[0] for row in values),
            ),
            EngineColumn(
                field=EngineField(
                    field_id=f"field:{prefix}_signal",
                    name="Signal",
                    logical_type="numeric",
                    unit_label=signal_unit,
                ),
                values=tuple(row[1] for row in values),
            ),
        ),
    )


def test_concatenate_sources_materializes_confirmed_user_facing_labels() -> None:
    sources = (
        WorkflowSource(
            source_alias="data_1",
            source_dataset_id="source:one",
            source_version=1,
            content_hash="a" * 64,
            display_name="series_A.xlsx > Data",
            row_count=2,
        ),
        WorkflowSource(
            source_alias="data_2",
            source_dataset_id="source:two",
            source_version=1,
            content_hash="b" * 64,
            display_name="series_B.xlsx > Data",
            row_count=2,
        ),
    )
    resolved = (
        # The bound value is intentionally resolved before the unbound time
        # field for data_1.  Real providers preserve the requested field order,
        # while the other source remains in its worksheet order.  Concatenation
        # must align isomorphic fields by identity rather than reject that
        # harmless ordering difference.
        ResolvedWorkflowField(
            field_alias="data_1_signal",
            source_alias="data_1",
            field_id="field:one_signal",
            name="Signal",
            logical_type="numeric",
        ),
        ResolvedWorkflowField(
            field_alias="data_1_time",
            source_alias="data_1",
            field_id="field:one_time",
            name="Time",
            logical_type="numeric",
        ),
        ResolvedWorkflowField(
            field_alias="data_2_time",
            source_alias="data_2",
            field_id="field:two_time",
            name="Time",
            logical_type="numeric",
        ),
        ResolvedWorkflowField(
            field_alias="data_2_signal",
            source_alias="data_2",
            field_id="field:two_signal",
            name="Signal",
            logical_type="numeric",
        ),
        ResolvedWorkflowField(
            field_alias="source_group",
            source_alias="data_1",
            field_id="field:workflow_test_source_group",
            name="Source",
            logical_type="categorical",
        ),
    )
    item = CompiledTaskItem(
        task_kind="create",
        item_id="item:test.1",
        plot_alias="plot_1",
        plot_id="plot:test",
        profile_id="K19",
        sources=sources,
        resolved_fields=resolved,
        data_operations=(
            ConcatenateSources(
                source_aliases=("data_1", "data_2"),
                source_labels=("A", "B"),
            ),
        ),
        bindings=(
            ResolvedFieldBinding(role="time", source_alias="data_1", field_id="field:one_time"),
            ResolvedFieldBinding(
                role="series_1", source_alias="data_1", field_id="field:one_signal"
            ),
            ResolvedFieldBinding(
                role="group",
                source_alias="data_1",
                field_id="field:workflow_test_source_group",
            ),
        ),
        visual_actions=(),
        idempotency_key="workflow.test.1",
    )
    registrar = _Registrar()

    prepare_task_data(
        item,
        _Provider(
            {
                "source:one": _view("source:one", "one", ((1, 2), (2, 3))),
                "source:two": _view("source:two", "two", ((1, 5), (2, 8))),
            }
        ),
        registrar,
    )

    assert registrar.registered is not None
    source_column = registrar.registered.columns[-1]
    assert source_column.field.name == "Source"
    assert source_column.values == ("A", "A", "B", "B")


def test_agent_can_request_a_registered_unit_conversion_before_concatenation() -> None:
    sources = (
        WorkflowSource(
            source_alias="data_1",
            source_dataset_id="source:one",
            source_version=1,
            content_hash="a" * 64,
            display_name="one.csv",
            row_count=2,
        ),
        WorkflowSource(
            source_alias="data_2",
            source_dataset_id="source:two",
            source_version=1,
            content_hash="b" * 64,
            display_name="two.csv",
            row_count=2,
        ),
    )
    resolved = (
        ResolvedWorkflowField(
            field_alias="data_1_time",
            source_alias="data_1",
            field_id="field:one_time",
            name="Time",
            logical_type="numeric",
        ),
        ResolvedWorkflowField(
            field_alias="data_1_signal",
            source_alias="data_1",
            field_id="field:one_signal",
            name="Signal",
            logical_type="numeric",
            unit_label="mV",
        ),
        ResolvedWorkflowField(
            field_alias="data_2_time",
            source_alias="data_2",
            field_id="field:two_time",
            name="Time",
            logical_type="numeric",
        ),
        ResolvedWorkflowField(
            field_alias="data_2_signal",
            source_alias="data_2",
            field_id="field:two_signal",
            name="Signal",
            logical_type="numeric",
            unit_label="V",
        ),
        ResolvedWorkflowField(
            field_alias="data_2_signal_mv",
            source_alias="data_2",
            field_id="field:workflow_unit_signal_mv",
            name="Signal",
            logical_type="numeric",
            unit_label="mV",
        ),
        ResolvedWorkflowField(
            field_alias="source_group",
            source_alias="data_1",
            field_id="field:workflow_unit_source_group",
            name="Source",
            logical_type="categorical",
        ),
    )
    item = CompiledTaskItem(
        task_kind="create",
        item_id="item:unit.1",
        plot_alias="plot_1",
        plot_id="plot:unit",
        profile_id="K01",
        sources=sources,
        resolved_fields=resolved,
        data_operations=(
            ConvertUnit(
                source_alias="data_2",
                field_alias="data_2_signal",
                target_unit="mV",
                output_field_alias="data_2_signal_mv",
                output_name="Signal",
            ),
            SelectFields(
                source_alias="data_2",
                field_aliases=("data_2_time", "data_2_signal_mv"),
            ),
            ConcatenateSources(source_aliases=("data_1", "data_2")),
        ),
        bindings=(
            ResolvedFieldBinding(role="x", source_alias="data_1", field_id="field:one_time"),
            ResolvedFieldBinding(role="y", source_alias="data_1", field_id="field:one_signal"),
            ResolvedFieldBinding(
                role="group",
                source_alias="data_1",
                field_id="field:workflow_unit_source_group",
            ),
        ),
        visual_actions=(),
        idempotency_key="workflow.unit.1",
    )

    registrar = _Registrar()
    prepare_task_data(
        item,
        _Provider(
            {
                "source:one": _view("source:one", "one", ((1, 2), (2, 3)), signal_unit="mV"),
                "source:two": _view("source:two", "two", ((1, 0.005), (2, 0.008)), signal_unit="V"),
            }
        ),
        registrar,
    )
    assert registrar.registered is not None
    assert registrar.registered.columns[1].field.unit_label == "mV"
    assert registrar.registered.columns[1].values == (2.0, 3.0, 5.0, 8.0)


def test_agent_can_bucketize_an_explicit_numeric_field_with_confirmed_thresholds() -> None:
    source = WorkflowSource(
        source_alias="data_1",
        source_dataset_id="source:one",
        source_version=1,
        content_hash="a" * 64,
        display_name="signal.csv",
        row_count=5,
    )
    output_id = "field:workflow_bucket_level"
    item = CompiledTaskItem(
        task_kind="create",
        item_id="item:bucket.1",
        plot_alias="plot_1",
        plot_id="plot:bucket",
        profile_id="K03",
        sources=(source,),
        resolved_fields=(
            ResolvedWorkflowField(
                field_alias="time",
                source_alias="data_1",
                field_id="field:one_time",
                name="Time",
                logical_type="numeric",
            ),
            ResolvedWorkflowField(
                field_alias="signal",
                source_alias="data_1",
                field_id="field:one_signal",
                name="Signal",
                logical_type="numeric",
                unit_label="mV",
            ),
            ResolvedWorkflowField(
                field_alias="level",
                source_alias="data_1",
                field_id=output_id,
                name="Level",
                logical_type="categorical",
            ),
        ),
        data_operations=(
            BucketizeNumeric(
                source_alias="data_1",
                field_alias="signal",
                boundaries=(2.0, 5.0),
                labels=("低", "中", "高"),
                output_field_alias="level",
                output_name="Level",
            ),
        ),
        bindings=(
            ResolvedFieldBinding(role="x", source_alias="data_1", field_id="field:one_time"),
            ResolvedFieldBinding(role="y", source_alias="data_1", field_id="field:one_signal"),
            ResolvedFieldBinding(role="group", source_alias="data_1", field_id=output_id),
        ),
        visual_actions=(),
        idempotency_key="workflow.bucket.1",
    )
    registrar = _Registrar()
    view = _view(
        "source:one",
        "one",
        ((1, 1.0), (2, 2.0), (3, 4.0), (4, 5.0), (5, 8.0)),
        signal_unit="mV",
    )

    prepare_task_data(item, _Provider({"source:one": view}), registrar)

    assert registrar.registered is not None
    level = next(
        column for column in registrar.registered.columns if column.field.field_id == output_id
    )
    assert level.values == ("低", "中", "中", "高", "高")


def _text_view(*, invalid: bool = False) -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="source", dataset_id="source:text", version=1, content_hash="c" * 64
        ),
        row_ids=("row:header", "row:1", "row:2"),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id="field:angle_text", name="Angle", logical_type="text"
                ),
                values=("Angle", "0.1", "bad" if invalid else "0.2"),
            ),
            EngineColumn(
                field=EngineField(field_id="field:empty", name="Empty", logical_type="text"),
                values=(None, "", None),
            ),
        ),
    )


def _text_item() -> CompiledTaskItem:
    return CompiledTaskItem(
        task_kind="create",
        item_id="item:convert.1",
        plot_alias="plot_1",
        plot_id="plot:convert",
        profile_id="K03",
        sources=(
            WorkflowSource(
                source_alias="data_1",
                source_dataset_id="source:text",
                source_version=1,
                content_hash="c" * 64,
                display_name="instrument.txt > block_1",
                row_count=3,
            ),
        ),
        resolved_fields=(
            ResolvedWorkflowField(
                field_alias="angle_text",
                source_alias="data_1",
                field_id="field:angle_text",
                name="Angle",
                logical_type="text",
            ),
            ResolvedWorkflowField(
                field_alias="empty",
                source_alias="data_1",
                field_id="field:empty",
                name="Empty",
                logical_type="text",
            ),
            ResolvedWorkflowField(
                field_alias="angle_numeric",
                source_alias="data_1",
                field_id="field:workflow_angle_numeric",
                name="Angle",
                logical_type="numeric",
            ),
        ),
        data_operations=(
            ExcludeRows(source_alias="data_1", row_indices=(0,)),
            DropEmptyFields(source_alias="data_1", field_aliases=("empty",)),
            ConvertType(
                source_alias="data_1",
                field_alias="angle_text",
                target_type="numeric",
                output_field_alias="angle_numeric",
                output_name="Angle",
            ),
        ),
        bindings=(
            ResolvedFieldBinding(
                role="x", source_alias="data_1", field_id="field:workflow_angle_numeric"
            ),
            ResolvedFieldBinding(
                role="y", source_alias="data_1", field_id="field:workflow_angle_numeric"
            ),
        ),
        visual_actions=(),
        idempotency_key="workflow.convert.1",
    )


def test_explicit_cleanup_and_strict_text_to_numeric_conversion_are_immutable() -> None:
    source = _text_view()
    registrar = _Registrar()

    prepare_task_data(_text_item(), _Provider({"source:text": source}), registrar)

    assert registrar.registered is not None
    assert len(registrar.registered.row_ids) == 2
    assert all(row_id.startswith("row:workflow.") for row_id in registrar.registered.row_ids)
    assert tuple(column.field.name for column in registrar.registered.columns) == (
        "Angle",
        "Angle",
    )
    assert registrar.registered.columns[-1].values == (0.1, 0.2)
    assert source.row_ids == ("row:header", "row:1", "row:2")
    assert len(source.columns) == 2


def test_type_conversion_reports_the_exact_source_row_instead_of_coercing_to_missing() -> None:
    with pytest.raises(WorkflowDataError) as caught:
        prepare_task_data(
            _text_item(),
            _Provider({"source:text": _text_view(invalid=True)}),
            _Registrar(),
        )

    assert caught.value.code == "WORKFLOW_TYPE_CONVERSION_FAILED"
    assert "row:2" in caught.value.message
    assert "'bad'" in caught.value.message


def _series_view(
    dataset_id: str,
    prefix: str,
    x: tuple[float, ...],
    y: tuple[float, ...],
) -> EngineDataView:
    return EngineDataView(
        data=EngineDataRef(
            kind="source", dataset_id=dataset_id, version=1, content_hash=prefix * 64
        ),
        row_ids=tuple(f"row:{prefix}.{index}" for index in range(len(x))),
        columns=(
            EngineColumn(
                field=EngineField(
                    field_id=f"field:{prefix}_x", name="Angle", logical_type="numeric"
                ),
                values=x,
            ),
            EngineColumn(
                field=EngineField(
                    field_id=f"field:{prefix}_y", name="PSD", logical_type="numeric"
                ),
                values=y,
            ),
        ),
    )


def _aligned_item() -> CompiledTaskItem:
    aliases = ("data_1", "data_2", "data_3")
    prefixes = ("a", "b", "c")
    sources = tuple(
        WorkflowSource(
            source_alias=alias,
            source_dataset_id=f"source:{prefix}",
            source_version=1,
            content_hash=prefix * 64,
            display_name=f"{prefix}.txt > block_1",
            row_count=3,
        )
        for alias, prefix in zip(aliases, prefixes, strict=True)
    )
    resolved = tuple(
        field
        for alias, prefix in zip(aliases, prefixes, strict=True)
        for field in (
            ResolvedWorkflowField(
                field_alias=f"{alias}_x",
                source_alias=alias,
                field_id=f"field:{prefix}_x",
                name="Angle",
                logical_type="numeric",
            ),
            ResolvedWorkflowField(
                field_alias=f"{alias}_y",
                source_alias=alias,
                field_id=f"field:{prefix}_y",
                name="PSD",
                logical_type="numeric",
            ),
        )
    ) + tuple(
        ResolvedWorkflowField(
            field_alias=alias,
            source_alias="data_1",
            field_id=f"field:workflow_{alias}",
            name=name,
            logical_type="numeric",
        )
        for alias, name in (
            ("shared_x", "Angle"),
            ("series_a", "a"),
            ("series_b", "b"),
            ("series_c", "c"),
        )
    )
    operation = AlignSourcesOnX(
        source_aliases=aliases,
        x_field_aliases=("data_1_x", "data_2_x", "data_3_x"),
        value_field_aliases=("data_1_y", "data_2_y", "data_3_y"),
        output_x_field_alias="shared_x",
        output_x_name="Angle",
        output_series_fields=tuple(
            WorkflowOutputField(field_alias=f"series_{prefix}", name=f"{prefix}.txt")
            for prefix in prefixes
        ),
    )
    return CompiledTaskItem(
        task_kind="create",
        item_id="item:align.1",
        plot_alias="plot_1",
        plot_id="plot:align",
        profile_id="X38",
        sources=sources,
        resolved_fields=resolved,
        data_operations=(operation,),
        bindings=(
            ResolvedFieldBinding(
                role="x", source_alias="data_1", field_id="field:workflow_shared_x"
            ),
            *tuple(
                ResolvedFieldBinding(
                    role=f"series_{index}",
                    source_alias="data_1",
                    field_id=f"field:workflow_series_{prefix}",
                )
                for index, prefix in enumerate(prefixes, start=1)
            ),
        ),
        visual_actions=(),
        idempotency_key="workflow.align.1",
    )


def test_multiple_sources_align_to_one_wide_renderer_view_without_interpolation() -> None:
    registrar = _Registrar()
    prepare_task_data(
        _aligned_item(),
        _Provider(
            {
                "source:a": _series_view("source:a", "a", (1, 2, 3), (10, 11, 12)),
                "source:b": _series_view("source:b", "b", (1, 2, 3), (20, 21, 22)),
                "source:c": _series_view("source:c", "c", (1, 2, 3), (30, 31, 32)),
            }
        ),
        registrar,
    )

    assert registrar.registered is not None
    assert tuple(column.field.name for column in registrar.registered.columns) == (
        "Angle",
        "a.txt",
        "b.txt",
        "c.txt",
    )
    assert tuple(column.values for column in registrar.registered.columns) == (
        (1, 2, 3),
        (10, 11, 12),
        (20, 21, 22),
        (30, 31, 32),
    )


def test_multiple_source_alignment_rejects_x_mismatch_without_silent_interpolation() -> None:
    with pytest.raises(WorkflowDataError) as caught:
        prepare_task_data(
            _aligned_item(),
            _Provider(
                {
                    "source:a": _series_view("source:a", "a", (1, 2, 3), (10, 11, 12)),
                    "source:b": _series_view("source:b", "b", (1, 2.5, 3), (20, 21, 22)),
                    "source:c": _series_view("source:c", "c", (1, 2, 3), (30, 31, 32)),
                }
            ),
            _Registrar(),
        )

    assert caught.value.code == "WORKFLOW_ALIGNMENT_X_MISMATCH"
    assert "未执行排序、插值或静默截断" in caught.value.message
