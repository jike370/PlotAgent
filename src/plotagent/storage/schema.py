"""Initial storage schemas; deliberately no generic migration framework."""

from __future__ import annotations

import sqlite3

from plotagent.storage.errors import StorageErrorCode, StorageProblem

PROJECT_SCHEMA_VERSION = 1
CATALOG_SCHEMA_VERSION = 1

PROJECT_SCHEMA = """
CREATE TABLE schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE project_meta (
    project_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE objects (
    content_hash TEXT PRIMARY KEY,
    media_type TEXT NOT NULL,
    size INTEGER NOT NULL CHECK (size >= 0),
    ref_count INTEGER NOT NULL DEFAULT 0 CHECK (ref_count >= 0),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE import_recipes (
    import_recipe_id TEXT PRIMARY KEY,
    recipe_hash TEXT NOT NULL UNIQUE,
    recipe_json TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE import_sessions (
    session_id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL,
    dataset_count INTEGER NOT NULL CHECK (dataset_count > 0),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE source_dataset_versions (
    source_dataset_id TEXT NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version > 0),
    logical_source_id TEXT NOT NULL,
    source_object_hash TEXT NOT NULL REFERENCES objects(content_hash) ON DELETE RESTRICT,
    table_object_hash TEXT NOT NULL REFERENCES objects(content_hash) ON DELETE RESTRICT,
    import_recipe_id TEXT NOT NULL REFERENCES import_recipes(import_recipe_id) ON DELETE RESTRICT,
    contract_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES import_sessions(session_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_dataset_id, source_version),
    UNIQUE (logical_source_id, source_version)
) STRICT;

CREATE TABLE object_refs (
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content_hash TEXT NOT NULL REFERENCES objects(content_hash) ON DELETE RESTRICT,
    PRIMARY KEY (owner_type, owner_id, role)
) STRICT;

CREATE INDEX source_dataset_logical_version_idx
ON source_dataset_versions(logical_source_id, source_version DESC);

CREATE INDEX object_refs_hash_idx ON object_refs(content_hash);
"""

CATALOG_SCHEMA = """
CREATE TABLE schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    workspace_path TEXT NOT NULL UNIQUE,
    display_name TEXT,
    created_at TEXT NOT NULL,
    last_opened_at TEXT NOT NULL
) STRICT;

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
) STRICT;
"""


def initialize_project_schema(
    connection: sqlite3.Connection, project_id: str, created_at: str
) -> None:
    connection.executescript(PROJECT_SCHEMA)
    connection.executemany(
        "INSERT INTO schema_info(key, value) VALUES (?, ?)",
        (
            ("schema_version", str(PROJECT_SCHEMA_VERSION)),
            ("schema_kind", "plotagent-project"),
        ),
    )
    connection.execute(
        "INSERT INTO project_meta(project_id, created_at) VALUES (?, ?)",
        (project_id, created_at),
    )
    connection.execute(f"PRAGMA user_version = {PROJECT_SCHEMA_VERSION}")


def initialize_catalog_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(CATALOG_SCHEMA)
    connection.executemany(
        "INSERT INTO schema_info(key, value) VALUES (?, ?)",
        (
            ("schema_version", str(CATALOG_SCHEMA_VERSION)),
            ("schema_kind", "plotagent-catalog"),
        ),
    )
    connection.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")


def validate_schema(
    connection: sqlite3.Connection, expected_version: int, expected_kind: str
) -> None:
    try:
        rows = dict(connection.execute("SELECT key, value FROM schema_info").fetchall())
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    except (sqlite3.DatabaseError, TypeError, ValueError) as exc:
        raise StorageProblem(
            StorageErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "数据库没有受支持的 PlotAgent schema 标识。",
        ) from exc
    if (
        rows.get("schema_kind") != expected_kind
        or rows.get("schema_version") != str(expected_version)
        or user_version != expected_version
    ):
        raise StorageProblem(
            StorageErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "当前 build 不支持该项目 schema；原项目保持不变。",
        )
