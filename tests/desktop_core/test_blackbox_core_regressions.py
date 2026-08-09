from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from plotagent.contracts.base import PreparedDatasetRef
from plotagent.contracts.calculations import ConfusionCountSpec
from plotagent.desktop_core.application import _agent_failure_payload, _axis_labels
from plotagent.desktop_core.services import RpcServiceError
from tests.desktop_core.test_application import ApplicationHarness, _create_open


def _write_csv(path: Path, value: int) -> None:
    path.write_text(f"x,y\n0,{value}\n1,{value + 1}\n", encoding="utf-8")


def test_import_identity_survives_list_and_describe(tmp_path: Path) -> None:
    source = tmp_path / "experiment.csv"
    _write_csv(source, 3)
    app = ApplicationHarness(tmp_path / "app")
    try:
        project_id, revision = _create_open(app)
        imported = app.call(
            "datasets.import",
            {
                "project_id": project_id,
                "resource_id": "resource:experiment",
                "source_path": str(source),
                "idempotency_key": "import-experiment",
                "expected_version": revision,
                "options": {},
            },
        )
        dataset = imported["datasets"][0]
        assert dataset["display_name"] == "experiment:block_1"
        assert dataset["source_file_name"] == "experiment.csv"
        assert dataset["source_block"] == "block_1"

        listed = app.call("datasets.list", {"project_id": project_id})["datasets"][0]
        described = app.call(
            "datasets.describe",
            {
                "project_id": project_id,
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
            },
        )["dataset"]
        assert listed["display_name"] == described["display_name"]
        assert listed["source_file_name"] == described["source_file_name"]
    finally:
        app.close()


