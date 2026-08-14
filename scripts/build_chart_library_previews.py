"""Generate production chart-library previews from the current renderers.

The chart library must show what PlotAgent renders first, not a hand-drawn
family icon or a remote Origin help screenshot. This command uses the
representative engine fixtures and every production Matplotlib renderer to
create one default-state PNG per public profile. Origin qualification remains
tracked separately by the native renderer audit.
"""

# ruff: noqa: E402,I001,PLC2701 -- fixture imports intentionally mirror tests.

from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from matplotlib import rcParams

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine import CreatePlot, EngineDataView, PlotDocument, PlotEngineAction
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
    K18AreaRenderer,
    K19TimeSeriesRenderer,
    K20HeatmapRenderer,
    K21CorrelationMatrixRenderer,
    K22ContourRenderer,
    K24FacetRenderer,
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
from plotagent.engine.backends.matplotlib.backend import MatplotlibProfileRenderer
from plotagent.engine.profiles import ENGINE_PROFILES



def _fixture_module(name: str) -> Any:
    """Load frozen fixture modules without making them runtime dependencies."""

    return importlib.import_module(f"tests.engine.{name}")


column_cases = _fixture_module("test_column_family_profiles")
k01_cases = _fixture_module("test_k01_matplotlib_backend")
k03_cases = _fixture_module("test_k03_dynamic_profile")
k04_cases = _fixture_module("test_k04_bubble_profile")
k08_cases = _fixture_module("test_k08_matplotlib_backend")
calculated_cases = _fixture_module("test_k15_calculated_distribution")
matrix_cases = _fixture_module("test_k19_k21_k22_profiles")
k20_cases = _fixture_module("test_k20_origin_backend")
special_cases = _fixture_module("test_remaining_t1_special_profiles")
t1_cases = _fixture_module("test_t1_family_matplotlib_backends")
t2_cases = _fixture_module("test_t2_non_composite_profiles")
wide_cases = _fixture_module("test_x03_x39_x40_wide_series")
x_cases = _fixture_module("test_x05_x09_x13_profiles")
x23_cases = _fixture_module("test_x23_matplotlib_backend")

OUTPUT = REPOSITORY / "src" / "renderer" / "src" / "assets" / "chart-previews"
EXPECTED_SIZE = (1024, 768)
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
XLINK_HREF = f"{{{XLINK_NAMESPACE}}}href"
ET.register_namespace("", SVG_NAMESPACE)
ET.register_namespace("xlink", XLINK_NAMESPACE)


@dataclass(frozen=True, slots=True)
class PreviewCase:
    profile_id: str
    document: PlotDocument
    actions: tuple[PlotEngineAction, ...]
    view: EngineDataView


def _document_for(create: CreatePlot) -> PlotDocument:
    return PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id=create.profile_id,
        data=create.data,
        bindings=create.bindings,
        applied_action_ids=(create.action_id,),
    )


