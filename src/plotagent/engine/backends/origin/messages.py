"""Typed subprocess boundary for Origin automation workers."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import StrictModel
from plotagent.engine.contracts import EngineDataView, PlotDocument, PlotEngineAction
from plotagent.engine.ports import EngineReadback


class OriginWorkerRequest(StrictModel):
    install_dir: Annotated[str, StringConstraints(min_length=1, strict=True)]
    output_opju: Annotated[str, StringConstraints(min_length=1, strict=True)]
    previous_opju: Annotated[str, StringConstraints(min_length=1, strict=True)] | None = None
    document: PlotDocument
    actions: Annotated[tuple[PlotEngineAction, ...], Field(min_length=1)]
    data: EngineDataView

    @model_validator(mode="after")
    def coherent_history(self) -> OriginWorkerRequest:
        if tuple(action.action_id for action in self.actions) != self.document.applied_action_ids:
            raise ValueError("Origin worker action history differs from the plot document")
        if self.document.plot_version == 1 and self.previous_opju is not None:
            raise ValueError("the first Origin version cannot have a previous project")
        if self.document.plot_version > 1 and self.previous_opju is None:
            raise ValueError("an edited Origin version requires the previous project")
        if Path(self.output_opju).suffix.casefold() != ".opju":
            raise ValueError("Origin worker output must be OPJU")
        return self


class OriginWorkerResponse(StrictModel):
    readback: EngineReadback
