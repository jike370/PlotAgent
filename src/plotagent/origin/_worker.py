"""Dedicated hidden Origin worker for probe, K01 build, and fresh reopen.

This module deliberately contains no attach call, script execution entry point, formula,
or caller-supplied property path. It is launched in a new process for every phase.
"""

from __future__ import annotations

import gc
import json
import math
import os
import sys
import traceback
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

from plotagent.contracts.rendering import OriginExportPlan

from .constants import (
    GRAPH_LAYER_LONG_NAME,
    GRAPH_PAGE_LONG_NAME,
    GRAPH_PAGE_NAME,
    K01_FIXED_NUMERIC_PROPERTIES,
    MANIFEST_SHEET_LONG_NAME,
    MANIFEST_SHEET_NAME,
    METADATA_BOOK_LONG_NAME,
    METADATA_BOOK_NAME,
    PROJECT_FOLDERS,
    RAW_BOOK_LONG_NAME,
    RAW_BOOK_NAME,
    RAW_SHEET_LONG_NAME,
    RAW_SHEET_NAME,
    qualified_template_path,
)
from .k01 import K01OriginPlan, canonical_json, sha256_json, validation_report_for_plan


@dataclass(slots=True)
class WorkerFailure(Exception):
    code: str
    message: str
    details: dict[str, Any]


def _fail(code: str, message: str, **details: Any) -> NoReturn:
    raise WorkerFailure(code, message, details)


def _folder_items(collection: Any) -> list[Any]:
    return [collection.GetItem(index) for index in range(collection.GetCount())]


def _folder_by_name(root: Any, name: str) -> Any:
    for folder in _folder_items(root.obj.Folders):
        if folder.GetName() == name:
            return folder
    _fail("VALIDATION_FAILURE", f"missing Project Explorer folder: {name}")


def _page_names(folder: Any) -> list[str]:
    pages = folder.PageBases()
    return [pages.GetItem(index).GetName() for index in range(pages.GetCount())]


def _close_enough(actual: float, expected: float, tolerance: float) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance)


def _get_page(op: Any, name: str, wrapper: Any) -> Any:
    try:
        return wrapper(op.config.po.Pages[name])
    except Exception as exc:
        _fail("VALIDATION_FAILURE", f"could not read Origin page {name}", error=str(exc))


