# This file was generated with the assistance of an AI coding tool.
"""A small command line: ``python -m opencde_client --server URL --client-id ID <command>``.

Commands: ``discover``, ``login`` (opens the browser and stores the tokens in a
file only you can read), ``whoami``, ``projects``, ``topics PROJECT_ID``.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
from pathlib import Path

from opencde_client import OpenCdeClient, TokenSet, discover
from opencde_client.errors import OpenCdeError


def _token_file(server: str) -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "opencde-client"
    safe = "".join(ch if ch.isalnum() else "_" for ch in server)
    return base / f"{safe}.json"


def _save_tokens(path: Path, tokens: TokenSet) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at,
        "scope": tokens.scope,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    if os.name != "nt":
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _load_tokens(path: Path) -> TokenSet | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return TokenSet(data["access_token"], data.get("refresh_token"), float(data["expires_at"]), data.get("scope", ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-client", description="Talk to an OpenCDE server.")
    parser.add_argument("--server", required=True, help="Base URL of the server, e.g. https://cde.example")
    parser.add_argument("--client-id", help="The OAuth2 client id registered for this application")
    parser.add_argument("--client-secret", help="Secret of a confidential client (omit for public clients)")
    parser.add_argument(
        "--bcf-version",
        choices=("auto", "3.0", "2.1"),
        default="auto",
        help="Version of the BCF API to speak; auto takes the newest the server offers",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover", help="List the APIs the server offers")
    commands.add_parser("login", help="Sign in through the browser and store the tokens")
    commands.add_parser("whoami", help="Show the signed-in user")
    commands.add_parser("projects", help="List the projects you are a member of")
    topics = commands.add_parser("topics", help="List the topics of a project")
    topics.add_argument("project_id")
    args = parser.parse_args(argv)

    try:
        if args.command == "discover":
            for version in discover(args.server):
                print(f"{version.api_id:<12} {version.version_id:<6} {version.detailed_version or ''}")
            return 0
        if not args.client_id:
            parser.error("--client-id is required for this command")
        token_file = _token_file(args.server)
        with OpenCdeClient(
            args.server,
            client_id=args.client_id,
            client_secret=args.client_secret,
            tokens=_load_tokens(token_file),
            bcf_version=args.bcf_version,
        ) as cde:
            if args.command == "login":
                tokens = cde.login()
                _save_tokens(token_file, tokens)
                print(
                    f"Signed in; the token is valid for {int(tokens.expires_at - time.time())} s. Stored in {token_file}"
                )
                return 0
            if cde.tokens is None:
                print("Not signed in. Run the login command first.", file=sys.stderr)
                return 2
            if args.command == "whoami":
                user = cde.current_user()
                print(f"{user['id']}  {user.get('name', '')}")
            elif args.command == "projects":
                for project in cde.bcf.projects():
                    print(f"{project['project_id']}  {project['name']}")
            elif args.command == "topics":
                for topic in cde.bcf.topics(args.project_id, orderby="creation_date desc", top=50):
                    print(
                        f"{topic.get('server_assigned_id', ''):<12} {topic.get('topic_status', ''):<12} {topic['title']}"
                    )
            if cde.tokens is not None:
                _save_tokens(token_file, cde.tokens)
    except OpenCdeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
