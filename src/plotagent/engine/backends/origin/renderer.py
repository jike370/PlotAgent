"""Recipe-driven Origin renderer dispatch.

The worker owns the Origin process.  This registry owns the closed mapping
from a validated :class:`OriginRecipe` to one reviewed Python executor.  It
prevents an old or ad-hoc binder from being reachable merely because a module
still exists in the repository.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from plotagent.engine.ports import EngineReadback

from .messages import OriginWorkerRequest
from .recipe import ORIGIN_RENDERABLE_RECIPES, OriginRecipe

OriginRecipeExecutor = Callable[
    [Any, OriginWorkerRequest, Path, Path],
    EngineReadback,
]


class OriginRendererRegistry:
    """Exact, immutable renderer set for the current recipe catalog."""

    def __init__(self, renderers: Mapping[str, OriginRecipeExecutor]) -> None:
        expected = {
            recipe.binder_key
            for recipe in ORIGIN_RENDERABLE_RECIPES.values()
            if recipe.binder_key is not None
        }
        actual = set(renderers)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(
                f"Origin renderer registry differs from recipes; missing={missing}, extra={extra}"
            )
        self._renderers = MappingProxyType(dict(renderers))

    @property
    def binder_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._renderers))

    def execute(
        self,
        recipe: OriginRecipe,
        op: Any,
        request: OriginWorkerRequest,
        install_dir: Path,
        output: Path,
    ) -> EngineReadback:
        if recipe.support_status != "renderable" or recipe.binder_key is None:
            raise ValueError(f"Origin recipe {recipe.profile_id} is not renderable")
        if request.document.profile_id != recipe.profile_id:
            raise ValueError("Origin request profile differs from the selected recipe")
        return self._renderers[recipe.binder_key](op, request, install_dir, output)