def test_fast_consecutive_imports_are_serially_rebased(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    _write_csv(first, 1)
    _write_csv(second, 10)
    app = ApplicationHarness(tmp_path / "app")
    try:
        project_id, revision = _create_open(app)
        common = {"project_id": project_id, "expected_version": revision, "options": {}}
        imported_first = app.call(
            "datasets.import",
            {
                **common,
                "resource_id": "resource:first",
                "source_path": str(first),
                "idempotency_key": "import-first",
            },
        )
        imported_second = app.call(
            "datasets.import",
            {
                **common,
                "resource_id": "resource:second",
                "source_path": str(second),
                "idempotency_key": "import-second",
            },
        )

        assert imported_first["rebased"] is False
        assert imported_second["rebased"] is True
        listed = app.call("datasets.list", {"project_id": project_id})
        assert len(listed["datasets"]) == 2
        assert listed["project_version"] == revision + 2
        task_ids = {imported_first["task_id"], imported_second["task_id"]}
        task_states = {
            item["task_id"]: item["state"]
            for item in app.tasks.snapshot()["tasks"]
            if item["task_id"] in task_ids
        }
        assert task_states == {task_id: "succeeded" for task_id in task_ids}

        with pytest.raises(RpcServiceError) as captured:
            app.call(
                "datasets.import",
                {
                    **common,
                    "resource_id": "resource:future",
                    "source_path": str(second),
                    "idempotency_key": "import-future",
                    "expected_version": listed["project_version"] + 1,
                },
            )
        assert captured.value.code == "VERSION_CONFLICT"
    finally:
        app.close()


def test_imported_project_identity_survives_core_restart(tmp_path: Path) -> None:
    source = tmp_path / "restart-source.csv"
    _write_csv(source, 8)
    root = tmp_path / "app"
    first_app = ApplicationHarness(root)
    try:
        project_id, revision = _create_open(first_app)
        imported = first_app.call(
            "datasets.import",
            {
                "project_id": project_id,
                "resource_id": "resource:restart",
                "source_path": str(source),
                "idempotency_key": "import-restart",
                "expected_version": revision,
                "options": {},
            },
        )
        expected_dataset = imported["datasets"][0]
    finally:
        first_app.close()

    reopened_app = ApplicationHarness(root)
    try:
        opened = reopened_app.call("projects.open", {"project_id": project_id})
        listed = reopened_app.call("datasets.list", {"project_id": project_id})
    finally:
        reopened_app.close()

    assert opened["project_version"] == revision + 1
    assert listed["datasets"][0]["source_dataset_id"] == expected_dataset["source_dataset_id"]
    assert listed["datasets"][0]["display_name"] == "restart-source:block_1"
    assert listed["datasets"][0]["source_file_name"] == "restart-source.csv"


def test_s61_preaggregated_count_role_reaches_the_fixed_calculation(tmp_path: Path) -> None:
    app = ApplicationHarness(tmp_path / "app")
    try:
        spec = app.application._calculation_spec(  # noqa: SLF001
            "S61",
            "plot:s61",
            PreparedDatasetRef(
                prepared_dataset_id="prepared:s61",
                prepared_version=1,
                content_hash="a" * 64,
            ),
            {
                "actual": "field:actual",
                "predicted": "field:predicted",
                "count": "field:count",
            },
        )
    finally:
        app.close()

    assert isinstance(spec, ConfusionCountSpec)
    assert spec.count_field == "field:count"


def test_scientific_axis_defaults_follow_bound_roles() -> None:
    fields = {
        "field:row": SimpleNamespace(name="Observed row"),
        "field:column": SimpleNamespace(name="Measured column"),
        "field:actual": SimpleNamespace(name="Ground truth"),
        "field:predicted": SimpleNamespace(name="Model class"),
        "field:log2fc": SimpleNamespace(name="log2 fold change"),
        "field:pvalue": SimpleNamespace(name="raw p"),
        "field:qvalue": SimpleNamespace(name="adjusted q"),
    }

    assert _axis_labels(
        "K20",
        ("row", "column", "value"),
        {"row": "field:row", "column": "field:column"},
        fields,
    ) == ("Measured column", "Observed row")
    assert _axis_labels(
        "K21",
        ("row_label", "column_label", "correlation"),
        {"row_label": "field:row", "column_label": "field:column"},
        fields,
    ) == ("Measured column", "Observed row")
    assert _axis_labels(
        "S61",
        ("actual", "predicted"),
        {"actual": "field:actual", "predicted": "field:predicted"},
        fields,
    ) == ("Model class", "Ground truth")
    assert _axis_labels(
        "S07",
        ("feature", "log2fc", "pvalue"),
        {"log2fc": "field:log2fc", "pvalue": "field:pvalue"},
        fields,
    ) == ("log2 fold change", "-log10(p)")
    assert _axis_labels(
        "S07",
        ("feature", "log2fc", "pvalue"),
        {
            "log2fc": "field:log2fc",
            "pvalue": "field:pvalue",
            "qvalue": "field:qvalue",
        },
        fields,
    ) == ("log2 fold change", "-log10(q)")


def test_agent_timeout_and_validation_failures_have_non_blind_retry_semantics() -> None:
    timeout = _agent_failure_payload("REQUEST_TIMEOUT")
    assert timeout["error"]["side_effects_committed"] is False
    assert timeout["error"]["retry"] == {
        "allowed": True,
        "automatic": False,
        "requires_new_client_model_run_id": True,
    }

    invalid = _agent_failure_payload("AGENT_FIELD_ROLE_INVALID")
    assert invalid["error"]["retry"] == {
        "allowed": False,
        "automatic": False,
        "requires_new_client_model_run_id": False,
    }


def test_axis_defaults_survive_unrelated_edit_and_explicit_axis_edit_wins(
    tmp_path: Path,
) -> None:
    source = tmp_path / "confusion-counts.csv"
    source.write_text(
        "Actual,Predicted,Count\nCat,Cat,8\nCat,Dog,2\nDog,Cat,1\nDog,Dog,9\n",
        encoding="utf-8",
    )
    app = ApplicationHarness(tmp_path / "app-axis-labels")
    try:
        project_id, revision = _create_open(app)
        imported = app.call(
            "datasets.import",
            {
                "project_id": project_id,
                "resource_id": "resource:confusion-counts",
                "source_path": str(source),
                "idempotency_key": "import-confusion-counts",
                "expected_version": revision,
                "options": {},
            },
        )
        dataset = imported["datasets"][0]
        fields = {item["name"]: item["field_id"] for item in dataset["fields"]}
        created = app.call(
            "plots.create",
            {
                "project_id": project_id,
                "plot_id": "plot:confusion-counts",
                "chart_type_id": "S61",
                "source_dataset_id": dataset["source_dataset_id"],
                "source_version": dataset["source_version"],
                "field_mapping": {
                    "actual": fields["Actual"],
                    "predicted": fields["Predicted"],
                    "count": fields["Count"],
                },
                "idempotency_key": "create-confusion-counts",
                "expected_version": imported["project_version"],
            },
        )

        def labels(result: dict[str, object]) -> dict[str, str]:
            spec = result["spec"]
            assert isinstance(spec, dict)
            return {axis["orientation"]: axis["label"]["nodes"][0]["text"] for axis in spec["axes"]}

        assert labels(created) == {"x": "Predicted", "y": "Actual"}
        titled = app.call(
            "plots.patch",
            {
                "project_id": project_id,
                "plot_id": "plot:confusion-counts",
                "expected_version": 1,
                "idempotency_key": "title-confusion-counts",
                "patch": {
                    "operation": "set_plot_title",
                    "target_id": "plot:confusion-counts",
                    "expected_plot_version": 1,
                    "title": {"nodes": [{"kind": "plain", "text": "Confusion counts"}]},
                },
            },
        )
        assert labels(titled) == {"x": "Predicted", "y": "Actual"}
        relabelled = app.call(
            "plots.patch",
            {
                "project_id": project_id,
                "plot_id": "plot:confusion-counts",
                "expected_version": 2,
                "idempotency_key": "relabel-confusion-counts",
                "patch": {
                    "operation": "set_axis_label",
                    "target_id": "axis:x",
                    "expected_plot_version": 2,
                    "label": {"nodes": [{"kind": "plain", "text": "Predicted class"}]},
                },
            },
        )
        assert labels(relabelled) == {"x": "Predicted class", "y": "Actual"}
    finally:
        app.close()
