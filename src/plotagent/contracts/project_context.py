"""Authoritative project context and deterministic target-resolution contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.base import (
    SCHEMA_VERSION,
    FieldId,
    NonNegativeInt,
    SchemaVersion,
    Sha256,
    StrictModel,
    Token,
)

ConversationId = Annotated[
    str,
    StringConstraints(
        pattern=r"^conversation:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
ContextSnapshotId = Annotated[
    str,
    StringConstraints(
        pattern=r"^context:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
TargetPrecedence = Literal[
    "composer_scope",
    "explicit_turn_reference",
    "conversation_target",
    "recent_plan_output",
    "unique_candidate",
    "none",
]


class ObjectStaleness(StrictModel):
    object_alias: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
    ]
    expected_version: Annotated[int, Field(ge=1)]
    actual_version: Annotated[int, Field(ge=1)] | None = None
    reason: Literal["version_changed", "object_missing", "content_changed"]


class ContextFieldBinding(StrictModel):
    field_alias: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
    ]
    field_id: FieldId
    source_dataset_id: Annotated[
        str,
        StringConstraints(
            pattern=r"^source:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
            strict=True,
        ),
    ]
    source_version: Annotated[int, Field(ge=1)]


class ProjectContextSnapshot(StrictModel):
    """Local authority used to compile a provider proposal into executable work.

    The provider receives a minimized ``ContextEnvelope`` projection.  This richer
    snapshot remains local and binds aliases to stable object ids and versions.
    """

    schema_version: SchemaVersion = SCHEMA_VERSION
    snapshot_id: ContextSnapshotId
    snapshot_hash: Sha256
    project_id: Annotated[
        str,
        StringConstraints(
            pattern=r"^project:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
            strict=True,
        ),
    ]
    project_revision: NonNegativeInt
    conversation_id: ConversationId
    conversation_state: ConversationStateProjection
    known_objects: Annotated[tuple[ContextObjectRef, ...], Field(max_length=128)] = ()
    recent_result_objects: Annotated[tuple[ContextObjectRef, ...], Field(max_length=16)] = ()
    field_bindings: Annotated[tuple[ContextFieldBinding, ...], Field(max_length=256)] = ()
    project_rule_ids: tuple[Token, ...] = ()
    saved_setting_refs: tuple[Token, ...] = ()

    @model_validator(mode="after")
    def aliases_are_unique_and_state_is_consistent(self) -> ProjectContextSnapshot:
        aliases = tuple(item.object_alias for item in self.known_objects)
        if len(set(aliases)) != len(aliases):
            raise ValueError("known object aliases must be unique")
        selected = {item.object_alias: item for item in self.conversation_state.selected_objects}
        known = {item.object_alias: item for item in self.known_objects}
        if any(known.get(alias) != value for alias, value in selected.items()):
            raise ValueError("selected objects must match known authoritative objects")
        field_aliases = tuple(item.field_alias for item in self.field_bindings)
        if len(set(field_aliases)) != len(field_aliases):
            raise ValueError("field binding aliases must be unique")
        return self


class TargetResolution(StrictModel):
    status: Literal["resolved", "ambiguous", "missing"]
    precedence: TargetPrecedence
    target: ContextObjectRef | None = None
    candidates: Annotated[tuple[ContextObjectRef, ...], Field(max_length=8)] = ()
    question: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=512, strict=True),
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def status_matches_payload(self) -> TargetResolution:
        if self.status == "resolved":
            if self.target is None or self.candidates or self.question is not None:
                raise ValueError("resolved target must contain only target")
        elif self.status == "ambiguous":
            if self.target is not None or len(self.candidates) < 2 or self.question is None:
                raise ValueError("ambiguous target requires candidates and one question")
        elif self.target is not None or self.candidates:
            raise ValueError("missing target cannot bind authoritative objects")
        return self
