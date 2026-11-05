# This file was generated with the assistance of an AI coding tool.
"""The whole story over HTTP with the client library: discovery, PKCE sign-in, documents, topics, security."""

from __future__ import annotations

import hashlib

import pytest

from opencde_client import ApiError, AuthError, OpenCdeClient
from opencde_client.bcf import image_payload
from opencde_client.testing import HeadlessBrowser, headless_authorize
from tests.conftest import FIXTURES_DIR
from tests.ui.conftest import LiveServer

pytestmark = pytest.mark.e2e

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8ffff3f0005fe02fea7358184"
    "0000000049454e44ae426082"
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 16 + b"\xff\xd9"
WALLS = ("1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "3k3LbXmTfDWODxdSuyCGYE")
CALLBACK = "http://127.0.0.1:9/callback"


def signed_in(live: LiveServer, username: str) -> OpenCdeClient:
    cde = OpenCdeClient(live.url, client_id=live.world.public_client_id)
    tokens = headless_authorize(
        cde.oauth, username=username, password=live.world.password, redirect_uri=live.world.redirect
    )
    cde.use_tokens(tokens)
    return cde


def test_end_to_end_scenario(live_server: LiveServer) -> None:
    live = live_server
    world = live.world

    # 1. Discovery and sign-in.
    versions = {v.api_id: v.version_id for v in OpenCdeClient(live.url, client_id="x").foundation.versions()}
    assert versions == {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"}
    with signed_in(live, "editor") as editor:
        assert editor.auth_info.pkce_required
        assert "authorization_code_grant" in editor.auth_info.supported_oauth2_flows, "Foundation API 2.2 enum"
        me = editor.foundation.current_user()
        assert me["id"] == "editor"
        project_id = world.project_id
        assert [p["name"] for p in editor.bcf.projects()] == ["Building permit"]

        # 2. Documents: upload the IFC model in parts, download it, upload a new version, query with ETag.
        ifc = (FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes()
        started = editor.documents.start_upload(
            [{"file_name": "three_walls_gtin.ifc", "session_file_id": "model"}], callback_url=CALLBACK
        )
        browser = HeadlessBrowser(live.url)
        browser.sign_in("editor", world.password)
        params = browser.finish_upload_page(
            started["upload_ui_url"], project_id=project_id, titles={0: ("Three walls", "1")}
        )
        plan = editor.documents.upload_instructions(params["upload_documents_url"], {"model": len(ifc)})
        instructions = plan["documents_to_upload"][0]
        assert len(instructions["upload_file_parts"]) > 1, "the test server asks for small parts"
        version = editor.documents.upload_file(instructions, ifc)
        assert version["title"] == "Three walls" and version["file_description"]["size_in_bytes"] == len(ifc)
        assert hashlib.sha256(editor.documents.download(version)).hexdigest() == hashlib.sha256(ifc).hexdigest()
        metadata = {entry["name"]: entry["value"][0] for entry in editor.documents.metadata(version)["metadata"]}
        assert metadata["sha256"] == hashlib.sha256(ifc).hexdigest()

        latest, etag = editor.documents.query_versions([version["document_id"]])
        assert latest and latest["versions"][0]["version_index"] == 1 and etag
        assert editor.documents.query_versions([version["document_id"]], etag=etag) == (None, etag)

        again = editor.documents.start_upload(
            [
                {
                    "file_name": "three_walls_gtin_v2.ifc",
                    "session_file_id": "model",
                    "document_id": version["document_id"],
                }
            ],
            callback_url=CALLBACK,
        )
        params = browser.finish_upload_page(again["upload_ui_url"], project_id=project_id, titles={0: ("x", "B")})
        plan = editor.documents.upload_instructions(params["upload_documents_url"], {"model": len(ifc)})
        second = editor.documents.upload_file(plan["documents_to_upload"][0], ifc)
        assert second["version_index"] == 2 and second["version_number"] == "B"
        assert [v["version_index"] for v in editor.documents.versions(version)["documents"]] == [1, 2]
        changed, new_etag = editor.documents.query_versions([version["document_id"]], etag=etag)
        assert changed and changed["versions"][0]["version_index"] == 2 and new_etag != etag

        # Selection flow as the viewer.
        with signed_in(live, "viewer") as viewer:
            selection = viewer.documents.start_selection(callback_url=CALLBACK, supported_file_extensions=[".ifc"])
            viewer_browser = HeadlessBrowser(live.url)
            viewer_browser.sign_in("viewer", world.password)
            params = viewer_browser.finish_selection_page(
                selection["select_documents_url"], document_ids=[version["document_id"]]
            )
            selected = viewer.documents.selected_documents(params["selected_documents_url"])
            assert [d["version_index"] for d in selected["documents"]] == [2]
            assert viewer.documents.download(selected["documents"][0]) == ifc
            viewer_browser.close()

        # 3. BCF: a topic with labels, two viewpoints, comments, related topics, a document reference, events.
        topic = editor.bcf.create_topic(
            project_id,
            {
                "title": "Walls carry wrong GTIN",
                "topic_type": "Issue",
                "topic_status": "Open",
                "labels": ["Reuse", "Structural"],
                "priority": "High",
                "assigned_to": "contributor",
            },
        )
        assert topic["server_assigned_id"] == "ISSUE-0001"
        png_type, png_data = image_payload(PNG)
        jpg_type, jpg_data = image_payload(JPEG)
        camera = {
            "camera_view_point": {"x": 10.0, "y": -5.0, "z": 3.0},
            "camera_direction": {"x": -0.7, "y": 0.7, "z": -0.2},
            "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
            "field_of_view": 60.0,
            "aspect_ratio": 1.78,
        }
        viewpoint = editor.bcf.create_viewpoint(
            project_id,
            topic["guid"],
            {
                "perspective_camera": camera,
                "lines": [{"start_point": {"x": 0, "y": 0, "z": 0}, "end_point": {"x": 5, "y": 0, "z": 0}}],
                "clipping_planes": [{"location": {"x": 0, "y": 0, "z": 2.8}, "direction": {"x": 0, "y": 0, "z": -1}}],
                "snapshot": {"snapshot_type": png_type, "snapshot_data": png_data},
                "components": {
                    "selection": [{"ifc_guid": guid} for guid in WALLS],
                    "coloring": [
                        {"color": "FF0000", "components": [{"ifc_guid": WALLS[0]}]},
                        {"color": "0000FF", "components": [{"ifc_guid": WALLS[1]}, {"ifc_guid": WALLS[2]}]},
                    ],
                    "visibility": {"default_visibility": False, "exceptions": [{"ifc_guid": guid} for guid in WALLS]},
                },
            },
        )
        second_viewpoint = editor.bcf.create_viewpoint(
            project_id, topic["guid"], {"snapshot": {"snapshot_type": jpg_type, "snapshot_data": jpg_data}}
        )
        assert editor.bcf.snapshot(project_id, topic["guid"], viewpoint["guid"]) == (PNG, "image/png")
        assert editor.bcf.snapshot(project_id, topic["guid"], second_viewpoint["guid"]) == (JPEG, "image/jpeg")
        selection = editor.bcf.selection(project_id, topic["guid"], viewpoint["guid"])
        assert [c["ifc_guid"] for c in selection["selection"]] == list(WALLS)
        coloring = editor.bcf.coloring(project_id, topic["guid"], viewpoint["guid"])
        assert [c["color"] for c in coloring["coloring"]] == ["FF0000", "0000FF"]
        assert (
            editor.bcf.visibility(project_id, topic["guid"], viewpoint["guid"])["visibility"]["default_visibility"]
            is False
        )
        assert len(editor.bcf.viewpoints(project_id, topic["guid"])) == 2

        comment = editor.bcf.create_comment(
            project_id,
            topic["guid"],
            {"comment": "GTIN 3 should be 1 on the first wall.", "viewpoint_guid": viewpoint["guid"]},
        )
        reply = editor.bcf.create_comment(project_id, topic["guid"], {"comment": "Agreed, fixing."})
        assert [c["guid"] for c in editor.bcf.comments(project_id, topic["guid"])] == [comment["guid"], reply["guid"]]
        other = editor.bcf.create_topic(project_id, {"title": "Check wall schedule"})
        assert editor.bcf.set_related_topics(project_id, topic["guid"], [other["guid"]]) == [
            {"related_topic_guid": other["guid"]}
        ]
        reference = editor.bcf.add_document_reference(
            project_id, topic["guid"], {"document_guid": version["document_id"], "description": "The model"}
        )
        assert editor.bcf.document_references(project_id, topic["guid"])[0]["guid"] == reference["guid"]
        files = editor.bcf.files_information(project_id)
        assert [f["file"]["filename"] for f in files] == ["three_walls_gtin_v2.ifc"]
        assert (
            editor.bcf.set_files(project_id, topic["guid"], [files[0]["file"]])[0]["reference"]
            == files[0]["file"]["reference"]
        )

        updated = editor.bcf.update_topic(
            project_id,
            topic["guid"],
            {"title": topic["title"], "topic_type": "Issue", "topic_status": "In progress", "labels": ["Reuse"]},
        )
        assert updated["topic_status"] == "In progress"
        events = editor.bcf.topic_events(project_id, topic["guid"])
        assert [e["date"] for e in events] == sorted(e["date"] for e in events), "events come in date order"
        assert events[0]["actions"][0]["type"] == "topic_created"
        last = {a["type"]: a.get("value") for a in events[-1]["actions"]}
        assert last == {
            "status_updated": "In progress",
            "label_removed": "Structural",
            "priority_removed": None,
            "assigned_to_removed": None,
        }
        comment_events = editor.bcf.comment_events(project_id, topic["guid"], comment["guid"])
        assert [a["type"] for a in comment_events[0]["actions"]] == [
            "comment_created",
            "comment_text_updated",
            "viewpoint_updated",
        ]
        assert len(editor.bcf.topic_events(project_id, filter="type eq 'topic_created'")) == 2

        # 4. Security, from the client's point of view.
        with signed_in(live, "outsider") as outsider:
            with pytest.raises(ApiError) as info:
                outsider.bcf.topic(project_id, topic["guid"])
            assert info.value.status_code == 404
            with pytest.raises(ApiError) as info:
                outsider.documents.download(version)
            assert info.value.status_code == 404
        with signed_in(live, "viewer") as viewer:
            with pytest.raises(ApiError) as info:
                viewer.bcf.create_topic(project_id, {"title": "viewers cannot"})
            assert info.value.status_code == 403
        tokens = editor.tokens
        assert tokens is not None and tokens.refresh_token
        rotated = editor.oauth.refresh(tokens)
        with pytest.raises(ApiError) as info:
            editor.oauth.refresh(tokens)  # the spent refresh token: the whole family is revoked
        assert info.value.status_code == 400
        editor.use_tokens(rotated)
        with pytest.raises(AuthError, match="revoked"):
            editor.foundation.current_user()  # 401, and the automatic refresh is refused: the family is gone
        with pytest.raises(AuthError):
            headless_authorize(editor.oauth, username="editor", password="wrong-password", redirect_uri=world.redirect)
        browser.close()
