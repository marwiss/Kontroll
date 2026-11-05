# This file was generated with the assistance of an AI coding tool.
"""Admin pages for OAuth2 clients: list, register, edit, rotate secret, revoke tokens, delete."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import Response

from opencde.admin.access import (
    AdminDep,
    AdminForm,
    admin_context,
    flag,
    lines,
    not_found,
    password_confirmed,
    redirect_with_notice,
    text,
)
from opencde.auth.clients import Client, ClientError
from opencde.auth.dependencies import TokensDep
from opencde.deps import ClientsDep, GraphDep, UsersDep
from opencde.ids import is_uuid, normalize_guid
from opencde.ui.templating import render

router = APIRouter(prefix="/admin/clients", include_in_schema=False)

ClientId = Annotated[str, Path(alias="client_id", max_length=64)]


def _client_page(
    request: Request, admin: AdminDep, client: Client, error: str | None = None, status_code: int = 200
) -> Response:
    form = AdminForm(request, admin, "admin-client", client.client_id)
    return render(
        request,
        "admin/client.html",
        admin_context(request, admin, "clients", client=client, form_token=form.token(), error=error),
        status_code=status_code,
    )


def _secret_page(request: Request, admin: AdminDep, client: Client, secret: str, lead: str) -> Response:
    return render(
        request,
        "admin/secret.html",
        admin_context(
            request,
            admin,
            "clients",
            title=f"Client secret for {client.name}",
            lead=lead,
            secret=secret,
            extra_label="Client id",
            extra_value=client.client_id,
            back_url=f"/admin/clients/{client.client_id}",
            back_text="Open the client",
        ),
    )


@router.get("")
async def clients_list(request: Request, admin: AdminDep, clients: ClientsDep) -> Response:
    return render(request, "admin/clients.html", admin_context(request, admin, "clients", clients=await clients.all()))


@router.get("/new")
async def client_new(request: Request, admin: AdminDep) -> Response:
    form = AdminForm(request, admin, "admin-client-new")
    return render(
        request, "admin/client_new.html", admin_context(request, admin, "clients", form_token=form.token(), error=None)
    )


@router.post("")
async def client_create(request: Request, admin: AdminDep, clients: ClientsDep, graph: GraphDep) -> Response:
    form = AdminForm(request, admin, "admin-client-new")
    data = await request.form()
    if not form.check(data.get("form_token")):
        return redirect_with_notice("/admin/clients/new", "form_expired")
    public = text(data, "kind", max_length=16) != "confidential"
    try:
        client, secret = await clients.create(
            text(data, "name", max_length=200),
            lines(data, "redirect_uris", max_items=10, max_length=2000),
            public=public,
            description=text(data, "description", max_length=1000) or None,
            url=text(data, "url", max_length=2000) or None,
            created_by=admin.user.id,
        )
    except ClientError as exc:
        return render(
            request,
            "admin/client_new.html",
            admin_context(request, admin, "clients", form_token=form.token(), error=str(exc)),
            status_code=400,
        )
    await form.record(graph, "client.create", client_id=client.client_id, public=public)
    if secret:
        return _secret_page(
            request, admin, client, secret, "Store the secret in the application's configuration now; it is shown once."
        )
    return redirect_with_notice(f"/admin/clients/{client.client_id}", "created")


@router.get("/{client_id}")
async def client_page(request: Request, admin: AdminDep, client_id: ClientId, clients: ClientsDep) -> Response:
    client = await clients.get(normalize_guid(client_id)) if is_uuid(client_id) else None
    if client is None:
        raise not_found()
    return _client_page(request, admin, client)


@router.post("/{client_id}")
async def client_action(
    request: Request,
    admin: AdminDep,
    client_id: ClientId,
    clients: ClientsDep,
    users: UsersDep,
    tokens: TokensDep,
    graph: GraphDep,
) -> Response:
    client = await clients.get(normalize_guid(client_id)) if is_uuid(client_id) else None
    if client is None:
        raise not_found()
    form = AdminForm(request, admin, "admin-client", client.client_id)
    data = await request.form()
    page = f"/admin/clients/{client.client_id}"
    if not form.check(data.get("form_token")):
        return redirect_with_notice(page, "form_expired")
    action = text(data, "action", max_length=32)

    try:
        if action == "update":
            disabled = flag(data, "disabled")
            await clients.update(
                client.client_id,
                name=text(data, "name", max_length=200) or None,
                description=text(data, "description", max_length=1000),
                url=text(data, "url", max_length=2000),
                redirect_uris=lines(data, "redirect_uris", max_items=10, max_length=2000),
                disabled=disabled,
            )
            if disabled and not client.disabled:
                await tokens.revoke_all_for_client(client.client_id)
            await form.record(graph, "client.update", client_id=client.client_id, disabled=disabled)
            return redirect_with_notice(page, "saved")

        if action == "rotate":
            if not await password_confirmed(users, admin, data.get("confirm_password")):
                return redirect_with_notice(page, "wrong_password")
            secret = await clients.rotate_secret(client.client_id)
            await form.record(graph, "client.rotate_secret", client_id=client.client_id)
            return _secret_page(
                request, admin, client, secret, "The old secret stopped working. Update the application now."
            )

        if action == "revoke":
            await tokens.revoke_all_for_client(client.client_id)
            await form.record(graph, "client.revoke_tokens", client_id=client.client_id)
            return redirect_with_notice(page, "revoked")

        if action == "delete":
            if not await password_confirmed(users, admin, data.get("confirm_password")):
                return redirect_with_notice(page, "wrong_password")
            await clients.delete(client.client_id)
            await form.record(graph, "client.delete", client_id=client.client_id, name=client.name)
            return redirect_with_notice("/admin/clients", "deleted")
    except ClientError as exc:
        return _client_page(request, admin, client, error=str(exc), status_code=400)

    return redirect_with_notice(page, "invalid")
