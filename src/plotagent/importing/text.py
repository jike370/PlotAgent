"""Deterministic CSV/TXT structure detection and parsing."""

from __future__ import annotations

import codecs
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from plotagent.contracts.datasets import TextSourceCoordinate
from plotagent.importing.errors import ImportErrorCode, ImportProblem
from plotagent.importing.models import ImportRecipe, SourceDatasetArtifact, TraceEvent
from plotagent.importing.normalize import (
    build_candidate,
    looks_like_declared_header,
    parse_text_scalar,
    stable_hash,
)

_DELIMITERS = (",", "\t", ";", "|")
_DECIMAL_COMMA = re.compile(r"^[+-]?\d+,\d+(?:[eE][+-]?\d+)?$")
_DECIMAL_DOT = re.compile(r"^[+-]?\d+\.\d+(?:[eE][+-]?\d+)?$")


@dataclass(frozen=True)
class TextImportOptions:
    encoding: str | None = None
    delimiter: str | None = None
    decimal_mark: str | None = None
    header_row: int | None = None


@dataclass(frozen=True)
class _DecodedText:
    text: str
    encoding: str
    offset_codec: str
    bom_size: int


@dataclass(frozen=True)
class _Line:
    number: int
    text: str
    byte_start: int
    byte_end: int


@dataclass(frozen=True)
class _TableLine:
    line: _Line
    cells: tuple[str, ...]


