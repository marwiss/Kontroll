# This file was generated with the assistance of an AI coding tool.
"""Viewpoints (BCF API 3.5): cameras, snapshots, bitmaps and components.

Viewpoints are immutable (3.5.2): they are created whole and deleted whole.
Cameras, lines and clipping planes are stored as JSON text on the
``Viewpoint`` node (opaque geometry, identical on Neo4j and Memgraph).
Components become ``Component`` nodes so that the IFC graph can link them to
model elements later, and bitmaps become ``Bitmap`` nodes. Image bytes live in
storage under server-generated keys; the graph holds only the key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException

from opencde.bcf.images import decode_image
from opencde.bcf.schemas import (
    BitmapGET,
    ClippingPlane,
    Coloring,
    Component,
    Direction,
    Line,
    OrthogonalCamera,
    PerspectiveCamera,
    Point,
    SnapshotGET,
    ViewpointGET,
    ViewpointPOST,
    ViewSetupHints,
    Visibility,
)
from opencde.bcf.topic_access import TopicsDep
from opencde.deps import GraphDep, SettingsDep, StorageDep
from opencde.graph.graph import Graph, Tx
from opencde.ids import is_uuid, new_id, normalize_guid
from opencde.storage import LocalStorage, make_key
from opencde.store.protocols import TopicStore, ViewpointStore
from opencde.timeutil import now_iso

ROLE_SELECTION = "selection"
ROLE_COLORING = "coloring"
ROLE_EXCEPTION = "exception"
BATCH = 5_000


@dataclass(frozen=True)
class ViewpointRecord:
    model: ViewpointGET
    author: str
    snapshot_key: str | None
    snapshot_type: str | None


def _point(node: dict[str, Any], prefix: str) -> dict[str, float]:
    return {"x": node[f"{prefix}_x"], "y": node[f"{prefix}_y"], "z": node[f"{prefix}_z"]}


def _bitmap(node: dict[str, Any]) -> BitmapGET:
    return BitmapGET(
        guid=node["guid"],
        bitmap_type=node["bitmap_type"],
        location=Point(**_point(node, "loc")),
        normal=Direction(**_point(node, "nrm")),
        up=Direction(**_point(node, "up")),
        height=node["height"],
    )


def to_record(node: dict[str, Any], bitmaps: list[dict[str, Any]]) -> ViewpointRecord:
    camera = json.loads(node["camera"]) if node.get("camera") else None
    orthogonal = OrthogonalCamera.model_validate(camera) if camera and node.get("camera_kind") == "orthogonal" else None
    perspective = (
        PerspectiveCamera.model_validate(camera) if camera and node.get("camera_kind") == "perspective" else None
    )
    lines = [Line.model_validate(item) for item in json.loads(node["lines"])] if node.get("lines") else None
    planes = (
        [ClippingPlane.model_validate(item) for item in json.loads(node["clipping_planes"])]
        if node.get("clipping_planes")
        else None
    )
    model = ViewpointGET(
        guid=node["guid"],
        index=node.get("index"),
        orthogonal_camera=orthogonal,
        perspective_camera=perspective,
        lines=lines,
        clipping_planes=planes,
        bitmaps=[_bitmap(b) for b in bitmaps] if bitmaps else None,
        snapshot=SnapshotGET(snapshot_type=node["snapshot_type"]) if node.get("snapshot_type") else None,
    )
    return ViewpointRecord(
        model=model,
        author=node["author"],
        snapshot_key=node.get("storage_key"),
        snapshot_type=node.get("snapshot_type"),
    )


def _component_rows(body: ViewpointPOST) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    components = body.components
    if components is None:
        return rows

    def add(role: str, group: int, color: str | None, items: list[Component] | None) -> None:
        for position, item in enumerate(items or []):
            rows.append(
                {
                    "id": new_id(),
                    "role": role,
                    "group_index": group,
                    "position": position,
                    "color": color,
                    "ifc_guid": item.ifc_guid,
                    "originating_system": item.originating_system,
                    "authoring_tool_id": item.authoring_tool_id,
                }
            )

    add(ROLE_SELECTION, 0, None, components.selection)
    for group, coloring in enumerate(components.coloring or []):
        add(ROLE_COLORING, group, coloring.color.upper(), coloring.components)
    add(ROLE_EXCEPTION, 0, None, components.visibility.exceptions)
    return rows


def _component(node: dict[str, Any]) -> Component:
    return Component(
        ifc_guid=node.get("ifc_guid"),
        originating_system=node.get("originating_system"),
        authoring_tool_id=node.get("authoring_tool_id"),
    )


_SCOPE = """
MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
      -[:HAS_TOPIC]->(:Topic {guid: $topic_guid})-[:HAS_VIEWPOINT]->(v:Viewpoint {guid: $guid})
