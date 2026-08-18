from __future__ import annotations

from dataclasses import dataclass

from plotagent.contracts.workflows import (
    BucketizeNumeric,
    CompiledTaskItem,
    ConcatenateSources,
    ConvertUnit,
    ResolvedFieldBinding,
    ResolvedWorkflowField,
    SelectFields,
    WorkflowSource,
)
from plotagent.engine import EngineColumn, EngineDataRef, EngineDataView, EngineField
from plotagent.workflows.data_ops import prepare_task_data


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
