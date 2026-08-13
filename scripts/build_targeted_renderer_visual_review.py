"""Build current-source visual evidence for the four renderer changes.

The command renders Matplotlib and native Origin default/edited states for
K06, X13, X38 and X40. Origin previews are exported by a separate process so
the review proves a fresh application reopen rather than a same-session load.
"""

# ruff: noqa: E402,E501,I001 -- repository path setup and self-contained HTML.

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine import (  # noqa: E402
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
    PlotEngineAction,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.contracts import EngineScalar  # noqa: E402
from plotagent.engine.backends.matplotlib import (  # noqa: E402
    K06PointErrorRenderer,
    X13PopulationPyramidRenderer,
    X38OffsetStackRenderer,
    X40BeforeAfterRenderer,
)
from plotagent.engine.backends.matplotlib.backend import (  # noqa: E402
    MatplotlibProfileRenderer,
)
from plotagent.engine.backends.origin import (  # noqa: E402
    SubprocessOriginWorker,
    preflight_origin,
)
from plotagent.engine.backends.origin.messages import OriginWorkerRequest  # noqa: E402

OUTPUT = REPOSITORY / "build" / "visual-audit" / "renderer-rereview-4"
PROFILES = ("K06", "X13", "X38", "X40")


@dataclass(frozen=True, slots=True)
class ReviewCase:
    profile_id: str
    chinese_name: str
    official_name: str
    official_route: str
    document: PlotDocument
    actions: tuple[PlotEngineAction, ...]
    view: EngineDataView


def _column(
    field_id: str,
    name: str,
    logical_type: Literal["numeric", "categorical"],
    values: tuple[EngineScalar, ...],
) -> EngineColumn:
    return EngineColumn(
        field=EngineField(field_id=field_id, name=name, logical_type=logical_type),
        values=values,
    )


def _case(
    profile_id: str,
    roles: tuple[str, ...],
    columns: tuple[EngineColumn, ...],
    styles: tuple[tuple[str, dict[str, object]], ...],
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.rereview-{profile_id.lower()}",
        version=1,
        content_hash=sha256(profile_id.encode("ascii")).hexdigest(),
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=column.field.field_id)
        for role, column in zip(roles, columns, strict=True)
    )
    plot_id = f"plot:rereview-{profile_id.lower()}"
    create = CreatePlot(
        action_id=f"action:rereview-create-{profile_id.lower()}",
        plot_id=plot_id,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    actions: list[PlotEngineAction] = [create]
    for object_key, arguments in styles:
        actions.append(
            SetSeriesStyle(
                action_id=f"action:rereview-style-{profile_id.lower()}-{len(actions)}",
                target=f"series:rereview-{profile_id.lower()}.{object_key}",
                expected_plot_version=len(actions),
                color=arguments.get("color") if isinstance(arguments.get("color"), str) else None,
                line_width_pt=(
                    float(cast(float, arguments["line_width_pt"]))
                    if arguments.get("line_width_pt") is not None
                    else None
                ),
                line_style=cast(
                    Any,
                    arguments["line_style"]
                    if arguments.get("line_style") in {"solid", "dash", "dot", "dash_dot", "none"}
                    else None,
                ),
                symbol=cast(
                    Any,
                    str(arguments["symbol"]) if arguments.get("symbol") is not None else None,
                ),
                symbol_size_pt=(
                    float(cast(float, arguments["symbol_size_pt"]))
                    if arguments.get("symbol_size_pt") is not None
                    else None
                ),
            )
        )
    actions.append(
        SetLegend(
            action_id=f"action:rereview-legend-{profile_id.lower()}",
            target=f"legend:rereview-{profile_id.lower()}.main",
            expected_plot_version=len(actions),
            visible=True,
        )
    )
    document = PlotDocument(
        plot_id=plot_id,
        plot_version=len(actions),
        parent_version=len(actions) - 1,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:rereview-{index}" for index in range(len(columns[0].values))),
        columns=columns,
    )
    return document, tuple(actions), view


def _cases() -> tuple[ReviewCase, ...]:
    definitions: tuple[
        tuple[
            str,
            str,
            str,
            str,
            tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView],
        ],
        ...,
    ] = (
        (
            "K06",
            "双向误差棒图",
            "XY Error Bars",
            "X Y Error menu / ERRBAR.otpu",
            _case(
                "K06",
                ("x", "center", "x_lower", "x_upper", "lower", "upper"),
                (
                    _column("field:x", "Time", "numeric", (1.0, 2.0, 3.0, 4.0)),
                    _column("field:center", "Estimate", "numeric", (2.0, 3.0, 4.0, 3.5)),
                    _column("field:xl", "X lower", "numeric", (0.75, 1.8, 2.65, 3.7)),
                    _column("field:xu", "X upper", "numeric", (1.15, 2.35, 3.2, 4.4)),
                    _column("field:lower", "Y lower", "numeric", (1.55, 2.45, 3.65, 2.9)),
                    _column("field:upper", "Y upper", "numeric", (2.4, 3.65, 4.25, 4.2)),
                ),
                (
                    (
                        "primary",
                        {
                            "color": "#AA3300",
                            "line_width_pt": 2.0,
                            "symbol": "diamond",
                            "symbol_size_pt": 7.0,
                        },
                    ),
                ),
            ),
        ),
        (
            "X13",
            "人口金字塔",
            "Population Pyramid",
            "Plot.ogs [PopulationPyramid] / PopulationPyramid.otpu",
            _case(
                "X13",
                ("category", "left", "right"),
                (
                    _column(
                        "field:age",
                        "Age group",
                        "categorical",
                        ("0–9", "10–19", "20–29", "30–39", "40–49"),
                    ),
                    _column("field:left", "Male", "numeric", (10.0, 12.0, 9.0, 8.0, 6.0)),
                    _column("field:right", "Female", "numeric", (11.0, 13.0, 10.0, 9.0, 7.0)),
                ),
                (
                    ("left", {"color": "#2255AA", "line_width_pt": 1.2}),
                    ("right", {"color": "#CC6600", "line_width_pt": 1.2}),
                ),
            ),
        ),
        (
            "X38",
            "Y偏移堆叠线图",
            "Y Offset Stacked Lines",
            "Plot.ogs [OffsetYs] / OffsetStackY.otp",
            _case(
                "X38",
                ("x", "series_1", "series_2", "series_3"),
                (
                    _column("field:x", "Energy", "numeric", (1.0, 2.0, 3.0, 4.0, 5.0)),
                    _column("field:s1", "Spectrum 1", "numeric", (1.0, 2.5, 1.7, 3.0, 2.6)),
                    _column("field:s2", "Spectrum 2", "numeric", (2.0, 3.4, 2.5, 4.0, 3.6)),
                    _column("field:s3", "Spectrum 3", "numeric", (3.0, 4.2, 3.4, 5.0, 4.5)),
                ),
                (),
            ),
        ),
        (
            "X40",
            "前后对比图",
            "Before After",
            "Plot.ogs [BeforeAfter] / BeforeAfter.otpu",
            _case(
                "X40",
                ("series_1", "series_2", "label", "group"),
                (
                    _column(
                        "field:before",
                        "Before",
                        "numeric",
                        (10.0, 11.0, 12.0, 13.0, 14.0, 12.0, 11.0, 10.0, 13.0, 12.0, 14.0, 11.0),
                    ),
                    _column(
                        "field:after",
                        "After",
                        "numeric",
                        (11.0, 12.0, 13.5, 14.0, 15.0, 13.0, 12.0, 11.5, 14.0, 13.5, 15.5, 12.5),
                    ),
                    _column(
                        "field:subject",
                        "Subject",
                        "categorical",
                        tuple(f"P{index:02d}" for index in range(1, 13)),
                    ),
                    _column(
                        "field:group", "Group", "categorical", ("Control",) * 6 + ("Treatment",) * 6
                    ),
                ),
                (
                    ("connector", {"color": "#444444", "line_width_pt": 1.2}),
                    ("column_2", {"color": "#CC4A4A", "symbol": "diamond"}),
                ),
            ),
        ),
    )
    return tuple(
        ReviewCase(profile_id, chinese, official, route, *case)
        for profile_id, chinese, official, route, case in definitions
    )


