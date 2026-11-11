# This file was generated with the assistance of an AI coding tool.
"""Backup and restore round trip against the real database."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from opencde import backup
from opencde.accounts.roles import Role
from opencde.bcf.schemas import TopicPOST
from opencde.graph.graph import Graph
from opencde.seed import is_empty, wipe
from opencde.storage import LocalStorage, make_key
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.accounts.users import UserRepository
from opencde.store.bcf.topics import TopicRepository

pytestmark = pytest.mark.integration


async def test_backup_round_trip(graph: Graph, tmp_path: Path) -> None:
    users, projects, topics = UserRepository(graph), ProjectRepository(graph), TopicRepository(graph)
    storage = LocalStorage(tmp_path / "data")
    user = await users.create("backup.user", "a-long-and-strong-passphrase", is_admin=True)
    project = await projects.create("Backed up")
    await projects.set_member(project.project_id, user.id, Role.MANAGER)
    topic = await topics.create(
        project_id=project.project_id,
        author=user.username,
        body=TopicPOST(title="Keep me", labels=["Architecture"], topic_status="Open"),
    )
    key = make_key("bcf-documents", topic.guid)
    storage.write_bytes(key, b"document bytes")

    folder = tmp_path / "backups" / "first"
    manifest = await backup.export(graph, storage, folder)
    assert manifest.nodes >= 4 and manifest.relationships >= 3 and manifest.files == 1
    assert manifest.skipped_nodes == 0 and manifest.dialect == graph.dialect.name.value
    assert set(json.loads((folder / "manifest.json").read_text())["checksums"]) == {
        "nodes.jsonl.gz",
        "relationships.jsonl.gz",
        "storage.tar.gz",
    }
    with gzip.open(folder / "nodes.jsonl.gz", "rt") as handle:
        labels = {tuple(json.loads(line)["labels"]) for line in handle}
    assert ("Topic",) in labels and ("User",) in labels and ("Event",) in labels

    await wipe(graph)
    storage.delete(key)
    assert await is_empty(graph) and not storage.exists(key)

    restored = await backup.restore(graph, LocalStorage(tmp_path / "data"), folder)
    assert restored.nodes == manifest.nodes
    again = await topics.get(user_id=user.id, project_id=project.project_id, guid=topic.guid)
    assert again is not None and again.title == "Keep me" and again.labels == ["Architecture"]
    assert await users.project_role(user.id, project.project_id) is Role.MANAGER
    assert await users.authenticate("backup.user", "a-long-and-strong-passphrase") is not None
    assert storage.exists(key) and storage.open_read(key).read() == b"document bytes"
    row = await graph.one("MATCH (:Project)-[:HAS_EVENT]->(e:Event) RETURN count(e) AS n")
    assert row and row["n"] == 1, "relationships came back"

    (folder / "nodes.jsonl.gz").write_bytes(b"tampered")
    with pytest.raises(backup.BackupError, match="corrupt"):
        backup.read_manifest(folder)
