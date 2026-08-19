from __future__ import annotations

from pathlib import Path

import pytest

from plotagent.engine.backends.origin.recipe import (
    ORIGIN_RECIPES,
    ORIGIN_RENDERABLE_RECIPES,
    origin_recipe,
)
from plotagent.engine.profiles import ENGINE_PROFILES


def test_recipe_registry_covers_the_public_catalog_and_closes_the_origin_scope() -> None:
    public_ids = {profile.profile_id for profile in ENGINE_PROFILES}

    assert set(ORIGIN_RECIPES) == public_ids
    assert len(ORIGIN_RECIPES) == 34
    assert len(ORIGIN_RENDERABLE_RECIPES) == 34
    assert ORIGIN_RECIPES == ORIGIN_RENDERABLE_RECIPES
    assert ORIGIN_RECIPES["S61"].support_status == "renderable"


def test_public_agent_profiles_preserve_origin_default_marker_edge_width() -> None:
    for profile in ENGINE_PROFILES:
        for capability in profile.capabilities:
            assert "marker_stroke_width_pt" not in capability.parameters


def test_renderable_recipes_have_closed_routes_and_pinned_template_assets() -> None:
    for profile_id, recipe in ORIGIN_RENDERABLE_RECIPES.items():
        assert recipe.binder_key == profile_id
        assert recipe.official_help_url.startswith(
            ("https://docs.originlab.com/", "https://cloud.originlab.com/")
        )
        assert recipe.designation_contract
        assert recipe.local_dispatch
        assert recipe.readback_contract
        assert recipe.support_status == "renderable"
        if recipe.creation_kind == "graph_template":
            assert recipe.primary_template is not None
        for template in recipe.templates:
            assert Path(template.filename).name == template.filename
            assert len(template.sha256) == 64


@pytest.mark.parametrize(
    ("profile_id", "filename"),
    (
        ("K09", "gColumn.otpu"),
        ("K10", "STACKCOLUMN.otp"),
        ("K11", "StackColP.otp"),
        ("K19", "LINE.otpu"),
        ("K24", "Grouped.otp"),
        ("X05", "Beeswarm.otpu"),
        ("X09", "FloatCol.otp"),
        ("X24", "ParetoBin.otpu"),
    ),
)
def test_recipe_registry_rejects_the_previous_wrong_template_mappings(
    profile_id: str,
    filename: str,
) -> None:
    assert origin_recipe(profile_id).primary_template is not None
    assert origin_recipe(profile_id).primary_template.filename == filename  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("profile_id", "route_fragment"),
    (
        ("K06", "worksheet -p 201 ERRBAR"),
        ("K07", "general,201 ERRORBAND"),
        ("K09", "worksheet -px ? gColumn plot_gindexed plottype:=0"),
        ("K10", "general,213 StackColumn"),
        ("K11", "general,213 StackColP"),
        ("X03", "general,201 Lollipop"),
        ("X05", "worksheet -p 206 Beeswarm"),
        ("X09", "general,207 FloatCol"),
        ("X13", "PlotToTemplate PopulationPyramid"),
        ("X23", "PlotToTemplate DOUBLEY"),
        ("X39", "BoxChartImp,BoxLser"),
        ("X40", "general,206 BeforeAfter"),
    ),
)
def test_recipe_pins_the_inspected_origin_2024_menu_dispatcher(
    profile_id: str,
    route_fragment: str,
) -> None:
    assert route_fragment in origin_recipe(profile_id).local_dispatch


def test_error_and_time_series_designations_match_the_official_routes() -> None:
    assert origin_recipe("K06").designation_contract == (
        "X",
        "Y",
        "Y error",
        "X error",
    )
    assert origin_recipe("K19").designation_contract == (
        "numeric Date/Time X",
        "one or more Y",
    )


def test_bubble_recipe_separates_the_menu_creation_id_from_persisted_plot_id() -> None:
    recipe = origin_recipe("K04")

    assert "worksheet -p 248 Bubble" in recipe.local_dispatch
    assert recipe.native_plot_types == (201,)


def test_dual_layer_recipes_pin_the_official_native_plot_families() -> None:
    population = origin_recipe("X13")
    double_y = origin_recipe("X23")

    assert population.designation_contract == ("categorical X", "left Y", "right Y")
    assert population.native_plot_types == (203, 203)
    assert double_y.designation_contract == ("shared X", "left Y", "right Y")
    assert double_y.native_plot_types == (202, 202)


def test_distribution_recipes_keep_raw_y_designations_and_native_semantics() -> None:
    for profile_id in ("K12", "K13", "K14"):
        recipe = origin_recipe(profile_id)
        assert recipe.source_layout == "worksheet_wide"
        assert recipe.designation_contract == ("one raw-observation Y per group",)
        assert recipe.native_plot_types == (206,)
        assert recipe.proof_level == "manual_native_property"

    histogram = origin_recipe("K15")
    assert histogram.source_layout == "worksheet_wide"
    assert histogram.designation_contract == ("raw observation Y",)
    assert histogram.native_plot_types == (219,)
    assert histogram.proof_level == "manual_native_property"
    assert "Data Height=Count" in histogram.readback_contract


def test_row_wise_boxchart_recipes_preserve_the_source_wide_table() -> None:
    line_series = origin_recipe("X39")
    before_after = origin_recipe("X40")

    assert line_series.source_layout == "worksheet_wide"
    assert "no hidden or transposed worksheet" in line_series.readback_contract
    assert "worksheet -p 206 BoxLser" in line_series.local_dispatch
    assert before_after.source_layout == "worksheet_wide"
    assert "no per-subject transpose" in before_after.readback_contract
    assert "BeforeAfter 0 1" in before_after.local_dispatch


def test_removed_profiles_have_no_origin_recipe() -> None:
    for profile_id in ("K05", "K16", "K17", "K25", "S01", "S05", "S07", "S21", "S25", "S31", "X01"):
        with pytest.raises(ValueError, match=profile_id):
            origin_recipe(profile_id)


def test_manual_native_property_recipes_keep_the_exact_human_gate() -> None:
    manual = {
        profile_id: recipe
        for profile_id, recipe in ORIGIN_RENDERABLE_RECIPES.items()
        if recipe.proof_level == "manual_native_property"
    }

    assert len(manual) == 19
    assert all(recipe.manual_gate for recipe in manual.values())
    assert "Whisker" in manual["K13"].manual_gate
    assert "Drop To" in manual["X02"].manual_gate
