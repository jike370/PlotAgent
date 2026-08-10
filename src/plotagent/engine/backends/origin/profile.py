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

K18_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K18",
    filename="AREA.otpu",
    sha256="c14ad432ffd60db09f6763b7b988de4aa554dcf0d9772b18334970fb83eddaec",
    tier="T1",
)

K20_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K20",
    filename="Heat_Map.otpu",
    sha256="9bd8240ca582bbedfec797ea27b1ec5c2906939e304fa343cd1821bae2ffbb9f",
    tier="T1",
)

X23_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X23",
    filename="DOUBLEY.OTP",
    sha256="487547eb206e4645f3380a9a021ceb7fbcf4ec4d1fdb0a870d1eb0cde0c7641b",
    tier="T1",
)

X02_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="X02",
    filename="DROPLINE.OTP",
    sha256="69cbcf9349249092e2e32c8955c88c0a265ac47a46811885593d9eced643299f",
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
