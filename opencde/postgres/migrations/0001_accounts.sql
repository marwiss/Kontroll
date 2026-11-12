-- This file was generated with the assistance of an AI coding tool.
-- The accounts area (ADR 0029): users, projects and their members, teams, and the browser's sign-in sessions.

-- Timestamps are the server's canonical ISO 8601 form in UTC, as in the graphs, so that string order is time order.
CREATE DOMAIN iso_utc AS text
    CHECK (VALUE ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$');

CREATE TABLE users (
    id text PRIMARY KEY,
    username text NOT NULL UNIQUE,
    email text,
    full_name text,
    password_hash text NOT NULL,
    is_admin boolean NOT NULL DEFAULT false,
    disabled boolean NOT NULL DEFAULT false,
    must_change_password boolean NOT NULL DEFAULT false,
    created_at iso_utc NOT NULL,
    last_sign_in_at iso_utc
);
CREATE INDEX users_email ON users (email);

-- A project's BCF extensions (BCF 3.1.4) are one document of lists by name; its users are its members, not stored.
CREATE TABLE projects (
    project_id text PRIMARY KEY,
    name text NOT NULL,
    created_at iso_utc NOT NULL,
    topic_counter integer NOT NULL DEFAULT 0,
    block_on_validation_errors boolean NOT NULL DEFAULT false,
    ai_policy text NOT NULL DEFAULT 'local' CHECK (ai_policy IN ('local', 'cloud')),
    extensions jsonb NOT NULL DEFAULT '{}'
);

-- MEMBER_OF: every statement that reads for a member joins this table on the user's id.
CREATE TABLE memberships (
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('viewer', 'contributor', 'editor', 'manager')),
    since iso_utc NOT NULL,
    PRIMARY KEY (user_id, project_id)
);
CREATE INDEX memberships_project ON memberships (project_id);

CREATE TABLE teams (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    name text NOT NULL,
    ids_document_id text NOT NULL,
    responsible_user_id text REFERENCES users (id) ON DELETE SET NULL,
    created_at iso_utc NOT NULL,
    updated_at iso_utc NOT NULL
);
CREATE INDEX teams_project ON teams (project_id);

CREATE TABLE team_members (
    team_id text NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, user_id)
);

-- The id is the SHA-256 of the cookie, which is never stored.
CREATE TABLE web_sessions (
    id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at iso_utc NOT NULL,
    expires_at iso_utc NOT NULL,
    idle_expires_at iso_utc NOT NULL,
    ip text
);
CREATE INDEX web_sessions_user ON web_sessions (user_id);
CREATE INDEX web_sessions_expires_at ON web_sessions (expires_at);

-- What the accounts read of the other areas, empty until the migration of the area that holds the data defines it
-- anew: the files and the models a project owns, which go with it, and the latest version of each document, whose
-- IDS file points out a team's part of the model.
CREATE VIEW project_files (project_id, storage_key) AS
    SELECT NULL::text, NULL::text WHERE false;
CREATE VIEW project_models (project_id, model_id) AS
    SELECT NULL::text, NULL::text WHERE false;
CREATE VIEW document_heads (project_id, document_id, version_index, storage_key) AS
    SELECT NULL::text, NULL::text, NULL::integer, NULL::text WHERE false;
