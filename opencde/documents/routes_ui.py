# This file was generated with the assistance of an AI coding tool.
"""The browser side of the Documents API: metadata entry, document selection, details.

The client opens ``upload_ui_url`` or ``select_documents_url`` in the user's
browser. The URL carries an unguessable, short-lived token; the page also
requires the browser to be signed in as the user who started the flow, so a
leaked link alone is not enough. When the user finishes or cancels, the
browser is redirected to the client's callback with the query parameters the
specification names.
"""

from __future__ import annotations

from typing import Annotated, Any

import anyio
from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import RedirectResponse, Response

from opencde.accounts.roles import project_actions
from opencde.auth.forms import FormTokenError
from opencde.bcf.binary import file_response, sanitize_filename
from opencde.deps import ProjectsDep, SettingsDep, StorageDep, UsersDep
from opencde.documents.assembly import store_stream
from opencde.documents.links import api_base, with_query
from opencde.documents.repository import DocumentsDep, VersionRecord, default_metadata
from opencde.documents.sessions import (
    STATE_CANCELLED,
    STATE_METADATA,
    STATE_NEW,
    STATE_SELECTED,
    SelectionSession,
    SelectionSessionsDep,
    UploadSession,
    UploadSessionsDep,
)
from opencde.errors import CODE_UPLOAD_TOO_LARGE, ApiError
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.ifcgraph.service import IfcGraphDep
from opencde.storage import TooLargeError, make_key
from opencde.timeutil import now_iso
from opencde.ui.links import dataspatium_link
from opencde.ui.templating import render
from opencde.web.dependencies import (
    NO_STORE,
    WebUserDep,
    form_tokens,
    page_context,
    require_same_origin,
    signin_redirect,
)
from opencde.web.sessions import WebUser

router = APIRouter(prefix="/documents/1.0", include_in_schema=False)

Token = Annotated[str, Path(alias="token", max_length=128)]
DocumentId = Annotated[str, Path(alias="document_id", max_length=64)]
VersionIndex = Annotated[int, Path(alias="version_index", ge=1, le=1_000_000_000)]

UPLOAD_PURPOSE = "documents-upload"
SELECT_PURPOSE = "documents-select"
BROWSER_UPLOAD_PURPOSE = "documents-browser-upload"
MAX_TITLE = 200
MAX_VERSION_NUMBER = 50

# Browser uploads from the selection page are multipart bodies, streamed by the form parser.
BROWSER_UPLOAD_PATHS = (r"^/documents/1\.0/select-ui/[^/]+/upload$",)
# The HTML pages of this module, which share the API's prefix but are never shared cross-origin (no CORS).
PAGE_PATHS = (
    r"^/documents/1\.0/upload-ui/",
    r"^/documents/1\.0/select-ui/",
    r"^/documents/1\.0/documents/[^/]+/versions/[^/]+/details(/|$)",
)


# ---------------------------------------------------------------------------- helpers


def _message(
    request: Request, web_user: WebUser | None, title: str, message: str, *, status_code: int, hint: str = ""
) -> Response:
    return render(
        request,
        "web/message.html",
        page_context(request, web_user, title=title, message=message, hint=hint),
        status_code=status_code,
    )


def _expired(request: Request, web_user: WebUser | None) -> Response:
    return _message(
        request,
        web_user,
        "Link expired",
        "This link is not valid any more.",
        status_code=404,
        hint="Go back to the application and start again.",
    )


def _wrong_user(request: Request, web_user: WebUser | None) -> Response:
    return _message(
        request,
        web_user,
        "Another account",
        "This flow was started by another account.",
        status_code=403,
        hint="Sign out and sign in as the user who started it in the application.",
    )


def _callback(
    request: Request, web_user: WebUser | None, url: str, expires_at: str, params: dict[str, str]
) -> Response:
    if expires_at <= now_iso():
        return _message(
            request,
            web_user,
            "Application link expired",
            "The application's callback link has expired, so you cannot be sent back to it.",
            status_code=410,
            hint="Go back to the application and start again.",
        )
    return RedirectResponse(with_query(url, params), status_code=302, headers=NO_STORE)


async def _upload_projects(users: UsersDep, projects: ProjectsDep, user_id: str) -> list[Any]:
    """Projects where the user may add documents."""
    return [
        project for project, role in await projects.list_for_user(user_id) if "createDocument" in project_actions(role)
    ]


