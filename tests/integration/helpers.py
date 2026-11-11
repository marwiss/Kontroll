# This file was generated with the assistance of an AI coding tool.
"""Helpers that drive the real OAuth2 flow through the test client."""

from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from opencde.auth import pkce

FORM_TOKEN = re.compile(r'name="form_token" value="([^"]+)"')


@dataclass
class Session:
    access_token: str
    refresh_token: str
    scope: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def basic_auth(client_id: str, secret: str) -> dict[str, str]:
    raw = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


def authorize(
    client: TestClient,
    *,
    client_id: str,
    redirect_uri: str,
    username: str,
    password: str,
    scope: str | None = None,
    state: str = "state-123",
    decision: str = "allow",
    resource: str | None = None,
) -> tuple[str | None, dict[str, list[str]], str]:
    """Run GET + POST on the authorization endpoint. Returns (code, redirect query, verifier)."""
    verifier = secrets.token_urlsafe(48)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": pkce.challenge_for(verifier),
        "code_challenge_method": "S256",
    }
    if scope is not None:
        params["scope"] = scope
    if resource is not None:
        params["resource"] = resource
    page = client.get("/foundation/oauth2/auth", params=params)
    assert page.status_code == 200, page.text[:500]
    match = FORM_TOKEN.search(page.text)
    assert match, "sign-in form carries a form token"
    response = client.post(
        "/foundation/oauth2/auth",
        data={"form_token": match.group(1), "username": username, "password": password, "decision": decision},
        follow_redirects=False,
    )
    if response.status_code != 302:
        return None, {}, verifier
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return (query.get("code") or [None])[0], query, verifier


def exchange(
    client: TestClient,
    *,
    code: str,
    verifier: str,
    client_id: str,
    client_secret: str | None = None,
    redirect_uri: str | None = None,
    resource: str | None = None,
) -> Session:
    data = {"grant_type": "authorization_code", "code": code, "code_verifier": verifier}
    if redirect_uri:
        data["redirect_uri"] = redirect_uri
    if resource:
        data["resource"] = resource
    headers = basic_auth(client_id, client_secret) if client_secret else {}
    if not client_secret:
        data["client_id"] = client_id
    response = client.post("/foundation/oauth2/token", data=data, headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    return Session(body["access_token"], body["refresh_token"], body["scope"])


def sign_in(
    client: TestClient,
    *,
    client_id: str,
    redirect_uri: str,
    username: str,
    password: str,
    client_secret: str | None = None,
    scope: str | None = None,
) -> Session:
    code, _query, verifier = authorize(
        client, client_id=client_id, redirect_uri=redirect_uri, username=username, password=password, scope=scope
    )
    assert code, "authorization code expected"
    return exchange(client, code=code, verifier=verifier, client_id=client_id, client_secret=client_secret)
