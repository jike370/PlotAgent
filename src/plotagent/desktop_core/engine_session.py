"""Project-scoped production surface for the Agent Native plotting engine.

The desktop application owns this adapter, but the adapter only exposes the
engine's public action contract.  It never translates actions through the
legacy PlotSpec/compiler/rendering pipeline.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plotagent.engine import (
    EngineActionCodec,
    EngineCatalog,
    EngineDataViewRepository,
    PlotDocument,
    PlotDocumentRepository,
    PlotEngineAction,
    PlotEngineRuntime,
    PlotEngineService,
    ProjectEngineDataProvider,
    RoutedEngineDataProvider,
    RuntimeResult,
    document_ref,
)
from plotagent.engine.backends.matplotlib import (
    K01LineRenderer,
    K02LineSymbolRenderer,
    K03ScatterRenderer,
    K04BubbleRenderer,
    K06PointErrorRenderer,
    K07ErrorBandRenderer,
    K08ColumnRenderer,
    K09GroupedColumnRenderer,
    K10StackedColumnRenderer,
    K11PercentStackRenderer,
    K12StripRenderer,
    K13BoxRenderer,
    K14ViolinRenderer,
    K15HistogramRenderer,
    K16DensityRenderer,
    K18AreaRenderer,
    K19TimeSeriesRenderer,
    K20HeatmapRenderer,
    K21CorrelationMatrixRenderer,
    K22ContourRenderer,
    K24FacetRenderer,
    K25CompositeRenderer,
    MatplotlibBackend,
    S01SurvivalRenderer,
    S21ForestRenderer,
    S34NyquistRenderer,
    S61ConfusionRenderer,
    X02DropLineRenderer,
    X03LollipopRenderer,
    X05BeeswarmRenderer,
    X09FloatingIntervalRenderer,
    X13PopulationPyramidRenderer,
    X23DualYRenderer,
    X24ParetoRenderer,
    X35DualYColumnRenderer,
    X36DualYColumnLineRenderer,
    X38OffsetStackRenderer,
    X39LineSeriesRenderer,
    X40BeforeAfterRenderer,
)
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.storage.project import ProjectStore


@dataclass(slots=True)
class DesktopEngineSession:
    """One project's new plotting authority and local preview backend."""

    documents: PlotDocumentRepository
    data_views: EngineDataViewRepository
    catalog: EngineCatalog
    codec: EngineActionCodec
    service: PlotEngineService
    runtime: PlotEngineRuntime
    matplotlib: MatplotlibBackend
    artifact_root: Path

    @classmethod
    def open(cls, project: ProjectStore) -> DesktopEngineSession:
        documents = PlotDocumentRepository(project)
        data_views = EngineDataViewRepository(project)
        catalog = EngineCatalog(ENGINE_PROFILES)
        codec = EngineActionCodec(catalog)
        service = PlotEngineService(catalog, documents)
        artifact_root = project.cache_root / "agent-native" / "matplotlib"
        matplotlib = MatplotlibBackend(
            artifact_root,
            (
                K01LineRenderer(),
                K02LineSymbolRenderer(),
                K03ScatterRenderer(),
                K04BubbleRenderer(),
                K06PointErrorRenderer(),
                K07ErrorBandRenderer(),
                K08ColumnRenderer(),
                K09GroupedColumnRenderer(),
                K10StackedColumnRenderer(),
                K11PercentStackRenderer(),
                K12StripRenderer(),
                K13BoxRenderer(),
                K14ViolinRenderer(),
                K15HistogramRenderer(),
                K16DensityRenderer(),
                K18AreaRenderer(),
                K19TimeSeriesRenderer(),
                K20HeatmapRenderer(),
                K21CorrelationMatrixRenderer(),
                K22ContourRenderer(),
                K24FacetRenderer(),
                S01SurvivalRenderer(),
                S21ForestRenderer(),
                S34NyquistRenderer(),
                S61ConfusionRenderer(),
                X02DropLineRenderer(),
                X03LollipopRenderer(),
                X05BeeswarmRenderer(),
                X09FloatingIntervalRenderer(),
                X13PopulationPyramidRenderer(),
                X23DualYRenderer(),
                X24ParetoRenderer(),
                X35DualYColumnRenderer(),
                X36DualYColumnLineRenderer(),
                X38OffsetStackRenderer(),
                X39LineSeriesRenderer(),
                X40BeforeAfterRenderer(),
            ),
            composite_renderers=(K25CompositeRenderer(),),
        )
        runtime = PlotEngineRuntime(
            service,
            RoutedEngineDataProvider(
                ProjectEngineDataProvider(project),
                data_views,
            ),
            (matplotlib,),
        )
        return cls(
            documents=documents,
            data_views=data_views,
            catalog=catalog,
            codec=codec,
            service=service,
            runtime=runtime,
            matplotlib=matplotlib,
            artifact_root=artifact_root,
        )

    def execute(
        self,
        arguments: Mapping[str, object],
        *,
        expected_project_revision: int,
    ) -> dict[str, object]:
        action = self.codec.decode(arguments)
        return self.execute_action(
            action,
            expected_project_revision=expected_project_revision,
        )

    def execute_action(
        self,
        action: PlotEngineAction,
        *,
        expected_project_revision: int,
    ) -> dict[str, object]:
        """Execute one already validated public engine action."""

        result = self.runtime.execute(
            action,
            expected_project_revision=expected_project_revision,
        )
        return self._result_payload(result)

    def get(self, plot_id: str, plot_version: int | None = None) -> dict[str, object]:
        stored = self.documents.get(plot_id, plot_version)
        return self._document_payload(stored.document)

    def list_latest(self) -> tuple[dict[str, object], ...]:
        return tuple(self._document_payload(item.document) for item in self.documents.list_latest())

    def catalog_payload(self) -> dict[str, object]:
        return {
            "tool_name": self.codec.tool_name,
            "input_schema": self.codec.input_schema(),
            "profiles": self.codec.profile_manifest(),
        }

    def _result_payload(self, result: RuntimeResult) -> dict[str, object]:
        return {
            **self._document_payload(result.document),
            "readbacks": tuple(item.model_dump(mode="json") for item in result.readbacks),
        }

    def _document_payload(self, document: PlotDocument) -> dict[str, object]:
        applied_ids = set(document.applied_action_ids)
        actions = tuple(
            item.action.model_dump(mode="json")
            for item in self.documents.actions(document.plot_id)
            if item.action.action_id in applied_ids
        )
        payload: dict[str, object] = {
            "plot_id": document.plot_id,
            "plot_version": document.plot_version,
            "plot_ref": document_ref(document).model_dump(mode="json"),
            "profile_id": document.profile_id,
            "document": document.model_dump(mode="json"),
            "actions": actions,
        }
        preview = self._preview_descriptor(document, "png")
        if preview is not None:
            payload["preview"] = preview
        return payload

    def _preview_descriptor(self, document: PlotDocument, format: str) -> dict[str, Any] | None:
        path = (
            self.artifact_root
            / document.plot_id.removeprefix("plot:")
            / f"v{document.plot_version}"
            / f"preview.{format}"
        )
        if not path.is_file():
            return None
        body = path.read_bytes()
        content_hash = hashlib.sha256(body).hexdigest()
        return {
            "resource_id": "resource:engine-preview." + content_hash[:24],
            "path": str(path.resolve()),
            "content_hash": content_hash,
            "size": len(body),
            "format": format,
        }
