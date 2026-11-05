# This file was generated with the assistance of an AI coding tool.
"""Pure helpers of the Documents API and the browser sign-in."""

from __future__ import annotations

import pytest
from jsonschema import ValidationError

from opencde.documents.links import part_ranges, version_links, with_query
from opencde.documents.schemas import CallbackLink, SelectDocuments
from opencde.web.dependencies import safe_next
from tests.conformance.schemas import validate_documents


def test_part_ranges_cover_the_file_exactly() -> None:
    assert part_ranges(10, 4) == [(0, 3), (4, 7), (8, 9)]
    assert part_ranges(8, 4) == [(0, 3), (4, 7)]
    assert part_ranges(1, 1024) == [(0, 0)]
    with pytest.raises(ValueError):
        part_ranges(0, 1024)


def test_with_query_appends_to_callbacks_with_and_without_a_query() -> None:
    assert (
        with_query("https://app.test/cb", {"user_cancelled_upload": "true"})
        == "https://app.test/cb?user_cancelled_upload=true"
    )
    assert (
        with_query("https://app.test/cb?x=1", {"selected_documents_url": "http://s/d?a=b"})
        == "https://app.test/cb?x=1&selected_documents_url=http%3A%2F%2Fs%2Fd%3Fa%3Db"
    )


def test_version_links_are_absolute_and_complete() -> None:
    links = version_links("https://cde.test/documents/1.0", "doc-1", 3)
    assert links.document_version.url == "https://cde.test/documents/1.0/documents/doc-1/versions/3"
    assert links.document_version_download.url.endswith("/versions/3/download")
    assert links.document_versions.url.endswith("/documents/doc-1/versions")
    assert links.document_details.url.endswith("/versions/3/details")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/documents/1.0/upload-ui/abc", "/documents/1.0/upload-ui/abc"),
        ("/a?b=c", "/a?b=c"),
        ("https://evil.test/", "/"),
        ("//evil.test/", "/"),
        ("/\\evil.test", "/"),
        ("/a\r\nSet-Cookie: x", "/"),
        ("", "/"),
        (None, "/"),
        ("/" + "a" * 3000, "/"),
    ],
)
def test_safe_next_only_accepts_local_paths(value: str | None, expected: str) -> None:
    assert safe_next(value) == expected


def test_callback_and_extensions_rules() -> None:
    CallbackLink(url="https://app.test/callback", expires_in=600)
    with pytest.raises(ValueError):
        CallbackLink(url="ftp://app.test/callback", expires_in=600)
    with pytest.raises(ValueError):
        CallbackLink(url="javascript:alert(1)", expires_in=600)
    assert SelectDocuments(
        callback={"url": "http://127.0.0.1:1/cb", "expires_in": 60}, supported_file_extensions=[".IFC", ".ifc", ".pdf"]
    ).supported_file_extensions == [".ifc", ".pdf"]
    with pytest.raises(ValueError):
        SelectDocuments(callback={"url": "http://127.0.0.1:1/cb", "expires_in": 60}, supported_file_extensions=["ifc"])


def test_documents_schema_validation_helper() -> None:
    version = {
        "links": {
            "document_version": {"url": "http://s/v"},
            "document_version_metadata": {"url": "http://s/m"},
            "document_version_download": {"url": "http://s/d"},
            "document_versions": {"url": "http://s/vs"},
            "document_details": {"url": "http://s/details"},
        },
        "version_number": "1",
        "version_index": 1,
        "creation_date": "2026-11-05T10:00:00.000Z",
        "title": "Walls",
        "file_description": {"name": "walls.ifc", "size_in_bytes": 12},
        "document_id": "abc",
    }
    validate_documents(version, "DocumentVersion")
    validate_documents({"server_context": None, "documents": [version]}, "SelectedDocuments")
    with pytest.raises(ValidationError):
        validate_documents({**version, "storage_key": "leak"}, "DocumentVersion")
    with pytest.raises(ValidationError):
        validate_documents({"documents": [{"title": "no links"}]}, "DocumentVersions")
