# This file was generated with the assistance of an AI coding tool.
"""OAuth2 clients (RFC 6749 §2).

A client is the application that asks for access on a user's behalf: a BCF
plugin, a web viewer, a script. Confidential clients hold a secret (stored
hashed); public clients (native and browser apps) have none and rely on PKCE.
Every client uses PKCE, except a confidential one an administrator has marked
``pkce_optional`` because it cannot: BCF API 2.1 and its OAuth2 example know
nothing of PKCE. Its secret is what protects its codes then (RFC 9700 §2.1.1).
Redirect URIs are registered exactly and matched exactly (RFC 9700 §4.1),
with the loopback exception of RFC 8252 §7.3: for ``http://127.0.0.1`` and
``http://[::1]`` the port may vary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from opencde.errors import UserFacingError
from opencde.graph.graph import Graph
from opencde.ids import hash_secret, is_uuid, new_id, new_secret, normalize_guid, secrets_equal
from opencde.timeutil import now_iso

MAX_REDIRECTS = 10
MAX_DESCRIPTION = 4000  # BCF API 2.1 and Foundation API 2.2.3
LOOPBACK_HOSTS = ("127.0.0.1", "[::1]")


LOCALHOST_REFUSED = "error.redirect_uri.localhost"


class ClientError(UserFacingError):
    """A client-management request that cannot be fulfilled; the message is safe to show, ``key`` names it."""


@dataclass(frozen=True)
class Client:
    client_id: str
    name: str
    description: str | None
    url: str | None
    redirect_uris: list[str]
    is_public: bool
    disabled: bool
    created_at: str
    created_by: str | None
    dynamic: bool
    expires_at: str | None = None  # self-registered clients only: deleted once unused past this moment
    software_id: str | None = None  # RFC 7591: which software registered, and its version
    software_version: str | None = None
    last_used_at: str | None = None  # the latest token issuance
    pending: bool = False  # self-registered and waiting for an administrator, disabled until then
    pkce_optional: bool = False  # a confidential client that may sign in without PKCE
    headless_uploads: bool = False  # a confidential client that may upload documents without the browser page

    @property
    def is_confidential(self) -> bool:
        return not self.is_public


def _client(row: dict[str, Any]) -> Client:
    return Client(
        client_id=row["client_id"],
        name=row["name"],
        description=row.get("description"),
        url=row.get("url"),
        redirect_uris=list(row.get("redirect_uris") or []),
        is_public=bool(row.get("is_public", False)),
        disabled=bool(row.get("disabled", False)),
        created_at=row["created_at"],
        created_by=row.get("created_by"),
        dynamic=bool(row.get("dynamic", False)),
        expires_at=row.get("expires_at"),
        software_id=row.get("software_id"),
        software_version=row.get("software_version"),
        last_used_at=row.get("last_used_at"),
        pending=bool(row.get("pending_approval", False)),
        pkce_optional=bool(row.get("pkce_optional", False)),
        headless_uploads=bool(row.get("headless_uploads", False)),
    )


FIELDS = (
    "c {.client_id, .name, .description, .url, .redirect_uris, .is_public, .disabled, .created_at, .created_by, "
    ".dynamic, .expires_at, .software_id, .software_version, .last_used_at, .pending_approval, .pkce_optional, "
    ".headless_uploads}"
)


LOOPBACK_NAMES = ("127.0.0.1", "::1", "localhost")


def is_localhost(uri: str) -> bool:
    """Whether the way back goes to http://localhost, which only a sign-in to the MCP endpoint may use (F40 b)."""
    parts = urlsplit(uri)
    return parts.scheme.lower() == "http" and (parts.hostname or "").lower() == "localhost"


