from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from plotagent.charts.registry import get_chart, patch_operations_for_chart
from plotagent.contracts.registry import PRODUCT_CHART_IDS
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from tests.rendering.fixture_factory import resolve_chart


def test_first_release_qualification_surface_is_exactly_43_product_charts() -> None:
    assert len(PRODUCT_CHART_IDS) == 43
    assert len(set(PRODUCT_CHART_IDS)) == 43
    assert all(get_chart(chart_id).admission == "product" for chart_id in PRODUCT_CHART_IDS)
    assert all(
        "set_plot_title" in patch_operations_for_chart(chart_id) for chart_id in PRODUCT_CHART_IDS
    )


@pytest.mark.parametrize("chart_id", PRODUCT_CHART_IDS)
def test_product_chart_passes_formal_matplotlib_and_origin_plan_qualification(
    chart_id: str,
) -> None:
    resolved = resolve_chart(chart_id)
    figure = MatplotlibRenderer().build_figure(resolved)
    assert figure.axes
    assert all(
        0 <= value <= 1
        for axis in figure.axes
        for value in (
            axis.get_position().x0,
            axis.get_position().y0,
            axis.get_position().x1,
            axis.get_position().y1,
        )
    )
    plt.close(figure)

    plan = compile_origin_plan(
        (resolved,),
        build_origin_export_spec(
            (resolved,),
            export_id=f"export:qualification.{chart_id.lower()}",
        ),
    )
    assert plan.manifest.chart_type_ids == (chart_id,)
    assert plan.capability == "O1"
    assert not plan.manifest.known_differences
