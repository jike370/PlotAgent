"""Run the frozen SEQ-70 Agent quality evaluation against the desktop Core.

The evaluator uses the configured ``custom.default`` secret through the Windows
credential store. It never accepts, reads from the environment, prints, or writes
an API key. Generated projects and data are synthetic and live in temporary
directories; only aggregate evidence is retained under ``build``.
"""

# ruff: noqa: E501 -- frozen prompts and generated report HTML remain readable verbatim.

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import statistics
import subprocess
import tempfile
import time
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from plotagent.agent.evaluation import EvalTask, Seq70TaskSet, score_model_result
from plotagent.agent.project_context import ProjectContextService
from plotagent.agent.providers import ModelProvider
from plotagent.agent.providers.custom import CustomProviderConfig, OpenAICompatibleProvider
from plotagent.agent.task_orchestrator import PersistentTaskOrchestrator, TaskExecutionError
from plotagent.agent.task_plans import TaskPlanCompiler
from plotagent.contracts.agent_context import ContextObjectRef, ConversationStateProjection
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.decisions import ActionPlan, PatchPlotAction, PlotTitleIntent
from plotagent.contracts.task_runtime import TaskItemSnapshot, TaskOutputRef, TaskPlanSnapshot
from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.services import RpcContext, ServiceRegistry
from plotagent.desktop_core.tasks import BoundedWorkerExecutor, TaskRegistry
from plotagent.security.credentials import create_credential_store
from plotagent.security.network import (
    HttpxRawTransport,
    NetworkMode,
    NetworkPolicyGate,
    NetworkRequest,
    NetworkResponse,
    PolicyTransport,
)
from plotagent.storage import AgentRuntimeRepository, ProjectStore

REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_TASK_SET = REPOSITORY / "tests" / "fixtures" / "seq70" / "agent_tasks.json"
MULTI_SHEET = REPOSITORY / "tests" / "fixtures" / "import" / "files" / "excel_two_sheets.xlsx"


@dataclass(slots=True)
class NetworkCall:
    run_key: str
    url_suffix: str
    status_code: int | None
    latency_seconds: float
    input_tokens: int = 0
    input_cache_hit_tokens: int = 0
    input_cache_miss_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


