# This file was generated with the assistance of an AI coding tool.
"""A client's pop-up keeps its opener through the server's pages, so its callback page can report back.

The headless live suites play the pop-up with a helper and never see this; the owner's run in a real
browser did, when every page still sent ``Cross-Origin-Opener-Policy: same-origin``. The client here is
a page on another local origin that Playwright serves itself, so no second server is needed. (A client
that isolates itself with its own ``same-origin`` policy, as Dataspatium's service worker does, cuts the
opener on its side and must relay the callback another way; that is the client's concern, not tested here.)
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.ui.conftest import LiveServer

_playwright = pytest.importorskip("playwright.sync_api", reason="browser tests need `uv sync --group ui`")
sync_playwright = _playwright.sync_playwright

pytestmark = pytest.mark.ui

APP_ORIGIN = "http://localhost:8099"  # a local origin like a served client; Playwright answers for it
CALLBACK_PAGE = b"<!doctype html><title>callback</title><p id=opener></p>"


def _opener_kept_after(live_server: LiveServer, server_path: str) -> bool:
    """Open ``server_path`` in a pop-up from the client's origin, come back to the client: is window.opener still there?"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        context.route(
            f"{APP_ORIGIN}/**", lambda route: route.fulfill(status=200, content_type="text/html", body=CALLBACK_PAGE)
        )
        page = context.new_page()
        page.goto(f"{APP_ORIGIN}/")
        with context.expect_page() as popup_info:
            page.evaluate(f"window.open('{live_server.url}{server_path}', 'probe', 'popup,width=500,height=600')")
        popup = popup_info.value
        popup.wait_for_url(lambda url: not url.startswith("about:"))  # past the initial about:blank
        popup.wait_for_load_state()
        at_server = bool(popup.evaluate("!!window.opener"))
        # The server sends the browser back with a redirect, a navigation the page itself started; a
        # Playwright goto would be browser-initiated, which Chromium treats like a typed address.
        with popup.expect_navigation():
            popup.evaluate("url => location.assign(url)", f"{APP_ORIGIN}/oauth-callback.html?code=x&state=y")
        back = bool(popup.evaluate("!!window.opener"))
        browser.close()
        return at_server and back


def test_pages_a_client_opens_in_a_popup_keep_the_opener(live_server: LiveServer) -> None:
    client_id = live_server.world.public_client_id
    authorize = f"/foundation/oauth2/auth?response_type=code&client_id={client_id}&state=s&code_challenge=c&code_challenge_method=S256"
    assert _opener_kept_after(live_server, "/signin"), "the sign-in page"
    assert _opener_kept_after(live_server, authorize), "the authorization page"
    assert _opener_kept_after(live_server, "/documents/1.0/document-selection?selection_session=x"), (
        "the selection page"
    )
    # The administration's own policy (same-origin) is checked on the headers in tests/security.


def test_the_sign_in_popup_comes_back_to_the_client(live_server: LiveServer) -> None:
    """The whole pop-up flow in a real browser: the form's redirect to the client is not stopped.

    Chromium checks the page's ``form-action`` policy against the redirect that answers a form,
    so the authorization page must name the client's origin; the owner's quick-start run found
    that Chrome and Edge never left the sign-in page while Firefox did.
    """
    from opencde.auth import pkce

    world = live_server.world
    # The client lives on a real local server: a redirect the browser follows is not answered by a
    # Playwright route. The public client is registered for the loopback address, any port (RFC 8252).
    with _client_site() as app_origin:
        redirect = f"{app_origin}/callback"
        authorize = (
            f"{live_server.url}/foundation/oauth2/auth?response_type=code&client_id={world.public_client_id}"
            f"&redirect_uri={redirect}&state=s-1&code_challenge={pkce.challenge_for('v' * 48)}"
            "&code_challenge_method=S256&scope=profile"
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"{app_origin}/")
            with context.expect_page() as popup_info:
                page.evaluate(f"window.open('{authorize}', 'signin', 'popup,width=500,height=600')")
            popup = popup_info.value
            popup.wait_for_url(lambda url: "/foundation/oauth2/auth" in url)
            popup.fill("input[name=username]", "editor")
            popup.fill("input[name=password]", world.password)
            popup.click("button[name=decision][value=allow]")
            popup.wait_for_url(lambda url: url.startswith(redirect), timeout=15000)
            assert "code=" in popup.url and "state=s-1" in popup.url, popup.url
            assert popup.evaluate("!!window.opener"), "the client's page can still be reached from the pop-up"
            browser.close()


@contextmanager
def _client_site() -> Iterator[str]:
    """A throwaway HTTP server on the loopback address that answers every path with a small page."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(CALLBACK_PAGE)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
