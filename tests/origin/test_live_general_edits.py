from __future__ import annotations

import os
from pathlib import Path

import pytest

from plotagent.contracts.base import PhysicalLength
from plotagent.contracts.plots import AnnotationSpec, AxisRange, AxisTickSpec
from plotagent.origin import export_origin
from plotagent.origin.models import OriginExportSuccess
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.rendering import PlotResolver
from tests.contracts.helpers import rich_text
from tests.rendering.fixture_factory import build_plot_and_store

RUN_LIVE = os.environ.get("PLOTAGENT_RUN_ORIGIN_LIVE_GENERAL") == "1"


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="set PLOTAGENT_RUN_ORIGIN_LIVE_GENERAL=1 to run native general-edit readback",
)
def test_general_edits_survive_fresh_origin_reopen(tmp_path: Path) -> None:
    plot, store = build_plot_and_store("K01")
    scales = tuple(
        scale.model_copy(
            update={
                "axis_range": AxisRange(minimum=0, maximum=20, reverse=True),
                "ticks": AxisTickSpec(
                    major_interval=5,
                    number_format="fixed",
                    decimal_places=1,
                ),
            }
        )
        if scale.scale_id == "scale:y"
        else scale
        for scale in plot.scales
    )
    edited = plot.model_copy(
        update={
            "plot_id": "plot:live.general-edits",
            "title": rich_text("Qualified Origin title"),
            "scales": scales,
            "resolved_style": plot.resolved_style.model_copy(
                update={"font_size": PhysicalLength(value=11, unit="pt")}
            ),
            "annotations": (
                AnnotationSpec(
                    annotation_id="annotation:live.text",
                    kind="text",
                    text=rich_text("Peak"),
                    x=1,
                    y=10,
                ),
                AnnotationSpec(
                    annotation_id="annotation:live.line",
                    kind="reference_line",
                    y=8,
                ),
                AnnotationSpec(
                    annotation_id="annotation:live.band",
                    kind="reference_band",
                    y=12,
                    y2=16,
                ),
            ),
        }
    )
    resolved = PlotResolver().resolve(edited, store)
    plan = compile_origin_plan(
        (resolved,),
        build_origin_export_spec((resolved,), export_id="export:live.general-edits"),
    )
    target = tmp_path / "general-edits.opju"

    result = export_origin(plan, target, timeout_seconds=180.0)

    assert isinstance(result, OriginExportSuccess), result.to_dict()
    assert result.build_validation == result.reopen_validation
    assert target.is_file() and target.stat().st_size > 0
