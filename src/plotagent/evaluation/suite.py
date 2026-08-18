"""Load the frozen Agent Foundation suite migrated from workflow-era SEQ-70."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import Sha256, StrictModel
from plotagent.evaluation.contracts import (
    EvalBudget,
    EvalCase,
    EvalLayer,
    EvalSelection,
    EvalSuiteKind,
    GraderSpec,
)


class LegacySource(StrictModel):
    path: str
    sha256: Sha256
    byte_length: Annotated[int, Field(gt=0)]


class SuiteDefaults(StrictModel):
    suite_kind: EvalSuiteKind
    locale: str
    blocks_release: bool
    budget: EvalBudget


class SuiteCaseOverlay(StrictModel):
    legacy_task_id: Annotated[
        str,
        StringConstraints(pattern=r"^[WR][0-9]{2}$", strict=True),
    ]
    layer: EvalLayer
    claim: str


class EvalSuiteOverlay(StrictModel):
    schema_version: Literal["eval-suite.v1"]
    suite_id: str
    suite_version: Annotated[int, Field(ge=1)]
    legacy_source: LegacySource
    defaults: SuiteDefaults
    cases: tuple[SuiteCaseOverlay, ...]

    @model_validator(mode="after")
    def unique_cases(self) -> EvalSuiteOverlay:
        values = tuple(case.legacy_task_id for case in self.cases)
        if len(values) != len(set(values)):
            raise ValueError("suite case ids must be unique")
        return self


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_migrated_seq70_suite(repository: Path, overlay_path: Path) -> tuple[EvalCase, ...]:
    """Load all 24 legacy scenarios under new case/grader/budget semantics."""

    overlay = EvalSuiteOverlay.model_validate_json(overlay_path.read_text(encoding="utf-8"))
    source = repository / overlay.legacy_source.path
    if not source.is_file():
        raise ValueError("legacy source task set is missing")
    if source.stat().st_size != overlay.legacy_source.byte_length:
        raise ValueError("legacy source task set byte length changed")
    if _sha256(source) != overlay.legacy_source.sha256:
        raise ValueError("legacy source task set hash changed")
    legacy = json.loads(source.read_text(encoding="utf-8"))
    tasks = {str(task["task_id"]): task for task in legacy["tasks"]}
    if len(tasks) != 24:
        raise ValueError("the migrated SEQ-70 source must contain 24 unique tasks")
    if {case.legacy_task_id for case in overlay.cases} != set(tasks):
        raise ValueError("suite overlay must migrate every legacy task exactly once")

    cases: list[EvalCase] = []
    for item in overlay.cases:
        task = tasks[item.legacy_task_id]
        instruction = str(task.get("instruction", ""))
        expected = str(task.get("expected_outcome", task.get("scenario", "runtime invariant")))
        cases.append(EvalCase(
            eval_case_id=f"seq70-v2:{item.legacy_task_id}",
            suite_id=overlay.suite_id,
            suite_version=overlay.suite_version,
            layer=item.layer,
            suite_kind=overlay.defaults.suite_kind,
            claim=item.claim,
            instruction=instruction,
            locale=overlay.defaults.locale,
            selection=EvalSelection(
                source_fixture_ids=(),
                profile_ids=tuple(str(value) for value in task.get("selected_profile_ids", ())),
            ),
            environment={"entry": "agent-foundation-v2"},
            component_versions={"legacy_source_schema": str(legacy["schema_version"])},
            budget=overlay.defaults.budget,
            required_outcomes=(expected,),
            forbidden_outcomes=("confirmation-before-side-effect", "successful-item-reexecution"),
            graders=(
                GraderSpec(
                    grader_id=f"grader:{item.legacy_task_id}:result",
                    kind="deterministic",
                    claim="检查 durable task、计划、项目 revision 和真实结果。",
                ),
                GraderSpec(
                    grader_id=f"grader:{item.legacy_task_id}:trace",
                    kind="trace",
                    claim="检查确认、权限、工具与副作用协议。",
                ),
            ),
            trial_count=3 if item.layer == "E3" else 1,
            blocks_release=overlay.defaults.blocks_release,
        ))
    return tuple(cases)
