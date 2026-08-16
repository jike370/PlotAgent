from __future__ import annotations

from pathlib import Path

import pytest

from plotagent.engine import (
    BindFields,
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
    PlotEngineAction,
    SetLegend,
    SetSeriesStyle,
)
from plotagent.engine.backends.matplotlib import K03ScatterRenderer, MatplotlibBackend
from plotagent.engine.profile_data import k03_scatter

HASH = "6" * 64


def _case(
    group_values: tuple[str, ...],
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id="dataset.scatter",
        version=1,
        content_hash=HASH,
    )
    bindings = (
        FieldBinding(role="x", field_id="field:x"),
        FieldBinding(role="y", field_id="field:y"),
        FieldBinding(role="group", field_id="field:group"),
    )
    create = CreatePlot(
        action_id="action:create-scatter",
        plot_id="plot:k03-dynamic",
        profile_id="K03",
        data=data,
        bindings=bindings,
    )
    style = SetSeriesStyle(
        action_id="action:style-second",
        target="series:k03-dynamic.group_2",
        expected_plot_version=1,
        line_stroke_color="#AA3300",
        marker_shape="diamond",
        marker_size_pt=8,
    )
    legend = SetLegend(
        action_id="action:legend",
        target="legend:k03-dynamic.main",
        expected_plot_version=2,
        visible=True,
    )
    actions: tuple[PlotEngineAction, ...] = (create, style, legend)
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=3,
        parent_version=2,
        profile_id="K03",
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    count = len(group_values)
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{index}" for index in range(count)),
        columns=(
            EngineColumn(
                field=EngineField(field_id="field:x", name="Dose", logical_type="numeric"),
                values=tuple(float(index) for index in range(count)),
            ),
            EngineColumn(
                field=EngineField(field_id="field:y", name="Response", logical_type="numeric"),
                values=tuple(float(index * 2) for index in range(count)),
            ),
            EngineColumn(
                field=EngineField(
                    field_id="field:group", name="Cohort", logical_type="categorical"
                ),
                values=group_values,
            ),
        ),
    )
    return document, actions, view


def test_k03_group_order_and_semantic_series_are_data_driven(tmp_path: Path) -> None:
    document, actions, view = _case(("B", "A", "B", "C", "A"))
    scatter = k03_scatter(document, view)
    assert tuple(group.label for group in scatter.groups) == ("B", "A", "C")

    backend = MatplotlibBackend(tmp_path / "artifacts", (K03ScatterRenderer(),))
    change = backend.stage(document, actions, EngineRenderSource(data=view))
    change.publish()
    readback = backend.readback(document)

    assert {
        item.semantic_id for item in readback.objects if item.object_kind == "scatter_series"
    } == {
        "series:k03-dynamic.group_1",
        "series:k03-dynamic.group_2",
        "series:k03-dynamic.group_3",
    }
    assert (tmp_path / "artifacts" / "k03-dynamic" / "v3" / "preview.png").stat().st_size > 0
    assert (tmp_path / "artifacts" / "k03-dynamic" / "v3" / "preview.svg").stat().st_size > 0


@pytest.mark.parametrize("group_count", (1, 2, 5))
def test_k03_materializes_one_series_per_group(group_count: int) -> None:
    groups = tuple(f"G{index}" for index in range(1, group_count + 1))
    document, _, view = _case(groups)
    assert len(k03_scatter(document, view).groups) == group_count


def test_k03_rejects_series_ordinals_outside_materialized_data(tmp_path: Path) -> None:
    document, actions, view = _case(("A", "A"))
    backend = MatplotlibBackend(tmp_path / "artifacts", (K03ScatterRenderer(),))

    with pytest.raises(ValueError, match="outside the materialized series"):
        backend.stage(document, actions, EngineRenderSource(data=view))


def test_k03_rebinding_resets_obsolete_data_derived_series_styles(tmp_path: Path) -> None:
    document, actions, view = _case(("A", "A"))
    rebound = BindFields(
        action_id="action:rebind",
        target=document.plot_id,
        expected_plot_version=2,
        data=document.data,
        bindings=document.bindings,
    )
    rebound_actions: tuple[PlotEngineAction, ...] = (*actions[:2], rebound, actions[2])
    rebound_document = document.model_copy(
        update={
            "plot_version": 4,
            "parent_version": 3,
            "applied_action_ids": tuple(action.action_id for action in rebound_actions),
        }
    )
    backend = MatplotlibBackend(tmp_path / "artifacts", (K03ScatterRenderer(),))

    change = backend.stage(rebound_document, rebound_actions, EngineRenderSource(data=view))
    change.publish()

    assert backend.readback(rebound_document).document.plot_version == 4