def _inspect_project(op: Any, plan: K01OriginPlan) -> dict[str, Any]:
    root = op.root_folder()
    actual_folders = sorted(folder.GetName() for folder in _folder_items(root.obj.Folders))
    if actual_folders != sorted(PROJECT_FOLDERS):
        _fail(
            "VALIDATION_FAILURE",
            "Project Explorer folder set differs from the K01 plan",
            actual=actual_folders,
        )
    folders = {name: _folder_by_name(root, name) for name in PROJECT_FOLDERS}
    expected_pages = {
        "Data": [RAW_BOOK_NAME],
        "Analysis": [],
        "Graphs": [GRAPH_PAGE_NAME],
        "Metadata": [METADATA_BOOK_NAME],
    }
    for name, expected in expected_pages.items():
        actual = sorted(_page_names(folders[name]))
        if actual != sorted(expected):
            _fail(
                "VALIDATION_FAILURE",
                f"unexpected pages in {name}",
                expected=expected,
                actual=actual,
            )

    raw_book = _get_page(op, RAW_BOOK_NAME, op.WBook)
    raw_sheet = raw_book[0]
    if raw_book.lname != RAW_BOOK_LONG_NAME or raw_sheet.lname != RAW_SHEET_LONG_NAME:
        _fail("VALIDATION_FAILURE", "Raw Data long names did not survive readback")
    rows, columns = raw_sheet.shape
    if (rows, columns) != (len(plan.data.x), 2):
        _fail(
            "VALIDATION_FAILURE",
            "Raw Data shape differs from the K01 plan",
            actual_rows=rows,
            actual_columns=columns,
        )
    x_values = [float(value) for value in raw_sheet.to_list(0)]
    y_values = [float(value) for value in raw_sheet.to_list(1)]
    raw_hash = sha256_json({"x": x_values, "y": y_values})
    if raw_hash != plan.raw_data_sha256:
        _fail("VALIDATION_FAILURE", "Raw Data hash differs from the K01 plan")
    x_column = raw_sheet.obj[0]
    y_column = raw_sheet.obj[1]
    expected_column_metadata = (
        (
            x_column,
            plan.data.x_long_name,
            plan.data.x_unit,
            plan.data.x_comments,
            3,
        ),
        (
            y_column,
            plan.data.y_long_name,
            plan.data.y_unit,
            plan.data.y_comments,
            0,
        ),
    )
    for column, long_name, unit, comments, designation in expected_column_metadata:
        actual_column = (
            column.GetLongName(),
            column.GetUnits(),
            column.GetComments(),
            int(column.GetType()),
        )
        if actual_column != (long_name, unit, comments, designation):
            _fail(
                "VALIDATION_FAILURE",
                "worksheet column metadata differs from the K01 plan",
                actual=list(actual_column),
            )

    graph = _get_page(op, GRAPH_PAGE_NAME, op.GPage)
    if graph.lname != GRAPH_PAGE_LONG_NAME or len(graph) != 1:
        _fail("VALIDATION_FAILURE", "graph page title or layer count differs")
    layer = graph[0]
    plots = layer.plot_list()
    if len(plots) != 1:
        _fail("VALIDATION_FAILURE", "K01 graph must contain exactly one native plot")
    linked_y_dataset = plots[0].obj.GetDatasetName()
    expected_y_dataset = y_column.GetDatasetName()
    if linked_y_dataset != expected_y_dataset:
        _fail(
            "VALIDATION_FAILURE",
            "native graph plot is not linked to the Raw Data Y column",
            actual=linked_y_dataset,
        )
    x_axis = tuple(float(value) for value in layer.axis("x").limits)
    y_axis = tuple(float(value) for value in layer.axis("y").limits)
    for actual_axis, expected_axis in ((x_axis, plan.x_axis), (y_axis, plan.y_axis)):
        if len(actual_axis) != 3 or any(
            not _close_enough(actual, expected, 1e-10)
            for actual, expected in zip(actual_axis, expected_axis, strict=True)
        ):
            _fail(
                "VALIDATION_FAILURE",
                "axis limits or tick increment differ from the K01 plan",
                actual=list(actual_axis),
                expected=list(expected_axis),
            )
    if layer.axis("x").scale != 1 or layer.axis("y").scale != 1:
        _fail("VALIDATION_FAILURE", "K01 axes must remain native linear axes")
    labels: dict[str, str] = {}
    for name in ("xb", "yl", "legend"):
        label = layer.label(name)
        if label is None:
            _fail("VALIDATION_FAILURE", f"missing native graph label: {name}")
        labels[name] = label.text
    if labels != {
        "xb": plan.x_axis_title,
        "yl": plan.y_axis_title,
        "legend": plan.legend_text,
    }:
        _fail("VALIDATION_FAILURE", "axis title or legend text differs", actual=labels)
    page_units = int(graph.obj.GetUnits())
    if page_units != 2:
        _fail(
            "VALIDATION_FAILURE",
            "qualified K01 graph template must use millimetres",
            actual_units=page_units,
        )
    page_width_mm = float(graph.obj.GetWidth())
    page_height_mm = float(graph.obj.GetHeight())
    if not _close_enough(page_width_mm, plan.page_width_mm, 0.2) or not _close_enough(
        page_height_mm, plan.page_height_mm, 0.2
    ):
        _fail(
            "VALIDATION_FAILURE",
            "graph page physical size differs from the K01 plan",
            actual_width_mm=page_width_mm,
            actual_height_mm=page_height_mm,
        )

    metadata_book = _get_page(op, METADATA_BOOK_NAME, op.WBook)
    manifest_sheet = metadata_book[0]
    if (
        metadata_book.lname != METADATA_BOOK_LONG_NAME
        or manifest_sheet.name != MANIFEST_SHEET_NAME
        or manifest_sheet.lname != MANIFEST_SHEET_LONG_NAME
    ):
        _fail("VALIDATION_FAILURE", "Metadata/manifest object names differ")
    keys = [str(value) for value in manifest_sheet.to_list(0)]
    values = [str(value) for value in manifest_sheet.to_list(1)]
    metadata = dict(zip(keys, values, strict=True))
    expected_manifest_json = canonical_json(plan.manifest)
    if metadata != {
        "manifest_json": expected_manifest_json,
        "render_plan_sha256": plan.render_plan_sha256,
        "validation_report_sha256": plan.validation_report_sha256,
    }:
        _fail("VALIDATION_FAILURE", "Metadata manifest content differs from the plan")
    manifest = json.loads(metadata["manifest_json"])
    if manifest.get("object_map") != plan.object_map:
        _fail("VALIDATION_FAILURE", "manifest object map differs from the K01 plan")

    report_fields: dict[str, Any] = {
        "rows": len(plan.data.x),
        "raw_data_sha256": raw_hash,
        "x_axis": list(plan.x_axis),
        "y_axis": list(plan.y_axis),
        "x_axis_title": labels["xb"],
        "y_axis_title": labels["yl"],
        "legend_text": labels["legend"],
        "page_width_mm": plan.page_width_mm,
        "page_height_mm": plan.page_height_mm,
        "object_map": manifest["object_map"],
    }
    report = validation_report_for_plan(report_fields)
    report_hash = sha256_json(report)
    if report_hash != plan.validation_report_sha256:
        _fail(
            "VALIDATION_FAILURE",
            "validation report hash differs from the manifest",
            actual=report_hash,
            expected=plan.validation_report_sha256,
        )
    return {"report": report, "report_sha256": report_hash}


