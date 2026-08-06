"""Narrow secret storage for provider credentials.

Only two typed secret classes are supported.  Callers never provide a raw
Credential Manager target name, which prevents this adapter from becoming a
general-purpose account or project-secret store.
"""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from typing import Final, Protocol

from plotagent.security.errors import LocalSecurityError

_DEVICE_TARGET: Final = "PlotAgent/DeviceCredential"
_CUSTOM_TARGET_PREFIX: Final = "PlotAgent/CustomApiKey/"
_CONFIG_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_SECRET_BYTES: Final = 2_560

_CRED_TYPE_GENERIC: Final = 1
_CRED_PERSIST_LOCAL_MACHINE: Final = 2
_ERROR_NOT_FOUND: Final = 1_168


class CredentialStore(Protocol):
    def get_device_credential(self) -> str | None: ...

    def set_device_credential(self, secret: str) -> None: ...

    def delete_device_credential(self) -> None: ...

    def get_custom_api_key(self, provider_config_id: str) -> str | None: ...

    def set_custom_api_key(self, provider_config_id: str, secret: str) -> None: ...

    def delete_custom_api_key(self, provider_config_id: str) -> None: ...


class InMemoryCredentialStore:
    """Process-local adapter used on non-Windows platforms and in tests."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def get_device_credential(self) -> str | None:
        return self._secrets.get(_DEVICE_TARGET)

    def set_device_credential(self, secret: str) -> None:
        self._secrets[_DEVICE_TARGET] = _validate_secret(secret)

    def delete_device_credential(self) -> None:
        self._secrets.pop(_DEVICE_TARGET, None)

    def get_custom_api_key(self, provider_config_id: str) -> str | None:
        return self._secrets.get(_custom_target(provider_config_id))

    def set_custom_api_key(self, provider_config_id: str, secret: str) -> None:
        self._secrets[_custom_target(provider_config_id)] = _validate_secret(secret)

    def delete_custom_api_key(self, provider_config_id: str) -> None:
        self._secrets.pop(_custom_target(provider_config_id), None)


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    """Windows Credential Manager adapter restricted to PlotAgent targets."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WINDOWS_CREDENTIAL_MANAGER_UNAVAILABLE")
        self._api = ctypes.WinDLL("Advapi32", use_last_error=True)
        self._api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        self._api.CredWriteW.restype = wintypes.BOOL
        self._api.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
        ]
        self._api.CredReadW.restype = wintypes.BOOL
        self._api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._api.CredDeleteW.restype = wintypes.BOOL
        self._api.CredFree.argtypes = [ctypes.c_void_p]
        self._api.CredFree.restype = None

    def get_device_credential(self) -> str | None:
        return self._read(_DEVICE_TARGET)

    def set_device_credential(self, secret: str) -> None:
        self._write(_DEVICE_TARGET, secret)

    def delete_device_credential(self) -> None:
        self._delete(_DEVICE_TARGET)

    def get_custom_api_key(self, provider_config_id: str) -> str | None:
        return self._read(_custom_target(provider_config_id))

    def set_custom_api_key(self, provider_config_id: str, secret: str) -> None:
        self._write(_custom_target(provider_config_id), secret)

    def delete_custom_api_key(self, provider_config_id: str) -> None:
        self._delete(_custom_target(provider_config_id))

    def _write(self, target: str, secret: str) -> None:
        value = _validate_secret(secret)
        encoded = value.encode("utf-16-le")
        blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        credential = _CREDENTIALW()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = None
        if not self._api.CredWriteW(ctypes.byref(credential), 0):
            raise LocalSecurityError("CREDENTIAL_STORE_FAILED", category="credential_store")

    def _read(self, target: str) -> str | None:
        pointer = ctypes.POINTER(_CREDENTIALW)()
        if not self._api.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == _ERROR_NOT_FOUND:
                return None
            raise LocalSecurityError("CREDENTIAL_STORE_FAILED", category="credential_store")
        try:
            credential = pointer.contents
            encoded = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return encoded.decode("utf-16-le")
        except (UnicodeDecodeError, ValueError):
            raise LocalSecurityError(
                "CREDENTIAL_STORE_FAILED", category="credential_store"
            ) from None
        finally:
            self._api.CredFree(pointer)

    def _delete(self, target: str) -> None:
        if self._api.CredDeleteW(target, _CRED_TYPE_GENERIC, 0):
            return
        if ctypes.get_last_error() != _ERROR_NOT_FOUND:
            raise LocalSecurityError("CREDENTIAL_STORE_FAILED", category="credential_store")


def create_credential_store() -> CredentialStore:
    """Use the OS vault on Windows and an ephemeral adapter elsewhere."""

    if sys.platform == "win32":
        return WindowsCredentialStore()
    return InMemoryCredentialStore()


def _custom_target(provider_config_id: str) -> str:
    if not _CONFIG_ID_PATTERN.fullmatch(provider_config_id):
        raise ValueError("provider_config_id is not valid for credential storage")
    return f"{_CUSTOM_TARGET_PREFIX}{provider_config_id}"


def _validate_secret(secret: str) -> str:
    if not isinstance(secret, str) or not secret:
        raise ValueError("credential must be a non-empty bounded string")
    if "\x00" in secret or "\r" in secret or "\n" in secret:
        raise ValueError("credential contains forbidden characters")
    try:
        encoded = secret.encode("utf-16-le")
    except UnicodeEncodeError:
        raise ValueError("credential contains invalid Unicode") from None
    if len(encoded) > _MAX_SECRET_BYTES:
        raise ValueError("credential must be a non-empty bounded string")
    return secret
