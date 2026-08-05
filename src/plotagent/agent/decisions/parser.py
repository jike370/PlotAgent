"""Parse only complete JSON decisions; never infer intent from natural language."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from plotagent.agent.errors import AgentRuntimeError
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import AgentDecision

_DECISION_ADAPTER: TypeAdapter[AgentDecision] = TypeAdapter(AgentDecision)
_FORBIDDEN_KEYS = frozenset(
    {
        "tool",
        "tools",
        "tool_call",
        "tool_calls",
        "path",
        "url",
        "script",
        "command",
        "code",
        "python",
        "sql",
        "table_id",
        "renderer",
        "preparation_step",
        "calculation_kind",
        "processing_steps",
    }
)
_FORBIDDEN_TEXT_MARKERS = (
    "http://",
    "https://",
    "file://",
    "ftp://",
    "tool call",
    "tool_call",
    "```",
    "python",
    "pandas",
    "matplotlib",
    "originpro",
    "labtalk",
    "javascript",
    "renderer",
    "table_id",
    "table id",
    "preparationstep",
    "preparation_step",
    "plotcalculation",
    "processing step",
    "处理步骤",
)


@dataclass(frozen=True, slots=True)
class DecisionCandidate:
    decision: AgentDecision
    provider_response_hash: str
    decision_hash: str


class DecisionParseError(Exception):
    def __init__(self, categories: tuple[str, ...]) -> None:
        super().__init__("SCHEMA_INVALID")
        self.categories = categories


def parse_decision(output_text: str) -> DecisionCandidate:
    response_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    try:
        payload = json.loads(output_text)
    except (TypeError, ValueError):
        if _forbidden_text(output_text):
            raise AgentRuntimeError("AGENT_FORBIDDEN_PAYLOAD") from None
        raise DecisionParseError(("json_invalid",)) from None
    if _forbidden_value(payload):
        raise AgentRuntimeError("AGENT_FORBIDDEN_PAYLOAD")
    try:
        decision = _DECISION_ADAPTER.validate_json(output_text)
    except ValidationError as error:
        categories = tuple(
            dict.fromkeys(
                f"{item['loc'][0] if item['loc'] else 'root'}:{item['type']}"
                for item in error.errors(include_input=False, include_url=False)
            )
        )
        raise DecisionParseError(categories or ("schema_invalid",)) from None
    return DecisionCandidate(
        decision=decision,
        provider_response_hash=response_hash,
        decision_hash=canonical_hash(decision),
    )


def _forbidden_value(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in _FORBIDDEN_KEYS or _forbidden_value(item):
                return True
        return False
    if isinstance(value, list):
        return any(_forbidden_value(item) for item in value)
    return isinstance(value, str) and _forbidden_text(value)


def _forbidden_text(value: str) -> bool:
    lowered = value.casefold()
    if any(marker in lowered for marker in _FORBIDDEN_TEXT_MARKERS):
        return True
    if ":\\" in value or "..\\" in value or "../" in value or value.startswith("\\\\"):
        return True
    sql_pairs = (("select ", " from "), ("insert ", " into "), ("update ", " set "))
    return any(first in lowered and second in lowered for first, second in sql_pairs)
