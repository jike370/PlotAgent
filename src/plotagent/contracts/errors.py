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


WORKFLOW_ERROR_DEFINITIONS: tuple[
    tuple[str, bool, Literal["info", "warning", "blocked"], str], ...
] = (
    (
        "ACTION_NOT_ALLOWED",
        False,
        "blocked",
        "The requested visual action is not allowed by the selected profile.",
    ),
    (
        "FIELD_ALIAS_INVALID",
        False,
        "blocked",
        "A task references a field alias outside its workflow context.",
    ),
    (
        "FIELD_SOURCE_INVALID",
        False,
        "blocked",
        "A field binding does not belong to the declared source.",
    ),
    (
        "PLOT_ALIAS_INVALID",
        False,
        "blocked",
        "A task references a plot alias outside its workflow context.",
    ),
    (
        "PROFILE_NOT_ALLOWED",
        False,
        "blocked",
        "The requested chart profile is outside the workflow allowlist.",
    ),
    (
        "PROFILE_TARGET_MISMATCH",
        False,
        "blocked",
        "The selected plot does not use the requested profile.",
    ),
    (
        "REQUIRED_ROLE_MISSING",
        False,
        "blocked",
        "A workflow task is missing a required chart role.",
    ),
    (
        "ROLE_NOT_ALLOWED",
        False,
        "blocked",
        "A workflow binding uses a role not declared by the chart profile.",
    ),
    (
        "SOURCE_ALIAS_INVALID",
        False,
        "blocked",
        "A task references a source alias outside its workflow context.",
    ),
    (
        "TARGET_ALIAS_INVALID",
        False,
        "blocked",
        "A visual action target is not exposed by the selected chart profile.",
    ),
    (
        "TARGET_KIND_INVALID",
        False,
        "blocked",
        "A visual action target has the wrong semantic object kind.",
    ),
    (
        "WORKFLOW_CONTEXT_MISMATCH",
        False,
        "blocked",
        "A task draft does not belong to the active workflow run.",
    ),
    (
        "WORKFLOW_DRAFT_MISSING",
        False,
        "blocked",
        "The confirmed workflow no longer has its immutable task draft.",
    ),
    (
        "WORKFLOW_BINDING_OUTPUT_MISSING",
        False,
        "blocked",
        "A prepared data result does not contain a bound output field.",
    ),
    (
        "WORKFLOW_EMPTY_RESULT",
        False,
        "blocked",
        "A data operation produced no rows for plotting.",
    ),
    (
        "WORKFLOW_NON_ISOMORPHIC",
        False,
        "blocked",
        "The selected sources are not structurally compatible for this operation.",
    ),
    (
        "WORKFLOW_RESHAPE_DUPLICATE",
        False,
        "blocked",
        "A reshape operation found duplicate semantic coordinates.",
    ),
    (
        "WORKFLOW_SORT_TYPE_INVALID",
        False,
        "blocked",
        "A sort operation encountered incomparable values.",
    ),
    (
        "WORKFLOW_SOURCE_UNUSED",
        False,
        "blocked",
        "A declared workflow source is not consumed by the compiled task.",
    ),
    (
        "WORKFLOW_SOURCES_NOT_COMBINED",
        False,
        "blocked",
        "A multi-source task did not resolve to one prepared view.",
    ),
    (
        "WORKFLOW_EDIT_TARGET_INVALID",
        False,
        "blocked",
        "An edit task does not resolve to one persisted plot target.",
    ),
    (
        "WORKFLOW_PLAN_NOT_RUNNABLE",
        False,
        "blocked",
        "The task plan has not been confirmed or is already terminal.",
    ),
    (
        "UPSTREAM_TASK_ITEM_FAILED",
        True,
        "blocked",
        "A task item cannot run because one of its dependencies failed.",
    ),
    (
        "PROJECT_VERSION_CONFLICT",
        True,
        "blocked",
        "The project revision changed before the task item committed.",
    ),
    (
        "INSPECTION_BUDGET_EXCEEDED",
        False,
        "blocked",
        "The workflow exhausted its bounded data inspection budget.",
    ),
    (
        "INSPECTION_RANGE_INVALID",
        False,
        "blocked",
        "The requested inspection row range is outside the permitted window.",
    ),
    (
        "INSPECTION_SOURCES_INVALID",
        False,
        "blocked",
        "The requested schema comparison source set is invalid.",
    ),
    (
        "SOURCE_DUPLICATED",
        False,
        "blocked",
        "The same source version was selected more than once.",
    ),
    ("SOURCE_INVALID", False, "blocked", "The selected workflow source payload is invalid."),
    (
        "SOURCE_LIMIT_EXCEEDED",
        False,
        "blocked",
        "The workflow source selection exceeds the fixed limit.",
    ),
    (
        "SOURCE_REQUIRED",
        False,
        "blocked",
        "This workflow requires at least one selected source.",
    ),
    (
        "WORKFLOW_RECIPE_EXPORT_UNVERIFIED",
        False,
        "blocked",
        "The recipe is not backed by a verified export of a successful plan output.",
    ),
    (
        "WORKFLOW_RECIPE_PLAN_INCOMPLETE",
        False,
        "blocked",
        "Only a completely successful task plan can be saved as a recipe.",
    ),
    (
        "WORKFLOW_TOOL_UNKNOWN",
        False,
        "blocked",
        "The requested data inspection tool is not available.",
    ),
)

