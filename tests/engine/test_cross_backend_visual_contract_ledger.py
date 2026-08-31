from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_targeted_renderer_visual_review import _cases

REPOSITORY = Path(__file__).resolve().parents[2]


def test_visual_contract_ledger_covers_the_live_catalog_and_is_current() -> None:
    subprocess.run(
        [sys.executable, "scripts/build_cross_backend_visual_contract_ledger.py", "--check"],
        cwd=REPOSITORY,
        check=True,
    )
    catalog = json.loads(
        (REPOSITORY / "schemas" / "engine-profile-catalog.json").read_text(encoding="utf-8")
    )
    ledger = json.loads(
        (REPOSITORY / "docs" / "visual-contracts" / "audit-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger["profile_count"] == catalog["profile_count"] == 34
    assert [item["profile_id"] for item in ledger["profiles"]] == [
        item["profile_id"] for item in catalog["profiles"]
    ]
    for profile in ledger["profiles"]:
        assert profile["declared_parameters_remaining"] >= 0
        if profile["overall_status"] == "complete":
            assert profile["declared_parameters_remaining"] == 0
            assert profile["zero_edit_default"]["status"] in {
                "passed",
                "allowed_difference",
            }


def test_targeted_visual_audit_fixtures_use_live_catalog_role_contracts() -> None:
    catalog = json.loads(
        (REPOSITORY / "schemas" / "engine-profile-catalog.json").read_text(encoding="utf-8")
    )
    profiles = {item["profile_id"]: item for item in catalog["profiles"]}
    cases = {item.profile_id: item for item in _cases()}
    for profile_id in ("K06", "K07", "K14", "K22", "X09", "X23", "X35", "X36"):
        fixture_roles = [binding.role for binding in cases[profile_id].document.bindings]
        required_roles = profiles[profile_id]["required_roles"]
        allowed_roles = set(required_roles) | set(profiles[profile_id]["optional_roles"])
        assert set(required_roles) <= set(fixture_roles)
        assert len(fixture_roles) == len(set(fixture_roles))
        assert set(fixture_roles) <= allowed_roles
