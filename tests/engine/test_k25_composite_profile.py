from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import plotagent.engine.backends.origin.k25 as origin_k25
from plotagent.engine import (
    AddAnnotation,
    CreatePlot,
    EngineColumn,
    EngineComponentInput,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineReadback,
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
    PlotDocumentRepository,
    PlotEngineRuntime,
    PlotEngineService,
    SetChartParameter,
    SetTitle,
)
from plotagent.engine.backends.matplotlib import (
    K01LineRenderer,
    K25CompositeRenderer,
    MatplotlibBackend,
)
from plotagent.engine.backends.origin import OriginBackend, origin_recipe
from plotagent.engine.backends.origin.k25 import (
    _append_project_command,
    _merge_command,
    execute_k25_request,
)
from plotagent.engine.backends.origin.messages import OriginWorkerRequest, OriginWorkerResponse
from plotagent.engine.backends.origin.trace import OriginExecutionTrace
from plotagent.engine.profiles import ENGINE_PROFILES, K25_COMPOSITE_PROFILE
from plotagent.engine.repository import document_ref
from plotagent.engine.service import EngineCatalog, EngineCommandError
from plotagent.storage.project import ProjectStore

HASH_A = "a" * 64
HASH_B = "b" * 64


def _data(suffix: str, content_hash: str) -> EngineDataRef:
    return EngineDataRef(
        kind="source",
        dataset_id=f"dataset.{suffix}",
        version=1,
        content_hash=content_hash,
    )


def _child_action(suffix: str, content_hash: str) -> CreatePlot:
    data = _data(suffix, content_hash)
    return CreatePlot(
        action_id=f"action:create-{suffix}",
        plot_id=f"plot:{suffix}",
        profile_id="K01",
        data=data,
        bindings=(
            FieldBinding(role="x", field_id=f"field:{suffix}.x"),
            FieldBinding(role="y", field_id=f"field:{suffix}.y"),
        ),
    )


def _child_document(action: CreatePlot) -> PlotDocument:
    return PlotDocument(
        plot_id=action.plot_id,
        plot_version=1,
        profile_id=action.profile_id,
        data=action.data,
        bindings=action.bindings,
        applied_action_ids=(action.action_id,),
    )


def _view(action: CreatePlot) -> EngineDataView:
    assert action.data is not None
    return EngineDataView(
        data=action.data,
        row_ids=("row:1", "row:2", "row:3"),
        columns=tuple(
            EngineColumn(
                field=EngineField(
                    field_id=binding.field_id,
                    name=binding.role.upper(),
                    logical_type="numeric",
                ),
                values=(1.0, 2.0, 3.0) if binding.role == "x" else (2.0, 4.0, 3.0),
            )
            for binding in action.bindings
        ),
    )


class _Provider:
    def __init__(self, views: tuple[EngineDataView, ...]) -> None:
        self.views = {view.data: view for view in views}

    def materialize(self, data, field_ids):
        view = self.views[data]
        assert {column.field.field_id for column in view.columns} == set(field_ids)
        return view


def _create_composite(
    references,
    *,
    plot_id: str = "plot:composite",
    action_id: str = "action:create-composite",
) -> CreatePlot:
    return CreatePlot(
        action_id=action_id,
        plot_id=plot_id,
        profile_id="K25",
        components=tuple(references),
    )


def test_k25_profile_is_plot_backed_and_has_no_field_binding_surface() -> None:
    assert K25_COMPOSITE_PROFILE.source_kind == "plots"
    assert K25_COMPOSITE_PROFILE.minimum_components == 2
    assert K25_COMPOSITE_PROFILE.maximum_components == 4
    assert K25_COMPOSITE_PROFILE.required_roles == ()
    assert "bind_fields" not in {item.operation for item in K25_COMPOSITE_PROFILE.capabilities}
    recipe = origin_recipe("K25")
    assert recipe.creation_kind == "composition"
    assert recipe.official_entry == "Graph > Merge Graph Windows"
    assert recipe.templates == ()


def test_k25_service_pins_exact_component_versions_and_rejects_invalid_graphs(
    tmp_path: Path,
) -> None:
    first, second = _child_action("first", HASH_A), _child_action("second", HASH_B)
    with ProjectStore.create(tmp_path / "project", project_id="project:k25") as project:
        service = PlotEngineService(
            EngineCatalog(ENGINE_PROFILES),
            PlotDocumentRepository(project),
        )
        first_document = service.execute(first)
        second_document = service.execute(second)
        references = (document_ref(first_document), document_ref(second_document))
        composite = service.execute(_create_composite(references))
        assert composite.data is None
        assert composite.components == references

        with pytest.raises(EngineCommandError, match="2-4 component"):
            service.prepare(
                _create_composite((references[0],)).model_copy(
                    update={"plot_id": "plot:too-small", "action_id": "action:too-small"}
                )
            )
        with pytest.raises(EngineCommandError, match="content hash is stale"):
            service.prepare(
                _create_composite(
                    (
                        references[0].model_copy(update={"content_hash": "c" * 64}),
                        references[1],
                    )
                ).model_copy(update={"plot_id": "plot:stale", "action_id": "action:stale"})
            )
        with pytest.raises(EngineCommandError, match="nested plot compositions"):
            service.prepare(
                _create_composite(
                    (document_ref(composite), references[0]),
                    plot_id="plot:nested",
                    action_id="action:nested",
                )
            )


