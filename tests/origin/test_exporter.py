from pathlib import Path

from plotagent.origin import exporter
from plotagent.origin._process import WorkerInvocation
from plotagent.origin.constants import ORIGIN_TEMPLATE_SHA256
from plotagent.origin.models import (
    OriginEnvironment,
    OriginErrorCode,
    OriginExportFailure,
    OriginExportSuccess,
    OriginPreflightSuccess,
)


def _ready(target: Path) -> OriginPreflightSuccess:
    return OriginPreflightSuccess(
        status="ready",
        target_path=str(target),
        environment=OriginEnvironment(
            display_name="Origin2024 SR1",
            display_version="10.10.178",
            install_dir=r"D:\origin",
            executable_path=r"D:\origin\Origin64.exe",
            origin_bitness=64,
            python_bitness=64,
            originpro_version="1.1.15",
            runtime_version=10.100178,
            template_sha256=ORIGIN_TEMPLATE_SHA256,
            license_available=True,
        ),
    )


def test_publish_occurs_only_after_matching_fresh_reopen(
    tmp_path: Path, monkeypatch: object
) -> None:
    target = tmp_path / "k01.opju"
    monkeypatch.setattr(exporter, "preflight_origin", lambda *args, **kwargs: _ready(target))
    monkeypatch.setattr(exporter, "validate_target", lambda *args, **kwargs: None)

    calls: list[str] = []

    def fake_worker(mode: str, payload: dict[str, object], timeout: float) -> WorkerInvocation:
        calls.append(mode)
        plan = payload["plan"]
        report = {
            "report": {"chart_type_id": "K01"},
            "report_sha256": plan["validation_report_sha256"],
        }
        if mode == "build":
            Path(str(payload["temporary_opju_path"])).write_bytes(b"native-opju")
        return WorkerInvocation(
            ok=True,
            payload={"status": "ok", "validation": report},
            stderr="",
        )

    monkeypatch.setattr(exporter, "run_worker", fake_worker)

    result = exporter.export_k01(target)

    assert isinstance(result, OriginExportSuccess)
    assert calls == ["build", "reopen"]
    assert target.read_bytes() == b"native-opju"


def test_reopen_failure_never_replaces_existing_target(
    tmp_path: Path, monkeypatch: object
) -> None:
    target = tmp_path / "k01.opju"
    target.write_bytes(b"authoritative-old-file")
    monkeypatch.setattr(exporter, "preflight_origin", lambda *args, **kwargs: _ready(target))

    def fake_worker(mode: str, payload: dict[str, object], timeout: float) -> WorkerInvocation:
        if mode == "build":
            Path(str(payload["temporary_opju_path"])).write_bytes(b"unvalidated-new-file")
            return WorkerInvocation(
                ok=True,
                payload={"status": "ok", "validation": {"report_sha256": "build"}},
                stderr="",
            )
        return WorkerInvocation(
            ok=False,
            payload={
                "status": "error",
                "error": {"code": "REOPEN_FAILURE", "message": "injected"},
            },
            stderr="",
        )

    monkeypatch.setattr(exporter, "run_worker", fake_worker)

    result = exporter.export_k01(target)

    assert isinstance(result, OriginExportFailure)
    assert result.error.code is OriginErrorCode.REOPEN_FAILURE
    assert target.read_bytes() == b"authoritative-old-file"
