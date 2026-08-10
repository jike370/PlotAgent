"""Closed official-template identities for the replacement Origin backend."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from pydantic import StringConstraints

from plotagent.contracts.base import Sha256, StrictModel, Token


class OriginTemplateProfile(StrictModel):
    profile_id: Token
    filename: Annotated[
        str,
        StringConstraints(pattern=r"^[A-Za-z0-9_. -]+\.[Oo][Tt][Pp][Uu]?$", strict=True),
    ]
    sha256: Sha256
    tier: Literal["T1", "T2"]


K01_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K01",
    filename="LINE.otpu",
    sha256="76a7ce886e2290d29444ac3a92c736a2057d2583aea8867091db439cb23dc648",
    tier="T1",
)

K02_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K02",
    filename="LINESYMB.otpu",
    sha256="2f1292a939eac92cd0dc820309885caccfa53293d1db78d18447a5b5b329fed1",
    tier="T1",
)

K03_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K03",
    filename="SCATTER.OTP",
    sha256="efef85d7c3db5028c565a57e15c86f97d6ebeded6d779c1cdb11328a7fbd4a99",
    tier="T1",
)

K04_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K04",
    filename="bubble.otpu",
    sha256="abc20768493ef817b567bd3e58bb0c3da1a8ec59c56f0d1b92c2341479560b44",
    tier="T2",
)

K06_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K06",
    filename="ERRBAR.otpu",
    sha256="c17ebd8f68f8585c3bb4c431e75f4dc1724e3f54ee1fd7d0977b6cadcf1c599b",
    tier="T1",
)

K07_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K07",
    filename="ERRORBAND.otp",
    sha256="dfd36bf19bf3cf81bebd7d2b7d04a0ef05f07f90243678ddf3d03eded342c763",
    tier="T1",
)

K08_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K08",
    filename="COLUMN.otpu",
    sha256="ec9e654e886056a466c3447afeab950d371ac6f297d5e325b25e99b7a3d769cd",
    tier="T1",
)

K09_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K09",
    filename="COLUMN.otpu",
    sha256="ec9e654e886056a466c3447afeab950d371ac6f297d5e325b25e99b7a3d769cd",
    tier="T2",
)

K10_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K10",
    filename="STACKCOLUMN.otp",
    sha256="3ffd84ea777e414c60daab6e3b162b207379b94341ef1497c144a725f0caa264",
    tier="T1",
)

K11_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K11",
    filename="StackColP.otp",
    sha256="2094be00706be51883e7d5f8212e79e5eb1ac01ff66af45ba4953761ba8fe7d3",
    tier="T1",
)

K12_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K12",
    filename="ColumnScatter.otp",
    sha256="e9bfbf3b74bc78db041208505bf1c1b32b387378cc8aac91462d017a662c425d",
    tier="T2",
)

K13_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K13",
    filename="BOX.OTP",
    sha256="a1f26e68a6a070aba0769905c6b143766a51abd0d7e6039ad93de49ab600daaa",
    tier="T1",
)

K14_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K14",
    filename="Violin.otpu",
    sha256="ee71ef5fb2bf15cfc403444494f1779999df31d43c0a3e24001cb35b838bc1eb",
    tier="T1",
)

K15_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K15",
    filename="Hist.otpu",
    sha256="cc1d7edd9f07f8bb0e1b0fe6f9ea0f36439afa912d209efc29329df9c2f00cfa",
    tier="T1",
)

K16_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K16",
    filename="HISTDIST.otpu",
    sha256="a584e2ee70fa332c592cce714a0339e31e3a7d937889d3096f37722b7fcd50e7",
    tier="T2",
)

K18_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K18",
    filename="AREA.otpu",
    sha256="c14ad432ffd60db09f6763b7b988de4aa554dcf0d9772b18334970fb83eddaec",
    tier="T1",
)

K19_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K19",
    filename="TimeSeries.otp",
    sha256="ebe487cd9626437e522ae82e6fc302a280110bed4b26564984d4b0263eeb660c",
    tier="T1",
)

K20_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K20",
    filename="Heat_Map.otpu",
    sha256="9bd8240ca582bbedfec797ea27b1ec5c2906939e304fa343cd1821bae2ffbb9f",
    tier="T1",
)

K21_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K21",
    filename="Heat_Map_With_Labels.otpu",
    sha256="d1a7fcd8af232aef9ca348eb178466a13a744eb700da7d49d39cfbe16c935c7d",
    tier="T1",
)

K22_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K22",
    filename="CONTOUR.otpu",
    sha256="b4915054edd419955245e485b606784dbb6b4965dd6359b45603e00a866628e2",
    tier="T1",
)

X23_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X23",
    filename="DOUBLEY.OTP",
    sha256="487547eb206e4645f3380a9a021ceb7fbcf4ec4d1fdb0a870d1eb0cde0c7641b",
    tier="T1",
)

X24_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X24",
    filename="ParetoRaw.otpu",
    sha256="5f273e70f87c2e22d230417b35907c2524dc293476070e74312f872a7ff00a7b",
    tier="T1",
)

X35_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X35",
    filename="2Ys_Col.otpu",
    sha256="cba0737aaa4c2ab24a62062cfe37c095c5651d9048519b3fc2a3e9ccaa058ca9",
    tier="T1",
)

X36_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X36",
    filename="2Ys_ColSymb.otpu",
    sha256="6e951a3dd1f08cb2122cac48ce37476eef54d54c9fb424211e9fce39c677e1ab",
    tier="T1",
)

X38_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X38",
    filename="OffsetStackY.otp",
    sha256="c6d7548cf7389e5d53282c6d1873aa2e8e184de96ae54d2cd71937f0a56d98d3",
    tier="T1",
)

X02_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X02",
    filename="DROPLINE.OTP",
    sha256="69cbcf9349249092e2e32c8955c88c0a265ac47a46811885593d9eced643299f",
    tier="T1",
)

X03_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X03",
    filename="Lollipop.otpu",
    sha256="f76fc89b9438947bbcd601b53e03cf16732a931621143b469233e584f88ba58b",
    tier="T1",
)

X05_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X05",
    filename="ColumnScatter.otp",
    sha256="e9bfbf3b74bc78db041208505bf1c1b32b387378cc8aac91462d017a662c425d",
    tier="T1",
)

X09_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X09",
    filename="FLOATBAR.OTP",
    sha256="7fd8331a4f91170ce7a7b35428659e48b985fc6ce8164c706ea31b4e41dee93b",
    tier="T1",
)

X13_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X13",
    filename="PopulationPyramid.otpu",
    sha256="2c5958a91130d62cf8a6708f197bfd6248a3b22d81fc68eed1abe5f10988fbab",
    tier="T1",
)

X39_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X39",
    filename="BoxLser.otpu",
    sha256="8396fd58435c4ded363b889d7eb3c8cf8a3b22e82eb539e8cc85f6b58481ec83",
    tier="T1",
)

X40_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X40",
    filename="BeforeAfter.otpu",
    sha256="d37a1c2949696f29cd2a2fcf856a2c8b5f8be29e8ab040a83a9c2c9f0e262c0b",
    tier="T1",
)


def resolve_official_template(
    install_dir: Path,
    profile: OriginTemplateProfile,
) -> Path:
    root = install_dir.resolve()
    template = (root / profile.filename).resolve()
    if template.parent != root:
        raise ValueError("official Origin template escaped the configured install directory")
    if not template.is_file():
        raise FileNotFoundError(f"official Origin template is missing: {profile.filename}")
    if sha256(template.read_bytes()).hexdigest() != profile.sha256:
        raise ValueError(f"official Origin template hash differs: {profile.filename}")
    return template