def validate_redirect_uri(uri: str, *, allow_localhost: bool = False) -> str:
    """Accept https URIs, loopback http URIs and private-use schemes of native apps; nothing else."""
    uri = uri.strip()
    if not uri or len(uri) > 2000:
        raise ClientError("redirect URI missing or too long", key="error.redirect_uri.length")
    parts = urlsplit(uri)
    if parts.fragment:
        raise ClientError("redirect URI must not contain a fragment", key="error.redirect_uri.fragment")
    if not parts.scheme:
        raise ClientError("redirect URI must be absolute", key="error.redirect_uri.absolute")
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme == "https":
        if not host:
            raise ClientError("redirect URI needs a host", key="error.redirect_uri.host")
    elif scheme == "http":
        if host == "localhost" and not allow_localhost:
            raise ClientError(
                "Redirect URIs to http://localhost are not allowed here. Use http://127.0.0.1 instead, "
                "or set OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true on the server",
                key=LOCALHOST_REFUSED,
            )
        loopback = host in ("127.0.0.1", "::1") or (allow_localhost and host == "localhost")
        if not loopback:
            raise ClientError(
                "http redirect URIs are only allowed for the loopback address (127.0.0.1 or [::1])",
                key="error.redirect_uri.http_loopback",
            )
    elif scheme in ("javascript", "data", "vbscript", "file"):
        raise ClientError("unsafe redirect URI scheme", key="error.redirect_uri.scheme")
    # Any other scheme is a private-use scheme of a native application (RFC 8252 §7.1).
    return uri


def redirect_uri_matches(registered: str, requested: str) -> bool:
    """Exact match, except that loopback http URIs may use any port (RFC 8252 §7.3); a registered
    ``localhost`` is matched so too, since a program picks its port when it signs in (F40 b)."""
    if registered == requested:
        return True
    reg, req = urlsplit(registered), urlsplit(requested)
    if reg.scheme != "http" or req.scheme != "http":
        return False
    if (reg.hostname or "").lower() not in LOOPBACK_NAMES or (reg.hostname or "").lower() != (
        req.hostname or ""
    ).lower():
        return False
    return reg.path == req.path and reg.query == req.query and not req.fragment


