from __future__ import annotations

from collections import Counter

import pandas as pd

from plotagent.origin import build_origin_export_spec, compile_origin_plan
from scripts import build_per_chart_opju as builder


def test_per_chart_inventory_contains_only_qualified_charts() -> None:
    items = builder._items({"seq20", "fixed", "matrix", "structural"})

    assert len(items) == 37
    assert Counter(lane for lane, _case, _data, _target in items) == {
        "seq20": 16,
        "fixed": 11,
        "matrix": 4,
        "structural": 6,
    }
    chart_ids = [case.chart_id for _lane, case, _data, _target in items]
    assert len(chart_ids) == len(set(chart_ids))
    assert not {"S07", "K24", "K25", "S01", "K21", "S21", "S31", "S34"} & set(
        chart_ids
    )
    assert all(target.name == f"{case.chart_id}.opju" for _lane, case, _data, target in items)


def test_each_lane_compiles_default_and_edited_into_one_project() -> None:
    for lane in ("seq20", "fixed", "matrix", "structural"):
        selected = builder._items({lane})
        _lane, case, data_path, _target = selected[0]
        pair = builder._resolved_pair(lane, case, pd.read_csv(data_path))
        plan = compile_origin_plan(
            pair,
            build_origin_export_spec(
                pair,
                export_id=f"export:test.{case.chart_id.lower()}",
                target_scope="selected_plots",
            ),
        )

        assert len(pair) == 2
        assert pair[0].plan.chart_type_id == pair[1].plan.chart_type_id == case.chart_id
        assert len(plan.graph_objects) == 2
