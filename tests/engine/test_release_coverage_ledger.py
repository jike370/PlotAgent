from __future__ import annotations

import json

from plotagent.engine.profiles import ENGINE_PROFILES
from scripts.build_release_coverage_ledger import (
    CHART_ASSIGNMENT_KEYS,
    DOMAIN_IDS,
    JSON_OUTPUT,
    MARKDOWN_OUTPUT,
    build_ledger,
    render_outputs,
)


def test_release_coverage_ledger_assigns_every_public_chart() -> None:
    ledger = build_ledger()
    profile_ids = [str(profile.profile_id) for profile in ENGINE_PROFILES]
    charts = ledger["charts"]

    assert ledger["chart_count"] == 34
    assert [chart["profile_id"] for chart in charts] == profile_ids
    assert all(tuple(chart["assignments"]) == CHART_ASSIGNMENT_KEYS for chart in charts)
    assert all(
        len(chart["assignments"]["offline_matrix"]["matrix_keys"]) == 9
        for chart in charts
    )
    assert len(
        {
            chart["assignments"]["windows_ui"]["case_id"]
            for chart in charts
        }
    ) == 34


def test_release_coverage_ledger_assigns_all_cross_cutting_domains() -> None:
    ledger = build_ledger()
    domains = ledger["domains"]

    assert ledger["domain_count"] == len(DOMAIN_IDS)
    assert tuple(domain["domain_id"] for domain in domains) == DOMAIN_IDS
    assert all(domain["requirements"] for domain in domains)
    assert all(domain["case_ids"] for domain in domains)
    assert all(domain["candidate_evidence_status"] == "UNVERIFIED" for domain in domains)


def test_checked_in_release_coverage_ledger_is_generated_and_current() -> None:
    json_text, markdown_text = render_outputs()

    assert JSON_OUTPUT.read_text(encoding="utf-8") == json_text
    assert MARKDOWN_OUTPUT.read_text(encoding="utf-8") == markdown_text
    parsed = json.loads(json_text)
    assert parsed["schema_version"] == "plotagent.release-coverage-ledger.v1"
