"""Secret generation and keyed, versioned secret hashing."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

HASH_VERSION = "hmac-sha256-v1"


@dataclass(frozen=True, slots=True)
class SecretHasher:
    pepper: bytes

    @classmethod
    def from_text(cls, pepper: str) -> "SecretHasher":
        encoded = pepper.encode("utf-8")
        if len(encoded) < 32:
            raise ValueError("Control-plane secret pepper must contain at least 32 bytes")
        return cls(encoded)

    def digest(self, namespace: str, secret: str) -> str:
        material = namespace.encode("ascii") + b"\x00" + secret.encode("utf-8")
        digest = hmac.new(self.pepper, material, hashlib.sha256).hexdigest()
        return f"{HASH_VERSION}${digest}"

    def request_fingerprint(self, canonical_request: bytes) -> str:
        digest = hmac.new(
            self.pepper,
            b"model-run-request\x00" + canonical_request,
            hashlib.sha256,
        ).hexdigest()
        return f"{HASH_VERSION}${digest}"


def generate_invite_secret() -> str:
    return f"inv_v1_{secrets.token_urlsafe(32)}"


def generate_device_credential() -> str:
    return f"dc_v1_{secrets.token_urlsafe(32)}"
