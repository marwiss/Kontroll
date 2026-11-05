# This file was generated with the assistance of an AI coding tool.
"""The admin UI in a real browser: sign-in, every page, accessibility (axe-core), the enhancements, no console errors."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from tests.ui.conftest import LiveServer

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
    for path in PAGES:
        browser_page.goto(path)
        expect(browser_page.get_by_role("main")).to_be_visible()
        assert browser_page.title().endswith("OpenCDE server"), path
        violations = serious_violations(browser_page)
        assert violations == [], f"{path}: {violations}"
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