def _read_form_token(request: Request, token: str | None, purpose: str, session_id: str) -> bool:
    try:
        data = form_tokens(request).load(token, purpose)
    except FormTokenError:
        return False
    return data.get("session") == session_id


# ---------------------------------------------------------------------------- upload metadata page


async def _upload_page(
    request: Request,
    web_user: WebUser,
    session: UploadSession,
    projects: list[Any],
    error: str | None,
    status_code: int = 200,
) -> Response:
    selected = session.project_id or next((f.get("project_id") for f in session.files if f.get("project_id")), None)
    if selected is None and session.server_context and is_uuid(session.server_context):
        selected = normalize_guid(session.server_context)
    if selected not in {p.project_id for p in projects}:
        selected = projects[0].project_id if projects else None
    token = form_tokens(request).sign(UPLOAD_PURPOSE, {"session": session.id})
    return render(
        request,
        "documents/upload.html",
        page_context(
            request,
            web_user,
            files=session.files,
            projects=projects,
            selected_project=selected,
            form_token=token,
            action=request.url.path,
            error=error,
        ),
        status_code=status_code,
    )


@router.get("/upload-ui/{token}")
async def upload_ui(
    request: Request,
    token: Token,
    web_user: WebUserDep,
    sessions: UploadSessionsDep,
    users: UsersDep,
    projects: ProjectsDep,
) -> Response:
    if web_user is None:
        return signin_redirect(request)
    session = await sessions.by_token(token)
    if session is None or session.state not in (STATE_NEW, STATE_METADATA):
        return _expired(request, web_user)
    if session.user_id != web_user.user.id:
        return _wrong_user(request, web_user)
    return await _upload_page(
        request, web_user, session, await _upload_projects(users, projects, web_user.user.id), None
    )


@router.post("/upload-ui/{token}")
async def upload_ui_submit(
    request: Request,
    token: Token,
    web_user: WebUserDep,
    sessions: UploadSessionsDep,
    users: UsersDep,
    projects: ProjectsDep,
) -> Response:
    require_same_origin(request)
    if web_user is None:
        return signin_redirect(request)
    session = await sessions.by_token(token)
    if session is None or session.state not in (STATE_NEW, STATE_METADATA):
        return _expired(request, web_user)
    if session.user_id != web_user.user.id:
        return _wrong_user(request, web_user)
    form = await request.form()
    allowed = await _upload_projects(users, projects, web_user.user.id)
    form_token = form.get("form_token")
    if not _read_form_token(request, form_token if isinstance(form_token, str) else None, UPLOAD_PURPOSE, session.id):
        return await _upload_page(request, web_user, session, allowed, "The form has expired. Please try again.", 400)

    if form.get("action") == "cancel":
        await sessions.update(session.id, state=STATE_CANCELLED)
        return _callback(
            request, web_user, session.callback_url, session.callback_expires_at, {"user_cancelled_upload": "true"}
        )

    project_id = form.get("project_id")
    if not isinstance(project_id, str) or project_id not in {p.project_id for p in allowed}:
        return await _upload_page(
            request, web_user, session, allowed, "Choose a project you may add documents to.", 400
        )
    files = list(session.files)
    for index, item in enumerate(files):
        title = form.get(f"title_{index}")
        version = form.get(f"version_{index}")
        title = title.strip() if isinstance(title, str) else ""
        version = version.strip() if isinstance(version, str) else ""
        if item.get("document_id"):
            title = item["existing_title"] or item["title"]
            if item.get("project_id") and item["project_id"] != project_id:
                return await _upload_page(
                    request, web_user, session, allowed, "A new version must go to the document's own project.", 400
                )
        if not title or len(title) > MAX_TITLE or not version or len(version) > MAX_VERSION_NUMBER:
            return await _upload_page(
                request, web_user, session, allowed, "Every file needs a title and a version number.", 400
            )
        item.update(title=title, version_number=version, project_id=project_id)
    await sessions.update(session.id, state=STATE_METADATA, project_id=project_id, files=files)
    upload_url = f"{api_base(request.app.state.settings)}/upload-sessions/{session.id}/instructions"
    return _callback(
        request, web_user, session.callback_url, session.callback_expires_at, {"upload_documents_url": upload_url}
    )


# ---------------------------------------------------------------------------- selection page


def _filter(records: list[VersionRecord], extensions: list[str], show_all: bool) -> tuple[list[VersionRecord], int]:
    if not extensions or show_all:
        return records, 0
    kept = [record for record in records if record.extension in extensions]
    return kept, len(records) - len(kept)


