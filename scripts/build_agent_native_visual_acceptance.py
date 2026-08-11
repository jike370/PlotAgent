"""Build the single visual-acceptance surface for the Agent Native engine.

The audit fixtures come from the current engine test cases.  They are not old
PlotSpec fixtures and they never call the retired compiler.  Every normal case
is rendered twice by the independent Matplotlib renderer and, when requested,
twice by the official-template Origin binder.  K25 composes two immutable K01
children through the public component contract.
"""

# ruff: noqa: E402,E501,I001,PLC2701

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine import (  # noqa: E402
    CreatePlot,
    EngineComponentInput,
    EngineDataView,
    EngineRenderSource,
    PlotDocument,
    PlotEngineAction,
    SetTitle,
)
from plotagent.engine.backends.matplotlib import (  # noqa: E402
    K01LineRenderer,
    K02LineSymbolRenderer,
    K03ScatterRenderer,
    K04BubbleRenderer,
    K06PointErrorRenderer,
    K07ErrorBandRenderer,
    K08ColumnRenderer,
    K09GroupedColumnRenderer,
    K10StackedColumnRenderer,
    K11PercentStackRenderer,
    K12StripRenderer,
    K13BoxRenderer,
    K14ViolinRenderer,
    K15HistogramRenderer,
    K16DensityRenderer,
    K18AreaRenderer,
    K19TimeSeriesRenderer,
    K20HeatmapRenderer,
    K21CorrelationMatrixRenderer,
    K22ContourRenderer,
    K24FacetRenderer,
    K25CompositeRenderer,
    S01SurvivalRenderer,
    S21ForestRenderer,
    S34NyquistRenderer,
    S61ConfusionRenderer,
    X02DropLineRenderer,
    X03LollipopRenderer,
    X05BeeswarmRenderer,
    X09FloatingIntervalRenderer,
    X13PopulationPyramidRenderer,
    X23DualYRenderer,
    X24ParetoRenderer,
    X35DualYColumnRenderer,
    X36DualYColumnLineRenderer,
    X38OffsetStackRenderer,
    X39LineSeriesRenderer,
    X40BeforeAfterRenderer,
)
from plotagent.engine.backends.matplotlib.backend import (  # noqa: E402
    MatplotlibComponentArtifact,
)
from plotagent.engine.backends.origin import (  # noqa: E402
    SubprocessOriginWorker,
    preflight_origin,
)
from plotagent.engine.backends.origin.messages import (  # noqa: E402
    OriginWorkerRequest,
    OriginWorkerResponse,
)
from plotagent.engine.backends.origin import profile as origin_profiles  # noqa: E402
from plotagent.engine.profiles import ENGINE_PROFILES  # noqa: E402
from plotagent.engine.repository import document_ref  # noqa: E402

from tests.engine import test_column_family_profiles as column_cases  # noqa: E402
from tests.engine import test_k03_dynamic_profile as k03_cases  # noqa: E402
from tests.engine import test_k04_bubble_profile as k04_cases  # noqa: E402
from tests.engine import test_k08_matplotlib_backend as k08_cases  # noqa: E402
from tests.engine import test_k15_k16_calculated_distributions as calculated_cases  # noqa: E402
from tests.engine import test_k19_k21_k22_profiles as matrix_cases  # noqa: E402
from tests.engine import test_k20_origin_backend as k20_cases  # noqa: E402
from tests.engine import test_k25_composite_profile as k25_cases  # noqa: E402
from tests.engine import test_remaining_t1_special_profiles as special_cases  # noqa: E402
from tests.engine import test_t1_family_matplotlib_backends as t1_cases  # noqa: E402
from tests.engine import test_t2_non_composite_profiles as t2_cases  # noqa: E402
from tests.engine import test_x03_x39_x40_wide_series as wide_cases  # noqa: E402
from tests.engine import test_x05_x09_x13_profiles as x_cases  # noqa: E402
from tests.engine import test_x23_matplotlib_backend as x23_cases  # noqa: E402

