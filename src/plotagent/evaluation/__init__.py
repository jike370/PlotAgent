"""Versioned evaluation contracts and release aggregation for PlotAgent."""

from plotagent.evaluation.contracts import (
    EvalCase,
    EvalPolicy,
    EvalRunReport,
    EvalStatus,
    EvalTrial,
    EvidenceManifest,
    GraderResult,
)
from plotagent.evaluation.runner import aggregate_evaluation, write_evaluation_report

__all__ = [
    "EvalCase",
    "EvalPolicy",
    "EvalRunReport",
    "EvalStatus",
    "EvalTrial",
    "EvidenceManifest",
    "GraderResult",
    "aggregate_evaluation",
    "write_evaluation_report",
]
