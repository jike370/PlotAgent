"""Rebuild native Origin artifacts from plots already accepted by the real Agent chain.

This intentionally reuses the stored PlotSpecs and decisions. It is for renderer-only
fixes, so it neither contacts the model provider nor reads an API credential.
"""

from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, cast

from run_real_llm_visual_audit import Harness, _contact_sheet, _origin_png, _write_index


def _copy_evidence(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for name in ("data.csv", "reference.png", "matplotlib.png", "decisions.json"):
        shutil.copy2(source / name, destination / name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Rebuild only the named case; may be repeated.",
    )
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing audit directory: {output}")
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file() or not (source / "_app").is_dir():
        raise SystemExit("source is not a complete PlotAgent visual audit")
    manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    records = cast(list[dict[str, Any]], manifest["cases"])
    if args.case_ids:
        requested = set(cast(list[str], args.case_ids))
        known = {cast(str, record["case_id"]) for record in records}
        unknown = requested - known
        if unknown:
            raise SystemExit(f"unknown audit case(s): {', '.join(sorted(unknown))}")
        records = [
            record for record in records if cast(str, record["case_id"]) in requested
        ]
    output.mkdir(parents=True)

    harness = Harness(source / "_app")
    try:
        for index, record in enumerate(records, start=1):
            case_id = cast(str, record["case_id"])
            print(f"[{index}/{len(records)}] {case_id}", flush=True)
            source_case = source / case_id
            output_case = output / case_id
            _copy_evidence(source_case, output_case)
            project_id = cast(str, record["project_id"])
            plot_id = cast(str, record["plot_id"])
            plot_version = cast(int, record["plot_version"])
            harness.call("projects.open", {"project_id": project_id})
            opju_path = output_case / f"{case_id}.opju"
            result = harness.call(
                "exports.origin",
                {
                    "project_id": project_id,
                    "plot_id": plot_id,
                    "plot_version": plot_version,
                    "destination_resource_id": f"resource:origin-rebuild-{case_id}",
                    "destination_path": str(opju_path),
                    "idempotency_key": f"audit-origin-rebuild-{uuid.uuid4().hex}",
                    "expected_version": plot_version,
                },
            )
            if result.get("format") != "opju":
                raise RuntimeError(f"native Origin rebuild failed: {result.get('result')}")
            _origin_png(opju_path, output_case / "origin.png")
            _contact_sheet(output_case)
            _write_index(output, records)
    finally:
        harness.close()
    _write_index(output, records)
    print(json.dumps({"output": str(output), "completed": len(records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