OUTPUT = REPOSITORY / "build" / "visual-audit" / "agent-native-38"


@dataclass(frozen=True, slots=True)
class AuditCase:
    profile_id: str
    document: PlotDocument
    actions: tuple[PlotEngineAction, ...]
    view: EngineDataView


@dataclass(frozen=True, slots=True)
class _ComponentArtifact(MatplotlibComponentArtifact):
    component: EngineComponentInput
    png_path: Path
    svg_path: Path


def _document_for(create: CreatePlot) -> PlotDocument:
    return PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id=create.profile_id,
        data=create.data,
        bindings=create.bindings,
        components=create.components,
        applied_action_ids=(create.action_id,),
    )


def _provider_case(
    create: CreatePlot,
    provider: Any,
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    if create.data is None:
        raise ValueError("audit provider case must be data-backed")
    field_ids = tuple(binding.field_id for binding in create.bindings)
    materialize = provider.materialize
    view = materialize(create.data, field_ids)
    return _document_for(create), (create,), view


def _cases() -> tuple[AuditCase, ...]:
    factories: dict[str, Callable[[], tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]]] = {
        "K01": lambda: _provider_case(k25_cases._child_action("acceptance", "a" * 64), _K01Provider()),
        "K02": lambda: t1_cases._case(
            "K02",
            ("x", "y"),
            (
                t1_cases._column("field:x", "Time", (0.0, 1.0, 2.0, 3.0)),
                t1_cases._column("field:y", "Signal", (1.0, 2.2, 1.8, 3.4)),
            ),
        ),
        "K03": lambda: k03_cases._case(("Control", "Low", "Control", "High", "Low")),
        "K04": lambda: k04_cases._case(scales=True, edits=True),
        "K06": lambda: t1_cases._case(
            "K06",
            ("x", "center", "x_error", "y_error"),
            (
                t1_cases._column("field:x", "Time", (1.0, 2.0, 3.0)),
                t1_cases._column("field:center", "Estimate", (2.0, 3.0, 4.0)),
                t1_cases._column("field:xerr", "X error", (0.1, 0.2, 0.1)),
                t1_cases._column("field:yerr", "Y error", (0.3, 0.4, 0.2)),
            ),
        ),
        "K07": lambda: t1_cases._case(
            "K07",
            ("x", "center", "lower", "upper"),
            (
                t1_cases._column("field:x", "Dose", (0.0, 1.0, 2.0, 3.0)),
                t1_cases._column("field:center", "Response", (2.0, 3.0, 4.0, 4.5)),
                t1_cases._column("field:lower", "Lower", (1.5, 2.5, 3.0, 3.8)),
                t1_cases._column("field:upper", "Upper", (2.5, 3.7, 5.0, 5.2)),
            ),
        ),
        "K08": lambda: _provider_case(k08_cases._create(), k08_cases.Provider()),
        "K09": lambda: column_cases._case("K09", 3),
        "K10": lambda: column_cases._case("K10", 3),
        "K11": lambda: column_cases._case("K11", 3),
        "K12": lambda: column_cases._distribution_case("K12", 3),
        "K13": lambda: column_cases._distribution_case("K13", 3),
        "K14": lambda: column_cases._distribution_case("K14", 3),
        "K15": lambda: calculated_cases._case("K15"),
        "K16": lambda: calculated_cases._case("K16", grouped=True),
        "K18": lambda: t1_cases._case(
            "K18",
            ("x", "y"),
            (
                t1_cases._column("field:x", "Time", (0.0, 1.0, 2.0, 3.0)),
                t1_cases._column("field:y", "Amount", (1.0, 3.0, 2.4, 3.6)),
            ),
        ),
        "K19": matrix_cases._k19_case,
        "K20": k20_cases._case,
        "K21": matrix_cases._k21_case,
        "K22": matrix_cases._k22_case,
        "K24": t2_cases._k24_case,
        "S01": t2_cases._s01_case,
        "S21": t2_cases._s21_case,
        "S34": t2_cases._s34_case,
        "S61": t2_cases._s61_case,
        "X02": lambda: t1_cases._case(
            "X02",
            ("x", "y"),
            (
                t1_cases._column("field:x", "Position", (0.0, 1.0, 2.0, 3.0)),
                t1_cases._column("field:y", "Signal", (-1.0, 3.0, 1.5, -0.5)),
            ),
        ),
        "X03": lambda: wide_cases._case("X03", series_count=4, row_count=5),
        "X05": x_cases._x05_case,
        "X09": x_cases._x09_case,
        "X13": x_cases._x13_case,
        "X23": lambda: _provider_case(x23_cases._create(), x23_cases.Provider()),
        "X24": special_cases._x24_case,
        "X35": lambda: special_cases._dual_case("X35"),
        "X36": lambda: special_cases._dual_case("X36"),
        "X38": special_cases._x38_case,
        "X39": lambda: wide_cases._case("X39", series_count=4, row_count=5),
        "X40": lambda: wide_cases._case("X40", series_count=2, row_count=6),
    }
    expected = tuple(profile.profile_id for profile in ENGINE_PROFILES if profile.profile_id != "K25")
    if set(factories) != set(expected):
        raise RuntimeError(f"audit case inventory differs: {sorted(set(expected) ^ set(factories))}")
    return tuple(AuditCase(profile_id, *factories[profile_id]()) for profile_id in expected)


