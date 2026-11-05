# This file was generated with the assistance of an AI coding tool.
"""The ``opencde`` command line: run, inspect and administer the server.

opencde init [--dev]            write .env with fresh secrets
opencde serve                   start the HTTP server
opencde doctor                  check configuration and the database
opencde seed                    load demonstration data into an empty database
opencde user ...                create, list, disable users; set passwords; grant project roles
opencde project ...             create and list projects, manage members and extensions
opencde client ...              register OAuth2 clients, rotate secrets
opencde cleanup                 delete expired codes, tokens and sessions now
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer

from opencde import __version__

app = typer.Typer(no_args_is_help=True, help="Kontroll OpenCDE server.", rich_markup_mode="markdown")
user_app = typer.Typer(no_args_is_help=True, help="Manage users and their project roles.")
project_app = typer.Typer(no_args_is_help=True, help="Manage projects, members and BCF extensions.")
client_app = typer.Typer(no_args_is_help=True, help="Manage OAuth2 clients.")
app.add_typer(user_app, name="user")
app.add_typer(project_app, name="project")
app.add_typer(client_app, name="client")

T = TypeVar("T")


def _settings():
    from pydantic import ValidationError

    from opencde.settings import Settings

    try:
        return Settings()
    except ValidationError as exc:
        for error in exc.errors():
            typer.secho(f"CONFIG  {error['msg']}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from None


def _run(work: Callable[..., Awaitable[T]]) -> T:
    """Run ``work(graph, settings)`` against the configured database."""
    from opencde.bootstrap import GraphUnavailable, graph_session

    settings = _settings()

    async def main() -> T:
        async with graph_session(settings) as graph:
            return await work(graph, settings)

    try:
        return asyncio.run(main())
    except GraphUnavailable as exc:
        typer.secho(f"FAIL    {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


def _fail(message: str) -> typer.Exit:
    typer.secho(f"ERROR   {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


# --------------------------------------------------------------------------- server


@app.command()
def version() -> None:
    """Print the server version."""
    print(__version__)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Interface to bind. Use 0.0.0.0 inside a container.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="TCP port.")] = 8000,
    reload: Annotated[bool, typer.Option(help="Restart on code changes (development only).")] = False,
) -> None:
    """Start the HTTP server with uvicorn."""
    import uvicorn

    settings = _settings()  # fail fast on bad configuration, before the socket opens
    uvicorn.run(
        "opencde.asgi:app",
        host=host,
        port=port,
        reload=reload,
        proxy_headers=True,
        forwarded_allow_ips=",".join(settings.trusted_proxies),
        server_header=False,
        log_config=None,
    )


@app.command()
def init(
    dev: Annotated[bool, typer.Option("--dev", help="Local development on http://localhost:8000.")] = False,
    public_url: Annotated[str | None, typer.Option(help="Public https URL of the server (production).")] = None,
    force: Annotated[bool, typer.Option(help="Overwrite an existing .env.")] = False,
    path: Annotated[Path, typer.Option(help="Where to write the file.")] = Path(".env"),
) -> None:
    """Write a .env file with fresh secrets for development or production."""
    if path.exists() and not force:
        raise _fail(f"{path} exists; use --force to overwrite")
    if not dev and not public_url:
        raise _fail("give --public-url https://... for production, or --dev for local development")
    url = "http://localhost:8000" if dev else (public_url or "").rstrip("/")
    if not dev and not url.startswith("https://"):
        raise _fail("the public URL must start with https:// in production")
    lines = [
        "# Written by `opencde init`. Keep this file private; it is git-ignored.",
        f"OPENCDE_ENVIRONMENT={'development' if dev else 'production'}",
        f"OPENCDE_PUBLIC_URL={url}",
        f"OPENCDE_SECRET_KEY={secrets.token_urlsafe(48)}",
        "OPENCDE_GRAPH_DIALECT=neo4j",
        # 127.0.0.1 rather than localhost: Windows resolves localhost to ::1 first, where Docker does not listen.
        "OPENCDE_GRAPH_URI=bolt://127.0.0.1:7697" if dev else "OPENCDE_GRAPH_URI=bolt://graph:7687",
        "OPENCDE_GRAPH_USER=neo4j",
        f"OPENCDE_GRAPH_PASSWORD={secrets.token_urlsafe(24)}",
        "OPENCDE_LOG_LEVEL=DEBUG" if dev else "OPENCDE_LOG_LEVEL=INFO",
        "OPENCDE_LOG_JSON=false" if dev else "OPENCDE_LOG_JSON=true",
        'OPENCDE_CORS_ORIGINS=["*"]',
        'OPENCDE_TRUSTED_PROXIES=["127.0.0.1"]' if dev else 'OPENCDE_TRUSTED_PROXIES=["127.0.0.1", "172.16.0.0/12"]',
        "OPENCDE_ALLOW_LOCALHOST_REDIRECTS=true" if dev else "OPENCDE_ALLOW_LOCALHOST_REDIRECTS=false",
        "OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true" if dev else "OPENCDE_DYNAMIC_CLIENT_REGISTRATION=false",
        "NEO4J_HEAP=512m",
        "NEO4J_PAGECACHE=256m",
        "OPENCDE_DEV_PORT=8000",
        "OPENCDE_DEV_NEO4J_HTTP_PORT=7484",
        "OPENCDE_DEV_NEO4J_BOLT_PORT=7697",
    ]
    if not dev:
        lines.append(f"OPENCDE_DOMAIN={url.removeprefix('https://')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.secho(f"OK      wrote {path}", fg=typer.colors.GREEN)
    typer.echo(
        "        next: docker compose -f compose.yaml -f compose.dev.yaml up -d --build"
        if dev
        else "        next: see docs/deploy/vps-caddy.md"
    )


@app.command()
def doctor() -> None:
    """Check configuration and the graph database connection."""
    from opencde.graph.driver import create_driver, ping_within

    settings = _settings()
    print(f"OK      version {__version__}")
    print(f"OK      environment {settings.environment}")
    print(f"OK      public_url {settings.public_url}")
    print(f"OK      graph {settings.graph_dialect.value} {settings.graph_uri} database={settings.database_name}")
    print(f"OK      data_dir {settings.data_dir.resolve()}")

    async def check_graph() -> bool:
        driver = create_driver(settings)
        try:
            return await ping_within(driver, settings.database_name, settings.graph_connect_timeout_seconds)
        finally:
            await driver.close()

    if asyncio.run(check_graph()):
        print("OK      graph database answers")
    else:
        print("FAIL    graph database does not answer (check OPENCDE_GRAPH_URI, user and password)")
        raise typer.Exit(code=1)


@app.command()
def cleanup() -> None:
    """Delete expired codes, tokens and sessions now (the server also does this on a timer)."""
    from opencde.graph.cleanup import delete_expired

    async def work(graph, _settings):
        return await delete_expired(graph)

    print(f"OK      deleted {_run(work)} expired nodes")


@app.command()
def backup(
    target: Annotated[Path, typer.Argument(help="Directory that receives a new, timestamped backup folder.")],
) -> None:
    """Export the whole graph and all stored files to a folder (restorable into Neo4j or Memgraph)."""
    from opencde import backup as backups
    from opencde.bootstrap import make_storage
    from opencde.timeutil import now

    folder = target / ("opencde-backup-" + now().strftime("%Y%m%dT%H%M%SZ"))

    async def work(graph, settings):
        return await backups.export(graph, make_storage(settings), folder)

    manifest = _run(work)
    print(f"OK      {folder}")
    print(f"        {manifest.nodes} nodes, {manifest.relationships} relationships, {manifest.files} files")
    if manifest.skipped_nodes:
        print(f"WARN    {manifest.skipped_nodes} nodes without a unique key were not exported")


@app.command()
def restore(
    source: Annotated[Path, typer.Argument(help="A backup folder written by `opencde backup`.")],
    force: Annotated[bool, typer.Option("--force", help="Wipe the database and storage first.")] = False,
) -> None:
    """Load a backup. Refuses to touch a database that is not empty unless --force is given."""
    from opencde import backup as backups
    from opencde.bootstrap import make_storage
    from opencde.seed import is_empty, wipe

    try:
        manifest = backups.read_manifest(source)
    except backups.BackupError as exc:
        raise _fail(str(exc)) from None

    async def work(graph, settings):
        if not await is_empty(graph):
            if not force:
                raise backups.BackupError("the database is not empty; use --force to replace its contents")
            await wipe(graph)
        return await backups.restore(graph, make_storage(settings), source)

    try:
        _run(work)
    except backups.BackupError as exc:
        raise _fail(str(exc)) from None
    print(f"OK      restored backup from {manifest.created_at} ({manifest.dialect}, server {manifest.server_version})")
    print(f"        {manifest.nodes} nodes, {manifest.relationships} relationships, {manifest.files} files")


@app.command()
def revoke(
    username: Annotated[str | None, typer.Option("--user", help="Revoke every token and session of this user.")] = None,
    client_id: Annotated[str | None, typer.Option("--client", help="Revoke every token issued to this client.")] = None,
    everything: Annotated[bool, typer.Option("--all", help="Revoke every token and session on the server.")] = False,
) -> None:
    """Revoke access: after a leaked laptop, a compromised client, or as the first step of an incident response."""
    from opencde.accounts.users import UserRepository
    from opencde.auth.dependencies import token_repository

    if sum(bool(x) for x in (username, client_id, everything)) != 1:
        raise _fail("give exactly one of --user, --client or --all")

    async def work(graph, settings):
        tokens = token_repository(graph, settings)
        if everything:
            counters = await graph.write(
                lambda tx: tx.counters(
                    "MATCH (t) WHERE t:AccessToken OR t:RefreshToken OR t:AuthorizationCode OR t:WebSession DETACH DELETE t"
                )
            )
            return counters.nodes_deleted
        if username:
            user = await UserRepository(graph).get_by_username(username)
            if user is None:
                raise typer.BadParameter(f"no user named {username}")
            return await tokens.revoke_all_for_user(user.id)
        return await tokens.revoke_all_for_client(client_id or "")

    deleted = _run(work)
    print(f"OK      revoked {deleted} tokens and sessions")


@app.command()
def seed(
    password: Annotated[
        str | None, typer.Option(help="Use this password for every demo user instead of random ones.")
    ] = None,
    reset: Annotated[bool, typer.Option(help="DELETE EVERYTHING in the database first. Development only.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm --reset without a prompt.")] = False,
) -> None:
    """Load demonstration users, projects and clients into an empty database."""
    from opencde import seed as seeding

    async def work(graph, settings):
        if reset:
            if settings.is_production:
                raise _fail("--reset is not available in production")
            if not yes and not typer.confirm("This deletes ALL data in the database. Continue?"):
                raise typer.Exit(code=1)
            await seeding.wipe(graph)
        try:
            return await seeding.seed(
                graph,
                shared_password=password,
                public_redirects=["http://127.0.0.1/callback", "http://localhost:8080/callback"]
                if settings.allow_localhost_redirects
                else None,
                allow_localhost_redirects=settings.allow_localhost_redirects,
            )
        except seeding.SeedError as exc:
            raise _fail(str(exc)) from None

    result = _run(work)
    typer.secho("Demonstration data loaded. Passwords are shown once; store them now.", fg=typer.colors.GREEN)
    for username, pw in result.passwords.items():
        print(f"  user      {username:20} password {pw}")
    for name, project_id in result.projects.items():
        print(f"  project   {name:20} {project_id}")
    print(f"  client    public               {result.public_client_id}")
    print(
        f"  client    confidential         {result.confidential_client_id}  secret {result.confidential_client_secret}"
    )


# --------------------------------------------------------------------------- users


@user_app.command("create")
def user_create(
    username: str,
    password: Annotated[str | None, typer.Option(help="Omit to generate one.")] = None,
    email: Annotated[str | None, typer.Option()] = None,
    full_name: Annotated[str | None, typer.Option()] = None,
    admin: Annotated[bool, typer.Option("--admin", help="Server administrator (admin UI, all management).")] = False,
) -> None:
    """Create a user."""
    from opencde.accounts.users import AccountError, UserRepository

    generated = password is None
    pw = password or secrets.token_urlsafe(12)

    async def work(graph, _settings):
        try:
            return await UserRepository(graph).create(username, pw, email=email, full_name=full_name, is_admin=admin)
        except AccountError as exc:
            raise _fail(str(exc)) from None

    user = _run(work)
    print(f"OK      user {user.username} ({user.id}){' admin' if user.is_admin else ''}")
    if generated:
        print(f"        password {pw}  (shown once)")


@user_app.command("list")
def user_list() -> None:
    """List users with their project roles."""
    from opencde.accounts.users import UserRepository

    async def work(graph, _settings):
        repo = UserRepository(graph)
        users = await repo.search()
        return [(u, await repo.memberships(u.id)) for u in users]

    for user, memberships in _run(work):
        flags = " admin" if user.is_admin else ""
        flags += " disabled" if user.disabled else ""
        roles = ", ".join(f"{name} ({role.value})" for _, name, role in memberships) or "-"
        print(f"{user.username:24} {user.full_name or '':30}{flags:10} {roles}")


@user_app.command("set-password")
def user_set_password(
    username: str, password: Annotated[str | None, typer.Option(help="Omit to generate one.")] = None
) -> None:
    """Set a user's password (shown once when generated)."""
    from opencde.accounts.users import AccountError, UserRepository

    pw = password or secrets.token_urlsafe(12)

    async def work(graph, _settings):
        repo = UserRepository(graph)
        user = await repo.get_by_username(username)
        if user is None:
            raise _fail("no such user")
        try:
            await repo.set_password(user.id, pw, must_change=password is None)
        except AccountError as exc:
            raise _fail(str(exc)) from None

    _run(work)
    print(f"OK      password set for {username}" + (f"  password {pw}  (shown once)" if password is None else ""))


