"""Run the frozen deterministic DataPreparationRecipe cost/safety evaluation."""

from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from plotagent.data_preparation.recipes import build_data_preparation_recipe
from plotagent.storage import ImportResource, ProjectImportService, ProjectStore
from plotagent.storage.data_preparation_repository import DataPreparationRepository

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests" / "fixtures" / "data_preparation" / "recipe-eval-cases.json"


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _run_id(outcome: Any) -> str:
    if hasattr(outcome, "datasets") and outcome.datasets:
        return str(outcome.datasets[0].preparation_run_id)
    run_id = getattr(outcome, "preparation_run_id", None)
    if isinstance(run_id, str):
        return run_id
    raise AssertionError("preparation outcome did not expose a run id")


def evaluate(case_file: Path) -> dict[str, Any]:
    specification = json.loads(case_file.read_text(encoding="utf-8"))
    started = time.perf_counter()
    root = ROOT / "build" / "data-preparation-eval" / ".tmp" / f"run-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    with ProjectStore.create(root / "project", project_id="project:data-eval") as project:
        service = ProjectImportService(project)
        repository = DataPreparationRepository(project)
        seed_spec = specification["seed"]
        seed_path = root / str(seed_spec["file_name"])
        seed_path.write_text(str(seed_spec["content"]), encoding="utf-8")
        seed_outcome = service.import_resource(
            ImportResource(resource_id="resource:seed", path=seed_path)
        )
        seed_run = repository.get_run(_run_id(seed_outcome))
        recipe = repository.save_recipe(
            build_data_preparation_recipe(
                run=seed_run,
                display_name="冻结双列数据整理",
                parse_step=seed_run.executed_steps[0],
            )
        )

        results: list[dict[str, Any]] = []
        for index, case in enumerate(specification["cases"], start=1):
            source = root / str(case["file_name"])
            source.write_text(str(case["content"]), encoding="utf-8")
            wall_started = time.perf_counter()
            outcome = service.import_resource(
                ImportResource(resource_id=f"resource:case-{index}", path=source)
            )
            wall_ms = int((time.perf_counter() - wall_started) * 1_000)
            run = repository.get_run(_run_id(outcome))
            expected_route = str(case["expected_route"])
            results.append(
                {
                    "case_id": str(case["case_id"]),
                    "expected_route": expected_route,
                    "observed_route": run.route,
                    "state": run.state,
                    "model_turn_count": run.model_turn_count,
                    "tool_call_count": run.tool_call_count,
                    "local_duration_ms": run.local_duration_ms,
                    "wall_duration_ms": wall_ms,
                    "passed": run.route == expected_route and run.model_turn_count == 0,
                }
            )

    negative = [item for item in results if item["expected_route"] != "saved_recipe"]
    repeats = [item for item in results if item["expected_route"] == "saved_recipe"]
    wrong_matches = sum(item["observed_route"] == "saved_recipe" for item in negative)
    repeated_model_turns = sum(item["model_turn_count"] > 0 for item in repeats)
    durations = [int(item["wall_duration_ms"]) for item in results]
    metrics = {
        "case_count": len(results),
        "repeat_case_count": len(repeats),
        "negative_case_count": len(negative),
        "wrong_auto_match_rate": wrong_matches / len(negative) if negative else 0.0,
        "repeat_model_turn_rate": repeated_model_turns / len(repeats) if repeats else 0.0,
        "scored_model_turns": sum(int(item["model_turn_count"]) for item in results),
        "estimated_model_cost_cny": 0.0,
        "local_median_ms": _percentile(durations, 0.5),
        "local_p95_ms": _percentile(durations, 0.95),
        "wall_duration_ms": int((time.perf_counter() - started) * 1_000),
    }
    thresholds = specification["thresholds"]
    qualified = (
        all(bool(item["passed"]) for item in results)
        and metrics["wrong_auto_match_rate"] <= float(thresholds["wrong_auto_match_rate_max"])
        and metrics["repeat_model_turn_rate"] <= float(thresholds["repeat_model_turn_rate_max"])
        and metrics["local_p95_ms"] <= int(thresholds["local_p95_ms_max"])
    )
    return {
        "schema_version": "data-preparation-eval-report.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "case_source": str(case_file),
        "recipe_id": recipe.recipe_id,
        "thresholds": thresholds,
        "metrics": metrics,
        "qualified": qualified,
        "cases": results,
    }


def _markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# Data preparation frozen evaluation",
        "",
        f"Qualification: **{'GO' if report['qualified'] else 'NO-GO'}**",
        "",
        f"- Cases: {metrics['case_count']}",
        f"- Wrong automatic Recipe matches: {metrics['wrong_auto_match_rate']:.6f}",
        f"- Repeated-input model turn rate: {metrics['repeat_model_turn_rate']:.6f}",
        (
            "- Scored model turns / estimated cost: "
            f"{metrics['scored_model_turns']} / ¥{metrics['estimated_model_cost_cny']:.6f}"
        ),
        f"- Local median / p95: {metrics['local_median_ms']} ms / {metrics['local_p95_ms']} ms",
        "",
        "| Case | Expected | Observed | State | Model turns | Wall ms | Result |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for item in report["cases"]:
        lines.append(
            f"| {item['case_id']} | {item['expected_route']} | {item['observed_route']} | "
            f"{item['state']} | {item['model_turn_count']} | {item['wall_duration_ms']} | "
            f"{'PASS' if item['passed'] else 'FAIL'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = evaluate(args.cases.resolve())
    output = args.output_dir or (
        ROOT / "build" / "data-preparation-eval" / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "REPORT.md").write_text(_markdown(report), encoding="utf-8")
    print(output)
    if args.check and not report["qualified"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
