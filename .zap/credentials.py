# This file was generated with the assistance of an AI coding tool.
"""Sign in for the authenticated scan, against a throwaway server with the demo data, and write the plan it runs.

ZAP does not fill in variables in a replacer rule, so the values go into a copy of the plan, which git ignores:

    uv run python .zap/credentials.py <server> <public client id> <demo password>

In GitHub Actions they are also masked in the log.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from opencde_client import OpenCdeClient
from opencde_client.testing import HeadlessBrowser, headless_authorize

REDIRECT = "http://127.0.0.1/callback"
HERE = Path(__file__).parent


def main(server: str, client_id: str, password: str) -> None:
    browser = HeadlessBrowser(server)
    browser.sign_in("admin", password)
    session = browser.http.cookies["opencde_session"]
    browser.close()
    with OpenCdeClient(server, client_id=client_id) as cde:
        manager = headless_authorize(cde.oauth, username="officer", password=password, redirect_uri=REDIRECT)
        admin = headless_authorize(
            cde.oauth,
            username="admin",
            password=password,
            redirect_uri=REDIRECT,
            scopes=("profile", "bcf", "documents", "admin"),
        )
    values = {"SESSION": session, "TOKEN": manager.access_token, "ADMIN_TOKEN": admin.access_token}
    plan = (HERE / "authenticated.yaml").read_text(encoding="utf-8")
    for name, value in values.items():
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::add-mask::{value}")
        plan = plan.replace("${" + name + "}", value)
    (HERE / "authenticated-filled.yaml").write_text(plan, encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:4])
