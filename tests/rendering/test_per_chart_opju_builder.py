from __future__ import annotations

import json
from collections import Counter

import pandas as pd

from plotagent.origin import build_origin_export_spec, compile_origin_plan
from scripts import build_per_chart_opju as builder


def test_per_chart_inventory_contains_only_qualified_charts() -> None:
    items = builder._items({"seq20", "fixed", "matrix", "structural"})

    assert len(items) == 45
    assert Counter(lane for lane, _case, _data, _target in items) == {
        "seq20": 16,
        "fixed": 12,
        "matrix": 8,
        "structural": 9,
    }
    chart_ids = [case.chart_id for _lane, case, _data, _target in items]
    assert len(chart_ids) == len(set(chart_ids))
    assert {"S07", "K24", "K25", "S01", "K21", "S21", "S31", "S34"} <= set(
        chart_ids
    )
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
    former_gaps = {"S07", "K24", "K25", "S01", "K21", "S21", "S31", "S34"}
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


def test_built_manifest_has_45_fresh_projects_at_the_current_source() -> None:
    manifest = json.loads(builder.MANIFEST_PATH.read_text(encoding="utf-8"))
    items = builder._items({"seq20", "fixed", "matrix", "structural"})
    expected = {
        case.chart_id: (lane, case.case_id, data_path, target)
        for lane, case, data_path, target in items
    }
    current_source = builder.source_build_identity(
        builder.REPOSITORY,
        builder.seq20.SOURCE_SCOPE,
        scope_version="per-chart-opju-rendering-v1",
    )

    assert manifest["source_build_identity"]["source_sha256"] == current_source["source_sha256"]
    assert manifest["graph_order"] == ["default", "representative_edited"]
    assert set(manifest["charts"]) == set(expected)
    assert len(manifest["charts"]) == 45

    for chart_id, (lane, case_id, data_path, target) in expected.items():
        entry = manifest["charts"][chart_id]
        assert entry["lane"] == lane
        assert entry["case_id"] == case_id
        assert entry["path"] == str(target)
        assert entry["data_sha256"] == builder._sha256(data_path)
        assert entry["source_sha256"] == current_source["source_sha256"]
        assert entry["opju_sha256"] == builder._sha256(target)
        assert entry["opju_size"] == target.stat().st_size > 0
        assert len(entry["origin_plan_sha256"]) == 64
        assert len(entry["validation_report_sha256"]) == 64
        assert entry["fresh_reopen_identical"] is True
        assert entry["graph_order"] == ["default", "representative_edited"]
