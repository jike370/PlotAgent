"""Explicit local authority for the PlotAgent MCP server."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, model_validator

from plotagent.contracts.base import StrictModel


class McpServerSettings(StrictModel):
    engine_root: Path
    import_roots: tuple[Path, ...] = Field(min_length=1)
    export_root: Path

    @model_validator(mode="after")
    def normalized_distinct_roots(self) -> McpServerSettings:
        engine_root = self.engine_root.resolve()
        export_root = self.export_root.resolve()
        import_roots = tuple(root.resolve() for root in self.import_roots)
        if engine_root == export_root:
            raise ValueError("engine and export roots must be different")
        if len(import_roots) != len(set(import_roots)):
            raise ValueError("import roots must be unique")
        object.__setattr__(self, "engine_root", engine_root)
        object.__setattr__(self, "export_root", export_root)
        object.__setattr__(self, "import_roots", import_roots)
        return self

    @classmethod
    def from_environment(cls) -> McpServerSettings:
        import_value = _required_environment("PLOTAGENT_ENGINE_IMPORT_ROOTS")
        return cls(
            engine_root=Path(_required_environment("PLOTAGENT_ENGINE_ROOT")),
            import_roots=tuple(Path(value) for value in import_value.split(os.pathsep) if value),
            export_root=Path(_required_environment("PLOTAGENT_ENGINE_EXPORT_ROOT")),
        )


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required")
    return value
