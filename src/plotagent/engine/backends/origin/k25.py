"""Official-template K25 composition of native child Origin projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import ceil, sqrt
from pathlib import Path
from typing import Any

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    AddAnnotation,
    CreatePlot,
    PlotDocument,
    PlotEngineAction,
    SetChartParameter,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.repository import document_ref

from .messages import OriginWorkerRequest
from .profile import K25_ORIGIN_PROFILE, resolve_official_template

_TITLE = "_ENGINE_TITLE"
_GRAPH_NAME = "K25Merged"


@dataclass(frozen=True, slots=True)
class _CompositeState:
    title: str = ""
    columns: int = 0
    annotations: tuple[AddAnnotation, ...] = ()


def _trusted_path(path: Path) -> str:
    resolved = str(path.resolve())
    if any(character in resolved for character in ('"', "\r", "\n")):
        raise ValueError("Origin component path contains an unsafe character")
    return resolved.replace("/", "\\")


def _append_project_command(path: Path) -> str:
    return f'doc -a "{_trusted_path(path)}";'


def _merge_command(graph_names: tuple[str, ...], *, rows: int, columns: int) -> str:
    if not graph_names or any(not name.replace("_", "").isalnum() for name in graph_names):
        raise ValueError("Origin component graph names must be safe identifiers")
    if rows < 1 or columns < 1:
        raise ValueError("Origin composition grid must be positive")
    graphs = "+char(10)$+".join(f'"{name}"' for name in graph_names)
    return (
        "merge_graph option:=specified "
        f"graphs:={graphs} keep:=1 arrange:=1 row:={rows} col:={columns} "
        "newlayer:=1 groupgraph:=1 smartarrange:=0 "
        f"ogp:=[{_GRAPH_NAME}];"
    )


class K25OriginProject:
    """Append exact child OPJUs and merge their native graph windows."""

    def __init__(self, op: Any) -> None:
        self.op = op
        self.graph: Any = None
        self.source_graphs: tuple[Any, ...] = ()
        self.component_layer_counts: tuple[int, ...] = ()

    def create(
        self,
        install_dir: Path,
        document: PlotDocument,
        component_opjus: tuple[Path, ...],
        state: _CompositeState,
    ) -> None:
        if len(component_opjus) != len(document.components):
            raise ValueError("K25 component OPJU count differs from its PlotDocument")
        if not 2 <= len(component_opjus) <= 4:
            raise ValueError("K25 requires two to four component OPJUs")
        template = resolve_official_template(install_dir, K25_ORIGIN_PROFILE)
        self.op.new(asksave=False)
        source_graphs: list[Any] = []
        layer_counts: list[int] = []
        for index, project in enumerate(component_opjus, start=1):
            if not project.is_file():
                raise FileNotFoundError(f"K25 component OPJU is missing: {project}")
            before = {item.name for item in self.op.pages("g")}
            self.op.lt_exec(_append_project_command(project))
            added = tuple(item for item in self.op.pages("g") if item.name not in before)
            if len(added) != 1:
                raise RuntimeError("each K25 component OPJU must contain exactly one graph page")
            graph = added[0]
            graph.name = f"K25C{index}"
            count = len(tuple(graph))
            if count < 1:
                raise RuntimeError("a K25 component graph has no native layers")
            source_graphs.append(graph)
            layer_counts.append(count)

        merged = self.op.new_graph(
            _GRAPH_NAME,
            template=str(template.with_suffix(template.suffix.lower())),
            hidden=True,
        )
        if merged is None:
            raise RuntimeError("Origin could not create K25 from mgroups.otpu")
        columns = state.columns or ceil(sqrt(len(source_graphs)))
        rows = ceil(len(source_graphs) / columns)
        self.op.lt_exec(
            _merge_command(
                tuple(item.name for item in source_graphs),
                rows=rows,
                columns=columns,
            )
        )
        graphs = tuple(self.op.pages("g"))
        self.graph = next((item for item in graphs if item.name == _GRAPH_NAME), None)
        if self.graph is None:
            raise RuntimeError("Origin merge_graph did not produce the requested K25 page")
        self.source_graphs = tuple(source_graphs)
        self.component_layer_counts = tuple(layer_counts)
        self._decorate(document, state)

    def open(self, output: Path, document: PlotDocument) -> None:
        self.op.new(asksave=False)
        if not self.op.open(str(output), readonly=False, asksave=False):
            raise RuntimeError("Origin could not reopen K25")
        graphs = tuple(self.op.pages("g"))
        self.graph = next((item for item in graphs if item.name == _GRAPH_NAME), None)
        if self.graph is None:
            raise RuntimeError("reopened K25 has no merged graph page")
        sources: list[Any] = []
        for index in range(1, len(document.components) + 1):
            graph = next((item for item in graphs if item.name == f"K25C{index}"), None)
            if graph is None:
                raise RuntimeError("reopened K25 lost one component graph")
            sources.append(graph)
        self.source_graphs = tuple(sources)
        self.component_layer_counts = tuple(len(tuple(item)) for item in sources)

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.op.save(str(output))

    def verify(
        self,
        request: OriginWorkerRequest,
        state: _CompositeState,
    ) -> EngineReadback:
        if len(self.source_graphs) != len(request.document.components):
            raise RuntimeError("Origin K25 component graph count differs after reopen")
        merged_layers = tuple(self.graph)
        expected_layers = sum(self.component_layer_counts)
        if len(merged_layers) != expected_layers:
            raise RuntimeError("Origin K25 merged layer count differs after reopen")
        first = merged_layers[0]
        title = first.label(_TITLE)
        if state.title and (
            title is None or title.text != state.title or title.get_int("show") == 0
        ):
            raise RuntimeError("Origin K25 title differs after reopen")
        for annotation in state.annotations:
            label = self._annotation_layer(annotation).label(self._annotation_name(annotation))
            if label is None or label.text != annotation.text or label.get_int("show") == 0:
                raise RuntimeError("Origin K25 annotation differs after reopen")

        token = request.document.plot_id.removeprefix("plot:")
        objects: list[EngineObjectRef] = [
            EngineObjectRef(
                semantic_id=request.document.plot_id,
                backend="origin",
                object_kind="merged_graph",
                native_ref=f"graph:{self.graph.name}",
            )
        ]
        offset = 0
        for index, count in enumerate(self.component_layer_counts, start=1):
            objects.append(
                EngineObjectRef(
                    semantic_id=f"panel:{token}.component_{index}",
                    backend="origin",
                    object_kind="component_panel",
                    native_ref=(
                        f"graph:{self.graph.name}.layers:{offset + 1}-{offset + count}"
                    ),
                )
            )
            offset += count
        return EngineReadback(
            document=document_ref(request.document),
            backend="origin",
            objects=tuple(objects),
            data_hash=request.source.source_hash(),
            style_hash=canonical_hash(
                {
                    "state": asdict(state),
                    "template_sha256": K25_ORIGIN_PROFILE.sha256,
                    "component_layer_counts": list(self.component_layer_counts),
                }
            ),
        )

    def _decorate(self, document: PlotDocument, state: _CompositeState) -> None:
        layers = tuple(self.graph)
        if sum(self.component_layer_counts) != len(layers):
            raise RuntimeError("Origin K25 merge did not preserve all native component layers")
        title = layers[0].label(_TITLE)
        if title is None and state.title:
            title = layers[0].add_label(state.title)
            if title is None:
                raise RuntimeError("Origin could not create the K25 title")
            title.name = _TITLE
        if title is not None:
            title.text = state.title
            title.set_int("attach", 1)
            title.set_float("x1", 0.5)
            title.set_float("y1", 0.02)
            title.set_int("show", int(bool(state.title)))
        for annotation in state.annotations:
            layer = self._annotation_layer(annotation)
            label = layer.label(self._annotation_name(annotation)) or layer.add_label(
                annotation.text
            )
            if label is None:
                raise RuntimeError("Origin could not create a K25 annotation")
            label.name = self._annotation_name(annotation)
            label.text = annotation.text
            label.set_int("show", 1)
            if annotation.coordinate_system == "page":
                label.set_int("attach", 1)
                label.set_float("x1", annotation.x)
                label.set_float("y1", 1.0 - annotation.y)
            else:
                label.set_int("attach", 0)
                label.set_float("x1", annotation.x * 100.0)
                label.set_float("y1", (1.0 - annotation.y) * 100.0)

    def _annotation_layer(self, annotation: AddAnnotation) -> Any:
        layers = tuple(self.graph)
        if annotation.coordinate_system == "page":
            return layers[0]
        index = _panel_index(annotation, len(self.component_layer_counts))
        offset = sum(self.component_layer_counts[:index])
        return layers[offset]

    @staticmethod
    def _annotation_name(annotation: AddAnnotation) -> str:
        digest = sha256(annotation.annotation_id.encode("utf-8")).hexdigest()[:12]
        return f"_ENGINE_NOTE_{digest}"


def _panel_index(annotation: AddAnnotation, count: int) -> int:
    if annotation.coordinate_system != "axes":
        raise ValueError("K25 annotations support only page or panel axes coordinates")
    marker = ".component_"
    if not annotation.target.startswith("panel:") or marker not in annotation.target:
        raise ValueError("a K25 axes annotation must target one component panel")
    try:
        index = int(annotation.target.rsplit(marker, 1)[1]) - 1
    except ValueError as error:
        raise ValueError("a K25 panel target has an invalid ordinal") from error
    if not 0 <= index < count:
        raise ValueError("a K25 panel target is outside the component range")
    return index


def _state(
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
    component_count: int,
) -> _CompositeState:
    state = _CompositeState()
    for action in actions:
        if isinstance(action, CreatePlot):
            continue
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("K25 title target does not belong to this figure")
            state = replace(state, title=action.text)
        elif isinstance(action, SetChartParameter):
            if action.target != document.plot_id or action.parameter != "panel_columns":
                raise ValueError("K25 exposes only the panel_columns figure parameter")
            if isinstance(action.value, bool) or not isinstance(action.value, int):
                raise ValueError("K25 panel_columns must be an integer")
            if not 1 <= action.value <= component_count:
                raise ValueError("K25 panel_columns is outside the component range")
            state = replace(state, columns=action.value)
        elif isinstance(action, AddAnnotation):
            if action.coordinate_system == "data":
                raise ValueError("K25 has no shared data coordinate system")
            if not 0.0 <= action.x <= 1.0 or not 0.0 <= action.y <= 1.0:
                raise ValueError("K25 page and axes annotation coordinates must be normalized")
            if action.coordinate_system == "page" and action.target != document.plot_id:
                raise ValueError("a K25 page annotation must target the figure")
            if action.coordinate_system == "axes":
                _panel_index(action, component_count)
            state = replace(state, annotations=state.annotations + (action,))
        else:
            raise ValueError(f"Origin K25 cannot apply {action.operation}")
    return state


def execute_k25_request(
    op: Any,
    request: OriginWorkerRequest,
    install_dir: Path,
    output: Path,
) -> EngineReadback:
    if not request.source.components:
        raise ValueError("Origin K25 requires component plot inputs")
    state = _state(request.document, request.actions, len(request.source.components))
    project = K25OriginProject(op)
    # K25 is rebuilt from its exact immutable child versions for every document
    # version.  It never compiles arbitrary scripts or mutates a child project.
    project.create(
        install_dir,
        request.document,
        tuple(Path(path).resolve() for path in request.component_opjus),
        state,
    )
    project.save(output)
    reopened = K25OriginProject(op)
    reopened.open(output, request.document)
    return reopened.verify(request, state)
