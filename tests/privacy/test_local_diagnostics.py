from __future__ import annotations

import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from plotagent.diagnostics import (
    DiagnosticSnapshot,
    LocalDiagnosticBundleBuilder,
    LocalLogRecord,
    LogRetentionPolicy,
    SanitizedDataConsent,
    SanitizedError,
    StructuredLocalLogger,
    StructureSummary,
    TaskState,
    TaskTransition,
    VersionInfo,
)
from plotagent.security import LocalSecurityError

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
HASH = "a" * 64


def _snapshot() -> DiagnosticSnapshot:
    return DiagnosticSnapshot(
        versions=VersionInfo(
            app="0.1.0",
            os="Windows-11-25H2",
            python="3.13.9",
            schema="beta-2",
            dependencies={"sqlite": "3.51.3"},
        ),
        structures=(StructureSummary("SOURCE_DATASET", 10, 3, 20, HASH),),
        errors=(
            SanitizedError.from_stack(
                "IMPORT_FAILED",
                'Traceback:\n  File "C:\\Users\\alice\\secret.py", line 7, in load\n'
                "ValueError: sk-super-secret-value",
            ),
        ),
        task_transitions=(TaskTransition(TaskState.RUNNING, "IMPORT"),),
        config_flags={"LOCAL_ONLY": True},
        origin_capability="O1",
    )


def test_log_record_rejects_path_or_data_in_allowlisted_fields(tmp_path: Path) -> None:
    with pytest.raises(LocalSecurityError) as captured:
        LocalLogRecord(event_code="TASK_EVENT", app_version="C:\\Users\\alice\\app")
    assert captured.value.code == "LOG_SCHEMA_VIOLATION"
    with pytest.raises(LocalSecurityError):
        LocalLogRecord(event_code="TASK_EVENT", app_version="sk-super-secret")

    logger = StructuredLocalLogger(tmp_path / "logs", now=lambda: NOW)
    logger.write(
        LocalLogRecord(
            event_code="TASK_EVENT",
            task_state=TaskState.FAILED,
            task_stage="IMPORT",
            error_code="IMPORT_FAILED",
            stack_trace='  File "C:\\Users\\alice\\secret.py", line 7, in load\n'
            "ValueError: sk-super-secret-value",
        )
    )
    content = next((tmp_path / "logs").glob("plotagent-*.jsonl")).read_text("ascii")
    assert "C:\\Users" not in content
    assert "secret.py" not in content
    assert "sk-super-secret-value" not in content
    assert '"scrubbed_stack":"File \\"<path>\\", line 7, in load\\nValueError"' in content


def test_log_retention_prunes_by_age_and_total_bytes(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old = log_dir / "plotagent-old.jsonl"
    old.write_bytes(b"x" * 100)
    old_time = (NOW - timedelta(days=15)).timestamp()
    os.utime(old, (old_time, old_time))
    logger = StructuredLocalLogger(
        log_dir,
        retention=LogRetentionPolicy(
            max_age=timedelta(days=14), max_total_bytes=600, max_segment_bytes=180
        ),
        now=lambda: NOW,
    )
    assert not old.exists()

    for _ in range(8):
        logger.write(LocalLogRecord(event_code="TASK_EVENT", task_stage="IMPORT"))

    segments = list(log_dir.glob("plotagent-*.jsonl"))
    assert sum(path.stat().st_size for path in segments) <= 600


def test_long_lived_logger_rotates_before_records_exceed_14_days(tmp_path: Path) -> None:
    clock = [NOW]
    log_dir = tmp_path / "logs"
    logger = StructuredLocalLogger(log_dir, now=lambda: clock[0])
    logger.write(LocalLogRecord(event_code="TASK_EVENT"))
    original = next(log_dir.glob("plotagent-*.jsonl"))

    clock[0] = NOW + timedelta(days=14)
    logger.write(LocalLogRecord(event_code="TASK_EVENT"))

    assert not original.exists()
    assert len(list(log_dir.glob("plotagent-*.jsonl"))) == 1


def test_default_bundle_is_exact_previewed_allowlisted_and_local(tmp_path: Path) -> None:
    builder = LocalDiagnosticBundleBuilder(now=lambda: NOW)
    preview = builder.preview(_snapshot())
    preview_text = "\n".join(item.exact_json for item in preview.files)

    assert preview.requires_sanitized_data_consent is False
    assert "C:\\Users" not in preview_text
    assert "secret.py" not in preview_text
    assert "sk-super-secret-value" not in preview_text
    assert "column_name" not in preview_text
    assert "output_path" not in preview_text

    output = tmp_path / "diagnostic.plotdiag"
    builder.save_local(preview, output)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {"manifest.json", "diagnostics.json"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["sanitized_data_consent"] == "absent"
        assert manifest["forbidden_scan_result"] == "passed"
        assert str(output) not in archive.read("manifest.json").decode("ascii")


def test_unknown_or_forbidden_diagnostic_fields_are_rejected() -> None:
    raw: dict[str, object] = {
        "versions": {"app": "1", "os": "Windows", "python": "3.13", "schema": "2"},
        "prompt": "ignore previous instructions",
    }
    with pytest.raises(LocalSecurityError) as captured:
        LocalDiagnosticBundleBuilder(now=lambda: NOW).preview(raw)
    assert captured.value.code == "DIAGNOSTIC_SCHEMA_VIOLATION"
    with pytest.raises(LocalSecurityError):
        SanitizedError("IMPORT_FAILED", "File relative/secret.csv")


def test_sanitized_data_requires_preview_bound_single_use_consent(tmp_path: Path) -> None:
    builder = LocalDiagnosticBundleBuilder(now=lambda: NOW)
    preview = builder.preview(
        _snapshot(),
        sanitized_columns={
            "C:\\Users\\alice\\patient-secret.csv": ["sk-secret-token", 42, -1, None]
        },
    )
    text = "\n".join(item.exact_json for item in preview.files)
    assert preview.requires_sanitized_data_consent
    assert "patient-secret" not in text
    assert "sk-secret-token" not in text
    assert "42" not in text
    assert "negative" in text and "positive" in text

    with pytest.raises(LocalSecurityError) as captured:
        builder.save_local(preview, tmp_path / "without-consent.plotdiag")
    assert captured.value.code == "DIAGNOSTIC_DATA_CONSENT_REQUIRED"

    consent = SanitizedDataConsent.confirm(preview, explicitly_confirmed=True)
    output = tmp_path / "with-consent.plotdiag"
    builder.save_local(preview, output, consent=consent)
    assert output.is_file()
    with pytest.raises(LocalSecurityError):
        builder.save_local(preview, tmp_path / "reused.plotdiag", consent=consent)

    other_builder = LocalDiagnosticBundleBuilder(now=lambda: NOW)
    with pytest.raises(LocalSecurityError) as wrong_operation:
        other_builder.save_local(preview, tmp_path / "other-operation.plotdiag")
    assert wrong_operation.value.code == "DIAGNOSTIC_SCHEMA_VIOLATION"
