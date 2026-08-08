"""Local conversation authority; provider decisions never mutate this state."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.base import SemanticAlias, StrictModel, Token, VersionId


class ConversationState(StrictModel):
    state_version: VersionId = 1
    current_target: ContextObjectRef
    selected_objects: tuple[ContextObjectRef, ...] = ()
    confirmed_field_aliases: tuple[SemanticAlias, ...] = ()
    project_rule_ids: tuple[Token, ...] = ()
    saved_setting_refs: tuple[Token, ...] = ()
    unresolved_question_ids: tuple[Token, ...] = ()
    recent_result_kinds: tuple[
        Literal["action_plan", "needs_input", "unsupported", "no_change", "execution_result"],
        ...,
    ] = Field(default=(), max_length=8)

    def project(self) -> ConversationStateProjection:
        return ConversationStateProjection(
            state_version=self.state_version,
            current_target=self.current_target,
            selected_objects=self.selected_objects,
            confirmed_field_aliases=self.confirmed_field_aliases,
            project_rule_ids=self.project_rule_ids,
            saved_setting_refs=self.saved_setting_refs,
            unresolved_question_ids=self.unresolved_question_ids,
            recent_result_kinds=self.recent_result_kinds,
        )

    @classmethod
    def from_projection(cls, value: ConversationStateProjection) -> ConversationState:
        return cls.model_validate_json(value.model_dump_json())


class ConversationStateReducer:
    """Reduce only local UI selections and authoritative execution results."""

    def select_target(
        self,
        state: ConversationState,
        target: ContextObjectRef,
        *,
        selected_objects: tuple[ContextObjectRef, ...] = (),
    ) -> ConversationState:
        return state.model_copy(
            update={
                "state_version": state.state_version + 1,
                "current_target": target,
                "selected_objects": selected_objects,
            }
        )

    def confirm_fields(
        self, state: ConversationState, field_aliases: tuple[SemanticAlias, ...]
    ) -> ConversationState:
        return state.model_copy(
            update={
                "state_version": state.state_version + 1,
                "confirmed_field_aliases": tuple(dict.fromkeys(field_aliases)),
            }
        )

    def record_decision(
        self,
        state: ConversationState,
        *,
        decision_kind: Literal["action_plan", "needs_input", "unsupported", "no_change"],
        unresolved_question_ids: tuple[Token, ...] = (),
    ) -> ConversationState:
        """Persist the bounded outcome of one provider turn without trusting it as state.

        The local reducer records only the decision class and locally validated
        question identifiers.  Provider prose and proposed object identities never
        enter the authoritative conversation state.
        """

        recent = (*state.recent_result_kinds, decision_kind)[-8:]
        return state.model_copy(
            update={
                "state_version": state.state_version + 1,
                "unresolved_question_ids": tuple(dict.fromkeys(unresolved_question_ids)),
                "recent_result_kinds": recent,
            }
        )

    def record_execution_result(
        self,
        state: ConversationState,
        *,
        target: ContextObjectRef,
        unresolved_question_ids: tuple[Token, ...] = (),
    ) -> ConversationState:
        recent = (*state.recent_result_kinds, "execution_result")[-8:]
        return state.model_copy(
            update={
                "state_version": state.state_version + 1,
                "current_target": target,
                "unresolved_question_ids": unresolved_question_ids,
                "recent_result_kinds": recent,
            }
        )
