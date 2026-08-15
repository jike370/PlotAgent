"""Shared normalization and construction of the authoritative SourceDataset contract."""

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

from plotagent.contracts.base import ContentTableRef, WarningRecord
from plotagent.contracts.datasets import (
    DataQualitySummary,
    SourceCoordinate,
    SourceDataset,
    SourceField,
    UnitSpec,
)
from plotagent.importing.errors import ImportErrorCode, ImportProblem
from plotagent.importing.models import (
    ImportRecipe,
    ProvenanceMarker,
    Scalar,
    SourceDatasetArtifact,
    TraceEvent,
)

_MISSING = frozenset({"", "na", "n/a", "null", "none", "missing", "-", "—"})
_TRUE = frozenset({"true"})
_FALSE = frozenset({"false"})
_UNIT_PATTERN = re.compile(r"(?:\(([^()]+)\)|\[([^\[\]]+)\])\s*$")
_HEADER_NAMES = frozenset(
    {
        "x",
        "y",
        "z",
        "time",
        "value",
        "signal",
        "center",
        "lower",
        "upper",
        "error",
        "category",
        "group",
        "component",
        "label",
        "row",
        "column",
        "rowlabel",
        "columnlabel",
        "actual",
        "predicted",
        "count",
        "correlation",
        "feature",
        "log2fc",
        "pvalue",
        "p_value",
    }
)


def looks_like_declared_header(cells: tuple[str, ...]) -> bool:
    """Recognize common explicit scientific headers without guessing arbitrary text rows."""

    normalized = tuple(re.sub(r"[^a-z0-9_]+", "", value.strip().casefold()) for value in cells)
    if (
        not normalized
        or any(not value for value in normalized)
        or len(set(normalized)) != len(normalized)
    ):
        return False
    return all(
        value in _HEADER_NAMES
        or re.fullmatch(r"(?:series|measurement|field|sample)\d+", value) is not None
        for value in normalized
    )


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
            return parse_text_scalar(value, ".")
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
) -> Literal["numeric", "categorical", "datetime", "boolean", "text"]:
    useful = types - {"null"}
    if not useful:
        return "text"
    if useful <= {"int64", "float64"}:
        return "numeric"
    if useful == {"bool"}:
        return "boolean"
    if useful <= {"date", "datetime"}:
        return "datetime"
    return "text"


def _unit(header: str) -> UnitSpec:
    match = _UNIT_PATTERN.search(header)
    if match is None:
        return UnitSpec(
            source_text="",
            dimensionality="dimensionless",
            kind="dimensionless",
            registry_version="units.v1",
        )
    unit = (match.group(1) or match.group(2) or "").strip()
    if not unit:
        return UnitSpec(
            source_text="",
            dimensionality="dimensionless",
            kind="dimensionless",
            registry_version="units.v1",
        )
    return UnitSpec(
        source_text=unit,
        dimensionality="opaque",
        kind="opaque",
        registry_version="units.v1",
    )


