"""Build one fresh-reopen-validated OPJU per qualified chart.

Each project contains two graph pages in a fixed order: default, then the
representative edited state.  The source data and PlotSpecs are reused from the
visual-qualification generators; charts without same-source evidence remain
excluded.
"""

# ruff: noqa: E402 -- repository bootstrap precedes local application imports.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.registry import PRODUCT_CHART_IDS
from plotagent.origin import build_origin_export_spec, compile_origin_plan, export_origin
from plotagent.origin.models import OriginExportSuccess
from plotagent.rendering import PlotResolver, RenderTable, ResolvedPlot
from scripts import build_seq20_visual_baseline as seq20
from scripts import build_visual29_fixed as fixed
from scripts import build_visual29_matrix as matrix
from scripts import build_visual29_structural as structural
from scripts import build_visual29_structural_synthetic as structural_synthetic
from scripts.visual_source_identity import source_build_identity

Lane = Literal["seq20", "fixed", "matrix", "structural"]
OUTPUT = REPOSITORY / "build" / "visual-audit"
MANIFEST_PATH = OUTPUT / "per-chart-opju.manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _items(selected: set[Lane]) -> list[tuple[Lane, Any, Path, Path]]:
    items: list[tuple[Lane, Any, Path, Path]] = []
    if "seq20" in selected:
        for batch, cases in seq20.BATCHES.items():
            for case in cases:
                items.append(
                    (
                        "seq20",
                        case,
                        seq20.FIXTURES / case.case_id / "data.csv",
                        seq20.OUTPUT / f"batch-{batch}" / case.case_id / f"{case.chart_id}.opju",
                    )
                )
    if "fixed" in selected:
        items.extend(
            (
                "fixed",
                case,
                fixed.FIXTURES / case.case_id / "data.csv",
                fixed.OUTPUT / case.case_id / f"{case.chart_id}.opju",
            )
            for case in fixed.QUALIFIED_CASES
        )
    if "matrix" in selected:
        items.extend(
            (
                "matrix",
                case,
                matrix.FIXTURES / case.case_id / "data.csv",
                matrix.OUTPUT / case.case_id / f"{case.chart_id}.opju",
            )
            for case in matrix.CASES
        )
    if "structural" in selected:
        items.extend(
            (
                "structural",
                case,
                structural.FIXTURES / case.case_id / "data.csv",
                structural.OUTPUT / case.case_id / f"{case.chart_id}.opju",
            )
            for case in structural.CASES
        )
        items.extend(
            (
                "structural",
                case,
                structural_synthetic.FIXTURES / case.case_id / "data.csv",
                structural_synthetic.OUTPUT / case.case_id / f"{case.chart_id}.opju",
            )
            for case in structural_synthetic.CASES
        )
    product_ids = set(PRODUCT_CHART_IDS)
    return [item for item in items if item[1].chart_id in product_ids]


