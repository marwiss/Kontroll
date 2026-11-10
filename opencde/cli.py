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
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, TypeVar
from urllib.parse import urlsplit

import typer

from opencde import __version__

app = typer.Typer(no_args_is_help=True, help="Dataregium OpenCDE server.", rich_markup_mode="markdown")
user_app = typer.Typer(no_args_is_help=True, help="Manage users and their project roles.")
project_app = typer.Typer(no_args_is_help=True, help="Manage projects, members and BCF extensions.")
client_app = typer.Typer(no_args_is_help=True, help="Manage OAuth2 clients.")
ifcgraph_app = typer.Typer(no_args_is_help=True, help="Inspect and prune the imported IFC models.")
app.add_typer(user_app, name="user")
app.add_typer(project_app, name="project")
app.add_typer(client_app, name="client")
app.add_typer(ifcgraph_app, name="ifc-lpg")
app.add_typer(ifcgraph_app, name="ifcgraph", hidden=True)  # its old name, so that scripts keep working

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


def _interactive() -> bool:
    return sys.stdin.isatty()


def _ask_for_values() -> tuple[str | None, list[str]]:
    """The public address, or None for this machine only, and the lines for .env that the answers add."""
    if not typer.confirm("Will other people use this server, over the internet?", default=False):
        if typer.confirm(
            "Turn on what the quick start with Dataspatium uses (self-registration, request log, IFC-LPG)?",
            default=True,
        ):
            return None, [
                "OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true",
                "OPENCDE_REQUEST_LOG_ENABLED=true",
                "OPENCDE_IFC_LPG_ENABLED=true",
            ]
        return None, []
    while True:
        url = typer.prompt("The server's public address, for example https://cde.example.org").strip().rstrip("/")
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.hostname and not parts.path:
            break
        typer.echo("        It has to be https:// and a host name, with no path after it.")
    extra = []
    email = typer.prompt(
        "An e-mail address for messages about the certificate (optional)", default="", show_default=False
    )
    if email.strip():
        extra.append(f"OPENCDE_ACME_EMAIL={email.strip()}")
    if typer.confirm(
        "Let applications register themselves? Most servers register them in the administration", default=False
    ):
        extra.append("OPENCDE_DYNAMIC_CLIENT_REGISTRATION=true")
    if typer.confirm("Turn uploaded IFC models into a graph?", default=False):
        extra.append("OPENCDE_IFC_LPG_ENABLED=true")
    return url, extra


def _say_what_comes_next(url: str, *, dev: bool) -> None:
    if dev:
        compose = "docker compose -f compose.yaml -f compose.dev.yaml"
        steps = [
            f"{compose} up -d --build --wait",
            f"{compose} exec api opencde seed",
            f"Then open {url}/ and follow docs/en/quickstart.md.",
        ]
    else:
        compose = "docker compose -f compose.yaml -f compose.prod.yaml"
        steps = [
            f"Check that {url.removeprefix('https://')} points at this machine and that ports 80 and 443 are open.",
            f"{compose} pull",
            f"{compose} up -d",
            f"{compose} exec api opencde doctor",
            f"{compose} exec api opencde user create admin --admin",
            f'{compose} exec api opencde client create "Your application" --public --redirect-uri https://app.example.org/callback',
            f"Then sign in at {url}/signin and see docs/en/deploy/vps-caddy.md.",
        ]
    typer.echo("        next:")
    for step in steps:
        typer.echo(f"          {step}")


@app.command()
def init(
    dev: Annotated[bool, typer.Option("--dev", help="Local development on http://127.0.0.1:8000.")] = False,
    public_url: Annotated[str | None, typer.Option(help="Public https URL of the server (production).")] = None,
    force: Annotated[bool, typer.Option(help="Overwrite an existing .env.")] = False,
    path: Annotated[Path, typer.Option(help="Where to write the file.")] = Path(".env"),
) -> None:
    """Write a .env file with fresh secrets. Without --dev or --public-url it asks, then says what comes next."""
    if path.exists() and not force:
        raise _fail(f"{path} exists; use --force to overwrite")
    extra: list[str] = []
    guided = not dev and not public_url
    if guided:
        if not _interactive():
            raise _fail("give --public-url https://... for production, or --dev for local development")
        public_url, extra = _ask_for_values()
        dev = public_url is None
    url = "http://127.0.0.1:8000" if dev else (public_url or "").rstrip("/")
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
    # A value asked for replaces the line that says otherwise.
    names = {line.split("=", 1)[0] for line in extra}
    lines = [line for line in lines if line.split("=", 1)[0] not in names] + extra
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.secho(f"OK      wrote {path}", fg=typer.colors.GREEN)
    if guided:
        _say_what_comes_next(url, dev=dev)
        return
    typer.echo(
        "        next: docker compose -f compose.yaml -f compose.dev.yaml up -d --build"
        if dev
        else "        next: see docs/en/deploy/vps-caddy.md"
    )


