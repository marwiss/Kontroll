# This file was generated with the assistance of an AI coding tool.
"""The web administration: access control, CSRF, and every management flow at the HTTP level."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from opencde.settings import Settings
from opencde.store.accounts.projects import PRAXI_STATUSES
from tests.integration.conftest_accounts import World, build_world, login_as
from tests.integration.helpers import authorize, exchange
from tests.integration.test_web_signin import form_token, web_sign_in

INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)")  # the pages load files from their own origin, nothing inline

pytestmark = [pytest.mark.integration, pytest.mark.security]

SECRET = re.compile(r'id="secret-value">([^<]+)<')
USER_LINK = re.compile(r'href="/admin/users/([0-9a-f-]{36})"')
ADMIN_PAGES = (
    "/admin",
    "/admin/users",
    "/admin/users/new",
    "/admin/projects",
    "/admin/projects/new",
    "/admin/clients",
    "/admin/clients/new",
    "/admin/sessions",
    "/admin/audit",
    "/admin/audit.csv",
    "/admin/requests",
    "/admin/settings",
)


@pytest.fixture
def world(settings: Settings, clean_database: None) -> World:
    return build_world(settings)


def notice_of(response: Any) -> str:
    assert response.status_code == 303, response.text[:300]
    return parse_qs(urlsplit(response.headers["location"]).query).get("notice", [""])[0]


def post(client: TestClient, path: str, page_html: str, **fields: str) -> Any:
    return client.post(path, data={"form_token": form_token(page_html), **fields}, follow_redirects=False)


def test_admin_pages_need_the_admin_role(client: TestClient, world: World) -> None:
    anonymous = client.get("/admin", follow_redirects=False)
    assert anonymous.status_code == 302 and anonymous.headers["location"].startswith("/signin?next=%2Fadmin")

    web_sign_in(client, world, "viewer")
    for path in ADMIN_PAGES:
        response = client.get(path)
        assert response.status_code == 404, path
        assert "There is no such page" in response.text, "an HTML 404 for browsers"
    assert client.post("/admin/projects", data={"name": "x"}, follow_redirects=False).status_code == 404
    assert client.get("/account").status_code == 200, "every signed-in user has an account page"
    client.cookies.clear()

    web_sign_in(client, world, "admin")
    for path in ADMIN_PAGES:
        response = client.get(path)
        assert response.status_code == 200, path
        if path.endswith(".csv"):
            continue
        assert response.headers["content-security-policy"].startswith("default-src 'none'")
        assert not INLINE_SCRIPT.search(response.text)
        assert ' style="' not in response.text and "onclick" not in response.text
    assert client.get("/static/js/admin.js").status_code == 200


def test_csrf_protections_on_admin_forms(client: TestClient, world: World) -> None:
    web_sign_in(client, world, "admin")
    assert (
        notice_of(client.post("/admin/projects", data={"name": "No token"}, follow_redirects=False)) == "form_expired"
    )
    page = client.get("/admin/projects/new").text
    cross = client.post(
        "/admin/projects",
        data={"form_token": form_token(page), "name": "Cross"},
        headers={"Sec-Fetch-Site": "cross-site"},
        follow_redirects=False,
    )
    assert cross.status_code == 403
    users_page = client.get("/admin/users/new").text
    wrong_purpose = client.post(
        "/admin/projects", data={"form_token": form_token(users_page), "name": "Wrong"}, follow_redirects=False
    )
    assert notice_of(wrong_purpose) == "form_expired", "a token for one form does not work on another"
    assert "No token" not in client.get("/admin/projects").text and "Cross" not in client.get("/admin/projects").text


def test_validation_messages_follow_the_page_language(client: TestClient, world: World) -> None:
    web_sign_in(client, world, "admin")
    page = client.get("/admin/users/new", params={"lang": "sv"}).text  # sets the language cookie as well
    refused = post(client, "/admin/users", page, username="x", full_name="", email="")
    assert "Användarnamnet måste vara 3–128 tecken" in refused.text, "the repository's message in the page language"  # noqa: RUF001
    assert "user name: 3-128" not in refused.text
    weak = post(client, "/admin/users", page, username="weak_user", full_name="", email="", password="short")
    assert "Lösenordet avvisades: använd minst 12 tecken" in weak.text
    english = client.get("/admin/clients/new", params={"lang": "en"}).text
    bad_client = post(client, "/admin/clients", english, name="x", redirect_uris="not a uri", public="on")
    assert "The redirect URI must be absolute." in bad_client.text


def test_user_management(client: TestClient, world: World) -> None:
    web_sign_in(client, world, "admin")
    created = post(
        client,
        "/admin/users",
        client.get("/admin/users/new").text,
        username="inspector",
        full_name="Inga Inspector",
        email="inga@example.test",
    )
    assert created.status_code == 200, "a generated password is shown once"
    password = SECRET.search(created.text).group(1)  # type: ignore[union-attr]
    user_id = USER_LINK.search(created.text).group(1)  # type: ignore[union-attr]
    assert len(password) >= 20 and "must be changed" in created.text
    assert "inspector" in client.get("/admin/users", params={"q": "inga"}).text

    page = client.get(f"/admin/users/{user_id}")
    assert page.status_code == 200 and "must change password" in page.text
    assert (
        notice_of(
            post(
                client,
                f"/admin/users/{user_id}",
                page.text,
                action="update",
                full_name="Inga I.",
                email="inga@example.test",
            )
        )
        == "saved"
    )
    assert (
        notice_of(
            post(
                client,
                f"/admin/users/{user_id}",
                page.text,
                action="membership",
                project_id=world.project_id,
                role="editor",
            )
        )
        == "member_saved"
    )
    page = client.get(f"/admin/users/{user_id}")
    assert "Building permit" in page.text and 'value="editor" selected' in page.text
    assert (
        notice_of(
            post(
                client,
                f"/admin/users/{user_id}",
                page.text,
                action="membership",
                project_id=world.project_id,
                role="owner",
            )
        )
        == "invalid"
    )
    assert (
        notice_of(
            post(client, f"/admin/users/{user_id}", page.text, action="update", is_admin="on", full_name="Inga I.")
        )
        == "wrong_password"
    )
    assert (
        notice_of(
            post(
                client,
                f"/admin/users/{user_id}",
                page.text,
                action="update",
                is_admin="on",
                full_name="Inga I.",
                confirm_password=world.password,
            )
        )
        == "saved"
    )
    assert "admin" in client.get("/admin/users", params={"q": "inspector"}).text
    assert (
        notice_of(
            post(client, f"/admin/users/{user_id}", page.text, action="remove_membership", project_id=world.project_id)
        )
        == "member_removed"
    )

    # The new user signs in with the generated password and must change it first.
    admin_cookies = dict(client.cookies)
    client.cookies.clear()
    signin = client.get("/signin").text
    response = client.post(
        "/signin",
        data={"form_token": form_token(signin), "username": "inspector", "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302 and response.headers["location"] == "/account?notice=change_password"
    account = client.get("/account")
    assert "Choose your own" in account.text
    strong = "correct-horse-battery-staple-2026"
    assert (
        notice_of(
            post(
                client,
                "/account",
                account.text,
                action="change_password",
                current_password="wrong",
                new_password=strong,
                repeat_password=strong,
            )
        )
        == "wrong_password"
    )
    mismatch = post(
        client,
        "/account",
        account.text,
        action="change_password",
        current_password=password,
        new_password=strong,
        repeat_password=strong + "x",
    )
    assert mismatch.status_code == 400
    assert (
        notice_of(
            post(
                client,
                "/account",
                account.text,
                action="change_password",
                current_password=password,
                new_password=strong,
                repeat_password=strong,
            )
        )
        == "password_changed"
    )
    client.cookies.clear()
    for name, value in admin_cookies.items():
        client.cookies.set(name, value)

    # Reset password, self-protection and deletion.
    page = client.get(f"/admin/users/{user_id}").text
    reset = post(client, f"/admin/users/{user_id}", page, action="reset_password", confirm_password=world.password)
    assert reset.status_code == 200 and SECRET.search(reset.text)
    me = client.get(f"/admin/users/{world.users['admin']}").text
    assert (
        notice_of(
            post(client, f"/admin/users/{world.users['admin']}", me, action="update", disabled="on", is_admin="on")
        )
        == "not_yourself"
    )
    assert (
        notice_of(
            post(client, f"/admin/users/{world.users['admin']}", me, action="delete", confirm_password=world.password)
        )
        == "not_yourself"
    )
    assert (
        notice_of(post(client, f"/admin/users/{user_id}", page, action="delete", confirm_password="nope"))
        == "wrong_password"
    )
    assert (
        notice_of(post(client, f"/admin/users/{user_id}", page, action="delete", confirm_password=world.password))
        == "deleted"
    )
    assert client.get(f"/admin/users/{user_id}").status_code == 404
    assert "admin.user.delete" in client.get("/admin/audit", params={"type": "admin.user"}).text


def test_project_management_reaches_the_bcf_api(client: TestClient, world: World) -> None:
    web_sign_in(client, world, "admin")
    created = post(client, "/admin/projects", client.get("/admin/projects/new").text, name="Renovation")
    assert notice_of(created) == "created"
    project_path = urlsplit(created.headers["location"]).path
    project_id = project_path.rsplit("/", 1)[-1]
    page = client.get(project_path).text
    assert "Renovation" in page and "No members yet" in page

    assert notice_of(post(client, project_path, page, action="rename", name="Renovation 2026")) == "saved"
    assert (
        notice_of(post(client, project_path, page, action="member", user_id=world.users["viewer"], role="contributor"))
        == "member_saved"
    )
    assert (
        notice_of(
            post(
                client,
                project_path,
                page,
                action="extensions",
                topic_type="Issue\nRequest",
                topic_status="Open\nClosed\n\nClosed",
                topic_label="A",
                snippet_type=".ifc",
                priority="High",
                stage="Design",
                custom_information="",
            )
        )
        == "extensions_saved"
    )
    assert notice_of(post(client, project_path, page, action="checks", block_on_validation_errors="on")) == "saved"
    assert 'name="block_on_validation_errors" value="on" checked' in client.get(project_path).text
    assert notice_of(post(client, project_path, page, action="checks")) == "saved"
    assert 'name="block_on_validation_errors" value="on" checked' not in client.get(project_path).text

    viewer = login_as(client, world, "viewer")
    projects = client.get("/bcf/3.0/projects", headers=viewer.headers).json()
    assert {p["name"] for p in projects} == {"Building permit", "Renovation 2026"}
    extensions = client.get(f"/bcf/3.0/projects/{project_id}/extensions", headers=viewer.headers).json()
    assert extensions["topic_status"] == ["Open", "Closed"] and extensions["users"] == ["viewer"]
    assert extensions["project_actions"] == ["createTopic", "createDocument"], "contributor role (B-67)"
    assert notice_of(post(client, project_path, page, action="praxi_statuses")) == "extensions_saved"
    praxi = client.get(f"/bcf/3.0/projects/{project_id}/extensions", headers=viewer.headers).json()
    assert praxi["topic_status"] == list(PRAXI_STATUSES) and praxi["topic_type"] == ["Issue", "Request"], "B-68"

    assert (
        notice_of(post(client, project_path, page, action="remove_member", user_id=world.users["viewer"]))
        == "member_removed"
    )
    assert client.get(f"/bcf/3.0/projects/{project_id}", headers=viewer.headers).status_code == 404
    assert notice_of(post(client, project_path, page, action="delete", confirm_password="nope")) == "wrong_password"
    assert notice_of(post(client, project_path, page, action="delete", confirm_password=world.password)) == "deleted"
    assert client.get(project_path).status_code == 404


def test_client_management_and_secret_rotation(client: TestClient, world: World) -> None:
    web_sign_in(client, world, "admin")
    created = post(
        client,
        "/admin/clients",
        client.get("/admin/clients/new").text,
        name="Server app 2",
        kind="confidential",
        redirect_uris="https://app.example.test/callback\nhttp://127.0.0.1/cb",
        description="Integration",
    )
    assert created.status_code == 200
    secret = SECRET.search(created.text).group(1)  # type: ignore[union-attr]
    client_id = re.search(r'id="extra-value">([0-9a-f-]{36})<', created.text).group(1)  # type: ignore[union-attr]
    bad = post(
        client,
        "/admin/clients",
        client.get("/admin/clients/new").text,
        name="Bad",
        kind="public",
        redirect_uris="http://evil.example/cb",
    )
    assert bad.status_code == 400 and "loopback" in bad.text

    code, _, verifier = authorize(
        client,
        client_id=client_id,
        redirect_uri="https://app.example.test/callback",
        username="editor",
        password=world.password,
    )
    assert code
    session = exchange(client, code=code, verifier=verifier, client_id=client_id, client_secret=secret)
    assert client.get("/foundation/1.0/current-user", headers=session.headers).status_code == 200

    page = client.get(f"/admin/clients/{client_id}").text
    assert "Server app 2" in page and "Rotate secret" in page
    assert (
        notice_of(
            post(
                client,
                f"/admin/clients/{client_id}",
                page,
                action="update",
                name="Server app 3",
                redirect_uris="https://app.example.test/callback",
                description="",
                url="",
            )
        )
        == "saved"
    )
    rotated = post(client, f"/admin/clients/{client_id}", page, action="rotate", confirm_password=world.password)
    assert rotated.status_code == 200
    new_secret = SECRET.search(rotated.text).group(1)  # type: ignore[union-attr]
    assert new_secret != secret
    code, _, verifier = authorize(
        client,
        client_id=client_id,
        redirect_uri="https://app.example.test/callback",
        username="editor",
        password=world.password,
    )
    old = client.post(
        "/foundation/oauth2/token",
        data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier},
        auth=(client_id, secret),
    )
    assert old.status_code == 401, "the old secret stopped working"

    assert notice_of(post(client, f"/admin/clients/{client_id}", page, action="revoke")) == "revoked"
    assert client.get("/foundation/1.0/current-user", headers=session.headers).status_code == 401
    assert (
        notice_of(post(client, f"/admin/clients/{client_id}", page, action="delete", confirm_password=world.password))
        == "deleted"
    )
    assert client.get(f"/admin/clients/{client_id}").status_code == 404


def test_sessions_audit_and_settings_pages(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "admin")
    sessions = client.get("/admin/sessions")
    assert "Native app" in sessions.text and ">editor<" in sessions.text
    family = re.search(r'name="family_id" value="([0-9a-f-]{36})"', sessions.text).group(1)  # type: ignore[union-attr]
    assert (
        notice_of(
            post(
                client,
                "/admin/sessions",
                sessions.text,
                action="revoke_family",
                user_id=world.users["editor"],
                family_id=family,
            )
        )
        == "revoked"
    )
    assert client.get("/foundation/1.0/current-user", headers=editor.headers).status_code == 401

    audit = client.get("/admin/audit", params={"type": "admin.session"})
    assert "admin.session.revoke_family" in audit.text
    csv = client.get("/admin/audit.csv", params={"type": "admin."})
    assert (
        csv.headers["content-type"].startswith("text/csv")
        and csv.text.splitlines()[0] == "at,type,actor,client_id,ip,details"
    )
    assert "admin.session.revoke_family" in csv.text

    settings_page = client.get("/admin/settings").text
    assert "OPENCDE_PUBLIC_URL" in settings_page and "http://testserver" in settings_page
    assert "Graph database" in settings_page and 'class="badge badge--danger"' not in settings_page
    assert "test-secret-key" not in settings_page and "test-password" not in settings_page
    swedish = client.get("/admin/settings", headers={"Accept-Language": "sv"}).text
    assert "Grafdatabas" in swedish and "check." not in swedish, "the checks speak the language of the page"

    overview = client.get("/admin").text
    assert "Recent audit events" in overview and "admin.session.revoke_family" in overview


def test_account_page_apps_and_sessions(client: TestClient, world: World) -> None:
    editor = login_as(client, world, "editor")
    web_sign_in(client, world, "editor")
    account = client.get("/account")
    assert account.status_code == 200 and "Native app" in account.text and "this browser" in account.text
    family = re.search(r'name="family_id" value="([0-9a-f-]{36})"', account.text).group(1)  # type: ignore[union-attr]
    assert notice_of(post(client, "/account", account.text, action="revoke_app", family_id=family)) == "revoked"
    assert client.get("/foundation/1.0/current-user", headers=editor.headers).status_code == 401
    assert "/admin" not in client.get("/account").text, "no admin link for ordinary users"
    assert notice_of(post(client, "/account", account.text, action="sign_out_everywhere")) == "revoked"
    assert client.get("/account", follow_redirects=False).status_code == 302, "signed out"
