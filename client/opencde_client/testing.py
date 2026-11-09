# This file was generated with the assistance of an AI coding tool.
"""Helpers for automated tests: drive the server's browser pages without a browser.

Real applications never see a user's password; these helpers exist so test
suites and demo scripts can complete the sign-in and the Documents API pages
of a *Dataregium* server headlessly. They depend on that server's page markup.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from opencde_client.auth import OAuth2Client, TokenSet, generate_state, generate_verifier
from opencde_client.errors import AuthError

FORM_TOKEN = re.compile(r'name="form_token" value="([^"]+)"')


def _form_token(html: str) -> str:
    match = FORM_TOKEN.search(html)
    if not match:
        raise AuthError("the page carries no form token")
    return match.group(1)


def headless_authorize(
    oauth: OAuth2Client,
    *,
    username: str,
    password: str,
    redirect_uri: str,
    scopes: tuple[str, ...] | list[str] = ("profile", "bcf", "documents"),
    transport: httpx.BaseTransport | None = None,
) -> TokenSet:
    """Complete the authorization code flow by posting the sign-in form (test environments only)."""
    state, verifier = generate_state(), generate_verifier()
    url = oauth.authorization_url(redirect_uri=redirect_uri, state=state, verifier=verifier, scopes=scopes)
    with httpx.Client(transport=transport, follow_redirects=False, timeout=30.0) as browser:
        page = browser.get(url)
        if page.status_code != 200:
            raise AuthError(f"authorization page answered {page.status_code}")
        response = browser.post(
            str(page.url),
            data={
                "form_token": _form_token(page.text),
                "username": username,
                "password": password,
                "decision": "allow",
            },
        )
        if response.status_code != 302:
            raise AuthError("sign-in was not accepted")
        code = OAuth2Client.parse_callback(response.headers["location"], expected_state=state)
    return oauth.exchange(code=code, verifier=verifier, redirect_uri=redirect_uri)


class HeadlessBrowser:
    """A cookie-holding ``httpx.Client`` that fills in the server's own pages."""

    def __init__(self, base_url: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.http = httpx.Client(base_url=base_url, transport=transport, follow_redirects=False, timeout=30.0)

    def close(self) -> None:
        self.http.close()

    def sign_in(self, username: str, password: str) -> None:
        page = self.http.get("/signin")
        response = self.http.post(
            "/signin", data={"form_token": _form_token(page.text), "username": username, "password": password}
        )
        if response.status_code != 302:
            raise AuthError("browser sign-in failed")

    @staticmethod
    def _callback_params(response: httpx.Response) -> dict[str, str]:
        if response.status_code != 302:
            raise AuthError(f"expected a redirect to the callback, got {response.status_code}")
        return {key: values[0] for key, values in parse_qs(urlsplit(response.headers["location"]).query).items()}

    def finish_upload_page(
        self, upload_ui_url: str, *, project_id: str, titles: dict[int, tuple[str, str]]
    ) -> dict[str, str]:
        """Save metadata on the upload page; returns the callback's query parameters (``upload_documents_url``)."""
        page = self.http.get(upload_ui_url)
        if page.status_code != 200:
            raise AuthError(f"upload page answered {page.status_code}")
        data: dict[str, Any] = {"form_token": _form_token(page.text), "project_id": project_id, "action": "save"}
        for index, (title, version) in titles.items():
            data[f"title_{index}"] = title
            data[f"version_{index}"] = version
        return self._callback_params(self.http.post(upload_ui_url, data=data))

    def cancel_upload_page(self, upload_ui_url: str) -> dict[str, str]:
        page = self.http.get(upload_ui_url)
        return self._callback_params(
            self.http.post(upload_ui_url, data={"form_token": _form_token(page.text), "action": "cancel"})
        )

    def finish_selection_page(self, select_documents_url: str, *, document_ids: list[str]) -> dict[str, str]:
        page = self.http.get(select_documents_url)
        if page.status_code != 200:
            raise AuthError(f"selection page answered {page.status_code}")
        data: dict[str, Any] = {"form_token": _form_token(page.text), "action": "select", "selected": document_ids}
        return self._callback_params(self.http.post(select_documents_url, data=data))
