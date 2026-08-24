"""Versioned persistence for agent-native plot documents.

This repository deliberately uses new tables.  It does not read or write the
legacy ``plot_spec_versions`` graph compiler state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    AppliedAction,
    CreatePlot,
    PlotDocument,
    PlotDocumentRef,
    PlotJournalAction,
)
from plotagent.storage.project import ProjectStore

_ACTION_ADAPTER: TypeAdapter[PlotJournalAction] = TypeAdapter(PlotJournalAction)


def _document_from_json(value: str) -> PlotDocument:
    try:
        return PlotDocument.model_validate_json(value)
    except ValidationError:
        payload = json.loads(value)
        if not isinstance(payload, dict) or payload.get("schema_version") != "2.0":
            raise
        payload.pop("components", None)
        if isinstance(payload.get("bindings"), list):
            payload["bindings"] = tuple(payload["bindings"])
        if isinstance(payload.get("applied_action_ids"), list):
            payload["applied_action_ids"] = tuple(payload["applied_action_ids"])
        return PlotDocument.model_validate(payload)


def _action_from_json(value: str) -> PlotJournalAction:
    try:
        return _ACTION_ADAPTER.validate_json(value)
    except ValidationError:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise
        payload.pop("components", None)
        if isinstance(payload.get("bindings"), list):
            payload["bindings"] = tuple(payload["bindings"])
        return _ACTION_ADAPTER.validate_python(payload)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def document_ref(document: PlotDocument) -> PlotDocumentRef:
    return PlotDocumentRef(
        plot_id=document.plot_id,
        plot_version=document.plot_version,
        content_hash=canonical_hash(document),
    )


@dataclass(frozen=True, slots=True)
class StoredPlotDocument:
    document: PlotDocument
    content_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class StoredPlotRecord:
    plot_id: str
    plot_version: int
    document_json: str
    content_hash: str
    created_at: str


class EngineRepositoryConflict(ValueError):
    pass


class PlotDocumentRepository:
    """Single-writer repository for the replacement plot domain."""

    def __init__(self, project: ProjectStore) -> None:
        self._project = project
        connection = project._assert_writer()  # noqa: SLF001
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS engine_plot_document_versions (
                plot_id TEXT NOT NULL,
                plot_version INTEGER NOT NULL CHECK (plot_version >= 1),
                parent_version INTEGER,
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                document_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (plot_id, plot_version),
                UNIQUE (plot_id, content_hash)
            );

            CREATE INDEX IF NOT EXISTS idx_engine_plot_documents_latest
            ON engine_plot_document_versions(plot_id, plot_version DESC);

            CREATE TABLE IF NOT EXISTS engine_plot_action_journal (
                action_id TEXT PRIMARY KEY,
                plot_id TEXT NOT NULL,
                plot_version INTEGER NOT NULL,
                action_json TEXT NOT NULL,
                before_ref_json TEXT,
                after_ref_json TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                FOREIGN KEY (plot_id, plot_version)
                    REFERENCES engine_plot_document_versions(plot_id, plot_version)
                    ON DELETE RESTRICT
            );
            """
        )

    def latest_version(self, plot_id: str) -> int | None:
        row = (
            self._project._assert_writer()  # noqa: SLF001
            .execute(
                "SELECT MAX(plot_version) FROM engine_plot_document_versions WHERE plot_id = ?",
                (plot_id,),
            )
            .fetchone()
        )
        return None if row is None or row[0] is None else int(row[0])

    def get(self, plot_id: str, plot_version: int | None = None) -> StoredPlotDocument:
        version = plot_version if plot_version is not None else self.latest_version(plot_id)
        if version is None:
            raise KeyError(f"plot document {plot_id} was not found")
        row = (
            self._project._assert_writer()  # noqa: SLF001
            .execute(
                """
                SELECT document_json, content_hash, created_at
                FROM engine_plot_document_versions
                WHERE plot_id = ? AND plot_version = ?
                """,
                (plot_id, version),
            )
            .fetchone()
        )
        if row is None:
            raise KeyError(f"plot document {plot_id}@{version} was not found")
        return StoredPlotDocument(
            document=_document_from_json(str(row[0])),
            content_hash=str(row[1]),
            created_at=str(row[2]),
        )

    def list_latest_records(self) -> tuple[StoredPlotRecord, ...]:
        rows = self._project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT documents.plot_id, documents.plot_version,
                   documents.document_json, documents.content_hash, documents.created_at
            FROM engine_plot_document_versions AS documents
            INNER JOIN (
                SELECT plot_id, MAX(plot_version) AS plot_version
                FROM engine_plot_document_versions
                GROUP BY plot_id
            ) AS latest
            ON documents.plot_id = latest.plot_id
               AND documents.plot_version = latest.plot_version
            ORDER BY documents.rowid
            """
        )
        return tuple(
            StoredPlotRecord(
                plot_id=str(plot_id),
                plot_version=int(plot_version),
                document_json=str(document_json),
                content_hash=str(content_hash),
                created_at=str(created_at),
            )
            for plot_id, plot_version, document_json, content_hash, created_at in rows
        )

    def list_latest(self) -> tuple[StoredPlotDocument, ...]:
        rows = self._project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT documents.plot_id, documents.plot_version
            FROM engine_plot_document_versions AS documents
            INNER JOIN (
                SELECT plot_id, MAX(plot_version) AS plot_version
                FROM engine_plot_document_versions
                GROUP BY plot_id
            ) AS latest
            ON documents.plot_id = latest.plot_id
               AND documents.plot_version = latest.plot_version
            ORDER BY documents.rowid
            """
        )
        return tuple(self.get(str(plot_id), int(version)) for plot_id, version in rows)

    def commit(
        self,
        document: PlotDocument,
        action: PlotJournalAction,
        *,
        expected_project_revision: int | None = None,
    ) -> AppliedAction:
        """Atomically append one document version and its explicit action."""

        connection = self._project._assert_writer()  # noqa: SLF001
        latest = self.latest_version(document.plot_id)
        if latest is None:
            if document.plot_version != 1 or not isinstance(action, CreatePlot):
                raise ValueError("a plot history must start with create_plot at version 1")
            before = None
            expected_actions: tuple[str, ...] = (action.action_id,)
        else:
            previous = self.get(document.plot_id, latest)
            if document.plot_version != latest + 1 or document.parent_version != latest:
                raise ValueError("plot document version is stale or non-linear")
            if isinstance(action, CreatePlot):
                raise ValueError("create_plot cannot be appended to an existing plot")
            before = PlotDocumentRef(
                plot_id=previous.document.plot_id,
                plot_version=previous.document.plot_version,
                content_hash=previous.content_hash,
            )
            expected_actions = previous.document.applied_action_ids + (action.action_id,)
        if document.applied_action_ids != expected_actions:
            raise ValueError("plot document action history does not match the committed action")

        after = document_ref(document)
        applied_at = _utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            if expected_project_revision is not None:
                cursor = connection.execute(
                    "UPDATE project_meta SET revision = revision + 1 WHERE revision = ?",
                    (expected_project_revision,),
                )
                if cursor.rowcount != 1:
                    raise EngineRepositoryConflict("project version is stale")
            connection.execute(
                """
                INSERT INTO engine_plot_document_versions (
                    plot_id, plot_version, parent_version, content_hash, document_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document.plot_id,
                    document.plot_version,
                    document.parent_version,
                    after.content_hash,
                    document.model_dump_json(),
                    applied_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO engine_plot_action_journal (
                    action_id, plot_id, plot_version, action_json,
                    before_ref_json, after_ref_json, applied_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.action_id,
                    document.plot_id,
                    document.plot_version,
                    _json(action),
                    None if before is None else before.model_dump_json(),
                    after.model_dump_json(),
                    applied_at,
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        return AppliedAction(
            action=action,
            document_before=before,
            document_after=after,
            applied_at=applied_at,
        )

    def actions(self, plot_id: str) -> tuple[AppliedAction, ...]:
        rows = self._project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT action_json, before_ref_json, after_ref_json, applied_at
            FROM engine_plot_action_journal
            WHERE plot_id = ?
            ORDER BY plot_version
            """,
            (plot_id,),
        )
        result: list[AppliedAction] = []
        for action_json, before_json, after_json, applied_at in rows:
            result.append(
                AppliedAction(
                    action=_action_from_json(str(action_json)),
                    document_before=(
                        None
                        if before_json is None
                        else PlotDocumentRef.model_validate_json(str(before_json))
                    ),
                    document_after=PlotDocumentRef.model_validate_json(str(after_json)),
                    applied_at=str(applied_at),
                )
            )
        return tuple(result)

    def find_action(self, action_id: str) -> AppliedAction | None:
        row = self._project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT action_json, before_ref_json, after_ref_json, applied_at
            FROM engine_plot_action_journal
            WHERE action_id = ?
            """,
            (action_id,),
        ).fetchone()
        if row is None:
            return None
        action_json, before_json, after_json, applied_at = row
        return AppliedAction(
            action=_action_from_json(str(action_json)),
            document_before=(
                None
                if before_json is None
                else PlotDocumentRef.model_validate_json(str(before_json))
            ),
            document_after=PlotDocumentRef.model_validate_json(str(after_json)),
            applied_at=str(applied_at),
        )
