# This file was generated with the assistance of an AI coding tool.
"""A written file against the IFC standard. Skipped when IfcOpenShell is not installed."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from opencde.ifcgraph.validation import compare_issues, main
from tests.conftest import FIXTURES_DIR

ROOT = Path(__file__).resolve().parents[2]
MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"


def exchange(*statements: str) -> bytes:
    body = "\n".join(statements)
    return (
        "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [x]'),'2;1');\n"
        "FILE_NAME('t.ifc','2026-11-07T00:00:00',(''),(''),'','','');\n"
        f"FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n{body}\nENDSEC;\nEND-ISO-10303-21;\n"
    ).encode("ascii")


GOOD = (
    "#1=IFCPERSON($,'Family',$,$,$,$,$,$);",
    "#2=IFCORGANIZATION($,'Org',$,$,$);",
    "#3=IFCPERSONANDORGANIZATION(#1,#2,$);",
    "#4=IFCAPPLICATION(#2,'1','App','app');",
    "#5=IFCOWNERHISTORY(#3,#4,$,.NOCHANGE.,$,$,$,1);",
    "#6=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",
    "#7=IFCUNITASSIGNMENT((#6));",
    "#8=IFCPROJECT('2iFPi1Pg90_94gtQu544_Z',#5,'p',$,$,$,$,$,#7);",
    "#9=IFCWALL('0KhR8hr7H8eewFRKm6V1bJ',#5,'wall',$,$,$,$,$,.SOLIDWALL.);",
)


def issues(tmp_path: Path, statements: tuple[str, ...]) -> dict:
    path = tmp_path / "file.ifc"
    path.write_bytes(exchange(*statements))
    return run(path)


def run(path: Path, against: Path | None = None) -> dict:
    arguments = [sys.executable, "-m", "opencde.ifcgraph.validation", str(path)]
    if against is not None:
        arguments += ["--against", str(against)]
    done = subprocess.run(arguments, capture_output=True, text=True, timeout=300, check=False)  # noqa: S603 - this very interpreter
    assert done.returncode in (0, 1), done.stderr
    answer = json.loads(done.stdout)
    assert done.returncode == (1 if answer["new_count"] else 0)
    return answer


def replaced(old: str, new: str) -> tuple[str, ...]:
    assert any(old in line for line in GOOD), old
    return tuple(line.replace(old, new) for line in GOOD)


def test_the_extra_holds_what_the_validator_needs() -> None:
    """The EXPRESS rules import ``_pytest``, which IfcOpenShell does not declare. In the tests it is there anyway, which
    is why this looks at what a production install gets: the image is built with the extra and without the dev group."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra = project["project"]["optional-dependencies"]["ifcgraph"]
    assert any(requirement.startswith("pytest") for requirement in extra)
    assert '"--extra ifcgraph"' in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_counting_what_is_new() -> None:
    def issue(instance: int | None, message: str, attribute: str | None = None) -> dict:
        return {"kind": "schema", "instance": instance, "attribute": attribute, "message": message}

    both = issue(1, "already there")
    answer = compare_issues([both, issue(2, "new")], [both, issue(3, "fixed")])
    assert answer["issues"] == 2 and answer["new_count"] == 1 and answer["gone"] == 1
    assert answer["new"][0]["instance"] == 2
    same_rule_elsewhere = compare_issues([issue(2, "the rule")], [issue(1, "the rule")])
    assert same_rule_elsewhere["new_count"] == 1, "the same rule on another instance is another issue"
    layout = compare_issues(
        [issue(1, "Invalid enumeration:\n\n#1=IFCX(.A.,1.E-09);")],
        [issue(1, "Invalid enumeration:\n\n#1= IFCX(.A.,1.E-009);")],
    )
    assert layout["new_count"] == 0, "the line of the file as it is written is no part of an issue"


pytest.importorskip("ifcopenshell", reason="the ifcgraph extra is not installed")


def test_a_good_file_has_no_issues(tmp_path: Path) -> None:
    answer = issues(tmp_path, GOOD)
    assert answer["issues"] == 0, answer["new"]


@pytest.mark.parametrize(
    ("old", "new", "said"),
    [
        pytest.param(".SOLIDWALL.", ".NOSUCHWALL.", "NOSUCHWALL", id="an enumeration value the schema does not have"),
        pytest.param("'wall'", "5", "", id="a number where the schema has a string"),
        pytest.param("'0KhR8hr7H8eewFRKm6V1bJ'", "'not a GlobalId'", "GlobalId", id="a GlobalId of the wrong form"),
        pytest.param("'0KhR8hr7H8eewFRKm6V1bJ'", "$", "", id="an attribute that is not optional left out"),
        pytest.param("'0KhR8hr7H8eewFRKm6V1bJ'", "'2iFPi1Pg90_94gtQu544_Z'", "GlobalId", id="a GlobalId used twice"),
        pytest.param("(#6)", "()", "", id="an empty list where the schema wants one"),
        pytest.param("(#6)", "(#99)", "", id="a reference to nothing, which a deleted node leaves in a block"),
        pytest.param("#3,#4", "#4,#4", "", id="a reference to the wrong class"),
    ],
)
def test_what_breaks_the_standard_is_found(old: str, new: str, said: str, tmp_path: Path) -> None:
    answer = issues(tmp_path, replaced(old, new))
    assert answer["new_count"] > 0
    assert said in json.dumps(answer["new"])


def test_only_what_the_other_file_does_not_have_counts(tmp_path: Path) -> None:
    upload = tmp_path / "upload.ifc"
    upload.write_bytes(exchange(*replaced("'wall'", "5")))
    same_flaw = tmp_path / "same.ifc"
    same_flaw.write_bytes(exchange(*(line.replace("'wall'", "5") for line in GOOD)))
    assert run(same_flaw, upload)["new_count"] == 0

    another = tmp_path / "another.ifc"
    another.write_bytes(exchange(*(line.replace("'wall'", "5").replace("'p'", "6") for line in GOOD)))
    answer = run(another, upload)
    assert answer["issues"] > answer["new_count"] > 0

    fixed = tmp_path / "fixed.ifc"
    fixed.write_bytes(exchange(*GOOD))
    answer = run(fixed, upload)
    assert answer["new_count"] == 0 and answer["gone"] > 0


def test_a_file_that_differs_only_in_how_it_is_written_has_nothing_new(tmp_path: Path) -> None:
    """The parser's complaint quotes the line of the file, in layout and with the spelling of REALs as they stand."""
    flawed = "#9=IFCWALL('0KhR8hr7H8eewFRKm6V1bJ',#5,'wall',$,$,$,$,$,.NULLENUM.);"
    upload = tmp_path / "upload.ifc"
    upload.write_bytes(exchange(*GOOD[:-1], flawed.replace("=", "= ", 1)))
    written = tmp_path / "written.ifc"
    written.write_bytes(exchange(*GOOD[:-1], flawed))
    answer = run(written, upload)
    assert answer["issues"] > 0
    assert answer["new_count"] == 0, answer["new"]


def test_the_fixture_model_is_clean(tmp_path: Path) -> None:
    assert run(MODEL)["issues"] == 0


def test_the_process_says_when_it_can_say_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "missing.ifc")]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