def _provider_case(
    create: CreatePlot,
    provider: Any,
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    if create.data is None:
        raise ValueError("chart preview fixtures must be data-backed")
    field_ids = tuple(binding.field_id for binding in create.bindings)
    view = provider.materialize(create.data, field_ids)
    return _document_for(create), (create,), view


def _cases() -> tuple[PreviewCase, ...]:
    factories: dict[
        str,
        Callable[[], tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]],
    ] = {
        "K01": lambda: _provider_case(k01_cases._create(), k01_cases.Provider()),
        "K02": lambda: t1_cases._case(
            "K02",
            ("x", "y"),
            (
                t1_cases._column("field:x", "Time", (0.0, 1.0, 2.0, 3.0)),
                t1_cases._column("field:y", "Signal", (1.0, 2.2, 1.8, 3.4)),
            ),
        ),
        "K03": lambda: k03_cases._case(("Control", "Low", "Control", "High", "Low")),
        "K04": lambda: k04_cases._case(scales=True, edits=True),
        "K06": lambda: t1_cases._case(
            "K06",
            ("x", "center", "x_lower", "x_upper", "lower", "upper"),
            (
                t1_cases._column("field:x", "Time", (1.0, 2.0, 3.0, 4.0)),
                t1_cases._column("field:center", "Estimate", (2.0, 3.0, 4.0, 3.5)),
                t1_cases._column("field:x-lower", "X lower", (0.75, 1.8, 2.65, 3.7)),
                t1_cases._column("field:x-upper", "X upper", (1.15, 2.35, 3.2, 4.4)),
                t1_cases._column("field:lower", "Y lower", (1.55, 2.45, 3.65, 2.9)),
                t1_cases._column("field:upper", "Y upper", (2.4, 3.65, 4.25, 4.2)),
            ),
        ),
        "K07": lambda: t1_cases._case(
            "K07",
            ("x", "center", "lower", "upper"),
            (
                t1_cases._column("field:x", "Dose", (0.0, 1.0, 2.0, 3.0)),
                t1_cases._column("field:center", "Response", (2.0, 3.0, 4.0, 4.5)),
                t1_cases._column("field:lower", "Lower", (1.5, 2.5, 3.0, 3.8)),
                t1_cases._column("field:upper", "Upper", (2.5, 3.7, 5.0, 5.2)),
            ),
        ),
        "K08": lambda: _provider_case(k08_cases._create(), k08_cases.Provider()),
        "K09": lambda: column_cases._case("K09", 3),
        "K10": lambda: column_cases._case("K10", 3),
        "K11": lambda: column_cases._case("K11", 3),
        "K12": lambda: column_cases._distribution_case("K12", 3),
        "K13": lambda: column_cases._distribution_case("K13", 3),
        "K14": lambda: column_cases._distribution_case("K14", 3),
        "K15": lambda: calculated_cases._case("K15"),
        "K18": matrix_cases._k18_case,
        "K19": matrix_cases._k19_case,
        "K20": k20_cases._case,
        "K21": matrix_cases._k21_case,
        "K22": matrix_cases._k22_case,
        "K24": t2_cases._k24_case,
        "S34": t2_cases._s34_case,
        "S61": t2_cases._s61_case,
        "X02": lambda: t1_cases._case(
            "X02",
            ("x", "y"),
            (
                t1_cases._column("field:x", "Position", (0.0, 1.0, 2.0, 3.0)),
                t1_cases._column("field:y", "Signal", (-1.0, 3.0, 1.5, -0.5)),
            ),
        ),
        "X03": lambda: wide_cases._case("X03", series_count=4, row_count=5),
        "X05": x_cases._x05_case,
        "X09": x_cases._x09_case,
        "X13": x_cases._x13_case,
        "X23": lambda: _provider_case(x23_cases._create(), x23_cases.Provider()),
        "X24": special_cases._x24_case,
        "X35": lambda: special_cases._dual_case("X35"),
        "X36": lambda: special_cases._dual_case("X36"),
        "X38": special_cases._x38_case,
        "X39": lambda: wide_cases._case("X39", series_count=4, row_count=5),
        "X40": lambda: wide_cases._case("X40", series_count=2, row_count=6),
    }
    expected = tuple(profile.profile_id for profile in ENGINE_PROFILES)
    if set(factories) != set(expected):
        raise RuntimeError(
            f"chart preview fixture inventory differs: {sorted(set(expected) ^ set(factories))}"
        )
    return tuple(PreviewCase(profile_id, *factories[profile_id]()) for profile_id in expected)


