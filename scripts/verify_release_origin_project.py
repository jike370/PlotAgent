"""Fresh-process verifier for one representative release-matrix OPJU."""

from __future__ import annotations

import json
import os
import sys
from hashlib import sha256
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine.backends.origin.messages import OriginWorkerRequest  # noqa: E402
from plotagent.engine.backends.origin.visual_t1 import _verify_actions  # noqa: E402
from plotagent.engine.contracts import CreatePlot  # noqa: E402
from plotagent.engine.visual_t1 import split_visual_actions  # noqa: E402


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: verify_release_origin_project REQUEST_JSON OPJU PNG RESULT_JSON")
    request_path, opju_path, png_path, result_path = (
        Path(value).resolve() for value in sys.argv[1:]
    )
    request = OriginWorkerRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    if request.document.plot_version < 2:
        raise RuntimeError("fresh release verification requires an edited document")
    _structural, visual = split_visual_actions(
        tuple(action for action in request.actions if not isinstance(action, CreatePlot))
    )
    if not visual:
        raise RuntimeError("fresh release verification requires visual actions")

    import originpro as op  # type: ignore[import-untyped]  # noqa: PLC0415

    op.set_show(False)
    try:
        op.new(asksave=False)
        if not op.open(str(opju_path), readonly=True, asksave=False):
            raise RuntimeError(f"Origin could not fresh-reopen {opju_path}")
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
        snapshot = _verify_actions(op, graph, request.document, visual)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        graph.save_fig(str(png_path), type="png", replace=True, width=1600)
        if not png_path.is_file() or png_path.stat().st_size <= 0:
            raise RuntimeError("fresh Origin session did not export a non-empty PNG")
        result = {
            "schema_version": "plotagent.release-origin-fresh.v1",
            "process_id": os.getpid(),
            "profile_id": request.document.profile_id,
            "plot_id": request.document.plot_id,
            "plot_version": request.document.plot_version,
            "graph_count": len(graphs),
            "worksheet_count": len(worksheets),
            "matrix_count": len(matrices),
            "visual_snapshot": snapshot,
            "opju_sha256": _sha(opju_path),
            "opju_size": opju_path.stat().st_size,
            "png_sha256": _sha(png_path),
            "png_size": png_path.stat().st_size,
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        op.exit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
