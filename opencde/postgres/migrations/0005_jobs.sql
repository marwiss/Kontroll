-- This file was generated with the assistance of an AI coding tool.
-- The jobs area (ADR 0029): the server's records of what it runs, apart from the IFC graph that holds the models.
-- A job's identity, owner, state and the times its queries ask for are columns; what it writes as it goes is its
-- fields, a jsonb document of values, as a node's properties are in the graph. A project owns its jobs, and they go
-- with it; a version owns its checks, a topic its trial, and a user the change sets it has open.

-- A conversion of a document version (or a BCF project document) into a model of the IFC graph, which bears its id.
CREATE TABLE conversions (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    document_id text,
    version_index integer,
    bcf_document_guid text,
    file_name text NOT NULL,
    storage_key text NOT NULL,
    state text NOT NULL CHECK (state IN ('queued', 'running', 'done', 'failed')),
    created_at iso_utc NOT NULL,
    running_at iso_utc,
    done_at iso_utc,
    fields jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX conversions_project ON conversions (project_id);
CREATE INDEX conversions_version ON conversions (document_id, version_index);
CREATE INDEX conversions_state ON conversions (state);

-- The check of a version's file, or a precheck: a file a member checked without making it a version, which has no
-- version and expires, and which the cleaner deletes with its file.
CREATE TABLE validations (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    version_id text REFERENCES document_versions (id) ON DELETE CASCADE,
    storage_key text NOT NULL,
    file_name text NOT NULL,
    author text,
    state text NOT NULL CHECK (state IN ('queued', 'running', 'done', 'failed')),
    created_at iso_utc NOT NULL,
    running_at iso_utc,
    expires_at iso_utc,
    fields jsonb NOT NULL DEFAULT '{}',
    CHECK ((version_id IS NULL) = (expires_at IS NOT NULL))
);
CREATE INDEX validations_version ON validations (version_id);
CREATE INDEX validations_project ON validations (project_id);
CREATE INDEX validations_state ON validations (state);
CREATE INDEX validations_expires_at ON validations (expires_at);

-- The trial of the change set a topic's snippet holds, against its base version; the topic's project is its own.
CREATE TABLE proposals (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    topic_guid text NOT NULL REFERENCES topics (guid) ON DELETE CASCADE,
    snippet_key text NOT NULL,
    author text,
    state text NOT NULL CHECK (state IN ('queued', 'running', 'clean', 'issues', 'failed', 'approved')),
    created_at iso_utc NOT NULL,
    running_at iso_utc,
    base_document_id text,
    base_version_index integer,
    storage_key text,
    fields jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX proposals_topic ON proposals (topic_guid);
CREATE INDEX proposals_base ON proposals (base_document_id);
CREATE INDEX proposals_project ON proposals (project_id);
CREATE INDEX proposals_state ON proposals (state);

-- A clash check between two document versions; the request is the server's JSON.
CREATE TABLE clashes (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    state text NOT NULL CHECK (state IN ('queued', 'running', 'done', 'failed')),
    request text NOT NULL,
    author text NOT NULL,
    created_at iso_utc NOT NULL,
    running_at iso_utc,
    fields jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX clashes_project ON clashes (project_id);
CREATE INDEX clashes_state ON clashes (state);

-- A merge of a building into the project, or the preparation of the other model for one. A preparation's model stands
-- in for a day (expires_at): the job's round then takes the model out and keeps the record as expired.
CREATE TABLE merges (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('merge', 'prepare')),
    state text NOT NULL CHECK (state IN ('queued', 'running', 'done', 'failed', 'conflict', 'expired')),
    request text NOT NULL,
    author text NOT NULL,
    created_at iso_utc NOT NULL,
    running_at iso_utc,
    model_id text,
    expires_at iso_utc,
    fields jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX merges_project ON merges (project_id);
CREATE INDEX merges_state ON merges (state);

-- A change set the MCP endpoint fills step by step, its user's alone; it expires 24 hours after its last use. The
-- steps are the JSON the write tools read, kept as text so that what was measured is what is kept.
CREATE TABLE change_set_drafts (
    changeset_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES documents (document_id) ON DELETE CASCADE,
    version_index integer NOT NULL,
    steps text NOT NULL DEFAULT '[]',
    refs integer NOT NULL DEFAULT 0,
    topic_guid text,
    created_at iso_utc NOT NULL,
    expires_at iso_utc NOT NULL
);
CREATE INDEX change_set_drafts_user ON change_set_drafts (user_id);
CREATE INDEX change_set_drafts_expires_at ON change_set_drafts (expires_at);

-- What the other areas read of the jobs, defined anew over these tables with the columns those areas gave them.

-- The accounts: the models a project's conversions made, which go before it, and every file a project owns.
CREATE OR REPLACE VIEW project_models (project_id, model_id) AS
    SELECT c.project_id, c.id FROM conversions c;
CREATE OR REPLACE VIEW project_files (project_id, storage_key) AS
    SELECT f.project_id, f.storage_key FROM document_files f
    UNION ALL SELECT b.project_id, b.storage_key FROM bcf_files b
    UNION ALL SELECT c.project_id, c.storage_key FROM conversions c
    UNION ALL SELECT r.project_id, r.storage_key FROM validations r;

-- The documents: a version's checks, and what the graph of its model showed once it was converted. The columns keep
-- the types of 0003's empty views, which these replace: times iso_utc, counts integer, the rest text.
CREATE OR REPLACE VIEW version_validations (
    version_id, created_at, state, issue_count, error_count, truncated, checked_at, ruleset, checks, report, rooms
) AS
    SELECT r.version_id, r.created_at, r.state, (r.fields ->> 'issue_count')::integer,
           (r.fields ->> 'error_count')::integer, (r.fields ->> 'truncated')::boolean,
           (r.fields ->> 'checked_at')::iso_utc, r.fields ->> 'ruleset', r.fields ->> 'checks', r.fields ->> 'report',
           r.fields ->> 'rooms'
    FROM validations r
    WHERE r.version_id IS NOT NULL;
CREATE OR REPLACE VIEW version_graph_checks (
    project_id, document_id, version_index, created_at, graph_checked_at, graph_issue_count, graph_error_count,
    graph_ruleset, graph_report
) AS
    SELECT c.project_id, c.document_id, c.version_index, c.created_at, (c.fields ->> 'graph_checked_at')::iso_utc,
           (c.fields ->> 'graph_issue_count')::integer, (c.fields ->> 'graph_error_count')::integer,
           c.fields ->> 'graph_ruleset', c.fields ->> 'graph_report'
    FROM conversions c
    WHERE c.document_id IS NOT NULL AND c.fields ->> 'graph_checked_at' IS NOT NULL;

-- BCF: the IFC project of each finished conversion of a version, and the files of a topic's trials, which reach
-- project_files through bcf_files.
CREATE OR REPLACE VIEW conversion_ifc_projects (document_id, version_index, ifc_project_guid) AS
    SELECT c.document_id, c.version_index, c.fields ->> 'ifc_project_guid'
    FROM conversions c
    WHERE c.state = 'done' AND c.document_id IS NOT NULL;
CREATE OR REPLACE VIEW proposal_files (topic_guid, storage_key) AS
    SELECT r.topic_guid, r.storage_key FROM proposals r WHERE r.storage_key IS NOT NULL;
