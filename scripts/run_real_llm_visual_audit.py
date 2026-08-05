"""Run a production-Core visual audit against a configured custom model provider.

The script never accepts or reads an API key from arguments or environment
variables. PlotAgent resolves ``custom.default`` from the OS credential store,
the same boundary used by the desktop application.
"""

# ruff: noqa: E501 -- natural-language prompts and generated HTML stay readable verbatim.

from __future__ import annotations

import argparse
import html
import json
import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageDraw, ImageOps

from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.services import RpcContext, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskRegistry

REPOSITORY = Path(__file__).resolve().parents[1]
V2_BENCHMARK = Path(r"C:\Users\pc\Documents\PLOT-v2\test-data\built-in-chart-benchmark")
V2_ADAPTER = Path(r"C:\Users\pc\Documents\PLOT-v2\test-data\origin-adapter-benchmark-v1")


@dataclass(frozen=True, slots=True)
class AuditCase:
    case_id: str
    chart_type_id: str
    title: str
    source: Path
    reference: Path
    reference_kind: str
    create_instruction: str
    edit_instruction: str


CASES = (
    AuditCase(
        "K01_single_trend",
        "K01",
        "Single trend line",
        V2_BENCHMARK / "001_single_trend" / "data.csv",
        V2_ADAPTER / "001_single_trend" / "python_preview.png",
        "v2 regression target (not an independent reference)",
        "请只创建一张 K01 折线图：列 x 映射为 x，列 y 映射为 y。不要替换图形类型。",
        "把当前图的 x 轴标题改为 Time (s)。保持 K01 和数据映射不变。",
    ),
    AuditCase(
        "K03_scatter_correlation",
        "K03",
        "Scatter correlation",
        V2_BENCHMARK / "005_scatter_correlation" / "data.csv",
        V2_ADAPTER / "005_scatter_correlation" / "python_preview.png",
        "v2 regression target (not an independent reference)",
        "Create exactly one K03 scatter plot: map column x to role x and column y to role y. 不要换图。",
        "Set the current plot's y-axis label to Response，保持 K03 和字段映射不变。",
    ),
    AuditCase(
        "K04_bubble_dot",
        "K04",
        "Bubble and colormap scatter",
        V2_BENCHMARK / "014_bubble_dot" / "data.csv",
        V2_BENCHMARK / "014_bubble_dot" / "reference.png",
        "independent Origin-derived reference",
        "请创建一张 K04 气泡颜色散点图：X→x，Y→y，Size→size，Color→color。只创建这一张图。",
        "把当前图的 x 轴标题改为 X value，图形类型和气泡映射不要变。",
    ),
    AuditCase(
        "K09_grouped_column",
        "K09",
        "Grouped column",
        V2_BENCHMARK / "006_grouped_column" / "data.csv",
        V2_BENCHMARK / "006_grouped_column" / "reference.png",
        "independent Origin-derived reference",
        "请创建一张 K09 分组柱状图：B1→category，F→group，D→value。列名虽然不透明，也必须严格按此映射。",
        "将当前图的 y 轴标题改为 Measured value，保持 K09 与分组关系不变。",
    ),
    AuditCase(
        "K22_contour_phase_map",
        "K22",
        "Supplied-grid contour map",
        V2_BENCHMARK / "013_contour_phase_map" / "data.csv",
        V2_BENCHMARK / "013_contour_phase_map" / "reference.png",
        "independent Origin-derived reference",
        "创建一张 K22 规则网格等高图：Wavelength→x，Temperature→y，Amplitude→z。数据已经是完整规则网格，不做拟合或插值。",
        "把当前图的 x 轴标题改为 Wavelength (nm)，保持 K22、网格和 z 映射不变。",
    ),
    AuditCase(
        "S21_forest_plot",
        "S21",
        "Forest effect interval",
        V2_BENCHMARK / "019_forest_plot" / "data.csv",
        V2_ADAPTER / "019_forest_plot" / "python_preview.png",
        "v2 regression target (not an independent reference)",
        "创建一张 S21 森林图：Study→label，estimate→effect，ci_low→lower，ci_high→upper，weight→weight。不得计算新的效应量或置信区间。",
        "Set the current plot's x-axis label to Effect estimate，保持 S21 和区间数据不变。",
    ),
)


