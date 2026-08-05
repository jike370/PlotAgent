"""Stable, layered errors for deterministic imports."""

from __future__ import annotations

from enum import StrEnum


class ImportErrorCode(StrEnum):
    FORMAT_UNSUPPORTED = "IMPORT_FORMAT_UNSUPPORTED"
    BINARY_UNSUPPORTED = "IMPORT_BINARY_UNSUPPORTED"
    ENCODING_AMBIGUOUS = "IMPORT_ENCODING_AMBIGUOUS"
    ENCODING_UNSUPPORTED = "IMPORT_ENCODING_UNSUPPORTED"
    DELIMITER_AMBIGUOUS = "IMPORT_DELIMITER_AMBIGUOUS"
    DECIMAL_AMBIGUOUS = "IMPORT_DECIMAL_AMBIGUOUS"
    HEADER_AMBIGUOUS = "IMPORT_HEADER_AMBIGUOUS"
    REGION_AMBIGUOUS = "IMPORT_REGION_AMBIGUOUS"
    DUPLICATE_HEADERS = "IMPORT_DUPLICATE_HEADERS"
    ROW_WIDTH_MISMATCH = "IMPORT_ROW_WIDTH_MISMATCH"
    NO_DATA = "IMPORT_NO_DATA"
    PARSER_FAILED = "IMPORT_PARSER_FAILED"
    FORMULA_UNCACHED = "FORMULA_UNCACHED"
    MACRO_CONTENT_IGNORED = "MACRO_CONTENT_IGNORED"
    EXTERNAL_LINK_NOT_REFRESHED = "EXTERNAL_LINK_NOT_REFRESHED"


class ImportProblem(Exception):
    """An expected import outcome with a stable code and recovery action."""

    def __init__(
        self,
        code: ImportErrorCode,
        message: str,
        remediation: str,
        *,
        clarification_options: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.remediation = remediation
        self.clarification_options = clarification_options
