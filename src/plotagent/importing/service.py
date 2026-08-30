"""Public deterministic import inspection entry point."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from plotagent.importing.errors import ImportErrorCode, ImportProblem
from plotagent.importing.models import (
    Clarification,
    ClarificationOption,
    Imported,
    ImportResponse,
    Rejection,
    TraceEvent,
)
from plotagent.importing.normalize import sha256_bytes
from plotagent.importing.text import TextImportOptions, inspect_text

_TEXT_SUFFIXES = frozenset({".csv", ".tsv", ".txt", ".dat"})
_EXCEL_SUFFIXES = frozenset({".xlsx", ".xlsm", ".xls"})


def _problem_response(problem: ImportProblem, trace: tuple[TraceEvent, ...]) -> ImportResponse:
    if problem.clarification_options:
        options = tuple(
            ClarificationOption(value=value, label=value) for value in problem.clarification_options
        )
        return Clarification(
            code=problem.code.value,
            question=problem.message,
            options=options,
            trace=trace,
        )
    return Rejection(
        code=problem.code.value,
        message=problem.message,
        remediation=problem.remediation,
        trace=trace,
    )


def inspect_source(
    path: str | Path,
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
    decimal_mark: str | None = None,
    header_row: int | None = None,
    header_rows: Mapping[str, int] | None = None,
    sheet: str | None = None,
) -> ImportResponse:
    """Inspect and fully parse a supported source without executing embedded content."""

    source_path = Path(path)
    suffix = source_path.suffix.casefold()
    sniff_trace = (
        TraceEvent(stage="sniff", code="IMPORT_SOURCE_READ", details={"format": suffix}),
    )
    if suffix not in _TEXT_SUFFIXES | _EXCEL_SUFFIXES:
        return Rejection(
            code=ImportErrorCode.FORMAT_UNSUPPORTED.value,
            message="文件格式不在第一轮确定性导入范围内。",
            remediation="请使用 .xlsx、.xlsm、.xls、.csv、.tsv、.txt 或 .dat。",
            trace=sniff_trace,
        )
    try:
        raw = source_path.read_bytes()
    except OSError:
        return Rejection(
            code=ImportErrorCode.PARSER_FAILED.value,
            message="无法读取授权文件。",
            remediation="请确认文件仍可访问后重试。",
            trace=sniff_trace,
        )
    source_hash = sha256_bytes(raw)
    try:
        if suffix in _TEXT_SUFFIXES:
            effective_delimiter = delimiter
            if effective_delimiter is None and suffix == ".tsv":
                effective_delimiter = "\t"
            sources = inspect_text(
                path=source_path,
                raw=raw,
                source_hash=source_hash,
                options=TextImportOptions(
                    encoding=encoding,
                    delimiter=effective_delimiter,
                    decimal_mark=decimal_mark,
                    header_row=header_row,
                ),
            )
        else:
            from plotagent.importing.excel import inspect_excel

            sources = inspect_excel(
                path=source_path,
                source_hash=source_hash,
                selected_sheet=sheet,
                header_row=header_row,
                header_rows=header_rows,
            )
    except ImportProblem as problem:
        return _problem_response(problem, sniff_trace)
    except (OSError, ValueError, TypeError) as exc:
        return Rejection(
            code=ImportErrorCode.PARSER_FAILED.value,
            message="文件解析失败，未创建正式数据集。",
            remediation=f"请检查文件结构后重试（{type(exc).__name__}）。",
            trace=sniff_trace,
        )
    trace = sniff_trace + tuple(event for source in sources for event in source.trace)
    return Imported(source_object_hash=source_hash, sources=sources, trace=trace)
