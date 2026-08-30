"""Canonical Origin creation recipes for Agent Native chart profiles.

This module is the single runtime authority for how a public chart profile is
created in Origin.  A recipe records the official Origin route, the pinned
Origin 2024 template assets (when the route uses one), the required source
layout, the rebuild policy and the native facts that must survive readback.

Recipes intentionally do not contain arbitrary LabTalk.  Executable binders
remain ordinary reviewed Python modules and are selected by ``binder_key``.
The recipe tells those binders what they are allowed to create; it is not a
second scripting language exposed to an Agent.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import StringConstraints, model_validator

from plotagent.contracts.base import ChartTypeId, Sha256, StrictModel, Token

OriginCreationKind = Literal[
    "graph_template",
    "x_function",
    "analysis",
    "app",
]
OriginSourceLayout = Literal[
    "worksheet_xy",
    "worksheet_wide",
    "worksheet_long_indexed",
    "matrix",
    "analysis_table",
]
OriginSupportStatus = Literal[
    "renderable",
    "structural_fail",
    "dependency_blocked",
    "automation_blocked",
]
OriginProofLevel = Literal["proven_native_structure", "manual_native_property", "blocked"]
OriginRebuildPolicy = Literal[
    "recreate_from_source",
    "recompute_analysis",
]
OriginRevisionMaterialization = Literal[
    "previous_project",
    "current_state",
]

_HelpUrl = Annotated[
    str,
    StringConstraints(pattern=r"^https://(?:docs|cloud)\.originlab\.com/", strict=True),
]
_NonEmpty = Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]


class OriginTemplateIdentity(StrictModel):
    """One hash-pinned asset shipped by the inspected Origin installation."""

    filename: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z0-9_. -]+\.[Oo][Tt][Pp][Uu]?$", strict=True),
    ]
    sha256: Sha256
    role: Literal["primary", "same_layout", "output_layout"] = "primary"


class OriginRecipe(StrictModel):
    """Closed recipe selected by a public ``profile_id``."""

    profile_id: ChartTypeId
    chinese_name: _NonEmpty
    official_name: _NonEmpty
    official_help_url: _HelpUrl
    official_entry: _NonEmpty
    local_dispatch: _NonEmpty
    creation_kind: OriginCreationKind
    binder_key: Token | None
    templates: tuple[OriginTemplateIdentity, ...] = ()
    source_layout: OriginSourceLayout
    designation_contract: tuple[_NonEmpty, ...]
    rebuild_policy: OriginRebuildPolicy
    revision_materialization: OriginRevisionMaterialization = "previous_project"
    native_plot_types: tuple[int, ...] = ()
    readback_contract: tuple[_NonEmpty, ...]
    support_status: OriginSupportStatus = "renderable"
    proof_level: OriginProofLevel
    manual_gate: str | None = None

    @model_validator(mode="after")
    def _validate_route(self) -> OriginRecipe:
        if self.support_status == "renderable" and self.binder_key is None:
            raise ValueError("a renderable Origin recipe requires a binder key")
        if self.support_status != "renderable" and self.proof_level != "blocked":
            raise ValueError("a blocked Origin recipe must use proof_level='blocked'")
        if self.proof_level == "manual_native_property" and not self.manual_gate:
            raise ValueError("manual-native recipes require a precise manual gate")
        if self.creation_kind == "graph_template" and not self.templates:
            raise ValueError("graph-template recipes require a pinned template")
        if self.creation_kind == "app" and self.support_status != "dependency_blocked":
            raise ValueError("an Origin App route must remain dependency-blocked until proven")
        if len({item.filename.casefold() for item in self.templates}) != len(self.templates):
            raise ValueError("a recipe cannot repeat an Origin template")
        return self

    @property
    def primary_template(self) -> OriginTemplateIdentity | None:
        return next((item for item in self.templates if item.role == "primary"), None)


def _template(filename: str, digest: str, *, role: str = "primary") -> OriginTemplateIdentity:
    return OriginTemplateIdentity(filename=filename, sha256=digest, role=role)  # type: ignore[arg-type]


_T = {
    "line": _template(
        "LINE.otpu", "76a7ce886e2290d29444ac3a92c736a2057d2583aea8867091db439cb23dc648"
    ),
    "linesymb": _template(
        "LINESYMB.otpu", "2f1292a939eac92cd0dc820309885caccfa53293d1db78d18447a5b5b329fed1"
    ),
    "scatter": _template(
        "SCATTER.OTP", "efef85d7c3db5028c565a57e15c86f97d6ebeded6d779c1cdb11328a7fbd4a99"
    ),
    "bubble": _template(
        "bubble.otpu", "abc20768493ef817b567bd3e58bb0c3da1a8ec59c56f0d1b92c2341479560b44"
    ),
    "errorbar": _template(
        "ERRBAR.otpu", "c17ebd8f68f8585c3bb4c431e75f4dc1724e3f54ee1fd7d0977b6cadcf1c599b"
    ),
    "errorband": _template(
        "ERRORBAND.otp", "dfd36bf19bf3cf81bebd7d2b7d04a0ef05f07f90243678ddf3d03eded342c763"
    ),
    "column": _template(
        "COLUMN.otpu", "ec9e654e886056a466c3447afeab950d371ac6f297d5e325b25e99b7a3d769cd"
    ),
    "stack_column": _template(
        "STACKCOLUMN.otp",
        "3ffd84ea777e414c60daab6e3b162b207379b94341ef1497c144a725f0caa264",
    ),
    "percent_stack_column": _template(
        "StackColP.otp",
        "2094be00706be51883e7d5f8212e79e5eb1ac01ff66af45ba4953761ba8fe7d3",
    ),
    "gcolumn": _template(
        "gColumn.otpu", "7178d8b38efdb448909d3e0956d12347ef9340773be3c8f4625fe5b4cca06d0e"
    ),
    "column_scatter": _template(
        "ColumnScatter.otp",
        "e9bfbf3b74bc78db041208505bf1c1b32b387378cc8aac91462d017a662c425d",
    ),
    "box": _template("BOX.OTP", "a1f26e68a6a070aba0769905c6b143766a51abd0d7e6039ad93de49ab600daaa"),
    "violin": _template(
        "Violin.otpu", "ee71ef5fb2bf15cfc403444494f1779999df31d43c0a3e24001cb35b838bc1eb"
    ),
    "hist": _template(
        "Hist.otpu", "cc1d7edd9f07f8bb0e1b0fe6f9ea0f36439afa912d209efc29329df9c2f00cfa"
    ),
    "area": _template(
        "AREA.otpu", "c14ad432ffd60db09f6763b7b988de4aa554dcf0d9772b18334970fb83eddaec"
    ),
    "heatmap": _template(
        "Heat_Map.otpu", "9bd8240ca582bbedfec797ea27b1ec5c2906939e304fa343cd1821bae2ffbb9f"
    ),
    "heatmap_labels": _template(
        "Heat_Map_With_Labels.otpu",
        "d1a7fcd8af232aef9ca348eb178466a13a744eb700da7d49d39cfbe16c935c7d",
    ),
    "contour": _template(
        "CONTOUR.otpu", "b4915054edd419955245e485b606784dbb6b4965dd6359b45603e00a866628e2"
    ),
    "grouped": _template(
        "Grouped.otp", "b3a1999cc9e95e55d661863e60efbcc792af415bc83b0962f01f1636d35c7af0"
    ),
    "mgroups": _template(
        "mgroups.otpu", "391e5689e8f5436f029099086a9e65b50679606120275a6a958417d235f1dd9b"
    ),
    "dropline": _template(
        "DROPLINE.OTP", "69cbcf9349249092e2e32c8955c88c0a265ac47a46811885593d9eced643299f"
    ),
    "lollipop": _template(
        "Lollipop.otpu", "f76fc89b9438947bbcd601b53e03cf16732a931621143b469233e584f88ba58b"
    ),
    "beeswarm": _template(
        "Beeswarm.otpu", "301dd6c8c2938b4459bcad1bc04233e1c24d7aaf94f53474db1231692769a979"
    ),
    "floatcol": _template(
        "FloatCol.otp", "f1ea445735f9cf3fa93ed3de9ff187db0fc83ccba92578e6939fbafafeddb3f6"
    ),
    "population": _template(
        "PopulationPyramid.otpu",
        "2c5958a91130d62cf8a6708f197bfd6248a3b22d81fc68eed1abe5f10988fbab",
    ),
    "doubley": _template(
        "DOUBLEY.OTP", "487547eb206e4645f3380a9a021ceb7fbcf4ec4d1fdb0a870d1eb0cde0c7641b"
    ),
    "paretobin": _template(
        "ParetoBin.otpu", "fa991237fbf2f5a0139b4acd6ba44372928f55922a8c347941d3a6442559ba84"
    ),
    "two_y_column": _template(
        "2Ys_Col.otpu", "cba0737aaa4c2ab24a62062cfe37c095c5651d9048519b3fc2a3e9ccaa058ca9"
    ),
    "two_y_column_symbol": _template(
        "2Ys_ColSymb.otpu",
        "6e951a3dd1f08cb2122cac48ce37476eef54d54c9fb424211e9fce39c677e1ab",
    ),
    "offset_y": _template(
        "OffsetStackY.otp",
        "c6d7548cf7389e5d53282c6d1873aa2e8e184de96ae54d2cd71937f0a56d98d3",
    ),
    "box_line_series": _template(
        "BoxLser.otpu", "8396fd58435c4ded363b889d7eb3c8cf8a3b22e82eb539e8cc85f6b58481ec83"
    ),
    "before_after": _template(
        "BeforeAfter.otpu",
        "d37a1c2949696f29cd2a2fcf856a2c8b5f8be29e8ab040a83a9c2c9f0e262c0b",
    ),
}


# Exact creation routes recovered from the inspected Origin 2024 Build 178
# installation.  These are provenance signatures, not Agent-visible scripts:
# binders still own parameter substitution and execution.  Keeping the route in
# the recipe prevents a renderer from loading the right template through a
# different, visually similar construction path.
_LOCAL_DISPATCH: Mapping[str, str] = MappingProxyType(
    {
        "K01": "Plot.ogs [Line] -> general,200 Line",
        "K02": "Plot.ogs [LineSymbol] -> general,202 LineSymb",
        "K03": "Plot.ogs [Scatter] -> general,201 Scatter",
        "K04": "worksheet -p 248 Bubble",
        "K06": "menu 33336 -> worksheet -p 201 ERRBAR",
        "K07": "Plot.ogs [ScatterErrorBand] -> general,201 ERRORBAND",
        "K08": "Plot.ogs [Column] -> general,203 Column",
        "K09": (
            "Plot.ogs [GroupedCols] -> worksheet -px ? gColumn "
            "plot_gindexed plottype:=0"
        ),
        "K10": "Plot.ogs [StackCol] -> general,213 StackColumn",
        "K11": "Plot.ogs [StackColPercentage] -> general,213 StackColP",
        "K12": "Plot.ogs [ColumnScatter] -> BoxChartImp ColumnScatter",
        "K13": "Plot.ogs [BoxChart] -> BoxChartImp Box",
        "K14": "Plot.ogs [ViolinPlot] -> ViolinPlotImp 206 Violin",
        "K15": "Plot.ogs [Histogram] -> worksheet -p 219 Hist",
        "K18": "Plot.ogs [Area] -> general,204 Area",
        "K19": "Plot.ogs [Line] -> general,200 Line",
        "K20": "Plot3D.ogs [HeatMap] -> GenericHeatMap Heat_Map 105 1 1",
        "K21": (
            "Plot3D.ogs [HeatMapWithLabels] -> "
            "GenericHeatMap Heat_Map_With_Labels 105 1 1"
        ),
        "K22": "Plot3D.ogs [ContourColor] -> matrix PID226 CONTOUR",
        "K24": "plot_group type:=linesymb template:=Grouped",
        "S34": "Plot.ogs [LineSymbol] -> general,202 LineSymb",
        "S61": "plotvm type:=105 template:=Heat_Map_With_Labels",
        "X02": "worksheet -p 201 DROPLINE",
        "X03": "Plot.ogs [Lollipop] -> general,201 Lollipop",
        "X05": "Plot.ogs [Beeswarm] -> worksheet -p 206 Beeswarm",
        "X09": "Plot.ogs [FloatColumn] -> general,207 FloatCol",
        "X13": "Plot.ogs [PopulationPyramid] -> PlotToTemplate PopulationPyramid",
        "X23": "Plot.ogs [2Ys_Y-Y] -> PlotToTemplate DOUBLEY",
        "X24": "plot_paretobin template:=ParetoBin",
        "X35": "Plot.ogs [2YsCol] -> PlotToTemplate 2Ys_Col",
        "X36": "Plot.ogs [2YsColSymb] -> PlotToTemplate 2Ys_ColSymb",
        "X38": "Plot.ogs [OffsetYs] -> worksheet -P 200 OffsetStackY",
        "X39": (
            "Plot.ogs [LineSeries] -> run.section(,BoxChartImp,BoxLser 0) "
            "-> worksheet -p 206 BoxLser"
        ),
        "X40": "Plot.ogs [BeforeAfter] -> run.section(,general,206 BeforeAfter 0 1)",
    }
)


def _r(
    profile_id: ChartTypeId,
    chinese_name: str,
    official_name: str,
    help_url: str,
    entry: str,
    kind: OriginCreationKind,
    source_layout: OriginSourceLayout,
    designation: tuple[str, ...],
    readback: tuple[str, ...],
    *,
    template_keys: tuple[str, ...] = (),
    binder_key: str | None = None,
    rebuild_policy: OriginRebuildPolicy = "recreate_from_source",
    revision_materialization: OriginRevisionMaterialization = "previous_project",
    native_plot_types: tuple[int, ...] = (),
    support_status: OriginSupportStatus = "renderable",
    proof_level: OriginProofLevel = "proven_native_structure",
    manual_gate: str | None = None,
) -> OriginRecipe:
    templates = tuple(_T[key] for key in template_keys)
    return OriginRecipe(
        profile_id=profile_id,
        chinese_name=chinese_name,
        official_name=official_name,
        official_help_url=help_url,
        official_entry=entry,
        local_dispatch=_LOCAL_DISPATCH[str(profile_id)],
        creation_kind=kind,
        binder_key=binder_key,
        templates=templates,
        source_layout=source_layout,
        designation_contract=designation,
        rebuild_policy=rebuild_policy,
        revision_materialization=revision_materialization,
        native_plot_types=native_plot_types,
        readback_contract=readback,
        support_status=support_status,
        proof_level=proof_level,
        manual_gate=manual_gate,
    )


_RECIPES = (
    _r(
        "K01",
        "折线图",
        "Line Graph",
        "https://docs.originlab.com/origin-help/line-graph/",
        "Plot > Basic 2D: Line",
        "graph_template",
        "worksheet_xy",
        ("X", "Y"),
        ("native line", "X/Y source binding"),
        template_keys=("line",),
        binder_key="K01",
        native_plot_types=(200,),
    ),
    _r(
        "K02",
        "线+符号图",
        "Line+Symbol Graph",
        "https://docs.originlab.com/origin-help/linesym-graph/",
        "Plot > Basic 2D: Line + Symbol",
        "graph_template",
        "worksheet_xy",
        ("X", "Y"),
        ("one native line-symbol plot", "X/Y source binding"),
        template_keys=("linesymb",),
        binder_key="K02",
        native_plot_types=(202,),
    ),
    _r(
        "K03",
        "二维散点图",
        "2D Scatter Graph",
        "https://docs.originlab.com/origin-help/2dscatter-graph/",
        "Plot > Basic 2D: Scatter",
        "graph_template",
        "worksheet_xy",
        ("X", "Y", "optional group split into native plots"),
        ("native scatter plots", "group/source binding"),
        template_keys=("scatter",),
        binder_key="K03",
        native_plot_types=(201,),
        # K03 always reconstructs the requested graph from immutable source
        # data plus the complete effective action history.  Its binder never
        # opens ``previous_opju``; recursively materializing v1..vN before a
        # first export only repeats Origin startup and template construction.
        revision_materialization="current_state",
    ),
    _r(
        "K04",
        "索引大小气泡与颜色映射图",
        "Indexed Size (Bubble) and Color Map Graph",
        "https://docs.originlab.com/origin-help/bubble-color-map-graph/",
        "Plot > Basic 2D: Bubble + Color Mapped",
        "graph_template",
        "worksheet_xy",
        ("X", "Y", "size Y", "color Y"),
        (
            "size modifier",
            "color modifier",
            "Bubble Scale present",
            "Color Scale absent by default",
        ),
        template_keys=("bubble",),
        binder_key="K04",
        # The menu dispatcher uses creation type 248, but Origin persists the
        # result as one Scatter DataPlot (PID 201) with size/color modifiers.
        native_plot_types=(201,),
    ),
    _r(
        "K06",
        "XY双向误差棒图",
        "XY Error Bar Graph",
        "https://docs.originlab.com/origin-help/xy-errbar-graph/",
        "Plot > Basic 2D: XY Error",
        "graph_template",
        "worksheet_xy",
        ("X", "Y", "Y error", "X error"),
        ("horizontal ErrorBar2D", "vertical ErrorBar2D", "cap width"),
        template_keys=("errorbar",),
        binder_key="K06",
        native_plot_types=(201,),
    ),
    _r(
        "K07",
        "误差带图",
        "Error Band Graph",
        "https://docs.originlab.com/origin-help/error-band-graph/",
        "Plot > Basic 2D: Error Band",
        "graph_template",
        "worksheet_xy",
        ("X", "Y", "YEr-", "YEr+"),
        ("native ErrorBand", "fill relation", "source designation"),
        template_keys=("errorband",),
        binder_key="K07",
        native_plot_types=(201,),
    ),
    _r(
        "K08",
        "柱状图",
        "Column Graph",
        "https://docs.originlab.com/origin-help/column-graph/",
        "Plot > Bar, Pie, Area: Column",
        "graph_template",
        "worksheet_xy",
        ("categorical X", "Y"),
        ("native column", "category/source binding"),
        template_keys=("column",),
        binder_key="K08",
        native_plot_types=(203,),
        # K08 always rebuilds the requested native state from source plus the
        # complete action history.  Replaying v1..vN before a first export only
        # multiplies Origin startup cost and does not contribute state.
        revision_materialization="current_state",
    ),
    _r(
        "K09",
        "分组柱状图（索引数据）",
        "Grouped Columns",
        "https://docs.originlab.com/origin-help/grouped-column-index-data/",
        "Plot > Categorical: Grouped Columns...",
        "x_function",
        "worksheet_long_indexed",
        ("Y", "one or more Group Columns"),
        ("plot_gindexed output", "Subset groups", "category order"),
        template_keys=("gcolumn",),
        binder_key="K09",
        native_plot_types=(203,),
        proof_level="manual_native_property",
        manual_gate=(
            "Origin 2024 does not expose the nested Subset depth reliably; "
            "confirm Group Columns in Plot Details."
        ),
    ),
    _r(
        "K10",
        "堆积柱状图",
        "Stacked Column Graph",
        "https://docs.originlab.com/origin-help/stack-column-graph/",
        "Plot > Bar, Pie, Area: Stacked Column",
        "graph_template",
        "worksheet_wide",
        ("categorical X", "one or more Y"),
        ("native PID 213 group", "Layer Stack.Offset=1", "StackOffset=0", "complete legend"),
        template_keys=("stack_column",),
        binder_key="K10",
        native_plot_types=(213,),
    ),
    _r(
        "K11",
        "100%堆积柱状图",
        "100% Stacked Column Graph",
        "https://docs.originlab.com/origin-help/100-stack-column-graph/",
        "Plot > Bar, Pie, Area: 100% Stacked Column",
        "graph_template",
        "worksheet_wide",
        ("categorical X", "one or more Y"),
        (
            "native PID 213 group",
            "Layer Stack.Offset=1",
            "StackOffset=1",
            "Y maximum=100",
            "complete legend",
        ),
        template_keys=("percent_stack_column",),
        binder_key="K11",
        native_plot_types=(213,),
    ),
    _r(
        "K12",
        "列散点图（条带图）",
        "Column Scatter",
        "https://docs.originlab.com/origin-help/column-scatter/",
        "Plot > Basic 2D: Column Scatter",
        "graph_template",
        "worksheet_wide",
        ("one raw-observation Y per group",),
        (
            "raw observations unchanged",
            "all source designation codes=1",
            "one native PID 206 per source Y",
            "ordered source-Y binding",
        ),
        template_keys=("column_scatter",),
        binder_key="K12",
        native_plot_types=(206,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Box Type=Data and Jitter Points in Plot Details; "
            "stable automation readback is unavailable."
        ),
    ),
    _r(
        "K13",
        "箱线图",
        "Box Chart Graph",
        "https://docs.originlab.com/origin-help/boxchart-graph/",
        "Plot > Statistical: Box Chart",
        "graph_template",
        "worksheet_wide",
        ("one raw-observation Y per group",),
        (
            "raw observations unchanged",
            "all source designation codes=1",
            "native PID 206 source binding",
            "Box Range=25/75",
            "Whisker Range=Outlier",
            "coefficient=1.5",
            "outlier membership matches the frozen Tukey calculation",
        ),
        template_keys=("box",),
        binder_key="K13",
        native_plot_types=(206,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Whisker Range=Outlier and coefficient=1.5; "
            "the bare BOX template can otherwise remain 5/95."
        ),
    ),
    _r(
        "K14",
        "小提琴图",
        "Violin Plot",
        "https://docs.originlab.com/origin-help/violin-plot/",
        "Plot > Statistical: Violin Plot",
        "graph_template",
        "worksheet_wide",
        ("one raw-observation Y per group",),
        (
            "raw observations unchanged",
            "all source designation codes=1",
            "one native PID 206 per source Y",
            "ordered source-Y binding",
            "Curve Type=Kernel Smooth",
            "custom bandwidth matches the shared frozen geometry",
            "Extend=0",
            "symmetric distribution enabled",
            "Scale=Width",
        ),
        template_keys=("violin",),
        binder_key="K14",
        native_plot_types=(206,),
        proof_level="manual_native_property",
        manual_gate="Confirm bandwidth, extend, scale and symmetric state in Plot Details.",
    ),
    _r(
        "K15",
        "直方图",
        "Histogram",
        "https://docs.originlab.com/origin-help/histogram-graph/",
        "Plot > Statistical: Histogram",
        "graph_template",
        "worksheet_wide",
        ("raw observation Y",),
        (
            "one raw Y column unchanged",
            "designation code=1",
            "one native PID 219",
            "ordered raw source binding",
            "bin begin/end/size/count match frozen histogram geometry",
            "Data Height=Count",
        ),
        template_keys=("hist",),
        binder_key="K15",
        native_plot_types=(219,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Data Height=Count and that native bin edges/counts match the "
            "shared frozen histogram geometry; PID 219 and raw source alone are insufficient."
        ),
    ),
    _r(
        "K18",
        "面积图",
        "Area Graph",
        "https://docs.originlab.com/origin-help/area-graph/",
        "Plot > Basic 2D: Area",
        "graph_template",
        "worksheet_xy",
        ("X", "one or more Y"),
        ("native area plots", "source binding"),
        template_keys=("area",),
        binder_key="K18",
        native_plot_types=(204,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Fill Area Under Curve uses the intended From Y value; "
            "the exact enum is not exposed reliably."
        ),
    ),
    _r(
        "K19",
        "日期时间折线图",
        "Line Graph with date/time X",
        "https://docs.originlab.com/origin-help/line-graph/",
        "Plot > Basic 2D: Line",
        "graph_template",
        "worksheet_xy",
        ("numeric Date/Time X", "one or more Y"),
        ("native line", "worksheet Date format", "X tick label type=Date/Time"),
        template_keys=("line",),
        binder_key="K19",
        native_plot_types=(200,),
    ),
    _r(
        "K20",
        "热图",
        "Heatmap",
        "https://docs.originlab.com/origin-help/heat_map/",
        "Plot > Contour: Heatmap",
        "graph_template",
        "matrix",
        ("matrix Z", "X/Y mapping"),
        ("matrix source", "native heatmap", "Color Scale"),
        template_keys=("heatmap",),
        binder_key="K20",
        native_plot_types=(105,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Fill to Grid Lines and the native heatmap enumeration in Plot Details."
        ),
    ),
    _r(
        "K21",
        "带标签热图（给定相关矩阵）",
        "Heatmap with Labels",
        "https://docs.originlab.com/origin-help/heatmap-labels/",
        "Plot > Contour: Heatmap with Labels",
        "graph_template",
        "matrix",
        ("supplied matrix Z", "row/column labels"),
        ("matrix source", "native heatmap", "labels bound to Z"),
        template_keys=("heatmap_labels",),
        binder_key="K21",
        native_plot_types=(105,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Label Source=Z; Origin 2024 automation does not expose this field reliably."
        ),
    ),
    _r(
        "K22",
        "填色等高线图",
        "Color Fill Contour",
        "https://docs.originlab.com/origin-help/colorfill-contour-graph/",
        "Plot > Contour, Heatmap: Contour - Color Fill",
        "graph_template",
        "matrix",
        ("regular matrix Z", "X/Y mapping"),
        ("matrix source", "native contour", "levels", "Color Scale", "axis ratio"),
        template_keys=("contour",),
        binder_key="K22",
        native_plot_types=(226,),
        proof_level="manual_native_property",
        manual_gate="Confirm contour levels and Link Axis Length to Scale X:Y in Plot Details.",
    ),
    _r(
        "K24",
        "Trellis分面图",
        "Trellis Plot",
        "https://docs.originlab.com/origin-help/trellis/",
        "Plot > Categorical > Trellis Plot",
        "x_function",
        "worksheet_long_indexed",
        ("X", "Y", "Group Columns"),
        ("plot_group output", "single-layer Trellis panels", "group/source binding"),
        template_keys=("grouped",),
        binder_key="K24",
        native_plot_types=(202,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Trellis panel properties; GraphLayer_GetDataPlots is unstable "
            "for this template in Origin 2024."
        ),
    ),
    _r(
        "S34",
        "Nyquist图",
        "Nyquist Plot",
        "https://cloud.originlab.com/fileexchange/index.aspx?C=0",
        "Origin 2024: Plot > Basic 2D > Line+Symbol",
        "graph_template",
        "worksheet_xy",
        ("Z real X", "negative Z imaginary Y", "optional frequency metadata"),
        ("one native line-symbol plot", "X/Y source binding", "frequency excluded from plot"),
        template_keys=("linesymb",),
        binder_key="S34",
        native_plot_types=(202,),
    ),
    _r(
        "S61",
        "带标签热图（混淆矩阵语义）",
        "Heatmap with Labels",
        "https://docs.originlab.com/origin-help/heatmap-labels/",
        "Plot > Contour: Heatmap with Labels",
        "graph_template",
        "matrix",
        ("precomputed confusion-count matrix",),
        ("native labeled heatmap", "labels bound to Z"),
        template_keys=("heatmap_labels",),
        binder_key="S61",
        native_plot_types=(105,),
    ),
    _r(
        "X02",
        "垂线图",
        "Vertical Drop Line",
        "https://docs.originlab.com/origin-help/vertical-drop-line/",
        "Plot > Basic 2D > Vertical Drop Line",
        "graph_template",
        "worksheet_xy",
        ("X", "Y"),
        ("native plot type 201", "vertical drop lines", "drop target"),
        template_keys=("dropline",),
        binder_key="X02",
        native_plot_types=(201,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Drop To=Auto/Axis Begin in Plot Details; "
            "the exact enum is not stable through OriginExt."
        ),
    ),
    _r(
        "X03",
        "棒棒糖图",
        "Lollipop Plot",
        "https://docs.originlab.com/origin-help/lollipop-plot/",
        "Plot > Basic 2D > Lollipop Plot",
        "graph_template",
        "worksheet_wide",
        ("optional X", "two or more Y"),
        ("native lollipop group", "axes exchanged", "Drop target=Follow Plot(1)"),
        template_keys=("lollipop",),
        binder_key="X03",
        native_plot_types=(201,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm the Lollipop group and Follow Plot(1); "
            "GraphLayer_GetDataPlots is unstable in Origin 2024."
        ),
    ),
    _r(
        "X05",
        "蜂群图",
        "Beeswarm Plot",
        "https://docs.originlab.com/origin-help/beeswarm-plot/",
        "Plot > Statistical > Beeswarm Plot",
        "graph_template",
        "worksheet_wide",
        ("one Y per group",),
        ("native data plots", "Arrange Points=Swarm", "source columns"),
        template_keys=("beeswarm",),
        binder_key="X05",
        native_plot_types=(206,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Arrange Points=Swarm in Plot Details; the property has no stable readback."
        ),
    ),
    _r(
        "X09",
        "浮动柱状图",
        "Floating Column Graph",
        "https://docs.originlab.com/origin-help/floating-column-graph/",
        "Plot > Bar Pie Area > Floating Column",
        "graph_template",
        "worksheet_wide",
        ("optional X", "start Y", "optional middle Y", "end Y"),
        (
            "native floating-column plot",
            "ordered adjacent boundary binding",
            "category source",
            "vertical column direction",
        ),
        template_keys=("floatcol",),
        binder_key="X09",
        native_plot_types=(207,),
        proof_level="proven_native_structure",
    ),
    _r(
        "X13",
        "人口金字塔（龙卷风/蝴蝶图）",
        "Population Pyramid Graph (Tornado Chart)",
        "https://docs.originlab.com/origin-help/population-pyramid-graph/",
        "Plot > Statistical > Population Pyramid",
        "graph_template",
        "worksheet_wide",
        ("categorical X", "left Y", "right Y"),
        (
            "exactly two native template layers",
            "one native column plot per layer",
            "both plots bind the category X source",
            "left/right Y bind source columns B/C",
            "template horizontal orientation",
            "zero plot offsets and unit plot scales",
        ),
        template_keys=("population",),
        binder_key="X13",
        native_plot_types=(203, 203),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm both PID 203 plots, Display/ExchangeXY, exact layer-2 link modes, "
            "X/Y source ranges and reopen stability."
        ),
    ),
    _r(
        "X23",
        "双Y轴Y-Y图",
        "2Ys Y-Y Graph",
        "https://docs.originlab.com/origin-help/2ys-y-y-graph/",
        "Plot > Multi-Panel/Axis > 2Ys Y-Y",
        "graph_template",
        "worksheet_wide",
        ("shared X", "left Y", "right Y"),
        (
            "exactly two native template layers",
            "one native line-symbol plot per layer",
            "both plots bind the shared X source",
            "left/right Y bind source columns B/C",
            "layer 2 has a straight 1:1 X link to layer 1",
            "independent left and right Y scales",
            "zero plot offsets and unit plot scales",
        ),
        template_keys=("doubley",),
        binder_key="X23",
        native_plot_types=(202, 202),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm both PID 202 plots, line+symbol visibility, exact X link, "
            "independent Y scales, source ranges and reopen stability."
        ),
    ),
    _r(
        "X24",
        "帕累托图（分箱数据）",
        "Pareto Chart - Binned Data",
        "https://docs.originlab.com/origin-help/paretochart-bindata/",
        "Plot > Statistical > Pareto > Binned Data",
        "x_function",
        "worksheet_xy",
        ("category", "count"),
        (
            "plot_paretobin output",
            "descending counts",
            "cumulative percent ends at 100",
            "right axis",
        ),
        template_keys=("paretobin",),
        binder_key="X24",
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm sorting, right axis, cumulative 100% and threshold "
            "in the native Pareto output."
        ),
    ),
    _r(
        "X35",
        "双Y轴柱状图",
        "2Ys Column",
        "https://docs.originlab.com/origin-help/2ys-column-graph/",
        "Plot > Multi-Panel/Axis > 2Ys Column",
        "graph_template",
        "worksheet_wide",
        ("optional X", "left Y", "right Y"),
        (
            "two native layers",
            "one native column per layer",
            "zero-baseline columns",
            "independent Y axes",
        ),
        template_keys=("two_y_column",),
        binder_key="X35",
        native_plot_types=(203,),
    ),
    _r(
        "X36",
        "双Y轴柱线图",
        "2Ys Column-Line Symbol",
        "https://docs.originlab.com/origin-help/2ys-column-linesym-graph/",
        "Plot > Multi-Panel/Axis > 2Ys Column-LineSymbol",
        "graph_template",
        "worksheet_wide",
        ("optional X", "left column Y", "right line-symbol Y"),
        ("two native layers", "native column", "native line-symbol", "independent Y axes"),
        template_keys=("two_y_column_symbol",),
        binder_key="X36",
        native_plot_types=(203, 202),
    ),
    _r(
        "X38",
        "Y偏移堆叠线图",
        "Stacked Lines by Y Offsets",
        "https://docs.originlab.com/origin-help/stacklineyoffset-graph",
        "Plot > Basic 2D > Stacked Lines by Y Offsets",
        "graph_template",
        "worksheet_wide",
        ("optional X", "two or more Y"),
        ("native line plots", "original unshifted Y", "display offset"),
        template_keys=("offset_y",),
        binder_key="X38",
        native_plot_types=(200,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm Individual Y Offset in Plot Details; "
            "the native offset theme is not exposed reliably."
        ),
    ),
    _r(
        "X39",
        "线条序列图",
        "Line Series Graph",
        "https://docs.originlab.com/origin-help/line-series-graph/",
        "Plot > Basic 2D > Line Series",
        "graph_template",
        "worksheet_wide",
        (
            "optional N row label retained as unselected metadata",
            "Y series_1",
            "Y series_2",
            "repeatable Y series_3..series_N; source rows remain rows",
        ),
        (
            "PID 206 native BoxChart plot group",
            "native member count equals selected Y-column count",
            "source rows, values, Long Name and Comments survive unchanged",
            "Connect Data Points joins equal-row values across selected columns",
            "no hidden or transposed worksheet",
        ),
        template_keys=("box_line_series",),
        binder_key="X39",
        native_plot_types=(206,),
        proof_level="manual_native_property",
        manual_gate=(
            "After fresh reopen confirm Plot Details > Connect Lines > Connect Data Points "
            "and one connector per source row; the BoxChart connector flag has no stable "
            "documented LabTalk readback."
        ),
    ),
    _r(
        "X40",
        "前后对比图",
        "Before and After Graph",
        "https://docs.originlab.com/origin-help/before-after-graph/",
        "Plot > Basic 2D > Before - After",
        "graph_template",
        "worksheet_wide",
        (
            "optional N subject label retained as unselected metadata",
            "Y Before",
            "Y After",
            "fig-agent supported subset: exactly one adjacent Y-column pair",
        ),
        (
            "PID 206 native BoxChart plot group",
            "Subgroup By Size equals 2",
            "column-label subgrouping is disabled and does not override size",
            "source rows and adjacent Before/After columns survive unchanged",
            "Connect Data Points is restricted to the adjacent pair",
            "no per-subject transpose",
        ),
        template_keys=("before_after",),
        binder_key="X40",
        native_plot_types=(206,),
        proof_level="manual_native_property",
        manual_gate=(
            "After fresh reopen compare subgroup properties with the official BeforeAfter "
            "sample, then confirm Connect Data Points within Subgroup in Plot Details."
        ),
    ),
)

if len({recipe.profile_id for recipe in _RECIPES}) != len(_RECIPES):
    raise RuntimeError("Origin recipe profile ids must be unique")
if set(_LOCAL_DISPATCH) != {str(recipe.profile_id) for recipe in _RECIPES}:
    raise RuntimeError("Origin local dispatcher evidence must cover the exact recipe catalog")

ORIGIN_RECIPES: Mapping[ChartTypeId, OriginRecipe] = MappingProxyType(
    {recipe.profile_id: recipe for recipe in _RECIPES}
)
ORIGIN_RENDERABLE_RECIPES: Mapping[ChartTypeId, OriginRecipe] = MappingProxyType(
    {
        profile_id: recipe
        for profile_id, recipe in ORIGIN_RECIPES.items()
        if recipe.support_status == "renderable"
    }
)


def origin_recipe(profile_id: str, *, require_renderable: bool = True) -> OriginRecipe:
    """Return the closed recipe or reject an unsupported Origin profile."""

    try:
        recipe = ORIGIN_RECIPES[profile_id]  # type: ignore[index]
    except KeyError as error:
        raise ValueError(f"Origin has no recipe for profile {profile_id}") from error
    if require_renderable and recipe.support_status != "renderable":
        reason = recipe.manual_gate or recipe.support_status
        raise ValueError(f"Origin profile {profile_id} is {recipe.support_status}: {reason}")
    return recipe
