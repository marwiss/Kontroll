# This file was generated with the assistance of an AI coding tool.
"""URLs the Documents API hands out, and the arithmetic of upload parts."""

from __future__ import annotations

from urllib.parse import urlencode

from opencde.documents.schemas import DocumentVersionLinks, LinkData
from opencde.settings import Settings


def api_base(settings: Settings) -> str:
    return f"{settings.public_url}/documents/1.0"


def with_query(url: str, params: dict[str, str]) -> str:
    """Append query parameters to a URL that may already carry some (the client's callback)."""
    separator = "&" if "?" in url else "?"
    return url + separator + urlencode(params)


def version_links(base: str, document_id: str, version_index: int) -> DocumentVersionLinks:
    version_url = f"{base}/documents/{document_id}/versions/{version_index}"
    return DocumentVersionLinks(
        document_version=LinkData(url=version_url),
        document_version_metadata=LinkData(url=f"{version_url}/metadata"),
        document_version_download=LinkData(url=f"{version_url}/download"),
        document_versions=LinkData(url=f"{base}/documents/{document_id}/versions"),
        document_details=LinkData(url=f"{version_url}/details"),
    )


def validation_report_url(base: str, document_id: str, version_index: int) -> str:
    """Where the report of a version's check against the IFC schema is (an extension, ``routes_validation.py``)."""
    return f"{base}/documents/{document_id}/versions/{version_index}/ifc-validation"


def part_ranges(size: int, part_size: int) -> list[tuple[int, int]]:
    """Inclusive zero-based byte ranges covering ``size`` bytes in parts of at most ``part_size``."""
    if size <= 0 or part_size <= 0:
        raise ValueError("size and part size must be positive")
    return [(start, min(start + part_size, size) - 1) for start in range(0, size, part_size)]
