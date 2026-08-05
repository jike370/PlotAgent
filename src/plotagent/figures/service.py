"""Pure numeric-only fixed-layout Figure version workflow."""

from __future__ import annotations

from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import Unsupported
from plotagent.contracts.plots import FigurePanel, FigureSpec, SafeRichText, SafeTextNode
from plotagent.figures.models import (
    FigureCreateRequest,
    FigureResult,
    FigureSourceSnapshot,
    FigureUpdate,
    FigureUpgradeRequest,
)
from plotagent.figures.protocols import FigureRepository
from plotagent.workflow_errors import WorkflowFailure, workflow_error

_LAYOUT_CAPACITY = {
    "1x2": 2,
    "1x3": 3,
    "1x4": 4,
    "2x1": 2,
    "2x2": 4,
    "2x3": 6,
    "3x1": 3,
}


class FigureService:
    def __init__(self, repository: FigureRepository) -> None:
        self._repository = repository

    def create(self, request: FigureCreateRequest) -> FigureResult | Unsupported:
        request_hash = self._create_hash(request)
        replay = self._idempotent_replay(
            request.project_id, request.idempotency_key, request_hash
        )
        if replay is not None:
            return replay
        unsupported = self._validate_layout(request.layout, len(request.plot_refs))
        if unsupported is not None:
            return unsupported
        snapshots = tuple(self._repository.get_plot_snapshot(ref) for ref in request.plot_refs)
        unsupported = self._validate_sources(snapshots, request.axis_policy)
        if unsupported is not None:
            return unsupported
        labels = request.panel_labels or tuple(
            self._label(index) for index in range(len(request.plot_refs))
        )
        if len(labels) != len(request.plot_refs):
            raise ValueError("panel labels must match the source plot count")
        figure = FigureSpec(
            figure_id=request.figure_id,
            figure_version=1,
            layout=request.layout,
            panels=tuple(
                FigurePanel(
                    panel_id=f"panel:{index + 1}",
                    plot_version_ref=plot_ref,
                    panel_label=labels[index],
                )
                for index, plot_ref in enumerate(request.plot_refs)
            ),
            alignment=request.alignment,
            axis_policy=request.axis_policy,
            common_legend=request.common_legend,
            physical_size=request.physical_size,
            publication_profile=request.publication_profile,
        )
        committed = self._repository.commit_figure(
            request.project_id,
            request.idempotency_key,
            request_hash,
            figure,
            expected_version=None,
        )
        return FigureResult(committed)

    def inspect_source_updates(self, figure_id: str) -> tuple[FigureUpdate, ...]:
        figure = self._repository.get_figure(figure_id)
        updates: list[FigureUpdate] = []
        for panel in figure.panels:
            latest = self._repository.get_latest_plot_ref(panel.plot_version_ref.plot_id)
            if latest != panel.plot_version_ref:
                updates.append(
                    FigureUpdate(panel.panel_id, panel.plot_version_ref, latest)
                )
        return tuple(updates)

    def upgrade_sources(
        self, request: FigureUpgradeRequest
    ) -> FigureResult | Unsupported:
        if not request.replacements:
            raise ValueError("explicit Figure upgrade requires at least one replacement")
        replacement_ids = tuple(item.panel_id for item in request.replacements)
        if len(set(replacement_ids)) != len(replacement_ids):
            raise ValueError("Figure replacement panel ids must be unique")
        request_hash = canonical_hash(
            {
                "project_id": request.project_id,
                "figure_id": request.figure_id,
                "expected_figure_version": request.expected_figure_version,
                "replacements": [
                    {
                        "panel_id": item.panel_id,
                        "plot_ref": item.plot_ref.model_dump(mode="json"),
                    }
                    for item in request.replacements
                ],
            }
        )
        replay = self._idempotent_replay(
            request.project_id, request.idempotency_key, request_hash
        )
        if replay is not None:
            return replay
        current = self._repository.get_figure(request.figure_id)
        if current.figure_version != request.expected_figure_version:
            raise WorkflowFailure(
                workflow_error(
                    "FIGURE_VERSION_CONFLICT",
                    "The Figure changed after the upgrade request was created.",
                )
            )
        replacement_map = {item.panel_id: item.plot_ref for item in request.replacements}
        known_panels = {panel.panel_id for panel in current.panels}
        if not set(replacement_map).issubset(known_panels):
            raise KeyError("unknown Figure panel")
        panels: list[FigurePanel] = []
        for panel in current.panels:
            replacement = replacement_map.get(panel.panel_id)
            if replacement is None:
                panels.append(panel)
                continue
            if replacement.plot_id != panel.plot_version_ref.plot_id:
                raise ValueError("source upgrades must retain the source plot identity")
            if replacement.plot_version <= panel.plot_version_ref.plot_version:
                raise ValueError("source upgrades must select a newer plot version")
            panels.append(
                FigurePanel(
                    panel_id=panel.panel_id,
                    plot_version_ref=replacement,
                    panel_label=panel.panel_label,
                )
            )
        snapshots = tuple(
            self._repository.get_plot_snapshot(panel.plot_version_ref) for panel in panels
        )
        unsupported = self._validate_sources(snapshots, current.axis_policy)
        if unsupported is not None:
            return unsupported
        upgraded = FigureSpec.model_validate(
            {
                **current.model_dump(mode="python"),
                "figure_version": current.figure_version + 1,
                "panels": tuple(panels),
                "parent_figure_version": current.figure_version,
            }
        )
        committed = self._repository.commit_figure(
            request.project_id,
            request.idempotency_key,
            request_hash,
            upgraded,
            expected_version=current.figure_version,
        )
        return FigureResult(committed)

    def _idempotent_replay(
        self, project_id: str, idempotency_key: str, request_hash: str
    ) -> FigureResult | None:
        existing = self._repository.find_by_idempotency(project_id, idempotency_key)
        if existing is None:
            return None
        existing_hash, figure = existing
        if existing_hash != request_hash:
            raise WorkflowFailure(
                workflow_error(
                    "FIGURE_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already belongs to a different Figure request.",
                )
            )
        return FigureResult(figure, replayed=True)

    def _validate_layout(self, layout: str, panel_count: int) -> Unsupported | None:
        capacity = _LAYOUT_CAPACITY.get(layout)
        if capacity is None or panel_count < 2 or panel_count > capacity:
            return Unsupported(
                target_alias="active_target",
                category="v1_scope",
                explanation="Use one of the fixed v1 layouts with two to six panels.",
            )
        return None

    def _validate_sources(
        self, snapshots: tuple[FigureSourceSnapshot, ...], axis_policy: str
    ) -> Unsupported | None:
        if any(not snapshot.numeric_only for snapshot in snapshots):
            return Unsupported(
                target_alias="active_target",
                category="v1_scope",
                explanation="v1 Figures can contain only numeric chart versions.",
            )
        if axis_policy in {"shared_x", "shared_both"} and len(
            {snapshot.x_axis for snapshot in snapshots}
        ) != 1:
            return Unsupported(
                target_alias="active_target",
                category="chart_capability",
                explanation="The selected plots do not have compatible X axes for sharing.",
            )
        if axis_policy in {"shared_y", "shared_both"} and len(
            {snapshot.y_axis for snapshot in snapshots}
        ) != 1:
            return Unsupported(
                target_alias="active_target",
                category="chart_capability",
                explanation="The selected plots do not have compatible Y axes for sharing.",
            )
        return None

    def _create_hash(self, request: FigureCreateRequest) -> str:
        return canonical_hash(
            {
                "project_id": request.project_id,
                "figure_id": request.figure_id,
                "layout": request.layout,
                "plot_refs": [ref.model_dump(mode="json") for ref in request.plot_refs],
                "physical_size": request.physical_size.model_dump(mode="json"),
                "publication_profile": request.publication_profile.model_dump(mode="json"),
                "alignment": request.alignment,
                "axis_policy": request.axis_policy,
                "common_legend": request.common_legend,
                "panel_labels": [label.model_dump(mode="json") for label in request.panel_labels],
            }
        )

    def _label(self, index: int) -> SafeRichText:
        return SafeRichText(nodes=(SafeTextNode(kind="plain", text=chr(ord("A") + index)),))
