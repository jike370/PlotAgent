from __future__ import annotations

import pytest

import plotagent.security.credentials as credential_module
from plotagent.security import InMemoryCredentialStore, create_credential_store


def test_in_memory_store_only_exposes_typed_secret_slots() -> None:
    store = InMemoryCredentialStore()

    store.set_device_credential("device-secret")
    store.set_custom_api_key("custom-one", "custom-secret")

    assert store.get_device_credential() == "device-secret"
    assert store.get_custom_api_key("custom-one") == "custom-secret"
    assert "device-secret" not in repr(store)
    assert "custom-secret" not in repr(store)

    store.delete_device_credential()
    store.delete_custom_api_key("custom-one")
    assert store.get_device_credential() is None
    assert store.get_custom_api_key("custom-one") is None


@pytest.mark.parametrize(
    "provider_config_id",
    ("", "../escape", "with/slash", "space is forbidden", "a" * 129),
)
def test_custom_target_name_is_allowlisted(provider_config_id: str) -> None:
    store = InMemoryCredentialStore()

    with pytest.raises(ValueError, match="provider_config_id"):
        store.set_custom_api_key(provider_config_id, "secret")


@pytest.mark.parametrize("secret", ("", "line\nbreak", "nul\x00byte", "x" * 1_281))
def test_secret_values_are_bounded(secret: str) -> None:
    with pytest.raises(ValueError, match="credential"):
        InMemoryCredentialStore().set_device_credential(secret)


def test_non_windows_factory_is_always_ephemeral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credential_module.sys, "platform", "linux")

    assert isinstance(create_credential_store(), InMemoryCredentialStore)
