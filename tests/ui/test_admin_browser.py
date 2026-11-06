# This file was generated with the assistance of an AI coding tool.
"""The admin UI in a real browser: sign-in, every page, accessibility (axe-core), the enhancements, no console errors."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from opencde_client import ApiError, AuthError, OAuth2Client, OpenCdeClient, generate_state, generate_verifier
from tests.ui.conftest import LiveServer
from tests.ui.test_popup_opener import _client_site

# The browser tools live in the optional ``ui`` dependency group; without it this module is skipped,
# not broken, when the whole tree is collected.
_playwright = pytest.importorskip("playwright.sync_api", reason="browser tests need `uv sync --group ui`")
_axe = pytest.importorskip("axe_playwright_python.sync_playwright", reason="browser tests need `uv sync --group ui`")
Axe = _axe.Axe
Page = _playwright.Page
expect = _playwright.expect
sync_playwright = _playwright.sync_playwright

pytestmark = pytest.mark.ui

PAGES = (
    "/",
    "/admin",
    "/admin/users",
    "/admin/users/new",
    "/admin/projects",
    "/admin/projects/new",
    "/admin/clients",
    "/admin/clients/new",
    "/admin/sessions",
    "/admin/audit",
    "/admin/settings",
    "/account",
)


@pytest.fixture
def page(live_server: LiveServer) -> Iterator[tuple[Page, list[str]]]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(base_url=live_server.url, viewport={"width": 1280, "height": 900})
        page = context.new_page()
        problems: list[str] = []
        page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: problems.append(str(error)))
        try:
            yield page, problems
        finally:
            context.close()
            browser.close()


def sign_in(page: Page, live_server: LiveServer, username: str) -> None:
    page.goto("/signin")
    page.get_by_label("User name").fill(username)
    page.get_by_label("Password").fill(live_server.world.password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(lambda url: not url.endswith("/signin"))


def serious_violations(page: Page) -> list[str]:
    results = Axe().run(page)
    return [
        f"{violation['id']}: {violation['help']} ({violation['impact']})"
        for violation in results.response["violations"]
        if violation.get("impact") in ("serious", "critical")
    ]


def test_admin_pages_are_accessible_and_quiet(page: tuple[Page, list[str]], live_server: LiveServer) -> None:
    browser_page, problems = page
    sign_in(browser_page, live_server, "admin")
    world = live_server.world
    browser_page.goto("/admin/users")
    user_page = browser_page.get_by_role("link", name="editor", exact=True).get_attribute("href")
    for path in (
        *PAGES,
        user_page,
        f"/admin/projects/{world.project_id}",
        f"/admin/clients/{world.public_client_id}",
    ):
        browser_page.goto(path)
        expect(browser_page.get_by_role("main")).to_be_visible()
        assert browser_page.title().endswith("OpenCDE server"), path
        violations = serious_violations(browser_page)
        assert violations == [], f"{path}: {violations}"
        # The browser refuses a form over a required field nobody can see, without saying why.
        assert browser_page.locator("details:not([open]) [required]").count() == 0, path
    assert problems == [], "no console errors (CSP violations would show up here)"


def test_admin_creates_a_project_and_a_user_through_the_forms(
    page: tuple[Page, list[str]], live_server: LiveServer
) -> None:
    browser_page, problems = page
    sign_in(browser_page, live_server, "admin")

    browser_page.goto("/admin/projects/new")
    browser_page.get_by_label("Name").fill("Browser project")
    browser_page.get_by_role("button", name="Create project").click()
    expect(browser_page.get_by_role("heading", name="Browser project")).to_be_visible()
    expect(browser_page.get_by_role("status")).to_contain_text("Created.")

    browser_page.get_by_label("Add member").select_option(label="viewer")
    browser_page.get_by_label("Role", exact=True).select_option("manager")
    browser_page.get_by_role("button", name="Add member").click()
    expect(browser_page.get_by_role("status")).to_contain_text("Membership saved.")
    expect(browser_page.get_by_role("link", name="viewer")).to_be_visible()

    # The confirmation dialog intercepts the removal; cancelling keeps the member.
    browser_page.get_by_role("button", name="Remove").first.click()
    dialog = browser_page.locator("dialog.confirm")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("Remove viewer from Browser project?")
    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden()
    expect(browser_page.get_by_role("link", name="viewer")).to_be_visible()
    browser_page.get_by_role("button", name="Remove").first.click()
    dialog.get_by_role("button", name="Confirm").click()
    expect(browser_page.get_by_role("status")).to_contain_text("Membership removed.")

    browser_page.goto("/admin/users/new")
    browser_page.get_by_label("User name").fill("browser.user")
    browser_page.get_by_label("Full name").fill("Browser User")
    browser_page.get_by_role("button", name="Create user").click()
    expect(browser_page.get_by_role("heading", name="Password for browser.user")).to_be_visible()
    secret = browser_page.locator("#secret-value").inner_text().strip()
    assert len(secret) >= 20
    expect(browser_page.get_by_role("button", name="Copy")).to_be_visible()

    browser_page.goto("/admin/users")
    filter_box = browser_page.get_by_placeholder("Filter rows…")
    expect(filter_box).to_be_visible()
    filter_box.fill("browser")
    expect(browser_page.get_by_role("status")).to_contain_text("1 of")
    expect(browser_page.get_by_role("link", name="browser.user")).to_be_visible()
    expect(browser_page.get_by_role("link", name="editor", exact=True)).to_be_hidden()
    browser_page.get_by_role("columnheader", name="User name").click()
    assert browser_page.get_by_role("columnheader", name="User name").get_attribute("aria-sort") == "ascending"
    assert problems == []


def test_the_whole_way_from_the_administration_to_an_issue_and_back(
    page: tuple[Page, list[str]], live_server: LiveServer
) -> None:
    """An administrator sets up a project, a user and a public client in the forms. The new user signs in from
    the client library in a browser of their own and files an issue. The administrator disables the user, and
    the token stops working at once."""
    admin, problems = page
    sign_in(admin, live_server, "admin")

    admin.goto("/admin/projects/new")
    admin.get_by_label("Name").fill("The whole way")
    admin.get_by_role("button", name="Create project").click()
    expect(admin.get_by_role("heading", name="The whole way")).to_be_visible()
    project_id = admin.url.split("/admin/projects/")[1].split("?")[0]

    admin.goto("/admin/users/new")
    admin.get_by_label("User name").fill("whole.way")
    admin.get_by_role("button", name="Create user").click()
    expect(admin.get_by_role("heading", name="Password for whole.way")).to_be_visible()
    password = admin.locator("#secret-value").inner_text().strip()

    admin.goto(f"/admin/projects/{project_id}")
    admin.get_by_label("Add member").select_option(label="whole.way")
    admin.get_by_label("Role", exact=True).select_option("editor")
    admin.get_by_role("button", name="Add member").click()
    expect(admin.get_by_role("status")).to_contain_text("Membership saved.")

    admin.goto("/admin/clients/new")
    admin.get_by_label("Name").fill("A viewer of the new user's")
    admin.get_by_label("Redirect URIs").fill("http://127.0.0.1/callback")
    admin.get_by_label("Type").select_option("public")
    admin.get_by_role("button", name="Register client").click()
    expect(admin.get_by_role("heading", name="A viewer of the new user's")).to_be_visible()
    client_id = admin.url.split("/admin/clients/")[1].split("?")[0]

    cde = OpenCdeClient(live_server.url, client_id=client_id)
    state, verifier = generate_state(), generate_verifier()
    own_browser = admin.context.browser.new_context()  # type: ignore[union-attr]
    person = own_browser.new_page()
    with _client_site() as app_origin:
        redirect = f"{app_origin}/callback"
        person.goto(cde.oauth.authorization_url(redirect_uri=redirect, state=state, verifier=verifier))
        person.get_by_label("User name").fill("whole.way")
        person.get_by_label("Password").fill(password)
        person.get_by_role("button", name="Allow and sign in").click()
        # A password someone else knows is good for one thing: changing it. The flow then goes on by itself.
        expect(person.get_by_role("heading", name="Change password")).to_be_visible()
        chosen = "correct-horse-battery-staple-2026"
        person.get_by_label("Current password").fill(password)
        person.get_by_label("New password", exact=True).fill(chosen)
        person.get_by_label("Repeat new password").fill(chosen)
        person.get_by_role("button", name="Change password").click()
        person.get_by_label("User name").fill("whole.way")
        person.get_by_label("Password").fill(chosen)
        person.get_by_role("button", name="Allow and sign in").click()
        person.wait_for_url(lambda url: url.startswith(redirect))
        code = OAuth2Client.parse_callback(person.url, expected_state=state)
    own_browser.close()
    cde.use_tokens(cde.oauth.exchange(code=code, verifier=verifier, redirect_uri=redirect))

    with cde:
        assert cde.foundation.current_user()["id"] == "whole.way"
        topic = cde.bcf.create_topic(project_id, {"title": "Filed by the new user"})
        assert [found["guid"] for found in cde.bcf.topics(project_id)] == [topic["guid"]]

        admin.goto("/admin/users")
        admin.get_by_role("link", name="whole.way").click()
        admin.get_by_label("Disabled: cannot sign in; tokens are revoked").check()
        admin.get_by_role("button", name="Save").click()
        expect(admin.get_by_role("status")).to_be_visible()

        with pytest.raises((ApiError, AuthError)):
            cde.foundation.current_user()
    assert problems == []


def test_a_form_on_a_page_saves_in_place_and_again(page: tuple[Page, list[str]], live_server: LiveServer) -> None:
    admin, problems = page
    sign_in(admin, live_server, "admin")
    admin.goto("/admin/users")
    admin.get_by_role("link", name="viewer", exact=True).click()
    admin.evaluate("window.stillHere = true")

    admin.get_by_label("Full name").fill("A first name")
    admin.get_by_role("button", name="Save").click()
    expect(admin.locator(".alert")).to_contain_text("Saved")
    assert admin.evaluate("window.stillHere === true"), "the page was not loaded again"
    assert "notice=saved" in admin.url, "the address says what a reload would show"
    assert admin.evaluate("document.activeElement.classList.contains('alert')"), "the keyboard follows the message"

    # The new page's form has its own token, so it saves again.
    admin.get_by_label("Full name").fill("A second name")
    admin.get_by_role("button", name="Save").click()
    expect(admin.get_by_label("Full name")).to_have_value("A second name")
    assert admin.evaluate("window.stillHere === true")

    # What the scripts add comes back: the confirmation stands before a removal.
    remove = admin.get_by_role("button", name="Remove").first
    remove.click()
    dialog = admin.locator("dialog.confirm")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Confirm").click()
    expect(admin.locator(".alert")).to_contain_text("Membership removed.")
    assert admin.evaluate("window.stillHere === true")
    admin.reload()
    expect(admin.get_by_label("Full name")).to_have_value("A second name")
    assert problems == []


def test_the_same_form_works_without_javascript(page: tuple[Page, list[str]], live_server: LiveServer) -> None:
    browser = page[0].context.browser
    context = browser.new_context(base_url=live_server.url, java_script_enabled=False)  # type: ignore[union-attr]
    plain = context.new_page()
    sign_in(plain, live_server, "admin")
    plain.goto("/admin/users")
    plain.get_by_role("link", name="viewer", exact=True).click()
    plain.get_by_label("Full name").fill("Without scripts")
    plain.get_by_role("button", name="Save").click()
    expect(plain.locator(".alert")).to_contain_text("Saved")
    expect(plain.get_by_label("Full name")).to_have_value("Without scripts")
    context.close()
