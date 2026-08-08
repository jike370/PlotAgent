from __future__ import annotations

import os
from pathlib import Path

import pytest

from plotagent.contracts.base import ColorValue, PhysicalLength
from plotagent.contracts.plots import (
    BarAreaEditSpec,
    ChartParameterEditSpec,
    ColorbarEditSpec,
    DualYAxisEditSpec,
    FacetEditSpec,
    FacetLabelEdit,
    SpecialistEditSpec,
    UncertaintyEditSpec,
    YOffsetEditSpec,
)
from plotagent.origin import export_origin
from plotagent.origin.models import OriginExportSuccess
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.rendering import PlotResolver
from tests.contracts.helpers import rich_text
from tests.rendering.fixture_factory import build_plot_and_store

RUN_LIVE = os.environ.get("PLOTAGENT_RUN_ORIGIN_LIVE_SPECIALIST") == "1"


def _resolved(chart_id: str, specialist: SpecialistEditSpec):
    plot, store = build_plot_and_store(chart_id)
    edited = plot.model_copy(update={"specialist": specialist})
    return PlotResolver().resolve(edited, store)


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="set PLOTAGENT_RUN_ORIGIN_LIVE_SPECIALIST=1 for specialist Origin readback",
)
def test_specialist_edits_survive_one_fresh_origin_reopen(tmp_path: Path) -> None:
    cases = (
        _resolved(
            "K09",
            SpecialistEditSpec(
                bar_area=BarAreaEditSpec(
                    fill_color=ColorValue(value="#3B82F6"),
                    edge_color=ColorValue(value="#1E3A8A"),
                    edge_width=PhysicalLength(value=1.1, unit="pt"),
                    width_ratio=0.65,
                    alpha=0.8,
                )
            ),
        ),
        _resolved(
            "K07",
            SpecialistEditSpec(
                uncertainty=UncertaintyEditSpec(
                    color=ColorValue(value="#7C3AED"),
                    line_width=PhysicalLength(value=1.3, unit="pt"),
                    cap_size=PhysicalLength(value=6, unit="pt"),
                    band_alpha=0.4,
                )
            ),
        ),
        _resolved(
            "K22",
            SpecialistEditSpec(
                colorbar=ColorbarEditSpec(
                    title=rich_text("Intensity"),
                    minimum=-3,
                    maximum=3,
                    levels=9,
                )
            ),
        ),
        _resolved(
            "X23",
            SpecialistEditSpec(
                dual_y=DualYAxisEditSpec(
                    left_color=ColorValue(value="#0F766E"),
                    right_color=ColorValue(value="#BE123C"),
                    axis_width=PhysicalLength(value=1.1, unit="pt"),
                )
            ),
        ),
        _resolved(
            "K24",
            SpecialistEditSpec(
                facet=FacetEditSpec(
                    order=("B", "A"),
                    labels=(FacetLabelEdit(value="B", label="Treatment"),),
                    gap=PhysicalLength(value=6, unit="mm"),
                    shared_x=False,
                    shared_y=False,
                    common_legend=False,
                )
            ),
        ),
        _resolved(
            "X38",
            SpecialistEditSpec(y_offset=YOffsetEditSpec(distance=10, order=("B", "A"))),
        ),
        _resolved(
            "X01",
            SpecialistEditSpec(chart_parameters=ChartParameterEditSpec(step_where="mid")),
        ),
        _resolved(
            "X24",
            SpecialistEditSpec(
                chart_parameters=ChartParameterEditSpec(pareto_reference_percent=75)
            ),
        ),
        _resolved(
            "S07",
            SpecialistEditSpec(
                chart_parameters=ChartParameterEditSpec(
                    volcano_absolute_log2_fold_change=2,
                    volcano_pvalue=0.01,
                )
            ),
        ),
    )
    plan = compile_origin_plan(
        cases,
        build_origin_export_spec(
            cases,
            export_id="export:live.specialist-edits",
            target_scope="selected_plots",
        ),
    )
    target = tmp_path / "specialist-edits.opju"

    result = export_origin(plan, target, timeout_seconds=360.0)

    assert isinstance(result, OriginExportSuccess), result.to_dict()
    assert result.build_validation == result.reopen_validation
    assert target.is_file() and target.stat().st_size > 0