"""


class ViewpointRepository:
    def __init__(self, graph: Graph, storage: LocalStorage, topics: TopicStore, *, max_image_bytes: int) -> None:
        self.graph = graph
        self.storage = storage
        self.topics = topics
        self.max_image_bytes = max_image_bytes

    async def search(self, *, user_id: str, project_id: str, topic_guid: str) -> list[ViewpointRecord]:
        rows = await self.graph.run(
            """
            MATCH (:User {id: $user_id})-[:MEMBER_OF]->(:Project {project_id: $project_id})
                  -[:HAS_TOPIC]->(:Topic {guid: $topic_guid})-[:HAS_VIEWPOINT]->(v:Viewpoint)
            OPTIONAL MATCH (v)-[:HAS_BITMAP]->(b:Bitmap)
            WITH v, b ORDER BY v.creation_date, v.guid, b.position
            WITH v, collect(CASE WHEN b IS NULL THEN null ELSE properties(b) END) AS bitmaps
            ORDER BY v.creation_date, v.guid
            RETURN properties(v) AS viewpoint, bitmaps
            """,
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
        )
        return [to_record(row["viewpoint"], row["bitmaps"]) for row in rows]

    async def get(self, *, user_id: str, project_id: str, topic_guid: str, guid: str) -> ViewpointRecord | None:
        row = await self.graph.one(
            _SCOPE
            + """
            OPTIONAL MATCH (v)-[:HAS_BITMAP]->(b:Bitmap)
            WITH v, b ORDER BY b.position
            RETURN properties(v) AS viewpoint, collect(CASE WHEN b IS NULL THEN null ELSE properties(b) END) AS bitmaps
            """,
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
            guid=guid,
        )
        return to_record(row["viewpoint"], row["bitmaps"]) if row else None

    async def bitmap(
        self, *, user_id: str, project_id: str, topic_guid: str, guid: str, bitmap_guid: str
    ) -> dict[str, Any] | None:
        row = await self.graph.one(
            _SCOPE + "MATCH (v)-[:HAS_BITMAP]->(b:Bitmap {guid: $bitmap_guid}) RETURN properties(b) AS bitmap",
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
            guid=guid,
            bitmap_guid=bitmap_guid,
        )
        return row["bitmap"] if row else None

    async def components(
        self, *, user_id: str, project_id: str, topic_guid: str, guid: str, role: str
    ) -> list[dict[str, Any]]:
        rows = await self.graph.run(
            _SCOPE
            + """
            MATCH (v)-[:HAS_COMPONENT]->(c:Component {role: $role})
            RETURN properties(c) AS component
            ORDER BY c.group_index, c.position
            """,
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
            guid=guid,
            role=role,
        )
        return [row["component"] for row in rows]

    async def selection(self, **scope: str) -> list[Component]:
        return [_component(node) for node in await self.components(role=ROLE_SELECTION, **scope)]

    async def coloring(self, **scope: str) -> list[Coloring]:
        groups: dict[int, Coloring] = {}
        for node in await self.components(role=ROLE_COLORING, **scope):
            group = groups.setdefault(node["group_index"], Coloring(color=node["color"], components=[]))
            group.components.append(_component(node))
        return [groups[key] for key in sorted(groups)]

    async def visibility(self, node: dict[str, Any], **scope: str) -> Visibility:
        exceptions = [_component(item) for item in await self.components(role=ROLE_EXCEPTION, **scope)]
        hints = None
        if node.get("has_hints"):
            hints = ViewSetupHints(
                spaces_visible=bool(node.get("spaces_visible")),
                space_boundaries_visible=bool(node.get("space_boundaries_visible")),
                openings_visible=bool(node.get("openings_visible")),
            )
        return Visibility(
            default_visibility=bool(node.get("default_visibility", True)), exceptions=exceptions, view_setup_hints=hints
        )

    async def node(self, *, user_id: str, project_id: str, topic_guid: str, guid: str) -> dict[str, Any] | None:
        row = await self.graph.one(
            _SCOPE + "RETURN properties(v) AS viewpoint",
            user_id=user_id,
            project_id=project_id,
            topic_guid=topic_guid,
            guid=guid,
        )
        return row["viewpoint"] if row else None

    async def create(self, *, project_id: str, topic_guid: str, author: str, body: ViewpointPOST) -> ViewpointRecord:
        if body.guid and not is_uuid(body.guid):
            raise HTTPException(400, "guid must be a UUID")
        guid = normalize_guid(body.guid) if body.guid else new_id()
        if await self.graph.one("MATCH (v:Viewpoint {guid: $guid}) RETURN v.guid AS guid", guid=guid):
            raise HTTPException(409, "A viewpoint with this guid already exists")  # Foundation API 1.5.1
        now = now_iso()

        # Decode and verify every image before anything is written.
        snapshot: tuple[str, bytes] | None = None
        if body.snapshot:
            data = decode_image(
                body.snapshot.snapshot_data, body.snapshot.snapshot_type, self.max_image_bytes, "snapshot"
            )
            snapshot = (make_key("snapshots", guid, body.snapshot.snapshot_type), data)
        bitmap_rows: list[dict[str, Any]] = []
        bitmap_files: list[tuple[str, bytes]] = []
        for position, bitmap in enumerate(body.bitmaps or []):
            data = decode_image(bitmap.bitmap_data, bitmap.bitmap_type, self.max_image_bytes, f"bitmaps[{position}]")
            bitmap_guid = new_id()
            key = make_key("bitmaps", bitmap_guid, bitmap.bitmap_type)
            bitmap_files.append((key, data))
            bitmap_rows.append(
                {
                    "guid": bitmap_guid,
                    "position": position,
                    "bitmap_type": bitmap.bitmap_type,
                    "storage_key": key,
                    "height": bitmap.height,
                    "loc_x": bitmap.location.x,
                    "loc_y": bitmap.location.y,
                    "loc_z": bitmap.location.z,
                    "nrm_x": bitmap.normal.x,
                    "nrm_y": bitmap.normal.y,
                    "nrm_z": bitmap.normal.z,
                    "up_x": bitmap.up.x,
                    "up_y": bitmap.up.y,
                    "up_z": bitmap.up.z,
                }
            )

        camera: OrthogonalCamera | PerspectiveCamera | None = body.orthogonal_camera or body.perspective_camera
        components = body.components
        hints = components.visibility.view_setup_hints if components else None
        properties = {
            "guid": guid,
            "index": body.index,
            "author": author,
            "creation_date": now,
            "camera_kind": "orthogonal"
            if body.orthogonal_camera
            else ("perspective" if body.perspective_camera else None),
            "camera": camera.model_dump_json() if camera else None,
            "lines": json.dumps([line.model_dump() for line in body.lines]) if body.lines else None,
            "clipping_planes": json.dumps([plane.model_dump() for plane in body.clipping_planes])
            if body.clipping_planes
            else None,
            "snapshot_type": body.snapshot.snapshot_type if body.snapshot else None,
            "storage_key": snapshot[0] if snapshot else None,
            "has_components": components is not None,
            "default_visibility": components.visibility.default_visibility if components else True,
            "has_hints": hints is not None,
            "spaces_visible": hints.spaces_visible if hints else None,
            "space_boundaries_visible": hints.space_boundaries_visible if hints else None,
            "openings_visible": hints.openings_visible if hints else None,
        }
        component_rows = _component_rows(body)

        async def work(tx: Tx) -> dict[str, Any]:
            if await tx.one("MATCH (v:Viewpoint {guid: $guid}) RETURN v.guid AS guid", guid=guid):
                raise HTTPException(409, "A viewpoint with this guid already exists")
            row = await tx.one(
                """
                MATCH (:Project {project_id: $project_id})-[:HAS_TOPIC]->(t:Topic {guid: $topic_guid}),
                      (u:User {username: $author})
                CREATE (t)-[:HAS_VIEWPOINT]->(v:Viewpoint $props)
                CREATE (v)-[:CREATED_BY]->(u)
                RETURN properties(v) AS viewpoint
                """,
                project_id=project_id,
                topic_guid=topic_guid,
                author=author,
                props=properties,
            )
            if row is None:
                raise HTTPException(404, "Topic not found")
            for start in range(0, len(component_rows), BATCH):
                await tx.run(
                    """
                    MATCH (v:Viewpoint {guid: $guid})
                    UNWIND $rows AS row
                    CREATE (v)-[:HAS_COMPONENT]->(:Component {
                        id: row.id, role: row.role, group_index: row.group_index, position: row.position,
                        color: row.color, ifc_guid: row.ifc_guid, originating_system: row.originating_system,
                        authoring_tool_id: row.authoring_tool_id
                    })
                    """,
                    guid=guid,
                    rows=component_rows[start : start + BATCH],
                )
            if bitmap_rows:
                await tx.run(
                    """
                    MATCH (v:Viewpoint {guid: $guid})
                    UNWIND $rows AS row
                    CREATE (v)-[:HAS_BITMAP]->(:Bitmap {
                        guid: row.guid, position: row.position, bitmap_type: row.bitmap_type,
                        storage_key: row.storage_key, height: row.height,
                        loc_x: row.loc_x, loc_y: row.loc_y, loc_z: row.loc_z,
                        nrm_x: row.nrm_x, nrm_y: row.nrm_y, nrm_z: row.nrm_z,
                        up_x: row.up_x, up_y: row.up_y, up_z: row.up_z
                    })
                    """,
                    guid=guid,
                    rows=bitmap_rows,
                )
            # A new viewpoint is "floating" until a comment refers to it, which moves the topic (BCF 3.2.1).
            await self.topics.touch(tx, guid=topic_guid, author=author, now=now)
            return row["viewpoint"]

        written: list[str] = []
        try:
            for key, data in ([snapshot] if snapshot else []) + bitmap_files:
                self.storage.write_bytes(key, data)
                written.append(key)
            node = await self.graph.write(work)
        except BaseException:
            for key in written:
                self.storage.delete(key)
            raise
        return to_record(node, bitmap_rows)

    async def delete(self, *, topic_guid: str, guid: str) -> list[str]:
        """Delete the viewpoint with its components and bitmaps; 409 while a comment refers to it (BCF 3.5.9)."""

        async def work(tx: Tx) -> list[str] | None:
            row = await tx.one(
                """
                MATCH (t:Topic {guid: $topic_guid})-[:HAS_VIEWPOINT]->(v:Viewpoint {guid: $guid})
                OPTIONAL MATCH (t)-[:HAS_COMMENT]->(c:Comment {viewpoint_guid: $guid})
                WITH v, count(c) AS comments
                OPTIONAL MATCH (v)-[:HAS_BITMAP]->(b:Bitmap)
                RETURN comments, v.storage_key AS snapshot_key, collect(b.storage_key) AS bitmap_keys
                """,
                topic_guid=topic_guid,
                guid=guid,
            )
            if row is None:
                return None
            if row["comments"]:
                raise HTTPException(409, "A comment refers to this viewpoint; update the comment first")
            await tx.run(
                """
                MATCH (:Topic {guid: $topic_guid})-[:HAS_VIEWPOINT]->(v:Viewpoint {guid: $guid})
                OPTIONAL MATCH (v)-[:HAS_COMPONENT|HAS_BITMAP]->(child)
                DETACH DELETE child, v
                """,
                topic_guid=topic_guid,
                guid=guid,
            )
            keys = [key for key in row["bitmap_keys"] or [] if key]
            if row["snapshot_key"]:
                keys.append(row["snapshot_key"])
            return keys

        keys = await self.graph.write(work)
        if keys is None:
            raise HTTPException(404, "Viewpoint not found")
        return keys


def viewpoint_repository(
    graph: GraphDep, storage: StorageDep, topics: TopicsDep, settings: SettingsDep
) -> ViewpointStore:
    return ViewpointRepository(graph, storage, topics, max_image_bytes=settings.max_image_bytes)


ViewpointsDep = Annotated[ViewpointStore, Depends(viewpoint_repository)]
