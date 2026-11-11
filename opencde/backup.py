# This file was generated with the assistance of an AI coding tool.
"""Backup and restore at the application level.

Neo4j Community can only dump a database that is stopped, and Memgraph has
its own snapshot format, so the server exports its own data: every node and
relationship as JSON lines (identified by the unique keys of the schema, never
by database-internal ids) plus a tar archive of the storage directory. The
result restores into either database. See ADR 0006.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencde import __version__
from opencde.graph.graph import Graph
from opencde.graph.schema import KEYED
from opencde.storage import CATEGORIES, LocalStorage
from opencde.timeutil import now_iso

FORMAT = 1
BATCH = 1000
MAX_BATCH_BYTES = 16 * 1024 * 1024
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KEY_PROPS = sorted({prop for _, prop in KEYED})
_KEY_PROJECTION = "{" + ", ".join(f".{prop}" for prop in _KEY_PROPS) + "}"


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class Manifest:
    created_at: str
    server_version: str
    dialect: str
    nodes: int
    relationships: int
    skipped_nodes: int
    files: int
    checksums: dict[str, str]

    def to_json(self) -> dict[str, Any]:
        return {"format": FORMAT, **self.__dict__}


def node_key(labels: list[str], props: dict[str, Any]) -> tuple[str, str, Any] | None:
    """``(label, property, value)`` identifying a node across databases, or None when it has no unique key."""
    for label, prop in KEYED:
        if label in labels and props.get(prop) is not None:
            return label, prop, props[prop]
    return None


def _safe(name: str) -> str:
    if not _NAME.match(name):
        raise BackupError(f"unsafe label or relationship type in backup: {name!r}")
    return name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------- export


async def _present_labels(graph: Graph) -> set[str]:
    rows = await graph.run("MATCH (n) UNWIND labels(n) AS label RETURN DISTINCT label")
    return {row["label"] for row in rows}


async def export(graph: Graph, storage: LocalStorage, target_dir: Path) -> Manifest:
    """Write ``nodes.jsonl.gz``, ``relationships.jsonl.gz``, ``storage.tar.gz`` and ``manifest.json``."""
    # A command-line operation: nothing else runs on this event loop, so blocking file work is fine here.
    target_dir.mkdir(parents=True, exist_ok=False)  # noqa: ASYNC240
    present = await _present_labels(graph)
    primary = [(label, prop) for label, prop in KEYED if label in present]
    covered = {label for label, _ in primary}
    nodes = relationships = skipped = 0
    seen: set[tuple[str, str, Any]] = set()

    with gzip.open(target_dir / "nodes.jsonl.gz", "wt", encoding="utf-8") as out:
        for label, prop in primary:
            skip = 0
            while True:
                rows = await graph.run(
                    f"MATCH (n:{_safe(label)}) WHERE n.{_safe(prop)} IS NOT NULL "
                    f"RETURN labels(n) AS labels, properties(n) AS props ORDER BY n.{_safe(prop)} SKIP $skip LIMIT $batch",
                    skip=skip,
                    batch=BATCH,
                )
                for row in rows:
                    key = node_key(row["labels"], row["props"])
                    if key is None or key in seen:
                        continue  # a node with two unique labels is exported once, under the first
                    seen.add(key)
                    out.write(json.dumps({"labels": sorted(row["labels"]), "props": row["props"]}) + "\n")
                    nodes += 1
                if len(rows) < BATCH:
                    break
                skip += BATCH
        uncovered = present - covered
        if uncovered:
            row = await graph.one(
                "MATCH (n) WHERE NOT any(label IN labels(n) WHERE label IN $covered) RETURN count(n) AS n",
                covered=sorted(covered),
            )
            skipped = int(row["n"]) if row else 0

    with gzip.open(target_dir / "relationships.jsonl.gz", "wt", encoding="utf-8") as out:
        for label, prop in primary:
            skip = 0
            while True:
                rows = await graph.run(
                    f"MATCH (a:{_safe(label)})-[r]->(b) WHERE a.{_safe(prop)} IS NOT NULL "
                    f"RETURN a.{_safe(prop)} AS a_key, type(r) AS type, properties(r) AS props, "
                    f"labels(b) AS b_labels, b {_KEY_PROJECTION} AS b_keys "
                    f"ORDER BY a.{_safe(prop)} SKIP $skip LIMIT $batch",
                    skip=skip,
                    batch=BATCH,
                )
                for row in rows:
                    b_key = node_key(row["b_labels"], row["b_keys"])
                    if b_key is None:
                        continue
                    a_key = (label, prop, row["a_key"])
                    if node_key([label], {prop: row["a_key"]}) != a_key:
                        continue  # the start node is exported under another label; it appears there
                    out.write(
                        json.dumps(
                            {
                                "a": [label, prop, row["a_key"]],
                                "type": row["type"],
                                "props": row["props"] or {},
                                "b": list(b_key),
                            }
                        )
                        + "\n"
                    )
                    relationships += 1
                if len(rows) < BATCH:
                    break
                skip += BATCH

    files = 0
    with tarfile.open(target_dir / "storage.tar.gz", "w:gz") as archive:
        for category in sorted(CATEGORIES):
            for key in storage.iter_keys(category):
                archive.add(storage.path(key), arcname=key)
                files += 1

    checksums = {
        name: _sha256(target_dir / name) for name in ("nodes.jsonl.gz", "relationships.jsonl.gz", "storage.tar.gz")
    }
    manifest = Manifest(
        created_at=now_iso(),
        server_version=__version__,
        dialect=graph.dialect.name.value,
        nodes=nodes,
        relationships=relationships,
        skipped_nodes=skipped,
        files=files,
        checksums=checksums,
    )
    (target_dir / "manifest.json").write_text(json.dumps(manifest.to_json(), indent=2), encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------------- restore


def read_manifest(source_dir: Path) -> Manifest:
    path = source_dir / "manifest.json"
    if not path.is_file():
        raise BackupError(f"{source_dir} holds no manifest.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise BackupError(f"unsupported backup format {data.get('format')!r}")
    for name, expected in data["checksums"].items():
        actual = _sha256(source_dir / name)
        if actual != expected:
            raise BackupError(f"{name} is corrupt (checksum mismatch)")
    data.pop("format")
    return Manifest(**data)


async def restore(graph: Graph, storage: LocalStorage, source_dir: Path) -> Manifest:
    """Load a backup into an empty database and storage; the caller wipes first when needed."""
    manifest = read_manifest(source_dir)

    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    pending_bytes = 0
    with gzip.open(source_dir / "nodes.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            labels = tuple(_safe(label) for label in record["labels"])
            groups.setdefault(labels, []).append(record["props"])
            pending_bytes += len(line)  # a block of an IFC model's geometry is a lot of text in one node
            if sum(len(rows) for rows in groups.values()) >= BATCH or pending_bytes >= MAX_BATCH_BYTES:
                await _create_nodes(graph, groups)
                groups = {}
                pending_bytes = 0
    await _create_nodes(graph, groups)

    rel_groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    with gzip.open(source_dir / "relationships.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            a_label, a_prop, a_value = record["a"]
            b_label, b_prop, b_value = record["b"]
            key = (_safe(a_label), _safe(a_prop), _safe(record["type"]), _safe(b_label), _safe(b_prop))
            rel_groups.setdefault(key, []).append({"a": a_value, "b": b_value, "props": record["props"]})
            if sum(len(rows) for rows in rel_groups.values()) >= BATCH:
                await _create_relationships(graph, rel_groups)
                rel_groups = {}
    await _create_relationships(graph, rel_groups)

    with tarfile.open(source_dir / "storage.tar.gz", "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not _is_storage_key(member.name):
                raise BackupError(f"unexpected entry in storage archive: {member.name!r}")
        archive.extractall(storage.root, filter="data")
    return manifest


def _is_storage_key(name: str) -> bool:
    category, _, filename = name.partition("/")
    return bool(category and filename and "/" not in filename and ".." not in filename and not filename.startswith("."))


async def _create_nodes(graph: Graph, groups: dict[tuple[str, ...], list[dict[str, Any]]]) -> None:
    for labels, rows in groups.items():
        label_clause = ":".join(labels)
        await graph.run(f"UNWIND $rows AS row CREATE (n:{label_clause}) SET n = row", rows=rows)


async def _create_relationships(
    graph: Graph, groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]]
) -> None:
    for (a_label, a_prop, rel_type, b_label, b_prop), rows in groups.items():
        await graph.run(
            f"UNWIND $rows AS row "
            f"MATCH (a:{a_label} {{{a_prop}: row.a}}), (b:{b_label} {{{b_prop}: row.b}}) "
            f"CREATE (a)-[r:{rel_type}]->(b) SET r = row.props",
            rows=rows,
        )