class Harness:
    def __init__(self, root: Path) -> None:
        self.application = DesktopApplication(root)
        self.registry = ServiceRegistry()
        self.workers = BoundedWorkerExecutor(max_workers=2, maximum_pending=4)
        self.tasks = TaskRegistry(lambda _event: None)
        self.application.configure_services(self.registry, self.tasks, self.workers)

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        context = RpcContext(
            request_id="audit:" + uuid.uuid4().hex,
            tasks=self.tasks,
            workers=self.workers,
        )
        return cast(dict[str, Any], self.registry.dispatch(method, context, params))

    def close(self) -> None:
        self.workers.shutdown()
        self.application.close()


def _agent_call(
    harness: Harness,
    *,
    project_id: str,
    dataset: dict[str, Any],
    instruction: str,
    expected_version: int,
    run_id: str,
    target_plot_id: str | None = None,
) -> tuple[dict[str, Any], float]:
    params: dict[str, Any] = {
        "project_id": project_id,
        "source_dataset_id": dataset["source_dataset_id"],
        "source_version": dataset["source_version"],
        "user_instruction": instruction,
        "client_model_run_id": run_id,
        "expected_version": expected_version,
        "locale": "zh-CN",
        "retention_acknowledged": True,
    }
    if target_plot_id is not None:
        params["target"] = {"kind": "plot", "id": target_plot_id}
        params["scope"] = "current"
    started = time.perf_counter()
    result = harness.call("agent.decide", params)
    return result, time.perf_counter() - started


def _latest_execution(result: dict[str, Any]) -> dict[str, Any]:
    executions = result.get("executions")
    if isinstance(executions, list) and executions:
        return cast(dict[str, Any], executions[-1])
    execution = result.get("execution")
    if isinstance(execution, dict):
        return cast(dict[str, Any], execution)
    raise RuntimeError("the accepted Agent decision produced no plot execution")


def _origin_png(opju_path: Path, output: Path) -> None:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        op.open(str(opju_path), readonly=True)
        graphs = list(op.pages("g"))
        if not graphs:
            raise RuntimeError("the native project contains no graph page")
        graphs[0].save_fig(str(output), type="png", replace=True, width=1600)
    finally:
        op.exit()
    if not output.is_file() or not output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Origin did not produce a valid PNG")


def _contact_sheet(case_dir: Path) -> None:
    names = ("reference.png", "matplotlib.png", "origin.png")
    labels = ("REFERENCE", "MATPLOTLIB", "ORIGIN")
    loaded = [Image.open(case_dir / name).convert("RGB") for name in names]
    try:
        panel_width, panel_height, label_height = 620, 460, 42
        sheet = Image.new("RGB", (panel_width * 3, panel_height + label_height), "white")
        draw = ImageDraw.Draw(sheet)
        for index, (source, label) in enumerate(zip(loaded, labels, strict=True)):
            fitted = ImageOps.contain(source, (panel_width - 24, panel_height - 24))
            x = index * panel_width + (panel_width - fitted.width) // 2
            y = label_height + (panel_height - fitted.height) // 2
            sheet.paste(fitted, (x, y))
            draw.text((index * panel_width + 16, 14), label, fill="black")
        sheet.save(case_dir / "comparison.png", format="PNG", optimize=True)
    finally:
        for image in loaded:
            image.close()


