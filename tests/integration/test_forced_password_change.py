# This file was generated with the assistance of an AI coding tool.
"""A password someone else knows is good for one thing: changing it. Nothing else opens before that."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from opencde.auth import pkce
from opencde.bootstrap import make_graph
from opencde.settings import Settings
from opencde.store.accounts.users import UserRepository
from tests.integration.conftest_accounts import World, build_world
from tests.integration.test_web_signin import form_token

pytestmark = [pytest.mark.integration, pytest.mark.security]

CHOSEN = "correct-horse-battery-staple-2026"
VERIFIER = "v" * 50


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


@pytest.fixture
def one_time(settings: Settings, world: World) -> str:
    """The viewer's password was reset by an administrator, so it has to be changed."""

    async def reset() -> None:
        graph = make_graph(settings)
        try:
            users = UserRepository(graph)
            user = await users.get_by_username("viewer")
            assert user is not None
            await users.set_password(user.id, world.password, must_change=True)
        finally:
            await graph.close()

    asyncio.run(reset())
    return world.password


def _authorize_params(world: World) -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": world.public_client_id,
        "redirect_uri": world.redirect,
        "state": "s1",
        "code_challenge": pkce.challenge_for(VERIFIER),
        "code_challenge_method": "S256",
        "scope": "bcf",
    }


def _submit_authorization(client: TestClient, world: World, password: str, url: str = "/foundation/oauth2/auth"):
    page = client.get(url, params=_authorize_params(world) if url.endswith("/auth") else None)
    assert page.status_code == 200, page.text
    return client.post(
        "/foundation/oauth2/auth",
        data={"form_token": form_token(page.text), "username": "viewer", "password": password, "decision": "allow"},
        follow_redirects=False,
    )


def _change_form(client: TestClient, url: str) -> tuple[str, str]:
    page = client.get(url)
    assert page.status_code == 200
    action = re.search(r'action="([^"]*)"[^>]*class="stack"', page.text)
    assert action is not None
    return action.group(1).replace("&amp;", "&"), form_token(page.text)


def _change(client: TestClient, url: str, *, current: str, new: str = CHOSEN, repeat: str | None = None):
    action, token = _change_form(client, url)
    return client.post(
        action,
        data={
            "form_token": token,
            "action": "change_password",
            "current_password": current,
            "new_password": new,
            "repeat_password": repeat or new,
        },
        follow_redirects=False,
    )


def test_a_client_gets_no_code_for_a_password_that_has_to_change(
    client: TestClient, world: World, one_time: str
) -> None:
    refused = _submit_authorization(client, world, one_time)
    assert refused.status_code == 303
    target = urlsplit(refused.headers["location"])
    assert target.path == "/account", "no code, and no way back to the client yet"
    assert parse_qs(target.query)["notice"] == ["change_password"]
    # The page is a step in the client's popup, so it must not cut the way back to the window that opened it.
    assert client.get(refused.headers["location"]).headers["cross-origin-opener-policy"] == "unsafe-none"
    assert client.get("/account").headers["cross-origin-opener-policy"] == "same-origin"

    # Back on the way to the client, whatever goes wrong on the way.
    wrong = _change(client, refused.headers["location"], current="not-the-password")
    assert wrong.status_code == 303 and parse_qs(urlsplit(wrong.headers["location"]).query)["notice"] == [
        "wrong_password"
    ]
    assert "next=" in wrong.headers["location"]
    mismatch = _change(client, refused.headers["location"], current=one_time, repeat=CHOSEN + "x")
    assert mismatch.status_code == 400 and "next=" in re.search(
        r'action="([^"]*)"[^>]*class="stack"', mismatch.text
    ).group(1)  # type: ignore[union-attr]

    changed = _change(client, refused.headers["location"], current=one_time)
    assert changed.status_code == 303
    again = urlsplit(changed.headers["location"])
    assert again.path == "/foundation/oauth2/auth"
    assert parse_qs(again.query)["code_challenge"] == [pkce.challenge_for(VERIFIER)]
    assert parse_qs(again.query)["state"] == ["s1"]

    client.cookies.clear()
    assert _submit_authorization(client, world, one_time).status_code == 200, "the old password is gone"
    answer = _submit_authorization(client, world, CHOSEN)
    assert answer.status_code == 302
    query = parse_qs(urlsplit(answer.headers["location"]).query)
    assert query["state"] == ["s1"] and query["code"]
    token = client.post(
        "/foundation/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "code_verifier": VERIFIER,
            "client_id": world.public_client_id,
            "redirect_uri": world.redirect,
        },
    )
    assert token.status_code == 201, token.text


def test_the_pages_wait_for_the_new_password_too(client: TestClient, world: World, settings: Settings) -> None:
    async def reset() -> None:
        graph = make_graph(settings)
        try:
            users = UserRepository(graph)
            user = await users.get_by_username("admin")
            assert user is not None
            await users.set_password(user.id, world.password, must_change=True)
        finally:
            await graph.close()

    asyncio.run(reset())
    page = client.get("/signin", params={"next": "/admin/users"})
    signed_in = client.post(
        "/signin",
        data={"form_token": form_token(page.text), "username": "admin", "password": world.password},
        follow_redirects=False,
    )
    target = urlsplit(signed_in.headers["location"])
    assert target.path == "/account" and parse_qs(target.query)["next"] == ["/admin/users"]

    detour = client.get("/admin/projects", follow_redirects=False)
    assert detour.status_code == 302, "typing another address does not get around it"
    assert parse_qs(urlsplit(detour.headers["location"]).query)["next"] == ["/admin/projects"]
    upload = client.get(f"/documents/1.0/upload-ui/{'x' * 40}", follow_redirects=False)
    assert upload.status_code == 302 and urlsplit(upload.headers["location"]).path == "/account"

    changed = _change(client, signed_in.headers["location"], current=world.password)
    assert changed.status_code == 303 and changed.headers["location"] == "/admin/users"
    assert client.get("/admin/users").status_code == 200


@pytest.mark.parametrize("target", ["https://evil.example/", "//evil.example/", "/\\evil.example"])
def test_changing_a_password_leads_only_to_this_server(
    client: TestClient, world: World, one_time: str, target: str
) -> None:
    page = client.get("/signin")
    client.post(
        "/signin",
        data={"form_token": form_token(page.text), "username": "viewer", "password": one_time},
        follow_redirects=False,
    )
    url = client.build_request("GET", "/account", params={"notice": "change_password", "next": target}).url
    changed = _change(client, f"{url.path}?{url.query.decode()}", current=one_time)
    assert changed.status_code == 303 and changed.headers["location"] == "/account?notice=password_changed"