RENDERERS: dict[str, MatplotlibProfileRenderer] = {
    renderer.profile_id: renderer
    for renderer in (
        K01LineRenderer(), K02LineSymbolRenderer(), K03ScatterRenderer(), K04BubbleRenderer(),
        K06PointErrorRenderer(), K07ErrorBandRenderer(), K08ColumnRenderer(),
        K09GroupedColumnRenderer(), K10StackedColumnRenderer(), K11PercentStackRenderer(),
        K12StripRenderer(), K13BoxRenderer(), K14ViolinRenderer(), K15HistogramRenderer(),
        K18AreaRenderer(), K19TimeSeriesRenderer(), K20HeatmapRenderer(),
        K21CorrelationMatrixRenderer(), K22ContourRenderer(), K24FacetRenderer(),
        S34NyquistRenderer(), S61ConfusionRenderer(), X02DropLineRenderer(),
        X03LollipopRenderer(), X05BeeswarmRenderer(), X09FloatingIntervalRenderer(),
        X13PopulationPyramidRenderer(), X23DualYRenderer(), X24ParetoRenderer(),
        X35DualYColumnRenderer(), X36DualYColumnLineRenderer(), X38OffsetStackRenderer(),
        X39LineSeriesRenderer(), X40BeforeAfterRenderer(),
    )
}


def _default_state(case: PreviewCase) -> tuple[PlotDocument, tuple[PlotEngineAction, ...]]:
    create = case.actions[0]
    if not isinstance(create, CreatePlot):
        raise TypeError(f"{case.profile_id} preview history must begin with create_plot")
    return _document_for(create), (create,)


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _fixture_sha(view: EngineDataView) -> str:
    payload = json.dumps(
        view.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _element_id(element: ET.Element) -> str:
    return element.attrib.get("id", "")


def _clip_bounds(root: ET.Element, axes: ET.Element) -> tuple[float, float, float, float] | None:
    clip_ids = {
        clip.removeprefix("url(#").removesuffix(")")
        for element in axes.iter()
        if (clip := element.attrib.get("clip-path", "")).startswith("url(#")
    }
    for clip_id in clip_ids:
        clip_path = next(
            (element for element in root.iter() if _element_id(element) == clip_id),
            None,
        )
        if clip_path is None:
            continue
        rect = next(
            (element for element in clip_path if element.tag.endswith("rect")),
            None,
        )
        if rect is None:
            continue
        return (
            float(rect.attrib["x"]),
            float(rect.attrib["y"]),
            float(rect.attrib["width"]),
            float(rect.attrib["height"]),
        )
    return None


def _expanded_view_box(
    bounds: tuple[float, float, float, float],
    target_aspect: float,
) -> tuple[float, float, float, float]:
    x, y, width, height = bounds
    padding = max(width, height) * 0.035
    x -= padding
    y -= padding
    width += padding * 2
    height += padding * 2
    current_aspect = width / height
    if current_aspect < target_aspect:
        expanded_width = height * target_aspect
        x -= (expanded_width - width) / 2
        width = expanded_width
    else:
        expanded_height = width / target_aspect
        y -= (expanded_height - height) / 2
        height = expanded_height
    return x, y, width, height


def _scale_marker_definition(path: ET.Element, factor: float) -> None:
    number = re.compile(r"(?<![A-Za-z])[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")

    def scaled(match: re.Match[str]) -> str:
        return f"{float(match.group()) * factor:.6f}".rstrip("0").rstrip(".")

    path.attrib["d"] = number.sub(scaled, path.attrib["d"])


def _apply_preview_emphasis(profile_id: str, root: ET.Element) -> str:
    if profile_id in {"K02", "K03"}:
        marker_groups = [
            element
            for element in root.iter()
            if _element_id(element).startswith(
                ("line2d_", "PathCollection_")
            )
        ]
        marker_uses = [
            element
            for group in marker_groups
            for element in group.iter()
            if element.tag.endswith("use")
        ]
        marker_ids = {
            href.removeprefix("#")
            for marker in marker_uses
            if (href := marker.attrib.get(XLINK_HREF, "")).startswith("#")
        }
        for path in root.iter():
            if _element_id(path) in marker_ids and "d" in path.attrib:
                _scale_marker_definition(path, 1.8)
                path.attrib["style"] = "fill: #d95555; stroke: #d95555"
        for marker in marker_uses:
            marker.attrib["style"] = "fill: #d95555; stroke: #d95555"
        return "markers enlarged 1.8x and unified to the line-and-point red"

    if profile_id == "K04":
        bubble_group = next(
            (
                element
                for element in root.iter()
                if _element_id(element) == "PathCollection_1"
            ),
            None,
        )
        if bubble_group is None:
            raise RuntimeError("K04 preview has no bubble collection")
        bubbles = [element for element in bubble_group if element.tag.endswith("path")]
        scales = (1.35, 1.65, 1.95, 2.25)
        if len(bubbles) != len(scales):
            raise RuntimeError(f"K04 preview expected 4 bubbles, got {len(bubbles)}")
        coordinate = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)")
        for bubble, scale in zip(bubbles, scales, strict=True):
            values = [float(value) for value in coordinate.findall(bubble.attrib["d"])]
            x_values = values[0::2]
            y_values = values[1::2]
            center_x = (min(x_values) + max(x_values)) / 2
            center_y = (min(y_values) + max(y_values)) / 2
            bubble.attrib["transform"] = (
                f"translate({center_x:.6f} {center_y:.6f}) scale({scale}) "
                f"translate({-center_x:.6f} {-center_y:.6f})"
            )
        return "bubble radii progressively enlarged from 1.35x to 2.25x"

    return "none"


