"""Shared stable failures for local workflow services."""

from __future__ import annotations

from plotagent.contracts.errors import ERRORS_BY_CODE, ErrorResponse


class WorkflowFailure(RuntimeError):
    def __init__(self, error: ErrorResponse) -> None:
        super().__init__(error.message)
        self.error = error


def workflow_error(code: str, message: str) -> ErrorResponse:
    definition = ERRORS_BY_CODE[code]
    return ErrorResponse(
        code=code,
        severity=definition.default_severity,
        retryable=definition.retryable,
        message=message,
    )
