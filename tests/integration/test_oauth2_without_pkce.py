# This file was generated with the assistance of an AI coding tool.
"""A client that cannot use PKCE: BCF API 2.1's OAuth2 example to the letter, and what keeps it safe.

The example (``OAuth2Examples.md`` on the ``release_2_1`` branch) sends no redirect URI, no scope and no PKCE, and
asks for its tokens with HTTP Basic and the parameters in the query string. A confidential client an administrator
has marked may do that. Every other client goes on being refused.
"""

from __future__ import annotations

import asyncio
import re
import secrets
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from opencde.accounts.users import UserRepository
from opencde.auth import pkce
from opencde.auth.clients import Client, ClientError, ClientRepository
from opencde.bootstrap import make_graph
from opencde.settings import Settings
from tests.integration.conftest_accounts import REDIRECT, World, build_world, login_with_scope
from tests.integration.helpers import FORM_TOKEN, basic_auth
from tests.integration.test_admin_ui import notice_of, post
from tests.integration.test_forced_password_change import CHOSEN, _change
from tests.integration.test_web_signin import web_sign_in

pytestmark = [pytest.mark.integration, pytest.mark.security]

AUTH = "/foundation/oauth2/auth"
TOKEN = "/foundation/oauth2/token"  # an address


def _with_repository(settings: Settings, work: Any) -> Any:
    async def run() -> Any:
        graph = make_graph(settings)
        try:
            return await work(ClientRepository(graph))
        finally:
            await graph.close()

    return asyncio.run(run())


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


@pytest.fixture
def older(settings: Settings, world: World) -> tuple[Client, str]:
    """A confidential client marked ``pkce_optional``, with its secret."""

    async def work(clients: ClientRepository) -> tuple[Client, str | None]:
        return await clients.create("An older client", [REDIRECT], public=False, pkce_optional=True)

    client, secret = _with_repository(settings, work)
    assert secret
    return client, secret


def _code(client: TestClient, world: World, client_id: str, **extra: str) -> str:
    params = {"response_type": "code", "client_id": client_id, "state": "unique", **extra}
    page = client.get(AUTH, params=params)
    assert page.status_code == 200, page.text[:400]
    token = FORM_TOKEN.search(page.text)
    assert token
    answer = client.post(
        AUTH,
        data={"form_token": token.group(1), "username": "editor", "password": world.password, "decision": "allow"},
        follow_redirects=False,
    )
    assert answer.status_code == 302, answer.text[:400]
    query = parse_qs(urlsplit(answer.headers["location"]).query)
    assert query["state"] == ["unique"]
    return query["code"][0]


def test_the_example_of_bcf_2_1_to_the_letter(client: TestClient, world: World, older: tuple[Client, str]) -> None:
    registered, secret = older
    code = _code(client, world, registered.client_id)
    tokens = client.post(
        f"{TOKEN}?grant_type=authorization_code&code={code}", headers=basic_auth(registered.client_id, secret)
    )
    assert tokens.status_code == 201, tokens.text
    body = tokens.json()
    assert body["token_type"] == "bearer" and body["expires_in"] > 0 and body["refresh_token"]
    bearer = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/bcf/3.0/projects", headers=bearer).status_code == 200

    again = client.post(
        f"{TOKEN}?grant_type=refresh_token&refresh_token={body['refresh_token']}",
        headers=basic_auth(registered.client_id, secret),
    )
    assert again.status_code == 201, again.text
    assert again.json()["refresh_token"] != body["refresh_token"], "one-time-usable, as the example says"


def test_a_code_without_pkce_is_worth_nothing_without_the_secret(
    client: TestClient, world: World, older: tuple[Client, str]
) -> None:
    registered, _secret = older
    code = _code(client, world, registered.client_id)
    url = f"{TOKEN}?grant_type=authorization_code&code={code}"
    assert client.post(url, headers=basic_auth(registered.client_id, "not-the-secret")).status_code == 401
    assert client.post(f"{url}&client_id={registered.client_id}").status_code == 401


