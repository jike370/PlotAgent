from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from plotagent.engine import (
    CreatePlot,
    EngineCapability,
    EngineCatalog,
    EngineCommandError,
    EngineDataRef,
    EngineProfile,
    FieldBinding,
    PlotDocumentRepository,
    PlotEngineService,
    SetAxis,
    SetLegend,
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
            SetAxis(action_id="action:y-log", target="axis:demo.y", scale="log10")
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
                SetLegend(action_id="action:legend", target="legend:demo.main", visible=False)
            )


def test_catalog_is_not_bound_to_the_bundled_agent() -> None:
    source = inspect.getsource(__import__("plotagent.engine.service", fromlist=["*"]))
    assert "from plotagent.agent" not in source
    assert "PlotSpec" not in source
    assert "ResolvedPlot" not in source
