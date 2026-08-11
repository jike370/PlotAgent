"""Sealed Origin automation worker entry point."""

from __future__ import annotations

import sys
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

from .calculated_distribution import execute_k15_request
from .column_family import execute_k09_request, execute_k10_request, execute_k11_request
from .distribution import (
    execute_k12_request,
    execute_k13_request,
    execute_k14_request,
    execute_x05_request,
)
from .dual_y_special import execute_x35_request, execute_x36_request
from .k01 import execute_k01_request
from .k02 import execute_k02_request
from .k03 import execute_k03_request
from .k04 import execute_k04_request
from .k06 import execute_k06_request
from .k07 import execute_k07_request
from .k08 import execute_k08_request
from .k18 import execute_k18_request
from .k19 import execute_k19_request
from .k20 import execute_k20_request
from .k21 import execute_k21_request
from .k22 import execute_k22_request
from .k24 import execute_k24_request
from .k25 import execute_k25_request
from .messages import OriginWorkerRequest, OriginWorkerResponse
from .recipe import origin_recipe
from .renderer import OriginRendererRegistry
from .scientific_t2 import execute_s34_request
from .structural_t2 import execute_s01_request
from .trace import OriginExecutionTrace
from .wide_series import execute_x03_request, execute_x39_request, execute_x40_request
from .x02 import execute_x02_request
from .x09 import execute_x09_request
from .x13 import execute_x13_request
from .x23 import execute_x23_request
from .x24 import execute_x24_request
from .x38 import execute_x38_request


def _install_template_workbook_guard(op: Any) -> Callable[[], None]:
    """Discard workbooks created as side effects of loading a graph template.

    Official graph templates may carry an empty ``Book1``.  Data-backed
    binders create their authoritative workbook before ``new_graph``; any new
    workbook introduced by that call is therefore template residue, not plot
    data.  Keeping it would make a fresh OPJU contain unrelated editable data.
    """

    original = op.new_graph

    def new_graph(*args: object, **kwargs: object) -> Any:
        existing = {book.name for book in op.pages("w")}
        graph = original(*args, **kwargs)
        for book in tuple(op.pages("w")):
            if book.name == "Book1" or book.name not in existing:
                book.destroy()
        return graph

    op.new_graph = new_graph

    def restore() -> None:
        op.new_graph = original

    return restore


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        raise SystemExit("usage: origin worker REQUEST_JSON RESPONSE_JSON")
    request_path, response_path = (Path(value).resolve() for value in args)
    request = OriginWorkerRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    renderers = OriginRendererRegistry(
        {
            "K01": execute_k01_request,
            "K02": execute_k02_request,
            "K03": execute_k03_request,
            "K04": execute_k04_request,
            "K06": execute_k06_request,
            "K07": execute_k07_request,
            "K08": execute_k08_request,
            "K09": execute_k09_request,
            "K10": execute_k10_request,
            "K11": execute_k11_request,
            "K12": execute_k12_request,
            "K13": execute_k13_request,
            "K14": execute_k14_request,
            "K15": execute_k15_request,
            "K18": execute_k18_request,
            "K19": execute_k19_request,
            "K20": execute_k20_request,
            "K21": execute_k21_request,
            "K22": execute_k22_request,
            "K24": execute_k24_request,
            "K25": execute_k25_request,
            "S01": execute_s01_request,
            "S34": execute_s34_request,
            "X02": execute_x02_request,
            "X03": execute_x03_request,
            "X05": execute_x05_request,
            "X09": execute_x09_request,
            "X13": execute_x13_request,
            "X23": execute_x23_request,
            "X24": execute_x24_request,
            "X35": execute_x35_request,
            "X36": execute_x36_request,
            "X38": execute_x38_request,
            "X39": execute_x39_request,
            "X40": execute_x40_request,
        }
    )
    recipe = origin_recipe(request.document.profile_id)
    output = Path(request.output_opju).resolve()
    trace = OriginExecutionTrace(
        path=output.parent / "execution-trace.jsonl",
        profile_id=request.document.profile_id,
        plot_id=request.document.plot_id,
        plot_version=request.document.plot_version,
    )
    trace.reset()
    with trace.activate():
        trace.record(
            "request_validated",
            "completed",
            details={
                "action_count": len(request.actions),
                "data_backed": request.source.data is not None,
                "recipe_id": recipe.profile_id,
                "template_filename": (
                    None if recipe.primary_template is None else recipe.primary_template.filename
                ),
            },
        )
        op: Any | None = None
        restore_new_graph: Callable[[], None] | None = None
        try:
            with trace.step("origin_session_start"):
                import originpro as op_module  # type: ignore[import-untyped]

                op = op_module
                op.set_show(False)
                restore_new_graph = _install_template_workbook_guard(op)
            with trace.step(
                "renderer_dispatch",
                details={
                    "binder_key": recipe.binder_key,
                    "template_filename": (
                        None
                        if recipe.primary_template is None
                        else recipe.primary_template.filename
                    ),
                },
            ):
                readback = renderers.execute(
                    recipe,
                    op,
                    request,
                    Path(request.install_dir).resolve(),
                    output,
                )
            with trace.step("response_write"):
                response_path.write_text(
                    OriginWorkerResponse(readback=readback).model_dump_json(indent=2),
                    encoding="utf-8",
                )
            trace.record(
                "worker_completed",
                "completed",
                details={
                    "data_hash": readback.data_hash,
                    "object_count": len(readback.objects),
                    "opju_sha256": sha256(output.read_bytes()).hexdigest(),
                    "opju_size": output.stat().st_size,
                    "style_hash": readback.style_hash,
                },
            )
        except BaseException as exc:
            trace.record("worker_failed", "failed", error=exc)
            raise
        finally:
            if restore_new_graph is not None:
                restore_new_graph()
            if op is not None:
                with trace.step("origin_session_exit"):
                    op.exit()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