class ClientRepository:
    def __init__(self, graph: Graph, *, allow_localhost_redirects: bool = False) -> None:
        self.graph = graph
        self.allow_localhost = allow_localhost_redirects

    def _clean_redirects(self, uris: list[str]) -> list[str]:
        if not uris:
            raise ClientError("at least one redirect URI is required", key="error.redirect_uri.required")
        if len(uris) > MAX_REDIRECTS:
            raise ClientError(
                f"at most {MAX_REDIRECTS} redirect URIs", key="error.redirect_uri.too_many", max=MAX_REDIRECTS
            )
        cleaned: list[str] = []
        for uri in uris:
            value = validate_redirect_uri(uri, allow_localhost=self.allow_localhost)
            if value not in cleaned:
                cleaned.append(value)
        return cleaned

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
        """Create a client. Returns the client and, for confidential clients, the secret (shown once).

        ``expires_at`` is set for self-registered clients: the cleaner deletes them once it has passed, and
        every token issuance moves it forward (:meth:`touch`), so only unused registrations disappear.
        """
        name = name.strip()
        if not name or len(name) > 200:
            raise ClientError("client name: 1-200 characters", key="error.client.name_length", max=200)
        if pkce_optional and public:
            raise ClientError("a public client cannot do without PKCE", key="error.client.public_needs_pkce")
        if headless_uploads and public:
            raise ClientError("a public client cannot upload headless", key="error.client.public_no_headless")
        if client_id is not None:
            if not is_uuid(client_id):
                raise ClientError("client_id must be a UUID", key="error.client.id_uuid")
            client_id = normalize_guid(client_id)
        secret = None if public else new_secret()
        row = await self.graph.one(
            f"""
            CREATE (c:Client {{
                client_id: $client_id, name: $name, description: $description, url: $url,
                redirect_uris: $redirect_uris, is_public: $public, secret_hash: $secret_hash,
                disabled: $pending, pending_approval: $pending, created_at: $now, created_by: $created_by,
                dynamic: $dynamic,
                expires_at: $expires_at, software_id: $software_id, software_version: $software_version,
                pkce_optional: $pkce_optional, headless_uploads: $headless_uploads
            }})
            RETURN {FIELDS} AS client
            """,
            client_id=client_id or new_id(),
            name=name,
            description=(description or "").strip()[:MAX_DESCRIPTION] or None,
            url=(url or "").strip()[:2000] or None,
            redirect_uris=self._clean_redirects(redirect_uris),
            public=public,
            secret_hash=hash_secret(secret) if secret else None,
            now=now_iso(),
            created_by=created_by,
            dynamic=dynamic,
            expires_at=expires_at if dynamic else None,
            software_id=(software_id or "").strip()[:100] or None,
            software_version=(software_version or "").strip()[:50] or None,
            pending=pending,
            pkce_optional=pkce_optional,
            headless_uploads=headless_uploads,
        )
        if row is None:  # CREATE always returns a row; this guards the type checker and a broken driver
            raise ClientError("client was not created", key="error.client.not_created")
        return _client(row["client"]), secret

    async def get(self, client_id: str) -> Client | None:
        row = await self.graph.one(f"MATCH (c:Client {{client_id: $id}}) RETURN {FIELDS} AS client", id=client_id)
        return _client(row["client"]) if row else None

    async def all(self) -> list[Client]:
        rows = await self.graph.run(f"MATCH (c:Client) RETURN {FIELDS} AS client ORDER BY c.name")
        return [_client(row["client"]) for row in rows]

    async def authenticate(self, client_id: str, secret: str | None) -> Client | None:
        """Confidential clients must present their secret; public clients must not have one."""
        row = await self.graph.one(
            f"MATCH (c:Client {{client_id: $id}}) RETURN {FIELDS} AS client, c.secret_hash AS secret_hash", id=client_id
        )
        if row is None:
            secrets_equal(hash_secret(secret or ""), hash_secret("no-such-client"))  # constant time
            return None
        client = _client(row["client"])
        if client.disabled:
            return None
        if client.is_public:
            return client if not secret else None
        if not secret or not secrets_equal(hash_secret(secret), row["secret_hash"] or ""):
            return None
        return client

    async def rotate_secret(self, client_id: str) -> str:
        client = await self.get(client_id)
        if client is None:
            raise ClientError("no such client", key="error.client.not_found")
        if client.is_public:
            raise ClientError("public clients have no secret", key="error.client.public_no_secret")
        secret = new_secret()
        await self.graph.run(
            "MATCH (c:Client {client_id: $id}) SET c.secret_hash = $hash", id=client_id, hash=hash_secret(secret)
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
            if client is not None and client.is_public:
                if pkce_optional:
                    raise ClientError("a public client cannot do without PKCE", key="error.client.public_needs_pkce")
                raise ClientError("a public client cannot upload headless", key="error.client.public_no_headless")
        row = await self.graph.one(
            f"""
            MATCH (c:Client {{client_id: $id}})
            SET c.name = coalesce($name, c.name),
                c.description = coalesce($description, c.description),
                c.url = coalesce($url, c.url),
                c.redirect_uris = coalesce($redirect_uris, c.redirect_uris),
                c.disabled = coalesce($disabled, c.disabled),
                c.pkce_optional = coalesce($pkce_optional, c.pkce_optional),
                c.headless_uploads = coalesce($headless_uploads, c.headless_uploads),
                c.pending_approval = CASE WHEN $disabled = false THEN false ELSE c.pending_approval END
            RETURN {FIELDS} AS client
            """,
            id=client_id,
            name=name.strip()[:200] if name else None,
            description=description,
            url=url,
            redirect_uris=self._clean_redirects(redirect_uris) if redirect_uris is not None else None,
            disabled=disabled,
            pkce_optional=pkce_optional,
            headless_uploads=headless_uploads,
        )
        if row is None:
            raise ClientError("no such client", key="error.client.not_found")
        return _client(row["client"])

    async def delete(self, client_id: str) -> bool:
        """Delete the client and every code and token issued to it."""

        async def work(tx: Any) -> int:
            counters = await tx.counters(
                """
                MATCH (c:Client {client_id: $id})
                OPTIONAL MATCH (t)-[:ISSUED_TO]->(c)
                DETACH DELETE t, c
                """,
                id=client_id,
            )
            return counters.nodes_deleted

        return await self.graph.write(work) > 0

    async def touch(self, client_id: str, *, expires_at: str) -> None:
        """The client issued a token: note the time, and let a self-registered client live until ``expires_at``."""
        await self.graph.run(
            """
            MATCH (c:Client {client_id: $id})
            SET c.last_used_at = $now,
                c.expires_at = CASE WHEN c.dynamic = true THEN $expires_at ELSE c.expires_at END
            """,
            id=client_id,
            expires_at=expires_at,
            now=now_iso(),
        )

    async def prune_dynamic(self, *, all_dynamic: bool = False) -> int:
        """Delete expired self-registered clients (or all of them) with their codes and tokens. Returns the count."""
        rows = await self.graph.run(
            "MATCH (c:Client) WHERE c.dynamic = true AND ($all OR c.expires_at < $now) RETURN c.client_id AS id",
            all=all_dynamic,
            now=now_iso(),
        )
        for row in rows:
            await self.delete(row["id"])
        return len(rows)
