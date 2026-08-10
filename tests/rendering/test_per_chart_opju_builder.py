from __future__ import annotations

from collections import Counter

import pandas as pd

from plotagent.origin import build_origin_export_spec, compile_origin_plan
from scripts import build_per_chart_opju as builder


def test_per_chart_inventory_contains_only_qualified_charts() -> None:
    items = builder._items({"seq20", "fixed", "matrix", "structural"})

    assert len(items) == 38
    assert Counter(lane for lane, _case, _data, _target in items) == {
        "seq20": 12,
        "fixed": 10,
        "matrix": 7,
        "structural": 9,
    }
    chart_ids = [case.chart_id for _lane, case, _data, _target in items]
    assert len(chart_ids) == len(set(chart_ids))
    assert {"K24", "K25", "S01", "K21", "S21", "S34"} <= set(chart_ids)
    assert {"K05", "K17", "S05", "S07", "S25", "S31", "X01"}.isdisjoint(chart_ids)
    assert all(target.name == f"{case.chart_id}.opju" for _lane, case, _data, target in items)


def test_each_chart_compiles_default_and_edited_into_one_project() -> None:
    for lane, case, data_path, _target in builder._items(
        {"seq20", "fixed", "matrix", "structural"}
    ):
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


def test_former_evidence_gaps_compile_default_and_edited_into_one_project() -> None:
    former_gaps = {"K24", "K25", "S01", "K21", "S21", "S34"}
    items = {
        case.chart_id: (lane, case, data_path)
        for lane, case, data_path, _target in builder._items(
            {"seq20", "fixed", "matrix", "structural"}
        )
    }

    assert former_gaps <= items.keys()
    for chart_id in sorted(former_gaps):
        lane, case, data_path = items[chart_id]
        pair = builder._resolved_pair(lane, case, pd.read_csv(data_path))
        plan = compile_origin_plan(
            pair,
            build_origin_export_spec(
                pair,
                export_id=f"export:test.former-gap.{chart_id.lower()}",
                target_scope="selected_plots",
            ),
        )

        assert len(pair) == 2
        assert pair[0].plan.chart_type_id == pair[1].plan.chart_type_id == chart_id
        assert len(plan.graph_objects) == 2
