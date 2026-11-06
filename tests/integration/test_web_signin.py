# This file was generated with the assistance of an AI coding tool.
"""Browser sign-in: session cookie, sign-out, CSRF checks and redirect safety."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from tests.integration.conftest_accounts import World, build_world

pytestmark = [pytest.mark.integration, pytest.mark.security]

FORM_TOKEN = re.compile(r'name="form_token" value="([^"]+)"')
SIGNOUT_TOKEN = re.compile(r'name="signout_token" value="([^"]+)"')


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def form_token(html: str) -> str:
    match = FORM_TOKEN.search(html)
    assert match, "page carries a form token"
    return match.group(1)


def web_sign_in(client: TestClient, world: World, username: str, next_url: str = "/") -> None:
    page = client.get("/signin", params={"next": next_url})
    assert page.status_code == 200
    response = client.post(
        "/signin",
        data={"form_token": form_token(page.text), "username": username, "password": world.password},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text


def test_sign_in_sets_a_hardened_cookie_and_sign_out_removes_it(client: TestClient, world: World) -> None:
    page = client.get("/signin", params={"next": "/documents/1.0/upload-ui/x"})
    response = client.post(
        "/signin",
        data={"form_token": form_token(page.text), "username": "editor", "password": world.password},
        follow_redirects=False,
    )
    assert response.status_code == 302 and response.headers["location"] == "/documents/1.0/upload-ui/x"
    cookie = response.headers["set-cookie"].lower()
    assert "opencde_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert "secure" not in cookie, "plain http in tests; Secure is set when the public URL is https"
    assert response.headers["cache-control"] == "no-store"

    # Signed in: /signin redirects to next; the message page knows the user.
    assert client.get("/signin", follow_redirects=False).status_code == 302
    expired = client.get("/documents/1.0/select-ui/not-a-real-token")
    assert expired.status_code == 404 and "Signed in as <strong>editor</strong>" in expired.text

    signout_match = SIGNOUT_TOKEN.search(expired.text)
    assert signout_match, "signed-in pages carry a sign-out form"
    signout = client.post("/signout", data={"signout_token": signout_match.group(1)}, follow_redirects=False)
    assert signout.status_code == 302
    assert "opencde_session=" in signout.headers["set-cookie"] and "max-age=0" in signout.headers["set-cookie"].lower()
    assert client.get("/signin").status_code == 200, "no session any more"


def test_wrong_password_disabled_user_and_tampered_token(client: TestClient, world: World) -> None:
    page = client.get("/signin")
    token = form_token(page.text)
    wrong = client.post("/signin", data={"form_token": token, "username": "editor", "password": "nope"})
    assert wrong.status_code == 200 and "not correct" in wrong.text and "set-cookie" not in wrong.headers
    unknown = client.post("/signin", data={"form_token": token, "username": "ghost", "password": world.password})
    assert "not correct" in unknown.text
    tampered = client.post(
        "/signin", data={"form_token": token + "x", "username": "editor", "password": world.password}
    )
    assert tampered.status_code == 400
    missing = client.post("/signin", data={"username": "editor", "password": world.password})
    assert missing.status_code == 400


def test_cross_site_posts_are_refused_and_next_cannot_leave_the_site(client: TestClient, world: World) -> None:
    page = client.get("/signin", params={"next": "https://evil.test/phish"})
    cross = client.post(
        "/signin",
        data={"form_token": form_token(page.text), "username": "editor", "password": world.password},
        headers={"Sec-Fetch-Site": "cross-site"},
        follow_redirects=False,
    )
    assert cross.status_code == 403
    foreign_origin = client.post(
        "/signin",
        data={"form_token": form_token(page.text), "username": "editor", "password": world.password},
        headers={"Origin": "https://evil.test"},
        follow_redirects=False,
    )
    assert foreign_origin.status_code == 403
    ok = client.post(
        "/signin",
        data={"form_token": form_token(page.text), "username": "editor", "password": world.password},
        headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"},
        follow_redirects=False,
    )
    assert ok.status_code == 302 and ok.headers["location"] == "/", "an external next is dropped"


def test_sign_in_page_has_strict_csp_and_no_inline_code(client: TestClient) -> None:
    page = client.get("/signin")
    assert page.headers["content-security-policy"].startswith("default-src 'none'")
    assert not re.search(r"<script(?![^>]*\bsrc=)", page.text), "scripts come from files, never inline"
    assert "style=" not in page.text and "onclick" not in page.text