class _K01Provider:
    def materialize(self, data, field_ids):
        action = k25_cases._child_action("acceptance", "a" * 64)
        view = k25_cases._view(action)
        columns = {column.field.field_id: column for column in view.columns}
        return view.model_copy(update={"data": data, "columns": tuple(columns[item] for item in field_ids)})


RENDERERS = {
    renderer.profile_id: renderer
    for renderer in (
        K01LineRenderer(), K02LineSymbolRenderer(), K03ScatterRenderer(), K04BubbleRenderer(),
        K06PointErrorRenderer(), K07ErrorBandRenderer(), K08ColumnRenderer(),
        K09GroupedColumnRenderer(), K10StackedColumnRenderer(), K11PercentStackRenderer(),
        K12StripRenderer(), K13BoxRenderer(), K14ViolinRenderer(), K15HistogramRenderer(),
        K16DensityRenderer(), K18AreaRenderer(), K19TimeSeriesRenderer(), K20HeatmapRenderer(),
        K21CorrelationMatrixRenderer(), K22ContourRenderer(), K24FacetRenderer(),
        S01SurvivalRenderer(), S21ForestRenderer(), S34NyquistRenderer(),
        S61ConfusionRenderer(), X02DropLineRenderer(), X03LollipopRenderer(),
        X05BeeswarmRenderer(), X09FloatingIntervalRenderer(), X13PopulationPyramidRenderer(),
        X23DualYRenderer(), X24ParetoRenderer(), X35DualYColumnRenderer(),
        X36DualYColumnLineRenderer(), X38OffsetStackRenderer(), X39LineSeriesRenderer(),
        X40BeforeAfterRenderer(),
    )
}


def _state(case: AuditCase, edited: bool) -> tuple[PlotDocument, tuple[PlotEngineAction, ...]]:
    create = case.actions[0]
    if not isinstance(create, CreatePlot):
        raise TypeError("audit histories must begin with create_plot")
    actions = case.actions if edited else (create,)
    if edited and not any(action.operation == "set_title" for action in actions):
        actions = (*actions, SetTitle(
            action_id=f"action:acceptance-title-{case.profile_id.lower()}",
            target=create.plot_id,
            expected_plot_version=len(actions),
            text=f"{case.profile_id} representative edit",
        ))
    return _document_from_history(create, tuple(actions)), tuple(actions)


def _document_from_history(
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
        components=create.components,
        applied_action_ids=tuple(action.action_id for action in actions),
    )