def _probe(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"expected_runtime_version"}:
        _fail("START_FAILURE", "probe payload contains missing or unknown fields")
    import originpro as op  # type: ignore[import-untyped]

    try:
        root = op.root_folder()
        runtime_version = float(op.org_ver())
        if not root.obj.IsValid():
            _fail("LICENSE_UNAVAILABLE", "Origin root project is unavailable")
        expected = float(payload["expected_runtime_version"])
        if not _close_enough(runtime_version, expected, 1e-12):
            _fail(
                "VERSION_UNSUPPORTED",
                "Origin runtime version differs from the build declaration",
                runtime_version=runtime_version,
            )
        return {"status": "ok", "runtime_version": runtime_version}
    except WorkerFailure:
        raise
    except Exception as exc:
        message = str(exc)
        code = (
            "LICENSE_UNAVAILABLE"
            if "licen" in message.lower() or "activat" in message.lower()
            else "START_FAILURE"
        )
        _fail(code, "dedicated Origin license probe failed", error=message)
    finally:
        with suppress(UnboundLocalError):
            del root
        gc.collect()
        op.exit()


def _prepare_origin_session_exit(op: Any, backend: Any | None = None) -> None:
    """Close the saved project and release its native handles.

    OriginExt can block in ``Application.Exit`` while a saved project remains
    current.  Switching to a fresh unsaved project first invalidates its native
    page proxies and lets the synchronous exit complete normally.
    """

    op.new(asksave=False)
    if backend is not None:
        backend.release_native_handles()
    gc.collect()


