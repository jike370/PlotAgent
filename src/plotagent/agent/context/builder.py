"""Build a deterministic, minimized ContextEnvelope from local authority."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Literal

from plotagent.agent.context.state import ConversationState
from plotagent.agent.errors import AgentRuntimeError
from plotagent.contracts.agent_context import (
    ChartCapabilities,
    ContextEnvelope,
    ContextField,
    ContextFieldSummary,
    ContextMessage,
    ContextObjectRef,
    ContextSampleRow,
    DataDisclosure,
    DisclosureCategory,
    NonFiniteSampleValue,
    SampleCellValue,
    SelectedContext,
)
from plotagent.contracts.base import FieldId, SemanticAlias, Token
from plotagent.contracts.canonical import canonical_hash, canonical_json

PROMPT_TEMPLATE_VERSION: Token = "agent-decision-v2"
SAMPLING_RULE_VERSION = "context-sample-v1"


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_rows: int = 20
    max_fields: int = 12
    max_scalars: int = 200
    max_bytes: int = 65_536
    max_messages: int = 8
    max_cell_chars: int = 256

    def __post_init__(self) -> None:
        if not (0 <= self.max_rows <= 20):
            raise ValueError("max_rows must be within the product limit")
        if not (0 <= self.max_fields <= 12):
            raise ValueError("max_fields must be within the product limit")
        if not (0 <= self.max_scalars <= 200):
            raise ValueError("max_scalars must be within the product limit")
        if self.max_bytes < 512 or not (0 <= self.max_messages <= 8):
            raise ValueError("invalid context byte/message budget")
        if not (16 <= self.max_cell_chars <= 256):
            raise ValueError("invalid sample cell text limit")


@dataclass(frozen=True, slots=True)
class DisclosureGrant:
    provider_type: Literal["builtin", "custom"]
    provider_config_id: Token
    retention_disclosure_version: Token
    retention_acknowledged: bool
    allowed_categories: frozenset[DisclosureCategory]
    authorization_scope: Literal["default_consent", "this_run", "this_conversation_similar"] = (
        "default_consent"
    )


@dataclass(frozen=True, slots=True)
class AuthoritativeField:
    field_alias: SemanticAlias
    field_id: FieldId
    name: str
    logical_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    unit_text: str = ""
    semantic_role: Token | None = None
    summary: ContextFieldSummary | None = None


@dataclass(frozen=True, slots=True)
class AuthoritativeSampleRow:
    row_id: str
    values: dict[FieldId, object]


@dataclass(frozen=True, slots=True)
class AuthoritativeProjectContext:
    target: ContextObjectRef
    dataset_content_hash: str
    fields: tuple[AuthoritativeField, ...] = ()
    sample_rows: tuple[AuthoritativeSampleRow, ...] = ()
    selected_objects: tuple[ContextObjectRef, ...] = ()
    message_window: tuple[ContextMessage, ...] = ()
    explicit_field_aliases: tuple[SemanticAlias, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextBuildRequest:
    user_instruction: str
    locale: str
    project: AuthoritativeProjectContext
    conversation_state: ConversationState
    chart_capabilities: ChartCapabilities
    disclosure_grant: DisclosureGrant
    required_categories: frozenset[DisclosureCategory] = field(default_factory=frozenset)


class ContextBuilder:
    def __init__(self, budget: ContextBudget | None = None) -> None:
        self._budget = budget or ContextBudget()

    def build(self, request: ContextBuildRequest) -> ContextEnvelope:
        grant = request.disclosure_grant
        if not grant.retention_acknowledged:
            raise AgentRuntimeError("PROVIDER_RETENTION_UNACKNOWLEDGED")
        mandatory_categories: frozenset[DisclosureCategory] = frozenset(
            {"user_instruction", "chart_capabilities"}
        )
        if not (request.required_categories | mandatory_categories).issubset(
            grant.allowed_categories
        ):
            raise AgentRuntimeError("EGRESS_PERMISSION_DENIED")
        if request.project.target != request.conversation_state.current_target:
            raise AgentRuntimeError("TARGET_STALE")

        instruction = _bounded_text(request.user_instruction, 4000)
        selected_fields = self._select_fields(request, instruction)
        messages = tuple(request.project.message_window[-self._budget.max_messages :])
        sample_rows = self._select_rows(request.project, selected_fields)

        while True:
            envelope = self._assemble(
                request,
                instruction=instruction,
                fields=selected_fields,
                rows=sample_rows,
                messages=messages,
            )
            if len(canonical_json(envelope).encode("utf-8")) <= self._budget.max_bytes:
                return envelope
            if sample_rows:
                sample_rows = sample_rows[:-1]
                continue
            if messages:
                messages = messages[1:]
                continue
            if selected_fields:
                selected_fields = selected_fields[:-1]
                continue
            raise AgentRuntimeError("CONTEXT_TOO_LARGE")

    def _select_fields(
        self, request: ContextBuildRequest, instruction: str
    ) -> tuple[AuthoritativeField, ...]:
        if "field_metadata" not in request.disclosure_grant.allowed_categories:
            return ()
        explicit = set(request.project.explicit_field_aliases)
        folded_instruction = instruction.casefold()

        def rank(item: AuthoritativeField) -> tuple[int, str]:
            if item.field_alias in explicit:
                priority = 0
            elif item.name.casefold() in folded_instruction:
                priority = 1
            elif item.semantic_role is not None:
                priority = 2
            else:
                priority = 3
            return priority, item.field_id

        return tuple(sorted(request.project.fields, key=rank)[: self._budget.max_fields])

    def _select_rows(
        self,
        project: AuthoritativeProjectContext,
        fields: tuple[AuthoritativeField, ...],
    ) -> tuple[AuthoritativeSampleRow, ...]:
        if not fields or self._budget.max_scalars == 0:
            return ()
        row_limit = min(
            self._budget.max_rows,
            self._budget.max_scalars // len(fields),
        )

        def row_key(row: AuthoritativeSampleRow) -> str:
            material = (
                f"{project.dataset_content_hash}|{row.row_id}|{SAMPLING_RULE_VERSION}"
            ).encode()
            return hashlib.sha256(material).hexdigest()

        return tuple(sorted(project.sample_rows, key=row_key)[:row_limit])

    def _assemble(
        self,
        request: ContextBuildRequest,
        *,
        instruction: str,
        fields: tuple[AuthoritativeField, ...],
        rows: tuple[AuthoritativeSampleRow, ...],
        messages: tuple[ContextMessage, ...],
    ) -> ContextEnvelope:
        allowed = request.disclosure_grant.allowed_categories
        context_fields = tuple(
            ContextField(
                field_alias=item.field_alias,
                field_id=item.field_id,
                name=_bounded_text(item.name, 256),
                logical_type=item.logical_type,
                unit_text=_bounded_text(item.unit_text, 128, allow_empty=True),
                semantic_role=item.semantic_role,
                summary=item.summary if "statistics" in allowed else None,
            )
            for item in fields
        )
        context_rows = (
            tuple(self._context_row(row, fields) for row in rows) if "sample" in allowed else ()
        )
        context_messages = messages if "message_window" in allowed else ()
        selected = SelectedContext(
            fields=context_fields,
            sample_rows=context_rows,
            selected_objects=request.project.selected_objects,
            message_window=context_messages,
        )
        categories: list[DisclosureCategory] = ["user_instruction", "chart_capabilities"]
        if context_fields:
            categories.append("field_metadata")
        if any(item.summary is not None for item in context_fields):
            categories.append("statistics")
        if context_rows:
            categories.append("sample")
        if context_messages:
            categories.append("message_window")
        scalar_count = sum(len(row.values) for row in context_rows)
        disclosure_seed = DataDisclosure(
            provider_type=request.disclosure_grant.provider_type,
            provider_config_id=request.disclosure_grant.provider_config_id,
            authorization_scope=request.disclosure_grant.authorization_scope,
            retention_disclosure_version=(request.disclosure_grant.retention_disclosure_version),
            categories=tuple(categories),
            field_aliases=tuple(item.field_alias for item in context_fields),
            field_count=len(context_fields),
            row_count=len(context_rows),
            scalar_count=scalar_count,
            disclosure_hash="0" * 64,
        )
        disclosure = disclosure_seed.model_copy(
            update={
                "disclosure_hash": canonical_hash(
                    disclosure_seed.model_dump(mode="json", exclude={"disclosure_hash"})
                )
            }
        )
        envelope_seed = ContextEnvelope(
            schema_version="1.0",
            prompt_template_version=PROMPT_TEMPLATE_VERSION,
            locale=request.locale,
            user_instruction=instruction,
            target_snapshot=request.project.target,
            conversation_state=request.conversation_state.project(),
            chart_capabilities=request.chart_capabilities,
            selected_context=selected,
            data_disclosure=disclosure,
            context_hash="0" * 64,
        )
        return envelope_seed.model_copy(
            update={
                "context_hash": canonical_hash(
                    envelope_seed.model_dump(mode="json", exclude={"context_hash"})
                )
            }
        )

    def _context_row(
        self,
        row: AuthoritativeSampleRow,
        fields: tuple[AuthoritativeField, ...],
    ) -> ContextSampleRow:
        row_hash = hashlib.sha256(row.row_id.encode()).hexdigest()[:16]
        values: dict[str, SampleCellValue] = {}
        for item in fields:
            if item.field_id in row.values:
                values[item.field_alias] = self._sample_value(row.values[item.field_id])
        return ContextSampleRow(sample_key=f"sample:{row_hash}", values=values)

    def _sample_value(self, value: object) -> SampleCellValue:
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            if math.isnan(value):
                return NonFiniteSampleValue(value="nan")
            if math.isinf(value):
                return NonFiniteSampleValue(value="positive_inf" if value > 0 else "negative_inf")
            return value
        if isinstance(value, str):
            return _bounded_text(value, self._budget.max_cell_chars, allow_empty=True)
        return _bounded_text(str(value), self._budget.max_cell_chars, allow_empty=True)


def _bounded_text(value: str, limit: int, *, allow_empty: bool = False) -> str:
    normalized = value[:limit]
    if not normalized and not allow_empty:
        raise AgentRuntimeError("CONTEXT_TOO_LARGE")
    return normalized
