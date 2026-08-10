"""Native K25 composition of already rendered Agent Native plot documents."""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, replace
from math import ceil, sqrt
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")

import matplotlib.image as mpimg
import matplotlib.pyplot as plt

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

if TYPE_CHECKING:
    from plotagent.engine.backends.matplotlib.backend import MatplotlibComponentArtifact

_SVG = "http://www.w3.org/2000/svg"
_XLINK = "http://www.w3.org/1999/xlink"
_URL_REFERENCE = re.compile(r"url\(#([^)]+)\)")


@dataclass(frozen=True, slots=True)
class _CompositeState:
    title: str = ""
    columns: int = 0
    annotations: tuple[AddAnnotation, ...] = ()


class K25CompositeRenderer:
    """Compose child artifacts while keeping SVG children as vector objects."""

    profile_id = "K25"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        components: tuple[MatplotlibComponentArtifact, ...],
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        if not 2 <= len(components) <= 4:
            raise ValueError("K25 requires two to four component plots")
        state = self._state(document, actions, len(components))
        columns = state.columns or ceil(sqrt(len(components)))
        rows = ceil(len(components) / columns)
        self._render_png(components, state, columns, rows, png_path)
        self._render_svg(components, state, columns, rows, svg_path)

        token = document.plot_id.removeprefix("plot:")
        objects = [
            EngineObjectRef(
                semantic_id=document.plot_id,
                backend="matplotlib",
                object_kind="figure",
                native_ref="figure:0",
            )
        ]
        objects.extend(
            EngineObjectRef(
                semantic_id=f"panel:{token}.component_{index}",
                backend="matplotlib",
                object_kind="component_panel",
                native_ref=f"figure:0.panel:{index}",
            )
            for index in range(1, len(components) + 1)
        )
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=tuple(objects),
            data_hash=canonical_hash(
                [item.component.document.model_dump(mode="json") for item in components]
            ),
            style_hash=canonical_hash(asdict(state)),
        )

    @staticmethod
    def _render_png(
        components: tuple[MatplotlibComponentArtifact, ...],
        state: _CompositeState,
        columns: int,
        rows: int,
        destination: Path,
    ) -> None:
        figure, axes = plt.subplots(
            rows,
            columns,
            figsize=(6.4 * columns, 4.8 * rows),
            squeeze=False,
            constrained_layout=True,
        )
        for index, axis in enumerate(axes.flat):
            axis.set_axis_off()
            if index < len(components):
                axis.imshow(mpimg.imread(components[index].png_path))
        if state.title:
            figure.suptitle(state.title)
        for annotation in state.annotations:
            if annotation.coordinate_system == "page":
                figure.text(annotation.x, annotation.y, annotation.text)
                continue
            panel_index = K25CompositeRenderer._panel_index(annotation, len(components))
            axes.flat[panel_index].text(
                annotation.x,
                annotation.y,
                annotation.text,
                transform=axes.flat[panel_index].transAxes,
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(destination, dpi=160)
        plt.close(figure)

    @staticmethod
    def _render_svg(
        components: tuple[MatplotlibComponentArtifact, ...],
        state: _CompositeState,
        columns: int,
        rows: int,
        destination: Path,
    ) -> None:
        ET.register_namespace("", _SVG)
        ET.register_namespace("xlink", _XLINK)
        panel_width, panel_height = 640.0, 480.0
        top = 48.0 if state.title else 16.0
        width = panel_width * columns
        height = panel_height * rows + top
        root = ET.Element(
            f"{{{_SVG}}}svg",
            {
                "width": str(width),
                "height": str(height),
                "viewBox": f"0 0 {width} {height}",
                "version": "1.1",
            },
        )
        if state.title:
            title = ET.SubElement(
                root,
                f"{{{_SVG}}}text",
                {
                    "x": str(width / 2.0),
                    "y": "30",
                    "text-anchor": "middle",
                    "font-size": "22",
                },
            )
            title.text = state.title

        panels: list[ET.Element] = []
        for index, component in enumerate(components):
            child = ET.parse(component.svg_path).getroot()
            K25CompositeRenderer._namespace_ids(child, f"component{index + 1}")
            row, column = divmod(index, columns)
            panel = ET.SubElement(
                root,
                f"{{{_SVG}}}svg",
                {
                    "id": f"component-{index + 1}",
                    "x": str(column * panel_width),
                    "y": str(top + row * panel_height),
                    "width": str(panel_width),
                    "height": str(panel_height),
                    "viewBox": child.attrib.get(
                        "viewBox",
                        f"0 0 {child.attrib.get('width', panel_width)} "
                        f"{child.attrib.get('height', panel_height)}",
                    ),
                    "preserveAspectRatio": "xMidYMid meet",
                },
            )
            panels.append(panel)
            for item in child:
                panel.append(copy.deepcopy(item))

        for annotation in state.annotations:
            if annotation.coordinate_system == "page":
                parent, x, y = root, annotation.x * width, (1.0 - annotation.y) * height
            else:
                panel_index = K25CompositeRenderer._panel_index(annotation, len(components))
                parent = panels[panel_index]
                x = annotation.x * panel_width
                y = (1.0 - annotation.y) * panel_height
            label = ET.SubElement(
                parent,
                f"{{{_SVG}}}text",
                {"x": str(x), "y": str(y), "font-size": "16"},
            )
            label.text = annotation.text
        destination.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _namespace_ids(root: ET.Element, prefix: str) -> None:
        identifiers = {
            value: f"{prefix}-{value}"
            for element in root.iter()
            if (value := element.attrib.get("id"))
        }
        for element in root.iter():
            current = element.attrib.get("id")
            if current in identifiers:
                element.set("id", identifiers[current])
            for name, value in tuple(element.attrib.items()):
                if value.startswith("#") and value[1:] in identifiers:
                    element.set(name, "#" + identifiers[value[1:]])
                    continue
                element.set(
                    name,
                    _URL_REFERENCE.sub(
                        lambda match: f"url(#{identifiers.get(match.group(1), match.group(1))})",
                        value,
                    ),
                )

    @staticmethod
    def _panel_index(annotation: AddAnnotation, count: int) -> int:
        if annotation.coordinate_system != "axes":
            raise ValueError("K25 annotations support only page or panel axes coordinates")
        prefix = "panel:"
        marker = ".component_"
        if not annotation.target.startswith(prefix) or marker not in annotation.target:
            raise ValueError("a K25 axes annotation must target one component panel")
        try:
            index = int(annotation.target.rsplit(marker, 1)[1]) - 1
        except ValueError as error:
            raise ValueError("a K25 panel target has an invalid ordinal") from error
        if not 0 <= index < count:
            raise ValueError("a K25 panel target is outside the component range")
        return index

    @staticmethod
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
                    K25CompositeRenderer._panel_index(action, component_count)
                state = replace(state, annotations=state.annotations + (action,))
            else:
                raise ValueError(f"K25 Matplotlib renderer cannot apply {action.operation}")
        return state
