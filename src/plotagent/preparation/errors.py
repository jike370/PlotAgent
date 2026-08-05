"""Stable mapping and preparation errors."""

from __future__ import annotations

from enum import StrEnum


class PreparationErrorCode(StrEnum):
    MAPPING_FIELD_UNKNOWN = "MAPPING_FIELD_UNKNOWN"
    MAPPING_ROLE_DUPLICATE = "MAPPING_ROLE_DUPLICATE"
    MAPPING_REQUIRED_ROLE_MISSING = "MAPPING_REQUIRED_ROLE_MISSING"
    PREPARE_UNSUPPORTED = "PREPARE_UNSUPPORTED"
    PREPARE_SOURCE_COUNT_INVALID = "PREPARE_SOURCE_COUNT_INVALID"
    PREPARE_FIELD_UNKNOWN = "PREPARE_FIELD_UNKNOWN"
    PREPARE_NON_ISOMORPHIC = "PREPARE_NON_ISOMORPHIC"
    PREPARE_METADATA_MISSING = "PREPARE_METADATA_MISSING"
    PREPARE_NONFINITE = "PREPARE_NONFINITE"
    PREPARE_MISSING = "PREPARE_MISSING"
    PREPARE_STRUCTURE_INVALID = "PREPARE_STRUCTURE_INVALID"


class PreparationProblem(Exception):
    def __init__(self, code: PreparationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
