"""Versioned, minimized model context and disclosure contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import (
    SCHEMA_VERSION,
    ChartTypeId,
    FieldId,
    NonNegativeInt,
    ObjectId,
    SchemaVersion,
    SemanticAlias,
    Sha256,
    StrictModel,
    Token,
    VersionId,
)
from plotagent.contracts.decisions import ActionType, PatchOperation

DisclosureCategory = Literal[
    "user_instruction",
    "field_metadata",
    "statistics",
    "sample",
    "message_window",
    "chart_capabilities",
]


class ContextObjectRef(StrictModel):
    object_alias: SemanticAlias
    object_id: ObjectId
    object_version: VersionId
    object_type: Literal[
        "source_dataset",
        "prepared_dataset",
        "plot",
        "batch",
        "figure",
        "export",
        "project",
    ]
    content_hash: Sha256 | None = None


class ConversationStateProjection(StrictModel):
    state_version: VersionId
    current_target: ContextObjectRef
    selected_objects: tuple[ContextObjectRef, ...] = ()
    confirmed_field_aliases: tuple[SemanticAlias, ...] = ()
    project_rule_ids: tuple[Token, ...] = ()
    saved_setting_refs: tuple[Token, ...] = ()
    unresolved_question_ids: tuple[Token, ...] = ()
    recent_result_kinds: tuple[
        Literal["action_plan", "needs_input", "unsupported", "no_change", "execution_result"],
        ...,
    ] = ()

    @model_validator(mode="after")
    def unique_projection_refs(self) -> ConversationStateProjection:
        aliases = tuple(item.object_alias for item in self.selected_objects)
        if len(set(aliases)) != len(aliases):
            raise ValueError("selected object aliases must be unique")
        return self


class ContextFieldSummary(StrictModel):
    valid_count: NonNegativeInt
    missing_count: NonNegativeInt
    nan_count: NonNegativeInt = 0
    positive_inf_count: NonNegativeInt = 0
    negative_inf_count: NonNegativeInt = 0
    distinct_count: NonNegativeInt | None = None
    numeric_minimum: Annotated[float, Field(allow_inf_nan=False)] | None = None
    numeric_maximum: Annotated[float, Field(allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def ordered_numeric_range(self) -> ContextFieldSummary:
        if (
            self.numeric_minimum is not None
            and self.numeric_maximum is not None
            and self.numeric_minimum > self.numeric_maximum
        ):
            raise ValueError("summary numeric range must be ordered")
        return self


class ContextField(StrictModel):
    field_alias: SemanticAlias
    field_id: FieldId
    name: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    logical_type: Literal["numeric", "categorical", "datetime", "boolean", "text"]
    unit_text: Annotated[str, StringConstraints(max_length=128, strict=True)] = ""
    semantic_role: Token | None = None
    summary: ContextFieldSummary | None = None


class NonFiniteSampleValue(StrictModel):
    kind: Literal["nonfinite"] = "nonfinite"
    value: Literal["nan", "positive_inf", "negative_inf"]


SampleCellValue = str | int | float | bool | None | NonFiniteSampleValue


class ContextSampleRow(StrictModel):
    sample_key: Annotated[
        str,
        StringConstraints(pattern=r"^sample:[0-9a-f]{16}$", strict=True),
    ]
    values: dict[SemanticAlias, SampleCellValue]


class ContextMessage(StrictModel):
    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000, strict=True)]


class SelectedContext(StrictModel):
    fields: tuple[ContextField, ...] = ()
    sample_rows: tuple[ContextSampleRow, ...] = ()
    selected_objects: tuple[ContextObjectRef, ...] = ()
    message_window: tuple[ContextMessage, ...] = ()

    @model_validator(mode="after")
    def bounded_and_consistent(self) -> SelectedContext:
        if len(self.fields) > 12:
            raise ValueError("selected context exceeds the 12-field limit")
        if len(self.sample_rows) > 20:
            raise ValueError("selected context exceeds the 20-row limit")
        aliases = {field.field_alias for field in self.fields}
        if len(aliases) != len(self.fields):
            raise ValueError("context field aliases must be unique")
        if any(not set(row.values).issubset(aliases) for row in self.sample_rows):
            raise ValueError("sample cells must reference selected field aliases")
        if sum(len(row.values) for row in self.sample_rows) > 200:
            raise ValueError("selected context exceeds the 200-scalar limit")
        return self


class ChartCapabilities(StrictModel):
    capability_version: Token
    allowed_chart_type_ids: tuple[ChartTypeId, ...] = ()
    allowed_action_types: tuple[ActionType, ...]
    allowed_patch_operations: tuple[PatchOperation, ...] = ()
    export_formats: tuple[Literal["png", "svg", "opju"], ...] = ()
    limitation_ids: tuple[Token, ...] = ()


class DataDisclosure(StrictModel):
    provider_type: Literal["builtin", "custom"]
    provider_config_id: Token
    authorization_scope: Literal[
        "default_consent",
        "this_run",
        "this_conversation_similar",
    ]
    retention_disclosure_version: Token
    categories: tuple[DisclosureCategory, ...]
    field_aliases: tuple[SemanticAlias, ...]
    field_count: NonNegativeInt
    row_count: NonNegativeInt
    scalar_count: NonNegativeInt
    disclosure_hash: Sha256

    @model_validator(mode="after")
    def disclosure_counts_match(self) -> DataDisclosure:
        if self.field_count != len(self.field_aliases):
            raise ValueError("disclosure field count must match field aliases")
        if self.field_count > 12 or self.row_count > 20 or self.scalar_count > 200:
            raise ValueError("disclosure exceeds the default hard budget")
        if self.scalar_count > self.field_count * self.row_count:
            raise ValueError("disclosure scalar count exceeds the field/row product")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("disclosure categories must be unique")
        return self


class ContextEnvelope(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    prompt_template_version: Token
    locale: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})*$", strict=True),
    ]
    user_instruction: Annotated[str, StringConstraints(min_length=1, max_length=4000, strict=True)]
    target_snapshot: ContextObjectRef
    conversation_state: ConversationStateProjection
    chart_capabilities: ChartCapabilities
    selected_context: SelectedContext
    data_disclosure: DataDisclosure
    context_hash: Sha256

    @model_validator(mode="after")
    def target_matches_state(self) -> ContextEnvelope:
        if self.target_snapshot != self.conversation_state.current_target:
            raise ValueError("target snapshot must match the persistent conversation target")
        return self
