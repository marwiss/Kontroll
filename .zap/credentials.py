# This file was generated with the assistance of an AI coding tool.
"""Sign in for the authenticated scan and hand over what it needs, against a throwaway server with the demo data.

Prints the values as environment lines, and in GitHub Actions masks them in the log and adds them to the job:

    uv run python .zap/credentials.py <server> <public client id> <demo password>
"""

from __future__ import annotations

import os
import sys

from opencde_client import OpenCdeClient
from opencde_client.testing import HeadlessBrowser, headless_authorize

REDIRECT = "http://127.0.0.1/callback"


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
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as env:
            for name, value in values.items():
                print(f"::add-mask::{value}")
                env.write(f"{name}={value}\n")
    else:
        for name, value in values.items():
            print(f"{name}={value}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
