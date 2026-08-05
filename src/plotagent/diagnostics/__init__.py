"""Local logging and preview-first diagnostic bundles."""

from plotagent.diagnostics.bundle import (
    DiagnosticPreview,
    DiagnosticSnapshot,
    LocalDiagnosticBundleBuilder,
    PreviewFile,
    SanitizedDataConsent,
    SanitizedError,
    StructureSummary,
    TaskTransition,
    VersionInfo,
)
from plotagent.diagnostics.logging import (
    CountBucket,
    LocalLogRecord,
    LogRetentionPolicy,
    PerformanceBucket,
    StructuredLocalLogger,
    TaskState,
    scrub_stack_trace,
)

__all__ = [
    "CountBucket",
    "DiagnosticPreview",
    "DiagnosticSnapshot",
    "LocalDiagnosticBundleBuilder",
    "LocalLogRecord",
    "LogRetentionPolicy",
    "PerformanceBucket",
    "PreviewFile",
    "SanitizedDataConsent",
    "SanitizedError",
    "StructureSummary",
    "StructuredLocalLogger",
    "TaskState",
    "TaskTransition",
    "VersionInfo",
    "scrub_stack_trace",
]
