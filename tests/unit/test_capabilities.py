# This file was generated with the assistance of an AI coding tool.
"""The capabilities document: shape, no secrets, settings reflected, and the administration API switch."""

from pathlib import Path

from fastapi.testclient import TestClient

from opencde.main import create_app
from tests.conftest import test_settings as make_settings


def test_capabilities_document_has_the_agreed_shape_and_no_secrets(client: TestClient) -> None:
    response = client.get("/.well-known/dataregium", headers={"Origin": "https://app.example"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["access-control-allow-origin"] == "*", "clients read it cross-origin"
    body = response.json()
    assert set(body) == {"server", "apis", "bcf_versions", "scopes", "extensions", "limits", "links"}
    assert body["server"]["name"] == "Dataregium OpenCDE server" and body["server"]["public_url"] == "http://testserver"
    assert body["apis"] == {"foundation": "1.0", "bcf": "3.0", "documents": "1.0"}
    assert body["bcf_versions"] == ["3.0", "2.1"]
    assert body["scopes"] == ["profile", "bcf", "documents", "project", "admin"]
    extensions = body["extensions"]
    assert set(extensions) == {
        "dynamic_client_registration",
        "request_log",
        "admin_api",
        "ifcgraph",
        "ifc_queries",
        "ifc_clash",
        "ifc_validation",
        "ifc_precheck",
        "project_administration",
        "publication",
        "headless_uploads",
        "ifc_diff",
        "ifc_geometry",
        "ifc_changes",
        "ifc_merge",
        "graph_query",
        "ai_policy",
        "mcp",
    }
    assert extensions["dynamic_client_registration"] == {
        "enabled": False,
        "public_clients": True,
        "initial_access_token": False,
        "approval": False,
        "unused_days": 30,
        "url": "/foundation/oauth2/reg",
    }
    assert extensions["request_log"] == {"enabled": False, "retention_hours": 72, "url": "/admin/api/requests"}
    assert extensions["admin_api"] == {"enabled": True, "version": 1, "url": "/admin/api", "scope": "admin"}
    assert extensions["ifcgraph"] == {"enabled": False, "bolt": None, "workcopy": False, "graph_store": "neo4j"}
    assert extensions["ifc_queries"] == {"enabled": False}, "the queries need the IFC-LPG module"
    assert extensions["ifc_clash"] == {"enabled": False}, "the clash check is off until configured"
    assert extensions["ifc_validation"] == {"enabled": False}, "the checks of an upload need the IFC-LPG module"
    assert extensions["ifc_precheck"] == {"enabled": False}, "the precheck needs the IFC-LPG module"
    assert extensions["ifc_diff"] == {"enabled": False}, "the diff needs the IFC-LPG module"
    assert extensions["ifc_geometry"] == {"enabled": False}, "the geometry needs the IFC-LPG module"
    assert extensions["ifc_changes"]["snippet_type"] == "DataregiumIfcChangeSet", "the form of a proposed change"
    assert extensions["ifc_changes"]["ifc_proposals_url"] == "/documents/1.0/documents/{document_id}/ifc-proposals"
    assert extensions["ifc_changes"]["ops_form"] == "dataspatium-tools/1", "the write tools' operations, too"
    assert extensions["ifc_changes"]["ops_tools"] == [
        "create_storeys_and_grid",
        "define_type",
        "create_wall",
        "create_slab",
        "create_roof",
        "create_opening",
        "create_element",
        "create_spaces",
        "set_properties",
        "set_classification",
        "assign",
        "edit_element",
        "transform_elements",
        "delete_elements",
        "set_site",
    ]
    assert extensions["project_administration"] == {
        "enabled": True,
        "url": "/manage/1.0/projects",
        "teams_url": "/manage/1.0/projects/{project_id}/teams",
        "scope": "project",
        "roles": ["viewer", "contributor", "editor", "manager"],
        "for": "managers of a project",
    }, "managers administer their projects (OB-41)"
    assert extensions["publication"] == {
        "enabled": True,
        "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/publication",
        "roles": ["manager"],
        "formats": ["ifczip", "zip"],
    }, "a manager publishes a version (F9 a)"
    assert extensions["ifc_merge"] == {"enabled": False}, "the merge needs the IFC-LPG module"
    assert extensions["graph_query"] == {"enabled": False}
    assert client.post("/admin/api/graph/query", json={"cypher": "RETURN 1"}).status_code == 404, "not mounted"
    assert extensions["mcp"] == {"enabled": False}, "the MCP endpoint is off until the operator turns it on"
    assert body["limits"]["access_token_ttl_seconds"] == 3600 and body["limits"]["max_upload_bytes"] > 0
    assert body["links"] == {"dataspatium": None}
    secret_like = ("test-password", "test-secret-key", "bolt://127.0.0.1:9", "secret", "password")
    assert not any(word in response.text for word in secret_like), "nothing from the configuration's secrets"


def test_the_former_path_answers_the_same_document(client: TestClient) -> None:
    current = client.get("/.well-known/dataregium")
    former = client.get("/.well-known/kontroll")
    assert former.status_code == 200 and former.json() == current.json()
    assert former.headers["cache-control"] == current.headers["cache-control"]


def test_capabilities_reflect_the_settings_and_the_admin_api_can_be_off(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        request_log_enabled=True,
        dynamic_client_registration=True,
        dataspatium_url="https://app.example/",
        graph_public_bolt_url="bolt://cde.example.org:7687",
        admin_api_enabled=False,
        graph_query_enabled=True,
    )
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        body = client.get("/.well-known/dataregium").json()
        assert body["extensions"]["request_log"]["enabled"] is True
        assert body["extensions"]["dynamic_client_registration"]["enabled"] is True
        assert body["extensions"]["admin_api"]["enabled"] is False
        assert body["extensions"]["graph_query"] == {"enabled": False}, "the graph query needs the admin API"
        assert body["extensions"]["ifcgraph"]["bolt"] == "bolt://cde.example.org:7687"
        assert body["links"]["dataspatium"] == "https://app.example/"
        assert client.get("/admin/api/requests").status_code == 404, "the API is not mounted"
        assert client.post("/admin/api/graph/query", json={"cypher": "RETURN 1"}).status_code == 404
        assert client.get("/admin/requests", follow_redirects=False).status_code == 302, "the page still is"


def test_the_graph_query_is_announced_with_its_limits_when_on(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, graph_query_enabled=True, graph_query_max_rows=50, graph_query_timeout_seconds=2.5
    )
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        body = client.get("/.well-known/dataregium").json()
        assert body["extensions"]["graph_query"] == {
            "enabled": True,
            "url": "/admin/api/graph/query",
            "max_rows": 50,
            "timeout_seconds": 2.5,
        }
        refused = client.post("/admin/api/graph/query", json={"cypher": "RETURN 1"})
        assert refused.status_code == 401 and refused.json()["code"] == "unauthenticated", "mounted, guarded"


def test_the_proposals_against_a_document_are_announced_beside_the_trial(client: TestClient) -> None:
    changes = client.get("/.well-known/dataregium").json()["extensions"]["ifc_changes"]
    assert changes["proposal_url"] == "/bcf/3.0/projects/{project_id}/topics/{topic_guid}/ifc-proposal"
    assert changes["approve_url"] == changes["proposal_url"] + "/approve"
    assert changes["ifc_proposals_url"] == "/documents/1.0/documents/{document_id}/ifc-proposals"
    refused = client.get(f"/documents/1.0/documents/{'0' * 32}/ifc-proposals")
    assert refused.status_code == 401 and refused.json()["code"] == "unauthenticated", "mounted, guarded"


def test_the_named_queries_are_announced_with_the_module(tmp_path: Path) -> None:
    from opencde.ifcgraph.queries import MAX_ROWS, QUERIES

    with TestClient(create_app(make_settings(tmp_path, ifcgraph_enabled=True), startup_wait_seconds=0)) as client:
        announced = client.get("/.well-known/dataregium").json()["extensions"]["ifc_queries"]
        assert announced == {
            "enabled": True,
            "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-queries",
            "names": [*QUERIES, "changed-since"],
            "max_rows": MAX_ROWS,
        }
        refused = client.get(f"/documents/1.0/documents/{'0' * 32}/versions/1/ifc-queries")
        assert refused.status_code == 401 and refused.json()["code"] == "unauthenticated", "mounted, guarded"
    with TestClient(create_app(make_settings(tmp_path, apis=["bcf-2.1"]), startup_wait_seconds=0)) as client:
        assert client.get("/.well-known/dataregium").json()["extensions"]["ifc_queries"] == {"enabled": False}


def test_the_checks_of_an_upload_are_announced_with_whether_bsdd_is_asked(tmp_path: Path) -> None:
    for enabled in (False, True):
        settings = make_settings(tmp_path, ifcgraph_enabled=True, bsdd_enabled=enabled)
        with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
            announced = client.get("/.well-known/dataregium").json()["extensions"]["ifc_validation"]
            assert announced == {
                "enabled": True,
                "url": "/documents/1.0/documents/{document_id}/versions/{version_index}/ifc-validation",
                "bsdd": enabled,
                "rooms": False,
            }, "bSDD is asked only when the operator turns it on (OB-42)"
    off = make_settings(tmp_path, ifcgraph_enabled=True, ifcgraph_validate_uploads=False, bsdd_enabled=True)
    with TestClient(create_app(off, startup_wait_seconds=0)) as client:
        assert client.get("/.well-known/dataregium").json()["extensions"]["ifc_validation"] == {"enabled": False}


def test_the_mcp_endpoint_is_announced_with_its_revisions_scopes_and_policy_when_on(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, mcp_enabled=True), startup_wait_seconds=0)) as client:
        announced = client.get("/.well-known/dataregium").json()["extensions"]["mcp"]
        assert announced == {
            "enabled": True,
            "url": "/mcp",
            "protocol_versions": ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26"],
            "scopes": ["mcp", "mcp:propose"],
            "default_ai_policy": "local",
            "ai_policy_url": "/documents/1.0/projects/{project_id}/ai-policy",
        }, "the newest revision first, and a project nobody has set is local (F30 a)"
        refused = client.get(announced["ai_policy_url"].format(project_id="0" * 32))
        assert refused.status_code == 401 and refused.json()["code"] == "unauthenticated", "mounted, guarded"
    settings = make_settings(tmp_path, mcp_enabled=True, apis=["bcf-2.1"])
    with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
        announced = client.get("/.well-known/dataregium").json()["extensions"]["mcp"]
        assert announced["ai_policy_url"] is None, "the policy is read through the Documents API"


