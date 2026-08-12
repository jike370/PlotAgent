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
    "composition",
    "app",
]
OriginSourceLayout = Literal[
    "worksheet_xy",
    "worksheet_wide",
    "worksheet_long_indexed",
    "matrix",
    "analysis_table",
    "plot_components",
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
    "recompose_components",
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
    creation_kind: OriginCreationKind
    binder_key: Token | None
    templates: tuple[OriginTemplateIdentity, ...] = ()
    source_layout: OriginSourceLayout
    designation_contract: tuple[_NonEmpty, ...]
    rebuild_policy: OriginRebuildPolicy
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
    "histdist": _template(
        "HISTDIST.otpu", "a584e2ee70fa332c592cce714a0339e31e3a7d937889d3096f37722b7fcd50e7"
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
    "floatbar": _template(
        "FloatBar.otp", "7fd8331a4f91170ce7a7b35428659e48b985fc6ce8164c706ea31b4e41dee93b"
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
        creation_kind=kind,
        binder_key=binder_key,
        templates=templates,
        source_layout=source_layout,
        designation_contract=designation,
        rebuild_policy=rebuild_policy,
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
        native_plot_types=(248,),
    ),
    _r(
        "K06",
        "XY双向误差棒图",
        "XY Error Bar Graph",
        "https://docs.originlab.com/origin-help/xy-errbar-graph/",
        "Plot > Basic 2D: XY Error",
        "graph_template",
        "worksheet_xy",
        ("X", "Y", "X error", "Y error"),
        ("horizontal ErrorBar2D", "vertical ErrorBar2D", "cap width"),
        template_keys=("errorbar",),
        binder_key="K06",
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
        ("one Y per group",),
        ("one native data plot per group", "source columns"),
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
        ("one Y per group",),
        ("native box plots", "source columns"),
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
        ("one Y per group",),
        ("native violin plots", "Kernel Smooth distribution", "source columns"),
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
        "worksheet_xy",
        ("raw observation Y",),
        ("native histogram computation", "raw source binding", "plot type 219"),
        template_keys=("hist",),
        binder_key="K15",
        native_plot_types=(219,),
    ),
    _r(
        "K16",
        "一维核密度图",
        "1D Kernel Density Workflow",
        "https://docs.originlab.com/quick-help/kernel_density_graph/",
        "Histogram > Distribution > Kernel Smooth > Hide Bins",
        "graph_template",
        "worksheet_wide",
        ("raw observation Y",),
        ("Kernel Smooth", "bins hidden after reopen"),
        template_keys=("histdist",),
        support_status="structural_fail",
        proof_level="blocked",
        manual_gate=(
            "Observed Origin 2024 projects restore visible histogram bins; "
            "current output is not a pure KDE."
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
        ("numeric Date/Time X", "Y"),
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
        "K25",
        "多面板组合图",
        "Merge Graph Windows",
        "https://docs.originlab.com/origin-help/multipanel-graph/",
        "Graph > Merge Graph Windows",
        "composition",
        "plot_components",
        ("two to four immutable PlotDocument components",),
        ("component graph identity", "native merged layers", "no rasterized subplots"),
        binder_key="K25",
        rebuild_policy="recompose_components",
    ),
    _r(
        "S01",
        "Kaplan-Meier生存曲线",
        "Kaplan-Meier Estimator",
        "https://docs.originlab.com/origin-help/kaplanmeier-estimator/",
        "Statistics > Survival Analysis > Kaplan-Meier Estimator",
        "analysis",
        "analysis_table",
        ("Time", "Censor", "optional Group"),
        (
            "kaplanmeier report table",
            "analysis lock/input binding",
            "native survival graph",
            "censor marks",
        ),
        binder_key="S01",
        rebuild_policy="recompute_analysis",
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm analysis-lock source dependency and group categorical state; "
            "Origin 2024 does not support plot-in-one with sfci simultaneously."
        ),
    ),
    _r(
        "S21",
        "森林图",
        "Forest Plot",
        "https://cloud.originlab.com/fileexchange/index.aspx?fid=362",
        "Apps Gallery > Forest Plot App",
        "app",
        "worksheet_xy",
        ("effect", "lower CI", "upper CI", "optional weight/label"),
        ("official Forest Plot App output",),
        support_status="dependency_blocked",
        proof_level="blocked",
        manual_gate=(
            "The official Forest Plot App is not installed/proven; "
            "primitive error-bar fallbacks are forbidden."
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
        "浮动条形图",
        "Floating Bar Graph",
        "https://docs.originlab.com/origin-help/floating-bar-graph/",
        "Plot > Bar Pie Area > Floating Bar",
        "graph_template",
        "worksheet_wide",
        ("optional X", "start Y", "optional middle Y", "end Y"),
        (
            "native floating-bar plot",
            "ordered adjacent boundary binding",
            "category source",
            "exchanged XY direction",
        ),
        template_keys=("floatbar",),
        binder_key="X09",
        native_plot_types=(207,),
        proof_level="proven_native_structure",
    ),
    _r(
        "X13",
        "人口金字塔（龙卷风/蝴蝶图）",
        "Population Pyramid Graph",
        "https://docs.originlab.com/origin-help/population-pyramid-graph/",
        "Plot > Statistical > Population Pyramid",
        "graph_template",
        "worksheet_wide",
        ("category label", "left Y", "right Y"),
        ("two template layers", "shared category axis", "native horizontal columns"),
        template_keys=("population",),
        binder_key="X13",
        proof_level="manual_native_property",
        manual_gate=(
            "Compare the shared category designation with the official sample; "
            "the help page does not specify it fully."
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
        ("X/left Y/right Y or XYXY",),
        ("two native layers", "one native line per layer", "independent Y axes", "X link policy"),
        template_keys=("doubley",),
        binder_key="X23",
        native_plot_types=(200,),
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
        ("two or more numeric columns", "each source row is one series"),
        ("native BoxChart line-series object", "row-wise connection", "source Long Name/Comments"),
        template_keys=("box_line_series",),
        binder_key="X39",
        native_plot_types=(206,),
        proof_level="manual_native_property",
        manual_gate=(
            "Confirm row-wise BoxLser structure and Long Name/Comments mapping in Plot Details."
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
        ("Before", "After", "each source row is one pair"),
        ("native BoxChart before-after object", "Subgroup Size=2", "row-wise source binding"),
        template_keys=("before_after",),
        binder_key="X40",
        native_plot_types=(206,),
        proof_level="manual_native_property",
        manual_gate="Confirm Subgroup Size=2 and row-wise binding in Plot Details.",
    ),
)

if len({recipe.profile_id for recipe in _RECIPES}) != len(_RECIPES):
    raise RuntimeError("Origin recipe profile ids must be unique")

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
