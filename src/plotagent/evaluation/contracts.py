"""Strict contracts for repeatable Agent and release evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import NonEmptyText, Sha256, StrictModel

EvalLayer = Literal["E0", "E1", "E2", "E3", "E4", "E5", "E6"]
EvalSuiteKind = Literal["regression", "capability", "safety", "recovery", "exploratory"]
EvalStatus = Literal["PASS", "FAIL", "BLOCKED", "UNVERIFIED", "EVAL_INVALID"]
GraderKind = Literal["deterministic", "trace", "model", "human"]
ThresholdDirection = Literal["minimum", "maximum"]
ArtifactKind = Literal[
    "trace",
    "screenshot",
    "png",
    "svg",
    "opju",
    "fresh_reopen",
    "native_readback",
    "verification_report",
    "task_checkpoint",
    "task_event",
    "export",
    "log",
    "metadata",
]

EvalId = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$", strict=True),
]
RelativeArtifactPath = Annotated[
    str,
    StringConstraints(pattern=r"^[^:\r\n]{1,240}$", strict=True),
]


def _validate_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError("artifact path must be relative and must not traverse parents")
    return value


class FixtureAsset(StrictModel):
    fixture_id: EvalId
    path: RelativeArtifactPath
    sha256: Sha256
    byte_length: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def safe_path(self) -> FixtureAsset:
        _validate_relative_path(self.path)
        return self


class EvalBudget(StrictModel):
    max_wall_time_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    max_model_turns: Annotated[int, Field(ge=0)]
    max_tool_calls: Annotated[int, Field(ge=0)]
    max_repairs: Annotated[int, Field(ge=0)]
    max_input_tokens: Annotated[int, Field(ge=0)]
    max_output_tokens: Annotated[int, Field(ge=0)]
    max_estimated_cost: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class EvalSelection(StrictModel):
    source_fixture_ids: tuple[EvalId, ...] = ()
    profile_ids: tuple[str, ...] = ()
    plot_ids: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_values(self) -> EvalSelection:
        for values in (
            self.source_fixture_ids,
            self.profile_ids,
            self.plot_ids,
            self.permissions,
        ):
            if len(values) != len(set(values)):
                raise ValueError("evaluation selections must not contain duplicates")
        return self


class GraderSpec(StrictModel):
    grader_id: EvalId
    kind: GraderKind
    claim: NonEmptyText
    required: bool = True


class EvidenceRequirement(StrictModel):
    requirement_id: EvalId
    artifact_kind: ArtifactKind
    minimum_count: Annotated[int, Field(ge=1)] = 1
    description: NonEmptyText


class EvalCase(StrictModel):
    schema_version: Literal["eval-case.v1"] = "eval-case.v1"
    eval_case_id: EvalId
    suite_id: EvalId
    suite_version: Annotated[int, Field(ge=1)]
    layer: EvalLayer
    suite_kind: EvalSuiteKind
    claim: NonEmptyText
    instruction: str = ""
    locale: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$", strict=True),
    ] = "zh-CN"
    fixtures: tuple[FixtureAsset, ...] = ()
    initial_state: dict[str, object] = Field(default_factory=dict)
    selection: EvalSelection = Field(default_factory=EvalSelection)
    environment: dict[str, str] = Field(default_factory=dict)
    component_versions: dict[str, str] = Field(default_factory=dict)
    budget: EvalBudget
    required_outcomes: tuple[NonEmptyText, ...]
    forbidden_outcomes: tuple[NonEmptyText, ...] = ()
    graders: tuple[GraderSpec, ...]
    evidence_requirements: tuple[EvidenceRequirement, ...] = ()
    trial_count: Annotated[int, Field(ge=1)] | None = None
    blocks_release: bool = True
    reference_artifact_hashes: tuple[Sha256, ...] = ()

    @model_validator(mode="after")
    def validate_case(self) -> EvalCase:
        fixture_ids = {fixture.fixture_id for fixture in self.fixtures}
        if not set(self.selection.source_fixture_ids).issubset(fixture_ids):
            raise ValueError("selected fixture ids must exist in the fixture manifest")
        if len(self.graders) == 0:
            raise ValueError("an evaluation case must have at least one grader")
        for values, label in (
            (tuple(item.grader_id for item in self.graders), "grader ids"),
            (
                tuple(item.requirement_id for item in self.evidence_requirements),
                "evidence requirement ids",
            ),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        if not any(grader.required for grader in self.graders):
            raise ValueError("an evaluation case must have a required grader")
        return self


class MetricThreshold(StrictModel):
    metric: EvalId
    direction: ThresholdDirection
    value: Annotated[float, Field(allow_inf_nan=False)]


class EvalPolicy(StrictModel):
    schema_version: Literal["eval-policy.v1"] = "eval-policy.v1"
    policy_id: EvalId
    suite_id: EvalId
    suite_version: Annotated[int, Field(ge=1)]
    frozen_at: datetime
    required_layers: tuple[EvalLayer, ...]
    trials_by_layer: dict[EvalLayer, Annotated[int, Field(ge=1)]]
    thresholds: tuple[MetricThreshold, ...] = ()
    critical_trial_count: Annotated[int, Field(ge=1)] = 3
    require_clean_commit: bool = True
    require_fixture_hashes: bool = True
    require_evidence_hashes: bool = True

    @model_validator(mode="after")
    def validate_policy(self) -> EvalPolicy:
        if len(self.required_layers) != len(set(self.required_layers)):
            raise ValueError("required layers must be unique")
        if not set(self.required_layers).issubset(self.trials_by_layer):
            raise ValueError("every required layer must have a frozen trial count")
        metric_names = tuple(item.metric for item in self.thresholds)
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("metric thresholds must be unique")
        return self


class GraderResult(StrictModel):
    grader_id: EvalId
    kind: GraderKind
    status: EvalStatus
    summary: NonEmptyText
    observed: dict[str, object] = Field(default_factory=dict)


class EvidenceArtifact(StrictModel):
    artifact_id: EvalId
    kind: ArtifactKind
    path: RelativeArtifactPath
    sha256: Sha256
    byte_length: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def safe_path(self) -> EvidenceArtifact:
        _validate_relative_path(self.path)
        return self


class EvidenceManifest(StrictModel):
    schema_version: Literal["eval-evidence.v1"] = "eval-evidence.v1"
    manifest_id: EvalId
    eval_case_id: EvalId
    trial_id: EvalId
    git_commit: Sha256
    generated_at: datetime
    artifacts: tuple[EvidenceArtifact, ...]
    environment: dict[str, str]

    @model_validator(mode="after")
    def unique_artifacts(self) -> EvidenceManifest:
        values = tuple(item.artifact_id for item in self.artifacts)
        if len(values) != len(set(values)):
            raise ValueError("evidence artifact ids must be unique")
        return self


class EvalTrial(StrictModel):
    schema_version: Literal["eval-trial.v1"] = "eval-trial.v1"
    trial_id: EvalId
    eval_case_id: EvalId
    trial_index: Annotated[int, Field(ge=1)]
    status: EvalStatus
    started_at: datetime
    completed_at: datetime
    git_commit: Sha256
    evidence_manifest_id: EvalId
    grader_results: tuple[GraderResult, ...]
    metrics: dict[str, Annotated[float, Field(allow_inf_nan=False)]] = Field(default_factory=dict)
    failure_code: EvalId | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def validate_trial(self) -> EvalTrial:
        if self.completed_at < self.started_at:
            raise ValueError("trial completion must not precede its start")
        grader_ids = tuple(item.grader_id for item in self.grader_results)
        if len(grader_ids) != len(set(grader_ids)):
            raise ValueError("trial grader results must be unique")
        if self.status == "PASS" and any(item.status != "PASS" for item in self.grader_results):
            raise ValueError("a passing trial cannot contain a non-passing grader")
        if self.status in {"FAIL", "BLOCKED", "EVAL_INVALID"} and not self.failure_message:
            raise ValueError("non-passing terminal trials require a failure message")
        return self


class EvalCaseResult(StrictModel):
    eval_case_id: EvalId
    layer: EvalLayer
    status: EvalStatus
    passed_trials: Annotated[int, Field(ge=0)]
    expected_trials: Annotated[int, Field(ge=1)]
    observed_trials: Annotated[int, Field(ge=0)]
    trial_ids: tuple[EvalId, ...]
    summary: NonEmptyText


class EvalRunReport(StrictModel):
    schema_version: Literal["eval-run-report.v1"] = "eval-run-report.v1"
    run_id: EvalId
    policy_id: EvalId
    suite_id: EvalId
    suite_version: Annotated[int, Field(ge=1)]
    git_commit: Sha256
    generated_at: datetime
    decision: Literal["GO", "NO_GO", "EVAL_INVALID"]
    case_results: tuple[EvalCaseResult, ...]
    metrics: dict[str, Annotated[float, Field(allow_inf_nan=False)]]
    gate_failures: tuple[str, ...]
