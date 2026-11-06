# This file was generated with the assistance of an AI coding tool.
"""Unit tests of the client library against a mocked server (no network)."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

import httpx
import pytest

from opencde_client import (
    ApiError,
    ApiSession,
    AuthError,
    BcfClient,
    DocumentsClient,
    OAuth2Client,
    TokenSet,
    pkce_challenge,
)
from opencde_client.auth import generate_verifier
from opencde_client.bcf import content_disposition, image_payload
from opencde_client.client import OpenCdeClient
from opencde_client.errors import NotInThisVersion
from opencde_client.foundation import discover


def test_pkce_challenge_is_s256_base64url() -> None:
    verifier = generate_verifier()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert pkce_challenge(verifier) == expected
    assert (
        pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_authorization_url_and_callback_parsing() -> None:
    oauth = OAuth2Client(
        auth_url="https://cde.test/foundation/oauth2/auth", token_url="https://cde.test/t", client_id="app"
    )
    url = oauth.authorization_url(
        redirect_uri="http://127.0.0.1:5000/cb", state="s1", verifier="v" * 43, scopes=("bcf",)
    )
    assert url.startswith("https://cde.test/foundation/oauth2/auth?response_type=code&client_id=app")
    assert "code_challenge_method=S256" in url and "scope=bcf" in url and "state=s1" in url
    assert OAuth2Client.parse_callback("http://127.0.0.1:5000/cb?code=abc&state=s1", expected_state="s1") == "abc"
    with pytest.raises(AuthError, match="state"):
        OAuth2Client.parse_callback("http://127.0.0.1:5000/cb?code=abc&state=other", expected_state="s1")
    with pytest.raises(AuthError, match="access_denied"):
        OAuth2Client.parse_callback("http://127.0.0.1:5000/cb?error=access_denied&state=s1", expected_state="s1")
    with pytest.raises(AuthError, match="issuer"):
        OAuth2Client.parse_callback(
            "http://127.0.0.1:5000/cb?code=abc&state=s1&iss=https://evil.test",
            expected_state="s1",
            expected_issuer="https://cde.test",
        )


def test_token_exchange_and_refresh_use_the_spec_form_encoding() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201,
            json={
                "access_token": "a2",
                "refresh_token": "r2",
                "expires_in": 60,
                "token_type": "bearer",
                "scope": "bcf",
            },
        )

    oauth = OAuth2Client(
        auth_url="https://cde.test/a",
        token_url="https://cde.test/t",
        client_id="app",
        transport=httpx.MockTransport(handler),
    )
    tokens = oauth.exchange(code="c", verifier="v", redirect_uri="http://127.0.0.1:1/cb")
    body = dict(httpx.QueryParams(seen[0].content.decode()))
    assert body == {
        "grant_type": "authorization_code",
        "code": "c",
        "code_verifier": "v",
        "redirect_uri": "http://127.0.0.1:1/cb",
        "client_id": "app",
    }
    assert tokens.access_token == "a2" and tokens.refresh_token == "r2" and not tokens.is_expired
    refreshed = oauth.refresh(tokens)
    assert dict(httpx.QueryParams(seen[1].content.decode()))["grant_type"] == "refresh_token"
    assert refreshed.scope == "bcf"


def test_confidential_client_uses_basic_authentication() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Basic ")
        assert b"client_id" not in request.content
        return httpx.Response(201, json={"access_token": "a", "expires_in": 60})

    oauth = OAuth2Client(
        auth_url="https://cde.test/a",
        token_url="https://cde.test/t",
        client_id="app",
        client_secret="s",
        transport=httpx.MockTransport(handler),
    )
    assert oauth.exchange(code="c", verifier="v", redirect_uri="http://127.0.0.1:1/cb").refresh_token is None


def test_session_adds_bearer_refreshes_once_and_maps_errors() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("authorization", ""))
        if request.url.path == "/bcf/3.0/projects":
            if request.headers.get("authorization") == "Bearer old":
                return httpx.Response(401, json={"message": "expired"})
            return httpx.Response(200, json=[{"project_id": "p", "name": "P"}])
        return httpx.Response(404, json={"message": "Project not found"})

    def refresher(tokens: TokenSet) -> TokenSet:
        return TokenSet("new", "r", time.time() + 100, "bcf")

    session = ApiSession(
        "https://cde.test",
        tokens=TokenSet("old", "r", time.time() + 100, "bcf"),
        refresher=refresher,
        transport=httpx.MockTransport(handler),
    )
    bcf = BcfClient(session)
    assert bcf.projects() == [{"project_id": "p", "name": "P"}]
    assert calls == ["Bearer old", "Bearer new"], "one refresh and retry after 401"
    with pytest.raises(ApiError) as info:
        bcf.project("nope")
    assert info.value.status_code == 404 and info.value.message == "Project not found"


def test_bcf_requests_follow_the_specification_paths() -> None:
    seen: list[tuple[str, str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/snapshot"):
            return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
        return httpx.Response(200, json={})

    session = ApiSession(
        "https://cde.test", tokens=TokenSet("t", None, time.time() + 100, "bcf"), transport=httpx.MockTransport(handler)
    )
    bcf = BcfClient(session)
    bcf.topics(
        "p", filter="topic_status eq 'Open'", orderby="creation_date desc", top=10, skip=5, include_authorization=True
    )
    bcf.topic_events("p")
    bcf.topic_events("p", "t1", filter="type eq 'status_updated'")
    bcf.comment_events("p", "t1", "c1")
    assert bcf.snapshot("p", "t1", "v1") == (b"\x89PNG", "image/png")
    bcf.set_related_topics("p", "t1", ["t2"])
    bcf.upload_document("p", "Väggar.ifc", b"data", guid="g1")
    assert seen[0] == (
        "GET",
        "/bcf/3.0/projects/p/topics",
        {
            "$filter": "topic_status eq 'Open'",
            "$orderby": "creation_date desc",
            "$top": "10",
            "$skip": "5",
            "includeAuthorization": "true",
        },
    )
    assert seen[1][1] == "/bcf/3.0/projects/p/topics/events"
    assert seen[2] == ("GET", "/bcf/3.0/projects/p/topics/t1/events", {"$filter": "type eq 'status_updated'"})
    assert seen[3][1] == "/bcf/3.0/projects/p/topics/t1/comments/c1/events"
    assert seen[5][0] == "PUT" and seen[5][1].endswith("/related_topics")
    assert seen[6] == ("POST", "/bcf/3.0/projects/p/documents", {"guid": "g1"})
    assert content_disposition("Väggar.ifc") == "attachment; filename=\"V_ggar.ifc\"; filename*=UTF-8''V%C3%A4ggar.ifc"
    assert image_payload(b"\xff\xd8\xff\xe0rest")[0] == "jpg"
    with pytest.raises(ValueError):
        image_payload(b"GIF89a")


def test_documents_upload_follows_the_instructions_and_query_handles_304() -> None:
    received: dict[str, bytes] = {}
    data = bytes(range(256)) * 10

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/parts/"):
            assert request.method == "PUT" and request.headers["x-extra"] == "1"
            assert "authorization" not in request.headers, "include_authorization was false"
            received[request.url.path] = request.content
            return httpx.Response(200)
        if request.url.path == "/complete":
            return httpx.Response(200, text="   \n" + json.dumps({"document_id": "d", "version_index": 1}))
        if request.url.path == "/documents/1.0/document-versions":
            if request.headers.get("if-none-match") == '"abc"':
                return httpx.Response(304, headers={"etag": '"abc"'})
            return httpx.Response(200, json={"versions": []}, headers={"etag": '"abc"'})
        return httpx.Response(404, json={"message": "nope"})

    session = ApiSession(
        "https://cde.test",
        tokens=TokenSet("t", None, time.time() + 100, "documents"),
        transport=httpx.MockTransport(handler),
    )
    documents = DocumentsClient(session)
    plan = {
        "session_file_id": "f1",
        "upload_file_parts": [
            {
                "url": "https://cde.test/parts/1",
                "http_method": "PUT",
                "content_range_start": 0,
                "content_range_end": 1023,
                "include_authorization": False,
                "additional_headers": {"values": [{"name": "X-Extra", "value": "1"}]},
            },
            {
                "url": "https://cde.test/parts/2",
                "http_method": "PUT",
                "content_range_start": 1024,
                "content_range_end": len(data) - 1,
                "include_authorization": False,
                "additional_headers": {"values": [{"name": "X-Extra", "value": "1"}]},
            },
        ],
        "upload_completion": {"url": "https://cde.test/complete"},
        "upload_cancellation": {"url": "https://cde.test/cancel"},
    }
    version = documents.upload_file(plan, data)
    assert version == {"document_id": "d", "version_index": 1}, "leading keep-alive whitespace is tolerated"
    assert received["/parts/1"] + received["/parts/2"] == data
    result, etag = documents.query_versions(["d"])
    assert result == {"versions": []} and etag == '"abc"'
    assert documents.query_versions(["d"], etag=etag) == (None, '"abc"')


def test_discover_without_authentication() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"versions": [{"api_id": "bcf", "version_id": "3.0", "detailed_version": "x"}]})

    versions = discover("https://cde.test/", transport=httpx.MockTransport(handler))
    assert versions[0].api_id == "bcf" and versions[0].version_id == "3.0"


def _server_of_bcf_2_1(request: httpx.Request) -> httpx.Response:
    """A server that has BCF API 2.1 and nothing of the Foundation API."""
    if request.url.path == "/bcf/versions":
        return httpx.Response(200, json={"versions": [{"version_id": "2.1", "detailed_version": "https://example"}]})
    if request.url.path == "/bcf/2.1/auth":
        return httpx.Response(
            200,
            json={
                "oauth2_auth_url": "https://cde.test/oauth2/auth",
                "oauth2_token_url": "https://cde.test/oauth2/token",
                "supported_oauth2_flows": ["authorization_code_grant"],
            },
        )
    if request.url.path == "/bcf/2.1/current-user":
        return httpx.Response(200, json={"id": "someone@example.com", "name": "Someone"})
    if request.url.path == "/bcf/2.1/projects":
        return httpx.Response(200, json=[{"project_id": "p", "name": "A project"}])
    return httpx.Response(404, json={"message": "Not found"})


def _tokens() -> TokenSet:
    return TokenSet("a-bearer", "a-refresh", time.time() + 3600, "bcf")


def test_discover_finds_a_server_without_the_foundation_api() -> None:
    versions = discover("https://cde.test", transport=httpx.MockTransport(_server_of_bcf_2_1))
    assert [(item.api_id, item.version_id) for item in versions] == [("bcf", "2.1")]


def test_auto_takes_what_the_server_has_and_finds_its_way_to_sign_in() -> None:
    transport = httpx.MockTransport(_server_of_bcf_2_1)
    with OpenCdeClient(
        "https://cde.test", client_id="c", bcf_version="auto", tokens=_tokens(), transport=transport
    ) as cde:
        assert cde.bcf.version == "2.1" and cde.bcf.projects()[0]["name"] == "A project"
        assert cde.current_user()["id"] == "someone@example.com"
        assert cde.auth_info.oauth2_token_url == "https://cde.test/oauth2/token"
        assert cde.oauth is not None


def test_auto_takes_the_newest_the_server_offers() -> None:
    def both(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/foundation/versions"
        entries = [("foundation", "1.0"), ("bcf", "2.1"), ("bcf", "3.0"), ("documents", "1.0")]
        return httpx.Response(200, json={"versions": [{"api_id": a, "version_id": v} for a, v in entries]})

    with OpenCdeClient(
        "https://cde.test", client_id="c", bcf_version="auto", transport=httpx.MockTransport(both)
    ) as cde:
        assert cde.bcf.version == "3.0"


def test_auto_says_so_when_it_has_no_version_in_common() -> None:
    def older(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"versions": [{"api_id": "bcf", "version_id": "1.0"}]})

    with (
        OpenCdeClient(
            "https://cde.test", client_id="c", bcf_version="auto", transport=httpx.MockTransport(older)
        ) as cde,
        pytest.raises(NotInThisVersion, match=r"1.0"),
    ):
        _ = cde.bcf


def test_a_client_asks_nobody_until_it_has_to() -> None:
    def nobody(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"asked {request.url}")

    with OpenCdeClient("https://cde.test", client_id="c", transport=httpx.MockTransport(nobody)) as cde:
        assert cde.bcf.version == "3.0", "the default needs no discovery"
    with pytest.raises(ValueError, match="bcf_version"):
        OpenCdeClient("https://cde.test", client_id="c", bcf_version="1.0")


def test_what_came_with_3_0_is_not_asked_of_2_1() -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(200, json=[])

    session = ApiSession("https://cde.test", tokens=_tokens(), transport=httpx.MockTransport(handler))
    older = BcfClient(session, "2.1")
    with pytest.raises(NotInThisVersion, match="files information"):
        older.files_information("p")
    with pytest.raises(NotInThisVersion, match="viewpoints"):
        older.delete_viewpoint("p", "t", "v")
    assert asked == []
    older.topics("p")
    assert asked == ["/bcf/2.1/projects/p/topics"]
    with pytest.raises(NotInThisVersion, match="Foundation"):
        BcfClient(session).current_user()
