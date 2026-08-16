"""Artifact backend for independent Matplotlib profile renderers."""

from __future__ import annotations

import shutil
import uuid
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol, cast

import matplotlib

from plotagent.engine.contracts import EngineDataView, PlotDocument, PlotEngineAction
from plotagent.engine.ports import (
    EngineArtifact,
    EngineReadback,
    EngineRenderSource,
    PlotBackendChange,
)
from plotagent.engine.visual_t1 import split_visual_actions, visual_style_hash

from .font import resolve_font_family
from .visual_t1 import apply_visuals_before_save


def _visible_text(
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
    data: EngineDataView,
) -> tuple[str, ...]:
    """Collect renderer-visible text before selecting one shared font.

    Independent profile renderers draw titles, axis labels, annotations, field
    names, units and categorical values.  Resolving the font once at the backend
    boundary keeps all profiles on the same CJK-safe contract instead of relying
    on each renderer to remember its own rc_context.
    """

    result: list[str] = [document.profile_id]

    def collect(value: object) -> None:
        if isinstance(value, str):
            result.append(value)
        elif isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                collect(nested)

    for action in actions:
        collect(action.model_dump(mode="json"))
    for column in data.columns:
        result.append(column.field.name)
        if column.field.unit_label is not None:
            result.append(column.field.unit_label)
        collect(column.values)
    return tuple(result)


class MatplotlibProfileRenderer(Protocol):
    profile_id: str

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback: ...


class _Change:
    def __init__(self, staging: Path, final: Path, readback: EngineReadback) -> None:
        self._staging = staging
        self._final = final
        self._readback = readback
        self._published = False

    @property
    def readback(self) -> EngineReadback:
        return self._readback

    def publish(self) -> None:
        if self._final.exists():
            raise FileExistsError(f"Matplotlib version artifact already exists: {self._final}")
        self._final.parent.mkdir(parents=True, exist_ok=True)
        self._staging.replace(self._final)
        self._published = True

    def revert(self) -> None:
        if self._published:
            shutil.rmtree(self._final, ignore_errors=True)
            self._published = False

    def finalize(self) -> None:
        return None

    def discard(self) -> None:
        shutil.rmtree(self._staging, ignore_errors=True)


class MatplotlibBackend:
    backend_id: Literal["matplotlib"] = "matplotlib"

    def __init__(
        self,
        root: Path,
        renderers: tuple[MatplotlibProfileRenderer, ...],
    ) -> None:
        profile_ids = tuple(renderer.profile_id for renderer in renderers)
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("Matplotlib profile renderer ids must be unique")
        self._root = root
        self._renderers = {renderer.profile_id: renderer for renderer in renderers}

    def stage(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        source: EngineRenderSource,
    ) -> PlotBackendChange:
        staging = self._root / ".staging" / uuid.uuid4().hex
        staging.mkdir(parents=True)
        try:
            renderer = self._renderers[document.profile_id]
        except KeyError as error:
            raise ValueError(f"no Matplotlib renderer for {document.profile_id}") from error
        font_family = resolve_font_family(_visible_text(document, actions, source.data))
        structural_actions, visual_actions = split_visual_actions(actions)
        with (
            matplotlib.rc_context(
                {
                    "font.family": font_family,
                    "axes.unicode_minus": False,
                }
            ),
            apply_visuals_before_save(document, visual_actions),
        ):
            readback = renderer.render(
                document,
                structural_actions,
                source.data,
                staging / "preview.png",
                staging / "preview.svg",
            )
        readback = readback.model_copy(
            update={"style_hash": visual_style_hash(readback, visual_actions)}
        )
        (staging / "readback.json").write_text(readback.model_dump_json(indent=2), encoding="utf-8")
        final = self._version_dir(document)
        return _Change(staging, final, readback)

    def readback(self, document: PlotDocument) -> EngineReadback:
        return EngineReadback.model_validate_json(
            (self._version_dir(document) / "readback.json").read_text(encoding="utf-8")
        )

    def export(self, document: PlotDocument, destination: Path, format: str) -> EngineArtifact:
        if format not in {"png", "svg"}:
            raise ValueError("Matplotlib exports only PNG or SVG")
        export_format = cast(Literal["png", "svg"], format)
        source = self._version_dir(document) / f"preview.{export_format}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        payload = destination.read_bytes()
        return EngineArtifact(
            backend="matplotlib",
            format=export_format,
            artifact_hash=sha256(payload).hexdigest(),
            artifact_size=len(payload),
        )

    def _version_dir(self, document: PlotDocument) -> Path:
        token = document.plot_id.removeprefix("plot:")
        return self._root / token / f"v{document.plot_version}"
