from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from plotagent.batch.models import (
    BatchSubmission,
    BatchSubmissionRequest,
    BatchTaskRecord,
    BatchTemplate,
    BatchWorkItem,
    OutputKey,
    StagedPlot,
)
from plotagent.batch.protocols import CancellationToken
from plotagent.batch.service import BatchService, WorkflowFailure, workflow_error
from plotagent.contracts.base import (
    ColorValue,
    FieldMappingRef,
    PhysicalLength,
    PhysicalSize,
    PlotSpecRef,
    PreparationSpecRef,
    PreparedDatasetRef,
    SourceDatasetRef,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import NeedsInput, Unsupported
from plotagent.contracts.plots import (
    AxisSpec,
    DatasetFieldSignature,
    DatasetSignature,
    PlotProvenance,
    PlotSpec,
    PreparedSeriesData,
    PublicationProfileSnapshot,
    ResolvedStyleSnapshot,
    SafeRichText,
    SafeTextNode,
    ScaleSpec,
    SeriesSpec,
    StyleSourceRef,
    XYFamily,
)
from plotagent.figures.models import (
    AxisCompatibilitySignature,
    FigureCreateRequest,
    FigureResult,
    FigureSourceSnapshot,
    FigureUpgradeRequest,
    PanelReplacement,
)
from plotagent.figures.service import FigureService

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def rich_text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def size() -> PhysicalSize:
    return PhysicalSize(
        width=PhysicalLength(value=89.0, unit="mm"),
        height=PhysicalLength(value=60.0, unit="mm"),
    )


def profile() -> PublicationProfileSnapshot:
    return PublicationProfileSnapshot(
        profile_id="profile.test",
        profile_version=1,
        content_hash=HASH_B,
        physical_size=size(),
        dpi=300,
    )


def style() -> ResolvedStyleSnapshot:
    return ResolvedStyleSnapshot(
        font_family="Arial",
        font_size=PhysicalLength(value=8.0, unit="pt"),
        line_width=PhysicalLength(value=0.8, unit="pt"),
        marker_size=PhysicalLength(value=4.0, unit="pt"),
        colors=(ColorValue(value="#1F77B4"),),
    )


def prepared_ref(name: str, content_hash: str = HASH_A) -> PreparedDatasetRef:
    return PreparedDatasetRef(
        prepared_dataset_id=f"prepared:{name}",
        prepared_version=1,
        content_hash=content_hash,
    )


def plot(
    name: str = "template",
    version: int = 1,
    prepared: PreparedDatasetRef | None = None,
) -> PlotSpec:
    data_ref = prepared or prepared_ref("template")
    return PlotSpec(
        plot_id=f"plot:{name}",
        plot_version=version,
        chart_type_id="K01",
        family=XYFamily(geometry=("line",)),
        prepared_data_refs=(data_ref,),
        scales=(
            ScaleSpec(scale_id="scale:x", kind="linear"),
            ScaleSpec(scale_id="scale:y", kind="linear"),
        ),
        axes=(
            AxisSpec(
                axis_id="axis:x",
                scale_id="scale:x",
                orientation="x",
                position="bottom",
                label=rich_text("X"),
            ),
            AxisSpec(
                axis_id="axis:y",
                scale_id="scale:y",
                orientation="y",
                position="left",
                label=rich_text("Y"),
            ),
        ),
        series=(
            SeriesSpec(
                series_id="series:main",
                geometry="line",
                data=PreparedSeriesData(
                    prepared_dataset_ref=data_ref,
                    role_fields=("field:x", "field:y"),
                ),
            ),
        ),
        style_sources=(
            StyleSourceRef(
                source_kind="project",
                source_id="style.default",
                source_version=1,
                content_hash=HASH_A,
            ),
        ),
        resolved_style=style(),
        publication_profile=profile(),
        provenance=PlotProvenance(origin="manual", engine_build_hash=HASH_C),
    )


def signature(semantic_hash: str = HASH_B) -> DatasetSignature:
    return DatasetSignature(
        fields=(
            DatasetFieldSignature(
                field_id="field:x",
                logical_type="numeric",
                unit_hash=HASH_A,
                semantic_role="x",
            ),
            DatasetFieldSignature(
                field_id="field:y",
                logical_type="numeric",
                unit_hash=HASH_A,
                semantic_role="y",
            ),
        ),
        semantic_hash=semantic_hash,
    )


def work_item(name: str, dataset_signature: DatasetSignature | None = None) -> BatchWorkItem:
    return BatchWorkItem(
        item_id=f"item.{name}",
        source_ref=SourceDatasetRef(
            source_dataset_id=f"source:{name}",
            source_version=1,
            content_hash=HASH_A,
        ),
        dataset_signature=dataset_signature or signature(),
    )


def template() -> BatchTemplate:
    return BatchTemplate(
        field_mapping_ref=FieldMappingRef(
            field_mapping_id="mapping:batch",
            mapping_version=1,
            content_hash=HASH_A,
        ),
        preparation_spec_ref=PreparationSpecRef(
            preparation_spec_id="preparation:batch",
            preparation_version=1,
            content_hash=HASH_B,
        ),
        plot_calculation_spec_ref=None,
        plot_template=plot(),
        shared_style=style(),
    )


def request(
    *,
    task_id: str = "task:batch-one",
    key: str = "submit-one",
    items: tuple[BatchWorkItem, ...] | None = None,
    confirmed: bool = True,
) -> BatchSubmissionRequest:
    return BatchSubmissionRequest(
        task_id=task_id,
        project_id="project:test",
        action_id="action:batch",
        idempotency_key=key,
        batch_id=f"batch:{task_id.split(':')[-1]}",
        mapping_confirmed=confirmed,
        items=items or (work_item("one"), work_item("two")),
        template=template(),
    )


class FakeBatchRepository:
    def __init__(self) -> None:
        self.tasks: dict[str, BatchTaskRecord] = {}
        self.submissions: dict[tuple[str, str], str] = {}
        self.item_outputs: dict[OutputKey, PlotSpecRef] = {}
        self.batch_outputs: dict[OutputKey, object] = {}
        self.fail_item_ids: set[str] = set()
        self.fail_batch_commit = False
        self.on_item_commit: Callable[[str], None] | None = None

    def find_task_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> BatchTaskRecord | None:
        task_id = self.submissions.get((project_id, idempotency_key))
        return None if task_id is None else self.tasks[task_id]

    def add_task(self, task: BatchTaskRecord) -> None:
        self.tasks[task.request.task_id] = task
        self.submissions[(task.request.project_id, task.request.idempotency_key)] = (
            task.request.task_id
        )

    def get_task(self, task_id: str) -> BatchTaskRecord:
        return self.tasks[task_id]

    def save_task(self, task: BatchTaskRecord) -> None:
        self.tasks[task.request.task_id] = task

    def commit_item(self, key: OutputKey, item_id: str, staged: StagedPlot) -> PlotSpecRef:
        existing = self.item_outputs.get(key)
        if existing is not None:
            return existing
        if item_id in self.fail_item_ids:
            raise OSError("injected item commit failure")
        if self.on_item_commit is not None:
            self.on_item_commit(item_id)
        ref = PlotSpecRef(
            plot_id=staged.plot_spec.plot_id,
            plot_version=staged.plot_spec.plot_version,
            content_hash=canonical_hash(staged.plot_spec),
        )
        self.item_outputs[key] = ref
        return ref

    def commit_batch(self, key: OutputKey, batch: object) -> object:
        existing = self.batch_outputs.get(key)
        if existing is not None:
            return existing
        if self.fail_batch_commit:
            raise OSError("injected batch commit failure")
        self.batch_outputs[key] = batch
        return batch


class FakeBatchExecutor:
    def __init__(self) -> None:
        self.prepare_fail: set[str] = set()
        self.stage_fail: set[str] = set()
        self.signature_mismatch: set[str] = set()
        self.prepare_template_ids: list[int] = []
        self.stage_template_ids: list[int] = []
        self.discarded: list[str] = []
        self.on_stage: Callable[[str], None] | None = None

    def prepare_item(
        self, item: BatchWorkItem, batch_template: BatchTemplate, cancellation: CancellationToken
    ) -> PreparedDatasetRef:
        self.prepare_template_ids.append(id(batch_template))
        if item.item_id in self.prepare_fail:
            raise WorkflowFailure(
                workflow_error("PREPARE_UNSUPPORTED", "injected preparation failure")
            )
        return prepared_ref(item.item_id.replace("item.", ""), canonical_hash(item.source_ref))

    def stage_plot(
        self,
        item: BatchWorkItem,
        prepared: PreparedDatasetRef,
        batch_template: BatchTemplate,
        execution_signature: object,
        cancellation: CancellationToken,
    ) -> StagedPlot:
        self.stage_template_ids.append(id(batch_template))
        if self.on_stage is not None:
            self.on_stage(item.item_id)
        if item.item_id in self.stage_fail:
            raise WorkflowFailure(
                workflow_error("PLOTSPEC_FAMILY_MISMATCH", "injected render failure")
            )
        signature_hash = cast("object", execution_signature).content_hash
        if item.item_id in self.signature_mismatch:
            signature_hash = HASH_D
        return StagedPlot(
            staging_id=f"stage.{item.item_id}",
            plot_spec=plot(item.item_id.replace("item.", ""), prepared=prepared),
            execution_signature_hash=signature_hash,
        )

    def discard_staged(self, staged: StagedPlot) -> None:
        self.discarded.append(staged.staging_id)


def accepted(value: object) -> BatchSubmission:
    assert isinstance(value, BatchSubmission)
    return value


def test_batch_requires_one_mapping_and_rejects_heterogeneous_inputs_without_task() -> None:
    repository = FakeBatchRepository()
    service = BatchService(repository, FakeBatchExecutor())
    assert isinstance(service.submit(request(confirmed=False)), NeedsInput)
    mismatched = request(items=(work_item("one"), work_item("two", signature(HASH_C))))
    result = service.submit(mismatched)
    assert isinstance(result, Unsupported)
    assert "does not join" in result.explanation
    assert repository.tasks == {}


def test_batch_success_uses_one_template_and_idempotent_output_slots() -> None:
    repository = FakeBatchRepository()
    executor = FakeBatchExecutor()
    service = BatchService(repository, executor)
    submission = accepted(service.submit(request()))
    replay = accepted(service.submit(request()))
    assert replay.replayed is True
    task = service.run(submission.task_id)
    assert task.state == "succeeded"
    assert task.history == ("queued", "preparing", "running", "committing", "succeeded")
    assert {item.phase for item in task.items} == {"succeeded"}
    assert len(repository.item_outputs) == 2
    assert len(set(executor.prepare_template_ids + executor.stage_template_ids)) == 1
    assert task.batch_spec is not None
    assert task.batch_spec.execution_signature == submission.execution_signature
    service.run(submission.task_id)
    assert len(repository.item_outputs) == 2


def test_partial_success_keeps_stable_errors_and_explicit_export_scope() -> None:
    repository = FakeBatchRepository()
    executor = FakeBatchExecutor()
    executor.stage_fail.add("item.two")
    service = BatchService(repository, executor)
    task = service.run(accepted(service.submit(request())).task_id)
    assert task.state == "partially_succeeded"
    assert task.item("item.two").error is not None
    assert task.item("item.two").error.code == "PLOTSPEC_FAMILY_MISMATCH"
    assert len(repository.item_outputs) == 1
    with pytest.raises(WorkflowFailure) as empty:
        service.resolve_export_scope(task.request.task_id, "all")
    assert empty.value.error.code == "BATCH_EXPORT_SCOPE_EMPTY"
    service.set_review_state(task.request.task_id, ("item.one",), "confirmed")
    export = service.resolve_export_scope(task.request.task_id, "all")
    assert len(export.target_refs) == 1
    assert {(item.item_id, item.reason) for item in export.excluded} == {
        ("item.two", "failed")
    }
    selected = service.resolve_export_scope(
        task.request.task_id, "selected", ("item.one",)
    )
    assert selected.target_refs == export.target_refs


def test_failed_item_commit_does_not_publish_a_plot_and_can_be_retried_explicitly() -> None:
    repository = FakeBatchRepository()
    executor = FakeBatchExecutor()
    repository.fail_item_ids.add("item.two")
    service = BatchService(repository, executor)
    task = service.run(accepted(service.submit(request())).task_id)
    assert task.state == "partially_succeeded"
    assert task.item("item.two").plot_ref is None
    assert len(repository.item_outputs) == 1
    repository.fail_item_ids.clear()
    retried = accepted(service.retry_failed(task.request.task_id, "task:retry", "retry-key"))
    retry_task = service.run(retried.task_id)
    assert retry_task.state == "succeeded"
    assert tuple(item.work_item.item_id for item in retry_task.items) == ("item.two",)


def test_cancel_respects_item_commit_boundary_and_marks_remaining_items() -> None:
    repository = FakeBatchRepository()
    executor = FakeBatchExecutor()
    service = BatchService(repository, executor)
    task_id = accepted(service.submit(request())).task_id
    repository.on_item_commit = lambda item_id: service.request_cancel(task_id)
    task = service.run(task_id)
    assert task.state == "partially_succeeded"
    assert task.item("item.one").phase == "succeeded"
    assert task.item("item.two").phase == "cancelled"
    assert len(repository.item_outputs) == 1
    assert "cancelling" in task.history
    assert service.request_cancel(task_id) is False


def test_queued_cancel_publishes_nothing_and_idempotency_conflicts_are_stable() -> None:
    repository = FakeBatchRepository()
    service = BatchService(repository, FakeBatchExecutor())
    task_id = accepted(service.submit(request())).task_id
    assert service.request_cancel(task_id) is True
    assert repository.get_task(task_id).state == "cancelled"
    assert repository.item_outputs == {}
    changed = replace(request(), items=(work_item("three"),))
    with pytest.raises(WorkflowFailure) as conflict:
        service.submit(changed)
    assert conflict.value.error.code == "BATCH_IDEMPOTENCY_CONFLICT"


def test_batch_object_commit_failure_is_atomic_and_terminal() -> None:
    repository = FakeBatchRepository()
    repository.fail_batch_commit = True
    service = BatchService(repository, FakeBatchExecutor())
    task_id = accepted(service.submit(request())).task_id
    with pytest.raises(WorkflowFailure) as failure:
        service.run(task_id)
    assert failure.value.error.code == "BATCH_COMMIT_FAILED"
    assert repository.get_task(task_id).state == "failed"
    assert repository.batch_outputs == {}


class FakeFigureRepository:
    def __init__(self) -> None:
        self.sources: dict[PlotSpecRef, FigureSourceSnapshot] = {}
        self.latest: dict[str, PlotSpecRef] = {}
        self.figures: dict[str, list[object]] = {}
        self.keys: dict[tuple[str, str], tuple[str, object]] = {}
        self.fail_commit = False

    def add_source(
        self,
        ref: PlotSpecRef,
        *,
        numeric: bool = True,
        x_unit: str = HASH_A,
        y_unit: str = HASH_B,
    ) -> None:
        snapshot = FigureSourceSnapshot(
            ref,
            numeric,
            AxisCompatibilitySignature("linear", x_unit),
            AxisCompatibilitySignature("linear", y_unit),
        )
        self.sources[ref] = snapshot
        if (
            ref.plot_id not in self.latest
            or self.latest[ref.plot_id].plot_version < ref.plot_version
        ):
            self.latest[ref.plot_id] = ref

    def get_plot_snapshot(self, plot_ref: PlotSpecRef) -> FigureSourceSnapshot:
        return self.sources[plot_ref]

    def get_latest_plot_ref(self, plot_id: str) -> PlotSpecRef:
        return self.latest[plot_id]

    def get_figure(self, figure_id: str) -> object:
        return self.figures[figure_id][-1]

    def find_by_idempotency(self, project_id: str, key: str) -> tuple[str, object] | None:
        return self.keys.get((project_id, key))

    def commit_figure(
        self,
        project_id: str,
        key: str,
        request_hash: str,
        figure: object,
        expected_version: int | None,
    ) -> object:
        if self.fail_commit:
            raise OSError("injected Figure commit failure")
        existing = self.figures.get(figure.figure_id, [])
        if expected_version is None:
            if existing:
                raise AssertionError("Figure already exists")
        elif not existing or existing[-1].figure_version != expected_version:
            raise WorkflowFailure(
                workflow_error("FIGURE_VERSION_CONFLICT", "stale Figure commit")
            )
        self.figures.setdefault(figure.figure_id, []).append(figure)
        self.keys[(project_id, key)] = (request_hash, figure)
        return figure


def plot_ref(name: str, version: int = 1, content_hash: str = HASH_A) -> PlotSpecRef:
    return PlotSpecRef(
        plot_id=f"plot:{name}", plot_version=version, content_hash=content_hash
    )


def figure_request(
    refs: tuple[PlotSpecRef, ...], *, key: str = "figure-create"
) -> FigureCreateRequest:
    return FigureCreateRequest(
        project_id="project:test",
        figure_id="figure:test",
        idempotency_key=key,
        layout="2x3",
        plot_refs=refs,
        physical_size=size(),
        publication_profile=profile(),
        axis_policy="shared_both",
        common_legend=True,
    )


def test_figure_fixed_layout_pins_numeric_versions_and_is_idempotent() -> None:
    repository = FakeFigureRepository()
    refs = tuple(plot_ref(f"p{index}") for index in range(5))
    for ref in refs:
        repository.add_source(ref)
    service = FigureService(repository)
    result = service.create(figure_request(refs))
    assert isinstance(result, FigureResult)
    assert result.figure.layout == "2x3"
    assert result.figure.axis_policy == "shared_both"
    assert result.figure.common_legend is True
    assert [panel.panel_label.nodes[0].text for panel in result.figure.panels] == list("ABCDE")
    replay = service.create(figure_request(refs))
    assert isinstance(replay, FigureResult) and replay.replayed is True


def test_figure_rejects_image_sources_and_incompatible_shared_axes() -> None:
    repository = FakeFigureRepository()
    first, second = plot_ref("one"), plot_ref("two")
    repository.add_source(first)
    repository.add_source(second, numeric=False)
    service = FigureService(repository)
    assert isinstance(service.create(figure_request((first, second))), Unsupported)
    repository.add_source(second, numeric=True, y_unit=HASH_C)
    assert isinstance(service.create(figure_request((first, second), key="axes")), Unsupported)
    independent = replace(
        figure_request((first, second), key="independent"), axis_policy="independent"
    )
    assert isinstance(service.create(independent), FigureResult)


def test_figure_source_updates_are_advisory_until_explicit_version_upgrade() -> None:
    repository = FakeFigureRepository()
    old = plot_ref("one", 1, HASH_A)
    other = plot_ref("two", 1, HASH_B)
    repository.add_source(old)
    repository.add_source(other)
    service = FigureService(repository)
    created = service.create(figure_request((old, other)))
    assert isinstance(created, FigureResult)
    newer = plot_ref("one", 2, HASH_C)
    repository.add_source(newer)
    assert created.figure.panels[0].plot_version_ref == old
    updates = service.inspect_source_updates("figure:test")
    assert updates[0].pinned_ref == old and updates[0].latest_ref == newer
    upgraded = service.upgrade_sources(
        FigureUpgradeRequest(
            project_id="project:test",
            figure_id="figure:test",
            expected_figure_version=1,
            idempotency_key="upgrade-one",
            replacements=(PanelReplacement("panel:1", newer),),
        )
    )
    assert isinstance(upgraded, FigureResult)
    assert upgraded.figure.figure_version == 2
    assert upgraded.figure.parent_figure_version == 1
    assert upgraded.figure.panels[0].plot_version_ref == newer
    assert repository.figures["figure:test"][0].panels[0].plot_version_ref == old


def test_figure_version_conflict_and_failed_commit_preserve_current_version() -> None:
    repository = FakeFigureRepository()
    refs = (plot_ref("one"), plot_ref("two"))
    for ref in refs:
        repository.add_source(ref)
    service = FigureService(repository)
    created = service.create(figure_request(refs))
    assert isinstance(created, FigureResult)
    with pytest.raises(WorkflowFailure) as stale:
        service.upgrade_sources(
            FigureUpgradeRequest(
                project_id="project:test",
                figure_id="figure:test",
                expected_figure_version=2,
                idempotency_key="stale",
                replacements=(PanelReplacement("panel:1", refs[0]),),
            )
        )
    assert stale.value.error.code == "FIGURE_VERSION_CONFLICT"
    repository.fail_commit = True
    with pytest.raises(OSError):
        service.create(
            replace(
                figure_request(refs),
                figure_id="figure:other",
                idempotency_key="fail",
            )
        )
    assert "figure:other" not in repository.figures
