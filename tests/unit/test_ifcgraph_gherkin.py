# This file was generated with the assistance of an AI coding tool.
"""Running buildingSMART's ifc-gherkin-rules (ADR 0012): the installer's guards, and reading what behave reports."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
from typing import Any

import pytest

from opencde.ifcgraph import gherkin, gherkin_install
from opencde.ifcgraph.gherkin_install import InstallError, _inside, fetch, unpack_rules
from tests.conftest import FIXTURES_DIR

MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@pytest.mark.parametrize("name", ["../evil.py", "/etc/passwd", "C:/Windows/evil.dll", "features/../../evil.py", ""])
def test_an_archive_member_cannot_leave_its_folder(tmp_path: Path, name: str) -> None:
    with pytest.raises(InstallError):
        _inside(tmp_path, name)


def test_an_archive_member_inside_its_folder_lands_there(tmp_path: Path) -> None:
    assert _inside(tmp_path, "features/steps/given.py") == tmp_path / "features" / "steps" / "given.py"


def tar_of(files: dict[str, bytes], links: tuple[str, ...] = ()) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        for name in links:
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)
    return buffer.getvalue()


def test_only_the_rules_are_kept_from_the_rule_sets_archive(tmp_path: Path) -> None:
    root = "ifc-gherkin-rules-893f827/"
    archive = tar_of(
        {
            root + "features/rules/GRP/GRP001_Acyclic-groups.feature": b"Feature: GRP001",
            root + "features/steps/validation_handling.py": b"",
            root + "behave.ini": b"[behave.formatters]",
            root + "LICENSE": b"MIT",
            root + "outcome_embedding_json_formatter.py": b"",
            root + "test/files/GRP/grp001/pass-grp001.ifc": b"ISO-10303-21;",
            root + "main.py": b"import subprocess",
            root + "requirements.txt": b"django==5.2.4",
        },
        links=(root + "features/escape",),
    )
    assert unpack_rules(archive, tmp_path) == 5
    kept = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())
    assert kept == [
        "LICENSE",
        "behave.ini",
        "features/rules/GRP/GRP001_Acyclic-groups.feature",
        "features/steps/validation_handling.py",
        "outcome_embedding_json_formatter.py",
    ]


class Response:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self, limit: int = -1) -> bytes:
        return self.data if limit < 0 else self.data[:limit]

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_an_artifact_is_refused_unless_it_is_the_pinned_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gherkin_install.urllib.request, "urlopen", lambda url, timeout: Response(b"tampered"))
    with pytest.raises(InstallError, match="not the pinned"):
        fetch("https://example.test/rules.tar.gz", hashlib.sha256(b"original").hexdigest())
    assert fetch("https://example.test/rules.tar.gz", hashlib.sha256(b"tampered").hexdigest()) == b"tampered"
    with pytest.raises(InstallError, match="https"):
        fetch("http://example.test/rules.tar.gz", "0" * 64)


def test_every_artifact_and_package_is_pinned_by_its_hash() -> None:
    pins = [gherkin_install.RULES, gherkin_install.DATACLASS_COMPAT, gherkin_install.MODELS_LICENSE]
    pins += list(gherkin_install.IFCOPENSHELL_BUILDS.values())
    assert all(url.startswith("https://") and SHA256.match(digest) for url, digest in pins)
    assert gherkin_install.RULES_COMMIT in gherkin_install.RULES[0]
    requirements = (Path(gherkin_install.__file__).parent / "gherkin-requirements.txt").read_text(encoding="utf-8")
    packages = re.findall(r"^([a-z0-9_.-]+)==", requirements, flags=re.MULTILINE)
    assert "behave" in packages and "django" not in packages and "sqlalchemy" not in packages
    for block in re.split(
        r"\n(?=[a-z])", requirements.split("\n", 1)[1] if requirements.startswith("#") else requirements
    ):
        if re.match(r"^[a-z0-9_.-]+==", block):
            assert "--hash=sha256:" in block, block.splitlines()[0]


def embedded(value: Any) -> list[dict[str, str]]:
    return [{"mime_type": "application/json", "data": base64.b64encode(json.dumps(value).encode()).decode()}]


def behave_report(outcomes: list[dict[str, Any]], caught: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": "IFC106 - Resource entities should be referenced by rooted entity",
            "tags": ["implementer-agreement"],
            "elements": [{"validation_outcomes": embedded(outcomes), "caught_exceptions": embedded(caught)}],
        },
        {
            "name": "GEM004 - Constraints on representation identifiers",
            "tags": [],
            "elements": [
                {
                    "validation_outcomes": embedded([]),
                    "caught_exceptions": embedded([{"error_type": "FileNotFoundError", "step": "s", "location": "x"}]),
                }
            ],
        },
    ]


def test_findings_and_rules_that_could_not_run_are_told_apart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"ruleset": "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6"})
    )
    outcomes = [
        {
            "inst": 242,
            "feature": "IFC106 - Resource entities should be referenced by rooted entity",
            "severity": "WARNING",
            "scenario": "Resource entities need to be referenced by rooted entity",
            "last_step": "it must be referenced by an entity instance inheriting from IfcRoot",
            "expected": "referenced",
            "observed": None,
        },
        {"inst": 5, "severity": "EXECUTED"},
        {"inst": None, "severity": "ERROR"},
    ]
    caught = [{"error_type": "NoneType", "step": "it must be referenced", "location": ""}]

    def run_rules(env: Path, path: Path, report: Path, timeout: float) -> None:
        report.write_text(json.dumps(behave_report(outcomes, caught)), encoding="utf-8")

    monkeypatch.setattr(gherkin, "run_rules", run_rules)
    monkeypatch.setattr(gherkin, "global_ids", lambda path, ids: {242: "1Xezbq735AdBO_4DerG66G"} if 242 in ids else {})
    answer = gherkin.report_of(MODEL, tmp_path, 60)
    assert answer["ruleset"] == "ifc-gherkin-rules 893f827 with IfcOpenShell 0.8.6"
    assert answer["issue_count"] == 2 and answer["error_count"] == 1 and answer["truncated"] is False
    first = answer["issues"][0]
    assert {key: first[key] for key in ("kind", "rule", "severity", "step_id", "global_id")} == {
        "kind": "gherkin",
        "rule": "IFC106",
        "severity": "warning",
        "step_id": 242,
        "global_id": "1Xezbq735AdBO_4DerG66G",
    }
    assert first["message"].startswith("IFC106 - Resource entities") and "Expected: " in first["message"]
    assert answer["issues"][1]["step_id"] is None and answer["issues"][1]["global_id"] is None
    assert answer["rules_not_run"] == [{"rule": "GEM004", "error": "FileNotFoundError"}], "a step that only failed"


def test_without_an_environment_the_rules_cannot_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert gherkin.main([str(MODEL), "--env", str(tmp_path)]) == 2
    assert "no environment" in json.loads(capsys.readouterr().err)["error"]


def test_the_rules_see_none_of_the_servers_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCDE_SECRET_KEY", "not for the rules")
    monkeypatch.setenv("OPENCDE_GRAPH_PASSWORD", "nor this")
    assert not [key for key in gherkin._clean_environment() if key.startswith("OPENCDE_")]


def test_the_global_id_of_a_rooted_instance_is_read_from_the_file() -> None:
    pytest.importorskip("ifcopenshell", reason="the ifcgraph extra is not installed")
    names = gherkin.global_ids(MODEL, {242, 32, 999_999})
    assert names == {242: "1Xezbq735AdBO_4DerG66G"}, "#32 is an owner history, #999999 is no instance"