@app.command()
def doctor() -> None:
    """Check the configuration, the database and its schema, the storage, the clock and the server's headers."""
    from opencde.admin.doctor import run_checks
    from opencde.bootstrap import make_graph, make_storage

    settings = _settings()

    async def work():
        graph = make_graph(settings)
        try:
            return await run_checks(settings, graph, make_storage(settings))
        finally:
            await graph.close()

    checks = asyncio.run(work())
    for check in checks:
        print(f"{'OK' if check.ok else 'FAIL':7} {check.name}: {check.detail}")
    if not all(check.ok for check in checks):
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
    """Load demonstration users, projects, clients, the sample model and a topic into an empty database."""
    from opencde import seed as seeding
    from opencde.storage import LocalStorage

    async def work(graph, settings):
        if reset:
            if settings.is_production:
                raise _fail("--reset is not available in production")
            if not yes and not typer.confirm("This deletes ALL data in the database. Continue?"):
                raise typer.Exit(code=1)
            await seeding.wipe(graph)
        storage = LocalStorage(settings.data_dir)
        try:
            loaded = await seeding.seed(
                graph,
                storage=storage,
                shared_password=password,
                public_redirects=["http://127.0.0.1/callback", "http://127.0.0.1:8080/callback"]
                if settings.allow_localhost_redirects
                else None,
                allow_localhost_redirects=settings.allow_localhost_redirects,
                id_prefix=settings.server_assigned_id_prefix,
                max_image_bytes=settings.max_image_bytes,
            )
        except seeding.SeedError as exc:
            raise _fail(str(exc)) from None
        model = (
            await seeding.build_sample_graph(graph, storage, settings, loaded) if settings.ifcgraph_enabled else None
        )
        return loaded, model

    result, model = _run(work)
    typer.secho("Demonstration data loaded. Passwords are shown once; store them now.", fg=typer.colors.GREEN)
    for username, pw in result.passwords.items():
        print(f"  user      {username:20} password {pw}")
    for name, project_id in result.projects.items():
        print(f"  project   {name:20} {project_id}")
    print(f"  client    public               {result.public_client_id}")
    print(
        f"  client    confidential         {result.confidential_client_id}  secret {result.confidential_client_secret}"
    )
    print(f"  document  {seeding.SAMPLE_MODEL_FILE_NAME:20} {result.document_id}  (Building permit, version 1)")
    print(f"  topic     {'ISSUE-0001':20} {result.topic_guid}  viewpoint {result.viewpoint_guid}")
    print(f"  comment   {'':20} {result.comment_guid}")
    if model is not None:
        ending = f"{model.get('entities')} entities" if model["state"] == "done" else f"not built: {model.get('error')}"
        print(f"  graph     {seeding.SAMPLE_MODEL_FILE_NAME:20} {ending}")


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
    without_pkce: Annotated[
        bool,
        typer.Option("--without-pkce", help="Confidential client that cannot use PKCE, such as BCF API 2.1 clients."),
    ] = False,
) -> None:
    """Register an OAuth2 client. A confidential client's secret is shown once."""
    from opencde.auth.clients import ClientError, ClientRepository

    async def work(graph, settings):
        repo = ClientRepository(graph, allow_localhost_redirects=settings.allow_localhost_redirects)
        try:
            return await repo.create(
                name, redirect_uri, public=public, description=description, pkce_optional=without_pkce
            )
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
        software = f"  [{client.software_id} {client.software_version or ''}]".rstrip() if client.software_id else ""
        print(f"{client.client_id}  {kind:12}{flags:9} {client.name}  {', '.join(client.redirect_uris)}{software}")


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


@client_app.command("approve")
def client_approve(client_id: str) -> None:
    """Approve a self-registered client that waits for an administrator."""
    from opencde.auth.clients import ClientError, ClientRepository

    async def work(graph, settings):
        repo = ClientRepository(graph, allow_localhost_redirects=settings.allow_localhost_redirects)
        try:
            await repo.update(client_id, disabled=False)
        except ClientError as exc:
            raise _fail(str(exc)) from None

    _run(work)
    print(f"OK      approved {client_id}")