def _mechanically_edit_resolved_data(
    resolved: ResolvedPlot,
) -> tuple[ResolvedPlot, dict[str, Any]]:
    """Clone one resolved native table and change one finite numeric cell."""

    first_hash = resolved.plan.layers[0].data_ref.object_hash
    original = resolved.tables[first_hash]
    columns = {field_id: list(values) for field_id, values in original.columns.items()}
    mutation: dict[str, Any] | None = None
    preferred_roles = (
        "value",
        "z",
        "height",
        "y",
        "center",
        "upper",
        "survival",
        "risk_count",
        "effect",
        "estimate",
        "size",
        "weight",
    )
    ranked_fields = sorted(
        columns,
        key=lambda field_id: next(
            (
                index
                for index, role in enumerate(preferred_roles)
                if field_id.rsplit(".", 1)[-1] == role
            ),
            len(preferred_roles),
        ),
    )
    for field_id in ranked_fields:
        for row_position, raw_value in enumerate(columns[field_id]):
            if (
                not isinstance(raw_value, (int, float))
                or isinstance(raw_value, bool)
                or not (-float("inf") < float(raw_value) < float("inf"))
            ):
                continue
            before = float(raw_value)
            if isinstance(raw_value, int):
                after: int | float = raw_value + 1
            elif -1.0 <= before <= 1.0:
                after = before * 0.99 if before else 0.01
            else:
                after = before + max(abs(before) * 0.01, 0.01)
            columns[field_id][row_position] = after
            mutation = {
                "table_sha256_before": first_hash,
                "field_id": field_id,
                "row_position": row_position,
                "before": before,
                "after": float(after),
            }
            break
        if mutation is not None:
            break
    if mutation is None:
        raise RuntimeError("representative edited state requires one finite numeric value")

    changed = RenderTable.from_columns(columns)
    mutation["table_sha256_after"] = changed.object_hash
    tables = dict(resolved.tables)
    del tables[first_hash]
    tables[changed.object_hash] = changed
    layers = tuple(
        layer.model_copy(
            update={
                "data_ref": layer.data_ref.model_copy(
                    update={"object_hash": changed.object_hash}
                )
            }
        )
        if layer.data_ref.object_hash == first_hash
        else layer
        for layer in resolved.plan.layers
    )
    source_hashes = tuple(
        changed.object_hash if item == first_hash else item
        for item in resolved.plan.source_content_hashes
    )
    if changed.object_hash not in source_hashes:
        source_hashes += (changed.object_hash,)
    integrity = resolved.plan.data_integrity.model_copy(
        update={
            "full_data_hash": canonical_hash(
                cast(JsonValue, sorted(table.object_hash for table in tables.values()))
            )
        }
    )
    plan = resolved.plan.model_copy(
        update={
            "layers": layers,
            "source_content_hashes": source_hashes,
            "data_integrity": integrity,
        }
    )
    return ResolvedPlot.create(plan, tables), mutation


def _resolved_pair_with_mutation(
    lane: Lane, case: Any, frame: pd.DataFrame
) -> tuple[tuple[ResolvedPlot, ...], dict[str, Any]]:
    if lane == "structural" and case in structural_synthetic.CASES:
        resolved = [
            structural_synthetic.build_resolved(case.chart_id, frame, edited=edited)
            for edited in (False, True)
        ]
    else:
        builder: Any = {
            "seq20": seq20._build_plot,
            "fixed": fixed._build_plot,
            "matrix": matrix._build_plot,
            "structural": structural._build_plot,
        }[lane]
        resolved = []
        for edited in (False, True):
            plot, store = builder(case, frame, edited=edited)
            resolved.append(PlotResolver().resolve(plot, store))
    edited_resolved, mutation = _mechanically_edit_resolved_data(resolved[1])
    return (resolved[0], edited_resolved), mutation


def _resolved_pair(lane: Lane, case: Any, frame: pd.DataFrame) -> tuple[ResolvedPlot, ...]:
    return _resolved_pair_with_mutation(lane, case, frame)[0]


def _graph_data_sha256(plan: Any, graph_index: int) -> str:
    graph = plan.graph_objects[graph_index]
    objects = {item.object_id: item for item in plan.data_objects}
    payload = [objects[object_id].model_dump(mode="json") for object_id in graph.data_object_ids]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _graph_style_sha256(graph: Any) -> str:
    def axis_style(axis: Any) -> dict[str, Any]:
        return {
            "orientation": axis.orientation,
            "scale": axis.scale,
            "reverse": axis.reverse,
            "color": axis.color.model_dump(mode="json"),
            "line_width_pt": axis.line_width_pt,
        }

    def plot_style(plot: Any) -> dict[str, Any]:
        return {
            key: value
            for key, value in plot.model_dump(mode="json").items()
            if key
            not in {
                "plot_id",
                "data_object_id",
                "x_field_id",
                "y_field_id",
                "role_fields",
                "label",
            }
        }

    payload = {
            "page": (graph.page_width_mm, graph.page_height_mm),
            "font_size_pt": graph.font_size_pt,
            "legend": (
                graph.legend_visible,
                graph.legend_anchor_x,
                graph.legend_anchor_y,
            ),
            "colorbar": (
                graph.colorbar.model_dump(mode="json") if graph.colorbar is not None else None
            ),
            "size_key": (
                graph.size_key.model_dump(mode="json") if graph.size_key is not None else None
            ),
            "layers": tuple(
                {
                    "layout": (
                        layer.left_mm,
                        layer.top_mm,
                        layer.width_mm,
                        layer.height_mm,
                    ),
                    "axes": tuple(axis_style(axis) for axis in layer.axes),
                    "plots": tuple(plot_style(plot) for plot in layer.plots),
                }
                for layer in graph.layers
            ),
        }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {"schema_version": "1.0", "charts": {}}
    return cast(dict[str, Any], json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))


