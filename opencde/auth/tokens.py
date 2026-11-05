# This file was generated with the assistance of an AI coding tool.
"""Authorization codes, access tokens and refresh tokens (RFC 6749, RFC 9700).

All three are random 256-bit strings. The graph stores only their SHA-256
hash, who they belong to, which client they were issued to, their scope and
when they expire. Validation is a lookup; revocation is a delete.

Refresh tokens rotate: every use marks the old token as spent and issues a
new pair in the same *family*. If a spent refresh token is presented again,
someone else got hold of it, and the whole family is revoked (RFC 9700
§4.14). Authorization codes are single-use and short-lived; a code
presented twice revokes what the first presentation produced.

Revocations triggered by a refused request are committed in their own
transaction *before* the refusal is raised: a transaction function that raises
is rolled back, which would undo the very revocation that protects the user.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencde.auth import pkce
from opencde.graph.graph import Graph, Tx
from opencde.ids import hash_secret, new_id, new_secret
from opencde.timeutil import later_iso, now_iso


class GrantError(Exception):
    """An OAuth2 token request that must be refused. ``error`` follows RFC 6749 §5.2."""

    def __init__(self, error: str, description: str, status: int = 400) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str


@dataclass(frozen=True)
class Principal:
    """Who is calling the API: the user, through which client, with which scopes."""

    user_id: str
    username: str
    display_name: str
    is_admin: bool
    client_id: str
    scopes: tuple[str, ...]
    token_hash: str

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


@dataclass(frozen=True)
class _Refusal:
    """Why a grant is refused and what must be revoked first (committed separately)."""

    error: GrantError
    revoke_code_hash: str | None = None
    revoke_family_id: str | None = None
    delete_code_hash: str | None = None


class TokenRepository:
    def __init__(self, graph: Graph, *, code_ttl: int, access_ttl: int, refresh_ttl: int) -> None:
        self.graph = graph
        self.code_ttl = code_ttl
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl

    # -- authorization codes ------------------------------------------------------

    async def issue_code(
        self, *, user_id: str, client_id: str, redirect_uri: str, scope: str, code_challenge: str
    ) -> str:
        code = new_secret()
        await self.graph.run(
            """
            MATCH (u:User {id: $user_id}), (c:Client {client_id: $client_id})
            CREATE (ac:AuthorizationCode {
                code_hash: $code_hash, redirect_uri: $redirect_uri, scope: $scope,
                code_challenge: $code_challenge, created_at: $now, expires_at: $expires_at, spent: false
            })
            CREATE (ac)-[:FOR]->(u)
            CREATE (ac)-[:ISSUED_TO]->(c)
            """,
            user_id=user_id,
            client_id=client_id,
            code_hash=hash_secret(code),
            redirect_uri=redirect_uri,
            scope=scope,
            code_challenge=code_challenge,
            now=now_iso(),
            expires_at=later_iso(self.code_ttl),
        )
        return code

    async def redeem_code(
        self, *, code: str, client_id: str, redirect_uri: str | None, code_verifier: str
    ) -> TokenPair:
        """Exchange a code for tokens, atomically; any mismatch is ``invalid_grant``.

        ``redirect_uri`` may be omitted by the client (OAuth 2.1 drops it when PKCE is
        used, and PKCE is always used here); when present it must match the request.
        """
        code_hash = hash_secret(code or "")

        async def work(tx: Tx) -> TokenPair | _Refusal:
            row = await tx.one(
                """
                MATCH (ac:AuthorizationCode {code_hash: $code_hash})-[:FOR]->(u:User), (ac)-[:ISSUED_TO]->(c:Client)
                RETURN properties(ac) AS code, u.id AS user_id, u.disabled AS user_disabled,
                       c.client_id AS client_id, c.disabled AS client_disabled
                """,
                code_hash=code_hash,
            )
            if row is None:
                return _Refusal(GrantError("invalid_grant", "unknown authorization code"))
            stored = row["code"]
            if stored.get("spent"):
                # A replayed code: everything the first redemption produced must go.
                return _Refusal(
                    GrantError("invalid_grant", "authorization code already used"),
                    revoke_code_hash=code_hash,
                    delete_code_hash=code_hash,
                )
            if stored["expires_at"] <= now_iso():
                return _Refusal(GrantError("invalid_grant", "authorization code expired"), delete_code_hash=code_hash)
            if row["client_id"] != client_id:
                return _Refusal(GrantError("invalid_grant", "authorization code was issued to another client"))
            if redirect_uri is not None and stored["redirect_uri"] != redirect_uri:
                return _Refusal(GrantError("invalid_grant", "redirect_uri does not match the authorization request"))
            if not pkce.verify(code_verifier, stored["code_challenge"]):
                return _Refusal(GrantError("invalid_grant", "PKCE code_verifier does not match"))
            if row["user_disabled"] or row["client_disabled"]:
                return _Refusal(GrantError("invalid_grant", "account or client is disabled"))
            await tx.run(
                "MATCH (ac:AuthorizationCode {code_hash: $code_hash}) SET ac.spent = true", code_hash=code_hash
            )
            return await self._issue_pair(
                tx,
                user_id=row["user_id"],
                client_id=client_id,
                scope=stored["scope"],
                family_id=new_id(),
                code_hash=code_hash,
            )

        return await self._apply(await self.graph.write(work))

    # -- token pairs ----------------------------------------------------------------

    async def _issue_pair(
        self, tx: Tx, *, user_id: str, client_id: str, scope: str, family_id: str, code_hash: str | None
    ) -> TokenPair:
        access = new_secret()
        refresh = new_secret()
        now = now_iso()
        await tx.run(
            """
            MATCH (u:User {id: $user_id}), (c:Client {client_id: $client_id})
            CREATE (at:AccessToken {
                token_hash: $access_hash, scope: $scope, family_id: $family_id, code_hash: $code_hash,
                created_at: $now, expires_at: $access_expires
            })
            CREATE (rt:RefreshToken {
                token_hash: $refresh_hash, scope: $scope, family_id: $family_id, code_hash: $code_hash,
                created_at: $now, expires_at: $refresh_expires, spent: false
            })
            CREATE (at)-[:FOR]->(u) CREATE (at)-[:ISSUED_TO]->(c)
            CREATE (rt)-[:FOR]->(u) CREATE (rt)-[:ISSUED_TO]->(c)
            """,
            user_id=user_id,
            client_id=client_id,
            access_hash=hash_secret(access),
            refresh_hash=hash_secret(refresh),
            scope=scope,
            family_id=family_id,
            code_hash=code_hash,
            now=now,
            access_expires=later_iso(self.access_ttl),
            refresh_expires=later_iso(self.refresh_ttl),
        )
        return TokenPair(access_token=access, refresh_token=refresh, expires_in=self.access_ttl, scope=scope)

    async def refresh(self, *, refresh_token: str, client_id: str) -> TokenPair:
        """Rotate a refresh token. Reuse of a spent token revokes its whole family."""
        token_hash = hash_secret(refresh_token or "")

        async def work(tx: Tx) -> TokenPair | _Refusal:
            row = await tx.one(
                """
                MATCH (rt:RefreshToken {token_hash: $token_hash})-[:FOR]->(u:User), (rt)-[:ISSUED_TO]->(c:Client)
                RETURN properties(rt) AS token, u.id AS user_id, u.disabled AS user_disabled,
                       c.client_id AS client_id, c.disabled AS client_disabled
                """,
                token_hash=token_hash,
            )
            if row is None:
                return _Refusal(GrantError("invalid_grant", "unknown refresh token"))
            stored = row["token"]
            if stored.get("spent"):
                return _Refusal(
                    GrantError("invalid_grant", "refresh token reuse detected; all tokens of this session are revoked"),
                    revoke_family_id=stored["family_id"],
                )
            if row["client_id"] != client_id:
                return _Refusal(GrantError("invalid_grant", "refresh token was issued to another client"))
            if stored["expires_at"] <= now_iso() or row["user_disabled"] or row["client_disabled"]:
                return _Refusal(
                    GrantError("invalid_grant", "refresh token expired or account disabled"),
                    revoke_family_id=stored["family_id"],
                )
            await tx.run("MATCH (rt:RefreshToken {token_hash: $token_hash}) SET rt.spent = true", token_hash=token_hash)
            # The previous access tokens of the family are no longer needed.
            await tx.run(
                "MATCH (at:AccessToken {family_id: $family_id}) DETACH DELETE at", family_id=stored["family_id"]
            )
            pair = await self._issue_pair(
                tx,
                user_id=row["user_id"],
                client_id=client_id,
                scope=stored["scope"],
                family_id=stored["family_id"],
                code_hash=stored.get("code_hash"),
            )
            # Keep the absolute lifetime of the family: a rotated refresh token never outlives the first one.
            await tx.run(
                """
                MATCH (rt:RefreshToken {family_id: $family_id, spent: false})
                SET rt.expires_at = CASE WHEN rt.expires_at > $family_expires THEN $family_expires ELSE rt.expires_at END
                """,
                family_id=stored["family_id"],
                family_expires=stored.get("family_expires_at", stored["expires_at"]),
            )
            return pair

        return await self._apply(await self.graph.write(work))

    async def _apply(self, outcome: TokenPair | _Refusal) -> TokenPair:
        """Commit any revocation a refusal asks for, then raise it; or return the pair."""
        if isinstance(outcome, TokenPair):
            return outcome
        if outcome.revoke_code_hash:
            await self.graph.run(
                "MATCH (t) WHERE (t:AccessToken OR t:RefreshToken) AND t.code_hash = $code_hash DETACH DELETE t",
                code_hash=outcome.revoke_code_hash,
            )
        if outcome.revoke_family_id:
            await self.graph.run(
                "MATCH (t) WHERE (t:AccessToken OR t:RefreshToken) AND t.family_id = $family_id DETACH DELETE t",
                family_id=outcome.revoke_family_id,
            )
        if outcome.delete_code_hash:
            await self.graph.run(
                "MATCH (ac:AuthorizationCode {code_hash: $code_hash}) DETACH DELETE ac",
                code_hash=outcome.delete_code_hash,
            )
        raise outcome.error

    # -- validation and revocation -------------------------------------------------------

    async def principal(self, access_token: str) -> Principal | None:
        row = await self.graph.one(
            """
            MATCH (at:AccessToken {token_hash: $token_hash})-[:FOR]->(u:User), (at)-[:ISSUED_TO]->(c:Client)
            WHERE at.expires_at > $now AND coalesce(u.disabled, false) = false AND coalesce(c.disabled, false) = false
            RETURN at.scope AS scope, u.id AS user_id, u.username AS username, u.full_name AS full_name,
                   u.is_admin AS is_admin, c.client_id AS client_id
            """,
            token_hash=hash_secret(access_token),
            now=now_iso(),
        )
        if row is None:
            return None
        return Principal(
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["full_name"] or row["username"],
            is_admin=bool(row["is_admin"]),
            client_id=row["client_id"],
            scopes=tuple((row["scope"] or "").split()),
            token_hash=hash_secret(access_token),
        )

    async def revoke(self, token: str, *, client_id: str) -> bool:
        """Revoke an access token, or a refresh token with its whole family (RFC 7009)."""
        token_hash = hash_secret(token or "")

        async def work(tx: Tx) -> bool:
            row = await tx.one(
                """
                MATCH (t)-[:ISSUED_TO]->(c:Client {client_id: $client_id})
                WHERE (t:AccessToken OR t:RefreshToken) AND t.token_hash = $token_hash
                RETURN t.family_id AS family_id, labels(t) AS labels
                """,
                token_hash=token_hash,
                client_id=client_id,
            )
            if row is None:
                return False
            if "RefreshToken" in row["labels"]:
                await tx.run(
                    "MATCH (t) WHERE (t:AccessToken OR t:RefreshToken) AND t.family_id = $family_id DETACH DELETE t",
                    family_id=row["family_id"],
                )
            else:
                await tx.run("MATCH (at:AccessToken {token_hash: $token_hash}) DETACH DELETE at", token_hash=token_hash)
            return True

        return await self.graph.write(work)

    async def revoke_all_for_user(self, user_id: str) -> int:
        counters = await self.graph.write(
            lambda tx: tx.counters(
                """
                MATCH (t)-[:FOR]->(:User {id: $user_id})
                WHERE t:AccessToken OR t:RefreshToken OR t:AuthorizationCode OR t:WebSession
                DETACH DELETE t
                """,
                user_id=user_id,
            )
        )
        return counters.nodes_deleted

    async def revoke_all_for_client(self, client_id: str) -> int:
        counters = await self.graph.write(
            lambda tx: tx.counters(
                """
                MATCH (t)-[:ISSUED_TO]->(:Client {client_id: $client_id})
                WHERE t:AccessToken OR t:RefreshToken OR t:AuthorizationCode
                DETACH DELETE t
                """,
                client_id=client_id,
            )
        )
        return counters.nodes_deleted

    async def sessions_for_user(self, user_id: str) -> list[dict]:
        """Active refresh-token families per client, for "my account" and the admin UI."""
        return await self.graph.run(
            """
            MATCH (rt:RefreshToken {spent: false})-[:FOR]->(:User {id: $user_id}), (rt)-[:ISSUED_TO]->(c:Client)
            WHERE rt.expires_at > $now
            RETURN rt.family_id AS family_id, c.client_id AS client_id, c.name AS client_name,
                   rt.scope AS scope, rt.created_at AS created_at, rt.expires_at AS expires_at
            ORDER BY rt.created_at DESC
            """,
            user_id=user_id,
            now=now_iso(),
        )

    async def revoke_family(self, family_id: str, *, user_id: str) -> bool:
        counters = await self.graph.write(
            lambda tx: tx.counters(
                """
                MATCH (t)-[:FOR]->(:User {id: $user_id})
                WHERE (t:AccessToken OR t:RefreshToken) AND t.family_id = $family_id
                DETACH DELETE t
                """,
                family_id=family_id,
                user_id=user_id,
            )
        )
        return counters.nodes_deleted > 0