def _build(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"plan", "install_dir", "temporary_opju_path"}:
        _fail("BUILD_FAILURE", "build payload contains missing or unknown fields")
    plan = K01OriginPlan.from_dict(cast(dict[str, Any], payload["plan"]))
    temporary_path = Path(str(payload["temporary_opju_path"])).resolve(strict=False)
    Path(str(payload["install_dir"])).resolve(strict=True)
    template = qualified_template_path()
    import originpro as op

    try:
        root = op.root_folder()
        if root.obj.Folders.GetCount() != 0 or root.obj.PageBases().GetCount() != 0:
            _fail("BUILD_FAILURE", "dedicated Origin instance did not start from a blank project")
        folders = {name: root.obj.Folders.Add(name) for name in PROJECT_FOLDERS}
        if any(folder is None or not folder.IsValid() for folder in folders.values()):
            _fail("BUILD_FAILURE", "could not create the fixed Project Explorer folders")

        folders["Data"].Activate()
        raw_book = op.new_book("w", RAW_BOOK_NAME, hidden=True)
        if raw_book is None:
            _fail("BUILD_FAILURE", "could not create the K01 Raw Data workbook")
        raw_book.name = RAW_BOOK_NAME
        raw_book.lname = RAW_BOOK_LONG_NAME
        raw_sheet = raw_book[0]
        raw_sheet.name = RAW_SHEET_NAME
        raw_sheet.lname = RAW_SHEET_LONG_NAME
        raw_sheet.shape = (len(plan.data.x), 2)
        raw_sheet.from_list(
            0,
            list(plan.data.x),
            lname=plan.data.x_long_name,
            units=plan.data.x_unit,
            comments=plan.data.x_comments,
            axis="X",
        )
        raw_sheet.from_list(
            1,
            list(plan.data.y),
            lname=plan.data.y_long_name,
            units=plan.data.y_unit,
            comments=plan.data.y_comments,
            axis="Y",
        )

        folders["Metadata"].Activate()
        metadata_book = op.new_book("w", METADATA_BOOK_NAME, hidden=True)
        if metadata_book is None:
            _fail("BUILD_FAILURE", "could not create the Metadata workbook")
        metadata_book.name = METADATA_BOOK_NAME
        metadata_book.lname = METADATA_BOOK_LONG_NAME
        manifest_sheet = metadata_book[0]
        manifest_sheet.name = MANIFEST_SHEET_NAME
        manifest_sheet.lname = MANIFEST_SHEET_LONG_NAME
        manifest_sheet.shape = (3, 2)
        manifest_sheet.from_list(
            0,
            ["manifest_json", "render_plan_sha256", "validation_report_sha256"],
            lname="Key",
            comments="PlotAgent manifest field",
            axis="N",
        )
        manifest_sheet.from_list(
            1,
            [
                canonical_json(plan.manifest),
                plan.render_plan_sha256,
                plan.validation_report_sha256,
            ],
            lname="Value",
            comments="PlotAgent manifest value",
            axis="N",
        )

        folders["Graphs"].Activate()
        graph = op.new_graph(
            GRAPH_PAGE_NAME,
            template=str(template.with_name(template.name.lower())),
            hidden=True,
        )
        if graph is None:
            _fail("BUILD_FAILURE", "could not create the native K01 graph page")
        graph.name = GRAPH_PAGE_NAME
        graph.lname = GRAPH_PAGE_LONG_NAME
        graph.obj.SetWidth(plan.page_width_mm / 25.4)
        graph.obj.SetHeight(plan.page_height_mm / 25.4)
        layer = graph[0]
        layer.lname = GRAPH_LAYER_LONG_NAME
        plot = layer.add_plot(raw_sheet, coly=1, colx=0, type="l")
        if plot is None:
            _fail("BUILD_FAILURE", "could not create the native linked K01 line plot")
        plot.lname = "series:signal"
        plot.color = 1
        for property_name, value in K01_FIXED_NUMERIC_PROPERTIES:
            layer.obj.SetNumProp(property_name, value)
        layer.xscale = "linear"
        layer.yscale = "linear"
        layer.set_xlim(*plan.x_axis)
        layer.set_ylim(*plan.y_axis)
        for label_name, text in (
            ("xb", plan.x_axis_title),
            ("yl", plan.y_axis_title),
            ("legend", plan.legend_text),
        ):
            label = layer.label(label_name)
            if label is None:
                _fail("BUILD_FAILURE", f"qualified template is missing label {label_name}")
            label.text = text

        live_validation = _inspect_project(op, plan)
        try:
            saved = bool(op.save(str(temporary_path)))
        except Exception as exc:
            _fail("SAVE_FAILURE", "Origin could not save the temporary OPJU", error=str(exc))
        if not saved or not temporary_path.is_file() or temporary_path.stat().st_size == 0:
            _fail("SAVE_FAILURE", "Origin did not create a non-empty temporary OPJU")
        return {
            "status": "ok",
            "runtime_version": float(op.org_ver()),
            "validation": live_validation,
            "temporary_size": temporary_path.stat().st_size,
        }
    except WorkerFailure:
        raise
    except Exception as exc:
        _fail("BUILD_FAILURE", "native K01 construction failed", error=str(exc))
    finally:
        gc.collect()
        op.exit()


def _reopen(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"plan", "temporary_opju_path"}:
        _fail("REOPEN_FAILURE", "reopen payload contains missing or unknown fields")
    plan = K01OriginPlan.from_dict(cast(dict[str, Any], payload["plan"]))
    temporary_path = Path(str(payload["temporary_opju_path"])).resolve(strict=True)
    import originpro as op

    try:
        root = op.root_folder()
        if root.obj.Folders.GetCount() != 0 or root.obj.PageBases().GetCount() != 0:
            _fail("REOPEN_FAILURE", "fresh validation instance was not blank before load")
        if not op.open(str(temporary_path), readonly=True, asksave=False):
            _fail("REOPEN_FAILURE", "fresh Origin instance could not open the temporary OPJU")
        validation = _inspect_project(op, plan)
        return {
            "status": "ok",
            "runtime_version": float(op.org_ver()),
            "validation": validation,
        }
    except WorkerFailure:
        raise
    except Exception as exc:
        _fail("REOPEN_FAILURE", "fresh reopen validation failed", error=str(exc))
    finally:
        gc.collect()
        op.exit()


