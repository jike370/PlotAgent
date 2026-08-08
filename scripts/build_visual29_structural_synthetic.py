"""Build D-grade synthetic Origin evidence for K24, K25 and S01.

The reference path is deliberately independent from PlotAgent's renderer:
``reference`` uses OriginPro's shipped graph templates and native worksheet
plots, while ``render`` resolves the same frozen CSV through PlotAgent and
exports Matplotlib plus native O1 projects.  D-grade evidence is useful for
visual qualification and generalisation tests, but must never be reported as
an Origin A/C official same-source sample.
"""

# ruff: noqa: E402, E501 -- repository bootstrap and compact audit HTML are local.

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent import __version__ as PLOTAGENT_VERSION
from plotagent.contracts.base import (
    ColorValue,
    PhysicalLength,
    PreparedDatasetRef,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.plots import (
    FacetEditSpec,
    FacetLabelEdit,
    PrecomputedDataRef,
    PrecomputedSeriesData,
    PreparedSeriesData,
    SafeRichText,
    SafeTextNode,
    SeriesSpec,
    SpecialistEditSpec,
)
from plotagent.contracts.styles import SymbolStyle
from plotagent.exports import export_png
from plotagent.origin import build_origin_export_spec, compile_origin_plan, export_origin
from plotagent.origin.constants import (
    DECLARED_ORIGIN_BITNESS,
    DECLARED_ORIGIN_DISPLAY_NAME,
    DECLARED_ORIGIN_DISPLAY_VERSION,
    DECLARED_ORIGIN_RUNTIME_VERSION,
    DECLARED_ORIGINPRO_VERSION,
)
from plotagent.origin.models import OriginExportSuccess
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable, ResolvedPlot
from plotagent.rendering.resolver import PanelPlan
from scripts.visual_source_identity import assert_scope_clean, source_build_identity
from tests.rendering.fixture_factory import build_plot_and_store

ORIGIN = Path(r"D:\origin")
OUTPUT = REPOSITORY / "build" / "visual-audit" / "visual29-structural-synthetic"
FIXTURES = (
    REPOSITORY
    / "tests"
    / "fixtures"
    / "visual_regression"
    / "visual29-structural-synthetic"
)
GENERATOR_ID = "plotagent.visual29.structural.synthetic"
GENERATOR_VERSION = "1.0.0"
SEED = 24092501
CASE_IDS = ("K24", "K25", "S01")
SOURCE_SCOPE_VERSION = "visual29-structural-synthetic-rendering-v1"
SOURCE_SCOPE = (
    Path("pyproject.toml"),
    Path("src/plotagent/charts"),
    Path("src/plotagent/contracts/rendering.py"),
    Path("src/plotagent/contracts/styles.py"),
    Path("src/plotagent/origin"),
    Path("src/plotagent/rendering"),
)


@dataclass(frozen=True, slots=True)
class SyntheticCase:
    chart_id: Literal["K24", "K25", "S01"]
    slug: str
    title: str
    origin_template: Path
    origin_plot_type: str
    column_mapping: dict[str, str]
    semantic_claim: str
    dynamic_claim: str

    @property
    def case_id(self) -> str:
        return f"{self.chart_id}_{self.slug}"


CASES = (
    SyntheticCase(
        "K24",
        "facet",
        "分面图",
        ORIGIN / "mgroups.otpu",
        "native LINE plots in an Origin multi-panel template",
        {"facet": "panel identity", "base_x": "X", "base_y": "Y"},
        "Only the explicit facet column creates panels; no grouping is inferred.",
        "2/3/5 facets and 7/9/13 X values resolve without panel overlap.",
    ),
    SyntheticCase(
        "K25",
        "multi_panel",
        "多面板组合图",
        ORIGIN / "mgroups.otpu",
        "native LINE/SCATTER plots in an Origin multi-panel template",
        {"panel": "child-plan identity", "x": "X", "y": "Y"},
        "Every panel is an explicit child RenderPlan with a fixed placement.",
        "2/3/4 explicit child plans resolve in fixed non-overlapping layouts.",
    ),
    SyntheticCase(
        "S01",
        "precomputed_survival",
        "给定 KM 生存曲线",
        ORIGIN / "SurvivalPlot.otp",
        "native step-line equivalent plus risk-table layer",
        {
            "time": "X",
            "survival": "step Y",
            "lower": "CI lower",
            "upper": "CI upper",
            "risk_count": "risk-table Y",
            "group": "series identity",
        },
        "All step, confidence interval and risk-count values are supplied; no survival analysis runs.",
        "1/2/4 groups and shorter/longer time grids preserve monotone survival and panel separation.",
    ),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def generate_frame(
    chart_id: str,
    *,
    group_count: int | None = None,
    point_count: int | None = None,
) -> pd.DataFrame:
    """Return deterministic synthetic data; parameters drive generalisation tests."""

    if chart_id == "K24":
        facets = group_count or 3
        points = point_count or 9
        records: list[dict[str, Any]] = []
        for group_index in range(facets):
            label = f"Facet {chr(65 + group_index)}"
            for index, x_value in enumerate(np.linspace(0.0, 8.0, points)):
                y_value = (
                    0.75
                    + 0.22 * group_index
                    + 0.105 * x_value
                    + 0.18 * math.sin(x_value * 0.82 + group_index * 0.55)
                    + 0.012 * ((index * 7 + group_index * 3) % 5 - 2)
                )
                records.append(
                    {"facet": label, "base_x": round(x_value, 6), "base_y": round(y_value, 6)}
                )
        return pd.DataFrame(records)
    if chart_id == "K25":
        panels = group_count or 3
        points = point_count or 11
        records = []
        for panel_index in range(panels):
            label = f"Panel {chr(65 + panel_index)}"
            for x_value in np.linspace(0.0, 10.0, points):
                x_number = float(x_value)
                if panel_index % 3 == 0:
                    panel_y_value = (
                        0.35 + 0.14 * x_number + 0.22 * math.sin(x_number * 0.7)
                    )
                elif panel_index % 3 == 1:
                    panel_y_value = 1.8 * math.exp(-0.18 * x_number) + 0.15
                else:
                    panel_y_value = 0.55 + 0.055 * (x_number - 4.5) ** 2
                records.append(
                    {
                        "panel": label,
                        "x": round(x_number, 6),
                        "y": round(panel_y_value, 6),
                    }
                )
        return pd.DataFrame(records)
    if chart_id == "S01":
        groups = group_count or 2
        points = point_count or 9
        times = np.linspace(0.0, 24.0, points)
        records = []
        for group_index in range(groups):
            label = ("Placebo", "Treatment", "Cohort C", "Cohort D")[group_index]
            hazard = 0.075 - min(group_index, 3) * 0.011
            initial_risk = 96 - group_index * 7
            previous = 1.0
            for index, time_value in enumerate(times):
                survival = min(previous, math.exp(-hazard * time_value) * (1 - 0.012 * index))
                survival = max(0.05, survival)
                previous = survival
                spread = 0.035 + 0.005 * group_index + 0.002 * index
                records.append(
                    {
                        "time": round(time_value, 6),
                        "survival": round(survival, 6),
                        "lower": round(max(0.0, survival - spread), 6),
                        "upper": round(min(1.0, survival + spread), 6),
                        "risk_count": max(0, initial_risk - index * (8 + group_index)),
                        "group": label,
                    }
                )
        return pd.DataFrame(records)
    raise ValueError(f"unsupported synthetic structural chart: {chart_id}")


def _fixture_dir(case: SyntheticCase, fixtures: Path = FIXTURES) -> Path:
    return fixtures / case.case_id


def _provenance(case: SyntheticCase, data_path: Path) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "chart_type_id": case.chart_id,
        "case_id": case.case_id,
        "title": case.title,
        "evidence_grade": "D",
        "admission_class": "synthetic_origin_reference_visual_qualification",
        "origin_official_same_source_admission": False,
        "synthetic": True,
        "same_source_data": True,
        "generator": {
            "id": GENERATOR_ID,
            "version": GENERATOR_VERSION,
            "seed": SEED,
            "algorithm": "closed-form deterministic synthetic generator; no fitted or inferred values",
        },
        "data_sha256": _sha256(data_path),
        "reference_generation": {
            "path": "independent_origin_native_template_v1",
            "plotagent_renderer_used": False,
            "raw_csv_embedded": True,
            "raw_worksheet": f"DRef{case.chart_id}Raw",
            "origin_template": str(case.origin_template),
            "origin_template_sha256": _sha256(case.origin_template),
            "origin_plot_type": case.origin_plot_type,
            "column_mapping": case.column_mapping,
            "origin_version": DECLARED_ORIGIN_DISPLAY_VERSION,
            "originpro_version": DECLARED_ORIGINPRO_VERSION,
        },
        "semantic_claim": case.semantic_claim,
        "dynamic_claim": case.dynamic_claim,
    }


def prepare(fixtures: Path = FIXTURES) -> None:
    fixtures.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        case_dir = _fixture_dir(case, fixtures)
        case_dir.mkdir(parents=True, exist_ok=True)
        data_path = case_dir / "data.csv"
        generate_frame(case.chart_id).to_csv(data_path, index=False, lineterminator="\n")
        provenance = _provenance(case, data_path)
        (case_dir / "provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _ensure_layers(graph: Any, count: int) -> list[Any]:
    while len(list(graph)) < count:
        graph.add_layer(0)
    return list(graph)[:count]


def _layout_origin_layer(
    layer: Any,
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    layer.lt_exec(
        f"layer.left={left};layer.top={top};"
        f"layer.width={width};layer.height={height};"
    )
    legend = layer.label("Legend") or layer.label("legend")
    if legend is not None:
        legend.remove()


def _remove_origin_legend(layer: Any) -> None:
    legend = layer.label("Legend") or layer.label("legend")
    if legend is not None:
        legend.remove()
    template_title = layer.label("Title")
    if template_title is not None and "@LM" in template_title.text:
        template_title.remove()


def _prestep(frame: pd.DataFrame) -> pd.DataFrame:
    records: dict[str, pd.Series] = {}
    for group_index, (group, selected) in enumerate(frame.groupby("group", sort=False)):
        x = selected["time"].to_numpy(dtype=float)
        records[f"time_{group_index}"] = pd.Series(np.repeat(x, 2)[1:])
        for role in ("lower", "upper", "survival"):
            y = selected[role].to_numpy(dtype=float)
            records[f"{role}_{group_index}_{group}"] = pd.Series(np.repeat(y, 2)[:-1])
    return pd.DataFrame(records)


def _native_reference(case: SyntheticCase, frame: pd.DataFrame, case_dir: Path, op: Any) -> None:
    """Create a reference through Origin native templates, never PlotAgent."""

    op.new()
    raw_book = op.new_book("w", f"DRef{case.chart_id}Raw")
    raw_book[0].from_df(frame)
    if case.chart_id in {"K24", "K25"}:
        key = "facet" if case.chart_id == "K24" else "panel"
        labels = tuple(dict.fromkeys(frame[key].astype(str)))
        wide = pd.DataFrame()
        for index, label in enumerate(labels):
            selected = frame.loc[frame[key].astype(str) == label]
            x_name = "base_x" if case.chart_id == "K24" else "x"
            y_name = "base_y" if case.chart_id == "K24" else "y"
            wide[f"x_{index}"] = selected[x_name].reset_index(drop=True)
            wide[str(label)] = selected[y_name].reset_index(drop=True)
        sheet = op.new_book("w", f"DRef{case.chart_id}Plot")[0]
        sheet.from_df(wide)
        graph = op.new_graph(template=str(case.origin_template))
        layers = _ensure_layers(graph, len(labels))
        panel_width = 25.0
        panel_gap = 4.0
        first_left = (100.0 - len(labels) * panel_width - (len(labels) - 1) * panel_gap) / 2
        for index, (label, layer) in enumerate(zip(labels, layers, strict=True)):
            _layout_origin_layer(
                layer,
                left=first_left + index * (panel_width + panel_gap),
                top=14.0,
                width=panel_width,
                height=70.0,
            )
            plot_type: Any = 200 if case.chart_id == "K24" or index != 1 else 201
            layer.add_plot(sheet, coly=index * 2 + 1, colx=index * 2, type=plot_type)
            layer.rescale()
            _remove_origin_legend(layer)
            layer.axis("x").title = r"\p60(X)"
            layer.axis("y").title = rf"\p60({label})"
    else:
        stepped = _prestep(frame)
        sheet = op.new_book("w", "DRefS01Plot")[0]
        sheet.from_df(stepped)
        graph = op.new_graph(template=str(case.origin_template))
        layers = _ensure_layers(graph, 2)
        _layout_origin_layer(layers[0], left=13.0, top=7.0, width=79.0, height=59.0)
        _layout_origin_layer(layers[1], left=13.0, top=70.0, width=79.0, height=19.0)
        groups = tuple(dict.fromkeys(frame["group"].astype(str)))
        colors = (4, 2, 3, 6)
        for index, _group in enumerate(groups):
            x_column = index * 4
            lower = layers[0].add_plot(
                sheet, coly=x_column + 1, colx=x_column, type=200
            )
            upper = layers[0].add_plot(
                sheet, coly=x_column + 2, colx=x_column, type=200
            )
            survival = layers[0].add_plot(
                sheet, coly=x_column + 3, colx=x_column, type=200
            )
            color = colors[index % len(colors)]
            lower.color = color
            upper.color = color
            survival.color = color
            lower.set_fill_area(above=color, type=9)
            lower.set_cmd("-w 1")
            upper.set_cmd("-w 1")
            survival.set_cmd("-w 2")
        layers[0].rescale()
        _remove_origin_legend(layers[0])
        layers[0].set_xlim(0.0, float(frame["time"].max()))
        layers[0].set_ylim(0.0, 1.05, 0.2)
        layers[0].axis("x").title = ""
        layers[0].axis("y").title = r"\p60(Survival probability)"
        risk = op.new_book("w", "DRefS01Risk")[0]
        times = tuple(dict.fromkeys(frame["time"].astype(float)))
        risk_wide = pd.DataFrame({"time": times})
        for index, _group in enumerate(groups):
            risk_wide[f"row_{index}"] = tuple(float(len(groups) - index) for _ in times)
        risk.from_df(risk_wide)
        for index, group in enumerate(groups):
            selected = frame.loc[frame["group"].astype(str) == group]
            row_position = float(len(groups) - index)
            for time_value, count in zip(
                selected["time"], selected["risk_count"], strict=True
            ):
                label = layers[1].add_label(
                    rf"\p55({int(count)})", float(time_value), row_position
                )
                label.set_int("attach", 2)
                label.set_float("x1", float(time_value))
                label.set_float("y1", row_position)
            group_label = layers[1].add_label(
                rf"\p50({group})", float(times[0]), row_position
            )
            group_label.set_int("attach", 2)
            group_label.set_float("x1", float(times[0]))
            group_label.set_float("y1", row_position + 0.28)
        layers[1].set_xlim(float(times[0]), float(times[-1]))
        layers[1].set_ylim(0.5, float(len(groups)) + 0.75, 1.0)
        layers[1].axis("x").title = r"\p55(Time)"
        layers[1].axis("y").title = r"\p55(At risk)"
    reference = case_dir / "reference.png"
    project = case_dir / "reference-origin.opju"
    graph.save_fig(str(reference), type="png", replace=True, width=1600)
    op.save(str(project))
    op.open(str(project), readonly=True)
    reopened = list(op.pages("g"))
    if not reopened:
        raise RuntimeError(f"independent Origin reference lost its graph: {case.chart_id}")
    reopened[0].save_fig(
        str(case_dir / "reference-fresh-reopen.png"), type="png", replace=True, width=1600
    )


def reference(fixtures: Path = FIXTURES) -> None:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        for case in CASES:
            case_dir = _fixture_dir(case, fixtures)
            frame = pd.read_csv(case_dir / "data.csv")
            _native_reference(case, frame, case_dir, op)
            provenance_path = case_dir / "provenance.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance.update(
                {
                    "reference_sha256": _sha256(case_dir / "reference.png"),
                    "reference_fresh_reopen_sha256": _sha256(
                        case_dir / "reference-fresh-reopen.png"
                    ),
                    "reference_origin_opju_sha256": _sha256(
                        case_dir / "reference-origin.opju"
                    ),
                    "reference_fresh_reopen": True,
                }
            )
            provenance_path.write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    finally:
        op.exit()


def _rebound_prepared(plot: Any, frame: pd.DataFrame, roles: Sequence[str], identity: str) -> tuple[Any, RenderDataStore]:
    field_ids = tuple(plot.series[0].data.role_fields)
    table = RenderTable.from_columns(
        {
            field_id: tuple(frame[column].tolist())
            for field_id, column in zip(field_ids, roles, strict=True)
        }
    )
    prepared = PreparedDatasetRef(
        prepared_dataset_id=f"prepared:synthetic.structural.{identity}",
        prepared_version=1,
        content_hash=table.object_hash,
    )
    series = plot.series[0].model_copy(
        update={
            "data": PreparedSeriesData(
                prepared_dataset_ref=prepared, role_fields=field_ids
            )
        }
    )
    rebound = plot.model_copy(
        update={
            "plot_id": f"plot:synthetic.structural.{identity}",
            "prepared_data_refs": (prepared,),
            "series": (series,),
        }
    )
    return rebound, RenderDataStore({table.object_hash: table})


def build_k24(frame: pd.DataFrame, *, edited: bool = False) -> ResolvedPlot:
    plot, _ = build_plot_and_store("K24")
    plot, store = _rebound_prepared(plot, frame, ("facet", "base_x", "base_y"), "k24")
    labels = tuple(dict.fromkeys(frame["facet"].astype(str)))
    specialist = SpecialistEditSpec()
    if edited:
        specialist = specialist.model_copy(
            update={
                "facet": FacetEditSpec(
                    order=tuple(reversed(labels)),
                    labels=tuple(
                        FacetLabelEdit(value=label, label=f"{index + 1}. {label}")
                        for index, label in enumerate(reversed(labels))
                    ),
                    gap=PhysicalLength(value=2.5, unit="mm"),
                    shared_x=True,
                    shared_y=False,
                    common_legend=True,
                )
            }
        )
    plot = plot.model_copy(
        update={
            "plot_version": 2 if edited else 1,
            "title": _text("Facet response · edited" if edited else "Facet response"),
            "specialist": specialist,
            "resolved_style": plot.resolved_style.model_copy(
                update={"font_size": PhysicalLength(value=9.0 if edited else 8.0, unit="pt")}
            ),
        }
    )
    return PlotResolver().resolve(plot, store)


def _child_plot(frame: pd.DataFrame, panel: str, index: int, *, edited: bool) -> ResolvedPlot:
    child, _ = build_plot_and_store("K01")
    selected = frame.loc[frame["panel"].astype(str) == panel, ["x", "y"]]
    child, store = _rebound_prepared(child, selected, ("x", "y"), f"k25.child.{index}")
    style = child.series[0].style
    if edited:
        style = style.model_copy(
            update={
                "color": ColorValue(value=("#0072B2", "#D55E00", "#009E73", "#CC79A7")[index]),
                "line_width": PhysicalLength(value=1.4, unit="pt"),
                "symbol": SymbolStyle(shape=("circle", "square", "triangle_up", "diamond")[index]),
            }
        )
    child = child.model_copy(
        update={
            "plot_version": 2 if edited else 1,
            "title": _text(panel),
            "series": (child.series[0].model_copy(update={"style": style}),),
        }
    )
    return PlotResolver().resolve(child, store)


def _k25_placements(count: int, edited: bool) -> tuple[tuple[float, float, float, float], ...]:
    if not edited:
        width = (85.0 - 2.0 * (count - 1)) / count
        return tuple((2.0 + index * (width + 2.0), 2.0, width, 55.0) for index in range(count))
    columns = 2
    width, height = 41.5, 26.5
    return tuple(
        (2.0 + (index % columns) * 43.5, 2.0 + (index // columns) * 28.5, width, height)
        for index in range(count)
    )


def build_k25(frame: pd.DataFrame, *, edited: bool = False) -> ResolvedPlot:
    panels = tuple(dict.fromkeys(frame["panel"].astype(str)))
    if not 2 <= len(panels) <= 4:
        raise ValueError("K25 synthetic qualification requires two to four panels")
    base, _ = build_plot_and_store("K24")
    placeholder = PreparedDatasetRef(
        prepared_dataset_id="prepared:synthetic.structural.k25.placeholder",
        prepared_version=1,
        content_hash=hashlib.sha256(b"synthetic-k25-placeholder-v1").hexdigest(),
    )
    parent_series = base.series[0].model_copy(
        update={
            "geometry": "panel",
            "data": PreparedSeriesData(
                prepared_dataset_ref=placeholder,
                role_fields=("field:synthetic.structural.k25.panel",),
            ),
        }
    )
    parent = base.model_copy(
        update={
            "plot_id": "plot:synthetic.structural.k25",
            "plot_version": 2 if edited else 1,
            "chart_type_id": "K25",
            "prepared_data_refs": (placeholder,),
            "series": (parent_series,),
            "title": _text("Multi-panel figure · edited" if edited else "Multi-panel figure"),
        }
    )
    placements = _k25_placements(len(panels), edited)
    plans = tuple(
        PanelPlan(
            panel_id=f"panel:synthetic.{index}",
            resolved_plot=_child_plot(frame, panel, index, edited=edited),
            left_mm=left,
            top_mm=top,
            width_mm=width,
            height_mm=height,
            panel_label=_text(chr(65 + index)),
        )
        for index, (panel, (left, top, width, height)) in enumerate(
            zip(panels, placements, strict=True)
        )
    )
    return PlotResolver().resolve_panel_plans(parent, plans)


def build_s01(frame: pd.DataFrame, *, edited: bool = False) -> ResolvedPlot:
    base, _ = build_plot_and_store("S01")
    columns = ("time", "survival", "lower", "upper", "risk_count", "group")
    field_ids = {column: f"field:synthetic.structural.s01.{column}" for column in columns}
    table = RenderTable.from_columns(
        {field_ids[column]: tuple(frame[column].tolist()) for column in columns}
    )
    precomputed = PrecomputedDataRef(
        precomputed_id="precomputed:synthetic.structural.s01",
        precomputed_version=1,
        precomputed_kind="step_curve",
        content_hash=hashlib.sha256(b"synthetic-s01-precomputed-v1").hexdigest(),
        data_ref_hash=table.object_hash,
        field_ids=tuple(field_ids.values()),
    )

    def data(*roles: str) -> PrecomputedSeriesData:
        return PrecomputedSeriesData(
            precomputed_data_ref=precomputed,
            role_fields=tuple(field_ids[role] for role in roles),
        )

    series: tuple[SeriesSpec, ...] = (
        SeriesSpec(series_id="series:synthetic.s01.step", geometry="step", data=data("time", "survival", "group")),
        SeriesSpec(series_id="series:synthetic.s01.band", geometry="band", data=data("time", "lower", "upper", "group")),
        SeriesSpec(series_id="series:synthetic.s01.risk", geometry="risk_table", data=data("time", "risk_count", "group")),
    )
    if edited:
        category_colors = {
            "Placebo": ColorValue(value="#0072B2"),
            "Treatment": ColorValue(value="#D55E00"),
        }
        series = tuple(
            item.model_copy(
                update={
                    "style": item.style.model_copy(
                        update={
                            "category_colors": category_colors,
                            "line_width": PhysicalLength(value=1.3, unit="pt"),
                        }
                    )
                }
            )
            for item in series
        )
    plot = base.model_copy(
        update={
            "plot_id": "plot:synthetic.structural.s01",
            "plot_version": 2 if edited else 1,
            "precomputed_data_refs": (precomputed,),
            "series": series,
            "title": _text("Supplied survival curves · edited" if edited else "Supplied survival curves"),
            "resolved_style": base.resolved_style.model_copy(
                update={"font_size": PhysicalLength(value=9.0 if edited else 8.0, unit="pt")}
            ),
        }
    )
    return PlotResolver().resolve(plot, RenderDataStore({table.object_hash: table}))


def build_resolved(chart_id: str, frame: pd.DataFrame, *, edited: bool = False) -> ResolvedPlot:
    if chart_id == "K24":
        return build_k24(frame, edited=edited)
    if chart_id == "K25":
        return build_k25(frame, edited=edited)
    if chart_id == "S01":
        return build_s01(frame, edited=edited)
    raise ValueError(chart_id)


def _fresh_origin_png(target: Path, destination: Path) -> None:
    import originpro as op

    op.set_show(False)
    try:
        op.open(str(target), readonly=True)
        graphs = list(op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError(f"fresh PlotAgent OPJU graph count {len(graphs)} != 1")
        graphs[0].save_fig(str(destination), type="png", replace=True, width=1600)
    finally:
        op.exit()


def _contact_sheet(case_dir: Path, state: str) -> None:
    files = (
        case_dir / "reference-fresh-reopen.png",
        case_dir / state / "matplotlib.png",
        case_dir / state / "origin-fresh-reopen.png",
    )
    labels = ("D-GRADE ORIGIN REFERENCE", "MATPLOTLIB", "PLOTAGENT ORIGIN O1")
    images = [Image.open(path).convert("RGB") for path in files]
    try:
        width, height, header = 620, 470, 42
        output = Image.new("RGB", (width * 3, height + header), "white")
        draw = ImageDraw.Draw(output)
        for index, (source, label) in enumerate(zip(images, labels, strict=True)):
            fitted = ImageOps.contain(source, (width - 24, height - 24))
            output.paste(
                fitted,
                (index * width + (width - fitted.width) // 2, header + (height - fitted.height) // 2),
            )
            draw.text((index * width + 16, 14), f"{label} · {state.upper()}", fill="black")
        output.save(case_dir / f"comparison-{state}.png", optimize=True)
    finally:
        for source in images:
            source.close()


def _render_case(case: SyntheticCase, output: Path, fixtures: Path) -> dict[str, Any]:
    fixture_dir = _fixture_dir(case, fixtures)
    provenance = json.loads((fixture_dir / "provenance.json").read_text(encoding="utf-8"))
    required = ("data.csv", "reference.png", "reference-fresh-reopen.png", "reference-origin.opju")
    if any(not (fixture_dir / name).is_file() for name in required):
        raise RuntimeError(f"run --phase reference before rendering {case.chart_id}")
    if _sha256(fixture_dir / "data.csv") != provenance["data_sha256"]:
        raise RuntimeError(f"frozen synthetic data changed: {case.chart_id}")
    if _sha256(fixture_dir / "reference.png") != provenance["reference_sha256"]:
        raise RuntimeError(f"independent Origin reference changed: {case.chart_id}")
    case_dir = output / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    for name in (*required, "provenance.json"):
        shutil.copy2(fixture_dir / name, case_dir / name)
    frame = pd.read_csv(fixture_dir / "data.csv")
    entry: dict[str, Any] = {**provenance, "states": {}, "blocking_observations": []}
    resolved_states: list[ResolvedPlot] = []
    for state in ("default", "edited"):
        state_dir = case_dir / state
        state_dir.mkdir(exist_ok=True)
        resolved = build_resolved(case.chart_id, frame, edited=state == "edited")
        repeated = build_resolved(case.chart_id, frame, edited=state == "edited")
        if repeated.render_plan_hash != resolved.render_plan_hash:
            raise RuntimeError(f"non-deterministic render plan: {case.chart_id} {state}")
        resolved_states.append(resolved)
        export_png(state_dir / "matplotlib.png", resolved)
        (state_dir / "resolved-render-plan.json").write_text(
            resolved.plan.model_dump_json(indent=2), encoding="utf-8"
        )
        origin_plan = compile_origin_plan(
            (resolved,),
            build_origin_export_spec(
                (resolved,),
                export_id=f"export:synthetic.structural.{case.chart_id.lower()}.{state}",
                target_scope="selected_plots",
            ),
        )
        (state_dir / "origin-export-plan.json").write_text(
            origin_plan.model_dump_json(indent=2), encoding="utf-8"
        )
        target = state_dir / f"{case.chart_id}-{state}.opju"
        result = export_origin(
            origin_plan,
            target,
            expected_existing_sha256=_sha256(target) if target.is_file() else None,
            timeout_seconds=240.0,
        )
        if not isinstance(result, OriginExportSuccess):
            raise RuntimeError(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if result.build_validation != result.reopen_validation:
            raise RuntimeError(f"Origin validation drift: {case.chart_id} {state}")
        reopened = state_dir / "origin-fresh-reopen.png"
        _fresh_origin_png(target, reopened)
        state_entry = {
            "render_plan_sha256": resolved.render_plan_hash,
            "matplotlib_png_sha256": _sha256(state_dir / "matplotlib.png"),
            "origin_plan_sha256": canonical_hash(origin_plan),
            "origin_export_status": "success",
            "origin_opju_sha256": result.file_sha256,
            "origin_opju_size": result.file_size,
            "origin_fresh_png_sha256": _sha256(reopened),
            "fresh_reopen_identical": True,
            "validation_report_sha256": result.validation_report_sha256,
            "environment": result.environment.to_dict(),
            "panels": len(resolved.plan.panels),
            "layers": len(resolved.plan.layers),
            "visible_rows": resolved.plan.data_integrity.visible_rows,
        }
        (state_dir / "evidence.json").write_text(
            json.dumps(state_entry, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        entry["states"][state] = state_entry
        _contact_sheet(case_dir, state)
    combined_plan = compile_origin_plan(
        tuple(resolved_states),
        build_origin_export_spec(
            tuple(resolved_states),
            export_id=f"export:synthetic.structural.{case.chart_id.lower()}.per-chart",
            target_scope="selected_plots",
        ),
    )
    combined = case_dir / f"{case.chart_id}.opju"
    combined_result = export_origin(
        combined_plan,
        combined,
        expected_existing_sha256=_sha256(combined) if combined.is_file() else None,
        timeout_seconds=240.0,
    )
    if not isinstance(combined_result, OriginExportSuccess):
        raise RuntimeError(json.dumps(combined_result.to_dict(), ensure_ascii=False, indent=2))
    entry["per_chart_opju"] = {
        "states": ["default", "representative edited"],
        "sha256": combined_result.file_sha256,
        "size": combined_result.file_size,
        "fresh_reopen_identical": combined_result.build_validation
        == combined_result.reopen_validation,
    }
    return entry


def _write_index(entries: Sequence[dict[str, Any]], output: Path) -> None:
    cards = []
    for case, entry in zip(CASES, entries, strict=True):
        cards.append(
            f"""<article><h2>{case.chart_id} · {html.escape(case.title)}</h2>
<p><span>D 级合成证据</span> 同一冻结 CSV；参考图由 Origin 原生模板独立生成，不是 PlotAgent renderer 的输出。</p>
<p>{html.escape(case.semantic_claim)} {html.escape(case.dynamic_claim)}</p>
<h3>默认态</h3><a href="{case.case_id}/comparison-default.png"><img src="{case.case_id}/comparison-default.png"></a>
<h3>代表性编辑态</h3><a href="{case.case_id}/comparison-edited.png"><img src="{case.case_id}/comparison-edited.png"></a>
<p><a href="{case.case_id}/data.csv">CSV</a> · <a href="{case.case_id}/reference-origin.opju">独立 Origin 参考 OPJU</a> · <a href="{case.case_id}/reference.png">参考图</a> · <a href="{case.case_id}/{case.chart_id}.opju">PlotAgent 逐图 OPJU</a> · <a href="{case.case_id}/provenance.json">provenance</a></p>
<p>默认态 {entry['states']['default']['panels']} panels / {entry['states']['default']['layers']} layers；编辑态 {entry['states']['edited']['panels']} panels / {entry['states']['edited']['layers']} layers。</p></article>"""
        )
    (output / "index.html").write_text(
        f"""<!doctype html><meta charset="utf-8"><title>结构线 D 级合成 Origin 资格</title>
<style>body{{font:14px Arial,"Microsoft YaHei",sans-serif;margin:24px;background:#f4f6f8;color:#17202a}}main{{max-width:1500px;margin:auto}}article,.notice{{background:#fff;border:1px solid #d8dee7;margin:18px 0;padding:18px;border-radius:10px}}img{{width:100%;border:1px solid #d8dee7}}span{{background:#5b21b6;color:white;padding:3px 8px;border-radius:12px}}a{{color:#145fb8}}</style>
<main><h1>K24 / K25 / S01 · D 级合成 Origin 资格</h1><div class="notice"><strong>证据边界：</strong>这些图不再登记为“缺数据未测试”；其视觉资格来自冻结合成数据和 Origin 原生模板生成的独立参考。它们不是 Origin 官方 A/C 级样例，不能提升为官方同源证据。人工视觉签名仍为 pending。</div>{''.join(cards)}</main>""",
        encoding="utf-8",
    )


def render(
    output: Path = OUTPUT,
    fixtures: Path = FIXTURES,
    chart_ids: Sequence[str] = CASE_IDS,
) -> dict[str, Any]:
    assert_scope_clean(REPOSITORY, SOURCE_SCOPE)
    source_identity = source_build_identity(
        REPOSITORY,
        SOURCE_SCOPE,
        scope_version=SOURCE_SCOPE_VERSION,
    )
    output.mkdir(parents=True, exist_ok=True)
    selected = set(chart_ids)
    unknown = selected.difference(CASE_IDS)
    if unknown:
        raise ValueError(f"unsupported structural synthetic chart IDs: {sorted(unknown)}")
    existing_cases: dict[str, dict[str, Any]] = {}
    if selected != set(CASE_IDS):
        manifest_path = output / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError("partial render requires an existing complete manifest")
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing_manifest["qualification"]["source_build_identity"] != source_identity:
            raise RuntimeError("partial render cannot retain cases from a stale source identity")
        existing_cases = {
            str(item["chart_type_id"]): item for item in existing_manifest["cases"]
        }
        if set(existing_cases) != set(CASE_IDS):
            raise RuntimeError("partial render requires all structural synthetic cases")
    entries = [
        _render_case(case, output, fixtures)
        if case.chart_id in selected
        else existing_cases[case.chart_id]
        for case in CASES
    ]
    manifest = {
        "schema_version": "1.0",
        "stage": "VISUAL29-STRUCTURAL-SYNTHETIC-D",
        "generated_at": datetime.now(UTC).isoformat(),
        "plotagent_version": PLOTAGENT_VERSION,
        "lane_chart_type_ids": list(CASE_IDS),
        "origin_declaration": {
            "display_name": DECLARED_ORIGIN_DISPLAY_NAME,
            "display_version": DECLARED_ORIGIN_DISPLAY_VERSION,
            "runtime_version": DECLARED_ORIGIN_RUNTIME_VERSION,
            "bitness": DECLARED_ORIGIN_BITNESS,
            "originpro_version": DECLARED_ORIGINPRO_VERSION,
        },
        "rules": {
            "evidence_grade": "D",
            "synthetic_allowed": True,
            "origin_official_same_source_admission": False,
            "same_frozen_csv_required": True,
            "independent_origin_reference_required": True,
            "plotagent_renderer_for_reference_forbidden": True,
            "states": ["default", "representative edited"],
        },
        "cases": entries,
        "evidence_gaps": [],
        "qualification": {
            "evidence_status": "synthetic_origin_reference_pending_human",
            "source_build_identity": source_identity,
            "blocking_observations": [],
            "human_visual_signature": {"status": "pending", "reviewer": None, "signed_at": None},
            "decision": "NO-GO",
        },
        "audit_conclusion": "three prior data gaps are covered by explicitly labelled D-grade synthetic Origin references; human visual sign-off remains pending",
    }
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    (output / "manifest.json").write_text(payload, encoding="utf-8")
    (fixtures / "manifest.json").write_text(payload, encoding="utf-8")
    _write_index(entries, output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("prepare", "reference", "render", "all"), default="all")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--chart-id", action="append", choices=CASE_IDS)
    args = parser.parse_args()
    if args.phase in {"prepare", "all"}:
        prepare(args.fixtures)
        print("prepared deterministic D-grade synthetic data", flush=True)
    if args.phase in {"reference", "all"}:
        reference(args.fixtures)
        print("generated independent native Origin references", flush=True)
    if args.phase in {"render", "all"}:
        render(args.output, args.fixtures, args.chart_id or CASE_IDS)
        print(args.output / "index.html")


if __name__ == "__main__":
    main()
