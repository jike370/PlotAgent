from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from plotagent.contracts.engine_profiles import (
    CHART_PROFILES,
    CHART_PROFILES_BY_ID,
    V1_CHART_PROFILE_REGISTRY,
    ChartProfileRegistry,
    OriginOfficialTemplateProfile,
)
from plotagent.contracts.registry import PRODUCT_CHART_IDS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_engine_profiles_exactly_cover_the_38_chart_product_surface() -> None:
    assert len(CHART_PROFILES) == 38
    assert tuple(profile.chart_type_id for profile in CHART_PROFILES) == PRODUCT_CHART_IDS
    assert set(CHART_PROFILES_BY_ID) == set(PRODUCT_CHART_IDS)
    assert V1_CHART_PROFILE_REGISTRY.profiles == CHART_PROFILES


def test_engine_profiles_freeze_28_direct_and_10_declared_patch_templates() -> None:
    direct = tuple(profile for profile in CHART_PROFILES if profile.origin.tier == "T1")
    patched = tuple(profile for profile in CHART_PROFILES if profile.origin.tier == "T2")

    assert len(direct) == 28
    assert len(patched) == 10
    assert all(not profile.origin.declared_patch_ids for profile in direct)
    assert all(profile.origin.declared_patch_ids for profile in patched)
    assert len({profile.origin.binder_id for profile in CHART_PROFILES}) == 38


def test_engine_profiles_only_admit_frozen_official_template_names_and_hashes() -> None:
    for profile in CHART_PROFILES:
        template = profile.origin
        assert template.filename.lower().endswith((".otp", ".otpu"))
        assert len(template.sha256) == 64
        assert template.sha256 == template.sha256.lower()
        assert "/" not in template.filename
        assert "\\" not in template.filename


def test_local_official_template_catalog_matches_frozen_hashes_when_available() -> None:
    origin_home = Path(r"D:\origin")
    if not origin_home.is_dir():
        pytest.skip("local Origin template catalog is unavailable")

    for profile in CHART_PROFILES:
        path = origin_home / profile.origin.filename
        assert path.is_file(), profile.chart_type_id
        assert _sha256(path) == profile.origin.sha256, profile.chart_type_id


def test_profile_models_reject_tier_patch_and_surface_drift() -> None:
    with pytest.raises(ValidationError, match="cannot declare native patches"):
        OriginOfficialTemplateProfile(
            filename="LINE.otpu",
            sha256="0" * 64,
            tier="T1",
            binder_id="plotagent.origin.template.line",
            declared_patch_ids=("unexpected_patch",),
        )
    with pytest.raises(ValidationError, match="require at least one declared patch"):
        OriginOfficialTemplateProfile(
            filename="LINE.otpu",
            sha256="0" * 64,
            tier="T2",
            binder_id="plotagent.origin.template.line",
        )
    with pytest.raises(ValidationError, match="at least 38 items"):
        ChartProfileRegistry(profiles=CHART_PROFILES[:-1])
