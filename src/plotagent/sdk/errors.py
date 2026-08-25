"""Stable failures shared by PlotAgent's external interfaces."""

from __future__ import annotations


class PlotAgentSDKError(Exception):
    """A sanitized engine error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
