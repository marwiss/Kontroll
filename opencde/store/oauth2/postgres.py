# This file was generated with the assistance of an AI coding tool.
"""The OAuth2 area in PostgreSQL (ADR 0029): clients, authorization codes, access tokens and refresh tokens.

The same protocols as the graph's repositories (``opencde.store.protocols``), over the tables of
``opencde/postgres/migrations/0002_oauth2.sql``, with the same rules and refusals (the functions the two share in
``clients`` and ``tokens``). Codes and tokens are stored as their SHA-256 alone. A refresh token is used once: its use
marks it spent and issues a new pair in its family, and a spent one presented again revokes the family (RFC 9700
§4.14); a code is redeemed once, and a code presented twice revokes what the first redemption produced. A code or a
refresh token is read ``FOR UPDATE``, so that two requests with the same one take their turns and the second is the
replay it is. As in the graph, a revocation that a refusal asks for is committed before the refusal is raised.

Foreign keys delete what is issued to a client or a user with them; ``principal`` joins the user and the client of
the accounts area as the graph's statement follows ``FOR`` and ``ISSUED_TO``. Every statement is one string literal
with numbered parameters.

``client_store`` and ``token_store`` choose between the two: PostgreSQL when ``OPENCDE_STORE_URL`` names it, the
graph otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opencde.ids import hash_secret, new_id, new_secret
from opencde.store.oauth2.clients import (
    Client,
    ClientError,
    ClientRepository,
    _client,
    authenticated,
    check_flags,
    clean_redirects,
    new_client_fields,
)
from opencde.store.oauth2.tokens import (
    GrantError,
    Principal,
    TokenPair,
    TokenRepository,
    _Refusal,
    code_refusal,
    principal_of,
    refresh_refusal,
)
from opencde.timeutil import later_iso, now_iso

if TYPE_CHECKING:
    from opencde.graph.graph import Graph
    from opencde.postgres.database import Postgres, Tx
    from opencde.settings import Settings
    from opencde.store.protocols import ClientStore, TokenStore


# -- clients -----------------------------------------------------------------------------------------------------

CLIENT_INSERT = """
INSERT INTO oauth_clients AS c (
    client_id, name, description, url, redirect_uris, is_public, secret_hash, disabled, pending_approval, created_at,
    created_by, dynamic, expires_at, software_id, software_version, pkce_optional, headless_uploads
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8, $9, $10, $11, $12, $13, $14, $15, $16)
ON CONFLICT (client_id) DO NOTHING
RETURNING c.client_id, c.name, c.description, c.url, c.redirect_uris, c.is_public, c.disabled, c.created_at,
       c.created_by, c.dynamic, c.expires_at, c.software_id, c.software_version, c.last_used_at, c.pending_approval,
       c.pkce_optional, c.headless_uploads
"""
CLIENT_BY_ID = """
SELECT c.client_id, c.name, c.description, c.url, c.redirect_uris, c.is_public, c.disabled, c.created_at,
       c.created_by, c.dynamic, c.expires_at, c.software_id, c.software_version, c.last_used_at, c.pending_approval,
       c.pkce_optional, c.headless_uploads
FROM oauth_clients c WHERE c.client_id = $1
"""
CLIENT_ALL = """
SELECT c.client_id, c.name, c.description, c.url, c.redirect_uris, c.is_public, c.disabled, c.created_at,
       c.created_by, c.dynamic, c.expires_at, c.software_id, c.software_version, c.last_used_at, c.pending_approval,
       c.pkce_optional, c.headless_uploads
FROM oauth_clients c
ORDER BY c.name COLLATE "C", c.client_id COLLATE "C"
"""
CLIENT_SIGN_IN = """
SELECT c.client_id, c.name, c.description, c.url, c.redirect_uris, c.is_public, c.disabled, c.created_at,
       c.created_by, c.dynamic, c.expires_at, c.software_id, c.software_version, c.last_used_at, c.pending_approval,
       c.pkce_optional, c.headless_uploads, c.secret_hash
