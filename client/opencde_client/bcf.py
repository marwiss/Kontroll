# This file was generated with the assistance of an AI coding tool.
"""BCF API 3.0 (https://github.com/buildingSMART/BCF-API/tree/release_3_0).

Methods return the JSON objects of the specification as dictionaries, so that
new fields never need a library update. Section numbers refer to the README of
the specification.
"""

from __future__ import annotations

import base64
from typing import Any, BinaryIO
from urllib.parse import quote

from opencde_client.http import ApiSession

JSON = dict[str, Any]


def _odata(
    filter: str | None = None,
    orderby: str | None = None,
    top: int | None = None,
    skip: int | None = None,
    include_authorization: bool = False,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if filter:
        params["$filter"] = filter
    if orderby:
        params["$orderby"] = orderby
    if top is not None:
        params["$top"] = str(top)
    if skip is not None:
        params["$skip"] = str(skip)
    if include_authorization:
        params["includeAuthorization"] = "true"
    return params


def image_payload(data: bytes) -> tuple[str, str]:
    """``(type, base64)`` for a snapshot or bitmap from PNG or JPEG bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "png"
    elif data.startswith(b"\xff\xd8\xff"):
        kind = "jpg"
    else:
        raise ValueError("snapshots and bitmaps must be PNG or JPEG")
    return kind, base64.b64encode(data).decode("ascii")


def content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


class BcfClient:
    def __init__(self, session: ApiSession, version: str = "3.0") -> None:
        self.session = session
        self.base = f"/bcf/{version}"

    def _p(self, project_id: str, *rest: str) -> str:
        return "/".join([f"{self.base}/projects/{project_id}", *rest])

    # -- 3.1 projects ------------------------------------------------------------------------------

    def projects(self, *, include_authorization: bool = False) -> list[JSON]:
        return self.session.json(
            "GET", f"{self.base}/projects", params=_odata(include_authorization=include_authorization)
        )

    def project(self, project_id: str, *, include_authorization: bool = False) -> JSON:
        return self.session.json("GET", self._p(project_id), params=_odata(include_authorization=include_authorization))

    def update_project(self, project_id: str, name: str) -> JSON:
        return self.session.json("PUT", self._p(project_id), json={"name": name})

    def extensions(self, project_id: str) -> JSON:
        return self.session.json("GET", self._p(project_id, "extensions"))

    # -- 3.2 topics ---------------------------------------------------------------------------------

    def topics(self, project_id: str, **odata: Any) -> list[JSON]:
        return self.session.json("GET", self._p(project_id, "topics"), params=_odata(**odata))

    def create_topic(self, project_id: str, topic: JSON) -> JSON:
        return self.session.json("POST", self._p(project_id, "topics"), json=topic)

    def topic(self, project_id: str, topic_guid: str, *, include_authorization: bool = False) -> JSON:
        return self.session.json(
            "GET", self._p(project_id, "topics", topic_guid), params=_odata(include_authorization=include_authorization)
        )

    def update_topic(self, project_id: str, topic_guid: str, topic: JSON) -> JSON:
        return self.session.json("PUT", self._p(project_id, "topics", topic_guid), json=topic)

    def delete_topic(self, project_id: str, topic_guid: str) -> None:
        self.session.delete(self._p(project_id, "topics", topic_guid))

    def snippet(self, project_id: str, topic_guid: str) -> bytes:
        return self.session.get(self._p(project_id, "topics", topic_guid, "snippet")).content

    def upload_snippet(self, project_id: str, topic_guid: str, filename: str, data: bytes | BinaryIO) -> None:
        self.session.put(
            self._p(project_id, "topics", topic_guid, "snippet"),
            content=data,
            headers={"Content-Disposition": content_disposition(filename), "Content-Type": "application/octet-stream"},
        )

    # -- 3.3 files ----------------------------------------------------------------------------------

    def files_information(self, project_id: str) -> list[JSON]:
        return self.session.json("GET", self._p(project_id, "files_information"))

    def files(self, project_id: str, topic_guid: str) -> list[JSON]:
        return self.session.json("GET", self._p(project_id, "topics", topic_guid, "files"))

    def set_files(self, project_id: str, topic_guid: str, files: list[JSON]) -> list[JSON]:
        return self.session.json("PUT", self._p(project_id, "topics", topic_guid, "files"), json=files)

    # -- 3.4 comments -------------------------------------------------------------------------------

    def comments(self, project_id: str, topic_guid: str, **odata: Any) -> list[JSON]:
        return self.session.json("GET", self._p(project_id, "topics", topic_guid, "comments"), params=_odata(**odata))

    def create_comment(self, project_id: str, topic_guid: str, comment: JSON) -> JSON:
        return self.session.json("POST", self._p(project_id, "topics", topic_guid, "comments"), json=comment)

    def comment(self, project_id: str, topic_guid: str, comment_guid: str) -> JSON:
        return self.session.json("GET", self._p(project_id, "topics", topic_guid, "comments", comment_guid))

    def update_comment(self, project_id: str, topic_guid: str, comment_guid: str, comment: JSON) -> JSON:
        return self.session.json(
            "PUT", self._p(project_id, "topics", topic_guid, "comments", comment_guid), json=comment
        )

    def delete_comment(self, project_id: str, topic_guid: str, comment_guid: str) -> None:
        self.session.delete(self._p(project_id, "topics", topic_guid, "comments", comment_guid))

    # -- 3.5 viewpoints -----------------------------------------------------------------------------

    def viewpoints(self, project_id: str, topic_guid: str, *, include_authorization: bool = False) -> list[JSON]:
        return self.session.json(
            "GET",
            self._p(project_id, "topics", topic_guid, "viewpoints"),
            params=_odata(include_authorization=include_authorization),
        )

    def create_viewpoint(self, project_id: str, topic_guid: str, viewpoint: JSON) -> JSON:
        return self.session.json("POST", self._p(project_id, "topics", topic_guid, "viewpoints"), json=viewpoint)

    def viewpoint(self, project_id: str, topic_guid: str, viewpoint_guid: str) -> JSON:
        return self.session.json("GET", self._p(project_id, "topics", topic_guid, "viewpoints", viewpoint_guid))

    def snapshot(self, project_id: str, topic_guid: str, viewpoint_guid: str) -> tuple[bytes, str]:
        response = self.session.get(self._p(project_id, "topics", topic_guid, "viewpoints", viewpoint_guid, "snapshot"))
        return response.content, response.headers.get("content-type", "")

    def bitmap(self, project_id: str, topic_guid: str, viewpoint_guid: str, bitmap_guid: str) -> tuple[bytes, str]:
        response = self.session.get(
            self._p(project_id, "topics", topic_guid, "viewpoints", viewpoint_guid, "bitmaps", bitmap_guid)
        )
        return response.content, response.headers.get("content-type", "")

    def selection(self, project_id: str, topic_guid: str, viewpoint_guid: str) -> JSON:
        return self.session.json(
            "GET", self._p(project_id, "topics", topic_guid, "viewpoints", viewpoint_guid, "selection")
        )

    def coloring(self, project_id: str, topic_guid: str, viewpoint_guid: str) -> JSON:
        return self.session.json(
            "GET", self._p(project_id, "topics", topic_guid, "viewpoints", viewpoint_guid, "coloring")
        )

    def visibility(self, project_id: str, topic_guid: str, viewpoint_guid: str) -> JSON:
        return self.session.json(
            "GET", self._p(project_id, "topics", topic_guid, "viewpoints", viewpoint_guid, "visibility")
        )

    def delete_viewpoint(self, project_id: str, topic_guid: str, viewpoint_guid: str) -> None:
        self.session.delete(self._p(project_id, "topics", topic_guid, "viewpoints", viewpoint_guid))

    # -- 3.6 related topics, 3.7 document references -----------------------------------------------

    def related_topics(self, project_id: str, topic_guid: str) -> list[JSON]:
        return self.session.json("GET", self._p(project_id, "topics", topic_guid, "related_topics"))

    def set_related_topics(self, project_id: str, topic_guid: str, related: list[str]) -> list[JSON]:
        body = [{"related_topic_guid": guid} for guid in related]
        return self.session.json("PUT", self._p(project_id, "topics", topic_guid, "related_topics"), json=body)

    def document_references(self, project_id: str, topic_guid: str) -> list[JSON]:
        return self.session.json("GET", self._p(project_id, "topics", topic_guid, "document_references"))

    def add_document_reference(self, project_id: str, topic_guid: str, reference: JSON) -> JSON:
        return self.session.json(
            "POST", self._p(project_id, "topics", topic_guid, "document_references"), json=reference
        )

    def update_document_reference(self, project_id: str, topic_guid: str, reference_guid: str, reference: JSON) -> JSON:
        return self.session.json(
            "PUT", self._p(project_id, "topics", topic_guid, "document_references", reference_guid), json=reference
        )

    # -- 3.8 documents ------------------------------------------------------------------------------

    def documents(self, project_id: str) -> list[JSON]:
        return self.session.json("GET", self._p(project_id, "documents"))

    def upload_document(
        self, project_id: str, filename: str, data: bytes | BinaryIO, *, guid: str | None = None
    ) -> JSON:
        return self.session.json(
            "POST",
            self._p(project_id, "documents"),
            params={"guid": guid} if guid else None,
            content=data,
            headers={"Content-Disposition": content_disposition(filename), "Content-Type": "application/octet-stream"},
        )

    def download_document(self, project_id: str, document_guid: str) -> tuple[bytes, str]:
        response = self.session.get(self._p(project_id, "documents", document_guid))
        return response.content, response.headers.get("content-disposition", "")

    # -- 3.9, 3.10 events --------------------------------------------------------------------------

    def topic_events(self, project_id: str, topic_guid: str | None = None, **odata: Any) -> list[JSON]:
        path = (
            self._p(project_id, "topics", topic_guid, "events")
            if topic_guid
            else self._p(project_id, "topics", "events")
        )
        return self.session.json("GET", path, params=_odata(**odata))

    def comment_events(
        self, project_id: str, topic_guid: str | None = None, comment_guid: str | None = None, **odata: Any
    ) -> list[JSON]:
        if topic_guid and comment_guid:
            path = self._p(project_id, "topics", topic_guid, "comments", comment_guid, "events")
        else:
            path = self._p(project_id, "topics", "comments", "events")
        return self.session.json("GET", path, params=_odata(**odata))