def _normalize_preview_palette(root: ET.Element) -> None:
    color_map = {
        "#1f77b4": "#1676d2",
        "#2875d8": "#1676d2",
        "#2a6fdb": "#1676d2",
        "#d97800": "#62a6e3",
        "#d97706": "#62a6e3",
        "#ff7f0e": "#62a6e3",
        "#c53d4d": "#62a6e3",
        "#d84a4a": "#62a6e3",
        "#d94b4b": "#62a6e3",
        "#f04444": "#62a6e3",
        "#299764": "#a6ccee",
        "#2a9d6f": "#a6ccee",
        "#2ca02c": "#a6ccee",
    }
    for element in root.iter():
        for attribute, value in tuple(element.attrib.items()):
            normalized = value
            for source, destination in color_map.items():
                normalized = re.sub(
                    re.escape(source),
                    destination,
                    normalized,
                    flags=re.IGNORECASE,
                )
            element.attrib[attribute] = normalized


def _replace_style_paint(style: str, property_name: str, color: str) -> str:
    pattern = re.compile(rf"({property_name}:\s*)([^;]+)", re.IGNORECASE)

    def replaced(match: re.Match[str]) -> str:
        if match.group(2).strip().lower() == "none":
            return match.group(0)
        return f"{match.group(1)}{color}"

    return pattern.sub(replaced, style)


def _color_artist(artist: ET.Element, color: str) -> set[str]:
    referenced_ids: set[str] = set()
    for element in artist.iter():
        href = element.attrib.get(XLINK_HREF, "")
        if href.startswith("#"):
            referenced_ids.add(href.removeprefix("#"))
        style = element.attrib.get("style")
        if style is not None:
            style = _replace_style_paint(style, "stroke", color)
            style = _replace_style_paint(style, "fill", color)
            element.attrib["style"] = style
        for attribute in ("stroke", "fill"):
            value = element.attrib.get(attribute)
            if value is not None and value.lower() != "none":
                element.attrib[attribute] = color
    return referenced_ids


def _apply_preview_color_semantics(profile_id: str, root: ET.Element) -> None:
    continuous_color_profiles = {"K04", "K20", "K21", "K22", "S61"}
    if profile_id not in continuous_color_profiles:
        referenced_ids: set[str] = set()
        for artist in root.iter():
            if _element_id(artist).startswith(
                ("line2d_", "LineCollection_", "PathCollection_")
            ):
                referenced_ids.update(_color_artist(artist, "#d95555"))
        for element in root.iter():
            if _element_id(element) in referenced_ids:
                _color_artist(element, "#d95555")

    if profile_id == "K07":
        for artist in root.iter():
            if "PolyCollection_" in _element_id(artist):
                _color_artist(artist, "#d95555")


