# This file was generated with the assistance of an AI coding tool.
"""The ``opencde`` command line: run, inspect and administer the server.

Stage 0 ships ``serve``, ``version`` and a first ``doctor``. Later stages add
``init`` (interactive setup), ``seed`` (demo data) and the user, project,
client, backup and revoke commands.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from opencde import __version__

app = typer.Typer(no_args_is_help=True, help="Kontroll OpenCDE server.", rich_markup_mode="markdown")


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

    from opencde.settings import Settings

    settings = Settings()  # fail fast on bad configuration, before the socket opens
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
def doctor() -> None:
    """Check configuration and the graph database connection."""
    from pydantic import ValidationError

    from opencde.graph.driver import create_driver, ping_within
    from opencde.settings import Settings

    try:
        settings = Settings()
    except ValidationError as exc:
        for error in exc.errors():
            print(f"CONFIG  {error['msg']}")
        raise typer.Exit(code=1) from None

    print(f"OK      version {__version__}")
    print(f"OK      environment {settings.environment}")
    print(f"OK      public_url {settings.public_url}")
    print(f"OK      graph {settings.graph_dialect.value} {settings.graph_uri} database={settings.database_name}")

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


if __name__ == "__main__":
    app()