@client_app.command("prune")
def client_prune(
    all_dynamic: Annotated[
        bool, typer.Option("--all-dynamic", help="Delete every self-registered client, not only the expired ones.")
    ] = False,
) -> None:
    """Delete self-registered clients unused for OPENCDE_DYNAMIC_CLIENT_UNUSED_DAYS, with their tokens.
    The server does this on its own timer as well; this command does it now."""
    from opencde.auth.clients import ClientRepository

    async def work(graph, settings):
        repo = ClientRepository(graph, allow_localhost_redirects=settings.allow_localhost_redirects)
        return await repo.prune_dynamic(all_dynamic=all_dynamic)

    print(f"OK      deleted {_run(work)} self-registered client(s)")


# --------------------------------------------------------------------------- IFC-graph


@ifcgraph_app.command("list")
def ifcgraph_list(project_id: Annotated[str | None, typer.Option("--project")] = None) -> None:
    """List imported models with their state."""
    from opencde.ifcgraph.maintenance import list_models

    for model in _run(lambda graph, _settings: list_models(graph, project_id=project_id)):
        document = model.get("document_id") or model.get("bcf_document_guid") or "-"
        version = model.get("version_index")
        moment = model.get("done_at") or model.get("failed_at") or model.get("created_at") or ""
        print(
            f"{model['id']}  {model['state']:8} {model.get('file_name', ''):32} project {model['project_id']}  "
            f"document {document}{f' v{version}' if version is not None else ''}  {moment}"
        )


@ifcgraph_app.command("prune")
def ifcgraph_prune(
    project_id: Annotated[str | None, typer.Option("--project")] = None,
    everything: Annotated[
        bool, typer.Option("--all", help="Delete every model of the project (needs --project).")
    ] = False,
) -> None:
    """Delete failed models and finished models superseded by a newer version of the same document.
    Queued and running models and the documents themselves stay."""
    from opencde.ifcgraph.maintenance import prune_models

    if everything and not project_id:
        raise _fail("--all needs --project")
    result = _run(lambda graph, _settings: prune_models(graph, project_id=project_id, everything=everything))
    print(f"OK      deleted {result['models']} model(s) and {result['entities']} entities")


@ifcgraph_app.command("export")
def ifcgraph_export(
    model_id: str,
    target: Annotated[Path, typer.Argument(help="The file to write.")],
    validate: Annotated[
        bool, typer.Option("--validate/--no-validate", help="Check the file against the IFC standard.")
    ] = True,
    verify: Annotated[bool, typer.Option("--verify", help="Compare the file with the one that was uploaded.")] = False,
    geometry: Annotated[
        bool, typer.Option("--geometry", help="With --verify, also build and compare the meshes.")
    ] = False,
) -> None:
    """Write a model back as an IFC file from what the graph holds, and validate it. Only a model converted with
    OPENCDE_IFC_LPG_LOSSLESS can be."""
    from ifc_lpg.exporter import NotExportable

    from opencde.bootstrap import make_storage
    from opencde.ifcgraph.service import IfcGraphService

    async def work(graph, settings):
        service = IfcGraphService(graph, make_storage(settings), settings)
        instances = await service.export(model_id, target)
        found = await service.validate_against_upload(model_id, target) if validate else None
        answer = await service.compare_with_upload(model_id, target, geometry=geometry) if verify else None
        return instances, found, answer

    try:
        instances, found, answer = _run(work)
    except typer.Exit:
        raise
    except (NotExportable, RuntimeError, ValueError, OSError) as exc:
        raise _fail(str(exc)[:500]) from exc
    print(f"OK      wrote {target}: {instances} instances")
    if answer is not None:
        for check in answer["checks"]:
            word = {True: "OK", False: "DIFFERS", None: "UNKNOWN"}[check["passed"]]
            print(f"{word:7} {check['name']}{': ' + check['detail'] if check['detail'] else ''}")
    if found is not None:
        word = "INVALID" if found["new_count"] else "OK"
        print(f"{word:7} validation: {found['new_count']} issues the upload does not have, {found['issues']} in all")
        for issue in found["new"]:
            at = f"#{issue['instance']} " if issue["instance"] is not None else ""
            print(f"        {at}{' '.join(issue['message'].split())[:400]}")  # the rule can come many lines in
    if answer is not None and not answer["same_model"]:
        raise _fail("the file does not hold the same model as the upload")
    if found is not None and found["new_count"]:
        raise _fail("the file breaks the IFC standard in ways the upload does not")


if __name__ == "__main__":
    app()