def _create_from(actions: tuple[PlotEngineAction, ...]) -> CreatePlot:
    create = actions[0]
    if not isinstance(create, CreatePlot):
        raise TypeError("audit histories must begin with create_plot")
    return create


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _render_matplotlib(cases: tuple[AuditCase, ...]) -> None:
    for case in cases:
        renderer = RENDERERS[case.profile_id]
        case_dir = OUTPUT / case.profile_id
        case_dir.mkdir(parents=True, exist_ok=True)
        _write_json(case_dir / "data-view.json", case.view.model_dump(mode="json"))
        for edited, name in ((False, "default"), (True, "edited")):
            document, actions = _state(case, edited)
            readback = renderer.render(
                document,
                actions,
                case.view,
                case_dir / f"matplotlib-{name}.png",
                case_dir / f"matplotlib-{name}.svg",
            )
            _write_json(case_dir / f"matplotlib-{name}-readback.json", readback.model_dump(mode="json"))
    _render_k25_matplotlib()


def _k25_inputs() -> tuple[
    tuple[EngineComponentInput, ...], tuple[_ComponentArtifact, ...], PlotDocument, tuple[PlotEngineAction, ...]
]:
    components: list[EngineComponentInput] = []
    artifacts: list[_ComponentArtifact] = []
    for suffix, color in (("first", "b" * 64), ("second", "c" * 64)):
        action = k25_cases._child_action(suffix, color)
        document = k25_cases._child_document(action)
        view = k25_cases._view(action)
        component = EngineComponentInput(document=document, actions=(action,), data=view)
        target = OUTPUT / "K25" / "components" / suffix
        K01LineRenderer().render(document, (action,), view, target / "preview.png", target / "preview.svg")
        components.append(component)
        artifacts.append(_ComponentArtifact(component, target / "preview.png", target / "preview.svg"))
    create = k25_cases._create_composite(tuple(document_ref(item.document) for item in components))
    edit = SetTitle(
        action_id="action:acceptance-title-k25",
        target=create.plot_id,
        expected_plot_version=1,
        text="K25 representative edit",
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=2,
        parent_version=1,
        profile_id="K25",
        components=create.components,
        applied_action_ids=(create.action_id, edit.action_id),
    )
    return tuple(components), tuple(artifacts), document, (create, edit)


def _render_k25_matplotlib() -> None:
    components, artifacts, edited_document, actions = _k25_inputs()
    case_dir = OUTPUT / "K25"
    renderer = K25CompositeRenderer()
    create = _create_from(actions)
    default_document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id="K25",
        components=create.components,
        applied_action_ids=(create.action_id,),
    )
    for document, history, name in (
        (default_document, (create,), "default"),
        (edited_document, actions, "edited"),
    ):
        readback = renderer.render(
            document, history, artifacts,
            case_dir / f"matplotlib-{name}.png", case_dir / f"matplotlib-{name}.svg",
        )
        _write_json(case_dir / f"matplotlib-{name}-readback.json", readback.model_dump(mode="json"))
    _write_json(
        case_dir / "data-view.json",
        {"components": [item.model_dump(mode="json") for item in components]},
    )


def _run_origin_request(
    worker: SubprocessOriginWorker,
    install_dir: Path,
    output: Path,
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
    source: EngineRenderSource,
    *,
    previous: Path | None = None,
    component_opjus: tuple[Path, ...] = (),
) -> OriginWorkerResponse:
    if output.exists():
        output.unlink()
    response = worker.run(OriginWorkerRequest(
        install_dir=str(install_dir),
        output_opju=str(output),
        previous_opju=None if previous is None else str(previous),
        document=document,
        actions=actions,
        source=source,
        component_opjus=tuple(str(path) for path in component_opjus),
    ))
    if not output.is_file():
        raise RuntimeError(f"Origin did not create {output}")
    return response


