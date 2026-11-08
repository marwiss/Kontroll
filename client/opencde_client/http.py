# This file was generated with the assistance of an AI coding tool.
"""The HTTP session shared by the API clients: bearer token, automatic refresh, error mapping."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from opencde_client.auth import TokenSet
from opencde_client.errors import ApiError, AuthError

USER_AGENT = "opencde-client/0.1 (+https://github.com/marwiss/Dataregium)"
Refresher = Callable[[TokenSet], TokenSet]


class ApiSession:
    """An ``httpx.Client`` that adds ``Authorization: Bearer`` and refreshes the token once on 401.

    ``base_url`` is the server root (the part before ``/foundation``, ``/bcf`` and
    ``/documents``). Absolute URLs (the links servers hand out) are used as they are.
    """

    def __init__(
        self,
        base_url: str,
        *,
        tokens: TokenSet | None = None,
        refresher: Refresher | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        verify: bool | str = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.tokens = tokens
        self.refresher = refresher
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            verify=verify,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=False,
        )

    # -- lifecycle -------------------------------------------------------------------------

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> ApiSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- requests ----------------------------------------------------------------------------

    def _refresh(self) -> TokenSet:
        """Rotate the tokens; a refused refresh means the session is gone (revoked or expired)."""
        if self.refresher is None or self.tokens is None:
            raise AuthError("no way to refresh the session; sign in again")
        try:
            return self.refresher(self.tokens)
        except ApiError as exc:
            self.tokens = None
            raise AuthError("the session has expired or was revoked; sign in again") from exc

    def _headers(self, include_authorization: bool) -> dict[str, str]:
        if include_authorization and self.tokens is not None:
            return {"Authorization": f"Bearer {self.tokens.access_token}"}
        return {}

    def request(
        self,
        method: str,
        url: str,
        *,
        include_authorization: bool = True,
        expected: tuple[int, ...] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request; raise :class:`ApiError` for 4xx/5xx (or any status not in ``expected``)."""
        if self.tokens is not None and self.tokens.is_expired and self.refresher is not None:
            self.tokens = self._refresh()
        headers = {**self._headers(include_authorization), **kwargs.pop("headers", {})}
        response = self.client.request(method, url, headers=headers, **kwargs)
        if response.status_code == 401 and include_authorization and self.refresher is not None and self.tokens:
            self.tokens = self._refresh()
            headers = {**self._headers(True), **kwargs.get("headers", {})}
            response = self.client.request(method, url, headers=headers, **kwargs)
        ok = response.status_code in expected if expected else response.is_success or response.status_code == 304
        if not ok:
            raise ApiError(response)
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def json(self, method: str, url: str, **kwargs: Any) -> Any:
        """A request whose answer is JSON (leading whitespace from keep-alive responses is fine)."""
        response = self.request(method, url, **kwargs)
        text = response.text.strip()
        return response.json() if not text or text[0] in "{[" else httpx.Response(200, text=text).json()
