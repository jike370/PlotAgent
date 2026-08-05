"""Stable, owner-tagged error registry shared across workstreams."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints, model_validator

from plotagent.contracts.base import SCHEMA_VERSION, SchemaVersion, StrictModel

ErrorOwner = Literal[
    "W0_CONTRACTS",
    "W2_DATA",
    "W3_CALCULATIONS",
    "W4_RENDERING",
    "W5_WORKFLOW",
    "W6_ORIGIN",
    "W7_AGENT",
]
ErrorCode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{2,95}$", strict=True),
]


class ErrorDefinition(StrictModel):
    code: ErrorCode
    owner: ErrorOwner
    retryable: bool
    default_severity: Literal["info", "warning", "blocked"]
    description: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]


class ErrorRegistry(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    errors: tuple[ErrorDefinition, ...]

    @model_validator(mode="after")
    def unique_codes(self) -> ErrorRegistry:
        codes = tuple(error.code for error in self.errors)
        if len(set(codes)) != len(codes):
            raise ValueError("stable error codes must be unique")
        return self


def _error(
    code: str,
    owner: ErrorOwner,
    retryable: bool,
    severity: Literal["info", "warning", "blocked"],
    description: str,
) -> ErrorDefinition:
    return ErrorDefinition(
        code=code,
        owner=owner,
        retryable=retryable,
        default_severity=severity,
        description=description,
    )


STABLE_ERROR_REGISTRY = ErrorRegistry(
    errors=(
        _error(
            "SCHEMA_INVALID", "W0_CONTRACTS", False, "blocked", "Payload failed schema validation."
        ),
        _error(
            "SCHEMA_VERSION_UNSUPPORTED",
            "W0_CONTRACTS",
            False,
            "blocked",
            "The schema version is not supported by this build.",
        ),
        _error(
            "SCHEMA_GENERATION_OUT_OF_SYNC",
            "W0_CONTRACTS",
            False,
            "blocked",
            "Checked-in schemas or generated types differ from the contract source.",
        ),
        _error(
            "PROTOCOL_INVALID", "W0_CONTRACTS", False, "blocked", "Protocol envelope is invalid."
        ),
        _error(
            "ERROR_CODE_UNKNOWN",
            "W0_CONTRACTS",
            False,
            "blocked",
            "An unregistered error code was used.",
        ),
        _error(
            "MAPPING_REQUIRED_ROLE_MISSING",
            "W2_DATA",
            False,
            "blocked",
            "A required chart field role is not mapped.",
        ),
        _error(
            "MAPPING_DUPLICATE_ROLE",
            "W2_DATA",
            False,
            "blocked",
            "A field mapping contains the same semantic role more than once.",
        ),
        _error(
            "PREPARE_UNSUPPORTED",
            "W2_DATA",
            False,
            "blocked",
            "The requested preparation is outside v1.",
        ),
        _error(
            "PREPARE_NON_ISOMORPHIC",
            "W2_DATA",
            False,
            "blocked",
            "Inputs are not isomorphic under the frozen semantic signature.",
        ),
        _error(
            "PREPARE_UNIT_INCOMPATIBLE",
            "W2_DATA",
            False,
            "blocked",
            "Mapped units are incompatible.",
        ),
        _error(
            "PREPARE_NONFINITE_POLICY_REQUIRED",
            "W2_DATA",
            False,
            "blocked",
            "A fail or exclude-with-report policy is required for non-finite data.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_UNSUPPORTED",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "The chart registry does not allow this fixed plot calculation.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_VERSION_UNSUPPORTED",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "The fixed calculation algorithm version is not supported by this build.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_SHAPE_INVALID",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "Calculation columns, matrix shape, row ids, or field types are invalid.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_NONFINITE",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "Missing or non-finite calculation input is forbidden by the selected policy.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_LOG10_NONPOSITIVE",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "A Log10 field contains a non-positive plotted value.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_INSUFFICIENT_DATA",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "The fixed algorithm does not have enough valid observations.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_DOMAIN_INVALID",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "Input violates a frozen calculation domain rule.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_DUPLICATE_COORDINATE",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "Heatmap XY coordinates are not unique.",
        ),
        _error(
            "PLOTSPEC_CALCULATION_DUPLICATE_CELL",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "An input contains duplicate semantic cells that would require implicit aggregation.",
        ),
        _error(
            "PLOTSPEC_PRECOMPUTED_INPUT_REQUIRED",
            "W3_CALCULATIONS",
            False,
            "blocked",
            "A required user-provided precomputed input is missing.",
        ),
        _error(
            "PLOTSPEC_CHART_UNKNOWN",
            "W4_RENDERING",
            False,
            "blocked",
            "The chart type is not in the v1 registry.",
        ),
        _error(
            "PLOTSPEC_FAMILY_MISMATCH",
            "W4_RENDERING",
            False,
            "blocked",
            "Plot family or geometry conflicts with the chart registry.",
        ),
        _error(
            "PATCH_VERSION_CONFLICT",
            "W4_RENDERING",
            False,
            "blocked",
            "Patch expected version is stale.",
        ),
        _error(
            "BATCH_SIGNATURE_MISMATCH",
            "W5_WORKFLOW",
            False,
            "blocked",
            "Batch inputs have different signatures.",
        ),
        _error(
            "FIGURE_LAYOUT_UNSUPPORTED",
            "W5_WORKFLOW",
            False,
            "blocked",
            "Figure layout is outside the fixed v1 set.",
        ),
        _error(
            "RENDER_PLAN_HASH_MISMATCH",
            "W4_RENDERING",
            False,
            "blocked",
            "Export is not bound to the resolved render plan content.",
        ),
        _error(
            "ORIGIN_CAPABILITY_MISSING",
            "W6_ORIGIN",
            False,
            "blocked",
            "The target chart cannot meet O1 on the qualified Origin version.",
        ),
        _error(
            "AGENT_DECISION_INVALID",
            "W7_AGENT",
            False,
            "blocked",
            "Provider output is not a valid AgentDecision.",
        ),
    )
)

ERRORS_BY_CODE = {error.code: error for error in STABLE_ERROR_REGISTRY.errors}


class ErrorResponse(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    code: ErrorCode
    severity: Literal["info", "warning", "blocked"]
    retryable: bool
    message: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]

    @model_validator(mode="after")
    def registered_shape(self) -> ErrorResponse:
        definition = ERRORS_BY_CODE.get(self.code)
        if definition is None:
            raise ValueError("error code is not registered")
        if definition.retryable != self.retryable:
            raise ValueError("retryability must match the stable registry")
        return self
