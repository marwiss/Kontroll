# This file was generated with the assistance of an AI coding tool.
"""Links from the server's pages into a Dataspatium installation.

An extension outside the specifications, agreed with Dataspatium: when the operator sets
``OPENCDE_DATASPATIUM_URL``, project and document pages offer "Open in
Dataspatium". The app's route is ``#/inhamta/opencde`` with the server's
public URL and, optionally, the project, the document and the version
index; older app releases open the source and ignore the rest.
"""

from __future__ import annotations

from urllib.parse import urlencode

from opencde.settings import Settings


def dataspatium_link(
    settings: Settings,
    *,
    project_id: str | None = None,
    document_id: str | None = None,
    version_index: int | None = None,
) -> str | None:
    """The deep link, or ``None`` when no Dataspatium installation is configured."""
    if not settings.dataspatium_url:
        return None
    query: dict[str, str] = {"server": settings.public_url}
    if project_id:
        query["project"] = project_id
    if document_id:
        query["document"] = document_id
        if version_index is not None:
            query["version"] = str(version_index)
    return f"{settings.dataspatium_url.rstrip('/')}/#/inhamta/opencde?{urlencode(query)}"
