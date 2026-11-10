# This file was generated with the assistance of an AI coding tool.
"""The archive of a published version (F9 a): its names and its contents. The publication itself is proved against
a database in ``tests/integration/test_publication.py``."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from opencde.documents.routes_publication import archive_names, write_archive
from opencde.ids import new_id
from opencde.storage import LocalStorage, make_key


def test_an_ifc_file_becomes_an_ifczip_and_another_file_a_zip() -> None:
    assert archive_names("Building A.ifc") == ("Building A.ifc", "Building A.ifczip")
    assert archive_names("MODEL.IFC") == ("MODEL.IFC", "MODEL.ifczip")
    assert archive_names("drawing.pdf") == ("drawing.pdf", "drawing.pdf.zip")


def test_a_folder_or_a_drive_in_the_name_never_reaches_the_archive() -> None:
    assert archive_names("../../etc/model.ifc") == ("model.ifc", "model.ifczip")
    assert archive_names("C:" + chr(92) + "Temp" + chr(92) + "plan.ifc") == ("plan.ifc", "plan.ifczip")
    assert archive_names("") == ("document", "document.zip")


def test_the_archive_holds_the_file_and_its_hash_is_the_archives(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    source = make_key("documents", new_id())
    data = b"ISO-10303-21;" + bytes(range(256)) * 100
    storage.write_bytes(source, data)
    key = make_key("published", new_id(), "ifczip")
    size, sha256 = write_archive(storage, source, key, "model.ifc")
    stored = storage.path(key)
    assert size == stored.stat().st_size and sha256 == hashlib.sha256(stored.read_bytes()).hexdigest()
    with zipfile.ZipFile(stored) as archive:
        assert archive.namelist() == ["model.ifc"]
        assert archive.read("model.ifc") == data
        assert archive.getinfo("model.ifc").compress_type == zipfile.ZIP_DEFLATED
    assert not list(stored.parent.glob("*.tmp")), "nothing half written is left"
