"""Shared normalization, schema inference, quality, and deterministic identity helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from plotagent.importing.errors import ImportErrorCode, ImportProblem
from plotagent.importing.models import (
    DatasetCandidate,
    FieldQuality,
    FieldSchema,
    ImportRecipe,
    ProvenanceMarker,
    QualitySummary,
    Scalar,
    SourceCoordinate,
    TraceEvent,
    UnitSuggestion,
)

_MISSING = frozenset({"", "na", "n/a", "null", "none", "missing", "-", "—"})
_TRUE = frozenset({"true"})
_FALSE = frozenset({"false"})
_UNIT_PATTERN = re.compile(r"(?:\(([^()]+)\)|\[([^\[\]]+)\])\s*$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_hash(parts: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def normalize_header(value: object) -> str:
    return unicodedata.normalize("NFC", str(value).strip())


def parse_text_scalar(token: str, decimal_mark: str) -> Scalar:
    cleaned = token.strip()
    folded = cleaned.casefold()
    if folded in _MISSING:
        return None
    if folded in _TRUE:
        return True
    if folded in _FALSE:
        return False
    if folded in {"nan", "+nan", "-nan"}:
        return float("nan")
    if folded in {"inf", "+inf", "infinity", "+infinity"}:
        return float("inf")
    if folded in {"-inf", "-infinity"}:
        return float("-inf")

    numeric = cleaned.replace(" ", "")
    if decimal_mark == ",":
        numeric = numeric.replace(".", "").replace(",", ".")
    try:
        parsed = Decimal(numeric)
    except InvalidOperation:
        return cleaned
    if parsed == parsed.to_integral_value() and "." not in numeric and "e" not in numeric.lower():
        try:
            return int(parsed)
        except (OverflowError, ValueError):
            return float(parsed)
    return float(parsed)


def normalize_excel_scalar(value: object) -> Scalar:
    if value is None or isinstance(value, (str, int, float, bool, date, datetime)):
        if isinstance(value, str):
            parsed = parse_text_scalar(value, ".")
            return parsed
        return value
    return str(value)


def _physical_type(value: Scalar) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "float64"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    return "string"


def _logical_type(
    types: set[str],
) -> Literal["numeric", "boolean", "datetime", "text", "mixed"]:
    useful = types - {"null"}
    if not useful:
        return "text"
    if useful <= {"int64", "float64"}:
        return "numeric"
    if useful == {"bool"}:
        return "boolean"
    if useful <= {"date", "datetime"}:
        return "datetime"
    if useful == {"string"}:
        return "text"
    return "mixed"


def _unit_suggestion(header: str) -> UnitSuggestion | None:
    match = _UNIT_PATTERN.search(header)
    if match is None:
        return None
    unit = (match.group(1) or match.group(2) or "").strip()
    if not unit:
        return None
    return UnitSuggestion(source_text=unit)


def _canonical_recipe(recipe: ImportRecipe) -> str:
    return json.dumps(recipe.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def build_candidate(
    *,
    display_name: str,
    source_hash: str,
    recipe: ImportRecipe,
    headers: tuple[str, ...],
    rows: tuple[tuple[Scalar, ...], ...],
    coordinates: tuple[SourceCoordinate, ...],
    metadata: dict[str, str] | None = None,
    postamble: tuple[str, ...] = (),
    provenance: tuple[ProvenanceMarker, ...] = (),
    trace: tuple[TraceEvent, ...] = (),
) -> DatasetCandidate:
    if not rows:
        raise ImportProblem(
            ImportErrorCode.NO_DATA,
            "未找到可导入的数据行。",
            "请确认文件包含带至少两列的表格数据。",
        )
    normalized = tuple(normalize_header(header) for header in headers)
    if any(not header for header in normalized):
        raise ImportProblem(
            ImportErrorCode.HEADER_AMBIGUOUS,
            "表头包含空列名。",
            "请在源文件中为每列提供唯一列名。",
        )
    duplicates = tuple(sorted({name for name in normalized if normalized.count(name) > 1}))
    if duplicates:
        raise ImportProblem(
            ImportErrorCode.DUPLICATE_HEADERS,
            "规范化后存在重复列名。",
            "请在源文件中重命名重复列，或明确选择不同的解析区域。",
        )
    width = len(normalized)
    if any(len(row) != width for row in rows):
        raise ImportProblem(
            ImportErrorCode.ROW_WIDTH_MISMATCH,
            "数据行列数不一致。",
            "请修复不规则行，或将不同数据块拆分后重新导入。",
        )
    if len(coordinates) != len(rows):
        raise ValueError("one source coordinate is required for every data row")

    fields: list[FieldSchema] = []
    field_quality: list[FieldQuality] = []
    total_missing = total_nan = total_pos_inf = total_neg_inf = 0
    for index, (source_name, normalized_name) in enumerate(zip(headers, normalized, strict=True)):
        values = tuple(row[index] for row in rows)
        types = {_physical_type(value) for value in values}
        # Field ids are structure-stable so one FieldMapping can fan out across
        # fully isomorphic sources; the SourceDataset id still owns each field.
        field_id = "fld_" + stable_hash((normalized_name,))[:20]
        missing = sum(value is None for value in values)
        nan = sum(isinstance(value, float) and math.isnan(value) for value in values)
        pos_inf = sum(value == float("inf") for value in values)
        neg_inf = sum(value == float("-inf") for value in values)
        total_missing += missing
        total_nan += nan
        total_pos_inf += pos_inf
        total_neg_inf += neg_inf
        logical_type = _logical_type(types)
        precision: Literal["integer", "binary64"] | None = None
        if logical_type == "numeric":
            precision = "binary64" if "float64" in types else "integer"
        fields.append(
            FieldSchema(
                field_id=field_id,
                source_name=source_name,
                normalized_name=normalized_name,
                logical_type=logical_type,
                physical_types=tuple(sorted(types)),
                numeric_precision=precision,
                unit=_unit_suggestion(normalized_name),
            )
        )
        field_quality.append(
            FieldQuality(
                field_id=field_id,
                missing_count=missing,
                nan_count=nan,
                positive_inf_count=pos_inf,
                negative_inf_count=neg_inf,
            )
        )

    candidate_id = "src_" + stable_hash((source_hash, _canonical_recipe(recipe)))[:24]
    quality = QualitySummary(
        row_count=len(rows),
        column_count=width,
        missing_count=total_missing,
        nan_count=total_nan,
        positive_inf_count=total_pos_inf,
        negative_inf_count=total_neg_inf,
        unparseable_count=0,
        fields=tuple(field_quality),
    )
    return DatasetCandidate(
        candidate_id=candidate_id,
        display_name=display_name,
        source_object_hash=source_hash,
        recipe=recipe,
        fields=tuple(fields),
        rows=rows,
        coordinates=coordinates,
        instrument_metadata=metadata or {},
        postamble=postamble,
        quality=quality,
        provenance=provenance,
        trace=trace,
    )
