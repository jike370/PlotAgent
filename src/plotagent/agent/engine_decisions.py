"""Non-mutating decisions shared by Agent Native engine clients."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import StrictModel

AgentAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
]


class InputChoice(StrictModel):
    value: AgentAlias
    label: Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]


class InputQuestion(StrictModel):
    question_key: AgentAlias
    prompt: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    input_kind: Literal["single_choice", "multiple_choice", "number", "text"]
    choices: tuple[InputChoice, ...] = ()

    @model_validator(mode="after")
    def choices_match_kind(self) -> InputQuestion:
        expects_choices = self.input_kind in {"single_choice", "multiple_choice"}
        if expects_choices != bool(self.choices):
            raise ValueError("choice inputs require choices and other inputs forbid them")
        return self


class NeedsInput(StrictModel):
    schema_version: Literal["engine-agent.v1"] = "engine-agent.v1"
    decision_type: Literal["needs_input"] = "needs_input"
    target_alias: AgentAlias
    questions: Annotated[tuple[InputQuestion, ...], Field(min_length=1, max_length=3)]


class Unsupported(StrictModel):
    schema_version: Literal["engine-agent.v1"] = "engine-agent.v1"
    decision_type: Literal["unsupported"] = "unsupported"
    target_alias: AgentAlias
    category: Literal["provider_capability", "profile_capability", "data_requirement"]
    explanation: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]


class NoChange(StrictModel):
    schema_version: Literal["engine-agent.v1"] = "engine-agent.v1"
    decision_type: Literal["no_change"] = "no_change"
    target_alias: AgentAlias
    explanation: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
