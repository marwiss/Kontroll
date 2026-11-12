-- This file was generated with the assistance of an AI coding tool.
-- The Documents area (ADR 0029): documents and their versions, publications, and the upload and selection sessions.

-- A document belongs to a project and goes with it; latest_index counts its versions, so that two uploads at once
-- wait for each other on its row and get the next two numbers.
CREATE TABLE documents (
    document_id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    title text NOT NULL,
    created_at iso_utc NOT NULL,
    latest_index integer NOT NULL DEFAULT 0
);
CREATE INDEX documents_project ON documents (project_id);

-- The file is in storage under storage_key; the row keeps its name, size, SHA-256 and the metadata given at upload.
-- uploaded_by is UPLOADED_BY, which a deleted user leaves (author keeps the name); a version built on another names
-- it (DERIVED_FROM), and one approved from a change set keeps the changes, packed (ADR 0021).
CREATE TABLE document_versions (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents (document_id) ON DELETE CASCADE,
    version_index integer NOT NULL CHECK (version_index >= 1),
    version_number text NOT NULL,
    creation_date iso_utc NOT NULL,
    title text NOT NULL,
    file_name text NOT NULL,
    size_in_bytes bigint NOT NULL,
    sha256 text NOT NULL,
    storage_key text NOT NULL,
    author text NOT NULL,
    uploaded_by text REFERENCES users (id) ON DELETE SET NULL,
    metadata jsonb NOT NULL DEFAULT '[]',
    parent_version_index integer,
    approved_by text,
    change_set_id text,
    change_set text,
    UNIQUE (document_id, version_index),
    FOREIGN KEY (document_id, parent_version_index) REFERENCES document_versions (document_id, version_index)
);

-- A published version's archive (F9 a): one per version, which the unique key keeps when two publish at once.
CREATE TABLE publications (
    id text PRIMARY KEY,
    version_id text NOT NULL UNIQUE REFERENCES document_versions (id) ON DELETE CASCADE,
    storage_key text NOT NULL,
    file_name text NOT NULL,
    size_in_bytes bigint NOT NULL,
    sha256 text NOT NULL,
    published_at iso_utc NOT NULL,
    published_by text NOT NULL
);

-- The sessions of the Documents API keep only the hash of the token their browser page carries. They hold their
-- user and project as values, as the graph does, and expire on their own: deleting a user or a project leaves them
-- to the cleaner, which deletes the parts' files with the parts.
CREATE TABLE upload_sessions (
    id text PRIMARY KEY,
    token_hash text NOT NULL UNIQUE,
    user_id text NOT NULL,
    username text NOT NULL,
    callback_url text NOT NULL,
    callback_expires_at iso_utc NOT NULL,
    created_at iso_utc NOT NULL,
    expires_at iso_utc NOT NULL,
    server_context text,
    project_id text,
    state text NOT NULL,
    files jsonb NOT NULL DEFAULT '[]'
);
CREATE INDEX upload_sessions_expires_at ON upload_sessions (expires_at);

CREATE TABLE upload_parts (
    id text PRIMARY KEY,
    session_id text NOT NULL REFERENCES upload_sessions (id) ON DELETE CASCADE,
    file_index integer NOT NULL,
    part_index integer NOT NULL,
    range_start bigint NOT NULL,
    range_end bigint NOT NULL,
    received boolean NOT NULL DEFAULT false,
    storage_key text,
    size bigint,
    expires_at iso_utc NOT NULL
);
CREATE INDEX upload_parts_session ON upload_parts (session_id, file_index);
CREATE INDEX upload_parts_expires_at ON upload_parts (expires_at);

CREATE TABLE selection_sessions (
    id text PRIMARY KEY,
    token_hash text NOT NULL UNIQUE,
    user_id text NOT NULL,
    callback_url text NOT NULL,
    callback_expires_at iso_utc NOT NULL,
    created_at iso_utc NOT NULL,
    expires_at iso_utc NOT NULL,
    server_context text,
    extensions text[] NOT NULL DEFAULT '{}',
    state text NOT NULL,
    selected text[] NOT NULL DEFAULT '{}'
);
CREATE INDEX selection_sessions_expires_at ON selection_sessions (expires_at);

-- The seams of 0001 that are this area's: the latest version of each document, and the files a project owns. Each
-- later area that owns files makes project_files anew as the union of document_files and its own.
CREATE OR REPLACE VIEW document_heads (project_id, document_id, version_index, storage_key) AS
    SELECT DISTINCT ON (v.document_id) d.project_id, v.document_id, v.version_index, v.storage_key
    FROM document_versions v JOIN documents d ON d.document_id = v.document_id
    ORDER BY v.document_id, v.version_index DESC;
CREATE VIEW document_files (project_id, storage_key) AS
    SELECT d.project_id, v.storage_key FROM documents d JOIN document_versions v ON v.document_id = d.document_id
    UNION ALL
    SELECT d.project_id, pub.storage_key
    FROM documents d
    JOIN document_versions v ON v.document_id = d.document_id
    JOIN publications pub ON pub.version_id = v.id;
CREATE OR REPLACE VIEW project_files (project_id, storage_key) AS
    SELECT project_id, storage_key FROM document_files;

-- What the documents read of the jobs area, empty until its migration defines them anew with the same columns: the
-- checks of a version against the IFC schema (checks and rooms as JSON text, report packed), and what the graph of
-- a version's converted model showed. Times are iso_utc, counts integer, the rest text.
CREATE VIEW version_validations (
    version_id, created_at, state, issue_count, error_count, truncated, checked_at, ruleset, checks, report, rooms
) AS
    SELECT NULL::text, NULL::iso_utc, NULL::text, NULL::integer, NULL::integer, NULL::boolean, NULL::iso_utc,
           NULL::text, NULL::text, NULL::text, NULL::text
    WHERE false;
CREATE VIEW version_graph_checks (
    project_id, document_id, version_index, created_at, graph_checked_at, graph_issue_count, graph_error_count,
    graph_ruleset, graph_report
) AS
    SELECT NULL::text, NULL::text, NULL::integer, NULL::iso_utc, NULL::iso_utc, NULL::integer, NULL::integer,
           NULL::text, NULL::text
    WHERE false;
