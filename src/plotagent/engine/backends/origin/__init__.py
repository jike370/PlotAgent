"""Official-template Origin backend for Agent Native profiles."""

from .backend import OriginBackend, SubprocessOriginWorker
from .profile import (
    K01_ORIGIN_PROFILE,
    K02_ORIGIN_PROFILE,
    K03_ORIGIN_PROFILE,
    K06_ORIGIN_PROFILE,
    K07_ORIGIN_PROFILE,
    K08_ORIGIN_PROFILE,
    K20_ORIGIN_PROFILE,
    X23_ORIGIN_PROFILE,
    OriginTemplateProfile,
    resolve_official_template,
)

__all__ = [
    "K01_ORIGIN_PROFILE",
    "K02_ORIGIN_PROFILE",
    "K03_ORIGIN_PROFILE",
    "K06_ORIGIN_PROFILE",
    "K07_ORIGIN_PROFILE",
    "K08_ORIGIN_PROFILE",
    "K20_ORIGIN_PROFILE",
    "X23_ORIGIN_PROFILE",
    "OriginBackend",
    "OriginTemplateProfile",
    "SubprocessOriginWorker",
    "resolve_official_template",
]
