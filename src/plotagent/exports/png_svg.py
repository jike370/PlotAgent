"""Atomic formal PNG/SVG export and post-write structural validation."""

from __future__ import annotations

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import matplotlib
from PIL import Image, ImageChops

from plotagent.rendering.data import ResolvedPlot
from plotagent.rendering.matplotlib import MatplotlibRenderer

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SVG_NS = "http://www.w3.org/2000/svg"
_LENGTH = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*(mm)$")


@dataclass(frozen=True, slots=True)
class ArtifactValidation:
    format: str
    render_plan_hash: str
    width: float
    height: float
    element_counts: Mapping[str, int] = field(default_factory=dict)


def _expected_pixels(value_mm: float, dpi: int) -> int:
    return round(value_mm / 25.4 * dpi)


def validate_png(path: Path, resolved: ResolvedPlot) -> ArtifactValidation:
    """Decode PNG and verify signature, pixels, DPI metadata, hash, and content."""

    if path.read_bytes()[:8] != _PNG_SIGNATURE:
        raise ValueError("PNG_SIGNATURE_INVALID")
    plan = resolved.plan
    expected_size = (
        _expected_pixels(plan.canvas.width.value, plan.dpi),
        _expected_pixels(plan.canvas.height.value, plan.dpi),
    )
    with Image.open(path) as image:
        image.load()
        if image.size != expected_size:
            raise ValueError(
                f"PNG_DIMENSIONS_INVALID: expected {expected_size}, found {image.size}"
            )
        dpi = image.info.get("dpi")
        if not isinstance(dpi, tuple) or len(dpi) != 2:
            raise ValueError("PNG_DPI_METADATA_MISSING")
        if any(abs(float(value) - plan.dpi) > 0.5 for value in dpi):
            raise ValueError(f"PNG_DPI_METADATA_INVALID: {dpi}")
        if image.info.get("RenderPlanHash") != resolved.render_plan_hash:
            raise ValueError("RENDER_PLAN_HASH_MISMATCH")
        if image.mode not in {"RGB", "RGBA"}:
            raise ValueError(f"PNG_COLOR_MODE_INVALID: {image.mode}")
        rgb = image.convert("RGB")
        background = Image.new("RGB", rgb.size, plan.background.value[:7])
        if ImageChops.difference(rgb, background).getbbox() is None:
            raise ValueError("PNG_CONTENT_EMPTY")
    return ArtifactValidation(
        format="png",
        render_plan_hash=resolved.render_plan_hash,
        width=float(expected_size[0]),
        height=float(expected_size[1]),
    )


def _length_mm(value: str | None, name: str) -> float:
    if value is None:
        raise ValueError(f"SVG_{name.upper()}_MISSING")
    match = _LENGTH.fullmatch(value)
    if match is None:
        raise ValueError(f"SVG_{name.upper()}_UNIT_INVALID: {value}")
    return float(match.group(1))


def validate_svg(path: Path, resolved: ResolvedPlot) -> ArtifactValidation:
    """Safely parse SVG and verify physical geometry, vector structure, and hash."""

    content = path.read_text(encoding="utf-8")
    lowered = content.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("SVG_XML_DECLARATION_UNSAFE")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise ValueError("SVG_XML_INVALID") from error
    if root.tag != f"{{{_SVG_NS}}}svg":
        raise ValueError("SVG_ROOT_INVALID")
    width_mm = _length_mm(root.get("width"), "width")
    height_mm = _length_mm(root.get("height"), "height")
    plan = resolved.plan
    if abs(width_mm - plan.canvas.width.value) > 0.2:
        raise ValueError("SVG_WIDTH_INVALID")
    if abs(height_mm - plan.canvas.height.value) > 0.2:
        raise ValueError("SVG_HEIGHT_INVALID")
    view_box = root.get("viewBox")
    if view_box is None:
        raise ValueError("SVG_VIEWBOX_MISSING")
    parts = tuple(float(value) for value in view_box.split())
    expected_points = (
        plan.canvas.width.value / 25.4 * 72.0,
        plan.canvas.height.value / 25.4 * 72.0,
    )
    if len(parts) != 4 or parts[:2] != (0.0, 0.0):
        raise ValueError("SVG_VIEWBOX_INVALID")
    if abs(parts[2] - expected_points[0]) > 0.02 or abs(parts[3] - expected_points[1]) > 0.02:
        raise ValueError("SVG_VIEWBOX_INVALID")
    if resolved.render_plan_hash not in content:
        raise ValueError("RENDER_PLAN_HASH_MISMATCH")

    counts: dict[str, int] = {}
    forbidden = {"script", "foreignObject", "image", "audio", "video"}
    for element in root.iter():
        local_name = element.tag.rsplit("}", 1)[-1]
        counts[local_name] = counts.get(local_name, 0) + 1
        if local_name in forbidden:
            raise ValueError(f"SVG_FORBIDDEN_ELEMENT: {local_name}")
        for attribute, value in element.attrib.items():
            local_attribute = attribute.rsplit("}", 1)[-1].lower()
            if local_attribute.startswith("on"):
                raise ValueError(f"SVG_EVENT_HANDLER_FORBIDDEN: {local_attribute}")
            if local_attribute == "href" and not value.startswith("#"):
                raise ValueError("SVG_EXTERNAL_REFERENCE_FORBIDDEN")
            if "url(" in value.lower() and not re.search(r"url\(\s*#", value, flags=re.I):
                raise ValueError("SVG_EXTERNAL_REFERENCE_FORBIDDEN")
    if counts.get("path", 0) == 0 or counts.get("g", 0) == 0:
        raise ValueError("SVG_VECTOR_CONTENT_MISSING")
    text_count = counts.get("text", 0)
    if plan.svg_text_mode == "text_to_path" and text_count != 0:
        raise ValueError("SVG_TEXT_MODE_INVALID")
    if plan.svg_text_mode == "editable_text" and text_count == 0:
        raise ValueError("SVG_TEXT_MODE_INVALID")
    return ArtifactValidation(
        format="svg",
        render_plan_hash=resolved.render_plan_hash,
        width=width_mm,
        height=height_mm,
        element_counts=counts,
    )