def _normalize_preview_line_weights(root: ET.Element) -> None:
    artist_prefixes = ("line2d_", "LineCollection_")
    width_pattern = re.compile(r"stroke-width:\s*([0-9.]+)")
    for artist in root.iter():
        if not _element_id(artist).startswith(artist_prefixes):
            continue
        for element in artist.iter():
            style = element.attrib.get("style")
            if style is None:
                continue

            def widened(match: re.Match[str]) -> str:
                return f"stroke-width: {max(float(match.group(1)), 2.2):g}"

            element.attrib["style"] = width_pattern.sub(widened, style)


def _simplify_svg(source: Path, destination: Path, profile_id: str) -> str:
    """Reduce a full chart to its recognisable geometry for a library card."""

    tree = ET.parse(source)
    root = tree.getroot()
    for child in list(root):
        if child.tag.endswith("metadata"):
            root.remove(child)
    parent_by_child = {child: parent for parent in root.iter() for child in parent}
    axes = [element for element in root.iter() if _element_id(element).startswith("axes_")]
    axes_with_bounds = [
        (element, bounds)
        for element in axes
        if (bounds := _clip_bounds(root, element)) is not None
    ]
    if not axes_with_bounds:
        raise RuntimeError(f"no Matplotlib axes clip found in {source}")

    max_area = max(bounds[2] * bounds[3] for _, bounds in axes_with_bounds)
    selected = [
        (element, bounds)
        for element, bounds in axes_with_bounds
        if bounds[2] * bounds[3] >= max_area * 0.25
    ]
    selected_axes = {element for element, _ in selected}

    for element in axes:
        if element not in selected_axes and (parent := parent_by_child.get(element)) is not None:
            parent.remove(element)

    removable_prefixes = ("matplotlib.axis_", "legend_", "text_")
    parent_by_child = {child: parent for parent in root.iter() for child in parent}
    for element in list(root.iter()):
        if _element_id(element).startswith(removable_prefixes) and (
            parent := parent_by_child.get(element)
        ) is not None:
            parent.remove(element)

    for axes_element in selected_axes:
        patches = [
            child
            for child in list(axes_element)
            if _element_id(child).startswith("patch_")
        ]
        if patches:
            axes_element.remove(patches[0])
        for patch in patches[1:]:
            styles = " ".join(
                child.attrib.get("style", "") for child in patch.iter()
            ).lower()
            if "fill: none" in styles and "stroke:" in styles:
                axes_element.remove(patch)

    left = min(bounds[0] for _, bounds in selected)
    top = min(bounds[1] for _, bounds in selected)
    right = max(bounds[0] + bounds[2] for _, bounds in selected)
    bottom = max(bounds[1] + bounds[3] for _, bounds in selected)
    view_box = _expanded_view_box(
        (left, top, right - left, bottom - top),
        EXPECTED_SIZE[0] / EXPECTED_SIZE[1],
    )
    root.attrib.update(
        {
            "width": str(EXPECTED_SIZE[0]),
            "height": str(EXPECTED_SIZE[1]),
            "viewBox": " ".join(f"{value:.4f}" for value in view_box),
            "preserveAspectRatio": "xMidYMid meet",
        }
    )
    _normalize_preview_palette(root)
    _apply_preview_color_semantics(profile_id, root)
    _normalize_preview_line_weights(root)
    emphasis = _apply_preview_emphasis(profile_id, root)
    tree.write(destination, encoding="utf-8", xml_declaration=True)
    return emphasis


