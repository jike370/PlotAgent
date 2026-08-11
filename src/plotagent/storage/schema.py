"""Initial storage schemas; deliberately no generic migration framework."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from plotagent.storage.errors import StorageErrorCode, StorageProblem

PROJECT_SCHEMA_VERSION = 3
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

CREATE TABLE idempotency_records (
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (operation, idempotency_key)
) STRICT;
"""

AGENT_RUNTIME_SCHEMA = """
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE conversation_states (
    conversation_id TEXT PRIMARY KEY
        REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    state_version INTEGER NOT NULL CHECK (state_version > 0),
    state_json TEXT NOT NULL,
    context_hash TEXT,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE project_context_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL
        REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    project_revision INTEGER NOT NULL CHECK (project_revision >= 0),
    snapshot_hash TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX project_context_conversation_idx
    ON project_context_snapshots(conversation_id, created_at DESC);

CREATE TABLE task_plans (
    plan_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL
        REFERENCES conversations(conversation_id) ON DELETE RESTRICT,
    context_snapshot_id TEXT NOT NULL
        REFERENCES project_context_snapshots(snapshot_id) ON DELETE RESTRICT,
    context_hash TEXT NOT NULL,
    project_revision INTEGER NOT NULL CHECK (project_revision >= 0),
    source_plan_hash TEXT NOT NULL,
    source_plan_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'draft', 'needs_confirmation', 'ready', 'running', 'partial_success',
        'succeeded', 'failed', 'interrupted', 'needs_input', 'stale', 'cancelled'
    )),
    confirmation_state TEXT NOT NULL CHECK (confirmation_state IN (
        'not_required', 'pending', 'confirmed', 'rejected'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX task_plans_conversation_idx
    ON task_plans(conversation_id, updated_at DESC);

CREATE TABLE task_items (
    task_item_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES task_plans(plan_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    action_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'pending', 'ready', 'running', 'committing', 'succeeded', 'failed',
        'interrupted', 'blocked', 'stale', 'skipped', 'cancelled'
    )),
    depends_on_json TEXT NOT NULL,
    expected_objects_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    output_slots_json TEXT NOT NULL,
    outputs_json TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 32),
    failure_json TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (plan_id, position),
    UNIQUE (plan_id, action_id),
    UNIQUE (plan_id, idempotency_key)
) STRICT;

CREATE INDEX task_items_plan_state_idx ON task_items(plan_id, state, position);

CREATE TABLE task_attempts (
    attempt_id TEXT PRIMARY KEY,
    task_item_id TEXT NOT NULL REFERENCES task_items(task_item_id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 32),
    state TEXT NOT NULL CHECK (state IN (
        'running', 'succeeded', 'failed', 'interrupted', 'cancelled'
    )),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    failure_json TEXT,
    UNIQUE (task_item_id, attempt_number)
) STRICT;

CREATE TABLE task_checkpoints (
    plan_id TEXT NOT NULL REFERENCES task_plans(plan_id) ON DELETE CASCADE,
    task_item_id TEXT NOT NULL REFERENCES task_items(task_item_id) ON DELETE CASCADE,
    checkpoint_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (plan_id, task_item_id, checkpoint_key)
) STRICT;

CREATE TABLE task_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL REFERENCES task_plans(plan_id) ON DELETE CASCADE,
    task_item_id TEXT REFERENCES task_items(task_item_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX task_events_plan_idx ON task_events(plan_id, event_id);
"""

PROJECT_SCHEMA += AGENT_RUNTIME_SCHEMA

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


def _execute_schema_script(connection: sqlite3.Connection, script: str) -> None:
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        raise sqlite3.DatabaseError("Incomplete schema statement")


def migrate_project_v1_to_v2(connection: sqlite3.Connection) -> None:
    """Atomically add the persistent conversation and task runtime."""

    rows = dict(connection.execute("SELECT key, value FROM schema_info").fetchall())
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if (
        rows.get("schema_kind") != "plotagent-project"
        or rows.get("schema_version") != "1"
        or version != 1
    ):
        raise StorageProblem(
            StorageErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "Only the project v1 to v2 upgrade is supported.",
        )
    connection.execute("BEGIN IMMEDIATE")
    try:
        _execute_schema_script(connection, AGENT_RUNTIME_SCHEMA)
        connection.execute(
            "UPDATE schema_info SET value = ? WHERE key = 'schema_version'",
            ("2",),
        )
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def migrate_project_v2_to_v3(connection: sqlite3.Connection) -> None:
    """Remove the retired plotting compiler tables without touching project data.

    Imported sources, CAS objects, conversation state and task history remain
    intact.  Plot documents and action journals are owned by the Agent Native
    engine and are created by its repositories when first used.
    """

    rows = dict(connection.execute("SELECT key, value FROM schema_info").fetchall())
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if (
        rows.get("schema_kind") != "plotagent-project"
        or rows.get("schema_version") != "2"
        or version != 2
    ):
        raise StorageProblem(
            StorageErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "Only the project v2 to v3 upgrade is supported.",
        )
    connection.execute("BEGIN IMMEDIATE")
    try:
        for table in (
            "export_records",
            "figure_spec_versions",
            "batch_spec_versions",
            "plot_spec_versions",
            "plot_inputs",
        ):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.execute(
            "UPDATE schema_info SET value = ? WHERE key = 'schema_version'",
            (str(PROJECT_SCHEMA_VERSION),),
        )
        connection.execute(f"PRAGMA user_version = {PROJECT_SCHEMA_VERSION}")
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def ensure_desktop_project_schema(connection: sqlite3.Connection) -> None:
    """Verify the shared data and Agent runtime needed by the desktop Core."""

    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(project_meta)")}
    connection.execute("BEGIN IMMEDIATE")
    try:
        if "revision" not in columns:
            connection.execute(
                "ALTER TABLE project_meta ADD COLUMN revision "
                "INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)"
            )
        connection.executescript(
            """
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
        for table in (
            "conversations",
            "conversation_states",
            "project_context_snapshots",
            "task_plans",
            "task_items",
            "task_attempts",
            "task_checkpoints",
            "task_events",
        ):
            row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            if row is None:
                raise sqlite3.DatabaseError(f"Project v2 table is missing: {table}")
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
