from __future__ import annotations

import os
from pathlib import Path

import pytest

from plotagent.contracts.registry import PRODUCT_CHART_IDS
from plotagent.origin import export_origin
from plotagent.origin.models import OriginExportSuccess
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from tests.rendering.fixture_factory import resolve_chart

RUN_LIVE = os.environ.get("PLOTAGENT_RUN_ORIGIN_LIVE_PRODUCT") == "1"


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="set PLOTAGENT_RUN_ORIGIN_LIVE_PRODUCT=1 for the 38-chart native gate",
)
def test_all_38_product_charts_survive_one_fresh_origin_reopen(tmp_path: Path) -> None:
    resolved = tuple(resolve_chart(chart_id) for chart_id in PRODUCT_CHART_IDS)
    plan = compile_origin_plan(
        resolved,
        build_origin_export_spec(
            resolved,
            export_id="export:live.product-38",
            target_scope="selected_plots",
        ),
    )
    target = tmp_path / "product-38.opju"

    result = export_origin(plan, target, timeout_seconds=900.0)

    assert isinstance(result, OriginExportSuccess), result.to_dict()
    assert result.build_validation == result.reopen_validation
    assert target.is_file() and target.stat().st_size > 0
