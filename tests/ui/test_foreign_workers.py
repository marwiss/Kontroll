# This file was generated with the assistance of an AI coding tool.
"""A service worker left on the server's address by another app, in a real browser.

Such a worker answers with old copies of the pages, whose expired form tokens make the sign-in fail. It
happens when another project once ran on the same address, for instance ``python -m http.server`` on its
default port 8000, which is also Kontroll's.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import Response

from tests.ui.conftest import LiveServer

_playwright = pytest.importorskip("playwright.sync_api", reason="browser tests need `uv sync --group ui`")
Page = _playwright.Page
sync_playwright = _playwright.sync_playwright

pytestmark = pytest.mark.ui

WORKER = """
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
"""

REGISTER = """
async (scope) => {
  const registration = await navigator.serviceWorker.register("/sw.js", { scope });
  const worker = registration.installing || registration.waiting || registration.active;
  if (worker.state !== "activated") {
    await new Promise((resolve) => worker.addEventListener("statechange", () => {
      if (worker.state === "activated") resolve();
    }));
  }
}
"""

COUNT = "async () => (await navigator.serviceWorker.getRegistrations()).length"


def _worker_script() -> Response:
    return Response(WORKER, media_type="text/javascript")


@pytest.fixture
def page(live_server: LiveServer) -> Iterator[Page]:
    live_server.app.add_api_route("/sw.js", _worker_script, include_in_schema=False)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        try:
            yield context.new_page()
        finally:
            browser.close()


def _loads_of(page: Page) -> list[str]:
    """The page's navigations. Not its load events: a quick reload can cancel the first load before it fires."""
    loads: list[str] = []
    page.on("request", lambda request: loads.append(request.url) if request.is_navigation_request() else None)
    return loads


def test_a_worker_covering_the_page_is_removed_and_the_page_fetched_again(page: Page, live_server: LiveServer) -> None:
    signin = f"{live_server.url}/signin"
    page.goto(signin)
    page.evaluate(REGISTER, "/")
    page.wait_for_function("navigator.serviceWorker.controller !== null")

    loads = _loads_of(page)
    page.goto(signin)
    page.wait_for_function("navigator.serviceWorker.controller === null")
    page.wait_for_load_state("load")

    assert page.evaluate(COUNT) == 0
    assert len(loads) == 2, "the first load came from the worker, and the script fetched the page once more"
    page.locator('input[name="username"]').wait_for()

    page.goto(signin)
    page.wait_for_timeout(500)
    assert len(loads) == 3, "with no worker left, a later visit loads once"


def test_a_worker_that_does_not_go_away_causes_one_reload_and_no_loop(page: Page, live_server: LiveServer) -> None:
    page.add_init_script(
        """
        Object.defineProperty(ServiceWorkerContainer.prototype, "controller", { get: () => ({}) });
        ServiceWorkerContainer.prototype.getRegistrations = async () => [
          { scope: location.origin + "/", unregister: async () => true },
        ];
        """
    )
    loads = _loads_of(page)
    page.goto(f"{live_server.url}/signin")
    page.wait_for_timeout(1500)
    assert len(loads) == 2


def test_a_worker_for_another_path_stays_and_nothing_reloads(page: Page, live_server: LiveServer) -> None:
    """An app on another path of the same address is none of this server's business."""
    signin = f"{live_server.url}/signin"
    page.goto(signin)
    page.evaluate(REGISTER, "/another-app/")

    loads = _loads_of(page)
    page.goto(signin)
    page.wait_for_timeout(800)

    assert page.evaluate(COUNT) == 1
    assert len(loads) == 1


def test_a_page_without_a_worker_loads_once(page: Page, live_server: LiveServer) -> None:
    loads = _loads_of(page)
    page.goto(f"{live_server.url}/signin")
    page.wait_for_timeout(500)
    assert len(loads) == 1
