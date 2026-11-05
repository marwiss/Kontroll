# This file was generated with the assistance of an AI coding tool.
"""OAuth2 endpoints of the Foundation API (2.2).

* ``GET  /foundation/oauth2/auth``   the authorization endpoint: shows the
  sign-in and consent page (RFC 6749 §4.1.1, PKCE required).
* ``POST /foundation/oauth2/auth``   the page's form: authenticates the user,
  issues a one-time code and redirects back to the client (§4.1.2).
* ``POST /foundation/oauth2/token``  exchanges a code or a refresh token
  (§4.1.3, §6); refresh tokens rotate.
* ``POST /foundation/oauth2/revoke`` RFC 7009 token revocation.
* ``POST /foundation/oauth2/reg``    dynamic client registration (Foundation
  API 2.2.3) when enabled.

Security rules follow RFC 9700: exact redirect URI matching with the RFC 8252
loopback exception, PKCE ``S256`` for every client, ``state`` required, the
``iss`` parameter in responses (RFC 9207), no open redirects (errors about
the client or its redirect URI are shown here, never redirected), and token
responses that are never cached.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import unquote, urlencode, urlsplit

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from opencde import audit
from opencde.auth import pkce
from opencde.auth.clients import Client, ClientError, redirect_uri_matches, validate_redirect_uri
from opencde.auth.dependencies import TokensDep
from opencde.auth.forms import FormTokenError, FormTokens
from opencde.auth.scopes import SCOPES, ScopeError, parse_scope, scope_string
from opencde.auth.tokens import GrantError
from opencde.deps import ClientsDep, GraphDep, SettingsDep, UsersDep, client_ip
from opencde.logging import get_logger
from opencde.ratelimit import RATE_EXCHANGE, RATE_REGISTRATION, RATE_SIGN_IN, limiter
from opencde.timeutil import later_iso
from opencde.ui.i18n import tr
from opencde.ui.templating import render

log = get_logger(__name__)

router = APIRouter(prefix="/foundation/oauth2", tags=["Foundation API"])

NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
FORM_PURPOSE = "oauth2-authorize"


def form_tokens(request: Request) -> FormTokens:
    settings = request.app.state.settings
    return FormTokens(settings.secret_key.get_secret_value(), settings.form_token_ttl_seconds)


# ---------------------------------------------------------------------------- helpers


def _oauth_error(status: int, error: str, description: str, headers: dict[str, str] | None = None) -> JSONResponse:
    """RFC 6749 §5.2 error body, plus the OpenCDE ``message`` field."""
    body = {"error": error, "error_description": description, "message": description}
    response_headers = dict(NO_STORE)
    if headers:
        response_headers.update(headers)
    return JSONResponse(body, status_code=status, headers=response_headers)


def _redirect_with(redirect_uri: str, params: dict[str, str]) -> RedirectResponse:
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(redirect_uri + separator + urlencode(params), status_code=302, headers=NO_STORE)


def _error_redirect(
    redirect_uri: str, error: str, description: str, state: str | None, issuer: str
) -> RedirectResponse:
    params = {"error": error, "error_description": description, "iss": issuer}
    if state:
        params["state"] = state
    return _redirect_with(redirect_uri, params)


async def _resolve_client_and_redirect(
    clients: Any, client_id: str | None, redirect_uri: str | None
) -> tuple[Client, str]:
    """RFC 6749 §4.1.2.1: these two are checked first and never cause a redirect."""
    if not client_id:
        raise HTTPException(400, "The request does not name a client (client_id).")
    client = await clients.get(client_id)
    if client is None or client.disabled:
        raise HTTPException(400, "Unknown client.")
    if not redirect_uri:
        if len(client.redirect_uris) == 1:
            return client, client.redirect_uris[0]
        raise HTTPException(400, "The request does not name a redirect URI and the client has several registered.")
    if not any(redirect_uri_matches(registered, redirect_uri) for registered in client.redirect_uris):
        raise HTTPException(400, "The redirect URI is not registered for this client.")
    return client, redirect_uri


def _scope_descriptions(scopes: list[str]) -> list[dict[str, str]]:
    return [{"name": name, "description": SCOPES[name]} for name in scopes]


# ---------------------------------------------------------------------------- authorization endpoint


@router.get("/auth", summary="Authorization endpoint: sign-in and consent page", include_in_schema=True)
async def authorize_page(
    request: Request,
    clients: ClientsDep,
    settings: SettingsDep,
    response_type: str | None = None,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    redirect_url: str | None = None,
    state: str | None = None,
    scope: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> Response:
    """Start of the authorization code flow (RFC 6749 §4.1.1). ``redirect_url`` is accepted as the
    spelling used in the Foundation API examples."""
    try:
        client, redirect_to = await _resolve_client_and_redirect(clients, client_id, redirect_uri or redirect_url)
    except HTTPException as exc:
        return render(request, "auth/error.html", {"message": exc.detail}, status_code=exc.status_code)

    issuer = settings.public_url
    if response_type != "code":
        return _error_redirect(
            redirect_to, "unsupported_response_type", "only response_type=code is supported", state, issuer
        )
    if not state or len(state) > 512:
        return _error_redirect(
            redirect_to, "invalid_request", "state is required (and at most 512 characters)", None, issuer
        )
    if not pkce.is_valid_challenge(code_challenge) or (code_challenge_method or pkce.METHOD) != pkce.METHOD:
        return _error_redirect(
            redirect_to, "invalid_request", "PKCE with code_challenge_method=S256 is required", state, issuer
        )
    try:
        scopes = parse_scope(scope)
    except ScopeError as exc:
        return _error_redirect(redirect_to, "invalid_scope", str(exc), state, issuer)

    token = form_tokens(request).sign(
        FORM_PURPOSE,
        {
            "client_id": client.client_id,
            "redirect_uri": redirect_to,
            "state": state,
            "scope": scope_string(scopes),
            "code_challenge": code_challenge,
        },
    )
    return render(
        request,
        "auth/authorize.html",
        {
            "client": client,
            "scopes": _scope_descriptions(scopes),
            "redirect_host": urlsplit(redirect_to).netloc or redirect_to,
            "form_token": token,
            "error": None,
        },
    )


@router.post("/auth", summary="Authorization endpoint: process the sign-in form", include_in_schema=False)
@limiter.limit(RATE_SIGN_IN)
async def authorize_submit(
    request: Request,
    clients: ClientsDep,
    users: UsersDep,
    tokens: TokensDep,
    graph: GraphDep,
    settings: SettingsDep,
    form_token: Annotated[str | None, Form()] = None,
    username: Annotated[str, Form(max_length=128)] = "",
    password: Annotated[str, Form(max_length=256)] = "",
    decision: Annotated[str, Form(max_length=16)] = "allow",
) -> Response:
    try:
        data = form_tokens(request).load(form_token, FORM_PURPOSE)
    except FormTokenError:
        return render(request, "auth/error.html", {"message": tr(request, "auth.error.form_expired")}, status_code=400)

    client = await clients.get(data["client_id"])
    if client is None or client.disabled:
        return render(
            request, "auth/error.html", {"message": tr(request, "auth.error.unknown_client")}, status_code=400
        )
    redirect_to: str = data["redirect_uri"]
    state: str = data["state"]
    issuer = settings.public_url
    ip = client_ip(request)

    if decision != "allow":
        await audit.record(graph, "auth.consent.denied", client_id=client.client_id, ip=ip)
        return _error_redirect(redirect_to, "access_denied", "the user denied the request", state, issuer)

    user = await users.authenticate(username, password)
    if user is None:
        await audit.record(
            graph, "auth.sign_in.failed", client_id=client.client_id, ip=ip, details={"username": username[:128]}
        )
        token = form_tokens(request).sign(FORM_PURPOSE, data)
        scopes = parse_scope(data["scope"])
        return render(
            request,
            "auth/authorize.html",
            {
                "client": client,
                "scopes": _scope_descriptions(scopes),
                "redirect_host": urlsplit(redirect_to).netloc or redirect_to,
                "form_token": token,
                "error": tr(request, "signin.error.credentials"),
            },
        )

    code = await tokens.issue_code(
        user_id=user.id,
        client_id=client.client_id,
        redirect_uri=redirect_to,
        scope=data["scope"],
        code_challenge=data["code_challenge"],
    )
    await audit.record(
        graph, "auth.code.issued", actor=user.id, client_id=client.client_id, ip=ip, details={"scope": data["scope"]}
    )
    return _redirect_with(redirect_to, {"code": code, "state": state, "iss": issuer})


# ---------------------------------------------------------------------------- token endpoint


def _basic_credentials(request: Request) -> tuple[str, str] | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic":
        return None
    try:
        decoded = base64.b64decode(value.strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ("", "")
    client_id, _, secret = decoded.partition(":")
    return unquote(client_id), unquote(secret)  # RFC 6749 §2.3.1: form-urlencoded before base64


async def _token_params(request: Request) -> dict[str, str]:
    """Parameters from the form body, falling back to the query string (Foundation API example)."""
    params: dict[str, str] = {k: v for k, v in request.query_params.items()}
    if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        form = await request.form()
        params.update({k: str(v) for k, v in form.items()})
    return params


async def _authenticate_client(request: Request, clients: Any, params: dict[str, str]) -> Client:
    basic = _basic_credentials(request)
    if basic is not None:
        client_id, secret = basic
    else:
        client_id, secret = params.get("client_id", ""), params.get("client_secret", "")
    client = await clients.authenticate(client_id, secret or None)
    if client is None:
        raise GrantError("invalid_client", "client authentication failed", 401)
    return client


@router.post("/token", summary="Token endpoint", status_code=201)
@limiter.limit(RATE_EXCHANGE)
async def token(request: Request, clients: ClientsDep, tokens: TokensDep, graph: GraphDep) -> Response:
    """Issue tokens for an authorization code or a refresh token (RFC 6749 §4.1.3 and §6).

    Confidential clients authenticate with HTTP Basic (client_id:client_secret) or form
    fields; public clients send only ``client_id``. Responds ``201 Created`` as the
    Foundation API examples do. Refresh tokens are single-use and rotate.
    """
    params = await _token_params(request)
    try:
        client = await _authenticate_client(request, clients, params)
    except GrantError as exc:
        basic = _basic_credentials(request) is not None
        return _oauth_error(
            exc.status, exc.error, exc.description, {"WWW-Authenticate": 'Basic realm="opencde"'} if basic else None
        )

    request.state.log_client_id = client.client_id  # for the request log, which otherwise sees no bearer here
    grant_type = params.get("grant_type", "")
    ip = client_ip(request)
    try:
        if grant_type == "authorization_code":
            code = params.get("code", "")
            verifier = params.get("code_verifier", "")
            if not code or not verifier:
                raise GrantError("invalid_request", "code and code_verifier are required")
            redirect_uri = params.get("redirect_uri") or params.get("redirect_url")
            pair = await tokens.redeem_code(
                code=code,
                client_id=client.client_id,
                redirect_uri=redirect_uri,
                code_verifier=verifier,
            )
            await audit.record(
                graph, "auth.token.issued", client_id=client.client_id, ip=ip, details={"grant": grant_type}
            )
        elif grant_type == "refresh_token":
            refresh_token = params.get("refresh_token", "")
            if not refresh_token:
                raise GrantError("invalid_request", "refresh_token is required")
            pair = await tokens.refresh(refresh_token=refresh_token, client_id=client.client_id)
            await audit.record(graph, "auth.token.refreshed", client_id=client.client_id, ip=ip)
        elif not grant_type:
            raise GrantError("invalid_request", "grant_type is required")
        else:
            raise GrantError("unsupported_grant_type", f"grant_type '{grant_type[:40]}' is not supported")
    except GrantError as exc:
        if "reuse detected" in exc.description or "already used" in exc.description:
            await audit.record(
                graph, "auth.replay_detected", client_id=client.client_id, ip=ip, details={"grant": grant_type}
            )
        return _oauth_error(exc.status, exc.error, exc.description)

    if client.dynamic:  # a self-registered client in use keeps its registration alive
        settings = request.app.state.settings
        await clients.touch(client.client_id, expires_at=later_iso(settings.dynamic_client_unused_days * 86400))
    return JSONResponse(
        {
            "access_token": pair.access_token,
            "token_type": "bearer",  # nosec B105
            "expires_in": pair.expires_in,
            "refresh_token": pair.refresh_token,
            "scope": pair.scope,
        },
        status_code=201,
        headers=NO_STORE,
    )


# ---------------------------------------------------------------------------- revocation


@router.post("/revoke", summary="Revoke a token (RFC 7009)", status_code=200)
@limiter.limit(RATE_EXCHANGE)
async def revoke(request: Request, clients: ClientsDep, tokens: TokensDep, graph: GraphDep) -> Response:
    """Revoke an access token, or a refresh token together with every token of its session.
    Always answers 200 for an authenticated client, whether or not the token was known."""
    params = await _token_params(request)
    try:
        client = await _authenticate_client(request, clients, params)
    except GrantError as exc:
        return _oauth_error(exc.status, exc.error, exc.description)
    request.state.log_client_id = client.client_id
    revoked = await tokens.revoke(params.get("token", ""), client_id=client.client_id)
    if revoked:
        await audit.record(graph, "auth.token.revoked", client_id=client.client_id, ip=client_ip(request))
    return JSONResponse({}, headers=NO_STORE)


# ---------------------------------------------------------------------------- dynamic registration


SUPPORTED_GRANT_TYPES = ("authorization_code", "refresh_token")
AUTH_METHOD_BASIC = "client_secret_basic"  # RFC 7591 default: a confidential client
AUTH_METHOD_NONE = "none"  # a public client: no secret, PKCE only


class RegistrationRequest(BaseModel):
    """Client metadata of Foundation API 2.2.3, plus the RFC 7591 §2 fields that choose a public client."""

    client_name: str = Field(min_length=1, max_length=200)
    client_description: str | None = Field(None, max_length=1000)
    client_url: str | None = Field(None, max_length=2000)
    redirect_url: str | None = Field(None, max_length=2000)
    redirect_uris: list[str] | None = Field(None, max_length=10)
    # "none" registers a public client (browser or native app) that gets no secret and relies on PKCE.
    token_endpoint_auth_method: Literal["client_secret_basic", "client_secret_post", "none"] = AUTH_METHOD_BASIC
    grant_types: list[str] | None = Field(None, max_length=4)
    # RFC 7591 §2: which software registered, shown to administrators and useful when debugging.
    software_id: str | None = Field(None, max_length=100)
    software_version: str | None = Field(None, max_length=50)


@router.post("/reg", summary="Dynamic client registration (Foundation API 2.2.3)", status_code=201)
@limiter.limit(RATE_REGISTRATION)
async def register_client(
    request: Request, body: RegistrationRequest, clients: ClientsDep, settings: SettingsDep, graph: GraphDep
) -> Response:
    """Register a client and return its metadata (RFC 7591 §3.2.1): ``client_id`` and, for a confidential
    client, the ``client_secret`` shown once. ``token_endpoint_auth_method: "none"`` registers a public client
    without a secret. Available only when ``OPENCDE_DYNAMIC_CLIENT_REGISTRATION`` is true."""
    if not settings.dynamic_client_registration:
        raise HTTPException(404, "Dynamic client registration is not enabled on this server")
    uris = list(body.redirect_uris or [])
    if body.redirect_url:
        uris.insert(0, body.redirect_url)
    if not uris:
        raise HTTPException(400, "redirect_url is required")
    grant_types = body.grant_types or list(SUPPORTED_GRANT_TYPES)
    if any(grant not in SUPPORTED_GRANT_TYPES for grant in grant_types):
        raise HTTPException(400, "grant_types may only contain authorization_code and refresh_token")
    public = body.token_endpoint_auth_method == AUTH_METHOD_NONE
    try:
        for uri in uris:
            validate_redirect_uri(uri, allow_localhost=settings.allow_localhost_redirects)
        client, secret = await clients.create(
            body.client_name,
            uris,
            public=public,
            description=body.client_description,
            url=body.client_url,
            dynamic=True,
            expires_at=later_iso(settings.dynamic_client_unused_days * 86400),  # deleted if never used
            software_id=body.software_id,
            software_version=body.software_version,
        )
    except ClientError as exc:
        raise HTTPException(400, str(exc)) from None
    await audit.record(
        graph,
        "auth.client.registered",
        client_id=client.client_id,
        ip=client_ip(request),
        details={"name": client.name, "public": public},
    )
    payload: dict[str, Any] = {
        "client_id": client.client_id,
        "client_id_issued_at": int(datetime.now(UTC).timestamp()),
        "client_name": client.name,
        "redirect_uris": list(client.redirect_uris),
        "token_endpoint_auth_method": body.token_endpoint_auth_method,
        "grant_types": grant_types,
    }
    if client.software_id:
        payload["software_id"] = client.software_id
    if client.software_version:
        payload["software_version"] = client.software_version
    if secret is not None:
        payload["client_secret"] = secret
        payload["client_secret_expires_at"] = 0  # RFC 7591 §3.2.1: 0 means the secret does not expire
    return JSONResponse(payload, status_code=201, headers=NO_STORE)
