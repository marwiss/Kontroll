-- This file was generated with the assistance of an AI coding tool.
-- The OAuth2 area (ADR 0029): clients, and the authorization codes, access tokens and refresh tokens issued to them.

-- A confidential client's secret is stored as its SHA-256; a public client has none and always uses PKCE. Only a
-- self-registered (dynamic) client has expires_at: the cleaner deletes it once unused past that moment.
CREATE TABLE oauth_clients (
    client_id text PRIMARY KEY,
    name text NOT NULL,
    description text,
    url text,
    redirect_uris text[] NOT NULL,
    is_public boolean NOT NULL,
    secret_hash text,
    disabled boolean NOT NULL DEFAULT false,
    pending_approval boolean NOT NULL DEFAULT false,
    created_at iso_utc NOT NULL,
    created_by text,
    dynamic boolean NOT NULL DEFAULT false,
    expires_at iso_utc,
    software_id text,
    software_version text,
    last_used_at iso_utc,
    pkce_optional boolean NOT NULL DEFAULT false,
    headless_uploads boolean NOT NULL DEFAULT false,
    CONSTRAINT oauth_clients_public
        CHECK (NOT is_public OR (secret_hash IS NULL AND NOT pkce_optional AND NOT headless_uploads))
);
CREATE INDEX oauth_clients_expires_at ON oauth_clients (expires_at);

-- Codes and tokens are stored as the SHA-256 of their value, which is never stored. A user's or a client's
-- deletion takes what was issued to them. A token names the code its family began with, which may be gone.
CREATE TABLE authorization_codes (
    code_hash text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    client_id text NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    redirect_uri text NOT NULL,
    redirect_required boolean NOT NULL DEFAULT false,
    scope text NOT NULL,
    code_challenge text,
    resource text,
    created_at iso_utc NOT NULL,
    auth_time iso_utc NOT NULL,
    expires_at iso_utc NOT NULL,
    spent boolean NOT NULL DEFAULT false
);
CREATE INDEX authorization_codes_user ON authorization_codes (user_id);
CREATE INDEX authorization_codes_client ON authorization_codes (client_id);
CREATE INDEX authorization_codes_expires_at ON authorization_codes (expires_at);

CREATE TABLE access_tokens (
    token_hash text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    client_id text NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    family_id text NOT NULL,
    code_hash text,
    scope text NOT NULL,
    resource text,
    created_at iso_utc NOT NULL,
    auth_time iso_utc,
    expires_at iso_utc NOT NULL
);
CREATE INDEX access_tokens_family ON access_tokens (family_id);
CREATE INDEX access_tokens_code ON access_tokens (code_hash);
CREATE INDEX access_tokens_user ON access_tokens (user_id);
CREATE INDEX access_tokens_client ON access_tokens (client_id);
CREATE INDEX access_tokens_expires_at ON access_tokens (expires_at);

-- A refresh token is spent when it is used and stays, spent, until it expires: presenting it again revokes its
-- family (RFC 9700 section 4.14).
CREATE TABLE refresh_tokens (
    token_hash text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    client_id text NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    family_id text NOT NULL,
    code_hash text,
    scope text NOT NULL,
    resource text,
    created_at iso_utc NOT NULL,
    auth_time iso_utc,
    expires_at iso_utc NOT NULL,
    spent boolean NOT NULL DEFAULT false
);
CREATE INDEX refresh_tokens_family ON refresh_tokens (family_id);
CREATE INDEX refresh_tokens_code ON refresh_tokens (code_hash);
CREATE INDEX refresh_tokens_user ON refresh_tokens (user_id);
CREATE INDEX refresh_tokens_client ON refresh_tokens (client_id);
CREATE INDEX refresh_tokens_expires_at ON refresh_tokens (expires_at);
