"""Build current-source visual evidence for targeted renderer audits.

The command renders Matplotlib and native Origin default/edited states for
the selected profiles. Origin previews are exported by a separate process so
the review proves a fresh application reopen rather than a same-session load.
"""

# ruff: noqa: E402,E501,I001 -- repository path setup and self-contained HTML.

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine import (  # noqa: E402
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineRenderSource,
    FieldBinding,
    PlotDocument,
    PlotEngineAction,
    SetChartParameter,
    SetColorMap,
    SetAxis,
    SetCanvas,
    SetLegend,
    SetErrorStyle,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.contracts import EngineScalar  # noqa: E402
from plotagent.engine.backends.matplotlib.factory import (  # noqa: E402
    default_matplotlib_backend,
)
from plotagent.engine.backends.origin import (  # noqa: E402
    SubprocessOriginWorker,
    preflight_origin,
)
from plotagent.engine.backends.origin.messages import OriginWorkerRequest  # noqa: E402

OUTPUT = REPOSITORY / "build" / "visual-audit" / "renderer-rereview-4"
PROFILES = (
    "K06",
    "K07",
    "K14",
    "K22",
    "X09",
    "X13",
    "X23",
    "X35",
    "X36",
    "X38",
    "X40",
)


@dataclass(frozen=True, slots=True)
class ReviewCase:
    profile_id: str
    chinese_name: str
    official_name: str
    official_route: str
    document: PlotDocument
    actions: tuple[PlotEngineAction, ...]
    view: EngineDataView


def _column(
    field_id: str,
    name: str,
    logical_type: Literal["numeric", "categorical"],
    values: tuple[EngineScalar, ...],
) -> EngineColumn:
    return EngineColumn(
        field=EngineField(field_id=field_id, name=name, logical_type=logical_type),
        values=values,
    )


def _case(
    profile_id: str,
    roles: tuple[str, ...],
    columns: tuple[EngineColumn, ...],
    styles: tuple[tuple[str, dict[str, object]], ...],
    *,
    legend_visible: bool | None = True,
) -> tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView]:
    data = EngineDataRef(
        kind="source",
        dataset_id=f"dataset.rereview-{profile_id.lower()}",
        version=1,
        content_hash=sha256(profile_id.encode("ascii")).hexdigest(),
    )
    bindings = tuple(
        FieldBinding(role=role, field_id=column.field.field_id)
        for role, column in zip(roles, columns, strict=True)
    )
    plot_id = f"plot:rereview-{profile_id.lower()}"
    create = CreatePlot(
        action_id=f"action:rereview-create-{profile_id.lower()}",
        plot_id=plot_id,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    actions: list[PlotEngineAction] = [create]
    for object_key, arguments in styles:
        actions.append(
            SetSeriesStyle(
                action_id=f"action:rereview-style-{profile_id.lower()}-{len(actions)}",
                target=f"series:rereview-{profile_id.lower()}.{object_key}",
                expected_plot_version=len(actions),
                line_stroke_color=cast(Any, arguments.get("line_stroke_color")),
                line_width_pt=(
                    float(cast(float, arguments["line_width_pt"]))
                    if arguments.get("line_width_pt") is not None
                    else None
                ),
                line_style=cast(
                    Any,
                    arguments["line_style"]
                    if arguments.get("line_style") in {"solid", "dash", "dot", "dash_dot", "none"}
                    else None,
                ),
                line_opacity=(
                    float(cast(float, arguments["line_opacity"]))
                    if arguments.get("line_opacity") is not None
                    else None
                ),
                marker_shape=cast(
                    Any,
                    str(arguments["marker_shape"])
                    if arguments.get("marker_shape") is not None
                    else None,
                ),
                marker_size_pt=(
                    float(cast(float, arguments["marker_size_pt"]))
                    if arguments.get("marker_size_pt") is not None
                    else None
                ),
                marker_fill_color=cast(Any, arguments.get("marker_fill_color")),
                marker_stroke_color=cast(Any, arguments.get("marker_stroke_color")),
                fill_color=cast(Any, arguments.get("fill_color")),
                fill_opacity=(
                    float(cast(float, arguments["fill_opacity"]))
                    if arguments.get("fill_opacity") is not None
                    else None
                ),
                fill_stroke_color=cast(Any, arguments.get("fill_stroke_color")),
                fill_stroke_width_pt=(
                    float(cast(float, arguments["fill_stroke_width_pt"]))
                    if arguments.get("fill_stroke_width_pt") is not None
                    else None
                ),
                fill_stroke_style=cast(
                    Any,
                    arguments["fill_stroke_style"]
                    if arguments.get("fill_stroke_style")
                    in {"solid", "dash", "dot", "dash_dot", "none"}
                    else None,
                ),
            )
        )
    if legend_visible is not None:
        actions.append(
            SetLegend(
                action_id=f"action:rereview-legend-{profile_id.lower()}",
                target=f"legend:rereview-{profile_id.lower()}.main",
                expected_plot_version=len(actions),
                visible=legend_visible,
            )
        )
    document = PlotDocument(
        plot_id=plot_id,
        plot_version=len(actions),
        parent_version=None if len(actions) == 1 else len(actions) - 1,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:rereview-{index}" for index in range(len(columns[0].values))),
        columns=columns,
    )
    return document, tuple(actions), view


def _cases() -> tuple[ReviewCase, ...]:
    definitions: tuple[
        tuple[
            str,
            str,
            str,
            str,
            tuple[PlotDocument, tuple[PlotEngineAction, ...], EngineDataView],
        ],
        ...,
    ] = (
        (
            "K06",
            "双向误差棒图",
            "XY Error Bars",
            "X Y Error menu / ERRBAR.otpu",
            _case(
                "K06",
                (
                    "x",
                    "center",
                    "x_err_minus",
                    "x_err_plus",
                    "y_err_minus",
                    "y_err_plus",
                ),
                (
                    _column("field:x", "Time", "numeric", (1.0, 2.0, 3.0, 4.0)),
                    _column("field:center", "Estimate", "numeric", (2.0, 3.0, 4.0, 3.5)),
                    _column("field:xl", "X lower", "numeric", (0.75, 1.8, 2.65, 3.7)),
                    _column("field:xu", "X upper", "numeric", (1.15, 2.35, 3.2, 4.4)),
                    _column("field:lower", "Y lower", "numeric", (1.55, 2.45, 3.65, 2.9)),
                    _column("field:upper", "Y upper", "numeric", (2.4, 3.65, 4.25, 4.2)),
                ),
                (
                    (
                        "primary",
                        {
                            "line_stroke_color": "#AA3300",
                            "line_width_pt": 2.0,
                            "marker_shape": "diamond",
                            "marker_size_pt": 7.0,
                            "marker_fill_color": "#AA3300",
                            "marker_stroke_color": "#AA3300",
                        },
                    ),
                ),
            ),
        ),
        (
            "K07",
            "误差带图",
            "Error Band",
            "Plot > Basic 2D: Error Band / ERRORBAND.otpu",
            _case(
                "K07",
                ("x", "center", "lower", "upper"),
                (
                    _column("field:x", "Time", "numeric", (0.0, 1.0, 2.0, 3.0, 4.0)),
                    _column(
                        "field:center",
                        "Mean response",
                        "numeric",
                        (1.2, 2.0, 2.7, 2.4, 3.1),
                    ),
                    _column(
                        "field:lower",
                        "Lower confidence bound",
                        "numeric",
                        (0.8, 1.5, 2.1, 1.9, 2.5),
                    ),
                    _column(
                        "field:upper",
                        "Upper confidence bound",
                        "numeric",
                        (1.7, 2.6, 3.4, 3.0, 3.8),
                    ),
                ),
                (
                    (
                        "primary",
                        {
                            "line_stroke_color": "#5B2A86",
                            "line_width_pt": 2.0,
                            "line_style": "dash",
                            "line_opacity": 0.7,
                        },
                    ),
                ),
            ),
        ),
        (
            "K14",
            "小提琴图",
            "Violin Plot",
            "Plot.ogs [ViolinPlot] / Violin.otp",
            _case(
                "K14",
                ("value", "group"),
                (
                    _column(
                        "field:value",
                        "Dwell time (s)",
                        "numeric",
                        (
                            15.0,
                            26.0,
                            44.0,
                            58.0,
                            79.0,
                            112.0,
                            168.0,
                            241.0,
                            355.0,
                            510.0,
                            745.0,
                            1020.0,
                            12.0,
                            19.0,
                            31.0,
                            47.0,
                            69.0,
                            98.0,
                            139.0,
                            205.0,
                            298.0,
                            430.0,
                            625.0,
                            890.0,
                        ),
                    ),
                    _column(
                        "field:group",
                        "U1-C (nM)",
                        "categorical",
                        ("0",) * 12 + ("100",) * 12,
                    ),
                ),
                (
                    (
                        "group_1",
                        {
                            "fill_color": "#4C9ED9",
                            "fill_opacity": 0.55,
                            "fill_stroke_color": "#7A1F5C",
                            "fill_stroke_width_pt": 1.8,
                            "fill_stroke_style": "dash",
                        },
                    ),
                    (
                        "group_2",
                        {
                            "line_stroke_color": "#2B6E3F",
                            "line_width_pt": 2.4,
                            "line_style": "dot",
                        },
                    ),
                ),
            ),
        ),
        (
            "K22",
            "填色等高线图",
            "Filled Contour",
            "Plot3D.ogs [ContourColor] / CONTOUR.otpu",
            _case(
                "K22",
                ("x", "y", "z"),
                (
                    _column(
                        "field:x",
                        "Temperature (°C)",
                        "numeric",
                        (0.0, 1.0, 2.0, 3.0, 4.0) * 4,
                    ),
                    _column(
                        "field:y",
                        "Pressure (MPa)",
                        "numeric",
                        (0.0,) * 5 + (1.0,) * 5 + (2.0,) * 5 + (3.0,) * 5,
                    ),
                    _column(
                        "field:z",
                        "Response",
                        "numeric",
                        (
                            0.4,
                            1.2,
                            2.0,
                            1.1,
                            0.3,
                            1.0,
                            3.2,
                            5.8,
                            3.0,
                            0.9,
                            0.8,
                            2.7,
                            4.9,
                            2.5,
                            0.7,
                            0.2,
                            0.9,
                            1.6,
                            0.8,
                            0.2,
                        ),
                    ),
                ),
                (),
                legend_visible=None,
            ),
        ),
        (
            "X09",
            "浮动柱状图",
            "Floating Column",
            "worksheet -p 207 FloatCol / FloatCol.otp",
            _case(
                "X09",
                ("category", "start", "middle", "end"),
                (
                    _column(
                        "field:category",
                        "Condition",
                        "categorical",
                        ("Control", "Dose A", "Dose B", "Dose C"),
                    ),
                    _column("field:start", "Minimum", "numeric", (1.0, 2.0, 1.5, 2.5)),
                    _column("field:middle", "Median", "numeric", (3.0, 4.0, 3.5, 5.0)),
                    _column("field:end", "Maximum", "numeric", (5.0, 6.5, 5.5, 7.0)),
                ),
                (
                    (
                        "primary",
                        {
                            "fill_color": "#4C9ED9",
                            "fill_opacity": 0.6,
                            "fill_stroke_color": "#7A1F5C",
                            "fill_stroke_width_pt": 1.8,
                            "fill_stroke_style": "dash",
                        },
                    ),
                ),
            ),
        ),
        (
            "X13",
            "人口金字塔",
            "Population Pyramid",
            "Plot.ogs [PopulationPyramid] / PopulationPyramid.otpu",
            _case(
                "X13",
                ("category", "left", "right"),
                (
                    _column(
                        "field:age",
                        "Age group",
                        "categorical",
                        ("0–9", "10–19", "20–29", "30–39", "40–49"),
                    ),
                    _column("field:left", "Male", "numeric", (10.0, 12.0, 9.0, 8.0, 6.0)),
                    _column("field:right", "Female", "numeric", (11.0, 13.0, 10.0, 9.0, 7.0)),
                ),
                (
                    ("left", {"fill_color": "#2255AA", "fill_stroke_width_pt": 1.2}),
                    ("right", {"fill_color": "#CC6600", "fill_stroke_width_pt": 1.2}),
                ),
            ),
        ),
        (
            "X23",
            "双 Y 轴折线图",
            "Dual-Y Line",
            "Plot.ogs [2Ys_Y-Y] / DOUBLEY.otpu",
            _case(
                "X23",
                ("x", "left", "right"),
                (
                    _column(
                        "field:time",
                        "Time (h)",
                        "numeric",
                        (0.0, 6.0, 12.0, 24.0, 36.0, 48.0, 64.0, 80.0),
                    ),
                    _column(
                        "field:left",
                        "Cell biomass (g DCW/L)",
                        "numeric",
                        (0.4256, 1.4043, 1.8027, 2.9639, 3.2135, 4.0043, 5.0812, 5.6705),
                    ),
                    _column(
                        "field:right",
                        "Itaconate (g/L)",
                        "numeric",
                        (0.0, 0.1717, 0.5227, 1.5116, 2.1458, 3.0693, 3.9252, 5.061),
                    ),
                ),
                (
                    (
                        "left",
                        {
                            "line_stroke_color": "#7A1F5C",
                            "line_width_pt": 2.0,
                            "line_style": "dash",
                            "marker_shape": "diamond",
                            "marker_size_pt": 7.0,
                            "marker_fill_color": "#7A1F5C",
                            "marker_stroke_color": "#7A1F5C",
                        },
                    ),
                    (
                        "right",
                        {
                            "line_stroke_color": "#2B6E3F",
                            "line_width_pt": 2.4,
                            "line_style": "dot",
                            "marker_shape": "square",
                            "marker_size_pt": 6.0,
                            "marker_fill_color": "#2B6E3F",
                            "marker_stroke_color": "#2B6E3F",
                        },
                    ),
                ),
            ),
        ),
        (
            "X35",
            "双 Y 轴柱状图",
            "Dual-Y Column",
            "Plot.ogs [2YsCol] / 2Ys_Col.otpu",
            _case(
                "X35",
                ("category", "left", "right"),
                (
                    _column(
                        "field:category",
                        "Z1_amount_wt_pct",
                        "numeric",
                        (0.0, 10.0, 20.0, 30.0, 50.0),
                    ),
                    _column(
                        "field:left",
                        "Crack_onset_strain_pct",
                        "numeric",
                        (5.0, 5.0, 20.0, 20.0, 10.0),
                    ),
                    _column(
                        "field:right",
                        "Modulus_GPa",
                        "numeric",
                        (0.48, 0.34, 0.09, 0.2, 0.15),
                    ),
                ),
                (
                    (
                        "left",
                        {
                            "fill_color": "#7A1F5C",
                            "fill_opacity": 0.75,
                            "fill_stroke_color": "#3E0E2E",
                            "fill_stroke_width_pt": 1.4,
                            "fill_stroke_style": "dash",
                        },
                    ),
                    (
                        "right",
                        {
                            "fill_color": "#2B6E3F",
                            "fill_opacity": 0.65,
                            "fill_stroke_color": "#163A22",
                            "fill_stroke_width_pt": 1.8,
                            "fill_stroke_style": "dot",
                        },
                    ),
                ),
            ),
        ),
        (
            "X36",
            "双 Y 轴柱线图",
            "Dual-Y Column and Line",
            "Plot.ogs [2YsColSymb] / 2Ys_Col_Symb.otpu",
            _case(
                "X36",
                ("category", "left", "right"),
                (
                    _column(
                        "field:category",
                        "Week_start",
                        "categorical",
                        (
                            "2021-08-02",
                            "2021-08-09",
                            "2021-08-16",
                            "2021-08-23",
                            "2021-08-30",
                            "2021-09-06",
                            "2021-09-20",
                            "2021-09-27",
                            "2021-10-04",
                            "2021-10-11",
                            "2021-10-18",
                            "2021-10-25",
                            "2021-11-01",
                            "2021-11-08",
                            "2021-11-15",
                            "2021-11-22",
                            "2021-11-29",
                            "2021-12-06",
                            "2021-12-13",
                            "2021-12-20",
                            "2021-12-27",
                            "2022-01-03",
                            "2022-01-10",
                        ),
                    ),
                    _column(
                        "field:left",
                        "Detected_WWTP_count",
                        "numeric",
                        (
                            17.0,
                            8.0,
                            5.0,
                            10.0,
                            19.0,
                            2.0,
                            17.0,
                            16.0,
                            20.0,
                            18.0,
                            13.0,
                            15.0,
                            21.0,
                            14.0,
                            22.0,
                            27.0,
                            23.0,
                            21.0,
                            22.0,
                            23.0,
                            24.0,
                            19.0,
                            26.0,
                        ),
                    ),
                    _column(
                        "field:right",
                        "Mean_coverage_gt10",
                        "numeric",
                        (
                            1592.452380952381,
                            1789.657894736842,
                            2814.212121212121,
                            2737.3,
                            2174.0454545454545,
                            4120.736842105263,
                            1632.1224489795918,
                            1548.3157894736842,
                            2637.793103448276,
                            1952.3225806451612,
                            2707.3023255813955,
                            2534.8039215686276,
                            2163.235294117647,
                            2129.55,
                            1917.7142857142858,
                            1498.1186440677966,
                            1520.6909090909091,
                            1963.2448979591836,
                            2475.265625,
                            2300.06,
                            2039.66,
                            1155.3809523809523,
                            1143.732142857143,
                        ),
                    ),
                ),
                (
                    (
                        "left",
                        {
                            "fill_color": "#178A17",
                            "fill_opacity": 0.85,
                            "fill_stroke_color": "#0D520D",
                            "fill_stroke_width_pt": 0.8,
                            "fill_stroke_style": "solid",
                        },
                    ),
                    (
                        "right",
                        {
                            "line_stroke_color": "#1357E6",
                            "line_width_pt": 2.0,
                            "line_style": "dash",
                            "marker_shape": "none",
                        },
                    ),
                ),
                legend_visible=False,
            ),
        ),
        (
            "X38",
            "Y偏移堆叠线图",
            "Y Offset Stacked Lines",
            "Plot.ogs [OffsetYs] / OffsetStackY.otp",
            _case(
                "X38",
                ("x", "series_1", "series_2", "series_3"),
                (
                    _column("field:x", "Energy", "numeric", (1.0, 2.0, 3.0, 4.0, 5.0)),
                    _column("field:s1", "Spectrum 1", "numeric", (1.0, 2.5, 1.7, 3.0, 2.6)),
                    _column("field:s2", "Spectrum 2", "numeric", (2.0, 3.4, 2.5, 4.0, 3.6)),
                    _column("field:s3", "Spectrum 3", "numeric", (3.0, 4.2, 3.4, 5.0, 4.5)),
                ),
                (),
            ),
        ),
        (
            "X40",
            "前后对比图",
            "Before After",
            "Plot.ogs [BeforeAfter] / BeforeAfter.otpu",
            _case(
                "X40",
                ("series_1", "series_2", "label"),
                (
                    _column(
                        "field:before",
                        "Before SFC",
                        "numeric",
                        (
                            7.383013,
                            7.099438,
                            4.100129,
                            2.561526,
                            6.373234,
                            4.712009,
                            4.32279,
                            6.600283,
                        ),
                    ),
                    _column(
                        "field:after",
                        "After SFC",
                        "numeric",
                        (
                            14.82147,
                            11.67961,
                            8.667145,
                            8.010834,
                            17.37752,
                            5.455426,
                            25.8365,
                            5.757706,
                        ),
                    ),
                    _column(
                        "field:mouse",
                        "Mouse",
                        "numeric",
                        tuple(float(index) for index in range(1, 9)),
                    ),
                ),
                (
                    (
                        "column_1",
                        {
                            "marker_shape": "square",
                            "marker_size_pt": 6.0,
                            "marker_fill_color": "#BDBDBD",
                            "marker_stroke_color": "#BDBDBD",
                        },
                    ),
                    (
                        "column_2",
                        {
                            "marker_shape": "circle",
                            "marker_size_pt": 6.0,
                            "marker_fill_color": "#D95B67",
                            "marker_stroke_color": "#D95B67",
                        },
                    ),
                    (
                        "connector",
                        {
                            "line_stroke_color": "#000000",
                            "line_width_pt": 1.0,
                            "line_style": "solid",
                        },
                    ),
                ),
                legend_visible=False,
            ),
        ),
    )
    return tuple(
        ReviewCase(profile_id, chinese, official, route, *case)
        for profile_id, chinese, official, route, case in definitions
    )


def _create(actions: tuple[PlotEngineAction, ...]) -> CreatePlot:
    action = actions[0]
    if not isinstance(action, CreatePlot):
        raise TypeError("visual review histories must begin with create_plot")
    return action


def _document(
    create: CreatePlot,
    actions: tuple[PlotEngineAction, ...],
) -> PlotDocument:
    version = len(actions)
    return PlotDocument(
        plot_id=create.plot_id,
        plot_version=version,
        parent_version=None if version == 1 else version - 1,
        profile_id=create.profile_id,
        data=create.data,
        bindings=create.bindings,
        applied_action_ids=tuple(action.action_id for action in actions),
    )


def _states(
    case: ReviewCase,
) -> tuple[tuple[str, PlotDocument, tuple[PlotEngineAction, ...]], ...]:
    create = _create(case.actions)
    edited_actions = list(case.actions)
    if case.profile_id == "K06":
        edited_actions.append(
            SetErrorStyle(
                action_id="action:rereview-error-k06",
                target=f"series:{create.plot_id.removeprefix('plot:')}.primary",
                expected_plot_version=len(edited_actions),
                bar_color="#B42318",
                bar_width_pt=1.75,
                cap_size_pt=6.0,
                bar_opacity=0.7,
            )
        )
    elif case.profile_id == "K07":
        edited_actions.append(
            SetErrorStyle(
                action_id="action:rereview-error-k07",
                target=f"series:{create.plot_id.removeprefix('plot:')}.primary",
                expected_plot_version=len(edited_actions),
                band_fill_color="#F59E0B",
                band_fill_opacity=0.35,
                band_stroke_color="#B45309",
                band_stroke_width_pt=1.5,
            )
        )
    elif case.profile_id == "K22":
        edited_actions.extend(
            (
                SetChartParameter(
                    action_id="action:rereview-levels-k22",
                    target=create.plot_id,
                    expected_plot_version=len(edited_actions),
                    parameter="levels",
                    value=7,
                ),
                SetColorMap(
                    action_id="action:rereview-colormap-k22",
                    target=f"series:{create.plot_id.removeprefix('plot:')}.matrix",
                    expected_plot_version=len(edited_actions) + 1,
                    palette="magma",
                    reverse=True,
                    colorbar_visible=True,
                    colorbar_anchor="bottom",
                    colorbar_title="Response",
                    colorbar_tick_format="decimal",
                ),
            )
        )
    elif case.profile_id == "X35":
        edited_actions.extend(
            (
                SetAxis(
                    action_id="action:rereview-x35-x-axis",
                    target=f"axis:{create.plot_id.removeprefix('plot:')}.x",
                    expected_plot_version=len(edited_actions),
                    label="Z1 amount (wt%)",
                ),
                SetAxis(
                    action_id="action:rereview-x35-left-axis",
                    target=f"axis:{create.plot_id.removeprefix('plot:')}.y_left",
                    expected_plot_version=len(edited_actions) + 1,
                    label="Crack-onset strain (%)",
                    bounds_mode="fixed",
                    minimum=0.0,
                    maximum=25.0,
                    title_color="#7A1F5C",
                    tick_color="#7A1F5C",
                    axis_line_color="#7A1F5C",
                ),
                SetAxis(
                    action_id="action:rereview-x35-right-axis",
                    target=f"axis:{create.plot_id.removeprefix('plot:')}.y_right",
                    expected_plot_version=len(edited_actions) + 2,
                    label="Modulus (GPa)",
                    bounds_mode="fixed",
                    minimum=0.0,
                    maximum=0.6,
                    title_color="#2B6E3F",
                    tick_color="#2B6E3F",
                    axis_line_color="#2B6E3F",
                ),
            )
        )
    elif case.profile_id == "X36":
        edited_actions.extend(
            (
                SetCanvas(
                    action_id="action:rereview-x36-canvas",
                    target=create.plot_id,
                    expected_plot_version=len(edited_actions),
                    width_mm=180.0,
                    height_mm=80.0,
                    aspect_ratio=2.25,
                ),
                SetAxis(
                    action_id="action:rereview-x36-x-axis",
                    target=f"axis:{create.plot_id.removeprefix('plot:')}.x",
                    expected_plot_version=len(edited_actions) + 1,
                    label="Week start",
                    tick_rotation_deg=90.0,
                    title_color="#000000",
                    tick_color="#000000",
                    axis_line_color="#000000",
                ),
                SetAxis(
                    action_id="action:rereview-x36-left-axis",
                    target=f"axis:{create.plot_id.removeprefix('plot:')}.y_left",
                    expected_plot_version=len(edited_actions) + 2,
                    label="Site count",
                    title_color="#000000",
                    tick_color="#000000",
                    axis_line_color="#000000",
                ),
                SetAxis(
                    action_id="action:rereview-x36-right-axis",
                    target=f"axis:{create.plot_id.removeprefix('plot:')}.y_right",
                    expected_plot_version=len(edited_actions) + 3,
                    label="Mean coverage",
                    title_color="#000000",
                    tick_color="#000000",
                    axis_line_color="#000000",
                ),
            )
        )
    elif case.profile_id == "X40":
        edited_actions.extend(
            (
                SetChartParameter(
                    action_id="action:rereview-x40-hide-identities",
                    target=create.plot_id,
                    expected_plot_version=len(edited_actions),
                    parameter="identity_labels_visible",
                    value=False,
                ),
                SetAxis(
                    action_id="action:rereview-x40-x-axis",
                    target=f"axis:{create.plot_id.removeprefix('plot:')}.x",
                    expected_plot_version=len(edited_actions) + 1,
                    axis_title_visible=False,
                ),
                SetAxis(
                    action_id="action:rereview-x40-y-axis",
                    target=f"axis:{create.plot_id.removeprefix('plot:')}.y",
                    expected_plot_version=len(edited_actions) + 2,
                    label="Peak ΔF/F (%)",
                    bounds_mode="fixed",
                    minimum=0.0,
                    maximum=40.0,
                ),
            )
        )
    if case.profile_id != "X40":
        edited_actions.append(
            SetTitle(
                action_id=f"action:rereview-title-{case.profile_id.lower()}",
                target=create.plot_id,
                expected_plot_version=len(edited_actions),
                text=f"{case.official_name} representative edit",
            )
        )
    edited = tuple(edited_actions)
    return (
        ("default", _document(create, (create,)), (create,)),
        ("edited", _document(create, edited), edited),
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _run_origin_history(
    worker: SubprocessOriginWorker,
    install_dir: Path,
    case: ReviewCase,
    state: str,
    actions: tuple[PlotEngineAction, ...],
) -> None:
    case_dir = OUTPUT / case.profile_id
    create = _create(actions)
    previous: Path | None = None
    response = None
    for version in range(1, len(actions) + 1):
        history = actions[:version]
        document = _document(create, history)
        target = (
            case_dir / f"origin-{state}.opju"
            if version == len(actions)
            else case_dir / f".origin-{state}-v{version}.opju"
        )
        if target.exists():
            target.unlink()
        structure_target = target.with_name(f"{target.stem}.official-structure.opju")
        if structure_target.exists():
            structure_target.unlink()
        response = worker.run(
            OriginWorkerRequest(
                install_dir=str(install_dir),
                output_opju=str(target),
                previous_opju=None if previous is None else str(previous),
                document=document,
                actions=history,
                source=EngineRenderSource(data=case.view),
            )
        )
        previous = target
    if response is None:
        raise RuntimeError(f"Origin produced no response for {case.profile_id} {state}")
    _write_json(
        case_dir / f"origin-{state}.readback.json",
        response.readback.model_dump(mode="json"),
    )


def _fresh_export(opju: Path, target: Path) -> None:
    subprocess.run(
        (
            str(REPOSITORY / ".venv" / "Scripts" / "python.exe"),
            str(REPOSITORY / "build" / "export_one_origin_graph.py"),
            str(opju),
            str(target),
        ),
        cwd=REPOSITORY,
        check=True,
    )


def _render(cases: tuple[ReviewCase, ...]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    probe = preflight_origin(OUTPUT / "origin-preflight.opju")
    if probe.status != "ready":
        raise RuntimeError(probe.error.message)
    install_dir = Path(probe.environment.install_dir)
    worker = SubprocessOriginWorker(timeout_seconds=900)
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.profile_id} {case.chinese_name}", flush=True)
        case_dir = OUTPUT / case.profile_id
        case_dir.mkdir(parents=True, exist_ok=True)
        _write_json(case_dir / "data-view.json", case.view.model_dump(mode="json"))
        for state, document, actions in _states(case):
            with TemporaryDirectory(prefix=f".{case.profile_id}-{state}-", dir=OUTPUT) as root:
                backend = default_matplotlib_backend(Path(root) / "matplotlib")
                change = backend.stage(
                    document,
                    actions,
                    EngineRenderSource(data=case.view),
                )
                readback = change.readback
                change.publish()
                backend.export(document, case_dir / f"matplotlib-{state}.png", "png")
                backend.export(document, case_dir / f"matplotlib-{state}.svg", "svg")
                change.finalize()
            _write_json(
                case_dir / f"matplotlib-{state}.readback.json",
                readback.model_dump(mode="json"),
            )
            _run_origin_history(worker, install_dir, case, state, actions)
            _fresh_export(
                case_dir / f"origin-{state}.opju",
                case_dir / f"origin-{state}-fresh.png",
            )


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _build_index(cases: tuple[ReviewCase, ...], *, approved: bool) -> None:
    status = "PASS" if approved else "PENDING"
    rows: list[dict[str, Any]] = []
    cards: list[str] = []
    for case in cases:
        case_dir = OUTPUT / case.profile_id
        images = tuple(
            (label, case_dir / filename)
            for label, filename in (
                ("Matplotlib 默认态", "matplotlib-default.png"),
                ("Origin 官方模板默认态（独立 fresh reopen）", "origin-default-fresh.png"),
                ("Matplotlib 代表编辑态", "matplotlib-edited.png"),
                ("Origin 原生代表编辑态（独立 fresh reopen）", "origin-edited-fresh.png"),
            )
        )
        opjus = (case_dir / "origin-default.opju", case_dir / "origin-edited.opju")
        for _label, path in images:
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"missing visual review image: {path}")
        for path in opjus:
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"missing visual review OPJU: {path}")
        panels = "".join(
            f"<figure><figcaption>{html.escape(label)}</figcaption>"
            f'<a href="{path.resolve().as_uri()}"><img src="{path.resolve().as_uri()}" '
            f'alt="{html.escape(case.chinese_name)} {html.escape(label)}"></a></figure>'
            for label, path in images
        )
        cards.append(
            f'<article id="{case.profile_id}"><header><h2>{case.profile_id} '
            f"{html.escape(case.chinese_name)}｜{html.escape(case.official_name)}</h2>"
            f"<span>{status}</span></header><p><b>官方路线：</b>{html.escape(case.official_route)}</p>"
            f'<p><a href="{opjus[0].resolve().as_uri()}">默认 OPJU</a>　'
            f'<a href="{opjus[1].resolve().as_uri()}">编辑 OPJU</a></p>'
            f'<div class="grid">{panels}</div></article>'
        )
        rows.append(
            {
                "profile_id": case.profile_id,
                "chinese_name": case.chinese_name,
                "official_name": case.official_name,
                "official_route": case.official_route,
                "visual_status": status,
                "artifacts": {
                    path.name: {"size": path.stat().st_size, "sha256": _sha(path)}
                    for path in (*[item[1] for item in images], *opjus)
                },
            }
        )
    commit = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=REPOSITORY, text=True
    ).strip()
    _write_json(
        OUTPUT / "review-manifest.json",
        {
            "schema_version": "plotagent.renderer-rereview.v1",
            "source_commit": commit,
            "profiles": list(PROFILES),
            "review_status": status,
            "reviewed_by": "Codex visual inspection" if approved else None,
            "cases": rows,
        },
    )
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>4图当前renderer复审</title>
<style>body{{margin:0;background:#f4f6f8;color:#17202a;font:14px/1.5 "Microsoft YaHei UI",sans-serif}}main{{max-width:1600px;margin:auto;padding:24px}}.intro,article{{background:white;border:1px solid #dce1e6;border-radius:12px;padding:20px;margin-bottom:18px}}header{{display:flex;justify-content:space-between;align-items:center}}h1,h2{{margin:0}}header span{{color:{"#127a48" if approved else "#8a5a00"};font-weight:700}}a{{color:#145c9e}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}figure{{margin:0;border:1px solid #dce1e6;border-radius:8px;overflow:hidden}}figcaption{{padding:8px;background:#f7f8fa;font-weight:600}}img{{display:block;width:100%;height:500px;object-fit:contain}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}img{{height:auto}}}}</style></head>
<body><main><section class="intro"><h1>当前 renderer 定向复审</h1><p>源码提交：{commit}</p><p>判定：{status}。所选模板均重新生成 Matplotlib/Origin 默认态、代表编辑态和独立 fresh-reopen 证据。</p></section>{"".join(cards)}</main></body></html>"""
    (OUTPUT / "index.html").write_text(page, encoding="utf-8")
    print(OUTPUT / "index.html")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="reuse rendered artifacts and rebuild only the audit page/manifest",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="record approval after the generated images have been inspected",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=PROFILES,
        help="render only the named profiles while retaining the complete review index",
    )
    args = parser.parse_args()
    cases = _cases()
    if tuple(case.profile_id for case in cases) != PROFILES:
        raise RuntimeError("targeted visual review inventory drifted")
    if not args.index_only:
        selected = (
            cases
            if args.profiles is None
            else tuple(case for case in cases if case.profile_id in set(args.profiles))
        )
        _render(selected)
    _build_index(cases, approved=args.approve)


if __name__ == "__main__":
    main()
