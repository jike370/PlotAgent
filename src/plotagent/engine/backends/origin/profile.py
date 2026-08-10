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

K08_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K08",
    filename="COLUMN.otpu",
    sha256="ec9e654e886056a466c3447afeab950d371ac6f297d5e325b25e99b7a3d769cd",
    tier="T1",
)

K20_ORIGIN_PROFILE = OriginTemplateProfile(
    profile_id="K20",
    filename="Heat_Map.otpu",
    sha256="9bd8240ca582bbedfec797ea27b1ec5c2906939e304fa343cd1821bae2ffbb9f",
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
