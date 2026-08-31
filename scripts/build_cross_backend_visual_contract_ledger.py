"""Build the 34-profile visual-contract audit ledger from authoritative inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
CATALOG = REPOSITORY / "schemas" / "engine-profile-catalog.json"
DECISIONS = REPOSITORY / "docs" / "visual-contracts" / "decisions.json"
LEDGER = REPOSITORY / "docs" / "visual-contracts" / "audit-ledger.json"
SUMMARY = REPOSITORY / "docs" / "CROSS-BACKEND-VISUAL-CONTRACT-AUDIT.md"

PARAMETER_STATUSES = {
    "passed",
    "failed",
    "allowed_difference",
    "not_applicable",
    "blocked",
}
DEFAULT_STATUSES = {"pending", "passed", "failed", "allowed_difference", "blocked"}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _catalog_sha256() -> str:
    return hashlib.sha256(CATALOG.read_bytes()).hexdigest().upper()


def _parameter_keys(profile: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        f"{capability['operation']}.{parameter}"
        for capability in profile["capabilities"]
        for parameter in capability["parameters"]
    )


def _validate_decision(profile: dict[str, Any], decision: dict[str, Any]) -> None:
    profile_id = profile["profile_id"]
    known_parameters = set(_parameter_keys(profile))
    parameter_results = decision.get("parameter_results", {})
    unknown = set(parameter_results) - known_parameters
    if unknown:
        raise RuntimeError(f"{profile_id} decisions contain unknown parameters: {sorted(unknown)}")
    for key, result in parameter_results.items():
        if result.get("status") not in PARAMETER_STATUSES:
            raise RuntimeError(f"{profile_id} {key} has invalid status")
        if not result.get("summary") or not result.get("evidence"):
            raise RuntimeError(f"{profile_id} {key} needs summary and evidence")
    zero_edit = decision.get("zero_edit_default", {"status": "pending"})
    if zero_edit.get("status") not in DEFAULT_STATUSES:
        raise RuntimeError(f"{profile_id} has invalid zero-edit status")
    if zero_edit.get("status") != "pending" and (
        not zero_edit.get("summary") or not zero_edit.get("evidence")
    ):
        raise RuntimeError(f"{profile_id} completed zero-edit decision needs summary and evidence")
    for requirement in decision.get("paper_requirements", []):
        required = {
            "case_id",
            "paper",
            "requirement",
            "data_status",
            "classification",
            "decision",
            "matplotlib_acceptance",
            "origin_acceptance",
            "evidence",
        }
        missing = required - set(requirement)
        if missing:
            raise RuntimeError(f"{profile_id} paper requirement misses: {sorted(missing)}")


def _build() -> tuple[dict[str, Any], str]:
    catalog = _load(CATALOG)
    decisions_document = _load(DECISIONS)
    profiles = catalog.get("profiles", [])
    decisions = decisions_document.get("profiles", {})
    if catalog.get("profile_count") != 34 or len(profiles) != 34:
        raise RuntimeError("visual-contract audit requires exactly 34 Catalog profiles")
    profile_ids = [profile["profile_id"] for profile in profiles]
    unknown_decisions = set(decisions) - set(profile_ids)
    if unknown_decisions:
        raise RuntimeError(f"decisions contain unknown profiles: {sorted(unknown_decisions)}")

    rows: list[dict[str, Any]] = []
    markdown_rows: list[str] = []
    for profile in profiles:
        profile_id = profile["profile_id"]
        decision = decisions.get(profile_id, {})
        _validate_decision(profile, decision)
        parameter_keys = _parameter_keys(profile)
        parameter_results = decision.get("parameter_results", {})
        zero_edit = decision.get("zero_edit_default", {"status": "pending"})
        audited_count = len(parameter_results)
        if audited_count == len(parameter_keys) and zero_edit["status"] in {
            "passed",
            "allowed_difference",
        }:
            overall_status = "complete"
        elif audited_count or zero_edit["status"] != "pending":
            overall_status = "partial"
        else:
            overall_status = "not_started"
        row = {
            "profile_id": profile_id,
            "display_name": profile["display_name"],
            "catalog_contract": {
                "required_roles": profile["required_roles"],
                "optional_roles": profile["optional_roles"],
                "repeatable_role_prefixes": profile["repeatable_role_prefixes"],
                "capabilities": profile["capabilities"],
                "declared_parameter_count": len(parameter_keys),
            },
            "parameter_results": parameter_results,
            "declared_parameters_audited": audited_count,
            "declared_parameters_remaining": len(parameter_keys) - audited_count,
            "zero_edit_default": zero_edit,
            "default_findings": decision.get("default_findings", []),
            "paper_requirements": decision.get("paper_requirements", []),
            "boundaries": decision.get("boundaries", []),
            "overall_status": overall_status,
        }
        rows.append(row)
        markdown_rows.append(
            f"| {profile_id} | {profile['display_name']} | {len(parameter_keys)} | "
            f"{audited_count} | {zero_edit['status']} | {overall_status} |"
        )

    ledger = {
        "schema_version": "cross-backend-visual-contract-audit.v1",
        "catalog_source": "schemas/engine-profile-catalog.json",
        "catalog_sha256": _catalog_sha256(),
        "profile_count": len(rows),
        "completion_rule": (
            "complete requires an explicit result for every Catalog-declared parameter and "
            "an adjudicated zero-edit cross-backend default; paper-only requirements remain "
            "separate capability candidates"
        ),
        "profiles": rows,
    }
    summary = (
        """# 34 模板跨后端视觉契约审计

本账本不是既有视觉冒烟页的改名。旧审计只能证明代表性产物曾经生成，
不能证明 Catalog 中每个公开参数都在 Matplotlib、Origin、保存和 fresh-reopen 后表达一致。

审计范围只来自三类权威输入：

1. `schemas/engine-profile-catalog.json` 中该模板已经公开的参数；
2. 同一份零编辑数据在 Matplotlib 与 Origin 中实际生成的默认外观；
3. 真实论文复刻明确要求、但 Catalog 尚未声明的参数。

`complete` 仅表示该模板的每个 Catalog 参数都有显式裁决，零编辑默认外观也已经裁决。
`partial`、`not_started` 不能用于宣称跨后端视觉一致。详细参数、证据、真实论文要求和边界见
[`visual-contracts/audit-ledger.json`](./visual-contracts/audit-ledger.json)。

| 模板 | Catalog 名称 | 已声明参数 | 已审参数 | 零编辑默认 | 总状态 |
|---|---|---:|---:|---|---|
"""
        + "\n".join(markdown_rows)
        + "\n"
    )
    return ledger, summary


def _serialized_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    ledger, summary = _build()
    expected = ((LEDGER, _serialized_json(ledger)), (SUMMARY, summary))
    if args.check:
        stale = [
            str(path.relative_to(REPOSITORY))
            for path, value in expected
            if not path.is_file() or path.read_text(encoding="utf-8") != value
        ]
        if stale:
            raise SystemExit("stale visual-contract audit outputs: " + ", ".join(stale))
        print("visual-contract audit outputs are current")
        return
    for path, value in expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        print(path.relative_to(REPOSITORY))


if __name__ == "__main__":
    main()