FROM oauth_clients c WHERE c.client_id = $1
"""
CLIENT_UPDATE = """
UPDATE oauth_clients c
SET name = coalesce($2::text, c.name), description = coalesce($3::text, c.description),
    url = coalesce($4::text, c.url), redirect_uris = coalesce($5::text[], c.redirect_uris),
    disabled = coalesce($6::boolean, c.disabled), pkce_optional = coalesce($7::boolean, c.pkce_optional),
    headless_uploads = coalesce($8::boolean, c.headless_uploads),
    pending_approval = CASE WHEN $6::boolean = false THEN false ELSE c.pending_approval END
WHERE c.client_id = $1
RETURNING c.client_id, c.name, c.description, c.url, c.redirect_uris, c.is_public, c.disabled, c.created_at,
       c.created_by, c.dynamic, c.expires_at, c.software_id, c.software_version, c.last_used_at, c.pending_approval,
       c.pkce_optional, c.headless_uploads
"""
CLIENT_TOUCH = """
UPDATE oauth_clients SET last_used_at = $3, expires_at = CASE WHEN dynamic THEN $2 ELSE expires_at END
WHERE client_id = $1
"""
CLIENT_PRUNE = "DELETE FROM oauth_clients WHERE dynamic AND ($1::boolean OR expires_at < $2)"


class PostgresClientRepository:
    def __init__(self, postgres: Postgres, *, allow_localhost_redirects: bool = False) -> None:
        self.postgres = postgres
        self.allow_localhost = allow_localhost_redirects

    async def create(
        self,
        name: str,
        redirect_uris: list[str],
        *,
        public: bool,
        description: str | None = None,
        url: str | None = None,
        created_by: str | None = None,
        dynamic: bool = False,
        client_id: str | None = None,
        expires_at: str | None = None,
        software_id: str | None = None,
        software_version: str | None = None,
        pending: bool = False,
        pkce_optional: bool = False,
        headless_uploads: bool = False,
    ) -> tuple[Client, str | None]:
        """Create a client. Returns the client and, for confidential clients, the secret (shown once)."""
        fields = new_client_fields(
            name,
            redirect_uris,
            public=public,
            description=description,
            url=url,
            dynamic=dynamic,
            client_id=client_id,
            expires_at=expires_at,
            software_id=software_id,
            software_version=software_version,
            pkce_optional=pkce_optional,
            headless_uploads=headless_uploads,
            allow_localhost=self.allow_localhost,
        )
        secret = None if public else new_secret()
        row = await self.postgres.one(
            CLIENT_INSERT,
            fields["client_id"],
            fields["name"],
            fields["description"],
            fields["url"],
            fields["redirect_uris"],
            public,
            hash_secret(secret) if secret else None,
            pending,
            now_iso(),
            created_by,
            dynamic,
            fields["expires_at"],
            fields["software_id"],
            fields["software_version"],
            pkce_optional,
            headless_uploads,
        )
        if row is None:  # a client_id that is taken, also when two ask for it at once
            raise ClientError("client was not created", key="error.client.not_created")
        return _client(row), secret

    async def get(self, client_id: str) -> Client | None:
        row = await self.postgres.one(CLIENT_BY_ID, client_id)
        return _client(row) if row else None

    async def all(self) -> list[Client]:
        return [_client(row) for row in await self.postgres.run(CLIENT_ALL)]

    async def authenticate(self, client_id: str, secret: str | None) -> Client | None:
        """Confidential clients must present their secret; public clients must not have one."""
        row = await self.postgres.one(CLIENT_SIGN_IN, client_id)
        if row is None:
            return authenticated(None, None, secret)
        return authenticated(_client(row), row["secret_hash"], secret)

    async def rotate_secret(self, client_id: str) -> str:
        client = await self.get(client_id)
        if client is None:
            raise ClientError("no such client", key="error.client.not_found")
        if client.is_public:
            raise ClientError("public clients have no secret", key="error.client.public_no_secret")
        secret = new_secret()
        await self.postgres.execute(
            "UPDATE oauth_clients SET secret_hash = $2 WHERE client_id = $1", client_id, hash_secret(secret)
        )
        return secret

    async def update(
        self,
        client_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        url: str | None = None,
        redirect_uris: list[str] | None = None,
        disabled: bool | None = None,
        pkce_optional: bool | None = None,
        headless_uploads: bool | None = None,
    ) -> Client:
        if pkce_optional or headless_uploads:
            client = await self.get(client_id)
            if client is not None:
                check_flags(public=client.is_public, pkce_optional=pkce_optional, headless_uploads=headless_uploads)
        row = await self.postgres.one(
            CLIENT_UPDATE,
            client_id,
            name.strip()[:200] if name else None,
            description,
            url,
            clean_redirects(redirect_uris, allow_localhost=self.allow_localhost) if redirect_uris is not None else None,
            disabled,
            pkce_optional,
            headless_uploads,
        )
        if row is None:
            raise ClientError("no such client", key="error.client.not_found")
        return _client(row)

    async def delete(self, client_id: str) -> bool:
        """Delete the client and, by its foreign keys, every code and token issued to it."""
        return await self.postgres.execute("DELETE FROM oauth_clients WHERE client_id = $1", client_id) > 0

    async def touch(self, client_id: str, *, expires_at: str) -> None:
        """The client issued a token: note the time, and let a self-registered client live until ``expires_at``."""
        await self.postgres.execute(CLIENT_TOUCH, client_id, expires_at, now_iso())

    async def prune_dynamic(self, *, all_dynamic: bool = False) -> int:
        """Delete expired self-registered clients (or all of them) with their codes and tokens. Returns the count."""
        return await self.postgres.execute(CLIENT_PRUNE, all_dynamic, now_iso())


# -- codes and tokens --------------------------------------------------------------------------------------------

CODE_INSERT = """
INSERT INTO authorization_codes (
    code_hash, user_id, client_id, redirect_uri, redirect_required, scope, code_challenge, resource, created_at,
    auth_time, expires_at
)
SELECT $1, u.id, c.client_id, $4, $5::boolean, $6, $7, $8, $9, $9, $10
FROM users u, oauth_clients c WHERE u.id = $2 AND c.client_id = $3
"""
CODE_TO_REDEEM = """
SELECT ac.redirect_uri, ac.redirect_required, ac.scope, ac.code_challenge, ac.resource, ac.created_at, ac.auth_time,
       ac.expires_at, ac.spent, u.id AS user_id, u.disabled AS user_disabled, c.client_id,
       c.disabled AS client_disabled, c.pkce_optional
