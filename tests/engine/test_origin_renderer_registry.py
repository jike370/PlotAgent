from __future__ import annotations

from pathlib import Path

import pytest

from plotagent.engine.backends.origin.recipe import ORIGIN_RENDERABLE_RECIPES, origin_recipe
from plotagent.engine.backends.origin.renderer import OriginRendererRegistry


def _executor(*_args):
    return object()


def _complete_mapping():
    return {
        recipe.binder_key: _executor
        for recipe in ORIGIN_RENDERABLE_RECIPES.values()
        if recipe.binder_key is not None
    }


def test_registry_requires_exactly_the_34_renderable_recipes() -> None:
    registry = OriginRendererRegistry(_complete_mapping())

    assert len(registry.binder_keys) == 34
    assert set(registry.binder_keys) == set(ORIGIN_RENDERABLE_RECIPES)


def test_registry_rejects_missing_and_unregistered_renderers() -> None:
    missing = _complete_mapping()
    missing.pop("K01")
    with pytest.raises(ValueError, match=r"missing=\['K01'\]"):
        OriginRendererRegistry(missing)

    extra = _complete_mapping() | {"S21": _executor}
    with pytest.raises(ValueError, match=r"extra=\['S21'\]"):
        OriginRendererRegistry(extra)


def test_registry_rejects_request_recipe_mismatch() -> None:
    registry = OriginRendererRegistry(_complete_mapping())
    request = type("Request", (), {"document": type("Document", (), {"profile_id": "K02"})()})()

    with pytest.raises(ValueError, match="differs"):
        registry.execute(origin_recipe("K01"), object(), request, Path("."), Path("x.opju"))
