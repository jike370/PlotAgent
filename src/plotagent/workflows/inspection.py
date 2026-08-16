"""Budgeted, read-only data inspection tools exposed to the bundled Agent."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from plotagent.contracts.workflows import (
    FieldProfile,
    InspectionAudit,
    RowPage,
    SchemaComparison,
    SourceInspection,
    WorkflowContext,
    WorkflowScalar,
)


class InspectionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class InspectionDataProvider(Protocol):
    def rows(self, source_alias: str) -> tuple[tuple[WorkflowScalar, ...], ...]: ...


@dataclass(slots=True)
class _Usage:
    tool_calls: int = 0
    preview_rows: int = 0
    profiled_fields: set[str] = field(default_factory=set)
    disclosed_scalars: int = 0


class DataInspectionService:
    """Expose bounded facts while recording every disclosure."""

    def __init__(self, context: WorkflowContext, provider: InspectionDataProvider) -> None:
        self.context = context
        self.provider = provider
        self._usage = _Usage()
        self._audits: list[InspectionAudit] = []

    @property
    def audits(self) -> tuple[InspectionAudit, ...]:
        return tuple(self._audits)

    def inspect_source(self, source_alias: str) -> SourceInspection:
        source = self._source(source_alias)
        fields = tuple(item for item in self.context.fields if item.source_alias == source_alias)
        self._record("inspect_source", (source_alias,), len(fields), 0, 0)
        return SourceInspection(
            source_alias=source_alias,
            display_name=source.display_name,
            row_count=source.row_count,
            fields=fields,
        )

    def preview_rows(
        self,
        source_alias: str,
        field_aliases: tuple[str, ...],
        *,
        offset: int = 0,
        limit: int = 5,
    ) -> RowPage:
        if offset < 0 or limit < 1 or limit > 40:
            raise InspectionError("INSPECTION_RANGE_INVALID", "预览范围无效。")
        fields = self._fields(source_alias, field_aliases)
        rows = self.provider.rows(source_alias)
        requested_rows = min(limit, max(0, len(rows) - offset))
        if self._usage.preview_rows + requested_rows > self.context.budget.max_preview_rows:
            raise InspectionError("INSPECTION_BUDGET_EXCEEDED", "本轮数据预览预算已用完。")
        source_fields = tuple(
            item for item in self.context.fields if item.source_alias == source_alias
        )
        positions = {item.field_alias: index for index, item in enumerate(source_fields)}
        selected = tuple(
            tuple(row[positions[field.field_alias]] for field in fields)
            for row in rows[offset : offset + limit]
        )
        scalar_count = sum(len(row) for row in selected)
        self._record("preview_rows", (source_alias,), len(fields), len(selected), scalar_count)
        return RowPage(
            source_alias=source_alias,
            field_aliases=tuple(field.field_alias for field in fields),
            offset=offset,
            rows=selected,
            has_more=offset + len(selected) < len(rows),
        )

    def profile_field(self, source_alias: str, field_alias: str) -> FieldProfile:
        field = self._fields(source_alias, (field_alias,))[0]
        if (
            field_alias not in self._usage.profiled_fields
            and len(self._usage.profiled_fields) >= self.context.budget.max_profiled_fields
        ):
            raise InspectionError("INSPECTION_BUDGET_EXCEEDED", "本轮字段分析预算已用完。")
        source_fields = tuple(
            item for item in self.context.fields if item.source_alias == source_alias
        )
        position = next(index for index, item in enumerate(source_fields) if item == field)
        values = tuple(row[position] for row in self.provider.rows(source_alias))
        valid = tuple(value for value in values if value is not None)
        numeric = tuple(
            float(value)
            for value in valid
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
        examples = tuple(dict.fromkeys(valid))[:8]
        self._usage.profiled_fields.add(field_alias)
        self._record("profile_field", (source_alias,), 1, 0, len(examples))
        return FieldProfile(
            source_alias=source_alias,
            field_alias=field_alias,
            valid_count=len(valid),
            missing_count=len(values) - len(valid),
            distinct_count=len(set(map(repr, valid))),
            numeric_minimum=min(numeric) if numeric else None,
            numeric_maximum=max(numeric) if numeric else None,
            examples=examples,
        )

    def compare_schemas(self, source_aliases: tuple[str, ...]) -> SchemaComparison:
        if not 2 <= len(source_aliases) <= 8 or len(source_aliases) != len(set(source_aliases)):
            raise InspectionError(
                "INSPECTION_SOURCES_INVALID", "结构比较需要 2 至 8 个不同数据表。"
            )
        names_by_source: dict[str, tuple[str, ...]] = {}
        for alias in source_aliases:
            self._source(alias)
            names_by_source[alias] = tuple(
                field.name for field in self.context.fields if field.source_alias == alias
            )
        common = set(names_by_source[source_aliases[0]])
        for names in names_by_source.values():
            common &= set(names)
        common_ordered = tuple(
            name for name in names_by_source[source_aliases[0]] if name in common
        )
        only = {
            alias: tuple(name for name in names if name not in common)
            for alias, names in names_by_source.items()
        }
        isomorphic = len({names for names in names_by_source.values()}) == 1
        self._record(
            "compare_schemas",
            source_aliases,
            sum(len(names) for names in names_by_source.values()),
            0,
            0,
        )
        return SchemaComparison(
            source_aliases=source_aliases,
            common_field_names=common_ordered,
            only_by_source=only,
            isomorphic=isomorphic,
        )

    def _source(self, source_alias: str):  # type: ignore[no-untyped-def]
        source = next(
            (item for item in self.context.sources if item.source_alias == source_alias),
            None,
        )
        if source is None:
            raise InspectionError("SOURCE_ALIAS_INVALID", "数据表别名不可用。")
        return source

    def _fields(self, source_alias: str, aliases: tuple[str, ...]):  # type: ignore[no-untyped-def]
        self._source(source_alias)
        if not aliases or len(aliases) != len(set(aliases)):
            raise InspectionError("FIELD_ALIAS_INVALID", "字段别名必须非空且互不重复。")
        by_alias = {
            item.field_alias: item
            for item in self.context.fields
            if item.source_alias == source_alias
        }
        try:
            return tuple(by_alias[alias] for alias in aliases)
        except KeyError as error:
            raise InspectionError("FIELD_ALIAS_INVALID", "字段别名不属于所选数据表。") from error

    def _record(
        self,
        tool_name: str,
        source_aliases: tuple[str, ...],
        field_count: int,
        row_count: int,
        scalar_count: int,
    ) -> None:
        if self._usage.tool_calls >= self.context.budget.max_tool_calls:
            raise InspectionError("INSPECTION_BUDGET_EXCEEDED", "本轮数据检查调用预算已用完。")
        if self._usage.disclosed_scalars + scalar_count > self.context.budget.max_disclosed_scalars:
            raise InspectionError("INSPECTION_BUDGET_EXCEEDED", "本轮数据披露预算已用完。")
        self._usage.tool_calls += 1
        self._usage.preview_rows += row_count
        self._usage.disclosed_scalars += scalar_count
        self._audits.append(
            InspectionAudit(
                workflow_run_id=self.context.workflow_run_id,
                tool_name=tool_name,  # type: ignore[arg-type]
                source_aliases=source_aliases,
                disclosed_field_count=field_count,
                disclosed_row_count=row_count,
                disclosed_scalar_count=scalar_count,
            )
        )
