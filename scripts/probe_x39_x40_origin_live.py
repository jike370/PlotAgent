"""Explicit live Origin acceptance probe for X39 Line Series and X40 Before After.

The default invocation is read-only and prints the acceptance plan.  Every
phase that can start Origin requires ``--allow-origin-com``.  Run ``fresh`` in
a separate process after a render phase so reopening is a genuine fresh-session
gate rather than an in-process assertion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, cast

from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
    SetSeriesStyle,
)
from plotagent.engine.backends.origin.wide_series import (
    WideSeriesOriginProject,
    read_wide_series_native_snapshot,
)

ProfileId = Literal["X39", "X40"]
CaseName = Literal["default", "edited", "dynamic"]
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTALL = Path(r"D:\origin")
DEFAULT_OUTPUT = ROOT / "build" / "origin-live-x39-x40"
HASH = "9" * 64

OFFICIAL_BASELINES: dict[ProfileId, dict[str, object]] = {
    "X39": {
        "opju": "BoxLser.opju",
        "opju_sha256": "365908c1073769ef1cb57403a203e09a5b047e6b98b4619651ec80ac44611c14",
        "template": "BoxLser.otpu",
        "template_sha256": "8396fd58435c4ded363b889d7eb3c8cf8a3b22e82eb539e8cc85f6b58481ec83",
        "long_names": ("Week1", "Week2", "Week3"),
        "comments": ("", "", ""),
        "row_count": 10,
        "designations": (4, 1, 1),
        "subgroup_size": 0,
    },
    "X40": {
        "opju": "BeforeAfter.opju",
        "opju_sha256": "c7ae482bea75cce94c198dd357c5bbb9b19e17678715259f2aa1d0c85da6f12e",
        "template": "BeforeAfter.otpu",
        "template_sha256": "d37a1c2949696f29cd2a2fcf856a2c8b5f8be29e8ab040a83a9c2c9f0e262c0b",
        "long_names": ("Before", "After", "Before", "After"),
        "comments": ("6 to 10", "6 to 10", "11-16", "11-16"),
        "row_count": 5,
        "designations": (4, 1, 1, 1),
        "subgroup_size": 2,
    },
}
PLOT_OGS_SHA256 = "e2a683084c4b75b3da6a82277bf8d309288547e7c5cd4a90e199616fac0d8f7b"


def probe_plan() -> dict[str, object]:
    return {
        "profiles": {
            "X39": {
                "official_project": "BoxLser.opju",
                "official_menu": "run.section(Plot,LineSeries)",
                "source": "untransposed wide worksheet; one Y column per position",
                "native_signature": "one PID-206 group; same worksheet row connects",
            },
            "X40": {
                "official_project": "BeforeAfter.opju",
                "official_menu": "run.section(Plot,BeforeAfter)",
                "source": "untransposed wide worksheet; product accepts exactly one pair",
                "native_signature": "one PID-206 group; subgroup size 2",
            },
        },
        "phases": ["baseline", "default", "edited", "dynamic", "fresh"],
        "automated_gates": [
            "worksheet width/row shape and Y designations",
            "Long Name and Comments metadata",
            "PID 206 member count/order",
            "single native group and group head",
            "member datasets bind the unchanged source columns",
            "X40 subgroup size 2",
            "connector and member style properties",
        ],
        "manual_gate": (
            "In Plot Details verify Connect Data Points is enabled for X39, and "
            "Connect Within Subgroup is enabled for X40. No stable documented "
            "LabTalk property is claimed for these two flags."
        ),
    }


def _case(profile_id: ProfileId, case_name: CaseName) -> tuple[
    PlotDocument,
    tuple[CreatePlot | SetSeriesStyle, ...],
    EngineDataView,
]:
    labels: tuple[str, ...]
    if profile_id == "X39":
        labels = (
            ("Week1", "Week2", "Week3", "Week4", "Week5")
            if case_name == "dynamic"
            else ("Week1", "Week2", "Week3")
        )
        row_count = 12 if case_name == "dynamic" else 5
    else:
        labels = ("Before", "After")
        row_count = 15 if case_name == "dynamic" else 6
    data_ref = EngineDataRef(
        kind="source",
        dataset_id=f"live.{profile_id.lower()}.{case_name}",
        version=1,
        content_hash=HASH,
    )
    bindings = tuple(
        FieldBinding(role=f"series_{index}", field_id=f"field:v{index}")
        for index in range(1, len(labels) + 1)
    )
    columns = tuple(
        EngineColumn(
            field=EngineField(
                field_id=f"field:v{index}",
                name=label,
                logical_type="numeric",
            ),
            values=tuple(
                float(8 + row * 0.7 + index * 1.3 + ((row + index) % 3) * 0.4)
                for row in range(row_count)
            ),
        )
        for index, label in enumerate(labels, start=1)
    )
    token = f"{profile_id.lower()}-{case_name}"
    create = CreatePlot(
        action_id=f"action:create-{token}",
        plot_id=f"plot:{token}",
        profile_id=profile_id,
        data=data_ref,
        bindings=bindings,
    )
    actions: list[CreatePlot | SetSeriesStyle] = [create]
    if case_name == "edited":
        actions.extend(
            (
                SetSeriesStyle(
                    action_id=f"action:connector-{token}",
                    expected_plot_version=1,
                    target=f"series:{token}.connector",
                    color="#303030",
                    line_width_pt=2.0,
                    line_style="dash",
                ),
                SetSeriesStyle(
                    action_id=f"action:column-2-{token}",
                    expected_plot_version=1,
                    target=f"series:{token}.column_2",
                    color="#B2182B",
                    symbol="square",
                    symbol_size_pt=8.0,
                ),
            )
        )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id=profile_id,
        data=data_ref,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    data = EngineDataView(
        data=data_ref,
        row_ids=tuple(f"row:{index + 1}" for index in range(row_count)),
        columns=columns,
    )
    return document, tuple(actions), data


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _json_value(value: object) -> object:
    return list(value) if isinstance(value, tuple) else value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_official_assets(profile_id: ProfileId, install_dir: Path) -> None:
    baseline = OFFICIAL_BASELINES[profile_id]
    artifacts = (
        (cast(str, baseline["opju"]), cast(str, baseline["opju_sha256"])),
        (cast(str, baseline["template"]), cast(str, baseline["template_sha256"])),
        ("Plot.ogs", PLOT_OGS_SHA256),
    )
    for filename, expected_hash in artifacts:
        path = install_dir / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        observed_hash = _sha256(path)
        if observed_hash != expected_hash:
            raise RuntimeError(
                f"official Origin asset drifted: {path}; "
                f"expected={expected_hash}, observed={observed_hash}"
            )
    plot_ogs = (install_dir / "Plot.ogs").read_text(
        encoding="utf-8", errors="replace"
    )
    required = (
        ("[LineSeries]", "run.section(, BoxChartImp, BoxLser 0);", "worksheet -p 206 %1;")
        if profile_id == "X39"
        else ("[BeforeAfter]", "run.section(, general, 206 BeforeAfter 0 1);")
    )
    missing = tuple(fragment for fragment in required if fragment not in plot_ogs)
    if missing:
        raise RuntimeError(f"Plot.ogs lacks official {profile_id} menu chain: {missing}")


def _open_origin() -> Any:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    return op


def _pages(op: Any) -> tuple[Any, Any]:
    graphs = list(op.pages("g"))
    books = list(op.pages("w"))
    if len(graphs) != 1 or len(books) != 1:
        raise RuntimeError(
            f"expected exactly one Origin graph/workbook, got {len(graphs)}/{len(books)}"
        )
    return graphs[0], books[0][0]


def _assert_snapshot(
    snapshot: dict[str, object],
    *,
    profile_id: ProfileId,
    long_names: tuple[str, ...],
    comments: tuple[str, ...],
    row_count: int,
    subgroup_size: int,
    designations: tuple[int, ...] | None = None,
) -> None:
    count = len(long_names)
    expected_indices = tuple(range(1, count + 1))
    checks = {
        "source_layout": snapshot["source_layout"] == "worksheet_wide",
        "worksheet_column_count": snapshot["worksheet_column_count"] == count,
        "row_counts": snapshot["source_row_counts"] == (row_count,) * count,
        "designations": snapshot["worksheet_designations"]
        == ((1,) * count if designations is None else designations),
        "long_names": snapshot["long_names"] == long_names,
        "comments": snapshot["comments"] == comments,
        "member_count": snapshot["native_member_count"] == count,
        "pid_206": snapshot["native_plot_types"] == (206,) * count,
        "member_order": snapshot["plot_indices"] == expected_indices,
        "iterated_order": snapshot["iterated_member_indices"] == expected_indices,
        "single_group": snapshot["native_group_count"] == 1,
        "group_head": snapshot["native_group_heads"] == (1,),
        "source_binding": snapshot["members_bind_source_columns"] is True,
        "boxchart_data_only": snapshot["boxchart_type"] == 2,
        "subgroup_size": snapshot["subgroup_size"] == subgroup_size,
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    if failed:
        raise RuntimeError(f"{profile_id} live snapshot failed: {failed}; {snapshot}")


def _export(graph: Any, path: Path) -> None:
    graph.save_fig(str(path), type="png", replace=True, width=1600)


def run_baseline(profile_id: ProfileId, install_dir: Path, output: Path) -> None:
    baseline = OFFICIAL_BASELINES[profile_id]
    _assert_official_assets(profile_id, install_dir)
    source = install_dir / cast(str, baseline["opju"])
    if not source.is_file():
        raise FileNotFoundError(source)
    op = _open_origin()
    try:
        op.new(asksave=False)
        if not op.open(str(source), readonly=True, asksave=False):
            raise RuntimeError(f"could not open official sample {source}")
        graph, sheet = _pages(op)
        long_names = cast(tuple[str, ...], baseline["long_names"])
        comments = cast(tuple[str, ...], baseline["comments"])
        snapshot = read_wide_series_native_snapshot(
            op, sheet, graph, profile_id=profile_id, column_count=len(long_names)
        )
        _assert_snapshot(
            snapshot,
            profile_id=profile_id,
            long_names=long_names,
            comments=comments,
            row_count=cast(int, baseline["row_count"]),
            subgroup_size=cast(int, baseline["subgroup_size"]),
            designations=cast(tuple[int, ...], baseline["designations"]),
        )
        case_dir = output / profile_id / "baseline"
        _write_json(case_dir / "snapshot.json", snapshot)
        _export(graph, case_dir / "origin.png")
    finally:
        op.exit()


def run_render(
    profile_id: ProfileId,
    case_name: CaseName,
    install_dir: Path,
    output: Path,
) -> None:
    _assert_official_assets(profile_id, install_dir)
    document, actions, data = _case(profile_id, case_name)
    case_dir = output / profile_id / case_name
    project_path = case_dir / "origin.opju"
    op = _open_origin()
    try:
        project = WideSeriesOriginProject(op, profile_id=profile_id)
        project.create(install_dir, document, data)
        for action in actions:
            project.apply(document, action, data)
        project.save(project_path)
        snapshot = read_wide_series_native_snapshot(
            op,
            project.sheet,
            project.graph,
            profile_id=profile_id,
            column_count=len(data.columns),
        )
        _assert_snapshot(
            snapshot,
            profile_id=profile_id,
            long_names=tuple(column.field.name for column in data.columns),
            comments=("",) * len(data.columns),
            row_count=len(data.row_ids),
            subgroup_size=(
                2 if profile_id == "X40" else cast(int, snapshot["subgroup_size"])
            ),
        )
        manifest = {
            "profile_id": profile_id,
            "case_name": case_name,
            "project": str(project_path),
            "long_names": tuple(column.field.name for column in data.columns),
            "comments": ("",) * len(data.columns),
            "row_count": len(data.row_ids),
            "subgroup_size": cast(int, snapshot["subgroup_size"]),
            "render_snapshot": snapshot,
        }
        _write_json(case_dir / "manifest.json", manifest)
        _export(project.graph, case_dir / "render.png")
    finally:
        op.exit()


def run_fresh(profile_id: ProfileId, case_name: CaseName, output: Path) -> None:
    case_dir = output / profile_id / case_name
    manifest_path = case_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    project_path = Path(manifest["project"])
    op = _open_origin()
    try:
        op.new(asksave=False)
        if not op.open(str(project_path), readonly=True, asksave=False):
            raise RuntimeError(f"fresh session could not open {project_path}")
        graph, sheet = _pages(op)
        long_names = tuple(manifest["long_names"])
        comments = tuple(manifest["comments"])
        snapshot = read_wide_series_native_snapshot(
            op, sheet, graph, profile_id=profile_id, column_count=len(long_names)
        )
        _assert_snapshot(
            snapshot,
            profile_id=profile_id,
            long_names=long_names,
            comments=comments,
            row_count=int(manifest["row_count"]),
            subgroup_size=int(manifest["subgroup_size"]),
        )
        rendered = manifest["render_snapshot"]
        for field in (
            "connector_color",
            "connector_line_width",
            "connector_line_type",
            "member_colors",
            "member_symbol_kinds",
            "member_symbol_sizes",
        ):
            if _json_value(snapshot[field]) != rendered[field]:
                raise RuntimeError(f"fresh {profile_id} {case_name} changed {field}")
        _write_json(case_dir / "fresh-snapshot.json", snapshot)
        _export(graph, case_dir / "fresh.png")
    finally:
        op.exit()


def _selected(value: str) -> tuple[ProfileId, ...]:
    return ("X39", "X40") if value == "both" else (cast(ProfileId, value),)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("plan", "baseline", "default", "edited", "dynamic", "fresh"),
        default="plan",
    )
    parser.add_argument("--profile", choices=("X39", "X40", "both"), default="both")
    parser.add_argument("--case", choices=("default", "edited", "dynamic"))
    parser.add_argument("--install-dir", type=Path, default=DEFAULT_INSTALL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-origin-com", action="store_true")
    args = parser.parse_args()
    if args.phase == "plan":
        print(json.dumps(probe_plan(), ensure_ascii=False, indent=2))
        return
    if not args.allow_origin_com:
        parser.error("live phases require explicit --allow-origin-com")
    profiles = _selected(args.profile)
    if args.phase == "fresh":
        if args.case is None:
            parser.error("fresh requires --case default|edited|dynamic")
        for profile_id in profiles:
            run_fresh(profile_id, cast(CaseName, args.case), args.output)
        return
    for profile_id in profiles:
        if args.phase == "baseline":
            run_baseline(profile_id, args.install_dir, args.output)
        else:
            run_render(
                profile_id,
                cast(CaseName, args.phase),
                args.install_dir,
                args.output,
            )


if __name__ == "__main__":
    main()
