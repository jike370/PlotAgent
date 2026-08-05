"""Registered W2 preparation errors."""

from __future__ import annotations

from enum import StrEnum


class PreparationErrorCode(StrEnum):
    MAPPING_REQUIRED_ROLE_MISSING = "MAPPING_REQUIRED_ROLE_MISSING"
    MAPPING_DUPLICATE_ROLE = "MAPPING_DUPLICATE_ROLE"
    PREPARE_UNSUPPORTED = "PREPARE_UNSUPPORTED"
    PREPARE_NON_ISOMORPHIC = "PREPARE_NON_ISOMORPHIC"
    PREPARE_UNIT_INCOMPATIBLE = "PREPARE_UNIT_INCOMPATIBLE"
    PREPARE_NONFINITE_POLICY_REQUIRED = "PREPARE_NONFINITE_POLICY_REQUIRED"


class PreparationProblem(Exception):
    def __init__(self, code: PreparationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