def _render_origin(cases: tuple[AuditCase, ...], *, resume: bool = False) -> None:
    probe = preflight_origin(OUTPUT / "origin-preflight.opju")
    if probe.status != "ready":
        raise RuntimeError(probe.error.message)
    install_dir = Path(probe.environment.install_dir)
    worker = SubprocessOriginWorker(timeout_seconds=900)
    for index, case in enumerate(cases, start=1):
        case_dir = OUTPUT / case.profile_id
        required = (
            case_dir / "origin-default.opju",
            case_dir / "origin-edited.opju",
            case_dir / "origin-default-readback.json",
            case_dir / "origin-edited-readback.json",
        )
        if resume and all(path.is_file() for path in required):
            print(f"[{index:02d}/38] Origin {case.profile_id} · resume skip", flush=True)
            continue
        print(f"[{index:02d}/38] Origin {case.profile_id}", flush=True)
        default_document, default_actions = _state(case, False)
        _edited_document, edited_actions = _state(case, True)
        default = case_dir / "origin-default.opju"
        response = _run_origin_request(
            worker, install_dir, default, default_document, default_actions,
            EngineRenderSource(data=case.view),
        )
        _write_json(case_dir / "origin-default-readback.json", response.readback.model_dump(mode="json"))
        previous = default
        create = _create_from(edited_actions)
        for version in range(2, len(edited_actions) + 1):
            history = edited_actions[:version]
            document = _document_from_history(create, history)
            target = (
                case_dir / "origin-edited.opju"
                if version == len(edited_actions)
                else case_dir / f".origin-v{version}.opju"
            )
            response = _run_origin_request(
                worker, install_dir, target, document, history,
                EngineRenderSource(data=case.view), previous=previous,
            )
            previous = target
        _write_json(case_dir / "origin-edited-readback.json", response.readback.model_dump(mode="json"))
    k25_dir = OUTPUT / "K25"
    k25_required = (
        k25_dir / "origin-default.opju",
        k25_dir / "origin-edited.opju",
        k25_dir / "origin-default-readback.json",
        k25_dir / "origin-edited-readback.json",
    )
    if resume and all(path.is_file() for path in k25_required):
        print("[38/38] Origin K25 · resume skip", flush=True)
    else:
        print("[38/38] Origin K25", flush=True)
        _render_k25_origin(worker, install_dir)
    _export_origin_previews((*cases,))


def _render_k25_origin(worker: SubprocessOriginWorker, install_dir: Path) -> None:
    components, _artifacts, edited_document, actions = _k25_inputs()
    case_dir = OUTPUT / "K25"
    child_opjus: list[Path] = []
    for component in components:
        child_path = case_dir / "components" / f"{component.document.plot_id.removeprefix('plot:')}.opju"
        _run_origin_request(
            worker, install_dir, child_path, component.document, component.actions,
            EngineRenderSource(data=component.data),
        )
        child_opjus.append(child_path)
    create = _create_from(actions)
    default_document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id="K25",
        components=create.components,
        applied_action_ids=(create.action_id,),
    )
    source = EngineRenderSource(components=components)
    default = case_dir / "origin-default.opju"
    response = _run_origin_request(
        worker, install_dir, default, default_document, (create,), source,
        component_opjus=tuple(child_opjus),
    )
    _write_json(case_dir / "origin-default-readback.json", response.readback.model_dump(mode="json"))
    response = _run_origin_request(
        worker, install_dir, case_dir / "origin-edited.opju", edited_document, actions, source,
        previous=default, component_opjus=tuple(child_opjus),
    )
    _write_json(case_dir / "origin-edited-readback.json", response.readback.model_dump(mode="json"))


def _export_origin_previews(cases: tuple[AuditCase, ...]) -> None:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        for profile_id in (*[case.profile_id for case in cases], "K25"):
            case_dir = OUTPUT / profile_id
            for name in ("default", "edited"):
                op.new(asksave=False)
                source = case_dir / f"origin-{name}.opju"
                if not op.open(str(source), readonly=True, asksave=False):
                    raise RuntimeError(f"could not fresh-reopen {source}")
                graphs = list(op.pages("g"))
                if not graphs:
                    raise RuntimeError(f"fresh-reopened {profile_id} has no graph")
                graphs[-1].save_fig(
                    str(case_dir / f"origin-{name}.png"), type="png", replace=True, width=1600,
                )
    finally:
        op.exit()


