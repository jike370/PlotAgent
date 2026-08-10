"""Flat per-chart engine profiles for the 38-chart template-first product surface."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from plotagent.contracts.base import ChartTypeId, StrictModel
from plotagent.contracts.registry import CHARTS_BY_ID, PRODUCT_CHART_IDS, EditCapability

TemplateTier = Literal["T1", "T2"]
BareTemplateStatus = Literal["pending", "AUTO", "DECLARED_PATCH", "REMOVE_OR_RECLASSIFY"]

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]
EntryPoint = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{2,127}$", strict=True),
]
TemplateFilename = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9_. -]+\.[Oo][Tt][Pp][Uu]?$", strict=True),
]


class OriginOfficialTemplateProfile(StrictModel):
    filename: TemplateFilename
    sha256: Sha256
    tier: TemplateTier
    binder_id: EntryPoint
    declared_patch_ids: tuple[EntryPoint, ...] = ()
    bare_template_status: BareTemplateStatus = "pending"

    @model_validator(mode="after")
    def tier_and_patch_are_consistent(self) -> OriginOfficialTemplateProfile:
        if self.tier == "T1" and self.declared_patch_ids:
            raise ValueError("T1 template profiles cannot declare native patches")
        if self.tier == "T2" and not self.declared_patch_ids:
            raise ValueError("T2 template profiles require at least one declared patch")
        if self.bare_template_status == "AUTO" and self.declared_patch_ids:
            raise ValueError("AUTO profiles cannot retain a declared patch")
        return self


class ChartProfile(StrictModel):
    chart_type_id: ChartTypeId
    profile_version: Literal["engine-profile.v1"] = "engine-profile.v1"
    required_roles: tuple[str, ...]
    optional_roles: tuple[str, ...]
    repeatable_roles: tuple[str, ...]
    edit_capabilities: tuple[EditCapability, ...]
    matplotlib_renderer_id: EntryPoint
    origin: OriginOfficialTemplateProfile


class ChartProfileRegistry(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    profiles: Annotated[tuple[ChartProfile, ...], Field(min_length=38, max_length=38)]

    @model_validator(mode="after")
    def exact_product_surface(self) -> ChartProfileRegistry:
        ids = tuple(profile.chart_type_id for profile in self.profiles)
        if len(set(ids)) != len(ids):
            raise ValueError("chart profile ids must be unique")
        if set(ids) != set(PRODUCT_CHART_IDS):
            raise ValueError("chart profiles must exactly match the 38-chart product surface")
        return self


# filename, sha256, tier, binder suffix, declared T2 patches
_ENGINE_PROFILE_ROWS: dict[
    ChartTypeId,
    tuple[str, str, TemplateTier, str, tuple[str, ...]],
] = {
    "K01": (
        "LINE.otpu",
        "76a7ce886e2290d29444ac3a92c736a2057d2583aea8867091db439cb23dc648",
        "T1",
        "line",
        (),
    ),
    "K02": (
        "LINESYMB.otpu",
        "2f1292a939eac92cd0dc820309885caccfa53293d1db78d18447a5b5b329fed1",
        "T1",
        "line_symbol",
        (),
    ),
    "K03": (
        "SCATTER.OTP",
        "efef85d7c3db5028c565a57e15c86f97d6ebeded6d779c1cdb11328a7fbd4a99",
        "T1",
        "scatter",
        (),
    ),
    "K04": (
        "bubble.otpu",
        "abc20768493ef817b567bd3e58bb0c3da1a8ec59c56f0d1b92c2341479560b44",
        "T2",
        "bubble",
        ("color_scale_visibility",),
    ),
    "K06": (
        "ERRBAR.otpu",
        "c17ebd8f68f8585c3bb4c431e75f4dc1724e3f54ee1fd7d0977b6cadcf1c599b",
        "T1",
        "point_error",
        (),
    ),
    "K07": (
        "ERRORBAND.otp",
        "dfd36bf19bf3cf81bebd7d2b7d04a0ef05f07f90243678ddf3d03eded342c763",
        "T1",
        "error_band",
        (),
    ),
    "K08": (
        "COLUMN.otpu",
        "ec9e654e886056a466c3447afeab950d371ac6f297d5e325b25e99b7a3d769cd",
        "T1",
        "column",
        (),
    ),
    "K09": (
        "COLUMN.otpu",
        "ec9e654e886056a466c3447afeab950d371ac6f297d5e325b25e99b7a3d769cd",
        "T2",
        "grouped_column",
        ("dynamic_plot_group",),
    ),
    "K10": (
        "STACKCOLUMN.otp",
        "3ffd84ea777e414c60daab6e3b162b207379b94341ef1497c144a725f0caa264",
        "T1",
        "stacked_column",
        (),
    ),
    "K11": (
        "StackColP.otp",
        "2094be00706be51883e7d5f8212e79e5eb1ac01ff66af45ba4953761ba8fe7d3",
        "T1",
        "percent_stack",
        (),
    ),
    "K12": (
        "ColumnScatter.otp",
        "e9bfbf3b74bc78db041208505bf1c1b32b387378cc8aac91462d017a662c425d",
        "T2",
        "strip",
        ("long_table_grouping",),
    ),
    "K13": (
        "BOX.OTP",
        "a1f26e68a6a070aba0769905c6b143766a51abd0d7e6039ad93de49ab600daaa",
        "T1",
        "box",
        (),
    ),
    "K14": (
        "Violin.otpu",
        "ee71ef5fb2bf15cfc403444494f1779999df31d43c0a3e24001cb35b838bc1eb",
        "T1",
        "violin",
        (),
    ),
    "K15": (
        "Hist.otpu",
        "cc1d7edd9f07f8bb0e1b0fe6f9ea0f36439afa912d209efc29329df9c2f00cfa",
        "T1",
        "histogram",
        (),
    ),
    "K16": (
        "HISTDIST.otpu",
        "a584e2ee70fa332c592cce714a0339e31e3a7d937889d3096f37722b7fcd50e7",
        "T2",
        "density",
        ("density_component_visibility",),
    ),
    "K18": (
        "AREA.otpu",
        "c14ad432ffd60db09f6763b7b988de4aa554dcf0d9772b18334970fb83eddaec",
        "T1",
        "area",
        (),
    ),
    "K19": (
        "TimeSeries.otp",
        "ebe487cd9626437e522ae82e6fc302a280110bed4b26564984d4b0263eeb660c",
        "T1",
        "time_series",
        (),
    ),
    "K20": (
        "Heat_Map.otpu",
        "9bd8240ca582bbedfec797ea27b1ec5c2906939e304fa343cd1821bae2ffbb9f",
        "T1",
        "heatmap",
        (),
    ),
    "K21": (
        "Heat_Map_With_Labels.otpu",
        "d1a7fcd8af232aef9ca348eb178466a13a744eb700da7d49d39cfbe16c935c7d",
        "T1",
        "correlation_matrix",
        (),
    ),
    "K22": (
        "CONTOUR.otpu",
        "b4915054edd419955245e485b606784dbb6b4965dd6359b45603e00a866628e2",
        "T1",
        "contour",
        (),
    ),
    "K24": (
        "mgroups.otpu",
        "391e5689e8f5436f029099086a9e65b50679606120275a6a958417d235f1dd9b",
        "T2",
        "facet",
        ("dynamic_facet_layers",),
    ),
    "K25": (
        "mgroups.otpu",
        "391e5689e8f5436f029099086a9e65b50679606120275a6a958417d235f1dd9b",
        "T2",
        "multi_panel",
        ("native_panel_composition",),
    ),
    "S01": (
        "SurvivalPlot.otp",
        "0b8759367ce19f1a82cfb9630ffefd849e0c600bce1e909985645c0a47de046b",
        "T2",
        "survival",
        ("risk_table_and_step_band",),
    ),
    "S21": (
        "SCATTERINTERVAL.otp",
        "fb319b1a6918427767373917ddda2cc5b95a88d9d295ff06e866762b955dd161",
        "T2",
        "forest",
        ("interval_weight_encoding",),
    ),
    "S34": (
        "LINESYMB.otpu",
        "2f1292a939eac92cd0dc820309885caccfa53293d1db78d18447a5b5b329fed1",
        "T2",
        "nyquist",
        ("equal_axis_and_direction_encoding",),
    ),
    "S61": (
        "Heat_Map_With_Labels.otpu",
        "d1a7fcd8af232aef9ca348eb178466a13a744eb700da7d49d39cfbe16c935c7d",
        "T2",
        "confusion_matrix",
        ("matrix_count_labels",),
    ),
    "X02": (
        "DROPLINE.OTP",
        "69cbcf9349249092e2e32c8955c88c0a265ac47a46811885593d9eced643299f",
        "T1",
        "drop_line",
        (),
    ),
    "X03": (
        "Lollipop.otpu",
        "f76fc89b9438947bbcd601b53e03cf16732a931621143b469233e584f88ba58b",
        "T1",
        "lollipop",
        (),
    ),
    "X05": (
        "ColumnScatter.otp",
        "e9bfbf3b74bc78db041208505bf1c1b32b387378cc8aac91462d017a662c425d",
        "T1",
        "beeswarm",
        (),
    ),
    "X09": (
        "FLOATBAR.OTP",
        "7fd8331a4f91170ce7a7b35428659e48b985fc6ce8164c706ea31b4e41dee93b",
        "T1",
        "floating_interval",
        (),
    ),
    "X13": (
        "PopulationPyramid.otpu",
        "2c5958a91130d62cf8a6708f197bfd6248a3b22d81fc68eed1abe5f10988fbab",
        "T1",
        "population_pyramid",
        (),
    ),
    "X23": (
        "DOUBLEY.OTP",
        "487547eb206e4645f3380a9a021ceb7fbcf4ec4d1fdb0a870d1eb0cde0c7641b",
        "T1",
        "dual_y_line",
        (),
    ),
    "X24": (
        "ParetoRaw.otpu",
        "5f273e70f87c2e22d230417b35907c2524dc293476070e74312f872a7ff00a7b",
        "T1",
        "pareto",
        (),
    ),
    "X35": (
        "2Ys_Col.otpu",
        "cba0737aaa4c2ab24a62062cfe37c095c5651d9048519b3fc2a3e9ccaa058ca9",
        "T1",
        "dual_y_column",
        (),
    ),
    "X36": (
        "2Ys_ColSymb.otpu",
        "6e951a3dd1f08cb2122cac48ce37476eef54d54c9fb424211e9fce39c677e1ab",
        "T1",
        "dual_y_column_line",
        (),
    ),
    "X38": (
        "OffsetStackY.otp",
        "c6d7548cf7389e5d53282c6d1873aa2e8e184de96ae54d2cd71937f0a56d98d3",
        "T1",
        "offset_stack_y",
        (),
    ),
    "X39": (
        "BoxLser.otpu",
        "8396fd58435c4ded363b889d7eb3c8cf8a3b22e82eb539e8cc85f6b58481ec83",
        "T1",
        "line_series",
        (),
    ),
    "X40": (
        "BeforeAfter.otpu",
        "d37a1c2949696f29cd2a2fcf856a2c8b5f8be29e8ab040a83a9c2c9f0e262c0b",
        "T1",
        "before_after",
        (),
    ),
}

_REPEATABLE_ROLES: dict[ChartTypeId, tuple[str, ...]] = {
    "X03": ("series_N",),
    "X39": ("series_N",),
    "X40": ("series_N",),
}


def _build_profile(chart_type_id: ChartTypeId) -> ChartProfile:
    chart = CHARTS_BY_ID[chart_type_id]
    filename, sha256, tier, binder, patches = _ENGINE_PROFILE_ROWS[chart_type_id]
    return ChartProfile(
        chart_type_id=chart_type_id,
        required_roles=chart.required_roles,
        optional_roles=chart.optional_roles,
        repeatable_roles=_REPEATABLE_ROLES.get(chart_type_id, ()),
        edit_capabilities=chart.edit_capabilities,
        matplotlib_renderer_id=f"plotagent.matplotlib.{chart_type_id.lower()}",
        origin=OriginOfficialTemplateProfile(
            filename=filename,
            sha256=sha256,
            tier=tier,
            binder_id=f"plotagent.origin.template.{binder}",
            declared_patch_ids=patches,
        ),
    )


CHART_PROFILES: tuple[ChartProfile, ...] = tuple(
    _build_profile(chart_type_id) for chart_type_id in PRODUCT_CHART_IDS
)
CHART_PROFILES_BY_ID: dict[ChartTypeId, ChartProfile] = {
    profile.chart_type_id: profile for profile in CHART_PROFILES
}
V1_CHART_PROFILE_REGISTRY = ChartProfileRegistry(profiles=CHART_PROFILES)

if set(_ENGINE_PROFILE_ROWS) != set(PRODUCT_CHART_IDS):
    raise RuntimeError("engine profile rows must exactly match the 38-chart product surface")
