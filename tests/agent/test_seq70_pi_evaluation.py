from __future__ import annotations

import json
from pathlib import Path

from plotagent.engine.profiles import ENGINE_PROFILES

ROOT = Path(__file__).parents[2]
TASK_SET = ROOT / "tests" / "fixtures" / "seq70" / "pi_agent_tasks.json"
RUNNER = ROOT / "scripts" / "run_seq70_pi_eval.ts"
CORE_HOST = ROOT / "scripts" / "seq70_core_host.py"


def _tasks() -> dict[str, object]:
    return json.loads(TASK_SET.read_text(encoding="utf-8"))


def test_seq70_pi_task_set_is_frozen_at_24_by_3() -> None:
    payload = _tasks()
    tasks = payload["tasks"]
    assert payload["schema_version"] == "seq70-pi-agent-eval-v2"
    assert payload["repeats"] == 3
    assert len(tasks) == 24
    assert len({item["task_id"] for item in tasks}) == 24
    assert sum(item["layer"] == "model" for item in tasks) == 18
    assert sum(item["layer"] == "runtime" for item in tasks) == 6


def test_seq70_pi_model_tasks_use_current_engine_profiles_and_actions() -> None:
    payload = _tasks()
    fixtures = payload["fixtures"]
    profiles = {profile.profile_id for profile in ENGINE_PROFILES}
    operations = {
        "create_plot",
        "bind_fields",
        "set_title",
        "set_axis",
        "set_series_style",
        "set_legend",
        "set_chart_parameter",
        "add_annotation",
        "export_plot",
    }
    model_tasks = [item for item in payload["tasks"] if item["layer"] == "model"]
    assert sum(item["category"] == "plan_mapping" for item in model_tasks) == 6
    assert sum(item["category"] == "necessary_question" for item in model_tasks) == 2
    for item in model_tasks:
        assert item["fixture"] in fixtures
        selected = item.get("selected_profile_id")
        assert selected is None or selected in profiles
        expected = item["expectation"]
        operation = expected.get("operation")
        assert operation is None or operation in operations
        assert "K25" not in json.dumps(item, ensure_ascii=False)


def test_seq70_pi_runner_uses_production_runtime_and_isolated_core() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    host = CORE_HOST.read_text(encoding="utf-8")
    assert "new PiAgentRuntime" in runner
    assert "provider.runtime.get" in runner
    assert "external_decision" not in runner
    assert "DesktopApplication(args.root)" in host
    assert "get_setting(_PROVIDER_SETTING_KEY)" in host
    assert "set_setting(_PROVIDER_SETTING_KEY" in host
