# This file was generated with the assistance of an AI coding tool.
"""One object that ties discovery, sign-in and the three APIs together."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from opencde_client.auth import DEFAULT_SCOPES, OAuth2Client, TokenSet
from opencde_client.bcf import BcfClient
from opencde_client.documents import DocumentsClient
from opencde_client.errors import AuthError
from opencde_client.foundation import AuthInfo, FoundationClient, auth_info
from opencde_client.http import ApiSession


class OpenCdeClient:
    """A signed-in connection to one OpenCDE server.

    ``client_id`` is the id the server's administrator registered for your
    application (public client with PKCE, or confidential with ``client_secret``).
    """

    def __init__(
        self,
        base_url: str,
        *,
        client_id: str,
        client_secret: str | None = None,
        tokens: TokenSet | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._transport = transport
        self._auth_info: AuthInfo | None = None
        self._oauth: OAuth2Client | None = None
        self.session = ApiSession(
            self.base_url, tokens=tokens, refresher=self._refresh, transport=transport, timeout=timeout
        )
        self.foundation = FoundationClient(self.session)
        self.bcf = BcfClient(self.session)
        self.documents = DocumentsClient(self.session)

    # -- sign-in ----------------------------------------------------------------------------------

    @property
    def auth_info(self) -> AuthInfo:
        if self._auth_info is None:
            self._auth_info = auth_info(self.base_url, transport=self._transport)
        return self._auth_info

    @property
    def oauth(self) -> OAuth2Client:
        if self._oauth is None:
            info = self.auth_info
            if not info.oauth2_auth_url or not info.oauth2_token_url:
                raise AuthError("the server does not advertise OAuth2 endpoints")
            self._oauth = OAuth2Client(
                auth_url=info.oauth2_auth_url,
                token_url=info.oauth2_token_url,
                revocation_url=info.oauth2_revocation_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                transport=self._transport,
            )
        return self._oauth

    def login(
        self,
        *,
        scopes: tuple[str, ...] | list[str] = DEFAULT_SCOPES,
        open_browser: Callable[[str], Any] | None = None,
        timeout: float = 300.0,
    ) -> TokenSet:
        """Authorization code flow with PKCE through the user's browser (loopback redirect)."""
        kwargs: dict[str, Any] = {"scopes": scopes, "timeout": timeout, "expected_issuer": self.base_url}
        if open_browser is not None:
            kwargs["open_browser"] = open_browser
        self.session.tokens = self.oauth.login_with_browser(**kwargs)
        return self.session.tokens

    def use_tokens(self, tokens: TokenSet) -> None:
        self.session.tokens = tokens

    @property
    def tokens(self) -> TokenSet | None:
        return self.session.tokens

    def _refresh(self, tokens: TokenSet) -> TokenSet:
        return self.oauth.refresh(tokens)

    def logout(self) -> None:
        """Revoke the refresh token (and with it the family) when the server supports RFC 7009."""
        tokens = self.session.tokens
        if tokens and tokens.refresh_token:
            # The RFC 7009 token_type_hint, not a secret.
            self.oauth.revoke(tokens.refresh_token, token_type_hint="refresh_token")  # noqa: S106 # nosec B106
        self.session.tokens = None

    # -- lifecycle --------------------------------------------------------------------------------

    def close(self) -> None:
        self.session.close()
        if self._oauth is not None:
            self._oauth.close()

    def __enter__(self) -> OpenCdeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
