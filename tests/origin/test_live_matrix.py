from __future__ import annotations

import os
from pathlib import Path

import pytest

from plotagent.charts.registry import CHARTS
from plotagent.origin import export_origin
from plotagent.origin.models import OriginExportSuccess
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from tests.rendering.fixture_factory import resolve_chart

RUN_LIVE = os.environ.get("PLOTAGENT_RUN_ORIGIN_LIVE_MATRIX") == "1"
SELECTED = {
    item.strip().upper()
    for item in os.environ.get("PLOTAGENT_ORIGIN_LIVE_CHARTS", "").split(",")
    if item.strip()
}


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="set PLOTAGENT_RUN_ORIGIN_LIVE_MATRIX=1 to run the 31-chart Origin matrix",
)
@pytest.mark.parametrize("chart_id", [entry.chart_type_id for entry in CHARTS])
def test_representative_chart_is_native_after_fresh_origin_reopen(
    chart_id: str, tmp_path: Path
) -> None:
    if SELECTED and chart_id not in SELECTED:
        pytest.skip("chart omitted by PLOTAGENT_ORIGIN_LIVE_CHARTS")
    resolved = resolve_chart(chart_id)
    plan = compile_origin_plan(
        (resolved,),
        build_origin_export_spec(
            (resolved,), export_id=f"export:live.{chart_id.lower()}"
        ),
    )
    target = tmp_path / f"{chart_id}.opju"

    result = export_origin(plan, target, timeout_seconds=120.0)

    assert isinstance(result, OriginExportSuccess), result.to_dict()
    assert result.build_validation == result.reopen_validation
    assert target.is_file() and target.stat().st_size > 0
