# This file was generated with the assistance of an AI coding tool.
"""The MCP endpoint's answers against the schema of revision 2026-07-28, as pinned in ``spec/mcp/`` (ADR 0028).

Every result and every error the endpoint gives at 2026-07-28 is validated against its definition in the official
JSON Schema. The database is stood in for (``tests/mcp_support.py``).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from tests.conftest import SPEC_DIR
from tests.mcp_support import META, MODERN, endpoint, headers, rpc

pytestmark = pytest.mark.conformance

SCHEMA = SPEC_DIR / "mcp" / MODERN / "schema.json"


@cache
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def conforms(instance: Any, definition: str) -> None:
    """``instance`` is what the schema's definition says it is; the errors name the paths that are not."""
    schema = _schema()
    validator = Draft202012Validator(
        {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"}
    )
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    assert not errors, f"{definition}: " + "; ".join(f"{list(e.absolute_path)}: {e.message}"[:300] for e in errors)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    with endpoint(tmp_path) as client:
        yield client


def test_the_pinned_schema_is_valid_json_schema_2020_12() -> None:
    Draft202012Validator.check_schema(_schema())
    assert "HeaderMismatchError" in _schema()["$defs"] and "DiscoverResultResponse" in _schema()["$defs"]


def test_the_discovery_conforms(client: TestClient) -> None:
    conforms(rpc(client, "server/discover").json(), "DiscoverResultResponse")


def test_the_list_of_tools_and_each_tool_conform(client: TestClient) -> None:
    body = rpc(client, "tools/list").json()
    conforms(body, "ListToolsResultResponse")
    for tool in body["result"]["tools"]:
        conforms(tool, "Tool")
        Draft202012Validator.check_schema(tool["inputSchema"])


def test_the_errors_conform(client: TestClient) -> None:
    mismatch = rpc(client, "tools/list", sent=headers("tools/call"))
    conforms(mismatch.json(), "HeaderMismatchError")
    meta = {**META, "io.modelcontextprotocol/protocolVersion": "2027-01-01"}
    unsupported = rpc(client, "tools/list", meta=meta, sent=headers("tools/list", version="2027-01-01"))
    conforms(unsupported.json(), "UnsupportedProtocolVersionError")
    for answer in (
        rpc(client, "resources/list"),
        rpc(client, "tools/call", {"name": "nothing"}),
        rpc(client, "tools/list", meta={}),
        client.post("/mcp", content=b"[]", headers=headers("tools/list") | {"Content-Type": "application/json"}),
        client.post("/mcp", content=b"{", headers=headers("tools/list") | {"Content-Type": "application/json"}),
    ):
        assert answer.status_code in (400, 404)
        conforms(answer.json(), "JSONRPCErrorResponse")