def _write_index(output: Path, records: list[dict[str, Any]]) -> None:
    cards: list[str] = []
    readme: list[str] = [
        "# DeepSeek v4 Flash real-chain visual audit",
        "",
        "Each case uses the production PlotAgent Core path: import → natural-language create → natural-language edit → formal Matplotlib export → native OPJU export → reopen in Origin → Origin PNG export.",
        "",
        "Reference provenance is stated per case. A v2 regression target is not an independent visual gold standard.",
        "",
    ]
    for record in records:
        folder = record["case_id"]
        cards.append(
            f"""<section><h2>{html.escape(record["chart_type_id"])} · {html.escape(record["title"])}</h2>
<p><b>Reference:</b> {html.escape(record["reference_kind"])} · <b>LLM:</b> create {record["create_seconds"]:.1f}s, edit {record["edit_seconds"]:.1f}s</p>
<a href="{folder}/comparison.png"><img class="sheet" src="{folder}/comparison.png" alt="comparison"></a>
<p><a href="{folder}/data.csv">data</a> · <a href="{folder}/matplotlib.png">Matplotlib PNG</a> · <a href="{folder}/origin.png">Origin PNG</a> · <a href="{folder}/{folder}.opju">OPJU</a> · <a href="{folder}/decisions.json">decisions</a></p></section>"""
        )
        readme.extend(
            [
                f"## {record['chart_type_id']} · {record['title']}",
                "",
                f"- Reference: {record['reference_kind']}",
                f"- Contact sheet: [{folder}/comparison.png]({folder}/comparison.png)",
                f"- Native project: [{folder}/{folder}.opju]({folder}/{folder}.opju)",
                "",
            ]
        )
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>PlotAgent visual audit</title>
<style>body{{font:15px system-ui;margin:32px;background:#f4f5f7;color:#202124}}main{{max-width:1500px;margin:auto}}section{{background:white;padding:22px;margin:22px 0;border-radius:14px;box-shadow:0 2px 12px #0001}}.sheet{{width:100%;height:auto;border:1px solid #ddd}}a{{color:#1358bf}}</style>
<main><h1>PlotAgent · DeepSeek v4 Flash real-chain audit</h1><p>Generated {html.escape(datetime.now().astimezone().isoformat(timespec="seconds"))}. No API key is stored in this directory.</p>{"".join(cards)}</main></html>"""
    (output / "index.html").write_text(document, encoding="utf-8")
    (output / "README.md").write_text("\n".join(readme), encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps(
            {"provider": "deepseek-v4-flash", "cases": records}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )


def _run_case(harness: Harness, case: AuditCase, output: Path) -> dict[str, Any]:
    case_dir = output / case.case_id
    case_dir.mkdir(parents=True)
    shutil.copy2(case.source, case_dir / "data.csv")
    shutil.copy2(case.reference, case_dir / "reference.png")

    created = harness.call(
        "projects.create",
        {
            "display_name": f"Visual audit {case.chart_type_id}",
            "idempotency_key": f"audit-project-{case.case_id}",
        },
    )
    project_id = cast(str, created["project_id"])
    opened = harness.call("projects.open", {"project_id": project_id})
    imported = harness.call(
        "datasets.import",
        {
            "project_id": project_id,
            "resource_id": f"resource:audit-{case.case_id}",
            "source_path": str(case.source),
            "idempotency_key": f"audit-import-{case.case_id}",
            "expected_version": opened["project_version"],
            "options": {},
        },
    )
    if imported.get("kind") != "committed":
        raise RuntimeError(f"import did not commit: {imported.get('kind')}")
    dataset = cast(dict[str, Any], imported["datasets"][0])

    create_result, create_seconds = _agent_call(
        harness,
        project_id=project_id,
        dataset=dataset,
        instruction=case.create_instruction,
        expected_version=cast(int, imported["project_version"]),
        run_id=f"model-run:audit-create-{case.case_id}",
    )
    if create_result.get("accepted") is not True:
        raise RuntimeError(f"create rejected: {create_result.get('error')}")
    create_execution = _latest_execution(create_result)
    if create_execution.get("chart_type_id") != case.chart_type_id:
        raise RuntimeError(
            f"model created {create_execution.get('chart_type_id')} instead of {case.chart_type_id}"
        )
    plot_id = cast(str, create_execution["plot_id"])

    edit_result, edit_seconds = _agent_call(
        harness,
        project_id=project_id,
        dataset=dataset,
        instruction=case.edit_instruction,
        expected_version=cast(int, create_execution["project_version"]),
        run_id=f"model-run:audit-edit-{case.case_id}",
        target_plot_id=plot_id,
    )
    if edit_result.get("accepted") is not True:
        raise RuntimeError(f"edit rejected: {edit_result.get('error')}")
    edit_execution = _latest_execution(edit_result)
    plot_version = cast(int, edit_execution["plot_version"])

    matplotlib_path = case_dir / "matplotlib.png"
    harness.call(
        "exports.png_svg",
        {
            "project_id": project_id,
            "plot_id": plot_id,
            "plot_version": plot_version,
            "format": "png",
            "destination_resource_id": f"resource:matplotlib-{case.case_id}",
            "destination_path": str(matplotlib_path),
            "idempotency_key": f"audit-matplotlib-{case.case_id}",
            "expected_version": plot_version,
        },
    )
    opju_path = case_dir / f"{case.case_id}.opju"
    origin_result = harness.call(
        "exports.origin",
        {
            "project_id": project_id,
            "plot_id": plot_id,
            "plot_version": plot_version,
            "destination_resource_id": f"resource:origin-{case.case_id}",
            "destination_path": str(opju_path),
            "idempotency_key": f"audit-origin-{case.case_id}",
            "expected_version": plot_version,
        },
    )
    if origin_result.get("format") != "opju":
        raise RuntimeError(f"native Origin export failed: {origin_result.get('result')}")
    _origin_png(opju_path, case_dir / "origin.png")
    _contact_sheet(case_dir)

    decisions = {
        "create_instruction": case.create_instruction,
        "create_decision": create_result.get("decision"),
        "edit_instruction": case.edit_instruction,
        "edit_decision": edit_result.get("decision"),
    }
    (case_dir / "decisions.json").write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "case_id": case.case_id,
        "chart_type_id": case.chart_type_id,
        "title": case.title,
        "reference_kind": case.reference_kind,
        "create_seconds": round(create_seconds, 3),
        "edit_seconds": round(edit_seconds, 3),
        "plot_id": plot_id,
        "plot_version": plot_version,
        "project_id": project_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (
        args.output.resolve()
        if args.output is not None
        else REPOSITORY
        / "build"
        / "visual-audit"
        / f"deepseek-v4-flash-{datetime.now():%Y%m%d-%H%M%S}"
    )
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing audit directory: {output}")
    output.mkdir(parents=True)
    missing = [
        str(path) for case in CASES for path in (case.source, case.reference) if not path.is_file()
    ]
    if missing:
        raise SystemExit("missing audit inputs: " + ", ".join(missing))

    harness = Harness(output / "_app")
    records: list[dict[str, Any]] = []
    try:
        provider = harness.call(
            "provider.configure",
            {
                "mode": "custom_provider",
                "provider_config_id": "custom.default",
                "base_url": "https://api.deepseek.com",
                "model_id": "deepseek-v4-flash",
                "retention_acknowledged": True,
            },
        )
        if provider.get("configured") is not True:
            raise RuntimeError("custom.default is not available in the OS credential store")
        for index, case in enumerate(CASES, start=1):
            print(f"[{index}/{len(CASES)}] {case.case_id}", flush=True)
            record = _run_case(harness, case, output)
            records.append(record)
            _write_index(output, records)
            print(
                "  accepted create/edit; matplotlib + Origin + OPJU complete",
                flush=True,
            )
    finally:
        harness.close()
    _write_index(output, records)
    print(json.dumps({"output": str(output), "completed": len(records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