def _decode(raw: bytes, requested: str | None) -> _DecodedText:
    if requested is not None:
        normalized = codecs.lookup(requested).name
        try:
            text = raw.decode(normalized)
        except UnicodeDecodeError as exc:
            raise ImportProblem(
                ImportErrorCode.ENCODING_UNSUPPORTED,
                f"文件不能按 {requested} 解码。",
                "请选择正确的文本编码后重试。",
            ) from exc
        if normalized == "utf-8-sig":
            return _DecodedText(text, "utf-8-sig", "utf-8", 3)
        if normalized in {"utf-16", "utf-16-le", "utf-16-be"}:
            if raw.startswith(codecs.BOM_UTF16_LE):
                return _DecodedText(text, "utf-16-le", "utf-16-le", 2)
            if raw.startswith(codecs.BOM_UTF16_BE):
                return _DecodedText(text, "utf-16-be", "utf-16-be", 2)
        return _DecodedText(text, normalized, normalized, 0)

    if raw.startswith(codecs.BOM_UTF8):
        return _DecodedText(raw.decode("utf-8-sig"), "utf-8-sig", "utf-8", 3)
    if raw.startswith(codecs.BOM_UTF16_LE):
        return _DecodedText(raw[2:].decode("utf-16-le"), "utf-16-le", "utf-16-le", 2)
    if raw.startswith(codecs.BOM_UTF16_BE):
        return _DecodedText(raw[2:].decode("utf-16-be"), "utf-16-be", "utf-16-be", 2)
    if b"\x00" in raw:
        even_nulls = raw[0::2].count(0)
        odd_nulls = raw[1::2].count(0)
        if odd_nulls > len(raw) // 8:
            return _DecodedText(raw.decode("utf-16-le"), "utf-16-le", "utf-16-le", 0)
        if even_nulls > len(raw) // 8:
            return _DecodedText(raw.decode("utf-16-be"), "utf-16-be", "utf-16-be", 0)
        raise ImportProblem(
            ImportErrorCode.BINARY_UNSUPPORTED,
            "文件包含不符合文本编码特征的二进制内容。",
            "请导出为 CSV、TSV 或纯文本后重新导入。",
        )
    try:
        return _DecodedText(raw.decode("utf-8"), "utf-8", "utf-8", 0)
    except UnicodeDecodeError as exc:
        text = raw.decode("cp1252")
        controls = sum(ord(char) < 32 and char not in "\r\n\t" for char in text)
        if controls > max(2, len(text) // 20):
            raise ImportProblem(
                ImportErrorCode.BINARY_UNSUPPORTED,
                "文件不像受支持的文本表格。",
                "请导出为 UTF-8、UTF-16 或 Windows-1252 文本后重试。",
            ) from exc
        return _DecodedText(text, "cp1252", "cp1252", 0)


def _lines(decoded: _DecodedText) -> tuple[_Line, ...]:
    result: list[_Line] = []
    byte_cursor = decoded.bom_size
    for number, raw_line in enumerate(decoded.text.splitlines(keepends=True), start=1):
        content = raw_line.rstrip("\r\n")
        content_size = len(content.encode(decoded.offset_codec))
        raw_size = len(raw_line.encode(decoded.offset_codec))
        result.append(_Line(number, content, byte_cursor, byte_cursor + content_size))
        byte_cursor += raw_size
    if decoded.text and not result:
        result.append(
            _Line(
                1,
                decoded.text,
                decoded.bom_size,
                len(decoded.text.encode(decoded.offset_codec)),
            )
        )
    return tuple(result)


def _parse_line(text: str, delimiter: str) -> tuple[str, ...]:
    try:
        parsed = next(csv.reader([text], delimiter=delimiter, strict=True))
    except csv.Error as exc:
        raise ImportProblem(
            ImportErrorCode.PARSER_FAILED,
            "文本中的引号或转义不完整。",
            "请修复 CSV 引号，或选择正确的分隔符。",
        ) from exc
    return tuple(parsed)


def _delimiter_score(lines: tuple[_Line, ...], delimiter: str) -> tuple[int, int]:
    widths: list[int] = []
    for line in lines:
        if not line.text.strip():
            continue
        try:
            widths.append(len(_parse_line(line.text, delimiter)))
        except ImportProblem:
            continue
    useful = [width for width in widths if width >= 2]
    if not useful:
        return (0, 0)
    mode, count = Counter(useful).most_common(1)[0]
    inconsistent = len(useful) - count
    return (count * 10 - inconsistent * 3, mode)


def _detect_delimiter(lines: tuple[_Line, ...], requested: str | None) -> str:
    if requested is not None:
        if len(requested) != 1:
            raise ImportProblem(
                ImportErrorCode.DELIMITER_AMBIGUOUS,
                "分隔符必须是单个字符。",
                "请选择逗号、制表符、分号或竖线。",
                clarification_options=_DELIMITERS,
            )
        return requested
    scores = {delimiter: _delimiter_score(lines, delimiter) for delimiter in _DELIMITERS}
    best_score = max(score for score, _width in scores.values())
    winners = tuple(
        delimiter for delimiter, (score, _width) in scores.items() if score == best_score
    )
    if best_score <= 0:
        raise ImportProblem(
            ImportErrorCode.NO_DATA,
            "未检测到至少两列的分隔文本数据。",
            "请确认文件分隔符和数据区域，或导出为标准 CSV/TSV。",
        )
    if len(winners) > 1:
        labels = tuple("TAB" if value == "\t" else value for value in winners)
        raise ImportProblem(
            ImportErrorCode.DELIMITER_AMBIGUOUS,
            "检测到多个同等合理的分隔符，请选择一个。",
            "选择后会继续同一次导入，不会创建临时数据集。",
            clarification_options=labels,
        )
    return winners[0]


def _detect_decimal_mark(
    table_rows: tuple[_TableLine, ...], delimiter: str, requested: str | None
) -> str:
    if requested is not None:
        if requested not in {".", ","}:
            raise ValueError("decimal_mark must be '.' or ','")
        return requested
    if delimiter == ",":
        return "."
    tokens = [cell.strip() for row in table_rows for cell in row.cells]
    comma = sum(bool(_DECIMAL_COMMA.fullmatch(token)) for token in tokens)
    dot = sum(bool(_DECIMAL_DOT.fullmatch(token)) for token in tokens)
    if comma and dot and comma == dot:
        raise ImportProblem(
            ImportErrorCode.DECIMAL_AMBIGUOUS,
            "逗号和句点小数格式同样常见，请确认小数点规则。",
            "选择规则后会继续同一次导入。",
            clarification_options=(".", ","),
        )
    return "," if comma > dot else "."


def _table_groups(lines: tuple[_Line, ...], delimiter: str) -> tuple[tuple[_TableLine, ...], ...]:
    groups: list[list[_TableLine]] = []
    current: list[_TableLine] = []
    for line in lines:
        cells = _parse_line(line.text, delimiter) if line.text.strip() else ()
        if len(cells) >= 2:
            current.append(_TableLine(line, cells))
            continue
        if current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return tuple(tuple(group) for group in groups if len(group) >= 2)


def _typed_count(cells: tuple[str, ...], decimal_mark: str) -> int:
    parsed = (parse_text_scalar(cell, decimal_mark) for cell in cells)
    return sum(value is not None and not isinstance(value, str) for value in parsed)


def _nonempty_column_indices(data_lines: tuple[_TableLine, ...]) -> tuple[int, ...]:
    """Return columns that contain at least one non-blank data token.

    Instrument exports commonly terminate every record with a delimiter.  The
    parser must not turn that serialization detail into a null-only field, but
    it also must not drop a sparsely populated real field.
    """

    if not data_lines:
        return ()
    return tuple(
        index
        for index in range(len(data_lines[0].cells))
        if any(row.cells[index].strip() for row in data_lines)
    )


def _header_index(
    group: tuple[_TableLine, ...], decimal_mark: str, requested: int | None
) -> tuple[int | None, int]:
    if requested == 0:
        return None, 0
    if requested is not None:
        for index, row in enumerate(group):
            if row.line.number == requested:
                return index, index + 1
        raise ImportProblem(
            ImportErrorCode.HEADER_AMBIGUOUS,
            "指定的表头行不在候选数据区域内。",
            "请选择候选区域中的表头行。",
        )
    first = group[0].cells
    second = group[1].cells
    first_typed = _typed_count(first, decimal_mark)
    second_typed = _typed_count(second, decimal_mark)
    if first_typed == 0 and second_typed > 0:
        return 0, 1
    if first_typed >= max(1, len(first) // 2):
        return None, 0
    if first_typed == 0 and second_typed == 0:
        if looks_like_declared_header(first):
            return 0, 1
        raise ImportProblem(
            ImportErrorCode.HEADER_AMBIGUOUS,
            f"第 {group[0].line.number} 行和第 {group[1].line.number} 行都可能是表头。",
            "请选择表头行，或选择“无表头”。",
            clarification_options=(
                f"line:{group[0].line.number}",
                f"line:{group[1].line.number}",
                "none",
            ),
        )
    if second_typed > first_typed:
        return 0, 1
    return None, 0


def _metadata(lines: tuple[_Line, ...], excluded: set[int]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines:
        if line.number in excluded or not line.text.strip():
            continue
        separator = "=" if "=" in line.text else ":" if ":" in line.text else None
        if separator is None:
            continue
        key, value = line.text.split(separator, 1)
        normalized_key = key.strip()
        if normalized_key and value.strip():
            result[normalized_key] = value.strip()
    return result


def inspect_text(
    *,
    path: Path,
    raw: bytes,
    source_hash: str,
    options: TextImportOptions,
) -> tuple[SourceDatasetArtifact, ...]:
    decoded = _decode(raw, options.encoding)
    lines = _lines(decoded)
    delimiter = _detect_delimiter(lines, options.delimiter)
    groups = _table_groups(lines, delimiter)
    if not groups:
        raise ImportProblem(
            ImportErrorCode.NO_DATA,
            "未找到完整的表格数据块。",
            "请确认至少包含两行、两列且分隔符一致的数据。",
        )
    all_table_rows = tuple(row for group in groups for row in group)
    decimal_mark = _detect_decimal_mark(all_table_rows, delimiter, options.decimal_mark)
    excluded_lines = {row.line.number for row in all_table_rows}
    metadata = _metadata(lines, excluded_lines)
    last_table_line = max(excluded_lines)
    postamble = tuple(
        line.text for line in lines if line.number > last_table_line and line.text.strip()
    )
    preamble_lines = tuple(line for line in lines if line.number < min(excluded_lines))
    suffix = path.suffix.casefold().lstrip(".")
    source_format = "tsv" if suffix == "tsv" else suffix

    candidates: list[SourceDatasetArtifact] = []
    for block_index, group in enumerate(groups, start=1):
        widths = {len(row.cells) for row in group}
        if len(widths) != 1:
            raise ImportProblem(
                ImportErrorCode.ROW_WIDTH_MISMATCH,
                f"数据块 {block_index} 的行宽不一致。",
                "请修复不规则行，或用空行拆分不同结构的数据块。",
            )
        header_index, data_index = _header_index(group, decimal_mark, options.header_row)
        raw_width = len(group[0].cells)
        data_lines = group[data_index:]
        active_columns = _nonempty_column_indices(data_lines)
        if not active_columns:
            raise ImportProblem(
                ImportErrorCode.NO_DATA,
                f"数据块 {block_index} 不包含可导入字段。",
                "请确认表头后至少有一列非空数据。",
            )
        if header_index is None:
            headers = tuple(f"column_{index + 1}" for index in active_columns)
            header_row = None
        else:
            headers = tuple(group[header_index].cells[index].strip() for index in active_columns)
            header_row = group[header_index].line.number
        rows = tuple(
            tuple(parse_text_scalar(row.cells[index], decimal_mark) for index in active_columns)
            for row in data_lines
        )
        block_name = f"block_{block_index}"
        coordinates = tuple(
            TextSourceCoordinate(
                source_row_id="row:"
                + stable_hash((source_hash, block_name, str(row.line.number)))[:24],
                block=block_name,
                channel=metadata.get("Channel") or metadata.get("channel"),
                sweep=metadata.get("Sweep") or metadata.get("sweep"),
                line_start=row.line.number,
                line_end=row.line.number,
                byte_start=row.line.byte_start,
                byte_end=row.line.byte_end,
            )
            for row in data_lines
        )
        trace = (
            TraceEvent(
                stage="detect",
                code="IMPORT_TEXT_STRUCTURE_DETECTED",
                details={
                    "encoding": decoded.encoding,
                    "delimiter": "TAB" if delimiter == "\t" else delimiter,
                    "decimal_mark": decimal_mark,
                    "block": block_index,
                },
            ),
            TraceEvent(
                stage="parse",
                code="IMPORT_TEXT_BLOCK_PARSED",
                details={
                    "rows": len(rows),
                    "columns": len(active_columns),
                    "discarded_empty_columns": raw_width - len(active_columns),
                },
            ),
        )
        recipe = ImportRecipe(
            parser_name="plotagent-text",
            parser_version="text-v2",
            source_format=source_format,  # type: ignore[arg-type]
            encoding=decoded.encoding,
            delimiter=delimiter,
            decimal_mark=decimal_mark,  # type: ignore[arg-type]
            header_row=header_row,
            data_start_row=data_lines[0].line.number,
            data_end_row=data_lines[-1].line.number,
            preamble_start_line=preamble_lines[0].number if preamble_lines else None,
            preamble_end_line=preamble_lines[-1].number if preamble_lines else None,
            postamble_start_line=last_table_line + 1 if postamble else None,
            postamble_end_line=lines[-1].number if postamble else None,
            block=block_name,
            column_names=tuple(headers),
        )
        candidates.append(
            build_candidate(
                display_name=f"{path.stem}:{block_name}",
                source_hash=source_hash,
                recipe=recipe,
                headers=headers,
                rows=rows,
                coordinates=coordinates,
                metadata=metadata,
                postamble=postamble,
                trace=trace,
            )
        )
    return tuple(candidates)
