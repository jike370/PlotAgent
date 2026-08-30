"""Typed subprocess boundary for Origin automation workers."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import StrictModel
from plotagent.engine.contracts import (
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    RestorePlotVersion,
)
from plotagent.engine.ports import EngineReadback, EngineRenderSource


class OriginWorkerRequest(StrictModel):
    install_dir: Annotated[str, StringConstraints(min_length=1, strict=True)]
    output_opju: Annotated[str, StringConstraints(min_length=1, strict=True)]
    previous_opju: Annotated[str, StringConstraints(min_length=1, strict=True)] | None = None
    document: PlotDocument
    actions: Annotated[tuple[PlotEngineAction, ...], Field(min_length=1)]
    source: EngineRenderSource

    @property
    def data(self) -> EngineDataView:
        return self.source.data

    @model_validator(mode="after")
    def coherent_history(self) -> OriginWorkerRequest:
        if not self.actions or not isinstance(self.actions[0], CreatePlot):
            raise ValueError("Origin worker action history must start with create_plot")
        if any(isinstance(action, RestorePlotVersion) for action in self.actions):
            raise ValueError("Origin worker cannot receive history-only restore actions")
        action_ids = tuple(action.action_id for action in self.actions)
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("Origin worker action history contains duplicate action ids")
        if self.document.plot_version == 1 and self.previous_opju is not None:
            raise ValueError("the first Origin version cannot have a previous project")
        # Some reviewed binders rebuild the requested revision completely from
        # immutable source plus the full action history.  For those recipes an
        # edited revision intentionally has no previous OPJU.  Backends own the
        # recipe policy; incremental binders still receive and validate a prior
        # project path.
        if Path(self.output_opju).suffix.casefold() != ".opju":
            raise ValueError("Origin worker output must be OPJU")
        return self


class OriginWorkerResponse(StrictModel):
    readback: EngineReadback