WORKFLOW_ERROR_REGISTRY = tuple(
    _error(code, "W5_WORKFLOW", retryable, severity, description)
    for code, retryable, severity, description in WORKFLOW_ERROR_DEFINITIONS
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
            "IMPORT_FORMAT_UNSUPPORTED",
            "W2_DATA",
            False,
            "blocked",
            "The selected source format is outside the deterministic import set.",
        ),
        _error(
            "IMPORT_BINARY_UNSUPPORTED",
            "W2_DATA",
            False,
            "blocked",
            "The selected source contains unsupported binary content.",
        ),
        _error(
            "IMPORT_ENCODING_AMBIGUOUS",
            "W2_DATA",
            True,
            "blocked",
            "Text encoding requires one explicit clarification.",
        ),
        _error(
            "IMPORT_ENCODING_UNSUPPORTED",
            "W2_DATA",
            True,
            "blocked",
            "The source cannot be decoded with the selected text encoding.",
        ),
        _error(
            "IMPORT_DELIMITER_AMBIGUOUS",
            "W2_DATA",
            True,
            "blocked",
            "Multiple delimiters are equally plausible and require clarification.",
        ),
        _error(
            "IMPORT_DECIMAL_AMBIGUOUS",
            "W2_DATA",
            True,
            "blocked",
            "Multiple decimal conventions are equally plausible and require clarification.",
        ),
        _error(
            "IMPORT_HEADER_AMBIGUOUS",
            "W2_DATA",
            True,
            "blocked",
            "The source header requires one explicit clarification.",
        ),
        _error(
            "IMPORT_REGION_AMBIGUOUS",
            "W2_DATA",
            True,
            "blocked",
            "Multiple table regions are equally plausible and require clarification.",
        ),
        _error(
            "IMPORT_DUPLICATE_HEADERS",
            "W2_DATA",
            True,
            "blocked",
            "Normalized source headers are not unique.",
        ),
        _error(
            "IMPORT_ROW_WIDTH_MISMATCH",
            "W2_DATA",
            True,
            "blocked",
            "Rows in a candidate data block have inconsistent widths.",
        ),
        _error(
            "IMPORT_NO_DATA",
            "W2_DATA",
            True,
            "blocked",
            "No supported tabular data block was detected.",
        ),
        _error(
            "IMPORT_PARSER_FAILED",
            "W2_DATA",
            True,
            "blocked",
            "The read-only parser failed before formal registration.",
        ),
        _error(
            "FORMULA_UNCACHED",
            "W2_DATA",
            False,
            "warning",
            "A formula had no cached value and was imported as missing.",
        ),
        _error(
            "MACRO_CONTENT_IGNORED",
            "W2_DATA",
            False,
            "info",
            "Workbook macro content was ignored and never executed.",
        ),
        _error(
            "EXTERNAL_LINK_NOT_REFRESHED",
            "W2_DATA",
            False,
            "warning",
            "Workbook external links were not loaded or refreshed.",
        ),
        _error(
            "WORKSPACE_FILESYSTEM_UNSUPPORTED",
            "W2_DATA",
            False,
            "blocked",
            "An active SQLite/WAL workspace must use a local fixed disk.",
        ),
        _error(
            "PROJECT_STORAGE_ALREADY_EXISTS",
            "W2_DATA",
            False,
            "blocked",
            "The requested project workspace already exists.",
        ),
        _error(
            "PROJECT_STORAGE_NOT_FOUND",
            "W2_DATA",
            False,
            "blocked",
            "The requested project workspace does not exist.",
        ),
        _error(
            "PROJECT_STORAGE_ALREADY_OPEN",
            "W2_DATA",
            True,
            "blocked",
            "The project workspace already has an active writer.",
        ),
        _error(
            "PROJECT_STORAGE_WRITER_THREAD",
            "W2_DATA",
            False,
            "blocked",
            "A project mutation was attempted outside its single writer thread.",
        ),
        _error(
            "PROJECT_STORAGE_CLOSED",
            "W2_DATA",
            False,
            "blocked",
            "A project mutation was attempted after storage was closed.",
        ),
        _error(
            "PROJECT_STORAGE_STAGED_OBJECT_INVALID",
            "W2_DATA",
            True,
            "blocked",
            "A staged object's path, size, or SHA-256 did not validate.",
        ),
        _error(
            "PROJECT_STORAGE_SOURCE_OBJECT_MISSING",
            "W2_DATA",
            True,
            "blocked",
            "A dataset was not bound to its staged immutable source object.",
        ),
        _error(
            "PROJECT_STORAGE_COMMIT_FAILED",
            "W2_DATA",
            True,
            "blocked",
            "Atomic project registration failed without publishing partial state.",
        ),
        _error(
            "PROJECT_STORAGE_CATALOG_FAILED",
            "W2_DATA",
            True,
            "blocked",
            "Minimal catalog registration failed.",
        ),
        _error(
            "PROJECT_STORAGE_OBJECT_NOT_FOUND",
            "W2_DATA",
            False,
            "blocked",
            "The requested immutable project object does not exist.",
        ),
        _error(
            "VERSION_CONFLICT",
            "W2_DATA",
            True,
            "blocked",
            "The project or object version changed before the operation committed.",
        ),
        _error(
            "IDEMPOTENCY_CONFLICT",
            "W2_DATA",
            False,
            "blocked",
            "An idempotency key was reused for a different request.",
        ),
        _error(
            "TASK_BUDGET_EXCEEDED",
            "W2_DATA",
            False,
            "blocked",
            "A durable task budget would be exceeded by the requested operation.",
        ),
        _error(
            "ARCHIVE_UNSAFE_PATH",
            "W2_DATA",
            False,
            "blocked",
            "A package entry has an absolute, traversing, reserved, or unknown path.",
        ),
        _error(
            "ARCHIVE_LINK_REJECTED",
            "W2_DATA",
            False,
            "blocked",
            "A package contains a link, reparse point, or special entry.",
        ),
        _error(
            "ARCHIVE_DUPLICATE_PATH",
            "W2_DATA",
            False,
            "blocked",
            "A package contains duplicate normalized paths.",
        ),
        _error(
            "ARCHIVE_LIMIT_EXCEEDED",
            "W2_DATA",
            False,
            "blocked",
            "A package exceeds an entry count or expanded-size limit.",
        ),
        _error(
            "ARCHIVE_BOMB_SUSPECTED",
            "W2_DATA",
            False,
            "blocked",
            "A package has an unsafe per-entry or total compression ratio.",
        ),
        _error(
            "PROJECT_PACKAGE_HASH_INVALID",
            "W2_DATA",
            False,
            "blocked",
            "A package file or referenced object failed SHA-256 verification.",
        ),
        _error(
            "PROJECT_PACKAGE_MANIFEST_INVALID",
            "W2_DATA",
            False,
            "blocked",
            "Package manifest, structure, SQLite snapshot, or references are inconsistent.",
        ),
        _error(
            "PROJECT_PACKAGE_TYPE_UNSUPPORTED",
            "W2_DATA",
            False,
            "blocked",
            "This build supports only full project packages.",
        ),
        _error(
            "PROJECT_PACKAGE_EXPORT_FAILED",
            "W2_DATA",
            True,
            "blocked",
            "Package export failed before atomic target replacement.",
        ),
        _error(
            "PROJECT_PACKAGE_IMPORT_FAILED",
            "W2_DATA",
            True,
            "blocked",
            "Package import failed without catalog or formal-workspace publication.",
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
            "BATCH_IDEMPOTENCY_CONFLICT",
            "W5_WORKFLOW",
            False,
            "blocked",
            "A batch idempotency key was reused with different inputs.",
        ),
        _error(
            "BATCH_ITEM_EXECUTION_FAILED",
            "W5_WORKFLOW",
            True,
            "blocked",
            "A batch item failed before its output commit completed.",
        ),
        _error(
            "BATCH_COMMIT_FAILED",
            "W5_WORKFLOW",
            True,
            "blocked",
            "A batch commit failed without publishing a partial output.",
        ),
        _error(
            "BATCH_TASK_NOT_CANCELLABLE",
            "W5_WORKFLOW",
            False,
            "blocked",
            "The batch task is terminal or inside its non-cancellable commit boundary.",
        ),
        _error(
            "BATCH_EXPORT_SCOPE_EMPTY",
            "W5_WORKFLOW",
            False,
            "blocked",
            "No succeeded and confirmed batch items remain in the requested export scope.",
        ),
        *WORKFLOW_ERROR_REGISTRY,
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
            "TASK_DRAFT_INVALID",
            "W7_AGENT",
            False,
            "blocked",
            "The proposed task draft does not satisfy the workflow contract.",
        ),
        _error(
            "PROVIDER_CONNECTION_FAILED",
            "W7_AGENT",
            True,
            "blocked",
            "The configured model provider could not complete the request.",
        ),
        _error(
            "PROVIDER_UNSUPPORTED",
            "W7_AGENT",
            False,
            "blocked",
            "The provider cannot produce the required structured decision.",
        ),
        _error(
            "REQUEST_TIMEOUT",
            "W7_AGENT",
            True,
            "blocked",
            "The model request exceeded its fixed timeout.",
        ),
        _error(
            "REQUEST_CANCELLED",
            "W7_AGENT",
            True,
            "info",
            "The model request was cancelled before a complete decision was accepted.",
        ),
        _error(
            "WORKFLOW_AGENT_EXHAUSTED",
            "W7_AGENT",
            False,
            "blocked",
            "The bounded Agent run ended without one valid task draft.",
        ),
        _error(
            "WORKFLOW_CONTEXT_TOO_LARGE",
            "W7_AGENT",
            False,
            "blocked",
            "The bounded workflow context cannot fit the configured egress budget.",
        ),
        _error(
            "EGRESS_PERMISSION_DENIED",
            "W7_AGENT",
            False,
            "blocked",
            "The required data disclosure category is not authorized.",
        ),
        _error(
            "TARGET_STALE",
            "W7_AGENT",
            True,
            "blocked",
            "The target version changed after the context was built.",
        ),
        _error(
            "PROVIDER_RETENTION_UNACKNOWLEDGED",
            "W7_AGENT",
            False,
            "blocked",
            "The provider retention disclosure has not been acknowledged.",
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