FROM authorization_codes ac
JOIN users u ON u.id = ac.user_id
JOIN oauth_clients c ON c.client_id = ac.client_id
WHERE ac.code_hash = $1
FOR UPDATE OF ac
"""
ACCESS_INSERT = """
INSERT INTO access_tokens (
    token_hash, user_id, client_id, family_id, code_hash, scope, resource, created_at, auth_time, expires_at
)
SELECT $1, u.id, c.client_id, $4, $5, $6, $7, $8, $9, $10
FROM users u, oauth_clients c WHERE u.id = $2 AND c.client_id = $3
"""
REFRESH_INSERT = """
INSERT INTO refresh_tokens (
    token_hash, user_id, client_id, family_id, code_hash, scope, resource, created_at, auth_time, expires_at
)
SELECT $1, u.id, c.client_id, $4, $5, $6, $7, $8, $9, $10
FROM users u, oauth_clients c WHERE u.id = $2 AND c.client_id = $3
"""
REFRESH_TO_USE = """
SELECT r.family_id, r.code_hash, r.scope, r.resource, r.created_at, r.auth_time, r.expires_at, r.spent,
       u.id AS user_id, u.disabled AS user_disabled, c.client_id, c.disabled AS client_disabled
FROM refresh_tokens r
JOIN users u ON u.id = r.user_id
JOIN oauth_clients c ON c.client_id = r.client_id
WHERE r.token_hash = $1
FOR UPDATE OF r
"""
#: A rotated refresh token never outlives the first one of its family.
FAMILY_LIFETIME = "UPDATE refresh_tokens SET expires_at = $2 WHERE family_id = $1 AND NOT spent AND expires_at > $2"
REVOKE_CODE_TOKENS = """
WITH a AS (DELETE FROM access_tokens WHERE code_hash = $1 RETURNING 1),
     r AS (DELETE FROM refresh_tokens WHERE code_hash = $1 RETURNING 1)
