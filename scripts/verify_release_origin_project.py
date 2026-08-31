"""Fresh-process verifier for one representative release-matrix OPJU."""

from __future__ import annotations

import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine.backends.origin.dual_y_special import (  # noqa: E402
    DualYSpecialOriginProject,
)
from plotagent.engine.backends.origin.k04 import K04OriginProject  # noqa: E402
from plotagent.engine.backends.origin.k07 import K07OriginProject  # noqa: E402
from plotagent.engine.backends.origin.distribution import (  # noqa: E402
    DistributionOriginProject,
)
from plotagent.engine.backends.origin.messages import OriginWorkerRequest  # noqa: E402
from plotagent.engine.backends.origin.native_visual_t1 import (  # noqa: E402
    K14ViolinStyleState,
)
from plotagent.engine.backends.origin.s34 import (  # noqa: E402
    s34_equal_axes_enabled,
    verify_s34_equal_scale_layout,
)
from plotagent.engine.backends.origin.visual_t1 import (  # noqa: E402
    _verify_actions,
    _verify_k14_product_style,
)
from plotagent.engine.backends.origin.x09 import X09OriginProject  # noqa: E402
from plotagent.engine.contracts import CreatePlot, SetSeriesStyle  # noqa: E402
from plotagent.engine.product_style import K14_VIOLIN_STYLE  # noqa: E402
from plotagent.engine.visual_t1 import (  # noqa: E402
    effective_visual_actions,
    product_default_visual_actions,
    split_visual_actions,
)
from scripts.origin_standalone_export import export_origin_png_standalone  # noqa: E402


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _k14_default_styles(op: object, plot_count: int) -> tuple[K14ViolinStyleState, ...]:
    color = getattr(op, "lt_float")
    return tuple(
        K14ViolinStyleState(
            fill_color=int(
                color(
                    f'color("{K14_VIOLIN_STYLE.palette[index % len(K14_VIOLIN_STYLE.palette)]}")'
                )
            ),
            fill_transparency=(1 - K14_VIOLIN_STYLE.fill_opacity) * 100,
            fill_only=1,
            follow_line_transparency=0,
            outline_color=int(color(f'color("{K14_VIOLIN_STYLE.outline_color}")')),
            outline_width=K14_VIOLIN_STYLE.outline_width_pt,
            outline_style=0,
        )
        for index in range(plot_count)
    )


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: verify_release_origin_project REQUEST_JSON OPJU PNG RESULT_JSON")
    request_path, opju_path, png_path, result_path = (
        Path(value).resolve() for value in sys.argv[1:]
    )
    request = OriginWorkerRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    structural, visual = split_visual_actions(
        tuple(action for action in request.actions if not isinstance(action, CreatePlot))
    )
    effective_visual = effective_visual_actions(
        (*product_default_visual_actions(request.document), *visual)
    )
    if not effective_visual and request.document.profile_id not in {"K04", "K14", "X09"}:
        raise RuntimeError(
            "fresh structural-only release verification is not registered for "
            f"{request.document.profile_id}"
        )

    import originpro as op  # type: ignore[import-untyped]  # noqa: PLC0415

    op.set_show(False)
    result: dict[str, object] | None = None
    try:
        structural_snapshot: dict[str, object] | None = None
        k07_axis_snapshot: dict[str, list[float]] | None = None
        k14_defaults: tuple[K14ViolinStyleState, ...] | None = None
        dual_y_native_snapshot: dict[str, object] | None = None
        dual_y_default_color_snapshot: dict[str, object] | None = None
        if effective_visual:
            if request.document.profile_id in {"X35", "X36"}:
                dual_y_project = DualYSpecialOriginProject(
                    op,
                    profile_id=cast(Literal["X35", "X36"], request.document.profile_id),
                )
                dual_y_project.open(opju_path)
                dual_y_native_snapshot = dual_y_project.verify_final_native_structure(
                    request.document,
                    request.data,
                )
                if not any(isinstance(action, SetSeriesStyle) for action in effective_visual):
                    dual_y_default_color_snapshot = (
                        dual_y_project.verify_product_default_series_colors()
                    )
            elif request.document.profile_id == "K07":
                k07_project = K07OriginProject(op)
                k07_project.open(opju_path)
                structural_snapshot = k07_project.verify(
                    request.document,
                    request.actions,
                    request.data,
                ).model_dump(mode="json")
                k07_axis_snapshot = {
                    axis_name: [
                        float(value)
                        for value in k07_project.layer.axis(axis_name).limits[:2]
                    ]
                    for axis_name in ("x", "y")
                }
            elif request.document.profile_id == "K14":
                k14_project = DistributionOriginProject(op, profile_id="K14")
                k14_project.reopen(opju_path)
                structural_snapshot = k14_project.verify(
                    request.document,
                    structural,
                    request.data,
                ).model_dump(mode="json")
                k14_defaults = _k14_default_styles(op, len(k14_project.plots))
            else:
                op.new(asksave=False)
                if not op.open(str(opju_path), readonly=True, asksave=False):
                    raise RuntimeError(f"Origin could not fresh-reopen {opju_path}")
        else:
            if request.document.profile_id == "K14":
                k14_project = DistributionOriginProject(op, profile_id="K14")
                k14_project.reopen(opju_path)
                structural_snapshot = k14_project.verify(
                    request.document,
                    structural,
                    request.data,
                ).model_dump(mode="json")
                k14_defaults = _k14_default_styles(op, len(k14_project.plots))
            elif request.document.profile_id == "X09":
                project = X09OriginProject(op)
                project.open(opju_path)
            else:
                project = K04OriginProject(op)
                project.reopen(opju_path)
            if request.document.profile_id != "K14":
                structural_readback = project.verify(
                    request.document,
                    structural,
                    request.data,
                )
                structural_snapshot = structural_readback.model_dump(mode="json")
        graphs = tuple(op.pages("g"))
        worksheets = tuple(op.pages("w"))
        matrices = tuple(op.pages("m"))
        if len(graphs) != 1:
            raise RuntimeError(
                f"representative OPJU must contain exactly one graph, observed {len(graphs)}"
            )
        if not worksheets and not matrices:
            raise RuntimeError("representative OPJU contains no editable native data page")
        graph = graphs[0]
        graph.activate()
        snapshot: dict[str, object]
        if effective_visual:
            snapshot = dict(
                _verify_actions(
                    op,
                    graph,
                    request.document,
                    effective_visual,
                )
            )
            if dual_y_native_snapshot is not None:
                snapshot["dual_y_final_native_structure"] = dual_y_native_snapshot
            if dual_y_default_color_snapshot is not None:
                snapshot["dual_y_product_default_series_colors"] = dual_y_default_color_snapshot
            if structural_snapshot is not None:
                snapshot["profile_structural_readback"] = structural_snapshot
            if k07_axis_snapshot is not None:
                snapshot["k07_persisted_axis_limits"] = k07_axis_snapshot
        else:
            snapshot = {"structural_readback": structural_snapshot}
        if k14_defaults is not None:
            snapshot["k14_product_style"] = _verify_k14_product_style(
                op,
                graph,
                effective_visual,
                k14_defaults,
            )
        if request.document.profile_id == "S34" and s34_equal_axes_enabled(
            request.document, request.actions
        ):
            snapshot["profile_invariant"] = verify_s34_equal_scale_layout(graph)
        result = {
            "schema_version": "plotagent.release-origin-fresh.v1",
            "process_id": os.getpid(),
            "profile_id": request.document.profile_id,
            "plot_id": request.document.plot_id,
            "plot_version": request.document.plot_version,
            "graph_count": len(graphs),
            "worksheet_count": len(worksheets),
            "matrix_count": len(matrices),
            "verification_mode": "visual" if effective_visual else "structural",
            "visual_export_mode": "origin_standalone_commandline",
            "visual_snapshot": snapshot,
            "opju_sha256": _sha(opju_path),
            "opju_size": opju_path.stat().st_size,
        }
    finally:
        op.exit()
    if result is None:
        raise RuntimeError("fresh Origin verification did not produce a result")
    export_origin_png_standalone(
        install_dir=Path(request.install_dir),
        opju_path=opju_path,
        png_path=png_path,
    )
    result["png_sha256"] = _sha(png_path)
    result["png_size"] = png_path.stat().st_size
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
