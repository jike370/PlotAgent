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
    assert len(ORIGIN_RECIPES) == 38
    assert len(ORIGIN_RENDERABLE_RECIPES) == 35
    assert set(ORIGIN_RECIPES) - set(ORIGIN_RENDERABLE_RECIPES) == {"K16", "S21", "S61"}
    assert ORIGIN_RECIPES["K16"].support_status == "structural_fail"
    assert ORIGIN_RECIPES["S21"].support_status == "dependency_blocked"
    assert ORIGIN_RECIPES["S61"].support_status == "automation_blocked"


def test_renderable_recipes_have_closed_routes_and_pinned_template_assets() -> None:
    for profile_id, recipe in ORIGIN_RENDERABLE_RECIPES.items():
        assert recipe.binder_key == profile_id
        assert recipe.official_help_url.startswith(
            ("https://docs.originlab.com/", "https://cloud.originlab.com/")
        )
        assert recipe.designation_contract
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
        ("K10", "COLUMN.otpu"),
        ("K11", "COLUMN.otpu"),
        ("K19", "LINE.otpu"),
        ("K24", "Grouped.otp"),
        ("X05", "Beeswarm.otpu"),
        ("X09", "FloatBar.otp"),
        ("X24", "ParetoBin.otpu"),
    ),
)
def test_recipe_registry_rejects_the_previous_wrong_template_mappings(
    profile_id: str,
    filename: str,
) -> None:
    assert origin_recipe(profile_id).primary_template is not None
    assert origin_recipe(profile_id).primary_template.filename == filename  # type: ignore[union-attr]


def test_blocked_profiles_fail_before_origin_automation() -> None:
    for profile_id in ("K16", "S21", "S61"):
        with pytest.raises(ValueError, match=profile_id):
            origin_recipe(profile_id)
        assert origin_recipe(profile_id, require_renderable=False).profile_id == profile_id


def test_manual_native_property_recipes_keep_the_exact_human_gate() -> None:
    manual = {
        profile_id: recipe
        for profile_id, recipe in ORIGIN_RENDERABLE_RECIPES.items()
        if recipe.proof_level == "manual_native_property"
    }

    assert len(manual) == 18
    assert all(recipe.manual_gate for recipe in manual.values())
    assert "Whisker" in manual["K13"].manual_gate
    assert "Drop To" in manual["X02"].manual_gate