SELECT (SELECT count(*) FROM a) + (SELECT count(*) FROM r) AS n
"""
REVOKE_FAMILY = """
WITH a AS (DELETE FROM access_tokens WHERE family_id = $1 RETURNING 1),
     r AS (DELETE FROM refresh_tokens WHERE family_id = $1 RETURNING 1)
SELECT (SELECT count(*) FROM a) + (SELECT count(*) FROM r) AS n
"""
PRINCIPAL = """
SELECT a.scope, u.id AS user_id, u.username, u.full_name, u.is_admin, c.client_id, a.auth_time, a.resource
FROM access_tokens a
JOIN users u ON u.id = a.user_id
JOIN oauth_clients c ON c.client_id = a.client_id
WHERE a.token_hash = $1 AND a.expires_at > $2 AND NOT u.disabled AND NOT c.disabled
"""
ISSUED_TO_CLIENT = """
SELECT 'refresh' AS kind, r.family_id FROM refresh_tokens r WHERE r.token_hash = $1 AND r.client_id = $2
UNION ALL
SELECT 'access' AS kind, a.family_id FROM access_tokens a WHERE a.token_hash = $1 AND a.client_id = $2
"""
REVOKE_USER = """
WITH a AS (DELETE FROM access_tokens WHERE user_id = $1 RETURNING 1),
     r AS (DELETE FROM refresh_tokens WHERE user_id = $1 RETURNING 1),
     ac AS (DELETE FROM authorization_codes WHERE user_id = $1 RETURNING 1),
     s AS (DELETE FROM web_sessions WHERE user_id = $1 RETURNING 1)
SELECT (SELECT count(*) FROM a) + (SELECT count(*) FROM r) + (SELECT count(*) FROM ac) + (SELECT count(*) FROM s) AS n
"""
REVOKE_CLIENT = """
WITH a AS (DELETE FROM access_tokens WHERE client_id = $1 RETURNING 1),
     r AS (DELETE FROM refresh_tokens WHERE client_id = $1 RETURNING 1),
     ac AS (DELETE FROM authorization_codes WHERE client_id = $1 RETURNING 1)
SELECT (SELECT count(*) FROM a) + (SELECT count(*) FROM r) + (SELECT count(*) FROM ac) AS n
"""
SESSIONS_OF_USER = """
SELECT r.family_id, c.client_id, c.name AS client_name, r.scope, r.created_at, r.expires_at
FROM refresh_tokens r JOIN oauth_clients c ON c.client_id = r.client_id
WHERE r.user_id = $1 AND NOT r.spent AND r.expires_at > $2
ORDER BY r.created_at DESC, r.family_id COLLATE "C"
"""
REVOKE_FAMILY_OF_USER = """
WITH a AS (DELETE FROM access_tokens WHERE family_id = $1 AND user_id = $2 RETURNING 1),
     r AS (DELETE FROM refresh_tokens WHERE family_id = $1 AND user_id = $2 RETURNING 1)