def _write_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(MANIFEST_PATH)


def _build(selected: set[Lane], *, force: bool) -> dict[str, Any]:
    source_identity = source_build_identity(
        REPOSITORY,
        seq20.SOURCE_SCOPE,
        scope_version="per-chart-opju-rendering-v1",
    )
    manifest = _load_manifest()
    charts = manifest.setdefault("charts", {})
    for retired_chart_id in tuple(charts):
        if retired_chart_id not in PRODUCT_CHART_IDS:
            del charts[retired_chart_id]
    manifest.update(
        {
            "schema_version": "1.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "source_build_identity": source_identity,
            "graph_order": ["default", "representative_edited"],
        }
    )

    for lane, case, data_path, target in _items(selected):
        if not data_path.is_file():
            raise RuntimeError(f"frozen data is missing: {data_path}")
        frame = pd.read_csv(data_path)
        pair, data_mutation = _resolved_pair_with_mutation(lane, case, frame)
        plan = compile_origin_plan(
            pair,
            build_origin_export_spec(
                pair,
                export_id=f"export:per-chart.{case.chart_id.lower()}",
                target_scope="selected_plots",
            ),
        )
        plan_sha256 = canonical_hash(plan)
        default_data_sha256 = _graph_data_sha256(plan, 0)
        edited_data_sha256 = _graph_data_sha256(plan, 1)
        default_style_sha256 = _graph_style_sha256(plan.graph_objects[0])
        edited_style_sha256 = _graph_style_sha256(plan.graph_objects[1])
        if default_data_sha256 == edited_data_sha256:
            raise RuntimeError(f"representative data mutation is not represented: {case.chart_id}")
        if default_style_sha256 == edited_style_sha256:
            raise RuntimeError(f"representative style edit is not represented: {case.chart_id}")
        key = str(case.chart_id)
        saved = charts.get(key)
        if (
            not force
            and isinstance(saved, dict)
            and target.is_file()
            and saved.get("source_sha256") == source_identity["source_sha256"]
            and saved.get("origin_plan_sha256") == plan_sha256
            and saved.get("opju_sha256") == _sha256(target)
            and saved.get("fresh_reopen_identical") is True
        ):
            print(f"skip {key}: {target}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        result = export_origin(
            plan,
            target,
            expected_existing_sha256=_sha256(target) if target.is_file() else None,
            timeout_seconds=600.0,
        )
        if not isinstance(result, OriginExportSuccess):
            raise RuntimeError(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if result.build_validation != result.reopen_validation:
            raise RuntimeError(f"fresh-reopen validation drift: {key}")
        charts[key] = {
            "lane": lane,
            "case_id": case.case_id,
            "path": str(target),
            "data_sha256": _sha256(data_path),
            "source_sha256": source_identity["source_sha256"],
            "origin_plan_sha256": plan_sha256,
            "opju_sha256": result.file_sha256,
            "opju_size": result.file_size,
            "validation_report_sha256": result.validation_report_sha256,
            "fresh_reopen_identical": True,
            "graph_order": ["default", "representative_edited"],
            "representative_data_mutation": data_mutation,
            "default_data_sha256": default_data_sha256,
            "edited_data_sha256": edited_data_sha256,
            "default_style_sha256": default_style_sha256,
            "edited_style_sha256": edited_style_sha256,
            "environment": result.environment.to_dict(),
        }
        _write_manifest(manifest)
        print(f"built {key}: {target}")

    _write_manifest(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lane",
        choices=("all", "seq20", "fixed", "matrix", "structural"),
        default="all",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    selected: set[Lane] = (
        {"seq20", "fixed", "matrix", "structural"}
        if args.lane == "all"
        else {args.lane}
    )
    _build(selected, force=args.force)


if __name__ == "__main__":
    main()
