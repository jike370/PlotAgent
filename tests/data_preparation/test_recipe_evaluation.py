from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "run_data_preparation_eval.py"
CASES = ROOT / "tests" / "fixtures" / "data_preparation" / "recipe-eval-cases.json"


def test_frozen_recipe_cost_and_safety_matrix_qualifies() -> None:
    spec = importlib.util.spec_from_file_location("run_data_preparation_eval", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.evaluate(CASES)

    assert report["qualified"] is True
    assert report["metrics"]["case_count"] == 14
    assert report["metrics"]["wrong_auto_match_rate"] == 0
    assert report["metrics"]["repeat_model_turn_rate"] == 0
    assert report["metrics"]["scored_model_turns"] == 0
    assert report["metrics"]["estimated_model_cost_cny"] == 0
