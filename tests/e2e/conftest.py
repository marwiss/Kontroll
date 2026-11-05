# This file was generated with the assistance of an AI coding tool.
"""End-to-end tests: the client library against the real server (uvicorn thread, database in Docker)."""

from __future__ import annotations

import pytest

from tests.ui import conftest as ui

pytestmark = pytest.mark.e2e

graph_target = ui.graph_target
settings = ui.settings
clean_database = ui.clean_database
live_server = ui.live_server
