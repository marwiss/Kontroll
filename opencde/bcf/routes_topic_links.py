# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.2.6-3.2.7 BIM snippet, 3.3.2-3.3.3 files, 3.6 related topics, 3.7 document references."""

from __future__ import annotations

import json
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, HTTPException, Path, Request, Response
from fastapi.responses import StreamingResponse

from opencde.bcf.access import parse_guid
from opencde.bcf.binary import file_response, filename_from_content_disposition, receive_upload
from opencde.bcf.schemas import (
    MAX_FILES,
    MAX_RELATED,
    DocumentReferencePOST,
    DocumentReferencePUT,
    FileRef,
    RelatedTopic,
    dump,
)
from opencde.bcf.topic_access import TopicCtx
from opencde.bcf.topic_links import LinksDep
from opencde.deps import SettingsDep, StorageDep
from opencde.documents.changes import MAX_CHANGE_SET_BYTES, SNIPPET_TYPE, problems
from opencde.ifcgraph.service import IfcGraphDep
from opencde.ratelimit import RATE_UPLOAD, limiter
from opencde.storage import LocalStorage, make_key

router = APIRouter(prefix="/projects/{project_id}/topics/{topic_id}", tags=["BCF API"])

ReferenceId = Annotated[str, Path(alias="reference_id", max_length=64)]


# -- BIM snippet (3.2.6, 3.2.7) -----------------------------------------------------------------


@router.get("/snippet", summary="3.2.6 GET Topic BIM Snippet", response_class=StreamingResponse)
async def snippet_get(topic: TopicCtx, links: LinksDep, storage: StorageDep) -> StreamingResponse:
    """The stored snippet file. 404 when the topic's snippet is external or was never uploaded."""
    info = await links.snippet(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid)
    if info is None:
        raise HTTPException(404, "Topic has no stored BIM snippet")
    return file_response(storage, info["storage_key"], media_type="application/octet-stream", filename=info["filename"])


@router.put("/snippet", summary="3.2.7 PUT Topic BIM Snippet", status_code=200, response_class=Response)
@limiter.limit(RATE_UPLOAD)
async def snippet_put(
    request: Request,
    topic: TopicCtx,
    links: LinksDep,
    storage: StorageDep,
    settings: SettingsDep,
    ifcgraph: IfcGraphDep,
) -> Response:
    """Upload the snippet as the request body. The topic's ``bim_snippet`` must already describe it.

    A snippet of the type `DataregiumIfcChangeSet` is held to the change set's schema
    (`GET /documents/1.0/ifc-changes/schema`), and 400 says what is wrong with it; when the IFC-LPG module is on,
    the change set is then tried on its base version (`GET …/ifc-proposal`).
    """
    topic.require_topic_action("updateBimSnippet")
    if topic.topic.bim_snippet is None:
        raise HTTPException(400, "Set bim_snippet on the topic before uploading the snippet file")
    key = make_key("snippets", topic.guid, "bin")
    size = await receive_upload(request, storage, key, settings.max_upload_bytes)
    if topic.topic.bim_snippet.snippet_type == SNIPPET_TYPE:
        found = await anyio.to_thread.run_sync(_change_set_problems, storage, key, size)
        if found:
            storage.delete(key)
            raise HTTPException(400, "The snippet is not a change set: " + "; ".join(found))
    await links.set_snippet(
        project_id=topic.project_id,
        topic_guid=topic.guid,
        author=topic.username,
        storage_key=key,
        filename=filename_from_content_disposition(request.headers.get("content-disposition")),
        size=size,
    )
    if ifcgraph is not None and topic.topic.bim_snippet.snippet_type == SNIPPET_TYPE:
        await ifcgraph.schedule_proposal(
            project_id=topic.project_id, topic_guid=topic.guid, snippet_key=key, author=topic.username
        )
    return Response(status_code=200)


