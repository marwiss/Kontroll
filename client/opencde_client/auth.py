# This file was generated with the assistance of an AI coding tool.
"""OAuth2 authorization code flow with PKCE (RFC 6749, RFC 7636, RFC 8252, RFC 9700).

The flow for a desktop or script client:

1. :meth:`OAuth2Client.authorization_url` builds the URL the user opens in a
   browser (``code_challenge``, ``state``, loopback ``redirect_uri``).
2. The server redirects the browser to the loopback listener with ``code``
   and ``state``; :meth:`OAuth2Client.login_with_browser` does steps 1-3.
3. :meth:`OAuth2Client.exchange` turns the code into a :class:`TokenSet`.
4. :meth:`OAuth2Client.refresh` rotates the refresh token when needed.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from opencde_client.errors import ApiError, AuthError

DEFAULT_SCOPES = ("profile", "bcf", "documents")
EXPIRY_MARGIN_SECONDS = 30.0


def generate_verifier() -> str:
    """A PKCE code verifier: 64 URL-safe characters of randomness (RFC 7636 §4.1)."""
    return secrets.token_urlsafe(48)


def pkce_challenge(verifier: str) -> str:
    """``BASE64URL(SHA256(verifier))`` without padding (RFC 7636 §4.2, method S256)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_state() -> str:
    return secrets.token_urlsafe(24)


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: float
    scope: str
    token_type: str = "bearer"  # noqa: S105 - the OAuth2 token type, not a secret

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - EXPIRY_MARGIN_SECONDS

    @classmethod
    def from_response(cls, body: dict[str, Any], *, previous: TokenSet | None = None) -> TokenSet:
        return cls(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token") or (previous.refresh_token if previous else None),
            expires_at=time.time() + float(body.get("expires_in", 3600)),
            scope=str(body.get("scope") or (previous.scope if previous else "")),
            token_type=str(body.get("token_type", "bearer")),
        )


class OAuth2Client:
    """The client side of the server's OAuth2 endpoints."""

    def __init__(
        self,
        *,
        auth_url: str,
        token_url: str,
        client_id: str,
        client_secret: str | None = None,
        revocation_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.auth_url = auth_url
        self.token_url = token_url
        self.revocation_url = revocation_url
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        self._http.close()

    # -- authorization request ------------------------------------------------------------------

    def authorization_url(
        self, *, redirect_uri: str, state: str, verifier: str, scopes: tuple[str, ...] | list[str] = DEFAULT_SCOPES
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
        separator = "&" if "?" in self.auth_url else "?"
        return f"{self.auth_url}{separator}{urlencode(params)}"

    @staticmethod
    def parse_callback(url: str, *, expected_state: str, expected_issuer: str | None = None) -> str:
        """The ``code`` from a redirect back to the client; refuses wrong ``state``, ``iss`` or errors."""
        query = parse_qs(urlsplit(url).query)
        if query.get("error"):
            raise AuthError(f"{query['error'][0]}: {(query.get('error_description') or [''])[0]}")
        if (query.get("state") or [None])[0] != expected_state:
            raise AuthError("state mismatch: the response does not belong to this request")
        issuer = (query.get("iss") or [None])[0]
        if expected_issuer and issuer and issuer.rstrip("/") != expected_issuer.rstrip("/"):
            raise AuthError("the response came from another issuer (mix-up attack?)")
        code = (query.get("code") or [None])[0]
        if not code:
            raise AuthError("no authorization code in the response")
        return code

    # -- token endpoint ------------------------------------------------------------------------

    def _client_auth(self, data: dict[str, str]) -> dict[str, Any]:
        """Confidential clients authenticate with HTTP Basic; public clients send ``client_id`` in the form."""
        if self.client_secret:
            return {"auth": (self.client_id, self.client_secret)}
        data["client_id"] = self.client_id
        return {}

    def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        data = dict(data)
        extra = self._client_auth(data)
        response = self._http.post(self.token_url, data=data, headers={"Accept": "application/json"}, **extra)
        if response.status_code not in (200, 201):
            raise ApiError(response)
        return response.json()

    def exchange(self, *, code: str, verifier: str, redirect_uri: str) -> TokenSet:
        body = self._token_request(
            {"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri}
        )
        return TokenSet.from_response(body)

    def refresh(self, tokens: TokenSet) -> TokenSet:
        if not tokens.refresh_token:
            raise AuthError("no refresh token; sign in again")
        body = self._token_request({"grant_type": "refresh_token", "refresh_token": tokens.refresh_token})
        return TokenSet.from_response(body, previous=tokens)

    def revoke(self, token: str, *, token_type_hint: str | None = None) -> None:
        """RFC 7009 revocation; a server without a revocation endpoint is left alone."""
        if not self.revocation_url:
            return
        data = {"token": token}
        if token_type_hint:
            data["token_type_hint"] = token_type_hint
        extra = self._client_auth(data)
        response = self._http.post(self.revocation_url, data=data, **extra)
        if response.is_error:
            raise ApiError(response)

    # -- the whole flow for a native client ------------------------------------------------------

    def login_with_browser(
        self,
        *,
        scopes: tuple[str, ...] | list[str] = DEFAULT_SCOPES,
        open_browser: Callable[[str], Any] = webbrowser.open,
        timeout: float = 300.0,
        expected_issuer: str | None = None,
    ) -> TokenSet:
        """Listen on ``http://127.0.0.1:<random port>/callback``, open the browser, exchange the code."""
        listener = _CallbackListener()
        redirect_uri = f"http://127.0.0.1:{listener.port}/callback"
        state, verifier = generate_state(), generate_verifier()
        url = self.authorization_url(redirect_uri=redirect_uri, state=state, verifier=verifier, scopes=scopes)
        try:
            open_browser(url)
            callback_url = listener.wait(timeout)
        finally:
            listener.close()
        code = self.parse_callback(callback_url, expected_state=state, expected_issuer=expected_issuer)
        return self.exchange(code=code, verifier=verifier, redirect_uri=redirect_uri)


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        listener = cast("_CallbackListener", self.server)
        listener.received = f"http://127.0.0.1:{listener.port}{self.path}"
        body = b"<!doctype html><title>Signed in</title><p>You are signed in. You can close this window.</p>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        listener.done.set()

    def log_message(self, format: str, *args: Any) -> None:
        return


class _CallbackListener(HTTPServer):
    """A one-shot loopback HTTP server receiving the redirect (RFC 8252 §7.3)."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _CallbackHandler)
        self.port = int(self.server_address[1])
        self.received: str | None = None
        self.done = threading.Event()
        self._thread = threading.Thread(target=self.serve_forever, name="opencde-callback", daemon=True)
        self._thread.start()

    def wait(self, timeout: float) -> str:
        if not self.done.wait(timeout) or self.received is None:
            raise AuthError("no response from the browser within the time limit")
        return self.received

    def close(self) -> None:
        self.shutdown()
        self.server_close()


def with_tokens(tokens: TokenSet, **changes: Any) -> TokenSet:
    return replace(tokens, **changes)
