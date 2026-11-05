# This file was generated with the assistance of an AI coding tool.
"""Python client for buildingSMART OpenCDE servers (Foundation API 1.0, BCF API 3.0, Documents API 1.0).

Typical use::

    from opencde_client import OpenCdeClient

    cde = OpenCdeClient("https://cde.example", client_id="my-app")
    cde.login()                         # opens the browser; PKCE authorization code flow
    for project in cde.bcf.projects():
        print(project["name"])

The library speaks the specifications as published by buildingSMART; it has no
knowledge of a particular server. ``httpx`` is the only dependency.
"""

from opencde_client.auth import OAuth2Client, TokenSet, generate_state, generate_verifier, pkce_challenge
from opencde_client.bcf import BcfClient
from opencde_client.client import OpenCdeClient
from opencde_client.documents import DocumentsClient
from opencde_client.errors import ApiError, AuthError, OpenCdeError
from opencde_client.foundation import ApiVersion, AuthInfo, FoundationClient, auth_info, discover
from opencde_client.http import ApiSession

__version__ = "2.2.0"

__all__ = [
    "ApiError",
    "ApiSession",
    "ApiVersion",
    "AuthError",
    "AuthInfo",
    "BcfClient",
    "DocumentsClient",
    "FoundationClient",
    "OAuth2Client",
    "OpenCdeClient",
    "OpenCdeError",
    "TokenSet",
    "__version__",
    "auth_info",
    "discover",
    "generate_state",
    "generate_verifier",
    "pkce_challenge",
]
