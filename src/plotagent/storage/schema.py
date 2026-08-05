"""Initial storage schemas; deliberately no generic migration framework."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from plotagent.storage.errors import StorageErrorCode, StorageProblem

PROJECT_SCHEMA_VERSION = 1
CATALOG_SCHEMA_VERSION = 2

PROJECT_SCHEMA = """
CREATE TABLE schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE project_meta (
    project_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)
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

CREATE TABLE plot_inputs (
    plot_id TEXT NOT NULL,
    plot_version INTEGER NOT NULL CHECK (plot_version > 0),
    field_mapping_json TEXT NOT NULL,
    field_mapping_hash TEXT NOT NULL,
    preparation_spec_json TEXT NOT NULL,
    preparation_spec_hash TEXT NOT NULL,
    prepared_dataset_json TEXT NOT NULL,
    prepared_table_hash TEXT NOT NULL REFERENCES objects(content_hash) ON DELETE RESTRICT,
    render_bindings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (plot_id, plot_version)
) STRICT;

CREATE TABLE plot_spec_versions (
    plot_id TEXT NOT NULL,
    plot_version INTEGER NOT NULL CHECK (plot_version > 0),
    parent_plot_version INTEGER,
    content_hash TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (plot_id, plot_version),
    UNIQUE (plot_id, content_hash),
    FOREIGN KEY (plot_id, plot_version)
        REFERENCES plot_inputs(plot_id, plot_version) ON DELETE RESTRICT
) STRICT;

CREATE INDEX plot_spec_latest_idx
ON plot_spec_versions(plot_id, plot_version DESC);

CREATE TABLE batch_spec_versions (
    batch_id TEXT NOT NULL,
    batch_version INTEGER NOT NULL CHECK (batch_version > 0),
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (batch_id, batch_version)
) STRICT;

CREATE TABLE figure_spec_versions (
    figure_id TEXT NOT NULL,
    figure_version INTEGER NOT NULL CHECK (figure_version > 0),
    content_hash TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (figure_id, figure_version)
) STRICT;

CREATE TABLE export_records (
    export_id TEXT PRIMARY KEY,
    plot_id TEXT NOT NULL,
    plot_version INTEGER NOT NULL CHECK (plot_version > 0),
    format TEXT NOT NULL CHECK (format IN ('png', 'svg', 'opju')),
    destination_path TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_size INTEGER NOT NULL CHECK (artifact_size >= 0),
    render_plan_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (plot_id, plot_version)
        REFERENCES plot_spec_versions(plot_id, plot_version) ON DELETE RESTRICT
) STRICT;

CREATE TABLE idempotency_records (
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (operation, idempotency_key)
) STRICT;
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
    source_project_id TEXT,
    package_sha256 TEXT,
    created_at TEXT NOT NULL,
    last_opened_at TEXT NOT NULL
) STRICT;

CREATE INDEX projects_package_sha_idx ON projects(package_sha256);
CREATE INDEX projects_source_project_idx ON projects(source_project_id);

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


def migrate_catalog_v1_to_v2(path: Path) -> None:
    """Apply the one supported pre-release catalog upgrade atomically."""

    with sqlite3.connect(path) as connection:
        rows = dict(connection.execute("SELECT key, value FROM schema_info").fetchall())
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if rows.get("schema_kind") != "plotagent-catalog" or version != 1:
            raise StorageProblem(
                StorageErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Only the catalog v1 to v2 upgrade is supported.",
            )
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("ALTER TABLE projects ADD COLUMN source_project_id TEXT")
        connection.execute("ALTER TABLE projects ADD COLUMN package_sha256 TEXT")
        connection.execute("CREATE INDEX projects_package_sha_idx ON projects(package_sha256)")
        connection.execute(
            "CREATE INDEX projects_source_project_idx ON projects(source_project_id)"
        )
        connection.execute(
            "UPDATE schema_info SET value = ? WHERE key = 'schema_version'",
            (str(CATALOG_SCHEMA_VERSION),),
        )
        connection.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")
        connection.commit()


def ensure_desktop_project_schema(connection: sqlite3.Connection) -> None:
    """Add the closed desktop domain tables to an older schema-v1 work copy."""

    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(project_meta)")
    }
    connection.execute("BEGIN IMMEDIATE")
    try:
        if "revision" not in columns:
            connection.execute(
                "ALTER TABLE project_meta ADD COLUMN revision "
                "INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)"
            )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS plot_inputs (
                plot_id TEXT NOT NULL,
                plot_version INTEGER NOT NULL CHECK (plot_version > 0),
                field_mapping_json TEXT NOT NULL,
                field_mapping_hash TEXT NOT NULL,
                preparation_spec_json TEXT NOT NULL,
                preparation_spec_hash TEXT NOT NULL,
                prepared_dataset_json TEXT NOT NULL,
                prepared_table_hash TEXT NOT NULL REFERENCES objects(content_hash)
                    ON DELETE RESTRICT,
                render_bindings_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (plot_id, plot_version)
            ) STRICT;
            CREATE TABLE IF NOT EXISTS plot_spec_versions (
                plot_id TEXT NOT NULL,
                plot_version INTEGER NOT NULL CHECK (plot_version > 0),
                parent_plot_version INTEGER,
                content_hash TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (plot_id, plot_version),
                UNIQUE (plot_id, content_hash),
                FOREIGN KEY (plot_id, plot_version)
                    REFERENCES plot_inputs(plot_id, plot_version) ON DELETE RESTRICT
            ) STRICT;
            CREATE INDEX IF NOT EXISTS plot_spec_latest_idx
                ON plot_spec_versions(plot_id, plot_version DESC);
            CREATE TABLE IF NOT EXISTS batch_spec_versions (
                batch_id TEXT NOT NULL,
                batch_version INTEGER NOT NULL CHECK (batch_version > 0),
                state TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (batch_id, batch_version)
            ) STRICT;
            CREATE TABLE IF NOT EXISTS figure_spec_versions (
                figure_id TEXT NOT NULL,
                figure_version INTEGER NOT NULL CHECK (figure_version > 0),
                content_hash TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (figure_id, figure_version)
            ) STRICT;
            CREATE TABLE IF NOT EXISTS export_records (
                export_id TEXT PRIMARY KEY,
                plot_id TEXT NOT NULL,
                plot_version INTEGER NOT NULL CHECK (plot_version > 0),
                format TEXT NOT NULL CHECK (format IN ('png', 'svg', 'opju')),
                destination_path TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                artifact_size INTEGER NOT NULL CHECK (artifact_size >= 0),
                render_plan_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (plot_id, plot_version)
                    REFERENCES plot_spec_versions(plot_id, plot_version) ON DELETE RESTRICT
            ) STRICT;
            CREATE TABLE IF NOT EXISTS idempotency_records (
                operation TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (operation, idempotency_key)
            ) STRICT;
            """
        )
        input_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(plot_inputs)")
        }
        if "render_bindings_json" not in input_columns:
            connection.execute(
                "ALTER TABLE plot_inputs ADD COLUMN render_bindings_json "
                "TEXT NOT NULL DEFAULT '{}'"
            )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


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
