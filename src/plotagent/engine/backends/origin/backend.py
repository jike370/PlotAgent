"""Versioned OPJU artifact backend using a sealed Origin worker."""

from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol

from plotagent.engine.contracts import PlotDocument, PlotEngineAction
from plotagent.engine.ports import (
    EngineArtifact,
    EngineReadback,
    EngineRenderSource,
    PlotBackendChange,
)

from .messages import OriginWorkerRequest, OriginWorkerResponse
from .recipe import origin_recipe


class OriginWorker(Protocol):
    def run(self, request: OriginWorkerRequest) -> OriginWorkerResponse: ...


class SubprocessOriginWorker:
    def __init__(self, *, timeout_seconds: float = 900.0) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, request: OriginWorkerRequest) -> OriginWorkerResponse:
        output = Path(request.output_opju)
        request_path = output.with_suffix(".request.json")
        response_path = output.with_suffix(".response.json")
        request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
        completed = subprocess.run(
            (
                sys.executable,
                "-m",
                "plotagent.engine.backends.origin.worker",
                str(request_path),
                str(response_path),
            ),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Origin worker failed: "
                + (completed.stderr.strip() or completed.stdout.strip() or "unknown error")
            )
        return OriginWorkerResponse.model_validate_json(response_path.read_text(encoding="utf-8"))


class _Change:
    def __init__(self, staging: Path, final: Path, readback: EngineReadback) -> None:
        self._staging = staging
        self._final = final
        self._readback = readback
        self._published = False

    @property
    def readback(self) -> EngineReadback:
        return self._readback

    def publish(self) -> None:
        if self._final.exists():
            raise FileExistsError(f"Origin version artifact already exists: {self._final}")
        self._final.parent.mkdir(parents=True, exist_ok=True)
        self._staging.replace(self._final)
        self._published = True

    def revert(self) -> None:
        if self._published:
            shutil.rmtree(self._final, ignore_errors=True)
            self._published = False

    def finalize(self) -> None:
        return None

    def discard(self) -> None:
        shutil.rmtree(self._staging, ignore_errors=True)


class OriginBackend:
    backend_id: Literal["origin"] = "origin"

    def __init__(self, root: Path, install_dir: Path, worker: OriginWorker) -> None:
        self._root = root
        self._install_dir = install_dir
        self._worker = worker

    def stage(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        source: EngineRenderSource,
    ) -> PlotBackendChange:
        # Reject an unproven Origin route before creating staging files or
        # launching Origin. Matplotlib support for the same public profile is
        # independent; this check closes only the native OPJU path.
        origin_recipe(document.profile_id)
        staging = self._root / ".staging" / uuid.uuid4().hex
        staging.mkdir(parents=True)
        previous = None
        if document.plot_version > 1:
            previous = (
                self._root
                / document.plot_id.removeprefix("plot:")
                / (f"v{document.plot_version - 1}")
                / "plot.opju"
            )
            if not previous.is_file():
                raise FileNotFoundError(f"previous Origin project is missing: {previous}")
        request = OriginWorkerRequest(
            install_dir=str(self._install_dir),
            output_opju=str(staging / "plot.opju"),
            previous_opju=None if previous is None else str(previous),
            document=document,
            actions=actions,
            source=source,
        )
        response = self._worker.run(request)
        if not (staging / "plot.opju").is_file():
            raise RuntimeError("Origin worker did not create a staged OPJU")
        (staging / "readback.json").write_text(
            response.readback.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return _Change(staging, self._version_dir(document), response.readback)

    def readback(self, document: PlotDocument) -> EngineReadback:
        return EngineReadback.model_validate_json(
            (self._version_dir(document) / "readback.json").read_text(encoding="utf-8")
        )

    def export(self, document: PlotDocument, destination: Path, format: str) -> EngineArtifact:
        if format != "opju":
            raise ValueError("Origin backend exports only OPJU")
        source = self._version_dir(document) / "plot.opju"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        payload = destination.read_bytes()
        return EngineArtifact(
            backend="origin",
            format="opju",
            artifact_hash=sha256(payload).hexdigest(),
            artifact_size=len(payload),
        )

    def _version_dir(self, document: PlotDocument) -> Path:
        return self._root / document.plot_id.removeprefix("plot:") / f"v{document.plot_version}"