def _write_audit_page(entries: list[dict[str, object]]) -> Path:
    catalog_source = (
        REPOSITORY / "src" / "renderer" / "src" / "data" / "chartCatalog.ts"
    ).read_text(encoding="utf-8")
    chinese_names = dict(
        re.findall(r"^\s*(\w+): \{ name: '([^']+)'", catalog_source, re.MULTILINE)
    )
    audit_directory = REPOSITORY / "build" / "visual-audit" / "chart-library-previews"
    audit_directory.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(
        (
            '<article><img src="../../../src/renderer/src/assets/chart-previews/'
            f'{entry["profile_id"]}.svg" alt=""><footer><strong>{entry["profile_id"]}</strong>'
            f'<span>{chinese_names.get(str(entry["profile_id"]), "")}</span></footer></article>'
        )
        for entry in entries
    )
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>图形库轻量预览审计</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 32px; background: #f4f6f8; color: #172033;
      font: 14px/1.45 system-ui, sans-serif;
    }}
    header {{
      display: flex; align-items: end; justify-content: space-between;
      margin: 0 auto 24px; max-width: 1440px;
    }}
    h1 {{ margin: 0; font-size: 24px; }}
    header p {{ margin: 0; color: #5c667a; }}
    main {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px; max-width: 1440px; margin: auto;
    }}
    article {{
      overflow: hidden; background: #fff; border: 1px solid #dbe0e8;
      border-radius: 10px;
    }}
    img {{
      display: block; width: 100%; aspect-ratio: 4 / 3;
      object-fit: contain; background: #fff;
    }}
    footer {{
      display: flex; gap: 9px; align-items: baseline; padding: 10px 12px;
      border-top: 1px solid #edf0f4;
    }}
    footer strong {{ color: #1768e5; font-variant-numeric: tabular-nums; }}
  </style>
</head>
<body>
  <header>
    <div><h1>图形库轻量预览</h1><p>仅保留图类核心几何，无坐标轴、标题、图例和色标</p></div>
    <p>{len(entries)} 张</p>
  </header>
  <main>{cards}</main>
</body>
</html>
"""
    output = audit_directory / "index.html"
    output.write_text(page, encoding="utf-8")
    return output


def main() -> None:
    rcParams["svg.hashsalt"] = "plotagent-chart-library-preview"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
    ).strip()
    cases = _cases()
    if set(RENDERERS) != {case.profile_id for case in cases}:
        raise RuntimeError("chart preview renderer inventory differs from public profiles")

    entries: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        preview = OUTPUT / f"{case.profile_id}.svg"
        raw_png = OUTPUT / f".{case.profile_id}.raw.png"
        raw_svg = OUTPUT / f".{case.profile_id}.raw.svg"
        preview.unlink(missing_ok=True)
        raw_png.unlink(missing_ok=True)
        raw_svg.unlink(missing_ok=True)
        document, actions = _default_state(case)
        renderer = RENDERERS[case.profile_id]
        renderer.render(document, actions, case.view, raw_png, raw_svg)
        emphasis = _simplify_svg(raw_svg, preview, case.profile_id)
        raw_png.unlink(missing_ok=True)
        raw_svg.unlink(missing_ok=True)
        width, height = EXPECTED_SIZE
        entries.append(
            {
                "profile_id": case.profile_id,
                "backend": "matplotlib",
                "state": "default",
                "renderer": type(renderer).__name__,
                "fixture_sha256": _fixture_sha(case.view),
                "asset_format": "svg",
                "asset_sha256": _sha(preview),
                "preview_emphasis": emphasis,
                "width": width,
                "height": height,
            }
        )
        print(
            f"[{index:02d}/{len(cases)}] {case.profile_id} -> {preview.name}",
            flush=True,
        )

    expected_names = {f"{case.profile_id}.svg" for case in cases}
    for old in (*OUTPUT.glob("*.png"), *OUTPUT.glob("*.svg")):
        if old.name not in expected_names:
            old.unlink()
    manifest = {
        "schema_version": "plotagent.chart-library-previews.v4",
        "source_commit": source_commit,
        "source_policy": (
            "simplified vector preview derived from the production Matplotlib default "
            "state and representative engine fixtures"
        ),
        "simplification_policy": (
            "retain chart geometry; remove titles, axes, ticks, labels, legends, and color scales"
        ),
        "preview_palette": {
            "line_and_point": "#d95555",
            "bar_primary": "#1676d2",
            "bar_secondary": "#62a6e3",
            "bar_tertiary": "#a6ccee",
        },
        "origin_qualification": "tracked separately by the native Origin renderer audit",
        "count": len(entries),
        "entries": entries,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    audit_page = _write_audit_page(entries)
    print(f"audit -> {audit_page}", flush=True)


if __name__ == "__main__":
    main()