RENDERERS: dict[str, MatplotlibProfileRenderer] = {
    "K06": K06PointErrorRenderer(),
    "X13": X13PopulationPyramidRenderer(),
    "X38": X38OffsetStackRenderer(),
    "X40": X40BeforeAfterRenderer(),
}


def _create(actions: tuple[PlotEngineAction, ...]) -> CreatePlot:
    action = actions[0]
    if not isinstance(action, CreatePlot):
        raise TypeError("visual review histories must begin with create_plot")
    return action


def _document(
    create: CreatePlot,
    actions: tuple[PlotEngineAction, ...],
) -> PlotDocument:
    version = len(actions)
    return PlotDocument(
        plot_id=create.plot_id,
        plot_version=version,
        parent_version=None if version == 1 else version - 1,
        profile_id=create.profile_id,
        data=create.data,
        bindings=create.bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )


def _states(
    case: ReviewCase,
) -> tuple[tuple[str, PlotDocument, tuple[PlotEngineAction, ...]], ...]:
    create = _create(case.actions)
    edited = (
        *case.actions,
        SetTitle(
            action_id=f"action:rereview-title-{case.profile_id.lower()}",
            target=create.plot_id,
            expected_plot_version=len(case.actions),
            text=f"{case.official_name} representative edit",
        ),
    )
    return (
        ("default", _document(create, (create,)), (create,)),
        ("edited", _document(create, edited), edited),
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _run_origin_history(
    worker: SubprocessOriginWorker,
    install_dir: Path,
    case: ReviewCase,
    state: str,
    actions: tuple[PlotEngineAction, ...],
) -> None:
    case_dir = OUTPUT / case.profile_id
    create = _create(actions)
    previous: Path | None = None
    response = None
    for version in range(1, len(actions) + 1):
        history = actions[:version]
        document = _document(create, history)
        target = (
            case_dir / f"origin-{state}.opju"
            if version == len(actions)
            else case_dir / f".origin-{state}-v{version}.opju"
        )
        if target.exists():
            target.unlink()
        response = worker.run(
            OriginWorkerRequest(
                install_dir=str(install_dir),
                output_opju=str(target),
                previous_opju=None if previous is None else str(previous),
                document=document,
                actions=history,
                source=EngineRenderSource(data=case.view),
            )
        )
        previous = target
    if response is None:
        raise RuntimeError(f"Origin produced no response for {case.profile_id} {state}")
    _write_json(
        case_dir / f"origin-{state}.readback.json",
        response.readback.model_dump(mode="json"),
    )


def _fresh_export(opju: Path, target: Path) -> None:
    subprocess.run(
        (
            str(REPOSITORY / ".venv" / "Scripts" / "python.exe"),
            str(REPOSITORY / "build" / "export_one_origin_graph.py"),
            str(opju),
            str(target),
        ),
        cwd=REPOSITORY,
        check=True,
    )


def _render(cases: tuple[ReviewCase, ...]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    probe = preflight_origin(OUTPUT / "origin-preflight.opju")
    if probe.status != "ready":
        raise RuntimeError(probe.error.message)
    install_dir = Path(probe.environment.install_dir)
    worker = SubprocessOriginWorker(timeout_seconds=900)
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/4] {case.profile_id} {case.chinese_name}", flush=True)
        case_dir = OUTPUT / case.profile_id
        case_dir.mkdir(parents=True, exist_ok=True)
        _write_json(case_dir / "data-view.json", case.view.model_dump(mode="json"))
        for state, document, actions in _states(case):
            readback = RENDERERS[case.profile_id].render(
                document,
                actions,
                case.view,
                case_dir / f"matplotlib-{state}.png",
                case_dir / f"matplotlib-{state}.svg",
            )
            _write_json(
                case_dir / f"matplotlib-{state}.readback.json",
                readback.model_dump(mode="json"),
            )
            _run_origin_history(worker, install_dir, case, state, actions)
            _fresh_export(
                case_dir / f"origin-{state}.opju",
                case_dir / f"origin-{state}-fresh.png",
            )


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _build_index(cases: tuple[ReviewCase, ...], *, approved: bool) -> None:
    status = "PASS" if approved else "PENDING"
    rows: list[dict[str, Any]] = []
    cards: list[str] = []
    for case in cases:
        case_dir = OUTPUT / case.profile_id
        images = tuple(
            (label, case_dir / filename)
            for label, filename in (
                ("Matplotlib 默认态", "matplotlib-default.png"),
                ("Origin 官方模板默认态（独立 fresh reopen）", "origin-default-fresh.png"),
                ("Matplotlib 代表编辑态", "matplotlib-edited.png"),
                ("Origin 原生代表编辑态（独立 fresh reopen）", "origin-edited-fresh.png"),
            )
        )
        opjus = (case_dir / "origin-default.opju", case_dir / "origin-edited.opju")
        for _label, path in images:
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"missing visual review image: {path}")
        for path in opjus:
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"missing visual review OPJU: {path}")
        panels = "".join(
            f"<figure><figcaption>{html.escape(label)}</figcaption>"
            f'<a href="{path.resolve().as_uri()}"><img src="{path.resolve().as_uri()}" '
            f'alt="{html.escape(case.chinese_name)} {html.escape(label)}"></a></figure>'
            for label, path in images
        )
        cards.append(
            f'<article id="{case.profile_id}"><header><h2>{case.profile_id} '
            f"{html.escape(case.chinese_name)}｜{html.escape(case.official_name)}</h2>"
            f"<span>{status}</span></header><p><b>官方路线：</b>{html.escape(case.official_route)}</p>"
            f'<p><a href="{opjus[0].resolve().as_uri()}">默认 OPJU</a>　'
            f'<a href="{opjus[1].resolve().as_uri()}">编辑 OPJU</a></p>'
            f'<div class="grid">{panels}</div></article>'
        )
        rows.append(
            {
                "profile_id": case.profile_id,
                "chinese_name": case.chinese_name,
                "official_name": case.official_name,
                "official_route": case.official_route,
                "visual_status": status,
                "artifacts": {
                    path.name: {"size": path.stat().st_size, "sha256": _sha(path)}
                    for path in (*[item[1] for item in images], *opjus)
                },
            }
        )
    commit = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=REPOSITORY, text=True
    ).strip()
    _write_json(
        OUTPUT / "review-manifest.json",
        {
            "schema_version": "plotagent.renderer-rereview.v1",
            "source_commit": commit,
            "profiles": list(PROFILES),
            "review_status": status,
            "reviewed_by": "Codex visual inspection" if approved else None,
            "cases": rows,
        },
    )
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>4图当前renderer复审</title>
<style>body{{margin:0;background:#f4f6f8;color:#17202a;font:14px/1.5 "Microsoft YaHei UI",sans-serif}}main{{max-width:1600px;margin:auto;padding:24px}}.intro,article{{background:white;border:1px solid #dce1e6;border-radius:12px;padding:20px;margin-bottom:18px}}header{{display:flex;justify-content:space-between;align-items:center}}h1,h2{{margin:0}}header span{{color:{"#127a48" if approved else "#8a5a00"};font-weight:700}}a{{color:#145c9e}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}figure{{margin:0;border:1px solid #dce1e6;border-radius:8px;overflow:hidden}}figcaption{{padding:8px;background:#f7f8fa;font-weight:600}}img{{display:block;width:100%;height:500px;object-fit:contain}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}img{{height:auto}}}}</style></head>
<body><main><section class="intro"><h1>当前renderer四图复审</h1><p>源码提交：{commit}</p><p>判定：{status}。四图均重新生成Matplotlib/Origin默认态、代表编辑态和独立fresh-reopen证据。</p></section>{"".join(cards)}</main></body></html>"""
    (OUTPUT / "index.html").write_text(page, encoding="utf-8")
    print(OUTPUT / "index.html")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="reuse rendered artifacts and rebuild only the audit page/manifest",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="record approval after the generated images have been inspected",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=PROFILES,
        help="render only the named profiles while retaining the complete review index",
    )
    args = parser.parse_args()
    cases = _cases()
    if tuple(case.profile_id for case in cases) != PROFILES:
        raise RuntimeError("targeted visual review inventory drifted")
    if not args.index_only:
        selected = (
            cases
            if args.profiles is None
            else tuple(case for case in cases if case.profile_id in set(args.profiles))
        )
        _render(selected)
    _build_index(cases, approved=args.approve)


if __name__ == "__main__":
    main()