def _manifest() -> dict[str, Any]:
    profile_map = {profile.profile_id: profile for profile in ENGINE_PROFILES}
    templates = {
        profile_id: getattr(origin_profiles, f"{profile_id}_ORIGIN_PROFILE")
        for profile_id in profile_map
    }
    entries: list[dict[str, object]] = []
    for profile_id in profile_map:
        case_dir = OUTPUT / profile_id
        files = {
            name: case_dir / name
            for name in (
                "matplotlib-default.png", "matplotlib-edited.png",
                "origin-default.png", "origin-edited.png",
                "origin-default.opju", "origin-edited.opju",
                "matplotlib-default-readback.json", "matplotlib-edited-readback.json",
                "origin-default-readback.json", "origin-edited-readback.json",
            )
        }
        missing = [name for name, path in files.items() if not path.is_file()]
        template = templates[profile_id]
        entries.append({
            "profile_id": profile_id,
            "display_name": profile_map[profile_id].display_name,
            "template": template.model_dump(mode="json"),
            "origin_construction": (
                "native_merge" if profile_id == "K25" else "official_template"
            ),
            "mechanical_status": "PASS" if not missing else "INCOMPLETE",
            "visual_status": "UNVERIFIED",
            "missing": missing,
            "artifacts": {
                name: {"path": str(path), "sha256": _sha(path), "size": path.stat().st_size}
                for name, path in files.items() if path.is_file()
            },
        })
    return {
        "schema_version": "agent-native-visual.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_commit": subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=REPOSITORY, text=True
        ).strip(),
        "scope": "38 formal Agent Native profiles; 37 official Origin templates plus K25 native merge; default and representative edit",
        "summary": {
            "profile_count": len(entries),
            "mechanical_pass": sum(item["mechanical_status"] == "PASS" for item in entries),
            "visual_unverified": len(entries),
        },
        "profiles": entries,
    }


def _index(manifest: dict[str, Any]) -> None:
    _contact_sheet(manifest, "default")
    _contact_sheet(manifest, "edited")
    cards: list[str] = []
    for entry in manifest["profiles"]:  # type: ignore[index]
        profile_id = entry["profile_id"]
        template = entry["template"]
        origin_caption = (
            "Origin 原生合并"
            if entry["origin_construction"] == "native_merge"
            else "Origin 官方模板"
        )
        figures = "".join(
            f'<figure><figcaption>{html.escape(caption)}</figcaption>'
            f'<a href="{profile_id}/{filename}"><img loading="lazy" src="{profile_id}/{filename}"></a></figure>'
            for filename, caption in (
                ("matplotlib-default.png", "Matplotlib · 默认态"),
                ("origin-default.png", f"{origin_caption} · 默认态"),
                ("matplotlib-edited.png", "Matplotlib · 代表编辑态"),
                ("origin-edited.png", f"{origin_caption} · 代表编辑态"),
            )
        )
        cards.append(f'''<article id="{profile_id}"><header><div><b>{profile_id}</b> {html.escape(str(entry['display_name']))}</div><span>UNVERIFIED</span></header>
<p>Origin 图族资产：<code>{html.escape(str(template['filename']))}</code> · {template['tier']} · {origin_caption}</p>
<div class="figures">{figures}</div>
<footer><a href="{profile_id}/origin-default.opju">默认 OPJU</a><a href="{profile_id}/origin-edited.opju">编辑 OPJU</a><a href="{profile_id}/data-view.json">数据</a><a href="{profile_id}/origin-edited-readback.json">Origin 读回</a></footer></article>''')
    content = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PlotAgent Agent Native · 38 图视觉验收</title><style>
