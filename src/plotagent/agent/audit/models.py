"""Audit metadata deliberately excludes request/response bodies and samples."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints

from plotagent.contracts.base import ObjectId, Sha256, StrictModel, VersionId
from plotagent.contracts.canonical import canonical_hash


class AuditTargetRef(StrictModel):
    object_id: ObjectId
    object_version: VersionId
    content_hash: Sha256 | None = None


class AuditUsage(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    repair_input_tokens: int = Field(ge=0)
    repair_output_tokens: int = Field(ge=0)
    source: Literal["provider", "unavailable", "mixed"]


class ModelRunAudit(StrictModel):
    client_model_run_id: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128, strict=True),
    ]
    provider_type: Literal["builtin", "custom", "local_only"]
    provider_config_id: str
    endpoint_origin: str
    model_id: str
    model_profile: str
    deployment_id: str | None = None
    protocol: Literal["builtin_proxy", "responses", "chat_completions", "none"]
    output_capability: Literal["P1", "P2", "P0"]
    prompt_template_version: str
    prompt_template_hash: Sha256
    context_schema_version: str
    decision_schema_version: str
    decision_schema_hash: Sha256
    context_hash: Sha256
    disclosure_hash: Sha256
    disclosure_categories: tuple[str, ...]
    disclosure_field_count: int = Field(ge=0, le=12)
    disclosure_row_count: int = Field(ge=0, le=20)
    disclosure_scalar_count: int = Field(ge=0, le=200)
    target_ref: AuditTargetRef
    provider_request_ids: tuple[str, ...] = ()
    provider_response_hashes: tuple[Sha256, ...] = ()
    decision_hash: Sha256 | None = None
    started_at: datetime
    finished_at: datetime
    latency_ms: int = Field(ge=0)
    usage: AuditUsage
    status: Literal["completed", "failed", "cancelled"]
    error_code: str | None = None
    repair_count: int = Field(ge=0, le=1)


class HashedModelRunAudit(StrictModel):
    record: ModelRunAudit
    audit_hash: Sha256

    @classmethod
    def create(cls, record: ModelRunAudit) -> HashedModelRunAudit:
        return cls(record=record, audit_hash=canonical_hash(record))


class AuditSink(Protocol):
    def record(self, audit: HashedModelRunAudit) -> None: ...


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.records: list[HashedModelRunAudit] = []

    def record(self, audit: HashedModelRunAudit) -> None:
        self.records.append(audit)