SELECT (SELECT count(*) FROM a) + (SELECT count(*) FROM r) AS n
"""


def _count(row: dict[str, Any] | None) -> int:
    return int(row["n"]) if row else 0


class PostgresTokenRepository:
    def __init__(
        self, postgres: Postgres, *, code_ttl: int, access_ttl: int, refresh_ttl: int, refresh_idle: int
    ) -> None:
        self.postgres = postgres
        self.code_ttl = code_ttl
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl
        self.refresh_idle = refresh_idle

    # -- authorization codes ------------------------------------------------------

    async def issue_code(
        self,
        *,
        user_id: str,
        client_id: str,
        redirect_uri: str,
        scope: str,
        code_challenge: str | None,
        redirect_required: bool = False,
        resource: str | None = None,
    ) -> str:
        """As :meth:`TokenRepository.issue_code`: the code's hash is stored, the code is returned once."""
        code = new_secret()
        await self.postgres.execute(
            CODE_INSERT,
            hash_secret(code),
            user_id,
            client_id,
            redirect_uri,
            redirect_required,
            scope,
            code_challenge,
            resource,
            now_iso(),
            later_iso(self.code_ttl),
        )
        return code

    async def redeem_code(
        self,
        *,
        code: str,
        client_id: str,
        redirect_uri: str | None,
        code_verifier: str | None,
        resource: str | None = None,
    ) -> TokenPair:
        """Exchange a code for tokens, atomically, by the rules of :meth:`TokenRepository.redeem_code`."""
        code_hash = hash_secret(code or "")

        async def work(tx: Tx) -> TokenPair | _Refusal:
            row = await tx.one(CODE_TO_REDEEM, code_hash)
            if row is None:
                return _Refusal(GrantError("invalid_grant", "unknown authorization code"))
            refusal = code_refusal(
                row,
                row,
                code_hash=code_hash,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
                resource=resource,
            )
            if refusal is not None:
                return refusal
            await tx.execute("UPDATE authorization_codes SET spent = true WHERE code_hash = $1", code_hash)
            return await self._issue_pair(
                tx,
                user_id=row["user_id"],
                client_id=client_id,
                scope=row["scope"],
                family_id=new_id(),
                code_hash=code_hash,
                auth_time=row["auth_time"] or row["created_at"],
                resource=row["resource"],
            )

        return await self._apply(await self.postgres.write(work))

    # -- token pairs ----------------------------------------------------------------

    async def _issue_pair(
        self,
        tx: Tx,
        *,
        user_id: str,
        client_id: str,
        scope: str,
        family_id: str,
        code_hash: str | None,
        auth_time: str | None,
        resource: str | None,
    ) -> TokenPair:
        access = new_secret()
        refresh = new_secret()
        now = now_iso()
        common = (family_id, code_hash, scope, resource, now, auth_time)
        await tx.execute(ACCESS_INSERT, hash_secret(access), user_id, client_id, *common, later_iso(self.access_ttl))
        await tx.execute(REFRESH_INSERT, hash_secret(refresh), user_id, client_id, *common, later_iso(self.refresh_ttl))
        return TokenPair(access_token=access, refresh_token=refresh, expires_in=self.access_ttl, scope=scope)

    async def refresh(self, *, refresh_token: str, client_id: str, resource: str | None = None) -> TokenPair:
        """Rotate a refresh token by the rules of :meth:`TokenRepository.refresh`: reuse of a spent token revokes its
        whole family, and the new pair keeps the family's binding, authentication time and absolute lifetime."""
        token_hash = hash_secret(refresh_token or "")

        async def work(tx: Tx) -> TokenPair | _Refusal:
            row = await tx.one(REFRESH_TO_USE, token_hash)
            if row is None:
                return _Refusal(GrantError("invalid_grant", "unknown refresh token"))
            refusal = refresh_refusal(row, row, client_id=client_id, resource=resource, refresh_idle=self.refresh_idle)
            if refusal is not None:
                return refusal
            await tx.execute("UPDATE refresh_tokens SET spent = true WHERE token_hash = $1", token_hash)
            # The previous access tokens of the family are no longer needed.
            await tx.execute("DELETE FROM access_tokens WHERE family_id = $1", row["family_id"])
            pair = await self._issue_pair(
                tx,
                user_id=row["user_id"],
                client_id=client_id,
                scope=row["scope"],
                family_id=row["family_id"],
                code_hash=row["code_hash"],
                auth_time=row["auth_time"],  # a refresh never counts as a new authentication
                resource=row["resource"],  # the family stays bound where its code was
            )
            await tx.execute(FAMILY_LIFETIME, row["family_id"], row["expires_at"])
            return pair

        return await self._apply(await self.postgres.write(work))

    async def _apply(self, outcome: TokenPair | _Refusal) -> TokenPair:
        """Commit any revocation a refusal asks for, then raise it; or return the pair."""
        if isinstance(outcome, TokenPair):
            return outcome
        if outcome.revoke_code_hash:
            await self.postgres.one(REVOKE_CODE_TOKENS, outcome.revoke_code_hash)
        if outcome.revoke_family_id:
            await self.postgres.one(REVOKE_FAMILY, outcome.revoke_family_id)
        if outcome.delete_code_hash:
            await self.postgres.execute(
                "DELETE FROM authorization_codes WHERE code_hash = $1", outcome.delete_code_hash
            )
        raise outcome.error

    # -- validation and revocation -------------------------------------------------------

    async def principal(self, access_token: str) -> Principal | None:
        row = await self.postgres.one(PRINCIPAL, hash_secret(access_token), now_iso())
        return principal_of(row, access_token) if row else None

    async def revoke(self, token: str, *, client_id: str) -> bool:
        """Revoke an access token, or a refresh token with its whole family (RFC 7009)."""
        token_hash = hash_secret(token or "")

        async def work(tx: Tx) -> bool:
            row = await tx.one(ISSUED_TO_CLIENT, token_hash, client_id)
            if row is None:
                return False
            if row["kind"] == "refresh":
                await tx.one(REVOKE_FAMILY, row["family_id"])
            else:
                await tx.execute("DELETE FROM access_tokens WHERE token_hash = $1", token_hash)
            return True

        return await self.postgres.write(work)

    async def revoke_all_for_user(self, user_id: str) -> int:
        """Every code, token and browser session of the user."""
        return _count(await self.postgres.one(REVOKE_USER, user_id))

    async def revoke_all_for_client(self, client_id: str) -> int:
        return _count(await self.postgres.one(REVOKE_CLIENT, client_id))

    async def sessions_for_user(self, user_id: str) -> list[dict]:
        """Active refresh-token families per client, for "my account" and the admin UI."""
        return await self.postgres.run(SESSIONS_OF_USER, user_id, now_iso())

    async def revoke_family(self, family_id: str, *, user_id: str) -> bool:
        return _count(await self.postgres.one(REVOKE_FAMILY_OF_USER, family_id, user_id)) > 0


# -- where OAuth2 is ---------------------------------------------------------------------------------------------


def client_store(graph: Graph, postgres: Postgres | None, settings: Settings) -> ClientStore:
    allow = settings.registers_localhost
    if postgres is not None:
        return PostgresClientRepository(postgres, allow_localhost_redirects=allow)
    return ClientRepository(graph, allow_localhost_redirects=allow)


def token_store(graph: Graph, postgres: Postgres | None, settings: Settings) -> TokenStore:
    ttls = {
        "code_ttl": settings.authorization_code_ttl_seconds,
        "access_ttl": settings.access_token_ttl_seconds,
        "refresh_ttl": settings.refresh_token_ttl_seconds,
        "refresh_idle": settings.refresh_token_idle_seconds,
    }
    if postgres is not None:
        return PostgresTokenRepository(postgres, **ttls)
    return TokenRepository(graph, **ttls)