def _change_set_problems(storage: LocalStorage, key: str, size: int) -> list[str]:
    """What keeps the stored snippet from being a change set (ADR 0021); empty when nothing does."""
    if size > MAX_CHANGE_SET_BYTES:
        return [f"a change set is at most {MAX_CHANGE_SET_BYTES} bytes"]
    with storage.open_read(key) as handle:
        raw = handle.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return ["the body is not JSON"]
    return problems(data)


# -- header files (3.3.2, 3.3.3) ----------------------------------------------------------------


@router.get("/files", summary="3.3.2 GET Files (Header)")
async def files_get(topic: TopicCtx, links: LinksDep) -> list[dict[str, Any]]:
    return [
        dump(item)
        for item in await links.files(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid)
    ]


@router.put("/files", summary="3.3.3 PUT Files (Header)")
async def files_put(topic: TopicCtx, body: list[FileRef], links: LinksDep) -> list[dict[str, Any]]:
    """Replace the topic's file references. Needs ``updateFiles``."""
    topic.require_topic_action("updateFiles")
    if len(body) > MAX_FILES:
        raise HTTPException(400, f"At most {MAX_FILES} files per topic")
    stored = await links.set_files(
        project_id=topic.project_id, topic_guid=topic.guid, author=topic.username, files=body
    )
    return [dump(item) for item in stored]


# -- related topics (3.6) -----------------------------------------------------------------------


@router.get("/related_topics", summary="3.6.1 GET Related Topics")
async def related_topics_get(topic: TopicCtx, links: LinksDep) -> list[dict[str, Any]]:
    guids = await links.related(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid)
    return [dump(RelatedTopic(related_topic_guid=guid)) for guid in guids]


@router.put("/related_topics", summary="3.6.2 PUT Related Topics")
async def related_topics_put(topic: TopicCtx, body: list[RelatedTopic], links: LinksDep) -> list[dict[str, Any]]:
    """Replace the list of related topics (all must belong to the project). Needs ``updateRelatedTopics``."""
    topic.require_topic_action("updateRelatedTopics")
    if len(body) > MAX_RELATED:
        raise HTTPException(400, f"At most {MAX_RELATED} related topics")
    guids = await links.set_related(
        project_id=topic.project_id,
        topic_guid=topic.guid,
        author=topic.username,
        guids=[item.related_topic_guid for item in body],
    )
    return [dump(RelatedTopic(related_topic_guid=guid)) for guid in guids]


# -- document references (3.7) ------------------------------------------------------------------


@router.get("/document_references", summary="3.7.1 GET Document References")
async def document_references_get(topic: TopicCtx, links: LinksDep) -> list[dict[str, Any]]:
    found = await links.references(user_id=topic.user_id, project_id=topic.project_id, topic_guid=topic.guid)
    return [dump(item) for item in found]


@router.post("/document_references", summary="3.7.2 POST Document Reference", status_code=201)
async def document_reference_post(topic: TopicCtx, body: DocumentReferencePOST, links: LinksDep) -> dict[str, Any]:
    """Reference a project document (``document_guid``) or an external resource (``url``). Needs ``updateDocumentReferences``."""
    topic.require_topic_action("updateDocumentReferences")
    created = await links.add_reference(
        project_id=topic.project_id, topic_guid=topic.guid, author=topic.username, body=body
    )
    return dump(created)


@router.put("/document_references/{reference_id}", summary="3.7.3 PUT Document Reference")
async def document_reference_put(
    topic: TopicCtx, reference_id: ReferenceId, body: DocumentReferencePUT, links: LinksDep
) -> dict[str, Any]:
    topic.require_topic_action("updateDocumentReferences")
    guid = parse_guid(reference_id, "Document reference")
    updated = await links.update_reference(
        project_id=topic.project_id, topic_guid=topic.guid, guid=guid, author=topic.username, body=body
    )
    if updated is None:
        raise HTTPException(404, "Document reference not found")
    return dump(updated)
