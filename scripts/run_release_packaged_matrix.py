from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import platform
import queue
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
RELEASE_ROOT = REPOSITORY / "release" / "windows"
PUBLISH_ROOT = RELEASE_ROOT / "publish"
MANIFEST_PATH = PUBLISH_ROOT / "release-manifest.json"
UNPACKED_ROOT = RELEASE_ROOT / "electron" / "win-unpacked"
DESKTOP_EXECUTABLE = UNPACKED_ROOT / "PlotAgent.exe"
CORE_EXECUTABLE = (
    UNPACKED_ROOT
    / "resources"
    / "core"
    / "plotagent-core"
    / "plotagent-core.exe"
)


@dataclass(frozen=True, slots=True)
class PackagedResult:
    case_id: str
    status: str
    duration_ms: float
    observation: str
    evidence: str


class _CoreClient:
    def __init__(self, executable: Path, environment: dict[str, str]) -> None:
        self.process = subprocess.Popen(
            [str(executable)],
            cwd=executable.parent,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if self.process.stdin is None or self.process.stdout is None or self.process.stderr is None:
            raise RuntimeError("packaged Core pipes were not available")
        self.stdin = self.process.stdin
        self.stdout_queue: queue.Queue[bytes] = queue.Queue()
        self.stdout: list[bytes] = []
        self.stderr: list[bytes] = []
        self.threads = (
            self._reader(self.process.stdout, self.stdout, self.stdout_queue),
            self._reader(self.process.stderr, self.stderr, None),
        )

    @staticmethod
    def _reader(
        stream: IO[bytes],
        captured: list[bytes],
        destination: queue.Queue[bytes] | None,
    ) -> threading.Thread:
        def read() -> None:
            for line in iter(stream.readline, b""):
                captured.append(line)
                if destination is not None:
                    destination.put(line)

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        return thread

    def request(
        self,
        request_id: str,
        method: str,
        params: object = ...,
        *,
        timeout_seconds: float = 20,
    ) -> object:
        payload: dict[str, object] = {
            "jsonrpc": "2.0",
            "protocol_version": "1.0",
            "id": request_id,
            "method": method,
        }
        if params is not ...:
            payload["params"] = params
        self.stdin.write(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
        self.stdin.flush()
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"timed out waiting for packaged Core request {request_id}")
            line = self.stdout_queue.get(timeout=remaining)
            message = json.loads(line)
            if isinstance(message, dict) and message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"packaged Core RPC failed: {message['error']}")
                return message.get("result")

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.request("req:shutdown", "system.shutdown")
                self.process.wait(timeout=10)
        finally:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=5)
            for thread in self.threads:
                thread.join(timeout=1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8"
    ).strip()


def _isolated_environment(root: Path, configured_origin: Path) -> dict[str, str]:
    app_data = root / "appdata" / "roaming"
    local_app_data = root / "appdata" / "local"
    user_profile = root / "user-profile"
    temporary = root / "temp"
    for path in (app_data, local_app_data, user_profile, temporary):
        path.mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "APPDATA": str(app_data),
        "LOCALAPPDATA": str(local_app_data),
        "USERPROFILE": str(user_profile),
        "HOME": str(user_profile),
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "PLOTAGENT_ORIGIN_EXECUTABLE": str(configured_origin),
    }


def _core_case(
    output: Path,
    case_id: str,
    configured_origin: Path,
    expected_status: str,
    expected_code: str | None,
) -> PackagedResult:
    started = time.perf_counter()
    case_root = output / "profiles" / case_id
    environment = _isolated_environment(case_root, configured_origin)
    client = _CoreClient(CORE_EXECUTABLE, environment)
    try:
        initialized = cast(
            dict[str, object],
            client.request(
                "req:init",
                "system.initialize",
                {"protocol_version": "1.0", "desktop_api_version": "1.0"},
            ),
        )
        status = cast(dict[str, object], client.request("req:origin", "origin.status", {}))
        if initialized.get("status") != "ready":
            raise RuntimeError(f"packaged Core was not ready: {initialized}")
        if status.get("status") != expected_status:
            raise RuntimeError(f"unexpected Origin status: {status}")
        if expected_code is not None:
            error = cast(dict[str, object], status.get("error"))
            if error.get("code") != expected_code:
                raise RuntimeError(f"unexpected Origin error: {status}")
        if expected_status == "ready":
            origin_environment = cast(dict[str, object], status.get("environment"))
            if origin_environment.get("display_version") != "10.1.0":
                raise RuntimeError(f"wrong packaged Origin version: {status}")
        status_path = output / "readback" / f"{case_id}.json"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        leaked = b"".join(client.stderr)
        if b"Traceback" in leaked:
            raise RuntimeError("packaged Core leaked a traceback")
        observation = f"Core ready; origin={status['status']}"
        if expected_code is not None:
            observation += f"; code={expected_code}"
        result_status = "PASS"
    except Exception as exc:  # noqa: BLE001 - release evidence records stable failure text
        result_status = "FAIL"
        observation = f"{type(exc).__name__}: {exc}"
        status_path = output / "readback" / f"{case_id}.json"
    finally:
        client.close()
    return PackagedResult(
        case_id=case_id,
        status=result_status,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        observation=observation,
        evidence=str(status_path.relative_to(output)),
    )