@user_app.command("disable")
def user_disable(
    username: str, enable: Annotated[bool, typer.Option("--enable", help="Re-enable instead.")] = False
) -> None:
    """Disable (or re-enable) a user. Disabled users cannot sign in and their tokens stop working."""
    from opencde.accounts.users import AccountError, UserRepository

    async def work(graph, _settings):
        repo = UserRepository(graph)
        user = await repo.get_by_username(username)
        if user is None:
            raise _fail("no such user")
        try:
            await repo.update(user.id, disabled=not enable)
        except AccountError as exc:
            raise _fail(str(exc)) from None

    _run(work)
    print(f"OK      {username} {'enabled' if enable else 'disabled'}")


@user_app.command("grant")
def user_grant(username: str, project_id: str, role: str) -> None:
    """Give a user a role (viewer, contributor, editor, manager) in a project."""
    from opencde.accounts.projects import ProjectRepository
    from opencde.accounts.roles import Role
    from opencde.accounts.users import AccountError, UserRepository

    try:
        wanted = Role(role)
    except ValueError:
        raise _fail("role must be one of viewer, contributor, editor, manager") from None

    async def work(graph, _settings):
        user = await UserRepository(graph).get_by_username(username)
        if user is None:
            raise _fail("no such user")
        try:
            await ProjectRepository(graph).set_member(project_id, user.id, wanted)
        except AccountError as exc:
            raise _fail(str(exc)) from None

    _run(work)
    print(f"OK      {username} is {wanted.value} in {project_id}")


