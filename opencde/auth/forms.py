# This file was generated with the assistance of an AI coding tool.
"""Signed, expiring form tokens.

The sign-in and consent page carries the OAuth2 request inside a token signed
with the server's secret key. When the form comes back, the signature proves
the parameters were issued by this server (not forged by an attacker's page)
and the timestamp bounds how long a form stays valid. The same mechanism
protects the admin UI's forms against cross-site request forgery.
"""

from __future__ import annotations

from typing import Any

from itsdangerous import BadData, URLSafeTimedSerializer


class FormTokenError(ValueError):
    pass


class FormTokens:
    def __init__(self, secret_key: str, max_age_seconds: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key, salt="opencde.form")
        self.max_age = max_age_seconds

    def sign(self, purpose: str, payload: dict[str, Any]) -> str:
        return self._serializer.dumps({"purpose": purpose, **payload})

    def load(self, token: str | None, purpose: str) -> dict[str, Any]:
        """The payload if the token is genuine, unexpired and for ``purpose``; raises otherwise."""
        if not token:
            raise FormTokenError("missing form token")
        try:
            data = self._serializer.loads(token, max_age=self.max_age)
        except BadData as exc:
            raise FormTokenError("invalid or expired form token") from exc
        if not isinstance(data, dict) or data.get("purpose") != purpose:
            raise FormTokenError("form token used for the wrong purpose")
        data.pop("purpose", None)
        return data