def test_only_a_marked_client_may_leave_pkce_out(client: TestClient, world: World) -> None:
    for client_id in (world.public_client_id, world.confidential_client_id):
        answer = client.get(
            AUTH,
            params={"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "state": "s"},
            follow_redirects=False,
        )
        assert answer.status_code == 302
        query = parse_qs(urlsplit(answer.headers["location"]).query)
        assert query["error"] == ["invalid_request"] and "code" not in query


def test_a_public_client_cannot_be_marked(settings: Settings, world: World) -> None:
    async def create(clients: ClientRepository) -> Any:
        return await clients.create("Public", [REDIRECT], public=True, pkce_optional=True)

    with pytest.raises(ClientError):
        _with_repository(settings, create)

    async def update(clients: ClientRepository) -> Any:
        return await clients.update(world.public_client_id, pkce_optional=True)

    with pytest.raises(ClientError):
        _with_repository(settings, update)


def test_a_marked_client_that_uses_pkce_is_held_to_it(
    client: TestClient, world: World, older: tuple[Client, str]
) -> None:
    registered, secret = older
    verifier = secrets.token_urlsafe(48)
    challenge = {"code_challenge": pkce.challenge_for(verifier), "code_challenge_method": "S256"}
    headers = basic_auth(registered.client_id, secret)
    grant = {"grant_type": "authorization_code"}

    code = _code(client, world, registered.client_id, **challenge)
    missing = client.post(TOKEN, data={**grant, "code": code}, headers=headers)
    assert missing.status_code == 400 and missing.json()["error"] == "invalid_request"
    wrong = client.post(TOKEN, data={**grant, "code": code, "code_verifier": "w" * 50}, headers=headers)
    assert wrong.status_code == 400 and wrong.json()["error"] == "invalid_grant"
    right = client.post(TOKEN, data={**grant, "code": code, "code_verifier": verifier}, headers=headers)
    assert right.status_code == 201, right.text

    spoilt = client.get(
        AUTH,
        params={"response_type": "code", "client_id": registered.client_id, "state": "s", "code_challenge": "short"},
        follow_redirects=False,
    )
    assert spoilt.status_code == 302 and "invalid_request" in spoilt.headers["location"]


def test_a_verifier_for_a_code_without_a_challenge_is_refused(
    client: TestClient, world: World, older: tuple[Client, str]
) -> None:
    """RFC 9700 §2.1.1: otherwise someone who stole a code could claim that PKCE was used."""
    registered, secret = older
    code = _code(client, world, registered.client_id)
    answer = client.post(
        TOKEN,
        data={"grant_type": "authorization_code", "code": code, "code_verifier": "v" * 50},
        headers=basic_auth(registered.client_id, secret),
    )
    assert answer.status_code == 400 and answer.json()["error"] == "invalid_grant"


def test_a_named_redirect_uri_must_be_named_again(client: TestClient, world: World, older: tuple[Client, str]) -> None:
    """Without PKCE, RFC 6749 §4.1.3 still holds: it is what ties the code to where it was sent."""
    registered, secret = older
    headers = basic_auth(registered.client_id, secret)
    grant = {"grant_type": "authorization_code"}

    code = _code(client, world, registered.client_id, redirect_uri=REDIRECT)
    left_out = client.post(TOKEN, data={**grant, "code": code}, headers=headers)
    assert left_out.status_code == 400 and left_out.json()["error"] == "invalid_grant"

    code = _code(client, world, registered.client_id, redirect_uri=REDIRECT)
    named = client.post(TOKEN, data={**grant, "code": code, "redirect_uri": REDIRECT}, headers=headers)
    assert named.status_code == 201, named.text


def test_taking_the_mark_away_stops_it(
    client: TestClient, settings: Settings, world: World, older: tuple[Client, str]
) -> None:
    registered, secret = older
    code = _code(client, world, registered.client_id)

    async def update(clients: ClientRepository) -> Any:
        return await clients.update(registered.client_id, pkce_optional=False)

    _with_repository(settings, update)
    issued = client.post(
        f"{TOKEN}?grant_type=authorization_code&code={code}", headers=basic_auth(registered.client_id, secret)
    )
    assert issued.status_code == 400 and issued.json()["error"] == "invalid_grant"
    page = client.get(
        AUTH, params={"response_type": "code", "client_id": registered.client_id, "state": "s"}, follow_redirects=False
    )
    assert page.status_code == 302 and "invalid_request" in page.headers["location"]


def test_the_audit_log_says_that_pkce_was_left_out(client: TestClient, world: World, older: tuple[Client, str]) -> None:
    registered, _secret = older
    _code(client, world, registered.client_id)
    admin = login_with_scope(client, world, "admin", "profile bcf documents admin")
    entries = client.get("/admin/api/audit", params={"type": "auth.code.issued"}, headers=admin.headers).json()
    ours = [entry for entry in entries["items"] if entry.get("client_id") == registered.client_id]
    assert ours, entries
    assert ours[0]["details"]["pkce"] is False


def test_the_administration_can_mark_a_client(client: TestClient, world: World) -> None:
    admin = login_with_scope(client, world, "admin", "profile bcf documents admin")
    created = client.post(
        "/admin/api/clients",
        json={"name": "Older", "redirect_uris": [REDIRECT], "public": False, "pkce_optional": True},
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["pkce_optional"] is True
    client_id = created.json()["client_id"]
    changed = client.patch(f"/admin/api/clients/{client_id}", json={"pkce_optional": False}, headers=admin.headers)
    assert changed.status_code == 200 and changed.json()["pkce_optional"] is False

    refused = client.post(
        "/admin/api/clients",
        json={"name": "Public", "redirect_uris": [REDIRECT], "public": True, "pkce_optional": True},
        headers=admin.headers,
    )
    assert refused.status_code == 400


def test_a_password_that_has_to_change_brings_no_pkce_along(
    client: TestClient, settings: Settings, world: World, older: tuple[Client, str]
) -> None:
    """The flow starts over after the change with what the client asked for, which is neither a challenge nor a URI."""

    async def reset() -> None:
        graph = make_graph(settings)
        try:
            users = UserRepository(graph)
            user = await users.get_by_username("editor")
            assert user is not None
            await users.set_password(user.id, world.password, must_change=True)
        finally:
            await graph.close()

    asyncio.run(reset())
    registered, secret = older
    page = client.get(AUTH, params={"response_type": "code", "client_id": registered.client_id, "state": "unique"})
    token = FORM_TOKEN.search(page.text)
    assert token
    refused = client.post(
        AUTH,
        data={"form_token": token.group(1), "username": "editor", "password": world.password, "decision": "allow"},
        follow_redirects=False,
    )
    assert refused.status_code == 303 and urlsplit(refused.headers["location"]).path == "/account"
    changed = _change(client, refused.headers["location"], current=world.password)
    assert changed.status_code == 303
    again = urlsplit(changed.headers["location"])
    query = parse_qs(again.query)
    assert again.path == AUTH and query["state"] == ["unique"]
    assert "code_challenge" not in query and "code_challenge_method" not in query and "redirect_uri" not in query

    client.cookies.clear()
    page = client.get(changed.headers["location"])
    token = FORM_TOKEN.search(page.text)
    assert token
    answer = client.post(
        AUTH,
        data={"form_token": token.group(1), "username": "editor", "password": CHOSEN, "decision": "allow"},
        follow_redirects=False,
    )
    assert answer.status_code == 302, answer.text[:300]
    code = parse_qs(urlsplit(answer.headers["location"]).query)["code"][0]
    tokens = client.post(
        f"{TOKEN}?grant_type=authorization_code&code={code}", headers=basic_auth(registered.client_id, secret)
    )
    assert tokens.status_code == 201, tokens.text


def test_the_pages_of_the_administration_can_mark_a_client(client: TestClient, world: World) -> None:
    web_sign_in(client, world, "admin", "/admin")
    new = client.get("/admin/clients/new", params={"lang": "en"}).text
    assert 'name="pkce_optional"' in new
    created = post(
        client,
        "/admin/clients",
        new,
        name="Older",
        redirect_uris=REDIRECT,
        kind="confidential",
        pkce_optional="on",
    )
    assert created.status_code == 200, "the page that shows the secret once"
    client_id = next(c for c in re.findall(r"/admin/clients/([0-9a-f-]{36})", created.text))
    page = client.get(f"/admin/clients/{client_id}", params={"lang": "en"}).text
    assert "Without PKCE" in page and re.search(r'name="pkce_optional"[^>]*checked', page)

    saved = post(client, f"/admin/clients/{client_id}", page, action="update", name="Older", redirect_uris=REDIRECT)
    assert notice_of(saved) == "saved"
    page = client.get(f"/admin/clients/{client_id}", params={"lang": "en"}).text
    assert "Without PKCE" not in page, "an unticked box takes the mark away"

    public = post(
        client,
        "/admin/clients",
        client.get("/admin/clients/new", params={"lang": "en"}).text,
        name="Public",
        redirect_uris=REDIRECT,
        kind="public",
        pkce_optional="on",
    )
    assert public.status_code == 400 and "A public client cannot do without PKCE." in public.text
    assert 'name="pkce_optional"' not in client.get(f"/admin/clients/{world.public_client_id}").text