def _canonical_recipe(recipe: ImportRecipe) -> str:
    return json.dumps(recipe.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _coordinate_samples(
    coordinates: tuple[SourceCoordinate, ...],
) -> tuple[SourceCoordinate, ...]:
    if len(coordinates) <= 20:
        return coordinates
    return coordinates[:10] + coordinates[-10:]


def _quality_warnings(provenance: tuple[ProvenanceMarker, ...]) -> tuple[WarningRecord, ...]:
    kinds = {marker.kind for marker in provenance}
    warnings: list[WarningRecord] = []
    if "formula_uncached" in kinds:
        warnings.append(
            WarningRecord(
                warning_id="formula_uncached",
                message="Formula cells without cached values were imported as missing.",
            )
        )
    if "macro_ignored" in kinds:
        warnings.append(
            WarningRecord(
                warning_id="macro_ignored",
                message="Workbook macro content was ignored and never executed.",
            )
        )
    if "external_link" in kinds:
        warnings.append(
            WarningRecord(
                warning_id="external_link_not_refreshed",
                message="External links were not loaded or refreshed.",
            )
        )
    return tuple(warnings)


def _row_has_valid_value(row: tuple[Scalar, ...]) -> bool:
    return any(
        value is not None and not (isinstance(value, float) and not math.isfinite(value))
        for value in row
    )


def build_candidate(
    *,
    display_name: str,
    source_hash: str,
    recipe: ImportRecipe,
    headers: tuple[str, ...],
    unit_source_texts: tuple[str, ...] | None = None,
    rows: tuple[tuple[Scalar, ...], ...],
    coordinates: tuple[SourceCoordinate, ...],
    metadata: dict[str, str] | None = None,
    postamble: tuple[str, ...] = (),
    provenance: tuple[ProvenanceMarker, ...] = (),
    trace: tuple[TraceEvent, ...] = (),
) -> SourceDatasetArtifact:
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
    if unit_source_texts is not None and len(unit_source_texts) != width:
        raise ValueError("one unit source text is required for every field")
    if any(len(row) != width for row in rows):
        raise ImportProblem(
            ImportErrorCode.ROW_WIDTH_MISMATCH,
            "数据行列数不一致。",
            "请修复不规则行，或将不同数据块拆分后重新导入。",
        )
    if len(coordinates) != len(rows):
        raise ValueError("one source coordinate is required for every data row")

    fields: list[SourceField] = []
    total_missing = total_nan = total_pos_inf = total_neg_inf = 0
    for index, normalized_name in enumerate(normalized):
        values = tuple(row[index] for row in rows)
        types = {_physical_type(value) for value in values}
        useful_types = types - {"null"}
        logical_type = _logical_type(types)
        precision = None
        if logical_type == "numeric":
            precision = 15 if "float64" in types else 0
        field_id = "field:" + stable_hash((normalized_name,))[:24]
        total_missing += sum(value is None for value in values)
        total_nan += sum(isinstance(value, float) and math.isnan(value) for value in values)
        total_pos_inf += sum(value == float("inf") for value in values)
        total_neg_inf += sum(value == float("-inf") for value in values)
        fields.append(
            SourceField(
                field_id=field_id,
                name=normalized_name,
                logical_type=logical_type,
                physical_type="+".join(sorted(useful_types)) if useful_types else "null",
                unit=(
                    _unit(f"[{unit_source_texts[index]}]")
                    if unit_source_texts is not None and unit_source_texts[index]
                    else _unit(normalized_name)
                ),
                source_column_index=index,
                precision_digits=precision,
            )
        )

    dataset_id = "source:" + stable_hash((source_hash, _canonical_recipe(recipe)))[:24]
    quality = DataQualitySummary(
        total_rows=len(rows),
        valid_rows=sum(_row_has_valid_value(row) for row in rows),
        missing_values=total_missing,
        nan_values=total_nan,
        positive_inf_values=total_pos_inf,
        negative_inf_values=total_neg_inf,
        unparseable_values=0,
        warnings=_quality_warnings(provenance),
    )
    from plotagent.importing.serialization import table_to_parquet_bytes

    parquet_bytes = table_to_parquet_bytes(
        source_dataset_id=dataset_id,
        source_object_hash=source_hash,
        fields=tuple(fields),
        rows=rows,
        coordinates=coordinates,
        recipe=recipe,
        quality=quality,
    )
    content_hash = sha256_bytes(parquet_bytes)
    source_dataset = SourceDataset(
        source_dataset_id=dataset_id,
        source_version=1,
        source_object_hash=source_hash,
        content_hash=content_hash,
        import_recipe_version=recipe.schema_version,
        parser_version=recipe.parser_version,
        unicode_normalization_version="unicode.nfc.v1",
        field_schema=tuple(fields),
        data_ref=ContentTableRef(
            object_hash=content_hash,
            row_count=len(rows),
            field_ids=tuple(field.field_id for field in fields),
        ),
        quality=quality,
        source_coordinate_samples=_coordinate_samples(coordinates),
    )
    return SourceDatasetArtifact(
        display_name=display_name,
        source_dataset=source_dataset,
        recipe=recipe,
        rows=rows,
        coordinates=coordinates,
        instrument_metadata=metadata or {},
        postamble=postamble,
        provenance=provenance,
        parquet_bytes=parquet_bytes,
        trace=trace,
    )