def _rewrite_svg_root(path: Path, resolved: ResolvedPlot) -> None:
    content = path.read_text(encoding="utf-8")
    content = re.sub(r"<!DOCTYPE[\s\S]*?>", "", content, count=1, flags=re.IGNORECASE)
    match = re.search(r"<svg\b[^>]*>", content)
    if match is None:
        raise ValueError("SVG_ROOT_INVALID")
    tag = match.group(0)
    tag = re.sub(r'\s(?:width|height|viewBox)="[^"]*"', "", tag)
    width_mm = resolved.plan.canvas.width.value
    height_mm = resolved.plan.canvas.height.value
    width_pt = width_mm / 25.4 * 72.0
    height_pt = height_mm / 25.4 * 72.0
    tag = tag[:-1] + (
        f' width="{width_mm:.6f}mm" height="{height_mm:.6f}mm"'
        f' viewBox="0 0 {width_pt:.6f} {height_pt:.6f}">'
    )
    metadata = (
        f'<metadata id="plotagent-metadata">render-plan-hash:{resolved.render_plan_hash}</metadata>'
    )
    content = content[: match.start()] + tag + metadata + content[match.end() :]
    path.write_text(content, encoding="utf-8", newline="\n")


def _atomic_export(path: Path, resolved: ResolvedPlot, output_format: str) -> ArtifactValidation:
    if resolved.plan.quality_tier != "formal":
        raise ValueError("RENDER_FORMAL_PLAN_REQUIRED")
    if output_format not in {"png", "svg"}:
        raise ValueError("RENDER_FORMAT_UNSUPPORTED")
    if path.suffix.lower() != f".{output_format}":
        raise ValueError("RENDER_EXTENSION_MISMATCH")
    if not path.parent.is_dir():
        raise ValueError("RENDER_TARGET_DIRECTORY_MISSING")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=f".{output_format}.tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    figure = None
    try:
        rc = {
            "font.family": [resolved.plan.fonts[0].family],
            "svg.fonttype": "path" if resolved.plan.svg_text_mode == "text_to_path" else "none",
            "text.usetex": False,
            "text.parse_math": False,
            "savefig.transparent": False,
        }
        with matplotlib.rc_context(cast(dict[Any, Any], rc)):
            figure = MatplotlibRenderer().build_figure(resolved)
            metadata = (
                {
                    "Software": "PlotAgent Matplotlib Agg",
                    "RenderPlanHash": resolved.render_plan_hash,
                }
                if output_format == "png"
                else {
                    "Title": "PlotAgent scientific figure",
                    "Description": f"render-plan-hash:{resolved.render_plan_hash}",
                }
            )
            figure.savefig(
                temporary,
                format=output_format,
                dpi=resolved.plan.dpi,
                facecolor=resolved.plan.background.value,
                edgecolor="none",
                metadata=metadata,
            )
        if output_format == "svg":
            _rewrite_svg_root(temporary, resolved)
            validation = validate_svg(temporary, resolved)
        else:
            validation = validate_png(temporary, resolved)
        os.replace(temporary, path)
        return validation
    finally:
        if figure is not None:
            figure.clear()
        temporary.unlink(missing_ok=True)


def export_png(path: Path, resolved: ResolvedPlot) -> ArtifactValidation:
    return _atomic_export(path, resolved, "png")


def export_svg(path: Path, resolved: ResolvedPlot) -> ArtifactValidation:
    return _atomic_export(path, resolved, "svg")
