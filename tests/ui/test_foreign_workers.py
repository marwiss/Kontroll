# This file was generated with the assistance of an AI coding tool.
"""A service worker left on the server's address by another app, in real browsers.

Such a worker answers with old copies of the pages, whose expired form tokens make the sign-in fail. It happens
when another project once ran on the same address, for instance ``python -m http.server`` on its default port 8000,
which is also Dataregium's. So the tests are what happens: the other app first, and then the server on its address.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from starlette.types import Receive, Scope, Send

from opencde.auth import pkce
from opencde.middleware import ForeignWorkerMiddleware
from tests.integration.conftest import GraphTarget
from tests.ui.conftest import LiveServer, _free_port, running_server

_playwright = pytest.importorskip("playwright.sync_api", reason="browser tests need `uv sync --group ui`")
Page = _playwright.Page
PlaywrightError = _playwright.Error
sync_playwright = _playwright.sync_playwright

pytestmark = pytest.mark.ui

WORKER = b"""
const CACHE = "other-app-v3";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(event.request, { ignoreSearch: true });
    const fresh = fetch(event.request).then((response) => {
      if (response.ok) cache.put(event.request, response.clone());
      return response;
    });
    if (hit) { fresh.catch(() => {}); return hit; }
    return fresh;
  })());
});
"""
OLD_PAGE = b"""<!doctype html><title>Another app</title><h1>Another app</h1>
<form method="post" action="/signin"><input type="hidden" name="form_token" value="expired-long-ago">
<input name="username"><input name="password" type="password"><button type="submit">Sign in</button></form>
"""
REGISTER = """
async () => {
  const registration = await navigator.serviceWorker.register("/sw.js");
  const worker = registration.installing || registration.waiting || registration.active;
  if (worker.state !== "activated") {
    await new Promise((resolve) => worker.addEventListener("statechange", () => {
      if (worker.state === "activated") resolve();
    }));
  }
}
"""
NOTHING_LEFT = """
async () => (await navigator.serviceWorker.getRegistrations()).length === 0 && (await caches.keys()).length === 0
"""
BROWSERS = ("chromium", "firefox")


class _OtherApp(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body, kind = (WORKER, "text/javascript") if self.path.startswith("/sw.js") else (OLD_PAGE, "text/html")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@contextmanager
def _other_app(port: int) -> Iterator[None]:
    server = ThreadingHTTPServer(("127.0.0.1", port), _OtherApp)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def _server_beside_the_browser(graph_target: GraphTarget, tmp_path: Path, port: int) -> Iterator[LiveServer]:
    """In a thread of its own: Playwright's sync API holds this thread's event loop, and setting up takes one."""
    server = running_server(graph_target, tmp_path, port=port)
    with ThreadPoolExecutor(1) as pool:
        live = pool.submit(server.__enter__).result()
        try:
            yield live
        finally:
            pool.submit(server.__exit__, None, None, None).result()


@contextmanager
def _browser_page(browser_name: str) -> Iterator[Page]:
    with sync_playwright() as playwright:
        try:
            browser = getattr(playwright, browser_name).launch()
        except PlaywrightError:
            pytest.skip(f"needs `uv run playwright install {browser_name}`")
        try:
            yield browser.new_context().new_page()
        finally:
            browser.close()


def _leave_the_other_apps_worker(page: Page, address: str) -> None:
    page.goto(f"{address}/")
    page.evaluate(REGISTER)
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    page.goto(f"{address}/signin")  # the worker saves this copy
    page.wait_for_timeout(500)
    page.goto(f"{address}/signin")
    assert page.title() == "Another app", "the worker answers from what it saved"


def _go_to(page: Page, address: str) -> None:
    """Firefox can reload the window for the worker's removal in the middle of this, and then it is simply done."""
    try:
        page.goto(address)
    except PlaywrightError:
        page.wait_for_function(NOTHING_LEFT, timeout=30000)
        page.goto(address)


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_a_worker_another_app_left_goes_by_itself_and_the_sign_in_works(
    browser_name: str, graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    port = _free_port()
    address = f"http://127.0.0.1:{port}"
    with _browser_page(browser_name) as page:
        with _other_app(port):
            _leave_the_other_apps_worker(page, address)

        with _server_beside_the_browser(graph_target, tmp_path, port) as live:
            # The old copy still shows, and with no script of the server's in it: the browser's own check does it.
            _go_to(page, f"{address}/signin")
            page.wait_for_function("document.title !== 'Another app'", timeout=30000)
            page.wait_for_function(NOTHING_LEFT, timeout=30000)
            page.wait_for_load_state("load")

            page.locator('input[name="username"]').fill("editor")
            page.locator('input[name="password"]').fill(live.world.password)
            page.locator('button[type="submit"]').first.click()
            page.wait_for_url(lambda url: not url.endswith("/signin"), timeout=15000)

            again = page.request.get(f"{address}/signin", headers={"Accept": "text/html"})
            assert again.status == 200


@pytest.mark.parametrize("browser_name", BROWSERS)
def test_a_failed_sign_in_as_the_worker_goes_stays_on_the_form(
    browser_name: str,
    graph_target: GraphTarget,
    clean_database: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sign-in sent in the seconds before the worker is gone. Fetched again, its page would be an error page."""
    answer = ForeignWorkerMiddleware.__call__

    async def after_the_sign_in(self: ForeignWorkerMiddleware, scope: Scope, receive: Receive, send: Send) -> None:
        if (b"service-worker", b"script") in scope.get("headers", ()):
            await asyncio.sleep(3)
        await answer(self, scope, receive, send)

    monkeypatch.setattr(ForeignWorkerMiddleware, "__call__", after_the_sign_in)
    port = _free_port()
    address = f"http://127.0.0.1:{port}"
    with _browser_page(browser_name) as page:
        with _other_app(port):
            _leave_the_other_apps_worker(page, address)

        with _server_beside_the_browser(graph_target, tmp_path, port) as live:
            world = live.world
            _go_to(
                page,
                f"{address}/foundation/oauth2/auth?response_type=code&client_id={world.public_client_id}"
                f"&redirect_uri={world.redirect}&state=s&code_challenge={pkce.challenge_for('v' * 50)}"
                "&code_challenge_method=S256&scope=bcf",
            )
            page.locator('input[name="username"]').fill("editor")
            page.locator('input[name="password"]').fill("not-the-password")
            page.locator('button[name="decision"][value="allow"]').click()
            page.wait_for_url(lambda url: "?" not in url, timeout=2500)
            page.wait_for_function(NOTHING_LEFT, timeout=30000)
            page.wait_for_timeout(1500)
            assert page.locator('input[name="username"]').count() == 1, page.inner_text("body")[:300]


def test_a_browsers_check_gets_the_script_at_any_address_and_others_get_what_they_always_got(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    import httpx

    check = {"Service-Worker": "script"}
    with running_server(graph_target, tmp_path) as live:
        for path in ("/sw.js", "/sw-coi.js", "/some/other/worker.js", "/signin"):
            answer = httpx.get(f"{live.url}{path}", headers=check)
            assert answer.status_code == 200, path
            assert answer.headers["content-type"].startswith("text/javascript")
            assert answer.headers["cache-control"] == "no-store"
            assert "registration.unregister" in answer.text
            assert answer.headers["x-content-type-options"] == "nosniff"
        assert httpx.get(f"{live.url}/sw.js").status_code == 404
        assert httpx.get(f"{live.url}/signin").headers["content-type"].startswith("text/html")
        assert httpx.post(f"{live.url}/sw.js", headers=check).status_code != 200