def _frozen_worker_entry_case(output: Path) -> PackagedResult:
    started = time.perf_counter()
    case_id = "PACKAGED-FROZEN-ORIGIN-WORKER-ENTRY"
    evidence_path = output / "readback" / f"{case_id}.json"
    try:
        completed = subprocess.run(
            [str(CORE_EXECUTABLE), "--origin-worker"],
            cwd=CORE_EXECUTABLE.parent,
            capture_output=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        stderr = completed.stderr.decode("utf-8", errors="replace")
        stdout = completed.stdout.decode("utf-8", errors="replace")
        combined = stderr + stdout
        if completed.returncode == 0 or "usage: origin worker" not in combined:
            raise RuntimeError(
                "frozen Core did not route --origin-worker to the sealed worker entry"
            )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(
                {
                    "returncode": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        status = "PASS"
        observation = "frozen Core routes --origin-worker and exits promptly on invalid arity"
    except Exception as exc:  # noqa: BLE001 - release evidence records stable failure text
        status = "FAIL"
        observation = f"{type(exc).__name__}: {exc}"
    return PackagedResult(
        case_id=case_id,
        status=status,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        observation=observation,
        evidence=str(evidence_path.relative_to(output)),
    )


def _packaged_matplotlib_case(output: Path, configured_origin: Path) -> PackagedResult:
    started = time.perf_counter()
    case_id = "PACKAGED-CORE-RENDER-EXPORT"
    case_root = output / "profiles" / case_id
    environment = _isolated_environment(case_root, configured_origin)
    evidence_path = output / "readback" / f"{case_id}.json"
    fixture = REPOSITORY / "tests" / "fixtures" / "import" / "files" / "excel_two_sheets.xlsx"
    export_root = output / "exports" / case_id
    export_root.mkdir(parents=True, exist_ok=True)
    client = _CoreClient(CORE_EXECUTABLE, environment)
    try:
        client.request(
            "req:init-render",
            "system.initialize",
            {"protocol_version": "1.0", "desktop_api_version": "1.0"},
        )
        created = cast(
            dict[str, object],
            client.request(
                "req:project-create",
                "projects.create",
                {
                    "display_name": "Packaged render smoke",
                    "idempotency_key": "packaged-render-smoke",
                },
            ),
        )
        project_id = cast(str, created["project_id"])
        opened = cast(
            dict[str, object],
            client.request("req:project-open", "projects.open", {"project_id": project_id}),
        )
        imported = cast(
            dict[str, object],
            client.request(
                "req:dataset-import",
                "datasets.import",
                {
                    "project_id": project_id,
                    "resource_id": "resource:packaged-render",
                    "source_path": str(fixture),
                    "idempotency_key": "packaged-render-data",
                    "expected_version": opened["project_version"],
                    "options": {},
                },
                timeout_seconds=60,
            ),
        )
        dataset = cast(dict[str, object], cast(list[object], imported["datasets"])[0])
        numeric = [
            cast(str, field["field_id"])
            for field in cast(list[dict[str, object]], dataset["fields"])
            if field["logical_type"] == "numeric"
        ]
        if len(numeric) < 2:
            raise RuntimeError("packaged fixture did not expose two numeric fields")
        rendered = cast(
            dict[str, object],
            client.request(
                "req:plot-create",
                "engine.actions.execute",
                {
                    "project_id": project_id,
                    "expected_project_version": imported["project_version"],
                    "action": {
                        "operation": "create_plot",
                        "action_id": "action:packaged-render.create",
                        "plot_id": "plot:packaged-render",
                        "profile_id": "K01",
                        "data": {
                            "kind": "source",
                            "dataset_id": dataset["source_dataset_id"],
                            "version": dataset["source_version"],
                            "content_hash": dataset["content_hash"],
                        },
                        "bindings": [
                            {"role": "x", "field_id": numeric[0]},
                            {"role": "y", "field_id": numeric[1]},
                        ],
                    },
                },
                timeout_seconds=90,
            ),
        )
        artifacts: dict[str, object] = {}
        for export_format in ("png", "svg"):
            destination = export_root / f"packaged-render.{export_format}"
            exported = cast(
                dict[str, object],
                client.request(
                    f"req:export-{export_format}",
                    "engine.exports.execute",
                    {
                        "project_id": project_id,
                        "action": {
                            "operation": "export_plot",
                            "action_id": f"action:packaged-render.export-{export_format}",
                            "target": "plot:packaged-render",
                            "expected_plot_version": rendered["plot_version"],
                            "format": export_format,
                            "output_name": destination.name,
                        },
                        "destination_resource_id": f"resource:packaged-{export_format}",
                        "destination_path": str(destination),
                    },
                    timeout_seconds=60,
                ),
            )
            if not destination.is_file():
                raise RuntimeError(f"packaged {export_format} export is missing")
            artifact = cast(dict[str, object], exported["artifact"])
            if _sha256(destination) != artifact["content_hash"]:
                raise RuntimeError(f"packaged {export_format} hash mismatch")
            artifacts[export_format] = {
                "path": str(destination),
                "size": destination.stat().st_size,
                "sha256": _sha256(destination),
            }
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(
                {
                    "project_id": project_id,
                    "plot_id": rendered["plot_id"],
                    "plot_version": rendered["plot_version"],
                    "artifacts": artifacts,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        status = "PASS"
        observation = "frozen Core rendered K01 and exported verified PNG and SVG"
    except Exception as exc:  # noqa: BLE001 - release evidence records stable failure text
        status = "FAIL"
        observation = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
    return PackagedResult(
        case_id=case_id,
        status=status,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        observation=observation,
        evidence=str(evidence_path.relative_to(output)),
    )


if os.name == "nt":
    _user32: Any = ctypes.WinDLL("user32", use_last_error=True)
    _enum_windows_proc: Any = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )
else:
    _user32 = None
    _enum_windows_proc = None


def _main_window_for_process(process_id: int) -> int | None:
    if _user32 is None or _enum_windows_proc is None:
        return None
    found: list[int] = []

    def visit(window: int, _parameter: int) -> bool:
        owner = ctypes.c_ulong()
        _user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == process_id and _user32.IsWindowVisible(window):
            found.append(int(window))
        return True

    callback = _enum_windows_proc(visit)
    _user32.EnumWindows(callback, 0)
    return found[0] if found else None


def _desktop_case(output: Path, configured_origin: Path) -> PackagedResult:
    started = time.perf_counter()
    case_id = "PACKAGED-ELECTRON-ISOLATED-PROFILE"
    case_root = output / "profiles" / case_id
    environment = _isolated_environment(case_root, configured_origin)
    user_data = case_root / "electron-user-data"
    process = subprocess.Popen(
        [str(DESKTOP_EXECUTABLE), f"--user-data-dir={user_data}"],
        cwd=DESKTOP_EXECUTABLE.parent,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        window: int | None = None
        catalog = case_root / "appdata" / "local" / "PlotAgent" / "catalog.sqlite3"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"packaged desktop exited with {process.returncode}")
            window = _main_window_for_process(process.pid)
            if window is not None and catalog.is_file():
                break
            time.sleep(0.1)
        if window is None or not catalog.is_file():
            raise RuntimeError("packaged desktop did not expose a window and isolated catalog")
        evidence_path = output / "readback" / f"{case_id}.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(
                {
                    "process_id": process.pid,
                    "window_handle": window,
                    "catalog_path": str(catalog),
                    "catalog_size": catalog.stat().st_size,
                    "user_data_path": str(user_data),
                    "configured_origin": str(configured_origin),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _user32.PostMessageW(window, 0x0010, 0, 0)
        process.wait(timeout=15)
        status = "PASS"
        observation = "packaged Electron window and isolated Core catalog opened and closed cleanly"
    except Exception as exc:  # noqa: BLE001 - release evidence records stable failure text
        status = "FAIL"
        observation = f"{type(exc).__name__}: {exc}"
        evidence_path = output / "readback" / f"{case_id}.json"
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
    return PackagedResult(
        case_id=case_id,
        status=status,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        observation=observation,
        evidence=str(evidence_path.relative_to(output)),
    )


def _integrity_case(output: Path) -> PackagedResult:
    started = time.perf_counter()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    installer_record = cast(dict[str, object], manifest["artifacts"][0])
    installer = PUBLISH_ROOT / cast(str, installer_record["path"])
    issues: list[str] = []
    if manifest.get("git_commit") != _git("rev-parse", "HEAD"):
        issues.append("manifest commit differs from HEAD")
    if manifest.get("source_dirty") is not False:
        issues.append("manifest was built from a dirty source")
    if not installer.is_file():
        issues.append("installer is missing")
    elif _sha256(installer) != installer_record.get("sha256"):
        issues.append("installer SHA-256 mismatch")
    for path in (DESKTOP_EXECUTABLE, CORE_EXECUTABLE):
        if not path.is_file():
            issues.append(f"packaged executable is missing: {path.name}")
    evidence = output / "readback" / "PACKAGED-INTEGRITY.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return PackagedResult(
        case_id="PACKAGED-INTEGRITY",
        status="PASS" if not issues else "FAIL",
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        observation=(
            "installer hash, manifest commit, source cleanliness, desktop and Core present"
            if not issues
            else "; ".join(issues)
        ),
        evidence=str(evidence.relative_to(output)),
    )


def execute(output: Path) -> tuple[PackagedResult, ...]:
    output.mkdir(parents=True, exist_ok=False)
    missing_origin = output / "fixtures" / "missing" / "Origin64.exe"
    wrong_origin = output / "fixtures" / "wrong" / "Origin64.exe"
    wrong_origin.parent.mkdir(parents=True)
    wrong_origin.write_bytes(b"not an Origin executable")
    supported_origin = Path(r"D:\origin\Origin64.exe")
    results = (
        _integrity_case(output),
        _frozen_worker_entry_case(output),
        _core_case(output, "PACKAGED-ORIGIN-MISSING", missing_origin, "error", "NOT_INSTALLED"),
        _core_case(
            output,
            "PACKAGED-ORIGIN-WRONG-VERSION",
            wrong_origin,
            "error",
            "VERSION_UNSUPPORTED",
        ),
        _core_case(output, "PACKAGED-ORIGIN-SUPPORTED", supported_origin, "ready", None),
        _packaged_matplotlib_case(output, missing_origin),
        _desktop_case(output, missing_origin),
    )
    metadata = {
        "schema_version": "release-packaged-matrix.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "commit": _git("rev-parse", "HEAD"),
        "worktree_status": _git("status", "--short"),
        "platform": platform.platform(),
        "case_count": len(results),
        "pass_count": sum(item.status == "PASS" for item in results),
        "fail_count": sum(item.status == "FAIL" for item in results),
        "isolated_profile_is_new_windows_sid": False,
    }
    (output / "run-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output / "matrix-results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(asdict(results[0])))
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)
    lines = [
        "# Release packaged matrix",
        "",
        f"- Commit: `{metadata['commit']}`",
        f"- PASS: {metadata['pass_count']}",
        f"- FAIL: {metadata['fail_count']}",
        "- Isolated profile uses a fresh directory but not a different Windows SID.",
        "",
        "| Case | Status | Duration ms | Observation |",
        "|---|---:|---:|---|",
    ]
    for item in results:
        observation = item.observation.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {item.case_id} | {item.status} | {item.duration_ms:.3f} | {observation} |"
        )
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    commit = _git("rev-parse", "--short", "HEAD")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default = REPOSITORY / "build" / "release-matrix" / f"packaged-{commit}-{timestamp}"
    output = (args.output or default).resolve()
    results = execute(output)
    print(output)
    print(
        f"PASS={sum(item.status == 'PASS' for item in results)} "
        f"FAIL={sum(item.status == 'FAIL' for item in results)}"
    )
    return 0 if all(item.status == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