:root{{--bg:#f4f4f2;--card:#fff;--line:#d8d8d3;--text:#171715;--muted:#676761;--accent:#0a6847}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 "Microsoft YaHei UI",sans-serif}}main{{max-width:1680px;margin:auto;padding:32px}}h1{{font-size:28px;margin:0 0 8px}}.intro{{color:var(--muted);max-width:920px;margin:0 0 24px}}nav{{position:sticky;top:0;background:rgba(244,244,242,.95);padding:12px 0;z-index:2;display:flex;gap:8px;flex-wrap:wrap}}nav a{{color:var(--text);text-decoration:none;border:1px solid var(--line);background:white;padding:4px 8px;border-radius:6px}}article{{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:0 0 22px;overflow:hidden}}article header{{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;font-size:17px}}article header span{{color:#865a00;font-size:12px}}article p{{padding:0 18px;color:var(--muted)}}.figures{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--line)}}figure{{margin:0;background:#fff;padding:12px}}figcaption{{font-weight:600;margin-bottom:8px}}img{{display:block;width:100%;height:420px;object-fit:contain;background:#fff}}footer{{display:flex;gap:16px;padding:12px 18px}}footer a{{color:var(--accent)}}code{{font-family:Consolas,monospace}}@media(max-width:900px){{.figures{{grid-template-columns:1fr}}img{{height:auto}}main{{padding:16px}}}}</style></head><body><main>
<h1>PlotAgent Agent Native · 38 图视觉验收</h1><p class="intro">这是新引擎的唯一视觉验收面。37 张数据图直接使用对应 Origin 官方模板；K25 使用 Origin 原生图页合并。每张图并列展示 Matplotlib 与 Origin 的默认态、代表编辑态。机械通过不等于视觉通过；请按图审查后记录结论。当前机械读回 38/38，视觉结论 0/38，全部保持 UNVERIFIED。</p>
<p class="intro"><a href="origin-default-contact-sheet.png">Origin 默认态总览</a> · <a href="origin-edited-contact-sheet.png">Origin 代表编辑态总览</a> · <a href="manifest.json">机械清单</a></p>
<nav>{''.join(f'<a href="#{item["profile_id"]}">{item["profile_id"]}</a>' for item in manifest['profiles'])}</nav>{''.join(cards)}</main></body></html>'''
    (OUTPUT / "index.html").write_text(content, encoding="utf-8")


def _contact_sheet(manifest: dict[str, Any], state: str) -> None:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    entries = manifest["profiles"]
    columns = 4
    cell_width, cell_height = 390, 320
    rows = (len(entries) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("arial.ttf", 22)
    for index, entry in enumerate(entries):
        profile_id = entry["profile_id"]
        source = OUTPUT / profile_id / f"origin-{state}.png"
        with Image.open(source) as raw:
            preview = ImageOps.contain(raw.convert("RGB"), (370, 275))
        x = (index % columns) * cell_width + (cell_width - preview.width) // 2
        y = (index // columns) * cell_height + 34
        sheet.paste(preview, (x, y))
        draw.text(((index % columns) * cell_width + 12, (index // columns) * cell_height + 6), profile_id, fill="black", font=font)
    sheet.save(OUTPUT / f"origin-{state}-contact-sheet.png", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("all", "matplotlib", "origin", "index"), default="all")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.force and OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases = _cases()
    if len(cases) != 37:
        raise RuntimeError(f"expected 37 data profiles plus K25, got {len(cases)}")
    if args.phase in {"all", "matplotlib"}:
        _render_matplotlib(cases)
    if args.phase in {"all", "origin"}:
        _render_origin(cases, resume=args.resume)
    if args.phase in {"all", "index"}:
        manifest = _manifest()
        _write_json(OUTPUT / "manifest.json", manifest)
        _index(manifest)
        if manifest["summary"]["mechanical_pass"] != 38:  # type: ignore[index]
            raise RuntimeError("visual acceptance is incomplete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
