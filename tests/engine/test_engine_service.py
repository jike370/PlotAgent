from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from plotagent.engine import (
    REMOVED_CHART_TYPE_ERROR_CODE,
    BindFields,
    CreatePlot,
    EngineCapability,
    EngineCatalog,
    EngineCommandError,
    EngineDataRef,
    EngineProfile,
    FieldBinding,
    PlotDocumentRepository,
    PlotEngineService,
    RemovedChartTypeError,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
)
from plotagent.storage.project import ProjectStore

HASH = "c" * 64


def _catalog() -> EngineCatalog:
    return EngineCatalog(
        (
            EngineProfile(
                profile_id="profile.line",
                display_name="Line",
                required_roles=("x", "y"),
                optional_roles=("group",),
                repeatable_role_prefixes=("series",),
                capabilities=(
                    EngineCapability(operation="create_plot"),
                    EngineCapability(operation="bind_fields"),
                    EngineCapability(operation="set_axis", parameters=("scale", "label")),
                    EngineCapability(operation="set_series_style"),
                ),
            ),
        )
    )


def _create(**bindings: str) -> CreatePlot:
    return CreatePlot(
        action_id="action:create",
        plot_id="plot:demo",
        profile_id="profile.line",
        data=EngineDataRef(
            kind="source",
            dataset_id="dataset.demo",
            version=1,
            content_hash=HASH,
        ),
        bindings=tuple(
            FieldBinding(role=role, field_id=field_id) for role, field_id in bindings.items()
        ),
    )


def test_service_builds_minimal_versions_from_public_actions(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:engine") as project:
        service = PlotEngineService(_catalog(), PlotDocumentRepository(project))
        created = service.execute(_create(x="field:x", y="field:y"))
        edited = service.execute(
            SetAxis(
                action_id="action:y-log",
                target="axis:demo.y",
                expected_plot_version=1,
                scale="log10",
            )
        )

        assert created.plot_version == 1
        assert edited.plot_version == 2
        assert edited.applied_action_ids == ("action:create", "action:y-log")
        assert service.repository.actions("plot:demo")[1].action.operation == "set_axis"


def test_service_rejects_profile_role_and_capability_mismatches(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:engine") as project:
        service = PlotEngineService(_catalog(), PlotDocumentRepository(project))
        with pytest.raises(EngineCommandError, match="missing required"):
            service.execute(_create(x="field:x"))
        with pytest.raises(EngineCommandError, match="unsupported field"):
            service.execute(_create(x="field:x", y="field:y", color="field:color"))

        service.execute(_create(x="field:x", y="field:y", series_1="field:z"))
        with pytest.raises(EngineCommandError, match="does not support set_legend"):
            service.execute(
                SetLegend(
                    action_id="action:legend",
                    target="legend:demo.main",
                    expected_plot_version=1,
                    visible=False,
                )
            )


@pytest.mark.parametrize(
    "profile_id",
    ("K05", "K16", "K17", "K25", "S01", "S05", "S07", "S21", "S25", "S31", "X01"),
)
def test_catalog_returns_a_stable_tombstone_for_removed_chart_types(profile_id: str) -> None:
    with pytest.raises(RemovedChartTypeError) as raised:
        _catalog().get(profile_id)

    assert raised.value.code == REMOVED_CHART_TYPE_ERROR_CODE
    assert str(raised.value) == f"CHART_TYPE_REMOVED: {profile_id}"


def test_service_rebinds_data_and_fields_as_one_new_version(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:engine") as project:
        service = PlotEngineService(_catalog(), PlotDocumentRepository(project))
        service.execute(_create(x="field:x", y="field:y"))
        rebound = service.execute(
            BindFields(
                action_id="action:rebind",
                target="plot:demo",
                expected_plot_version=1,
                data=EngineDataRef(
                    kind="prepared",
                    dataset_id="dataset.prepared",
                    version=2,
                    content_hash="e" * 64,
                ),
                bindings=(
                    FieldBinding(role="x", field_id="field:time"),
                    FieldBinding(role="y", field_id="field:response"),
                ),
            )
        )

        assert rebound.plot_version == 2
        assert rebound.data.dataset_id == "dataset.prepared"
        assert tuple(binding.field_id for binding in rebound.bindings) == (
            "field:time",
            "field:response",
        )


def test_service_rejects_parameters_not_exposed_by_the_profile(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:engine") as project:
        service = PlotEngineService(_catalog(), PlotDocumentRepository(project))
        service.execute(_create(x="field:x", y="field:y"))
        with pytest.raises(EngineCommandError, match="parameters.*symbol"):
            service.execute(
                SetSeriesStyle(
                    action_id="action:symbol",
                    target="series:demo.primary",
                    expected_plot_version=1,
                    symbol="circle",
                )
            )


def test_service_rejects_a_delayed_action_against_a_newer_document(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:engine") as project:
        service = PlotEngineService(_catalog(), PlotDocumentRepository(project))
        service.execute(_create(x="field:x", y="field:y"))
        service.execute(
            SetAxis(
                action_id="action:y-log",
                target="axis:demo.y",
                expected_plot_version=1,
                scale="log10",
            )
        )
        with pytest.raises(EngineCommandError, match="version is stale"):
            service.execute(
                SetAxis(
                    action_id="action:late",
                    target="axis:demo.y",
                    expected_plot_version=1,
                    label="Late response",
                )
            )


def test_service_rejects_reusing_an_action_id_with_different_arguments(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", project_id="project:engine") as project:
        service = PlotEngineService(_catalog(), PlotDocumentRepository(project))
        action = _create(x="field:x", y="field:y")
        service.execute(action)
        conflicting = action.model_copy(
            update={"bindings": _create(x="field:x", y="field:z").bindings}
        )
        with pytest.raises(EngineCommandError, match="already bound"):
            service.replay(conflicting)


def test_catalog_is_not_bound_to_the_bundled_agent() -> None:
    source = inspect.getsource(__import__("plotagent.engine.service", fromlist=["*"]))
    assert "from plotagent.agent" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
