"""Closed resolver for the 38 registered Origin official templates."""

from __future__ import annotations

import hashlib
from pathlib import Path

from plotagent.contracts.engine_profiles import CHART_PROFILES
from plotagent.contracts.rendering import OriginTemplateRef


class OriginTemplateCatalogError(ValueError):
    code = "TEMPLATE_OR_FONT_MISSING"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def official_template_path(install_dir: Path, template: OriginTemplateRef) -> Path:
    """Resolve one typed template without accepting a caller-supplied path."""

    root = install_dir.resolve(strict=True)
    path = (root / template.filename).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise OriginTemplateCatalogError("official template escaped the Origin install") from error
    if not path.is_file():
        raise OriginTemplateCatalogError(
            f"official Origin template is missing: {template.filename}"
        )
    actual = _sha256(path)
    if actual != template.template_hash or actual != template.signature_hash:
        raise OriginTemplateCatalogError(
            f"official Origin template hash differs: {template.filename}"
        )
    # originpro 1.1.15 incorrectly rejects uppercase .OTP/.OTPU arguments.
    # Windows resolves this normalized spelling to the same frozen file.
    return path.with_suffix(path.suffix.lower())


def validate_official_template_catalog(install_dir: Path) -> str:
    """Validate every unique production template and return one catalog digest."""

    root = install_dir.resolve(strict=True)
    registered: dict[str, str] = {}
    for profile in CHART_PROFILES:
        registered.setdefault(profile.origin.filename, profile.origin.sha256)
        if registered[profile.origin.filename] != profile.origin.sha256:
            raise OriginTemplateCatalogError(
                f"template filename has conflicting hashes: {profile.origin.filename}"
            )

    digest = hashlib.sha256()
    for filename, expected_hash in sorted(registered.items()):
        path = (root / filename).resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise OriginTemplateCatalogError(
                "official template escaped the Origin install"
            ) from error
        if not path.is_file():
            raise OriginTemplateCatalogError(f"official Origin template is missing: {filename}")
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise OriginTemplateCatalogError(f"official Origin template hash differs: {filename}")
        name = filename.encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(bytes.fromhex(actual_hash))
    return digest.hexdigest()