def _write_worker_response(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _build_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"plan", "install_dir", "temporary_opju_path"}:
        _fail("BUILD_FAILURE", "typed-plan build payload contains missing or unknown fields")
    plan = OriginExportPlan.model_validate_json(json.dumps(payload["plan"], ensure_ascii=False))
    temporary_path = Path(str(payload["temporary_opju_path"])).resolve(strict=False)
    install_dir = Path(str(payload["install_dir"])).resolve(strict=True)
    template = qualified_template_path()
    import originpro as op

    from ._origin_backend import OriginProBackend
    from .native import build_native_project
    from .validation import expected_validation_sha256

    try:
        backend = OriginProBackend(op, template, install_dir)
        runtime_version = float(op.org_ver())
        report_sha256 = expected_validation_sha256(plan)

        def emit_validated_report(report: dict[str, object]) -> None:
            # OriginExt Save may finish writing the OPJU while its COM call stays
            # blocked.  Give the parent the already-validated report first; the
            # transport independently waits for a stable non-empty file before
            # it accepts this response and reaps the worker.
            _write_worker_response(
                {
                    "status": "ok",
                    "runtime_version": runtime_version,
                    "validation": {
                        "report": report,
                        "report_sha256": report_sha256,
                    },
                    "temporary_size": 0,
                }
            )

        report = build_native_project(
            backend,
            plan,
            str(temporary_path),
            on_validated=emit_validated_report,
        )
        return {
            "status": "ok",
            "runtime_version": runtime_version,
            "validation": {
                "report": report,
                "report_sha256": report_sha256,
            },
            "temporary_size": temporary_path.stat().st_size,
        }
    except WorkerFailure:
        raise
    except Exception as exc:
        _fail("BUILD_FAILURE", "typed native Origin construction failed", error=str(exc))
    finally:
        _prepare_origin_session_exit(op, locals().get("backend"))


def _reopen_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"plan", "install_dir", "temporary_opju_path"}:
        _fail("REOPEN_FAILURE", "typed-plan reopen payload contains missing or unknown fields")
    plan = OriginExportPlan.model_validate_json(json.dumps(payload["plan"], ensure_ascii=False))
    temporary_path = Path(str(payload["temporary_opju_path"])).resolve(strict=True)
    install_dir = Path(str(payload["install_dir"])).resolve(strict=True)
    template = qualified_template_path()
    import originpro as op

    from ._origin_backend import OriginProBackend
    from .native import inspect_native_project
    from .validation import expected_validation_sha256

    try:
        root = op.root_folder()
        if root.obj.Folders.GetCount() != 0 or root.obj.PageBases().GetCount() != 0:
            _fail("REOPEN_FAILURE", "fresh validation instance was not blank before load")
        if not op.open(str(temporary_path), readonly=True, asksave=False):
            _fail("REOPEN_FAILURE", "fresh Origin instance could not open the temporary OPJU")
        backend = OriginProBackend(op, template, install_dir)
        report = inspect_native_project(backend, plan)
        return {
            "status": "ok",
            "runtime_version": float(op.org_ver()),
            "validation": {
                "report": report,
                "report_sha256": expected_validation_sha256(plan),
            },
        }
    except WorkerFailure:
        raise
    except Exception as exc:
        _fail("REOPEN_FAILURE", "typed native Origin fresh reopen failed", error=str(exc))
    finally:
        _prepare_origin_session_exit(op, locals().get("backend"))


def _finalize_plan_worker(exit_code: int) -> NoReturn:
    import originpro as op

    try:
        op.exit()
    finally:
        os._exit(exit_code)


def _emit_worker_response(payload: dict[str, Any], exit_code: int) -> int:
    _write_worker_response(payload)
    if len(sys.argv) == 2 and sys.argv[1] in {"build-plan", "reopen-plan"}:
        # Emit the complete result before OriginExt begins its potentially
        # blocking Application.Exit call.  The parent transport accepts this
        # line and reaps the isolated worker after a short cleanup grace period.
        _finalize_plan_worker(exit_code)
    return exit_code


def _main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {
        "probe",
        "build",
        "reopen",
        "build-plan",
        "reopen-plan",
    }:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": {"code": "START_FAILURE", "message": "invalid worker mode"},
                }
            )
        )
        return 2
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            _fail("START_FAILURE", "worker payload must be a JSON object")
        result = {
            "probe": _probe,
            "build": _build,
            "reopen": _reopen,
            "build-plan": _build_plan,
            "reopen-plan": _reopen_plan,
        }[sys.argv[1]](payload)
        return _emit_worker_response(result, 0)
    except WorkerFailure as exc:
        return _emit_worker_response(
            {
                "status": "error",
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
            2,
        )
    except Exception as exc:
        return _emit_worker_response(
            {
                "status": "error",
                "error": {
                    "code": "START_FAILURE",
                    "message": str(exc),
                    "details": {"traceback": traceback.format_exc(limit=5)},
                },
            },
            2,
        )


if __name__ == "__main__":
    raise SystemExit(_main())
