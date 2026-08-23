"""Build the frozen, machine-checkable PlotAgent release coverage ledger.

The ledger assigns every public chart and every cross-cutting product domain to
an executable test surface.  It is deliberately a coverage *contract*, not a
test result: candidate-specific PASS/FAIL evidence is produced later by the
assigned runners and must carry the same Git HEAD.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine.backends.origin.recipe import (  # noqa: E402
    ORIGIN_RENDERABLE_RECIPES,
)
from plotagent.engine.profiles import ENGINE_PROFILES  # noqa: E402
from scripts.release_matrix_cases import RELEASE_CASES  # noqa: E402
from scripts.run_release_data_stress_matrix import STRESS_CASE_IDS  # noqa: E402
from scripts.run_release_fault_matrix import FAULT_CASES  # noqa: E402
from scripts.run_release_operational_matrix import BATCH_NODEIDS  # noqa: E402

JSON_OUTPUT = REPOSITORY / "docs" / "PLOTAGENT-RELEASE-COVERAGE-LEDGER.json"
MARKDOWN_OUTPUT = REPOSITORY / "docs" / "PLOTAGENT-RELEASE-COVERAGE-LEDGER.md"

CHART_ASSIGNMENT_KEYS = (
    "data_contract",
    "offline_matrix",
    "origin_fresh_reopen",
    "public_edits",
    "history_recovery",
    "exports",
    "windows_ui",
)

DOMAIN_IDS = (
    "TASK-STATE",
    "DATA-INPUT",
    "MULTI-SOURCE",
    "UI",
    "FAULT-RECOVERY",
    "EXPORT",
    "PERFORMANCE",
    "PACKAGING",
    "BLACKBOX",
    "SEQ70",
)


def _capabilities(profile: Any) -> dict[str, list[str]]:
    return {
        str(capability.operation): [str(parameter) for parameter in capability.parameters]
        for capability in profile.capabilities
    }


def _chart_entry(profile: Any) -> dict[str, Any]:
    profile_id = str(profile.profile_id)
    recipe = ORIGIN_RENDERABLE_RECIPES[profile.profile_id]
    variants = ("minimal", "representative", "edge_error")
    formats = ("png", "svg", "opju")
    matrix_keys = [
        f"{profile_id}:{variant}:{format_name}"
        for variant in variants
        for format_name in formats
    ]
    return {
        "profile_id": profile_id,
        "chinese_name": recipe.chinese_name,
        "engine_display_name": profile.display_name,
        "role_contract": {
            "required": list(profile.required_roles),
            "optional": list(profile.optional_roles),
            "repeatable_prefixes": list(profile.repeatable_role_prefixes),
            "accepted_logical_types": {
                str(role): list(logical_types)
                for role, logical_types in profile.role_field_types.items()
            },
        },
        "public_capabilities": _capabilities(profile),
        "assignments": {
            "data_contract": {
                "case_ids": [f"DATA-{profile_id}-{variant.upper()}" for variant in variants],
                "source": "scripts/release_matrix_cases.py::RELEASE_CASES",
                "deterministic_test": (
                    "tests/engine/test_release_matrix.py::"
                    "test_release_cases_freeze_all_public_profiles_and_three_variants"
                ),
            },
            "offline_matrix": {
                "runner": "scripts/run_release_matrix.py",
                "matrix_keys": matrix_keys,
                "required_artifacts": [
                    "matrix-results.json",
                    "matrix-results.csv",
                    "run-metadata.json",
                    "REPORT.md",
                ],
            },
            "origin_fresh_reopen": {
                "runner": "scripts/run_release_origin_matrix.py",
                "case_id": f"ORIGIN-{profile_id}-REPRESENTATIVE-FRESH",
                "matrix_key": f"{profile_id}:representative:opju",
                "required_artifacts": [
                    f"{profile_id}/default/plot.opju",
                    f"{profile_id}/default/readback.json",
                    f"{profile_id}/representative/plot.opju",
                    f"{profile_id}/representative/fresh-readback.json",
                    f"{profile_id}/representative/fresh.png",
                ],
            },
            "public_edits": {
                "runner": "scripts/run_release_edit_matrix.py",
                "case_id_prefix": f"EDIT-{profile_id}-",
                "deterministic_tests": [
                    (
                        "tests/engine/test_release_matrix.py::"
                        "test_all_34_profiles_enumerate_every_public_edit_parameter_in_isolation"
                    ),
                    (
                        "tests/engine/test_release_matrix.py::"
                        "test_every_profile_parameter_pair_has_an_isolated_matplotlib_execution"
                    ),
                ],
                "required_artifacts": [
                    "isolated-edit-contracts.json",
                    "edit-results.json",
                    "edit-results.csv",
                    f"{profile_id}/origin/*/fresh-readback.json",
                ],
            },
            "history_recovery": {
                "case_id": f"RECOVERY-{profile_id}-UNDO-REDO-RESTART",
                "deterministic_test": (
                    "tests/engine/test_release_matrix.py::"
                    "test_all_formal_profile_documents_and_latest_versions_survive_project_reopen"
                ),
                "windows_ui_case": f"BB-RECOVERY-{profile_id}",
                "required_assertions": [
                    "linear action history",
                    "undo creates an inverse version",
                    "redo creates a forward version",
                    "restart restores the same plot id and latest version",
                    "no successful action is executed twice",
                ],
            },
            "exports": {
                "case_id": f"EXPORT-{profile_id}-PNG-SVG-OPJU",
                "matrix_keys": [
                    f"{profile_id}:representative:png",
                    f"{profile_id}:representative:svg",
                    f"{profile_id}:representative:opju",
                ],
                "edit_runner": "scripts/run_release_edit_matrix.py",
                "windows_ui_case": f"BB-EXPORT-{profile_id}",
                "required_assertions": [
                    "all formats identify the same plot id and version",
                    "PNG and SVG are non-empty and decodable",
                    "OPJU contains native editable data and graph objects",
                    "success is shown only after file proof matches Core metadata",
                ],
            },
            "windows_ui": {
                "case_id": f"BB-CHART-{profile_id}",
                "specification": "docs/PLOTAGENT-V3-BLACK-BOX-CAPABILITY.md",
                "required_evidence": [
                    "formal Electron screenshot",
                    "source and field binding",
                    "rendered plot id and version",
                    "artifact identity when exported",
                ],
            },
        },
        "candidate_evidence_status": "UNVERIFIED",
    }


def _domain_entries() -> list[dict[str, Any]]:
    fault_ids = [case.case_id for case in FAULT_CASES]
    return [
        {
            "domain_id": "TASK-STATE",
            "title": "任务状态与副作用",
            "requirements": [
                "规划",
                "追问",
                "确认",
                "执行",
                "部分失败",
                "修复",
                "跳过",
                "重新确认",
                "取消",
                "恢复",
                "重启",
                "data updates undo and redo complete immutable data/binding snapshots",
                "older persisted plans remain readable after additive contract upgrades",
            ],
            "deterministic_sources": [
                "tests/contracts/test_agent_tasks.py",
                "tests/tasking/test_task_ledger.py",
                "tests/desktop_core/test_agent_foundation.py",
                "tests/desktop_core/test_application.py",
                "src/main/agent/task-pump.test.ts",
                "src/main/agent/agent-foundation-runtime.test.ts",
                "src/renderer/src/data/productState.test.ts",
                "src/renderer/src/components/TaskDrawer.test.tsx",
                "src/renderer/src/data/plotHistory.test.ts",
            ],
            "release_runner": "scripts/run_release_operational_matrix.py",
            "case_ids": [
                *[
                    f"TASK-BATCH-{index:02d}"
                    for index in range(1, len(BATCH_NODEIDS) + 1)
                ],
                "TASK-LEGACY-PLAN-SCHEMA-COMPAT",
                "TASK-DATA-UPDATE-UNDO-REDO",
            ],
            "contract": "docs/PLOTAGENT-AGENT-TASK-STATE-MATRIX.md",
            "windows_ui_cases": [
                "BB-TASK-QUESTION-CONFIRM",
                "BB-TASK-PARTIAL-REPAIR-RECONFIRM",
                "BB-TASK-SKIP-CANCEL",
                "BB-TASK-RESTART-RESUME",
                "BB-TASK-DATA-UPDATE-UNDO-REDO",
            ],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "DATA-INPUT",
            "title": "导入、类型、单位与数据边界",
            "requirements": [
                "CSV/TSV",
                "multi-sheet XLS/XLSX/XLSM",
                "instrument TXT/DAT preamble and blocks",
                "missing and non-finite values",
                "extreme values and long text",
                "dynamic series cardinality",
                "immutable provenance and source coordinates",
            ],
            "deterministic_sources": [
                "tests/storage/test_project_storage.py",
                "tests/importing/test_goldens.py",
                "tests/workflows/test_data_ops.py",
                "tests/desktop_core/test_application.py",
                "tests/engine/test_release_data_stress_matrix.py",
            ],
            "release_runners": [
                "scripts/run_release_operational_matrix.py",
                "scripts/run_release_data_stress_matrix.py",
            ],
            "case_ids": [
                "IMPORT-CSV-100K",
                "IMPORT-XLSX-MULTISHEET",
                "IMPORT-TXT-INSTRUMENT",
                "IMPORT-TXT-MULTIBLOCK",
                *STRESS_CASE_IDS,
            ],
            "windows_ui_cases": [
                "BB-DATA-CSV",
                "BB-DATA-XLSX-MULTISHEET",
                "BB-DATA-TXT-INSTRUMENT",
                "BB-DATA-PARTIAL-IMPORT",
            ],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "MULTI-SOURCE",
            "title": "批量任务与多来源合并",
            "requirements": [
                "one task item per source",
                "multiple sources aligned into one renderer view",
                "explicit concatenate_sources or align_sources_on_x",
                "source-specific chart types",
                "partial success retains completed items",
                "a selected derived plot restores every immutable input and its data program",
                "confirmation cards identify raw source fields for every renderer role",
                "confirmation cards hydrate real sample rows for every referenced source",
            ],
            "deterministic_sources": [
                "tests/workflows/test_workflow_contracts.py",
                "tests/workflows/test_data_ops.py",
                "tests/desktop_core/test_application.py",
                "src/renderer/src/App.test.tsx",
            ],
            "release_runner": "scripts/run_release_operational_matrix.py",
            "case_ids": [
                "MULTI-BATCH-DIFFERENT-CHARTS",
                "MULTI-ALIGN-ON-X",
                "MULTI-CONCATENATE",
                "MULTI-PARTIAL-REPAIR",
                "MULTI-DERIVED-PLOT-CONTEXT-RECOVERY",
                "MULTI-CONFIRMATION-PROVENANCE",
                "MULTI-CONFIRMATION-SAMPLES-ALL-SOURCES",
            ],
            "windows_ui_cases": [
                "BB-MULTI-BATCH",
                "BB-MULTI-SAME-PLOT",
                "BB-MULTI-PARTIAL-REPAIR",
            ],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "UI",
            "title": "正式桌面交互",
            "requirements": [
                "data card explains prepared data",
                "confirmation card exposes every binding and source",
                "timeline appends results below plans",
                "editor preserves tab and exact plot target",
                "task progress, errors and terminal states are readable",
                "undo, redo and restart project the durable state",
                "data-update undo restores the complete prior data reference and bindings",
                (
                    "the UI chart choice is a default and the latest explicit "
                    "natural-language chart may override it"
                ),
                (
                    "the composer projects one final chart or a heterogeneous "
                    "multi-chart task from the durable plan"
                ),
                (
                    "chart projection remains correct across revision, rejection, "
                    "execution, restart, and late responses"
                ),
                (
                    "a projected single chart becomes the next structured default while a "
                    "heterogeneous task never leaks a hidden single-chart default"
                ),
            ],
            "deterministic_sources": [
                "src/renderer/src/App.test.tsx",
                "src/renderer/src/components/TaskDrawer.test.tsx",
                "src/renderer/src/components/FocusEditor.test.tsx",
                "src/renderer/src/components/ChartLibrary.test.tsx",
                "src/renderer/src/styles.test.ts",
                "src/main/ipc/desktop-ipc.test.ts",
            ],
            "case_ids": [
                "RC-UI-01",
                "RC-UI-02",
                "RC-UI-03",
                "RC-UI-04",
                "RC-UI-05",
                "RC-UI-06",
                "RC-UI-07",
            ],
            "windows_ui_cases": [
                "RC-UI-01",
                "RC-UI-02",
                "RC-UI-03",
                "RC-UI-04",
                "RC-UI-05",
                "RC-UI-06",
                "RC-UI-07",
            ],
            "required_artifacts": ["case CSV", "screenshots", "terminal log", "run metadata"],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "FAULT-RECOVERY",
            "title": "模型、Core、Origin、存储与锁故障",
            "requirements": [
                "provider timeout, rate limit, offline, proxy and malformed JSON",
                "Core malformed protocol and crash recovery",
                "cancel and partial execution",
                "safe retry, semantic repair and no-progress stop",
                "atomic disk failure and disk full",
                "Origin unavailable and Origin export failure",
                "dead writer recovery and live writer rejection",
            ],
            "deterministic_sources": [
                "tests/engine/test_release_fault_matrix.py",
                "tests/storage/test_project_storage.py",
                "tests/desktop_core/test_application.py",
                "src/main/core/supervisor-state.test.ts",
                "src/main/ipc/desktop-ipc.test.ts",
            ],
            "release_runners": [
                "scripts/run_release_fault_matrix.py",
                "scripts/run_release_packaged_matrix.py",
            ],
            "case_ids": [
                *fault_ids,
                "FAULT-CORE-CRASH-RECOVERY",
                "FAULT-ORIGIN-UNAVAILABLE",
                "FAULT-OPJU-EXPORT",
                "FAULT-DISK-FULL",
                "FAULT-DEAD-WRITER-LOCK",
                "FAULT-LIVE-WRITER-LOCK",
            ],
            "windows_ui_cases": [
                "BB-FAULT-PROVIDER",
                "BB-FAULT-PARTIAL-REPAIR",
                "BB-FAULT-ORIGIN",
                "BB-FAULT-RESTART-LOCK",
            ],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "EXPORT",
            "title": "PNG、SVG、OPJU 与版本一致性",
            "requirements": [
                "latest durable plot id and version are exported",
                "PNG and SVG are valid and non-empty",
                "OPJU is native, editable and fresh-reopen verified",
                "failure never displays a success receipt",
                "success receipt includes format, path name, plot id and version",
            ],
            "deterministic_sources": [
                "tests/desktop_core/test_application.py",
                "src/main/ipc/desktop-ipc.test.ts",
                "src/renderer/src/App.test.tsx",
                "tests/engine/test_release_matrix.py",
            ],
            "release_runners": [
                "scripts/run_release_matrix.py",
                "scripts/run_release_origin_matrix.py",
                "scripts/run_release_edit_matrix.py",
            ],
            "case_ids": [
                "EXPORT-34-PNG-SVG-OPJU",
                "EXPORT-LATEST-VERSION",
                "EXPORT-OPJU-NATIVE-FRESH",
                "EXPORT-FAILURE-NO-SUCCESS",
                "EXPORT-PROJECT-126",
            ],
            "windows_ui_cases": ["RC-EXP-126", "BB-EXPORT-PNG", "BB-EXPORT-SVG", "BB-EXPORT-OPJU"],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "PERFORMANCE",
            "title": "性能与资源边界",
            "requirements": [
                "100k row import and render",
                "bounded memory evidence",
                "large task progress remains responsive",
            ],
            "deterministic_sources": [
                "tests/engine/test_release_data_stress_matrix.py",
                "tests/engine/test_release_operational_matrix.py",
            ],
            "release_runners": [
                "scripts/run_release_data_stress_matrix.py",
                "scripts/run_release_operational_matrix.py",
            ],
            "case_ids": ["LARGE-K01-100K-RENDER", "IMPORT-CSV-100K"],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "PACKAGING",
            "title": "Windows 打包、隔离配置与安装产物",
            "requirements": [
                "installer identity matches frozen HEAD",
                "packaged Core starts in an isolated profile",
                "frozen Core routes the Origin worker entry without recursive Core startup",
                "packaged Core performs a real render and verified PNG/SVG export",
                "packaged Electron opens and closes cleanly",
                "Origin missing, wrong-version and supported states are truthful",
            ],
            "deterministic_sources": [
                "tests/engine/test_release_packaged_matrix.py",
                "tests/packaging/windows-release-tools.test.ps1",
            ],
            "release_runner": "scripts/run_release_packaged_matrix.py",
            "case_ids": [
                "PACKAGED-INTEGRITY",
                "PACKAGED-FROZEN-ORIGIN-WORKER-ENTRY",
                "PACKAGED-ORIGIN-MISSING",
                "PACKAGED-ORIGIN-WRONG-VERSION",
                "PACKAGED-ORIGIN-SUPPORTED",
                "PACKAGED-CORE-RENDER-EXPORT",
                "PACKAGED-ELECTRON-ISOLATED-PROFILE",
            ],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "BLACKBOX",
            "title": "完整 Windows 回归与探索性黑盒",
            "requirements": [
                "all 34 chart cases are attempted in formal Electron",
                "task, data, multi-source, edits, exports and recovery are exercised",
                "exploratory cases are not pre-scripted by implementation details",
                "zero required UNVERIFIED, FAIL and BLOCKED at release",
            ],
            "specifications": [
                "docs/PLOTAGENT-V3-BLACK-BOX-CAPABILITY.md",
                "docs/PLOTAGENT-RELEASE-COVERAGE-LEDGER.json",
            ],
            "case_ids": ["BB-FROZEN-REGRESSION", "BB-EXPLORATORY"],
            "required_artifacts": [
                "report.md",
                "case CSV",
                "run-metadata.json",
                "evidence screenshots",
                "exports",
            ],
            "candidate_evidence_status": "UNVERIFIED",
        },
        {
            "domain_id": "SEQ70",
            "title": "真实模型 24×3 语义评测",
            "requirements": [
                "same frozen HEAD and fixture identity",
                "one complete scored run only",
                "all frozen thresholds pass",
                "no best-of rerun selection",
            ],
            "runner": "scripts/run_seq70_workflow_eval.ts",
            "fixture": "tests/fixtures/seq70/workflow_tasks.json",
            "case_ids": ["SEQ70-24X3"],
            "required_artifacts": ["REPORT.md", "report.json", "index.html"],
            "candidate_evidence_status": "UNVERIFIED",
        },
    ]


def build_ledger() -> dict[str, Any]:
    charts = [_chart_entry(profile) for profile in ENGINE_PROFILES]
    ledger = {
        "schema_version": "plotagent.release-coverage-ledger.v1",
        "contract_revision": "2026-08-22",
        "purpose": (
            "Assign every release requirement to deterministic, runtime and UI evidence; "
            "candidate-specific results are recorded separately and must share one Git HEAD."
        ),
        "status_policy": {
            "assignment": "Every row in this file is assigned, but not thereby passed.",
            "candidate_states": ["PASS", "FAIL", "BLOCKED", "UNVERIFIED"],
            "release_rule": "No required row may be FAIL, BLOCKED or UNVERIFIED.",
        },
        "chart_count": len(charts),
        "charts": charts,
        "domain_count": len(DOMAIN_IDS),
        "domains": _domain_entries(),
    }
    validate_ledger(ledger)
    return ledger


def _source_paths(entry: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for key in (
        "deterministic_sources",
        "release_runners",
        "specifications",
    ):
        values = entry.get(key, [])
        paths.update(str(value) for value in values)
    for key in ("release_runner", "runner", "fixture", "contract", "specification"):
        value = entry.get(key)
        if value:
            paths.add(str(value))
    return paths


def _validate_target(target: str) -> None:
    path_text, separator, symbol = target.partition("::")
    path = REPOSITORY / path_text
    if not path.is_file():
        raise ValueError(f"assigned release source does not exist: {path_text}")
    if separator and symbol not in path.read_text(encoding="utf-8"):
        raise ValueError(f"assigned release symbol does not exist: {target}")


def validate_ledger(ledger: dict[str, Any]) -> None:
    profile_ids = [str(profile.profile_id) for profile in ENGINE_PROFILES]
    recipe_ids = [str(profile_id) for profile_id in ORIGIN_RENDERABLE_RECIPES]
    release_case_ids = {case.profile_id for case in RELEASE_CASES}
    charts = ledger["charts"]
    chart_ids = [chart["profile_id"] for chart in charts]
    if len(profile_ids) != 34 or chart_ids != profile_ids:
        raise ValueError("coverage ledger must preserve all 34 public profiles in catalog order")
    if set(profile_ids) != set(recipe_ids) or set(profile_ids) != release_case_ids:
        raise ValueError("profile, Origin recipe and release fixture catalogs differ")
    expected_variants = {"minimal", "representative", "edge_error"}
    for profile_id in profile_ids:
        variants = {
            case.variant for case in RELEASE_CASES if case.profile_id == profile_id
        }
        if variants != expected_variants:
            raise ValueError(f"{profile_id} lacks the three frozen release variants")
    for chart in charts:
        assignments = chart["assignments"]
        if tuple(assignments) != CHART_ASSIGNMENT_KEYS:
            raise ValueError(f"{chart['profile_id']} has incomplete chart assignments")
        keys = assignments["offline_matrix"]["matrix_keys"]
        if len(keys) != 9 or len(set(keys)) != 9:
            raise ValueError(f"{chart['profile_id']} must own nine unique offline MatrixKeys")
        if assignments["origin_fresh_reopen"]["matrix_key"] not in keys:
            raise ValueError(f"{chart['profile_id']} Origin evidence is not in its matrix")
        exports = assignments["exports"]["matrix_keys"]
        if len(exports) != 3 or not set(exports).issubset(keys):
            raise ValueError(f"{chart['profile_id']} export assignment is incomplete")
        if chart["candidate_evidence_status"] != "UNVERIFIED":
            raise ValueError("a coverage contract cannot claim candidate execution evidence")
        _validate_target(assignments["data_contract"]["source"])
        _validate_target(assignments["data_contract"]["deterministic_test"])
        _validate_target(assignments["offline_matrix"]["runner"])
        _validate_target(assignments["origin_fresh_reopen"]["runner"])
        for test in assignments["public_edits"]["deterministic_tests"]:
            _validate_target(test)
        _validate_target(assignments["public_edits"]["runner"])
        _validate_target(assignments["history_recovery"]["deterministic_test"])
        _validate_target(assignments["exports"]["edit_runner"])
        _validate_target(assignments["windows_ui"]["specification"])
    domains = ledger["domains"]
    domain_ids = [domain["domain_id"] for domain in domains]
    if tuple(domain_ids) != DOMAIN_IDS or len(set(domain_ids)) != len(DOMAIN_IDS):
        raise ValueError("cross-cutting release domain assignments are incomplete")
    for domain in domains:
        if not domain.get("requirements") or not domain.get("case_ids"):
            raise ValueError(f"{domain['domain_id']} has no requirements or cases")
        case_ids = domain["case_ids"]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError(f"{domain['domain_id']} repeats a case assignment")
        for source in _source_paths(domain):
            path = REPOSITORY / source
            if path == JSON_OUTPUT:
                continue
            if not path.is_file():
                raise ValueError(f"assigned release source does not exist: {source}")


def _markdown(ledger: dict[str, Any]) -> str:
    chart_rows = []
    for chart in ledger["charts"]:
        assignments = chart["assignments"]
        chart_rows.append(
            (
                "| {id} | {name} | 9 MatrixKeys | {origin} | {edit} | {recovery} | "
                "{export} | {ui} |"
            ).format(
                id=chart["profile_id"],
                name=chart["chinese_name"],
                origin=assignments["origin_fresh_reopen"]["case_id"],
                edit=assignments["public_edits"]["case_id_prefix"] + "*",
                recovery=assignments["history_recovery"]["case_id"],
                export=assignments["exports"]["case_id"],
                ui=assignments["windows_ui"]["case_id"],
            )
        )
    domain_rows = []
    for domain in ledger["domains"]:
        sources = sorted(_source_paths(domain))
        source_text = "<br>".join(f"`{source}`" for source in sources)
        cases = "、".join(domain["case_ids"])
        domain_rows.append(
            f"| {domain['domain_id']} | {domain['title']} | {cases} | {source_text} | UNVERIFIED |"
        )
    return "\n".join(
        [
            "# PlotAgent 发布覆盖账本",
            "",
            "> 本文件由 `scripts/build_release_coverage_ledger.py` 生成。它只证明测试归属完整，",
            "> 不证明候选已经通过；实际结果必须来自同一冻结 HEAD 的运行产物。",
            "",
            "## 1. 发布规则",
            "",
            (
                "- 34 个公开图类必须各自具备数据合同、离线矩阵、Origin fresh-reopen、"
                "公共编辑、历史恢复、三格式导出和正式 UI case。"
            ),
            (
                "- 任务状态、数据输入、多来源、UI、故障恢复、导出、性能、打包、黑盒和 "
                "SEQ-70 必须各有可执行归属。"
            ),
            "- 发布时任何必测项为 `FAIL`、`BLOCKED` 或 `UNVERIFIED` 都是 `NO-GO`。",
            "- JSON 版本是机器事实源；本页只提供审阅视图。",
            "",
            "## 2. 34 图逐项归属",
            "",
            "| ID | 图类 | 离线 | Origin | 公共编辑 | 撤销/重做/重启 | 导出 | Windows UI |",
            "|---|---|---|---|---|---|---|---|",
            *chart_rows,
            "",
            "## 3. 跨图类产品域归属",
            "",
            "| 域 | 范围 | 冻结 case | 可执行来源 | 候选证据 |",
            "|---|---|---|---|---|",
            *domain_rows,
            "",
            "## 4. 产物关系",
            "",
            "1. `run_release_matrix.py` 生成 306 个唯一 MatrixKey。",
            (
                "2. `run_release_origin_matrix.py` 在同一 HEAD 上关闭 34 个 representative "
                "OPJU 的 live/fresh 证据。"
            ),
            (
                "3. `run_release_edit_matrix.py` 逐能力执行 Matplotlib 与 Origin 编辑，并保存"
                "独立参数合同。"
            ),
            "4. 数据、故障、运行与打包 runner 各自产生 `run-metadata.json`、CSV 和报告。",
            "5. Windows 黑盒与 SEQ-70 只能在候选冻结后执行，不能替代上述确定性证据。",
            "",
        ]
    )


def render_outputs() -> tuple[str, str]:
    ledger = build_ledger()
    json_text = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    return json_text, _markdown(ledger)


def _check(path: Path, expected: str) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    json_text, markdown_text = render_outputs()
    if args.check:
        stale = [
            str(path.relative_to(REPOSITORY))
            for path, expected in (
                (JSON_OUTPUT, json_text),
                (MARKDOWN_OUTPUT, markdown_text),
            )
            if not _check(path, expected)
        ]
        if stale:
            print("stale release coverage ledger: " + ", ".join(stale))
            return 1
        print("release coverage ledger is current")
        return 0
    JSON_OUTPUT.write_text(json_text, encoding="utf-8")
    MARKDOWN_OUTPUT.write_text(markdown_text, encoding="utf-8")
    print(f"WROTE={JSON_OUTPUT.relative_to(REPOSITORY)}")
    print(f"WROTE={MARKDOWN_OUTPUT.relative_to(REPOSITORY)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
