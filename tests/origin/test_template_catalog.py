from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from plotagent.contracts.base import ResourceRef
from plotagent.contracts.engine_profiles import CHART_PROFILES_BY_ID
from plotagent.contracts.rendering import OriginTemplateRef
from plotagent.origin.template_catalog import (
    OriginTemplateCatalogError,
    official_template_path,
    validate_official_template_catalog,
)


def _template_ref(chart_id: str) -> OriginTemplateRef:
    profile = CHART_PROFILES_BY_ID[chart_id]
    return OriginTemplateRef(
        template_resource=ResourceRef(
            resource_id=f"resource:origin_template_{chart_id.lower()}",
            resource_kind="authorized_file",
        ),
        filename=profile.origin.filename,
        template_hash=profile.origin.sha256,
        signature_hash=profile.origin.sha256,
        tier=profile.origin.tier,
        binder_id=profile.origin.binder_id,
        declared_patch_ids=profile.origin.declared_patch_ids,
    )


def test_local_38_chart_official_template_catalog_is_complete() -> None:
    origin_home = Path(r"D:\origin")
    if not origin_home.is_dir():
        pytest.skip("local Origin official template catalog is unavailable")

    digest = validate_official_template_catalog(origin_home)

    assert len(digest) == 64
    assert digest == digest.lower()


def test_template_resolver_normalizes_uppercase_extension_and_rejects_hash_drift(
    tmp_path: Path,
) -> None:
    content = b"official-template-test"
    path = tmp_path / "SCATTER.OTP"
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    template = _template_ref("K03").model_copy(
        update={"template_hash": digest, "signature_hash": digest}
    )

    resolved = official_template_path(tmp_path, template)

    assert resolved.name == "SCATTER.otp"
    with pytest.raises(OriginTemplateCatalogError, match="hash differs"):
        official_template_path(
            tmp_path,
            template.model_copy(update={"template_hash": "0" * 64}),
        )