def test_the_ai_policy_is_announced_whether_or_not_mcp_is_on(tmp_path: Path) -> None:
    """A client's own AI reads a project's policy too (F29 a), so its address does not wait for the MCP endpoint."""
    with TestClient(create_app(make_settings(tmp_path), startup_wait_seconds=0)) as client:
        announced = client.get("/.well-known/dataregium").json()["extensions"]["ai_policy"]
        assert announced == {
            "enabled": True,
            "url": "/documents/1.0/projects/{project_id}/ai-policy",
            "default": "local",
        }
    with TestClient(create_app(make_settings(tmp_path, apis=["bcf-2.1"]), startup_wait_seconds=0)) as client:
        assert client.get("/.well-known/dataregium").json()["extensions"]["ai_policy"] == {"enabled": False}


def test_the_rooms_are_announced_when_the_operator_turns_them_on(tmp_path: Path) -> None:
    """The rooms of each storey are off by default, and need the IFC-LPG module (F36 a)."""
    assert make_settings(tmp_path).rooms_enabled is False, "off until configured"
    for enabled in (False, True):
        settings = make_settings(tmp_path, ifcgraph_enabled=True, rooms_enabled=enabled)
        with TestClient(create_app(settings, startup_wait_seconds=0)) as client:
            assert client.get("/.well-known/dataregium").json()["extensions"]["ifc_validation"]["rooms"] is enabled
    module_off = make_settings(tmp_path, rooms_enabled=True)
    with TestClient(create_app(module_off, startup_wait_seconds=0)) as client:
        assert client.get("/.well-known/dataregium").json()["extensions"]["ifc_validation"] == {"enabled": False}