async def _select_page(
    request: Request,
    web_user: WebUser,
    session: SelectionSession,
    *,
    documents: DocumentsDep,
    users: UsersDep,
    projects: ProjectsDep,
    show_all: bool,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    records = await documents.latest_in_projects(user_id=web_user.user.id)
    shown, hidden = _filter(records, session.extensions, show_all)
    grouped: dict[str, dict[str, Any]] = {}
    for project, _role in await projects.list_for_user(web_user.user.id):
        grouped[project.project_id] = {"project_id": project.project_id, "name": project.name, "documents": []}
    for record in shown:
        grouped.setdefault(
            record.project_id, {"project_id": record.project_id, "name": record.project_name, "documents": []}
        )
        grouped[record.project_id]["documents"].append(record)
    upload_projects = await _upload_projects(users, projects, web_user.user.id)
    token = form_tokens(request).sign(SELECT_PURPOSE, {"session": session.id})
    return render(
        request,
        "documents/select.html",
        page_context(
            request,
            web_user,
            projects=list(grouped.values()),
            extensions=session.extensions,
            hidden_count=hidden,
            show_all_url=with_query(request.url.path, {"all": "1"}),
            form_token=token,
            action=request.url.path,
            upload_projects=upload_projects,
            upload_action=f"{request.url.path}/upload",
            error=error,
        ),
        status_code=status_code,
    )


@router.get("/select-ui/{token}")
async def select_ui(
    request: Request,
    token: Token,
    web_user: WebUserDep,
    sessions: SelectionSessionsDep,
    documents: DocumentsDep,
    users: UsersDep,
    projects: ProjectsDep,
    all: str | None = None,
) -> Response:
    if web_user is None:
        return signin_redirect(request)
    session = await sessions.by_token(token)
    if session is None or session.state != STATE_NEW:
        return _expired(request, web_user)
    if session.user_id != web_user.user.id:
        return _wrong_user(request, web_user)
    return await _select_page(
        request, web_user, session, documents=documents, users=users, projects=projects, show_all=all == "1"
    )


@router.post("/select-ui/{token}")
async def select_ui_submit(
    request: Request,
    token: Token,
    web_user: WebUserDep,
    sessions: SelectionSessionsDep,
    documents: DocumentsDep,
    users: UsersDep,
    projects: ProjectsDep,
) -> Response:
    require_same_origin(request)
    if web_user is None:
        return signin_redirect(request)
    session = await sessions.by_token(token)
    if session is None or session.state != STATE_NEW:
        return _expired(request, web_user)
    if session.user_id != web_user.user.id:
        return _wrong_user(request, web_user)
    form = await request.form()
    form_token = form.get("form_token")
    if not _read_form_token(request, form_token if isinstance(form_token, str) else None, SELECT_PURPOSE, session.id):
        return await _select_page(
            request,
            web_user,
            session,
            documents=documents,
            users=users,
            projects=projects,
            show_all=False,
            error="The form has expired. Please try again.",
            status_code=400,
        )
    if form.get("action") == "cancel":
        await sessions.finish(session.id, state=STATE_CANCELLED, selected=[])
        return _callback(
            request, web_user, session.callback_url, session.callback_expires_at, {"user_cancelled_selection": "true"}
        )
    chosen = [value for value in form.getlist("selected") if isinstance(value, str) and is_uuid(value)]
    if not chosen:
        return await _select_page(
            request,
            web_user,
            session,
            documents=documents,
            users=users,
            projects=projects,
            show_all=False,
            error="Select at least one document.",
            status_code=400,
        )
    records = await documents.latest_many(user_id=web_user.user.id, document_ids=[normalize_guid(c) for c in chosen])
    selected = [f"{record.document_id}:{record.version_index}" for record in records]
    await sessions.finish(session.id, state=STATE_SELECTED, selected=selected)
    url = f"{api_base(request.app.state.settings)}/selection-sessions/{session.id}/documents"
    return _callback(
        request, web_user, session.callback_url, session.callback_expires_at, {"selected_documents_url": url}
    )


@router.post("/select-ui/{token}/upload")
async def select_ui_upload(
    request: Request,
    token: Token,
    web_user: WebUserDep,
    sessions: SelectionSessionsDep,
    documents: DocumentsDep,
    users: UsersDep,
    projects: ProjectsDep,
    storage: StorageDep,
    settings: SettingsDep,
    ifcgraph: IfcGraphDep,
) -> Response:
    """Upload a file from the selection page so it can be selected right away (not part of the specification)."""
    require_same_origin(request)
    if web_user is None:
        return signin_redirect(request)
    session = await sessions.by_token(token)
    if session is None or session.state != STATE_NEW:
        return _expired(request, web_user)
    if session.user_id != web_user.user.id:
        return _wrong_user(request, web_user)
    form = await request.form(max_files=2, max_fields=10)
    form_token = form.get("form_token")
    if not _read_form_token(request, form_token if isinstance(form_token, str) else None, SELECT_PURPOSE, session.id):
        raise HTTPException(400, "The form has expired. Please try again.")
    project_id = form.get("project_id")
    role = await users.project_role(web_user.user.id, project_id) if isinstance(project_id, str) else None
    if role is None or "createDocument" not in project_actions(role) or not isinstance(project_id, str):
        raise HTTPException(403, "You may not add documents to this project")
    upload = form.get("file")
    if upload is None or isinstance(upload, str) or not upload.filename:
        raise HTTPException(400, "Choose a file to upload")
    file_name = sanitize_filename(upload.filename) or "document"
    title = form.get("title")
    title = title.strip()[:MAX_TITLE] if isinstance(title, str) and title.strip() else file_name
    version_id = new_id()
    key = make_key("documents", version_id)
    try:
        size, sha256 = await anyio.to_thread.run_sync(
            store_stream, storage, upload.file, key, settings.max_upload_bytes
        )
    except TooLargeError:
        raise ApiError(413, f"The file exceeds {settings.max_upload_bytes} bytes", code=CODE_UPLOAD_TOO_LARGE) from None
    if size == 0:
        storage.delete(key)
        raise HTTPException(400, "The file is empty")
    project = next((p for p, _ in await projects.list_for_user(web_user.user.id) if p.project_id == project_id), None)
    try:
        record = await documents.create_version(
            project_id=project_id,
            document_id=None,
            title=title,
            version_number="1",
            file_name=file_name,
            size_in_bytes=size,
            sha256=sha256,
            storage_key=key,
            author=web_user.user.username,
            metadata=default_metadata(
                file_name=file_name,
                size_in_bytes=size,
                sha256=sha256,
                author=web_user.user.username,
                project_name=project.name if project else "",
            ),
        )
    except BaseException:
        storage.delete(key)
        raise
    if ifcgraph is not None:
        await ifcgraph.schedule(
            project_id=project_id,
            storage_key=key,
            file_name=file_name,
            document_id=record.document_id,
            version_index=record.version_index,
        )
    return RedirectResponse(request.url.path.removesuffix("/upload"), status_code=303, headers=NO_STORE)


# ---------------------------------------------------------------------------- details page


@router.get("/documents/{document_id}/versions/{version_index}/details")
async def document_details(
    request: Request,
    document_id: DocumentId,
    version_index: VersionIndex,
    web_user: WebUserDep,
    documents: DocumentsDep,
    settings: SettingsDep,
) -> Response:
    if web_user is None:
        return signin_redirect(request)
    record = (
        await documents.version(
            user_id=web_user.user.id, document_id=normalize_guid(document_id), version_index=version_index
        )
        if is_uuid(document_id)
        else None
    )
    if record is None:
        return _message(request, web_user, "Not found", "There is no such document version.", status_code=404)
    versions = await documents.versions(user_id=web_user.user.id, document_id=record.document_id)
    return render(
        request,
        "documents/details.html",
        page_context(
            request,
            web_user,
            record=record,
            versions=versions,
            download_url=f"{request.url.path}/download",
            dataspatium_link=dataspatium_link(
                settings,
                project_id=record.project_id,
                document_id=record.document_id,
                version_index=record.version_index,
            ),
        ),
    )


@router.get("/documents/{document_id}/versions/{version_index}/details/download")
async def document_details_download(
    request: Request,
    document_id: DocumentId,
    version_index: VersionIndex,
    web_user: WebUserDep,
    documents: DocumentsDep,
    storage: StorageDep,
) -> Response:
    if web_user is None:
        return signin_redirect(request)
    record = (
        await documents.version(
            user_id=web_user.user.id, document_id=normalize_guid(document_id), version_index=version_index
        )
        if is_uuid(document_id)
        else None
    )
    if record is None:
        raise HTTPException(404, "Document version not found")
    return file_response(storage, record.storage_key, media_type="application/octet-stream", filename=record.file_name)
