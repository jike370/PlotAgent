from pathlib import Path

from plotagent.origin import _process, exporter
from plotagent.origin._process import WorkerInvocation
from plotagent.origin.constants import ORIGIN_TEMPLATE_SHA256
from plotagent.origin.models import (
    OriginEnvironment,
    OriginErrorCode,
    OriginExportFailure,
    OriginExportSuccess,
    OriginPreflightSuccess,
)
from plotagent.origin.planner import build_origin_export_spec, compile_origin_plan
from plotagent.origin.validation import expected_validation_sha256
from tests.rendering.fixture_factory import resolve_chart


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

    def fake_worker(
        mode: str, payload: dict[str, object], timeout: float, **_kwargs: object
    ) -> WorkerInvocation:
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


def test_reopen_failure_never_replaces_existing_target(tmp_path: Path, monkeypatch: object) -> None:
    target = tmp_path / "k01.opju"
    target.write_bytes(b"authoritative-old-file")
    monkeypatch.setattr(exporter, "preflight_origin", lambda *args, **kwargs: _ready(target))

    def fake_worker(
        mode: str, payload: dict[str, object], timeout: float, **_kwargs: object
    ) -> WorkerInvocation:
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


def test_typed_origin_export_uses_independent_build_and_reopen_workers(
    tmp_path: Path, monkeypatch: object
) -> None:
    target = tmp_path / "typed.opju"
    resolved = resolve_chart("K13")
    plan = compile_origin_plan((resolved,), build_origin_export_spec((resolved,)))
    report_sha256 = expected_validation_sha256(plan)
    monkeypatch.setattr(exporter, "preflight_origin", lambda *args, **kwargs: _ready(target))
    monkeypatch.setattr(exporter, "validate_target", lambda *args, **kwargs: None)
    calls: list[str] = []

    def fake_worker(
        mode: str, payload: dict[str, object], timeout: float, **_kwargs: object
    ) -> WorkerInvocation:
        del timeout
        calls.append(mode)
        validation = {"report": {"chart_type_id": "K13"}, "report_sha256": report_sha256}
        if mode == "build-plan":
            Path(str(payload["temporary_opju_path"])).write_bytes(b"typed-native-opju")
        return WorkerInvocation(
            ok=True,
            payload={"status": "ok", "validation": validation},
            stderr="",
        )

    monkeypatch.setattr(exporter, "run_worker", fake_worker)

    result = exporter.export_origin(plan, target)

    assert isinstance(result, OriginExportSuccess)
    assert calls == ["build-plan", "reopen-plan"]
    assert target.read_bytes() == b"typed-native-opju"


def test_origin_worker_transport_is_forced_to_utf8() -> None:
    environment = _process._worker_environment()
    assert environment["PYTHONUTF8"] == "1"
    assert environment["PYTHONIOENCODING"] == "utf-8"
