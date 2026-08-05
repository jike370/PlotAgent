"""Repository adapter boundary for the pure Figure service."""

from __future__ import annotations

from typing import Protocol

from plotagent.contracts.base import PlotSpecRef
from plotagent.contracts.plots import FigureSpec
from plotagent.figures.models import FigureSourceSnapshot


class FigureRepository(Protocol):
    def get_plot_snapshot(self, plot_ref: PlotSpecRef) -> FigureSourceSnapshot: ...

    def get_latest_plot_ref(self, plot_id: str) -> PlotSpecRef: ...

    def get_figure(self, figure_id: str) -> FigureSpec: ...

    def find_by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> tuple[str, FigureSpec] | None: ...

    def commit_figure(
        self,
        project_id: str,
        idempotency_key: str,
        request_hash: str,
        figure: FigureSpec,
        expected_version: int | None,
    ) -> FigureSpec: ...