# --------------------------------------------------------------------------- projects


@project_app.command("create")
def project_create(name: str) -> None:
    """Create a project with default BCF extensions."""
    from opencde.accounts.projects import AccountError, ProjectRepository

    async def work(graph, _settings):
        try:
            return await ProjectRepository(graph).create(name)
        except AccountError as exc:
            raise _fail(str(exc)) from None

    project = _run(work)
    print(f"OK      project {project.name} {project.project_id}")


@project_app.command("list")
def project_list() -> None:
    """List projects and their members."""
    from opencde.accounts.projects import ProjectRepository

    async def work(graph, _settings):
        repo = ProjectRepository(graph)
        return [(p, await repo.members(p.project_id)) for p in await repo.all()]

    for project, members in _run(work):
        print(f"{project.project_id}  {project.name}")
        for user, role in members:
            print(f"    {role.value:12} {user.username}")


# --------------------------------------------------------------------------- clients


@client_app.command("create")
def client_create(
    name: str,
    redirect_uri: Annotated[list[str], typer.Option("--redirect-uri", help="Registered redirect URI (repeatable).")],
    public: Annotated[
        bool, typer.Option("--public", help="Public client (native or browser app): PKCE, no secret.")
    ] = False,
    description: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Register an OAuth2 client. A confidential client's secret is shown once."""
    from opencde.auth.clients import ClientError, ClientRepository

    async def work(graph, settings):
        repo = ClientRepository(graph, allow_localhost_redirects=settings.allow_localhost_redirects)
        try:
            return await repo.create(name, redirect_uri, public=public, description=description)
        except ClientError as exc:
            raise _fail(str(exc)) from None

    client, secret = _run(work)
    print(
        f"OK      client {client.name}  client_id {client.client_id}  {'public' if client.is_public else 'confidential'}"
    )
    if secret:
        print(f"        client_secret {secret}  (shown once)")


@client_app.command("list")
def client_list() -> None:
    """List OAuth2 clients."""
    from opencde.auth.clients import ClientRepository

    async def work(graph, settings):
        return await ClientRepository(graph, allow_localhost_redirects=settings.allow_localhost_redirects).all()

    for client in _run(work):
        kind = "public" if client.is_public else "confidential"
        flags = " disabled" if client.disabled else ""
        print(f"{client.client_id}  {kind:12}{flags:9} {client.name}  {', '.join(client.redirect_uris)}")


@client_app.command("rotate-secret")
def client_rotate_secret(client_id: str) -> None:
    """Replace a confidential client's secret. The old secret stops working at once."""
    from opencde.auth.clients import ClientError, ClientRepository

    async def work(graph, settings):
        try:
            return await ClientRepository(
                graph, allow_localhost_redirects=settings.allow_localhost_redirects
            ).rotate_secret(client_id)
        except ClientError as exc:
            raise _fail(str(exc)) from None

    print(f"OK      new client_secret {_run(work)}  (shown once)")


if __name__ == "__main__":
    app()
