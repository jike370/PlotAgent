"""Local project-context snapshots and cross-turn target resolution."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.project_context import (
    ProjectContextSnapshot,
    TargetPrecedence,
    TargetResolution,
)


class ProjectContextService:
    """Build deterministic local snapshots without disclosing extra data to a provider."""

    def build_snapshot(
        self,
        *,
        project_id: str,
        project_revision: int,
        conversation_id: str,
        conversation_state: ConversationStateProjection,
        known_objects: tuple[ContextObjectRef, ...],
        recent_result_objects: tuple[ContextObjectRef, ...] = (),
        project_rule_ids: tuple[str, ...] = (),
        saved_setting_refs: tuple[str, ...] = (),
    ) -> ProjectContextSnapshot:
        payload = {
            "project_id": project_id,
            "project_revision": project_revision,
            "conversation_id": conversation_id,
            "conversation_state": conversation_state.model_dump(mode="json"),
            "known_objects": [item.model_dump(mode="json") for item in known_objects],
            "recent_result_objects": [
                item.model_dump(mode="json") for item in recent_result_objects
            ],
            "project_rule_ids": list(project_rule_ids),
            "saved_setting_refs": list(saved_setting_refs),
        }
        snapshot_hash = canonical_hash(cast(JsonValue, payload))
        conversation_suffix = conversation_id.removeprefix("conversation:")[:48]
        snapshot_id = (
            f"context:{conversation_suffix}.{conversation_state.state_version}."
            f"{project_revision}.{snapshot_hash[:12]}"
        )
        return ProjectContextSnapshot(
            snapshot_id=snapshot_id,
            snapshot_hash=snapshot_hash,
            project_id=project_id,
            project_revision=project_revision,
            conversation_id=conversation_id,
            conversation_state=conversation_state,
            known_objects=known_objects,
            recent_result_objects=recent_result_objects,
            project_rule_ids=project_rule_ids,
            saved_setting_refs=saved_setting_refs,
        )


class TargetResolver:
    """Resolve target aliases in a fixed local precedence order."""

    def resolve(
        self,
        snapshot: ProjectContextSnapshot,
        *,
        composer_scope: tuple[str, ...] = (),
        explicit_turn_aliases: tuple[str, ...] = (),
        allowed_object_types: frozenset[str] | None = None,
    ) -> TargetResolution:
        objects = {
            item.object_alias: item
            for item in (
                snapshot.known_objects
                + snapshot.recent_result_objects
                + (snapshot.conversation_state.current_target,)
            )
        }

        def eligible(values: Iterable[ContextObjectRef]) -> tuple[ContextObjectRef, ...]:
            unique: dict[str, ContextObjectRef] = {}
            for value in values:
                if allowed_object_types is None or value.object_type in allowed_object_types:
                    unique[value.object_alias] = value
            return tuple(unique.values())

        tiers: tuple[tuple[TargetPrecedence, tuple[ContextObjectRef, ...]], ...] = (
            (
                "composer_scope",
                eligible(objects[alias] for alias in composer_scope if alias in objects),
            ),
            (
                "explicit_turn_reference",
                eligible(objects[alias] for alias in explicit_turn_aliases if alias in objects),
            ),
            ("conversation_target", eligible((snapshot.conversation_state.current_target,))),
            ("recent_plan_output", eligible(snapshot.recent_result_objects)),
            ("unique_candidate", eligible(snapshot.known_objects)),
        )
        for precedence, candidates in tiers:
            if len(candidates) == 1:
                return TargetResolution(
                    status="resolved",
                    precedence=precedence,
                    target=candidates[0],
                )
            if len(candidates) > 1:
                labels = "、".join(item.object_alias for item in candidates)
                return TargetResolution(
                    status="ambiguous",
                    precedence=precedence,
                    candidates=candidates[:8],
                    question=f"请选择要操作的对象：{labels}",
                )
        return TargetResolution(status="missing", precedence="none")