def test_k25_matplotlib_composes_exact_child_versions_as_vector_svg(tmp_path: Path) -> None:
    first, second = _child_action("first", HASH_A), _child_action("second", HASH_B)
    views = (_view(first), _view(second))
    with ProjectStore.create(tmp_path / "project", project_id="project:k25-mpl") as project:
        repository = PlotDocumentRepository(project)
        service = PlotEngineService(EngineCatalog(ENGINE_PROFILES), repository)
        backend = MatplotlibBackend(
            tmp_path / "artifacts",
            (K01LineRenderer(),),
            composite_renderers=(K25CompositeRenderer(),),
        )
        runtime = PlotEngineRuntime(service, _Provider(views), (backend,))
        first_document = runtime.execute(first).document
        second_document = runtime.execute(second).document
        composite = runtime.execute(
            _create_composite((document_ref(first_document), document_ref(second_document)))
        ).document
        titled = runtime.execute(
            SetTitle(
                action_id="action:k25-title",
                target=composite.plot_id,
                expected_plot_version=1,
                text="原生组合图",
            )
        ).document
        columns_document = runtime.execute(
            SetChartParameter(
                action_id="action:k25-columns",
                target=titled.plot_id,
                expected_plot_version=2,
                parameter="panel_columns",
                value=1,
            )
        ).document
        assert columns_document.plot_version == 3
        result = runtime.execute(
            AddAnnotation(
                action_id="action:k25-note",
                target="panel:composite.component_2",
                expected_plot_version=3,
                annotation_id="annotation:second-note",
                text="B",
                x=0.1,
                y=0.9,
                coordinate_system="axes",
            )
        )

        assert result.document.plot_version == 4
        assert result.readbacks[0].data_hash == origin_k25.canonical_hash(
            [first_document.model_dump(mode="json"), second_document.model_dump(mode="json")]
        )
        target = tmp_path / "artifacts" / "composite" / "v4"
        svg = target.joinpath("preview.svg").read_text(encoding="utf-8")
        assert "component-1" in svg and "component-2" in svg
        assert "原生组合图" in svg
        assert "font-family" in svg
        assert "data:image" not in svg
        assert "<image" not in svg
        parsed = ET.parse(target / "preview.svg").getroot()
        assert len(parsed.findall("{http://www.w3.org/2000/svg}svg")) == 2
        assert (target / "preview.png").stat().st_size > 1_000


class _Label:
    def __init__(self, text: str = "") -> None:
        self.name = ""
        self.text = text
        self.ints: dict[str, int] = {"show": 1}
        self.floats: dict[str, float] = {}

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = value

    def get_int(self, name: str) -> int:
        return self.ints.get(name, 0)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = value


class _Layer:
    def __init__(self) -> None:
        self.labels: dict[str, _Label] = {}

    def label(self, name: str):
        return next(
            (label for key, label in self.labels.items() if key == name or label.name == name),
            None,
        )

    def add_label(self, text: str):
        label = _Label(text)
        self.labels[f"pending-{len(self.labels)}"] = label
        return label


class _Graph:
    def __init__(self, name: str, layer_count: int = 1) -> None:
        self.name = name
        self.layers = [_Layer() for _index in range(layer_count)]

    def __iter__(self):
        return iter(self.layers)

    def activate(self) -> None:
        return None


class _Origin:
    def __init__(self) -> None:
        self.graphs: list[_Graph] = []
        self.saved: list[_Graph] = []
        self.commands: list[str] = []

    def new(self, *, asksave: bool) -> None:
        self.graphs = []

    def pages(self, kind: str):
        assert kind == "g"
        return tuple(self.graphs)

    def lt_exec(self, command: str) -> None:
        self.commands.append(command)
        if command.startswith("doc -a"):
            self.graphs.append(_Graph(f"Imported{len(self.graphs) + 1}"))
        elif command.startswith("merge_graph"):
            sources = [graph for graph in self.graphs if graph.name.startswith("K25C")]
            count = sum(len(tuple(item)) for item in sources)
            self.graphs.append(_Graph("Graph1", count))

    def lt_float(self, expression: str) -> float:
        if expression.startswith("__K25COUNT"):
            return 1.0
        if expression.startswith("__K25PID"):
            return 200.0
        raise AssertionError(f"unexpected LabTalk scalar read: {expression}")

    def new_graph(self, name: str, *, template: str, hidden: bool):
        graph = _Graph(name)
        self.graphs.append(graph)
        return graph

    def save(self, output: str) -> None:
        Path(output).write_bytes(b"fake-opju")
        self.saved = copy.deepcopy(self.graphs)

    def open(self, output: str, *, readonly: bool, asksave: bool) -> bool:
        self.graphs = copy.deepcopy(self.saved)
        return Path(output).is_file()


