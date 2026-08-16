"""Exact storage schemas; unsupported versions are rejected without mutation."""

from __future__ import annotations

import sqlite3

from plotagent.storage.errors import StorageErrorCode, StorageProblem

PROJECT_SCHEMA_VERSION = 4
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

WORKFLOW_RUNTIME_SCHEMA = """
CREATE TABLE workflow_runs (
    workflow_run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'routing', 'deterministic_attempt', 'recipe_matching', 'recipe_replay',
        'agent_single_turn', 'agent_exploration', 'needs_input', 'draft_ready',
        'awaiting_confirmation', 'executing', 'completed',
        'partially_succeeded', 'failed', 'cancelled'
    )),
    route TEXT CHECK (route IS NULL OR route IN (
        'deterministic', 'recipe_replay', 'agent_single_turn',
        'agent_exploration', 'needs_input', 'unsupported'
    )),
    context_hash TEXT CHECK (context_hash IS NULL OR length(context_hash) = 64),
    draft_id TEXT,
    plan_id TEXT,
    model_turn_count INTEGER NOT NULL DEFAULT 0 CHECK (model_turn_count BETWEEN 0 AND 6),
    tool_call_count INTEGER NOT NULL DEFAULT 0 CHECK (tool_call_count BETWEEN 0 AND 24),
    input_token_count INTEGER NOT NULL DEFAULT 0 CHECK (input_token_count >= 0),
    output_token_count INTEGER NOT NULL DEFAULT 0 CHECK (output_token_count >= 0),
    estimated_cost REAL NOT NULL DEFAULT 0 CHECK (estimated_cost >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE workflow_contexts (
    workflow_run_id TEXT PRIMARY KEY
        REFERENCES workflow_runs(workflow_run_id) ON DELETE CASCADE,
    project_revision INTEGER NOT NULL CHECK (project_revision >= 0),
    context_hash TEXT NOT NULL CHECK (length(context_hash) = 64),
    context_json TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE task_drafts (
    draft_id TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL
        REFERENCES workflow_runs(workflow_run_id) ON DELETE CASCADE,
    draft_hash TEXT NOT NULL CHECK (length(draft_hash) = 64),
    draft_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workflow_run_id, draft_id)
) STRICT;

CREATE TABLE workflow_task_plans (
    plan_id TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL
        REFERENCES workflow_runs(workflow_run_id) ON DELETE RESTRICT,
    expected_project_revision INTEGER NOT NULL CHECK (expected_project_revision >= 0),
    plan_hash TEXT NOT NULL CHECK (length(plan_hash) = 64),
    plan_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'awaiting_confirmation', 'ready', 'running', 'partially_succeeded',
        'succeeded', 'failed', 'rejected', 'cancelled'
    )),
    confirmation_state TEXT NOT NULL CHECK (confirmation_state IN (
        'pending', 'confirmed', 'rejected'
    )),
    current_project_revision INTEGER NOT NULL CHECK (current_project_revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE workflow_task_items (
    plan_id TEXT NOT NULL REFERENCES workflow_task_plans(plan_id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    state TEXT NOT NULL CHECK (state IN (
        'pending', 'running', 'succeeded', 'failed', 'blocked', 'cancelled'
    )),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 32),
    error_code TEXT,
    output_plot_id TEXT,
    output_plot_version INTEGER CHECK (output_plot_version IS NULL OR output_plot_version > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (plan_id, item_id),
    UNIQUE (plan_id, position)
) STRICT;

CREATE INDEX workflow_task_items_state_idx
    ON workflow_task_items(plan_id, state, position);

CREATE TABLE workflow_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id TEXT NOT NULL
        REFERENCES workflow_runs(workflow_run_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX workflow_events_run_idx ON workflow_events(workflow_run_id, event_id);

CREATE TABLE workflow_recipes (
    recipe_id TEXT NOT NULL,
    recipe_version INTEGER NOT NULL CHECK (recipe_version > 0),
    structure_fingerprint TEXT NOT NULL CHECK (length(structure_fingerprint) = 64),
    goal_signature TEXT NOT NULL CHECK (length(goal_signature) = 64),
    recipe_hash TEXT NOT NULL CHECK (length(recipe_hash) = 64),
    recipe_json TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (recipe_id, recipe_version),
    UNIQUE (recipe_hash)
) STRICT;

CREATE INDEX workflow_recipe_match_idx
    ON workflow_recipes(structure_fingerprint, goal_signature, archived);
"""

PROJECT_SCHEMA += WORKFLOW_RUNTIME_SCHEMA

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


def ensure_desktop_project_schema(connection: sqlite3.Connection) -> None:
    """Verify the exact workflow-era schema; never patch an older project in place."""

    required = (
        "workflow_runs",
        "workflow_contexts",
        "task_drafts",
        "workflow_task_plans",
        "workflow_task_items",
        "workflow_events",
        "workflow_recipes",
    )
    available = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    missing = tuple(table for table in required if table not in available)
    if missing:
        raise sqlite3.DatabaseError(f"Workflow project tables are missing: {missing!r}")


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
