# This file was generated with the assistance of an AI coding tool.
"""Sign in to an OpenCDE server from a script: authorization code flow with PKCE through your browser.

    uv run python docs/examples/login_pkce.py https://cde.example my-client-id

The administrator registers ``my-client-id`` as a public client with the
redirect URI ``http://127.0.0.1/callback`` (any port is accepted for loopback
addresses, RFC 8252). The script opens the browser, waits for the redirect and
prints who you are.
"""

import sys

from opencde_client import OpenCdeClient


def main(server: str, client_id: str) -> None:
    with OpenCdeClient(server, client_id=client_id) as cde:
        for api in cde.foundation.versions():
            print(f"{api.api_id} {api.version_id}")
        tokens = cde.login()  # opens the browser
        print(f"signed in with scopes: {tokens.scope}")
        user = cde.foundation.current_user()
        print(f"you are {user['id']} ({user.get('name', '')})")
        for project in cde.bcf.projects(include_authorization=True):
            print(
                f"- {project['name']}  actions: {', '.join(project.get('authorization', {}).get('project_actions', []))}"
            )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