def _component(action: CreatePlot) -> EngineComponentInput:
    return EngineComponentInput(
        document=_child_document(action),
        actions=(action,),
        data=_view(action),
    )


def test_k25_origin_uses_native_append_and_official_merge_graph(
    tmp_path: Path,
) -> None:
    install = tmp_path / "install"
    install.mkdir()
    first, second = _child_action("first", HASH_A), _child_action("second", HASH_B)
    components = (_component(first), _component(second))
    document = PlotDocument(
        plot_id="plot:composite",
        plot_version=1,
        profile_id="K25",
        components=tuple(document_ref(item.document) for item in components),
        applied_action_ids=("action:create-composite",),
    )
    create = _create_composite(document.components)
    first_opju, second_opju = tmp_path / "first.opju", tmp_path / "second.opju"
    first_opju.write_bytes(b"first")
    second_opju.write_bytes(b"second")
    output = tmp_path / "result.opju"
    request = OriginWorkerRequest(
        install_dir=str(install),
        output_opju=str(output),
        document=document,
        actions=(create,),
        source={"components": components},
        component_opjus=(str(first_opju), str(second_opju)),
    )
    op = _Origin()
    trace_path = tmp_path / "execution-trace.jsonl"
    trace = OriginExecutionTrace(
        path=trace_path,
        profile_id="K25",
        plot_id=document.plot_id,
        plot_version=document.plot_version,
    )
    trace.reset()
    with trace.activate():
        readback = execute_k25_request(op, request, install, output)

    assert output.read_bytes() == b"fake-opju"
    assert readback.data_hash == request.source.source_hash()
    assert [item.semantic_id for item in readback.objects] == [
        "plot:composite",
        "panel:composite.component_1",
        "panel:composite.component_2",
    ]
    assert sum(command.startswith("doc -a") for command in op.commands) == 2
    merge = next(command for command in op.commands if command.startswith("merge_graph"))
    assert 'graphs:="K25C1"+char(10)$+"K25C2"' in merge
    assert "row:=1 col:=2" in merge
    assert "ogp:=" not in merge
    assert "mgroups" not in " ".join(op.commands).lower()
    assert _append_project_command(first_opju).startswith('doc -a "')
    assert "keep:=1" in _merge_command(("K25C1", "K25C2"), rows=1, columns=2)
    trace_steps = {
        item["step"]
        for item in map(
            __import__("json").loads,
            trace_path.read_text(encoding="utf-8").splitlines(),
        )
        if item["status"] == "completed"
    }
    assert {
        "origin_project_initialize",
        "component_project_append",
        "official_merge_graph_execute",
        "agent_actions_apply",
        "native_structure_readback",
        "opju_save",
        "opju_open",
        "reopened_native_structure_verify",
    } <= trace_steps


class _Worker:
    def __init__(self) -> None:
        self.request: OriginWorkerRequest | None = None

    def run(self, request: OriginWorkerRequest) -> OriginWorkerResponse:
        self.request = request
        Path(request.output_opju).write_bytes(b"composite")
        return OriginWorkerResponse(
            readback=EngineReadback(
                document=document_ref(request.document),
                backend="origin",
                objects=(),
                data_hash=request.source.source_hash(),
                style_hash="d" * 64,
            )
        )


def test_origin_backend_resolves_exact_child_version_artifacts(tmp_path: Path) -> None:
    first, second = _child_action("first", HASH_A), _child_action("second", HASH_B)
    components = (_component(first), _component(second))
    document = PlotDocument(
        plot_id="plot:composite",
        plot_version=1,
        profile_id="K25",
        components=tuple(document_ref(item.document) for item in components),
        applied_action_ids=("action:create-composite",),
    )
    create = _create_composite(document.components)
    root = tmp_path / "origin"
    for component in components:
        target = root / component.document.plot_id.removeprefix("plot:") / "v1"
        target.mkdir(parents=True)
        target.joinpath("plot.opju").write_bytes(component.document.plot_id.encode())
    worker = _Worker()
    backend = OriginBackend(root, tmp_path / "install", worker)
    change = backend.stage(
        document,
        (create,),
        EngineRenderSource(components=components),
    )
    assert worker.request is not None
    assert tuple(Path(path).name for path in worker.request.component_opjus) == (
        "plot.opju",
        "plot.opju",
    )
    assert tuple(Path(path).parent.parent.name for path in worker.request.component_opjus) == (
        "first",
        "second",
    )
    change.publish()
    assert (root / "composite" / "v1" / "plot.opju").read_bytes() == b"composite"


def test_origin_command_builders_reject_script_delimiters(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        _append_project_command(tmp_path / 'bad";delete.opju')
    with pytest.raises(ValueError, match="safe identifiers"):
        _merge_command(("Graph1;delete",), rows=1, columns=1)
