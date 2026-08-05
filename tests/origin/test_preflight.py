from pathlib import Path

from plotagent.origin import preflight
from plotagent.origin.models import OriginErrorCode, OriginPreflightFailure


def test_target_requires_opju_suffix(tmp_path: Path) -> None:
    failure = preflight.validate_target(tmp_path / "k01.png")

    assert failure is not None
    assert failure.error.code is OriginErrorCode.SAVE_FAILURE


def test_existing_target_requires_expected_hash(tmp_path: Path) -> None:
    target = tmp_path / "k01.opju"
    target.write_bytes(b"existing")

    failure = preflight.validate_target(target)

    assert failure is not None
    assert failure.error.code is OriginErrorCode.EXTERNAL_MODIFIED


def test_other_origin_versions_are_stably_unsupported(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setattr(preflight, "validate_target", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        preflight,
        "_find_installations",
        lambda: [preflight._Installation("Origin2025", "10.20.1", Path(r"C:\Origin"))],
    )

    result = preflight.preflight_origin(tmp_path / "k01.opju")

    assert isinstance(result, OriginPreflightFailure)
    assert result.error.code is OriginErrorCode.VERSION_UNSUPPORTED
    assert result.error.details["declared_version"] == "10.10.178"
