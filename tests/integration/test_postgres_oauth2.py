# This file was generated with the assistance of an AI coding tool.
"""The OAuth2 area in PostgreSQL (ADR 0029) against a real database: the same tests on the graph's repositories and on
PostgreSQL's, PostgreSQL's own (the cleaner, the foreign keys, two requests with one code or token at once), and the
existing tests of the OAuth2 flow over HTTP with the app's OAuth2 and accounts in PostgreSQL.

Each case runs once on the graph (on every graph the session has) and once on PostgreSQL, which needs no graph:
``-k on_postgresql`` starts PostgreSQL alone. The flow over HTTP needs both, since the audit log is still the graph's.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from asyncpg.exceptions import CheckViolationError
from fastapi.testclient import TestClient
from pydantic import SecretStr

from opencde.auth import pkce
from opencde.graph.graph import Graph
from opencde.main import create_app
from opencde.postgres.cleanup import delete_expired
from opencde.postgres.database import Postgres
from opencde.settings import Settings
from opencde.store.accounts.postgres import (
    PostgresProjectRepository,
    PostgresUserRepository,
    PostgresWebSessionRepository,
)
from opencde.store.accounts.sessions import WebSessionRepository
from opencde.store.accounts.users import UserRepository
from opencde.store.oauth2.clients import ClientError, ClientRepository
from opencde.store.oauth2.postgres import PostgresClientRepository, PostgresTokenRepository
from opencde.store.oauth2.tokens import GrantError, TokenRepository
from opencde.store.protocols import ClientStore, TokenStore, UserStore, WebSessionStore
from opencde.timeutil import later_iso
from tests.integration import test_oauth2 as flow
from tests.integration import test_security_oauth2 as attacks
from tests.integration.conftest import PostgresTarget, emptied_postgres
from tests.integration.conftest_accounts import World, populate

pytestmark = pytest.mark.integration

PASSWORD = "a-long-and-strong-passphrase"
REDIRECT = "http://127.0.0.1/callback"
MCP = "http://testserver/mcp"
VERIFIER = "v" * 50
CHALLENGE = pkce.challenge_for(VERIFIER)
TTLS = {"code_ttl": 60, "access_ttl": 3600, "refresh_ttl": 30 * 86400, "refresh_idle": 7 * 86400}


@dataclass(frozen=True)
class OAuth2:
    users: UserStore
    clients: ClientStore
    sessions: WebSessionStore
    make_tokens: Callable[..., TokenStore]

    def tokens(self, **ttls: int) -> TokenStore:
        """The token repository, with the TTLs of ``TTLS`` unless told otherwise."""
        return self.make_tokens(**(TTLS | ttls))


async def _refused(work: Awaitable[Any], error: str, words: str) -> None:
    with pytest.raises(GrantError, match=words) as refused:
        await work
    assert refused.value.error == error


async def _signed_in(oauth2: OAuth2, user_id: str, client_id: str, tokens: TokenStore | None = None, **code: Any):
    """A code for the user through the client, with PKCE unless told otherwise, redeemed for a pair."""
    tokens = tokens or oauth2.tokens()
    issued = await tokens.issue_code(
        user_id=user_id,
        client_id=client_id,
        redirect_uri=REDIRECT,
        scope=code.pop("scope", "profile bcf documents"),
        code_challenge=code.pop("code_challenge", CHALLENGE),
        **code,
    )
    return await tokens.redeem_code(code=issued, client_id=client_id, redirect_uri=None, code_verifier=VERIFIER)


# -- the same on both ----------------------------------------------------------------------------------------------


async def clients_secrets_and_redirects(oauth2: OAuth2) -> None:
    clients = oauth2.clients
    confidential, secret = await clients.create(
        " Server app ", ["https://app.example.test/cb", "https://app.example.test/cb"], public=False, description="A"
    )
    assert secret is not None and len(secret) >= 40
    assert confidential.name == "Server app" and confidential.redirect_uris == ["https://app.example.test/cb"]
    assert confidential.is_confidential and not confidential.dynamic and confidential.expires_at is None
    assert await clients.authenticate(confidential.client_id, secret) == confidential
    assert await clients.authenticate(confidential.client_id, "wrong") is None
    assert await clients.authenticate(confidential.client_id, None) is None
    assert await clients.authenticate("00000000-0000-4000-8000-000000000000", secret) is None

    public, none = await clients.create("Native app", ["http://127.0.0.1/cb", "myapp://callback"], public=True)
    assert none is None and public.is_public
    assert await clients.authenticate(public.client_id, None) == public
    assert await clients.authenticate(public.client_id, "anything") is None, "public clients never present a secret"
    named, _ = await clients.create("Named", [REDIRECT], public=True, client_id="6F3C2B5E-8D1A-4C2E-9F7B-1A2B3C4D5E6F")
    assert named.client_id == "6f3c2b5e-8d1a-4c2e-9f7b-1a2b3c4d5e6f"

    for uri, words in (
        ("http://example.test/cb", "loopback"),
        ("https://example.test/cb#frag", "fragment"),
        ("javascript:alert(1)", "unsafe"),
    ):
        with pytest.raises(ClientError, match=words):
            await clients.create("Bad", [uri], public=True)
    with pytest.raises(ClientError, match="cannot do without PKCE"):
        await clients.create("Bad", [REDIRECT], public=True, pkce_optional=True)
    with pytest.raises(ClientError, match="cannot upload headless"):
        await clients.update(public.client_id, headless_uploads=True)
    with pytest.raises(ClientError, match="public clients have no secret"):
        await clients.rotate_secret(public.client_id)
    with pytest.raises(ClientError, match="no such client"):
        await clients.update("no-such-client", name="x")

    rotated = await clients.rotate_secret(confidential.client_id)
    assert await clients.authenticate(confidential.client_id, secret) is None
    assert await clients.authenticate(confidential.client_id, rotated) is not None
    changed = await clients.update(
        confidential.client_id,
        name="  Server application  ",
        redirect_uris=["https://app.example.test/b", "https://app.example.test/b"],
        pkce_optional=True,
        headless_uploads=True,
    )
    assert changed.name == "Server application" and changed.redirect_uris == ["https://app.example.test/b"]
    assert changed.pkce_optional and changed.headless_uploads and changed.description == "A", "None keeps a value"
    await clients.update(confidential.client_id, disabled=True)
    assert await clients.authenticate(confidential.client_id, rotated) is None, "a disabled client does not sign in"
    assert [c.name for c in await clients.all()] == ["Named", "Native app", "Server application"]
    assert await clients.delete(confidential.client_id) and not await clients.delete(confidential.client_id)
    assert await clients.get(confidential.client_id) is None


async def self_registered_clients_wait_expire_and_are_pruned(oauth2: OAuth2) -> None:
    clients, users = oauth2.clients, oauth2.users
    stale, _ = await clients.create(
        "Old app", ["https://a.test/cb"], public=True, dynamic=True, expires_at=later_iso(-60), software_id=" app "
    )
    fresh, _ = await clients.create(
        "Fresh app", ["https://b.test/cb"], public=False, dynamic=True, expires_at=later_iso(3600), pending=True
    )
    manual, _ = await clients.create("Manual", ["https://c.test/cb"], public=False, expires_at=later_iso(-60))
    assert manual.expires_at is None, "only self-registered clients expire"
    assert stale.software_id == "app" and stale.dynamic
    assert fresh.pending and fresh.disabled, "waiting for an administrator"
    approved = await clients.update(fresh.client_id, disabled=False)
    assert not approved.pending and not approved.disabled
    user = await users.create("editor", PASSWORD)
    pair = await _signed_in(oauth2, user.id, fresh.client_id)

    assert await clients.prune_dynamic() == 1, "the stale registration"
    assert await clients.get(stale.client_id) is None and await clients.prune_dynamic() == 0
    await clients.touch(fresh.client_id, expires_at=later_iso(7200))
    await clients.touch(manual.client_id, expires_at=later_iso(7200))
    touched, kept = await clients.get(fresh.client_id), await clients.get(manual.client_id)
    assert touched is not None and touched.expires_at and fresh.expires_at and touched.expires_at > fresh.expires_at
    assert touched.last_used_at is not None
    assert kept is not None and kept.expires_at is None and kept.last_used_at is not None, "a manual client never ages"

    assert await clients.prune_dynamic(all_dynamic=True) == 1, "every self-registered client can be dropped"
    assert await clients.get(fresh.client_id) is None and await clients.get(manual.client_id) is not None
    assert await oauth2.tokens().principal(pair.access_token) is None, "its tokens go with it"


async def a_code_is_redeemed_once_with_pkce_and_a_replay_revokes_its_tokens(oauth2: OAuth2) -> None:
    users, clients, tokens = oauth2.users, oauth2.clients, oauth2.tokens()
    user = await users.create("viewer", PASSWORD, full_name="Viewer")
    public, _ = await clients.create("Native app", [REDIRECT], public=True)
    other, secret = await clients.create("Server app", [REDIRECT], public=False)
    assert secret
    code = await tokens.issue_code(
        user_id=user.id,
        client_id=public.client_id,
        redirect_uri=REDIRECT,
        scope="profile bcf",
        code_challenge=CHALLENGE,
    )

    def redeem(**changes: Any) -> Awaitable[Any]:
        request = {"code": code, "client_id": public.client_id, "redirect_uri": REDIRECT, "code_verifier": VERIFIER}
        return tokens.redeem_code(**(request | changes))

    await _refused(redeem(code="not-a-code"), "invalid_grant", "unknown authorization code")
    await _refused(redeem(code_verifier="w" * 50), "invalid_grant", "PKCE code_verifier does not match")
    await _refused(redeem(code_verifier=None), "invalid_request", "code_verifier is required")
    await _refused(redeem(client_id=other.client_id), "invalid_grant", "issued to another client")
    await _refused(redeem(redirect_uri="http://127.0.0.1/other"), "invalid_grant", "redirect_uri does not match")
    await _refused(redeem(resource=MCP), "invalid_target", "resource does not match")
    pair = await redeem(redirect_uri=None)  # the mismatches above prove no leak, and spend nothing
    assert pair.scope == "profile bcf" and pair.expires_in == TTLS["access_ttl"]
    caller = await tokens.principal(pair.access_token)
    assert caller is not None and caller.username == "viewer" and caller.display_name == "Viewer"
    assert caller.scopes == ("profile", "bcf") and caller.client_id == public.client_id and not caller.is_admin
    assert caller.auth_time is not None and caller.resource is None and caller.token_hash != pair.access_token
    assert await tokens.principal(pair.refresh_token) is None, "a refresh token is no access token"

    await _refused(redeem(), "invalid_grant", "authorization code already used")
    assert await tokens.principal(pair.access_token) is None, "what the first redemption produced is gone"
    refreshed = tokens.refresh(refresh_token=pair.refresh_token, client_id=public.client_id)
    await _refused(refreshed, "invalid_grant", "unknown refresh token")
    await _refused(redeem(), "invalid_grant", "unknown authorization code")


async def a_code_without_pkce_is_for_a_marked_client_alone(oauth2: OAuth2) -> None:
    users, clients, tokens = oauth2.users, oauth2.clients, oauth2.tokens()
    user = await users.create("editor", PASSWORD)
    older, _ = await clients.create("An older client", [REDIRECT], public=False, pkce_optional=True)
    unmarked, _ = await clients.create("Server app", [REDIRECT], public=False)

    async def code(client_id: str) -> str:
        return await tokens.issue_code(
            user_id=user.id,
            client_id=client_id,
            redirect_uri=REDIRECT,
            scope="bcf",
            code_challenge=None,
            redirect_required=True,
        )

    plain = await code(older.client_id)
    request = {"code": plain, "client_id": older.client_id}
    await _refused(
        tokens.redeem_code(**request, redirect_uri=None, code_verifier=None),
        "invalid_grant",
        "redirect_uri is required",
    )
    await _refused(
        tokens.redeem_code(**request, redirect_uri=REDIRECT, code_verifier=VERIFIER),
        "invalid_grant",
        "issued without PKCE",
    )
    pair = await tokens.redeem_code(**request, redirect_uri=REDIRECT, code_verifier=None)
    assert pair.scope == "bcf"
    other = await code(unmarked.client_id)
    await _refused(
        tokens.redeem_code(code=other, client_id=unmarked.client_id, redirect_uri=REDIRECT, code_verifier=None),
        "invalid_grant",
        "issued without PKCE",
    )


async def an_expired_code_is_refused_and_forgotten(oauth2: OAuth2) -> None:
    user = await oauth2.users.create("editor", PASSWORD)
    public, _ = await oauth2.clients.create("Native app", [REDIRECT], public=True)
    expired = oauth2.tokens(code_ttl=-60)
    code = await expired.issue_code(
        user_id=user.id, client_id=public.client_id, redirect_uri=REDIRECT, scope="bcf", code_challenge=CHALLENGE
    )
    request = {"code": code, "client_id": public.client_id, "redirect_uri": None, "code_verifier": VERIFIER}
    await _refused(expired.redeem_code(**request), "invalid_grant", "authorization code expired")
    await _refused(oauth2.tokens().redeem_code(**request), "invalid_grant", "unknown authorization code")


async def a_refresh_rotates_and_a_reuse_revokes_the_family(oauth2: OAuth2) -> None:
    users, clients, tokens = oauth2.users, oauth2.clients, oauth2.tokens()
    user = await users.create("viewer", PASSWORD)
    public, _ = await clients.create("Native app", [REDIRECT], public=True)
    other, _ = await clients.create("Other app", [REDIRECT], public=True)
    first = await _signed_in(oauth2, user.id, public.client_id)
    signed_in = await tokens.principal(first.access_token)
    assert signed_in is not None
    (family,) = await tokens.sessions_for_user(user.id)
    assert family["client_id"] == public.client_id and family["client_name"] == "Native app"
    assert family["scope"] == "profile bcf documents" and family["created_at"] < family["expires_at"]

    await _refused(
        tokens.refresh(refresh_token=first.refresh_token, client_id=other.client_id),
        "invalid_grant",
        "issued to another client",
    )
    await _refused(
        tokens.refresh(refresh_token=first.refresh_token, client_id=public.client_id, resource=MCP),
        "invalid_target",
        "resource does not match the refresh token",
    )
    second = await tokens.refresh(refresh_token=first.refresh_token, client_id=public.client_id)
    assert second.refresh_token != first.refresh_token and second.scope == first.scope
    assert await tokens.principal(first.access_token) is None, "the old access token is gone"
    rotated = await tokens.principal(second.access_token)
    assert rotated is not None and rotated.auth_time == signed_in.auth_time, "a refresh is no new authentication"
    assert [f["family_id"] for f in await tokens.sessions_for_user(user.id)] == [family["family_id"]]

    await _refused(
        tokens.refresh(refresh_token=first.refresh_token, client_id=public.client_id),
        "invalid_grant",
        "reuse detected",
    )
    assert await tokens.principal(second.access_token) is None, "the reuse revokes the whole family"
    await _refused(
        tokens.refresh(refresh_token=second.refresh_token, client_id=public.client_id),
        "invalid_grant",
        "unknown refresh token",
    )
    assert await tokens.sessions_for_user(user.id) == []


async def a_family_keeps_its_binding_and_its_lifetime(oauth2: OAuth2) -> None:
    users, clients = oauth2.users, oauth2.clients
    user = await users.create("editor", PASSWORD)
    public, _ = await clients.create("An AI program", [REDIRECT], public=True)
    short = oauth2.tokens(refresh_ttl=3600)
    code = await short.issue_code(
        user_id=user.id,
        client_id=public.client_id,
        redirect_uri=REDIRECT,
        scope="mcp mcp:propose",
        code_challenge=CHALLENGE,
        resource=MCP,
    )
    request = {"code": code, "client_id": public.client_id, "redirect_uri": None, "code_verifier": VERIFIER}
    await _refused(short.redeem_code(**request, resource="https://evil.example/mcp"), "invalid_target", "resource")
    pair = await short.redeem_code(**request)  # naming none, the tokens are bound as the code is
    caller = await short.principal(pair.access_token)
    assert caller is not None and caller.resource == MCP and caller.scopes == ("mcp", "mcp:propose")
    (first,) = await short.sessions_for_user(user.id)

    long = oauth2.tokens(refresh_ttl=30 * 86400)
    renewed = await long.refresh(refresh_token=pair.refresh_token, client_id=public.client_id)
    bound = await long.principal(renewed.access_token)
    assert bound is not None and bound.resource == MCP, "a refresh keeps the binding"
    (after,) = await long.sessions_for_user(user.id)
    assert after["expires_at"] == first["expires_at"], "a rotated refresh token never outlives the first"
    named = await long.refresh(refresh_token=renewed.refresh_token, client_id=public.client_id, resource=MCP)
    assert named.scope == "mcp mcp:propose", "naming its own resource is fine"


async def an_idle_token_or_a_disabled_account_ends_the_family(oauth2: OAuth2) -> None:
    users, clients, tokens = oauth2.users, oauth2.clients, oauth2.tokens()
    user = await users.create("viewer", PASSWORD)
    public, _ = await clients.create("Native app", [REDIRECT], public=True)
    idle = await _signed_in(oauth2, user.id, public.client_id)
    await _refused(
        oauth2.tokens(refresh_idle=-60).refresh(refresh_token=idle.refresh_token, client_id=public.client_id),
        "invalid_grant",
        "expired or account disabled",
    )
    assert await tokens.principal(idle.access_token) is None, "the family is gone"

    lapsed = await _signed_in(oauth2, user.id, public.client_id, tokens=oauth2.tokens(refresh_ttl=-60))
    assert await tokens.sessions_for_user(user.id) == [], "an expired family is no session"
    await _refused(
        tokens.refresh(refresh_token=lapsed.refresh_token, client_id=public.client_id),
        "invalid_grant",
        "expired or account disabled",
    )

    pair = await _signed_in(oauth2, user.id, public.client_id)
    await users.update(user.id, disabled=True)
    assert await tokens.principal(pair.access_token) is None, "a disabled user's token answers for nobody"
    await _refused(
        tokens.refresh(refresh_token=pair.refresh_token, client_id=public.client_id),
        "invalid_grant",
        "expired or account disabled",
    )
    await users.update(user.id, disabled=False)
    assert await tokens.principal(pair.access_token) is None, "and the refusal revoked the family"

    again = await _signed_in(oauth2, user.id, public.client_id)
    await clients.update(public.client_id, disabled=True)
    assert await tokens.principal(again.access_token) is None, "nor a disabled client's"
    issued = await tokens.issue_code(
        user_id=user.id, client_id=public.client_id, redirect_uri=REDIRECT, scope="bcf", code_challenge=CHALLENGE
    )
    await _refused(
        tokens.redeem_code(code=issued, client_id=public.client_id, redirect_uri=None, code_verifier=VERIFIER),
        "invalid_grant",
        "account or client is disabled",
    )


async def tokens_are_revoked_one_family_or_all_at_once(oauth2: OAuth2) -> None:
    users, clients, tokens = oauth2.users, oauth2.clients, oauth2.tokens()
    user, other_user = await users.create("viewer", PASSWORD), await users.create("editor", PASSWORD)
    public, _ = await clients.create("Native app", [REDIRECT], public=True)
    other, _ = await clients.create("Other app", [REDIRECT], public=True)

    pair = await _signed_in(oauth2, user.id, public.client_id)
    assert await tokens.revoke(pair.access_token, client_id=public.client_id), "RFC 7009: an access token"
    assert await tokens.principal(pair.access_token) is None
    assert not await tokens.revoke(pair.refresh_token, client_id=other.client_id), "only by its own client"
    assert not await tokens.revoke("not-a-token", client_id=public.client_id)
    rotated = await tokens.refresh(refresh_token=pair.refresh_token, client_id=public.client_id)
    assert await tokens.revoke(rotated.refresh_token, client_id=public.client_id), "a refresh token, with its family"
    assert await tokens.principal(rotated.access_token) is None
    await _refused(
        tokens.refresh(refresh_token=pair.refresh_token, client_id=public.client_id),
        "invalid_grant",
        "unknown refresh token",
    )

    kept = await _signed_in(oauth2, user.id, public.client_id)
    (family,) = await tokens.sessions_for_user(user.id)
    assert not await tokens.revoke_family(family["family_id"], user_id=other_user.id), "only the user's own"
    assert await tokens.revoke_family(family["family_id"], user_id=user.id)
    assert await tokens.principal(kept.access_token) is None and await tokens.sessions_for_user(user.id) == []

    await _signed_in(oauth2, user.id, public.client_id)  # a spent code, an access and a refresh token
    await tokens.issue_code(
        user_id=user.id, client_id=other.client_id, redirect_uri=REDIRECT, scope="bcf", code_challenge=CHALLENGE
    )
    theirs = await _signed_in(oauth2, other_user.id, other.client_id)
    browser = await oauth2.sessions.create(user.id, "127.0.0.1")
    assert await tokens.revoke_all_for_client(public.client_id) == 5, "its three codes, and the last family's pair"
    assert await tokens.revoke_all_for_user(user.id) == 2, "the user's last code and their browser session"
    assert await oauth2.sessions.resolve(browser) is None
    assert await tokens.principal(theirs.access_token) is not None, "nobody else's"
    assert await tokens.revoke_all_for_user(other_user.id) == 3


CASES = (
    clients_secrets_and_redirects,
    self_registered_clients_wait_expire_and_are_pruned,
    a_code_is_redeemed_once_with_pkce_and_a_replay_revokes_its_tokens,
    a_code_without_pkce_is_for_a_marked_client_alone,
    an_expired_code_is_refused_and_forgotten,
    a_refresh_rotates_and_a_reuse_revokes_the_family,
    a_family_keeps_its_binding_and_its_lifetime,
    an_idle_token_or_a_disabled_account_ends_the_family,
    tokens_are_revoked_one_family_or_all_at_once,
)


def _on_the_graph(graph: Graph) -> OAuth2:
    return OAuth2(
        UserRepository(graph),
        ClientRepository(graph),
        WebSessionRepository(graph, ttl_seconds=3600, idle_seconds=600),
        lambda **ttls: TokenRepository(graph, **ttls),
    )


def _on_postgresql(pg: Postgres) -> OAuth2:
    return OAuth2(
        PostgresUserRepository(pg),
        PostgresClientRepository(pg),
        PostgresWebSessionRepository(pg, ttl_seconds=3600, idle_seconds=600),
        lambda **ttls: PostgresTokenRepository(pg, **ttls),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_the_graph(case: Callable[[OAuth2], Awaitable[None]], graph: Graph) -> None:
    await case(_on_the_graph(graph))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.__name__)
async def test_on_postgresql(case: Callable[[OAuth2], Awaitable[None]], pg: Postgres) -> None:
    await case(_on_postgresql(pg))


# -- PostgreSQL's own ----------------------------------------------------------------------------------------------


async def _count(pg: Postgres, statement: str) -> int:
    row = await pg.one(statement)
    return int(row["n"]) if row else 0


async def test_on_postgresql_expired_codes_tokens_and_registrations_are_deleted(pg: Postgres) -> None:
    oauth2 = _on_postgresql(pg)
    user = await oauth2.users.create("editor", PASSWORD)
    public, _ = await oauth2.clients.create("Native app", [REDIRECT], public=True)
    stale, _ = await oauth2.clients.create(
        "Old app", ["https://a.test/cb"], public=True, dynamic=True, expires_at=later_iso(-60)
    )
    await _signed_in(oauth2, user.id, public.client_id, tokens=oauth2.tokens(access_ttl=-60, refresh_ttl=-60))
    await oauth2.tokens(code_ttl=-60).issue_code(
        user_id=user.id, client_id=public.client_id, redirect_uri=REDIRECT, scope="bcf", code_challenge=CHALLENGE
    )
    alive = await _signed_in(oauth2, user.id, public.client_id)
    await _signed_in(oauth2, user.id, stale.client_id)  # what an expiring client was given goes with it

    assert await delete_expired(pg) == 4, "a code, an access token, a refresh token and a registration"
    assert await oauth2.clients.get(stale.client_id) is None
    assert await _count(pg, "SELECT count(*) AS n FROM authorization_codes") == 2, "the redeemed ones that last"
    assert await _count(pg, "SELECT count(*) AS n FROM access_tokens") == 1
    assert await _count(pg, "SELECT count(*) AS n FROM refresh_tokens") == 1
    assert await oauth2.tokens().principal(alive.access_token) is not None


async def test_on_postgresql_a_users_deletion_takes_what_was_issued_to_them(pg: Postgres) -> None:
    oauth2 = _on_postgresql(pg)
    user = await oauth2.users.create("editor", PASSWORD)
    public, _ = await oauth2.clients.create("Native app", [REDIRECT], public=True)
    await _signed_in(oauth2, user.id, public.client_id)
    assert await oauth2.users.delete(user.id)
    for statement in (
        "SELECT count(*) AS n FROM authorization_codes",
        "SELECT count(*) AS n FROM access_tokens",
        "SELECT count(*) AS n FROM refresh_tokens",
    ):
        assert await _count(pg, statement) == 0, statement
    assert await oauth2.clients.get(public.client_id) is not None, "the client stays"


async def test_on_postgresql_a_taken_client_id_and_a_public_secret_are_refused(pg: Postgres) -> None:
    clients = PostgresClientRepository(pg)
    first, _ = await clients.create("First", [REDIRECT], public=True)
    with pytest.raises(ClientError, match="not created"):
        await clients.create("Second", [REDIRECT], public=True, client_id=first.client_id)
    with pytest.raises(CheckViolationError, match="oauth_clients_public"):  # the rule holds in the table too
        await pg.execute("UPDATE oauth_clients SET secret_hash = 'h' WHERE client_id = $1", first.client_id)


async def test_on_postgresql_two_requests_with_one_code_or_token_take_their_turns(pg: Postgres) -> None:
    """A code or a refresh token is read ``FOR UPDATE``: of two requests at once, the second is the replay it is, and
    revokes what the first was given."""
    oauth2 = _on_postgresql(pg)
    tokens = oauth2.tokens()
    user = await oauth2.users.create("editor", PASSWORD)
    public, _ = await oauth2.clients.create("Native app", [REDIRECT], public=True)
    code = await tokens.issue_code(
        user_id=user.id, client_id=public.client_id, redirect_uri=REDIRECT, scope="bcf", code_challenge=CHALLENGE
    )
    request = {"code": code, "client_id": public.client_id, "redirect_uri": None, "code_verifier": VERIFIER}
    answers = await asyncio.gather(tokens.redeem_code(**request), tokens.redeem_code(**request), return_exceptions=True)
    (pair,) = [answer for answer in answers if not isinstance(answer, BaseException)]
    (refusal,) = [answer for answer in answers if isinstance(answer, GrantError)]
    assert "already used" in refusal.description and await tokens.principal(pair.access_token) is None

    fresh = await _signed_in(oauth2, user.id, public.client_id)
    use = {"refresh_token": fresh.refresh_token, "client_id": public.client_id}
    answers = await asyncio.gather(tokens.refresh(**use), tokens.refresh(**use), return_exceptions=True)
    (rotated,) = [answer for answer in answers if not isinstance(answer, BaseException)]
    (reuse,) = [answer for answer in answers if isinstance(answer, GrantError)]
    assert "reuse detected" in reuse.description and await tokens.principal(rotated.access_token) is None


# -- the flow over HTTP, with the OAuth2 and the accounts in PostgreSQL ------------------------------------------------

#: The existing tests of the flow that reach the store through the app alone.
FLOW = (
    flow.test_public_client_flow_with_pkce,
    flow.test_confidential_client_flow_with_basic_auth_and_scopes,
    flow.test_token_response_is_never_cached_and_has_spec_fields,
    flow.test_refresh_rotates_and_reuse_revokes_the_family,
    flow.test_code_is_single_use_and_replay_revokes_tokens,
    flow.test_revocation,
    flow.test_wrong_password_shows_the_form_again_without_redirect,
    attacks.test_unregistered_redirect_uri_is_shown_not_followed,
    attacks.test_loopback_port_may_vary_but_host_may_not,
    attacks.test_pkce_is_mandatory_and_plain_is_refused,
    attacks.test_wrong_verifier_wrong_client_and_wrong_redirect_are_invalid_grant,
    attacks.test_client_authentication_failures,
    attacks.test_passwords_and_codes_never_reach_the_logs,
)


@pytest.fixture
def pg_settings(settings: Settings, postgres_target: PostgresTarget) -> Settings:
    return settings.model_copy(
        update={"store_url": postgres_target.url, "store_password": SecretStr(postgres_target.password)}
    )


@pytest.fixture
def pg_world(clean_database: None, postgres_target: PostgresTarget) -> World:
    """The world in PostgreSQL alone: the graph has no user to issue a code for, so a flow that passes ran there."""

    async def build() -> World:
        postgres = await emptied_postgres(postgres_target)
        try:
            users, projects = PostgresUserRepository(postgres), PostgresProjectRepository(postgres)
            return await populate(users, projects, PostgresClientRepository(postgres))
        finally:
            await postgres.close()

    return asyncio.run(build())


@pytest.fixture
def pg_client(pg_settings: Settings, pg_world: World) -> Iterator[TestClient]:
    with TestClient(create_app(pg_settings, startup_wait_seconds=30)) as client:
        yield client


@pytest.mark.parametrize("case", FLOW, ids=lambda case: case.__name__.removeprefix("test_"))
def test_the_flow_with_postgresql(
    case: Callable[..., None], pg_client: TestClient, pg_world: World, caplog: pytest.LogCaptureFixture
) -> None:
    given = {"client": pg_client, "world": pg_world, "caplog": caplog}
    case(**{name: given[name] for name in inspect.signature(case).parameters})