class CountingRawTransport:
    """Count requests and provider-reported usage without retaining payloads."""

    def __init__(self, inner: HttpxRawTransport) -> None:
        self.inner = inner
        self.run_key = "unattributed"
        self.calls: list[NetworkCall] = []

    def send(self, request: NetworkRequest) -> NetworkResponse:
        started = time.perf_counter()
        try:
            response = self.inner.send(request)
        except Exception as error:
            self.calls.append(
                NetworkCall(
                    run_key=self.run_key,
                    url_suffix=request.url.rsplit("/", maxsplit=2)[-1],
                    status_code=None,
                    latency_seconds=time.perf_counter() - started,
                    error=type(error).__name__,
                )
            )
            raise
        usage = _extract_usage(response.body)
        self.calls.append(
            NetworkCall(
                run_key=self.run_key,
                url_suffix=request.url.rsplit("/", maxsplit=2)[-1],
                status_code=response.status_code,
                latency_seconds=time.perf_counter() - started,
                input_tokens=usage.get("input_tokens", 0),
                input_cache_hit_tokens=usage.get("input_cache_hit_tokens", 0),
                input_cache_miss_tokens=usage.get("input_cache_miss_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
        )
        return response


class Harness:
    def __init__(self, root: Path, provider: ModelProvider | None = None) -> None:
        provider_factory = None
        if provider is not None:

            def configured_provider(_mode: object, _params: object) -> ModelProvider:
                return provider

            provider_factory = configured_provider
        self.application = DesktopApplication(root, provider_factory=provider_factory)
        self.registry = ServiceRegistry()
        self.workers = BoundedWorkerExecutor(max_workers=2, maximum_pending=4)
        self.tasks = TaskRegistry(lambda _event: None)
        self.application.configure_services(self.registry, self.tasks, self.workers)

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        context = RpcContext(
            request_id="seq70:" + uuid.uuid4().hex,
            tasks=self.tasks,
            workers=self.workers,
        )
        return cast(dict[str, Any], self.registry.dispatch(method, context, params))

    def close(self) -> None:
        self.workers.shutdown()
        self.application.close()


@dataclass(slots=True)
class RuntimeExecutor:
    fail_once: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def execute(self, plan: TaskPlanSnapshot, item: TaskItemSnapshot) -> tuple[TaskOutputRef, ...]:
        del plan
        action_id = item.action.action_id
        self.calls.append(action_id)
        if action_id in self.fail_once:
            self.fail_once.remove(action_id)
            raise TaskExecutionError("ORIGIN_BUSY", "Origin is busy.", retryable=True)
        return (
            TaskOutputRef(
                output_slot=item.output_slots[0],
                output_kind="result",
                summary=action_id,
            ),
        )


class RuntimeAuthority:
    def __init__(self, current: ContextObjectRef | None = None) -> None:
        self.current_value = current

    def current(self, expected: ContextObjectRef) -> ContextObjectRef | None:
        return expected if self.current_value is None else self.current_value


def _extract_usage(body: bytes) -> dict[str, int]:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("usage"), dict):
        return {}
    usage = payload["usage"]
    assert isinstance(usage, dict)
    input_tokens = _integer_usage(usage, "input_tokens", "prompt_tokens")
    output_tokens = _integer_usage(usage, "output_tokens", "completion_tokens")
    cache_hit = _integer_usage(usage, "prompt_cache_hit_tokens")
    cache_miss = _integer_usage(usage, "prompt_cache_miss_tokens")
    details = usage.get("prompt_tokens_details")
    if cache_hit == 0 and isinstance(details, dict):
        cached = details.get("cached_tokens")
        cache_hit = cached if isinstance(cached, int) and cached >= 0 else 0
    if input_tokens and cache_hit + cache_miss == 0:
        cache_miss = input_tokens
    elif input_tokens and cache_hit + cache_miss < input_tokens:
        cache_miss += input_tokens - cache_hit - cache_miss
    return {
        "input_tokens": input_tokens,
        "input_cache_hit_tokens": cache_hit,
        "input_cache_miss_tokens": cache_miss,
        "output_tokens": output_tokens,
    }


def _integer_usage(value: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        item = value.get(key)
        if isinstance(item, int) and item >= 0:
            return item
    return 0


def _create_provider(task_set: Seq70TaskSet) -> tuple[ModelProvider, CountingRawTransport]:
    config = CustomProviderConfig(
        provider_config_id=task_set.provider["provider_config_id"],
        base_url=task_set.provider["base_url"],
        model_id=task_set.provider["model_id"],
        model_profile="seq70-frozen-v1",
    )
    credentials = create_credential_store()
    if not credentials.get_custom_api_key(config.provider_config_id):
        raise RuntimeError("custom.default is unavailable in the Windows credential store")

    def bearer(_request: NetworkRequest) -> str | None:
        return credentials.get_custom_api_key(config.provider_config_id)

    raw = HttpxRawTransport(bearer_token_provider=cast(Any, bearer))
    counting = CountingRawTransport(raw)
    policy = PolicyTransport(
        NetworkPolicyGate(NetworkMode.CUSTOM_PROVIDER, custom_endpoint=config.base_url),
        counting,
    )
    return OpenAICompatibleProvider(policy, config), counting


def _write_csv(path: Path, fixture: str) -> None:
    headers: tuple[str, ...]
    rows: list[tuple[Any, ...]]
    if fixture in {"xy", "positive_xy"}:
        rows = [(index, float(index + 1) ** 1.25) for index in range(1, 9)]
        if fixture == "xy":
            rows = [(index, value - 6.0) for index, value in rows]
        headers = ("x", "y")
    elif fixture == "grouped":
        headers = ("category", "group", "value")
        rows = [
            (category, group, 8.0 + category_index * 2.5 + group_index)
            for category_index, category in enumerate(("A", "B", "C", "D"))
            for group_index, group in enumerate(("Control", "Treatment"))
        ]
    elif fixture == "grid":
        headers = ("x", "y", "z")
        rows = [
            (x, y, round(math.sin(x / 2) + math.cos(y / 3), 6)) for x in range(5) for y in range(4)
        ]
    elif fixture == "error_xy":
        headers = ("x", "center", "x_lower", "x_upper", "lower", "upper")
        rows = [
            (x, 2.0 + x * 0.7, x - 0.15, x + 0.15, 1.7 + x * 0.7, 2.3 + x * 0.7)
            for x in range(1, 7)
        ]
    elif fixture == "forest":
        headers = ("label", "effect", "lower", "upper", "weight")
        rows = [
            (
                f"Study {index}",
                0.75 + index * 0.08,
                0.55 + index * 0.08,
                0.95 + index * 0.08,
                8 + index,
            )
            for index in range(1, 7)
        ]
    else:
        raise ValueError(f"unknown synthetic fixture: {fixture}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def _create_project(harness: Harness, label: str) -> tuple[str, int]:
    created = harness.call(
        "projects.create",
        {"display_name": label, "idempotency_key": "project-" + uuid.uuid4().hex},
    )
    project_id = cast(str, created["project_id"])
    opened = harness.call("projects.open", {"project_id": project_id})
    return project_id, cast(int, opened["project_version"])


def _import_source(
    harness: Harness,
    project_id: str,
    project_version: int,
    source: Path,
    label: str,
) -> dict[str, Any]:
    result = harness.call(
        "datasets.import",
        {
            "project_id": project_id,
            "resource_id": "resource:" + uuid.uuid4().hex,
            "source_path": str(source),
            "idempotency_key": f"import-{label}-{uuid.uuid4().hex}",
            "expected_version": project_version,
            "options": {},
        },
    )
    if result.get("kind") != "committed":
        raise RuntimeError(f"synthetic import did not commit: {result.get('kind')}")
    return result


def _field_ids(harness: Harness, project_id: str, dataset: Mapping[str, Any]) -> dict[str, str]:
    described = harness.call(
        "datasets.describe",
        {
            "project_id": project_id,
            "source_dataset_id": dataset["source_dataset_id"],
            "source_version": dataset["source_version"],
        },
    )
    return {str(field["name"]): str(field["field_id"]) for field in described["dataset"]["fields"]}


def _create_plot(
    harness: Harness,
    *,
    project_id: str,
    dataset: Mapping[str, Any],
    project_version: int,
    plot_id: str,
    chart_type_id: str,
) -> dict[str, Any]:
    fields = _field_ids(harness, project_id, dataset)
    mapping = {"x": fields["x"], "y": fields["y"]}
    return harness.call(
        "plots.create",
        {
            "project_id": project_id,
            "plot_id": plot_id,
            "chart_type_id": chart_type_id,
            "source_dataset_id": dataset["source_dataset_id"],
            "source_version": dataset["source_version"],
            "field_mapping": mapping,
            "idempotency_key": "plot-" + uuid.uuid4().hex,
            "expected_version": project_version,
        },
    )


def _create_batch(
    harness: Harness,
    *,
    project_id: str,
    project_version: int,
    member_count: int,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    datasets: list[dict[str, Any]] = []
    revision = project_version
    while len(datasets) < member_count:
        imported = _import_source(
            harness,
            project_id,
            revision,
            MULTI_SHEET,
            f"batch-{len(datasets)}",
        )
        revision = cast(int, imported["project_version"])
        datasets.extend(cast(list[dict[str, Any]], imported["datasets"]))
    datasets = datasets[:member_count]
    fields = _field_ids(harness, project_id, datasets[0])
    numeric = tuple(fields.values())[:2]
    created = harness.call(
        "agent.plans.create_batch",
        {
            "project_id": project_id,
            "source_datasets": [
                {
                    "source_dataset_id": dataset["source_dataset_id"],
                    "source_version": dataset["source_version"],
                }
                for dataset in datasets
            ],
            "chart_type_id": "K01",
            "field_mapping": {"x": numeric[0], "y": numeric[1]},
            "expected_version": revision,
        },
    )
    plan_id = created["task_plan"]["plan_id"]
    confirmed = harness.call(
        "agent.plans.confirm",
        {"project_id": project_id, "plan_id": plan_id, "accept": True},
    )
    executed = harness.call(
        "agent.plans.run",
        {"project_id": project_id, "plan_id": plan_id},
    )
    output = executed["task_plan"]["items"][-1]["outputs"][0]["object_ref"]
    stored = harness.call(
        "batch.get",
        {"project_id": project_id, "batch_id": output["object_id"]},
    )
    return (
        {
            "created": created,
            "confirmed": confirmed,
            "executed": executed,
            "batch": stored,
        },
        datasets[0],
        cast(int, stored["project_version"]),
    )


def _agent_params(
    task_set: Seq70TaskSet,
    *,
    project_id: str,
    dataset: Mapping[str, Any],
    instruction: str,
    project_version: int,
    run_id: str,
    selected_chart_id: str | None = None,
    target: dict[str, str] | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "project_id": project_id,
        "source_dataset_id": dataset["source_dataset_id"],
        "source_version": dataset["source_version"],
        "user_instruction": instruction,
        "client_model_run_id": run_id,
        "expected_version": project_version,
        "locale": "zh-CN",
        "execution_mode": "plan_only",
        "network_mode": "custom_provider",
        "provider": task_set.provider,
        "retention_acknowledged": True,
    }
    if selected_chart_id is not None:
        params["selected_chart_id"] = selected_chart_id
    if target is not None:
        params["target"] = target
    if scope is not None:
        params["scope"] = scope
    return params


def _run_model_task(
    task_set: Seq70TaskSet,
    task: EvalTask,
    repetition: int,
    provider: ModelProvider,
    transport: CountingRawTransport,
) -> dict[str, Any]:
    run_key = f"{task.task_id}.r{repetition}"
    with tempfile.TemporaryDirectory(prefix=f"seq70-{run_key}-") as temporary:
        root = Path(temporary)
        harness = Harness(root / "app", provider)
        started = time.perf_counter()
        try:
            project_id, revision = _create_project(harness, run_key)
            if task.setup == "batch4":
                batch_result, dataset, revision = _create_batch(
                    harness,
                    project_id=project_id,
                    project_version=revision,
                    member_count=4,
                )
                batch_id = batch_result["batch"]["batch"]["batch_id"]
                target = {"kind": "batch", "id": batch_id}
                scope = "batch"
                selected_chart_id = "K01"
            else:
                if task.fixture is None:
                    raise RuntimeError("model task has no fixture")
                source = root / f"{task.fixture}.csv"
                _write_csv(source, task.fixture)
                imported = _import_source(harness, project_id, revision, source, run_key)
                revision = cast(int, imported["project_version"])
                dataset = cast(dict[str, Any], imported["datasets"][0])
                target = None
                scope = None
                selected_chart_id = None
                if task.setup.startswith("plot_"):
                    chart_type_id = task.setup.removeprefix("plot_").upper()
                    plot_id = f"plot:{run_key}"
                    created = _create_plot(
                        harness,
                        project_id=project_id,
                        dataset=dataset,
                        project_version=revision,
                        plot_id=plot_id,
                        chart_type_id=chart_type_id,
                    )
                    revision = cast(int, created["project_version"])
                    target = {"kind": "plot", "id": plot_id}
                    scope = "current"
                    selected_chart_id = chart_type_id
                elif task.setup == "two_plots_cross_turn":
                    first = _create_plot(
                        harness,
                        project_id=project_id,
                        dataset=dataset,
                        project_version=revision,
                        plot_id=f"plot:{run_key}.one",
                        chart_type_id="K01",
                    )
                    revision = cast(int, first["project_version"])
                    second_plot_id = f"plot:{run_key}.two"
                    second = _create_plot(
                        harness,
                        project_id=project_id,
                        dataset=dataset,
                        project_version=revision,
                        plot_id=second_plot_id,
                        chart_type_id="K01",
                    )
                    revision = cast(int, second["project_version"])
                    transport.run_key = run_key
                    precondition = harness.call(
                        "agent.decide",
                        _agent_params(
                            task_set,
                            project_id=project_id,
                            dataset=dataset,
                            instruction=cast(str, task.precondition_instruction),
                            project_version=revision,
                            run_id=f"model-run:{run_key}.precondition",
                            selected_chart_id="K01",
                            target={"kind": "plot", "id": second_plot_id},
                            scope="current",
                        ),
                    )
                    if precondition.get("accepted") is not True:
                        raise RuntimeError(
                            f"cross-turn precondition failed: {precondition.get('error')}"
                        )
                    target = None
                    scope = None
                    selected_chart_id = "K01"
                elif task.setup != "source":
                    raise RuntimeError(f"unknown model setup: {task.setup}")

            if task.expectation is not None and task.expectation.chart_type_id is not None:
                selected_chart_id = task.expectation.chart_type_id
            transport.run_key = run_key
            try:
                result = harness.call(
                    "agent.decide",
                    _agent_params(
                        task_set,
                        project_id=project_id,
                        dataset=dataset,
                        instruction=cast(str, task.instruction),
                        project_version=revision,
                        run_id=f"model-run:{run_key}",
                        selected_chart_id=selected_chart_id,
                        target=target,
                        scope=scope,
                    ),
                )
            except Exception as error:
                result = {
                    "accepted": False,
                    "error": {"code": type(error).__name__, "message": str(error)[:300]},
                }
            score = score_model_result(task, result)
            elapsed = time.perf_counter() - started
            calls = [asdict(call) for call in transport.calls if call.run_key == run_key]
            return {
                "task_id": task.task_id,
                "repetition": repetition,
                "layer": task.layer,
                "category": task.category,
                "passed": score.passed,
                "latency_seconds": round(elapsed, 4),
                "score": asdict(score),
                "decision": result.get("decision"),
                "error": result.get("error"),
                "network_calls": calls,
            }
        except Exception as error:
            return {
                "task_id": task.task_id,
                "repetition": repetition,
                "layer": task.layer,
                "category": task.category,
                "passed": False,
                "latency_seconds": round(time.perf_counter() - started, 4),
                "score": None,
                "decision": None,
                "error": {"code": type(error).__name__, "message": str(error)[:300]},
                "network_calls": [
                    asdict(call) for call in transport.calls if call.run_key == run_key
                ],
            }
        finally:
            harness.close()


def _runtime_ref(version: int = 1) -> ContextObjectRef:
    return ContextObjectRef(
        object_alias="active_target",
        object_id="plot:runtime",
        object_version=version,
        object_type="plot",
        content_hash=("a" if version == 1 else "b") * 64,
    )


def _create_runtime(repository: AgentRuntimeRepository, action_count: int) -> TaskPlanSnapshot:
    state = ConversationStateProjection(state_version=1, current_target=_runtime_ref())
    repository.save_conversation_state("conversation:main", state, expected_state_version=None)
    context = ProjectContextService().build_snapshot(
        project_id=repository.project.project_id,
        project_revision=0,
        conversation_id="conversation:main",
        conversation_state=state,
        known_objects=(_runtime_ref(),),
    )
    repository.save_context_snapshot(context)
    plan = ActionPlan(
        plan_id="plan:seq70-runtime",
        target_alias="active_target",
        actions=tuple(
            PatchPlotAction(
                action_id=f"action:item-{index}",
                target_alias="active_target",
                patches=(PlotTitleIntent(target_alias="active_target", title=f"Item {index}"),),
            )
            for index in range(1, action_count + 1)
        ),
    )
    runtime = TaskPlanCompiler().compile(plan, context)
    repository.create_plan(runtime)
    return runtime


def _run_runtime_task(task: EvalTask, repetition: int) -> dict[str, Any]:
    started = time.perf_counter()
    run_key = f"{task.task_id}.r{repetition}"
    details: dict[str, Any] = {}
    try:
        if task.scenario in {"batch2_success", "batch4_success"}:
            member_count = 2 if task.scenario == "batch2_success" else 4
            with tempfile.TemporaryDirectory(prefix=f"seq70-{run_key}-") as temporary:
                harness = Harness(Path(temporary) / "app")
                try:
                    project_id, revision = _create_project(harness, run_key)
                    batch, _dataset, _revision = _create_batch(
                        harness,
                        project_id=project_id,
                        project_version=revision,
                        member_count=member_count,
                    )
                    plan = batch["executed"]["task_plan"]
                    item_states = [item["state"] for item in plan["items"]]
                    attempts = [item["attempt_count"] for item in plan["items"]]
                    passed = (
                        batch["created"]["task_plan"]["state"] == "needs_confirmation"
                        and batch["confirmed"]["confirmation_state"] == "confirmed"
                        and plan["state"] == "succeeded"
                        and item_states == ["succeeded"] * (member_count + 1)
                        and attempts == [1] * (member_count + 1)
                    )
                    details = {
                        "member_count": member_count,
                        "completed_item_count": batch["executed"]["completed_item_count"],
                        "attempt_counts": attempts,
                        "batch_completion": passed,
                    }
                finally:
                    harness.close()
        elif task.scenario == "partial_resume_only_failed":
            with (
                tempfile.TemporaryDirectory(prefix=f"seq70-{run_key}-") as temporary,
                ProjectStore.create(Path(temporary) / "project") as store,
            ):
                repository = AgentRuntimeRepository(store)
                runtime = _create_runtime(repository, 3)
                executor = RuntimeExecutor(fail_once={"action:item-3"})
                orchestrator = PersistentTaskOrchestrator(repository, RuntimeAuthority())
                partial = orchestrator.run(runtime.plan_id, executor)
                calls_before = tuple(executor.calls)
                completed = orchestrator.run(runtime.plan_id, executor, resume=True)
                partial_fidelity = [item.state for item in partial.items] == [
                    "succeeded",
                    "succeeded",
                    "failed",
                ]
                repeated_successes = sum(
                    executor.calls.count(action_id) - 1
                    for action_id in ("action:item-1", "action:item-2")
                )
                recovery_success = completed.state == "succeeded" and [
                    item.attempt_count for item in completed.items
                ] == [1, 1, 2]
                passed = partial_fidelity and recovery_success and repeated_successes == 0
                details = {
                    "partial_fidelity": partial_fidelity,
                    "recovery_success": recovery_success,
                    "successful_repeat_count": repeated_successes,
                    "successful_item_count": 2,
                    "calls_before_resume": calls_before,
                    "calls_after_resume": tuple(executor.calls),
                }
        elif task.scenario == "successful_replay_no_repeat":
            with (
                tempfile.TemporaryDirectory(prefix=f"seq70-{run_key}-") as temporary,
                ProjectStore.create(Path(temporary) / "project") as store,
            ):
                repository = AgentRuntimeRepository(store)
                runtime = _create_runtime(repository, 2)
                executor = RuntimeExecutor()
                orchestrator = PersistentTaskOrchestrator(repository, RuntimeAuthority())
                first = orchestrator.run(runtime.plan_id, executor)
                second = orchestrator.run(runtime.plan_id, executor)
                repeats = len(executor.calls) - 2
                passed = (
                    first.state == second.state == "succeeded"
                    and repeats == 0
                    and [item.attempt_count for item in second.items] == [1, 1]
                )
                details = {
                    "successful_repeat_count": repeats,
                    "successful_item_count": 2,
                    "attempt_counts": [item.attempt_count for item in second.items],
                }
        elif task.scenario == "stale_plan_no_side_effect":
            with (
                tempfile.TemporaryDirectory(prefix=f"seq70-{run_key}-") as temporary,
                ProjectStore.create(Path(temporary) / "project") as store,
            ):
                repository = AgentRuntimeRepository(store)
                runtime = _create_runtime(repository, 1)
                executor = RuntimeExecutor()
                orchestrator = PersistentTaskOrchestrator(
                    repository, RuntimeAuthority(_runtime_ref(version=2))
                )
                result = orchestrator.run(runtime.plan_id, executor)
                passed = (
                    result.state == "stale"
                    and result.items[0].attempt_count == 0
                    and not executor.calls
                )
                details = {
                    "stale_rejected": passed,
                    "executor_calls": tuple(executor.calls),
                }
        elif task.scenario == "restart_interrupted_resume":
            with tempfile.TemporaryDirectory(prefix=f"seq70-{run_key}-") as temporary:
                workspace = Path(temporary) / "project"
                with ProjectStore.create(workspace) as first_store:
                    first_repository = AgentRuntimeRepository(first_store)
                    runtime = _create_runtime(first_repository, 1)
                    first_repository.begin_attempt(runtime.items[0].task_item_id)
                with ProjectStore.open(workspace) as second_store:
                    repository = AgentRuntimeRepository(second_store)
                    recovered_ids = repository.recover_interrupted()
                    recovered = repository.get_plan(runtime.plan_id)
                    executor = RuntimeExecutor()
                    completed = PersistentTaskOrchestrator(repository, RuntimeAuthority()).run(
                        runtime.plan_id, executor, resume=True
                    )
                    passed = (
                        recovered_ids == (runtime.plan_id,)
                        and recovered.state == "interrupted"
                        and recovered.items[0].state == "interrupted"
                        and completed.state == "succeeded"
                        and completed.items[0].attempt_count == 2
                        and executor.calls == ["action:item-1"]
                    )
                    details = {
                        "restart_recovery": passed,
                        "recovered_plan_ids": recovered_ids,
                        "attempt_count": completed.items[0].attempt_count,
                    }
        else:
            raise ValueError(f"unknown runtime scenario: {task.scenario}")
        return {
            "task_id": task.task_id,
            "repetition": repetition,
            "layer": task.layer,
            "category": task.category,
            "passed": passed,
            "latency_seconds": round(time.perf_counter() - started, 4),
            "details": details,
            "error": None,
        }
    except Exception as error:
        return {
            "task_id": task.task_id,
            "repetition": repetition,
            "layer": task.layer,
            "category": task.category,
            "passed": False,
            "latency_seconds": round(time.perf_counter() - started, 4),
            "details": details,
            "error": {"code": type(error).__name__, "message": str(error)[:300]},
        }


def _ratio(records: list[dict[str, Any]], predicate: Any) -> tuple[int, int, float]:
    selected = [record for record in records if predicate(record)[0]]
    passed = sum(bool(predicate(record)[1]) for record in selected)
    return passed, len(selected), passed / len(selected) if selected else 1.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _aggregate(
    task_set: Seq70TaskSet,
    records: list[dict[str, Any]],
    network_calls: list[NetworkCall],
) -> dict[str, Any]:
    model = [record for record in records if record["layer"] == "model"]
    runtime = [record for record in records if record["layer"] == "runtime"]

    def score(record: dict[str, Any], key: str, default: bool = False) -> bool:
        value = record.get("score")
        return bool(value.get(key, default)) if isinstance(value, dict) else default

    raw_metrics: dict[str, tuple[int, int, float]] = {}
    raw_metrics["candidate_plan_legal_rate"] = _ratio(
        model, lambda record: (score(record, "expected_plan"), score(record, "plan_legal"))
    )
    raw_metrics["local_validator_accept_rate"] = _ratio(
        model, lambda record: (True, score(record, "schema_accepted"))
    )
    raw_metrics["target_binding_accuracy"] = _ratio(
        model,
        lambda record: (
            score(record, "target_binding_applicable"),
            score(record, "target_binding_correct"),
        ),
    )
    incorrect_count = sum(score(record, "incorrect_auto_binding") for record in model)
    forbidden_count = sum(
        bool(record.get("score"))
        and any(failure == "forbidden_action_plan" for failure in record["score"]["failures"])
        or (
            record["task_id"] in {"D14", "D15", "D18"}
            and (record.get("decision") or {}).get("decision_type") != "action_plan"
        )
        for record in model
    )
    del forbidden_count
    auto_denominator = sum(record["task_id"] in {"D14", "D15", "D18"} for record in model)
    raw_metrics["incorrect_auto_binding_rate"] = (
        incorrect_count,
        auto_denominator,
        incorrect_count / auto_denominator if auto_denominator else 0.0,
    )
    raw_metrics["field_mapping_first_pass_rate"] = _ratio(
        model,
        lambda record: (
            score(record, "field_mapping_applicable"),
            score(record, "field_mapping_correct"),
        ),
    )
    raw_metrics["necessary_question_rate"] = _ratio(
        model,
        lambda record: (
            score(record, "necessary_question_applicable"),
            score(record, "necessary_question_correct"),
        ),
    )
    invalid_denominator = sum(
        not score(record, "necessary_question_applicable") for record in model
    )
    invalid_count = sum(score(record, "invalid_question") for record in model)
    raw_metrics["invalid_question_rate"] = (
        invalid_count,
        invalid_denominator,
        invalid_count / invalid_denominator if invalid_denominator else 0.0,
    )
    raw_metrics["model_task_exact_success_rate"] = (
        sum(record["passed"] for record in model),
        len(model),
        sum(record["passed"] for record in model) / len(model),
    )
    raw_metrics["runtime_task_success_rate"] = (
        sum(record["passed"] for record in runtime),
        len(runtime),
        sum(record["passed"] for record in runtime) / len(runtime),
    )
    raw_metrics["batch_completion_rate"] = _ratio(
        runtime,
        lambda record: (
            record["task_id"] in {"R01", "R02"},
            bool(record.get("details", {}).get("batch_completion")),
        ),
    )
    raw_metrics["partial_failure_fidelity_rate"] = _ratio(
        runtime,
        lambda record: (
            record["task_id"] == "R03",
            bool(record.get("details", {}).get("partial_fidelity")),
        ),
    )
    raw_metrics["recovery_success_rate"] = _ratio(
        runtime,
        lambda record: (
            record["task_id"] == "R03",
            bool(record.get("details", {}).get("recovery_success")),
        ),
    )
    repeat_records = [record for record in runtime if record["task_id"] in {"R03", "R04"}]
    repeat_count = sum(
        int(record.get("details", {}).get("successful_repeat_count", 0))
        for record in repeat_records
    )
    successful_items = sum(
        int(record.get("details", {}).get("successful_item_count", 0)) for record in repeat_records
    )
    raw_metrics["successful_item_repeat_rate"] = (
        repeat_count,
        successful_items,
        repeat_count / successful_items if successful_items else 0.0,
    )
    raw_metrics["stale_rejection_rate"] = _ratio(
        runtime,
        lambda record: (
            record["task_id"] == "R05",
            bool(record.get("details", {}).get("stale_rejected")),
        ),
    )
    raw_metrics["restart_recovery_rate"] = _ratio(
        runtime,
        lambda record: (
            record["task_id"] == "R06",
            bool(record.get("details", {}).get("restart_recovery")),
        ),
    )
    model_latencies = [float(record["latency_seconds"]) for record in model]
    latency_p95 = _percentile(model_latencies, 0.95)

    metrics: dict[str, Any] = {}
    for name, (numerator, denominator, value) in raw_metrics.items():
        threshold_name = name + (
            "_max"
            if name.endswith("_rate")
            and name
            in {
                "incorrect_auto_binding_rate",
                "invalid_question_rate",
                "successful_item_repeat_rate",
            }
            else ""
        )
        threshold = task_set.thresholds.get(threshold_name, task_set.thresholds.get(name))
        is_maximum = threshold_name.endswith("_max")
        metrics[name] = {
            "numerator": numerator,
            "denominator": denominator,
            "value": round(value, 6),
            "threshold": threshold,
            "direction": "maximum" if is_maximum else "minimum",
            "passed": (
                value <= threshold
                if is_maximum and threshold is not None
                else value >= threshold
                if threshold is not None
                else None
            ),
        }
    latency_threshold = task_set.thresholds["model_latency_p95_seconds_max"]
    metrics["model_latency_p95_seconds"] = {
        "value": round(latency_p95, 4),
        "threshold": latency_threshold,
        "direction": "maximum",
        "passed": latency_p95 <= latency_threshold,
    }

    scored_calls = [call for call in network_calls if call.run_key != "__capability_probe__"]
    probe_calls = [call for call in network_calls if call.run_key == "__capability_probe__"]
    hit = sum(call.input_cache_hit_tokens for call in network_calls)
    miss = sum(call.input_cache_miss_tokens for call in network_calls)
    output = sum(call.output_tokens for call in network_calls)
    pricing = task_set.pricing_cny_per_million_tokens
    estimated_cost = (
        hit * pricing["input_cache_hit"]
        + miss * pricing["input_cache_miss"]
        + output * pricing["output"]
    ) / 1_000_000
    blocking = [name for name, metric in metrics.items() if metric.get("passed") is False]
    return {
        "qualification": "PASS" if not blocking else "NO_GO",
        "blocking_metrics": blocking,
        "metrics": metrics,
        "latency": {
            "model_task_median_seconds": round(statistics.median(model_latencies), 4),
            "model_task_p95_seconds": round(latency_p95, 4),
            "model_task_max_seconds": round(max(model_latencies), 4),
            "runtime_task_median_seconds": round(
                statistics.median(float(record["latency_seconds"]) for record in runtime), 4
            ),
        },
        "provider_usage": {
            "scored_http_call_count": len(scored_calls),
            "capability_probe_http_call_count": len(probe_calls),
            "failed_http_call_count": sum(
                call.status_code is None or call.status_code >= 400 for call in network_calls
            ),
            "input_tokens": sum(call.input_tokens for call in network_calls),
            "input_cache_hit_tokens": hit,
            "input_cache_miss_tokens": miss,
            "output_tokens": output,
            "estimated_cost_cny": round(estimated_cost, 6),
            "pricing_assumption": "provider-reported cache split; unclassified input is priced as cache miss",
            "pricing_source": task_set.pricing_source,
        },
    }


def _git_value(*args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=REPOSITORY, text=True, encoding="utf-8"
    ).strip()


def _write_report(output: Path, report: dict[str, Any]) -> None:
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = report["summary"]
    lines = [
        "# PlotAgent SEQ-70 Agent 自动评测",
        "",
        f"- 资格结论：**{summary['qualification']}**",
        f"- 固定任务：24 项 × 3 次 = {len(report['runs'])} 次",
        f"- 模型：{report['provider']['model_id']}",
        f"- 估算成本：¥{summary['provider_usage']['estimated_cost_cny']:.6f}",
        f"- 报告生成：{report['generated_at']}",
        "",
        "本报告不使用综合分数；每个指标独立判定。测试数据均为固定规则生成的合成数据。",
        "",
        "## 指标",
        "",
        "| 指标 | 结果 | 门槛 | 判定 |",
        "|---|---:|---:|---|",
    ]
    for name, metric in summary["metrics"].items():
        lines.append(
            f"| {name} | {metric['value']} | {metric['threshold']} | "
            f"{'通过' if metric['passed'] else '未通过'} |"
        )
    failures = [run for run in report["runs"] if not run["passed"]]
    lines.extend(["", "## 失败样例", ""])
    if not failures:
        lines.append("无。")
    else:
        for run in failures:
            details = run.get("score", {}).get("failures") if run.get("score") else run.get("error")
            lines.append(f"- {run['task_id']} / 第 {run['repetition']} 次：`{details}`")
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            name,
            metric["value"],
            metric["threshold"],
            "PASS" if metric["passed"] else "FAIL",
        )
        for name, metric in summary["metrics"].items()
    )
    failures_html = (
        "".join(
            f"<li><b>{run['task_id']} · r{run['repetition']}</b>: "
            f"{json.dumps(run.get('score', {}).get('failures') if run.get('score') else run.get('error'), ensure_ascii=False)}</li>"
            for run in failures
        )
        or "<li>无</li>"
    )
    html = f"""<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><title>SEQ-70 Agent Eval</title>
<style>body{{font:15px system-ui;margin:36px;background:#f4f5f7;color:#202124}}main{{max-width:1100px;margin:auto;background:white;padding:30px;border-radius:14px}}table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}.status{{font-size:26px;font-weight:700}}</style>
<main><h1>PlotAgent SEQ-70 Agent 自动评测</h1><p class=\"status\">{summary["qualification"]}</p>
<p>24 项固定任务 × 3 次。真实模型决策与本地恢复任务分层报告；测试数据全部为合成数据。</p>
<table><thead><tr><th>指标</th><th>结果</th><th>门槛</th><th>判定</th></tr></thead><tbody>{rows}</tbody></table>
<h2>失败样例</h2><ul>{failures_html}</ul><p><a href=\"report.json\">完整 JSON</a> · <a href=\"REPORT.md\">Markdown 报告</a></p></main></html>"""
    (output / "index.html").write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-set", type=Path, default=DEFAULT_TASK_SET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    task_set_path = args.task_set.resolve()
    task_set = Seq70TaskSet.model_validate_json(task_set_path.read_text(encoding="utf-8"))
    output = (
        args.output.resolve()
        if args.output is not None
        else REPOSITORY / "build" / "seq70-agent-eval" / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {output}")
    output.mkdir(parents=True)

    provider, transport = _create_provider(task_set)
    transport.run_key = "__capability_probe__"
    probe_started = time.perf_counter()
    capabilities = asyncio.run(provider.resolve_capabilities())
    probe_seconds = time.perf_counter() - probe_started
    print(
        f"provider={task_set.provider['model_id']} capability={capabilities.output_capability.value} "
        f"protocol={capabilities.protocol.value} probe={probe_seconds:.2f}s",
        flush=True,
    )

    records: list[dict[str, Any]] = []
    total = len(task_set.tasks) * task_set.repeats
    position = 0
    try:
        for repetition in range(1, task_set.repeats + 1):
            for task in task_set.tasks:
                position += 1
                print(f"[{position}/{total}] {task.task_id} r{repetition}", flush=True)
                if task.layer == "model":
                    record = _run_model_task(
                        task_set,
                        task,
                        repetition,
                        provider,
                        transport,
                    )
                else:
                    record = _run_runtime_task(task, repetition)
                records.append(record)
                print(
                    f"  {'PASS' if record['passed'] else 'FAIL'} {record['latency_seconds']:.2f}s",
                    flush=True,
                )
                checkpoint = {
                    "schema_version": task_set.schema_version,
                    "completed": len(records),
                    "total": total,
                    "runs": records,
                }
                (output / "checkpoint.json").write_text(
                    json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"
                )
    finally:
        transport.inner.close()

    summary = _aggregate(task_set, records, transport.calls)
    report = {
        "schema_version": task_set.schema_version,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "repository_commit": _git_value("rev-parse", "HEAD"),
        "task_set_path": str(task_set_path),
        "task_set_hash": canonical_hash(json.loads(task_set_path.read_text(encoding="utf-8"))),
        "synthetic_data": True,
        "provider": task_set.provider,
        "capability_probe": {
            "output_capability": capabilities.output_capability.value,
            "protocol": capabilities.protocol.value,
            "latency_seconds": round(probe_seconds, 4),
        },
        "summary": summary,
        "runs": records,
    }
    _write_report(output, report)
    print(
        json.dumps(
            {"output": str(output), "qualification": summary["qualification"]}, ensure_ascii=False
        )
    )
    return 0 if summary["qualification"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
