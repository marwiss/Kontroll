# This file was generated with the assistance of an AI coding tool.
"""A file through the records of a lossless conversion and back, without a database. Skipped without IfcOpenShell."""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from opencde.ifcgraph.step import StepFile, parse_statement, statement_text, statements_of, value_text
from opencde.ifcgraph.worker import main as worker_main
from tests.conftest import FIXTURES_DIR

pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

import ifcopenshell

from opencde.ifcgraph import lossless
from opencde.ifcgraph.convert import ConversionError, convert, convert_lossless
from opencde.ifcgraph.equivalence import compare
from opencde.ifcgraph.exporter import block_lines, node_line, write_merged
from opencde.ifcgraph.lossless import (
    ALL_ARGUMENTS,
    TAGGED,
    decode_block,
    decode_instance,
    encode_block,
    encode_instance,
)
from opencde.ifcgraph.schema import Schema, relationship_type
from opencde.ifcgraph.writer import main as writer_main
from opencde.ifcgraph.writer import write_records

MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"


def exchange(*statements: bytes | str, schema: str = "IFC4") -> bytes:
    body = b"\n".join(line if isinstance(line, bytes) else line.encode("latin-1") for line in statements)
    head = (
        "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [x]','Option [\\X2\\00E5\\X0\\]'),'2;1');\n"
        "FILE_NAME('t.ifc','2026-11-07T00:00:00',('A','B'),('O'),'pre','sys',$);\n"
        f"FILE_SCHEMA(('{schema}'));\nENDSEC;\nDATA;\n"
    ).encode("ascii")
    return head + body + b"\nENDSEC;\nEND-ISO-10303-21;\n"


def records_of(data: bytes, tmp_path: Path, *, include_geometry: bool = True) -> list[dict[str, Any]]:
    """What the worker writes, having been through JSON, as it is on the way to the database."""
    path = tmp_path / "source.ifc"
    path.write_bytes(data)
    return [json.loads(json.dumps(record)) for record in convert_lossless(path, include_geometry=include_geometry)]


def as_the_graph_holds_them(records: list[dict[str, Any]], out: Path) -> Path:
    """The records in the form the export reads out of the graph."""
    references: defaultdict[int, list[list[Any]]] = defaultdict(list)
    header = next(record for record in records if record["t"] == "h")
    for record in records:
        if record["t"] == "e" and "position" in record:
            references[record["a"]].append([relationship_type(record["type"]), record["position"], record["b"]])
    nodes = sorted((record for record in records if record["t"] == "n"), key=lambda record: record["step"])
    blocks = sorted((record for record in records if record["t"] == "g"), key=lambda record: record["first"])
    with out.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"schema": header["schema"], "ifc_header": header["ifc_header"]}) + "\n")
        write_merged(
            handle,
            [node_line(node["step"], node["props"], references[node["step"]]) for node in nodes],
            [line for block in blocks for line in block_lines(block["text"])],
        )
    return out


def there_and_back(data: bytes, tmp_path: Path, *, include_geometry: bool = True) -> bytes:
    records = records_of(data, tmp_path, include_geometry=include_geometry)
    instances = as_the_graph_holds_them(records, tmp_path / "instances.jsonl")
    written = tmp_path / "written.ifc"
    write_records(instances, written)
    return written.read_bytes()


def node_of(records: list[dict[str, Any]], step: int) -> dict[str, Any]:
    return next(record for record in records if record["t"] == "n" and record["step"] == step)


def references_of(records: list[dict[str, Any]], step: int) -> list[tuple[str, Any, int]]:
    return [
        (record["type"], record["position"], record["b"])
        for record in records
        if record["t"] == "e" and record["a"] == step and "position" in record
    ]


EVERY_KIND_OF_VALUE = (
    # the sign of a zero, and doubles at the edges of what a double can be
    "#1=IFCCOLOURRGB($,0.,-0.,0.30000000000000004);",
    "#2=IFCCARTESIANPOINT((5.E-324,1.7976931348623157E+308,-2.2250738585072014E-308));",
    "#3=IFCCARTESIANPOINT((0.1000000000000000055511151231257827,1.E+22,1.E-07));",
    # a REAL no double can hold, and an INTEGER no database can
    "#4=IFCCARTESIANPOINT((1.E+999,-1.E+999,0.));",
    "#5=IFCPROPERTYSINGLEVALUE('a',$,IFCINTEGER(9223372036854775807),$);",
    "#6=IFCPROPERTYSINGLEVALUE('b',$,IFCINTEGER(-9223372036854775808),$);",
    "#7=IFCPROPERTYSINGLEVALUE('c',$,IFCINTEGER(9223372036854775808),$);",
    # an INTEGER where the schema has a REAL, and the other way around
    "#8=IFCCARTESIANPOINT((1,2,3));",
    "#9=IFCCARTESIANPOINT((1,2.,3));",
    "#10=IFCSITE('0000000000000000000010',$,$,$,$,$,$,$,$,(1.,2,3),$,1,$,$);",
    # strings, in each escape and with what a database might not take
    "#11=IFCMATERIAL('\\X2\\00E5\\X0\\ \\S\\e \\X\\E5 \\PB\\\\S\\e \\X4\\0001F600\\X0\\ it''s \\\\ ;,()#1 $ *',$,$);",
    "#12=IFCMATERIAL('',$,$);",
    "#13=IFCMATERIAL('\\X\\00',$,$);",
    "#14=IFCMATERIAL('\\X2\\D83D\\X0\\',$,$);",
    "#15=IFCMATERIAL('C:\\Users\\x',$,$);",
    # enumerations and logicals, where the schema has them and where it does not
    "#16=IFCWALL('0000000000000000000016',$,$,$,$,$,$,$,.NULLENUM.);",
    "#17=IFCWALL('0000000000000000000017',$,$,$,$,$,$,$,'NOTDEFINED');",
    "#18=IFCMATERIAL(.NOTASTRING.,$,$);",
    "#19=IFCBSPLINESURFACE(1,1,((#2,#3),(#3,#2)),.UNSPECIFIED.,.T.,.F.,.U.);",
    "#20=IFCTRIMMEDCURVE($,(IFCPARAMETERVALUE(0.)),(IFCPARAMETERVALUE(1.)),.U.,.PARAMETER.);",
    # $ and * where they belong and where they do not, and an empty list
    "#21=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",
    "#22=IFCSIUNIT($,.LENGTHUNIT.,$,.METRE.);",
    "#23=IFCMATERIAL(*,$,$);",
    "#24=IFCPROPERTYSET('0000000000000000000024',$,$,$,());",
    "#25=IFCMATERIALPROPERTIES('n',$,($,$),#33);",
    # typed values, alone, with a list inside, with references inside, in a list, and in a SET with a reference
    "#26=IFCPROPERTYSINGLEVALUE('d',$,IFCLABEL('x'),$);",
    "#27=IFCPROPERTYSINGLEVALUE('e',$,IFCBOOLEAN(.T.),$);",
    "#28=IFCPROPERTYSINGLEVALUE('f',$,IFCLOGICAL(.U.),$);",
    "#29=IFCPROPERTYSINGLEVALUE('g',$,IFCCOMPOUNDPLANEANGLEMEASURE((1,2,3,4)),$);",
    "#30=IFCRELDEFINESBYPROPERTIES('0000000000000000000030',$,$,$,(#16,#17),IFCPROPERTYSETDEFINITIONSET((#24,#31)));",
    "#31=IFCPROPERTYSET('0000000000000000000031',$,$,$,(#26,#27,#26));",
    "#32=IFCPROPERTYLISTVALUE('h',$,(IFCLABEL('p'),IFCINTEGER(3),IFCREAL(1.5),IFCBOOLEAN(.F.)),$);",
    "#33=IFCMATERIAL('m',$,$);",
    "#34=IFCTRIMMEDCURVE(#35,(IFCPARAMETERVALUE(0.),#2),(#3,IFCPARAMETERVALUE(1.)),.T.,.PARAMETER.);",
    "#35=IFCLINE(#2,$);",
    "#36=IFCPROPERTYSINGLEVALUE('i',$,IFCNOSUCHTYPE('x'),$);",
    "#37=IFCPROPERTYSINGLEVALUE('j',$,'bare',$);",
    # lists in lists, of numbers, of references, and uneven ones
    "#38=IFCCARTESIANPOINTLIST3D(((0.,-0.,1.E-07),(1,2.5,3)));",
    "#39=IFCTRIANGULATEDFACESET(#38,$,$,((1,2,3),(3,2,1)),$);",
    "#40=IFCBSPLINESURFACE(1,1,((#2,#3,#2),(#3)),.UNSPECIFIED.,.T.,.F.,.U.);",
    "#41=IFCBSPLINESURFACE(1,1,((#2),()),.UNSPECIFIED.,.T.,.F.,.U.);",
    "#42=IFCBSPLINESURFACE(1,1,(#2,#3),.UNSPECIFIED.,.T.,.F.,.U.);",
    "#43=IFCPOLYLINE(((#2,#3)));",
    "#44=IFCPOLYLINE(#2);",
    "#45=IFCLINE((#2),$);",
    # order, repetition and a duplicate
    "#46=IFCPOLYLINE((#2,#3,#2,#2));",
    "#47=IFCCARTESIANPOINT((0.,0.,0.));",
    "#48=IFCCARTESIANPOINT((0.,0.,0.));",
    # references to nothing, to itself, and in a cycle
    "#49=IFCPOLYLINE((#2,#9999));",
    "#50=IFCLINE(#9999,$);",
    "#51=IFCPROPERTYSET('0000000000000000000051',$,$,$,(#9999));",
    "#52=IFCRELSPACEBOUNDARY2NDLEVEL('0000000000000000000052',$,$,$,$,$,$,.PHYSICAL.,.EXTERNAL.,$,#53);",
    "#53=IFCRELSPACEBOUNDARY2NDLEVEL('0000000000000000000053',$,$,$,$,$,$,.PHYSICAL.,.EXTERNAL.,$,#52);",
    "#54=IFCLOCALPLACEMENT(#54,$);",
    # binary
    "#55=IFCBLOBTEXTURE(.T.,.F.,$,$,$,'png',\"0FF\");",
    "#56=IFCBLOBTEXTURE(.T.,.F.,$,$,$,'png',\"15\");",
    "#57=IFCBLOBTEXTURE(.T.,.F.,$,$,$,'png',\"1A\");",
    '#58=IFCPIXELTEXTURE(.T.,.F.,$,$,$,2,1,1,("0FF","15"));',
    # classes the schema does not have, too few and too many attributes, and a complex instance
    "#59=IFCNOSUCHCLASS(1,'a',#2,(#3,$),IFCLABEL('x'));",
    "#60=IFCMATERIAL('too few');",
    "#61=IFCMATERIAL('too many',$,$,$,#2);",
    "#62=(IFCA(1,#2)IFCB('x'));",
    "#63=!USERDEFINED(1);",
    "#64=IFCDIRECTION((1.,0.,0.),$,$,$);",
    # a project whose owner history is no reference
    "#65=IFCPROJECT('0000000000000000000065',(1,2),$,$,$,$,$,$,$);",
)
RAW_BYTES = (b"#100=IFCMATERIAL('r\xc3\xa5 it''s \\X\\E5',$,$);", b"#101=IFCMATERIAL('\xe5',$,$);")
COMMENTS_AND_LAYOUT = (
    "/* before */ #200 = IFCDIRECTION ( ( 1. , /* inside; with a ' */ 0. ) ) ;",
    "#0201=IFCPOLYLINE((#200,#0200));",
)


BOTH_FORMS = pytest.mark.parametrize("as_nodes", [True, False], ids=["geometry as nodes", "geometry in blocks"])


@BOTH_FORMS
@pytest.mark.parametrize("statement", EVERY_KIND_OF_VALUE, ids=lambda statement: statement.split("=")[0])
def test_every_kind_of_value_comes_back(statement: str, as_nodes: bool, tmp_path: Path) -> None:
    # Whatever the statement refers to is here, so that it is the statement that is being tested.
    others = [line for line in EVERY_KIND_OF_VALUE if line != statement]
    data = exchange(statement, *others)
    comparison = compare(data, there_and_back(data, tmp_path, include_geometry=as_nodes))
    assert comparison.identical, comparison.checks


@BOTH_FORMS
def test_all_of_them_together_come_back_and_stay_as_they_are(as_nodes: bool, tmp_path: Path) -> None:
    data = exchange(*EVERY_KIND_OF_VALUE, *RAW_BYTES, *COMMENTS_AND_LAYOUT)
    once = there_and_back(data, tmp_path, include_geometry=as_nodes)
    comparison = compare(data, once)
    assert comparison.identical, comparison.checks
    assert there_and_back(once, tmp_path, include_geometry=as_nodes) == once, "a second round changes not one byte"


@BOTH_FORMS
def test_the_same_goes_for_a_real_model_and_its_geometry(as_nodes: bool, tmp_path: Path) -> None:
    from opencde.ifcgraph.equivalence import compare_files

    written = tmp_path / "out.ifc"
    written.write_bytes(there_and_back(MODEL.read_bytes(), tmp_path, include_geometry=as_nodes))
    comparison = compare_files(MODEL, written, geometry=True)
    assert comparison.identical, comparison.checks
    assert comparison.passed("geometry") is True


@BOTH_FORMS
def test_ifcopenshell_reads_the_written_file_as_it_reads_the_original(as_nodes: bool, tmp_path: Path) -> None:
    """A second opinion that shares nothing with this project's reader."""
    original = MODEL.read_bytes()
    written = there_and_back(original, tmp_path, include_geometry=as_nodes)
    ours = ifcopenshell.file.from_string(original.decode("ascii"))
    theirs = ifcopenshell.file.from_string(written.decode("ascii"))
    assert ours.to_string() == theirs.to_string()


def test_geometry_in_blocks_leaves_the_nodes_of_the_ordinary_form(tmp_path: Path) -> None:
    """The same nodes, the same relationships and the same values, with all the rest in the blocks."""
    records = records_of(MODEL.read_bytes(), tmp_path, include_geometry=False)
    header = next(record for record in records if record["t"] == "h")
    nodes = {record["step"]: record for record in records if record["t"] == "n"}
    ordinary = list(convert(MODEL))
    ordinary_nodes = {record["step"]: record for record in ordinary if record["t"] == "n"}
    assert nodes.keys() == ordinary_nodes.keys()
    assert not any("IfcCartesianPoint" in record["labels"] for record in nodes.values())
    for step, record in ordinary_nodes.items():
        assert nodes[step]["labels"] == record["labels"]
        for name, value in record["props"].items():
            assert nodes[step]["props"].get(name) == value, (step, name)
    ordinary_edges = {(record["a"], record["type"], record["b"]) for record in ordinary if record["t"] == "e"}
    edges = {(record["a"], record["type"], record["b"]) for record in records if record["t"] == "e"}
    assert edges == ordinary_edges

    blocks = [record for record in records if record["t"] == "g"]
    held = [step for block in blocks for step, _line in statements_in(block)]
    assert sum(block["instances"] for block in blocks) == len(held) == header["skipped"]
    assert held == sorted(held), "in order of id, so that a run of them can be merged with the nodes"
    assert not set(held) & nodes.keys(), "exactly once"
    assert len(held) + len(nodes) == 248


def statements_in(block: dict[str, Any]) -> list[tuple[int, bytes]]:
    return list(statements_of(decode_block(block["text"])))


def test_a_reference_into_a_block_is_kept_as_an_id(tmp_path: Path) -> None:
    records = records_of(MODEL.read_bytes(), tmp_path, include_geometry=False)
    wall = next(record for record in records if record["t"] == "n" and "IfcWall" in record["labels"])
    assert isinstance(wall["props"]["Representation__step"], int)
    assert isinstance(wall["props"]["ObjectPlacement__step"], int)
    assert "Representation" not in wall["props"] and "Representation__type" not in wall["props"]


@pytest.mark.parametrize(
    ("statements", "attribute", "ids"),
    [
        pytest.param(("#1=IFCLINE(#9,$);",), "Pnt", 9, id="one reference to nothing"),
        pytest.param(("#1=IFCPOLYLINE((#8,#9));",), "Points", [8, 9], id="a list of them"),
    ],
)
def test_a_reference_to_what_is_no_node_is_a_plain_id(
    statements: tuple[str, ...], attribute: str, ids: Any, tmp_path: Path
) -> None:
    data = exchange(*statements)
    properties = node_of(records_of(data, tmp_path), 1)["props"]
    assert properties[attribute + "__step"] == ids
    assert attribute not in properties
    assert compare(data, there_and_back(data, tmp_path)).identical


def test_a_list_of_references_keeps_the_ones_that_are_nodes_as_relationships(tmp_path: Path) -> None:
    data = exchange("#1=IFCPOLYLINE((#2,#9,#2));", "#2=IFCDIRECTION((1.,0.));")
    records = records_of(data, tmp_path)
    properties = node_of(records, 1)["props"]
    assert "Points__step" not in properties
    assert json.loads(properties["Points"]) == [{"r": 0}, {"d": 9}, {"r": 1}]
    assert references_of(records, 1) == [("Points", 0, 2), ("Points", 1, 2)]
    assert compare(data, there_and_back(data, tmp_path)).identical


@BOTH_FORMS
def test_an_owner_history_is_linked_from_its_project_alone(as_nodes: bool, tmp_path: Path) -> None:
    """Every root shares it, and an edge from each would make it the centre of the graph."""
    records = records_of(MODEL.read_bytes(), tmp_path, include_geometry=as_nodes)
    edges = [record for record in records if record["t"] == "e" and record["type"] == "OwnerHistory"]
    project = next(record for record in records if record["t"] == "n" and "IfcProject" in record["labels"])
    assert [edge["a"] for edge in edges] == [project["step"]]
    wall = next(record for record in records if record["t"] == "n" and "IfcWall" in record["labels"])
    assert wall["props"]["OwnerHistory__step"] == edges[0]["b"]


def test_many_instances_make_many_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("opencde.ifcgraph.convert.BLOCK_BYTES", 2000)
    statements = [f"#{step}=IFCCARTESIANPOINT(({step}.5,0.,-0.));" for step in range(1, 1001)]
    data = exchange(*reversed(statements))
    records = records_of(data, tmp_path, include_geometry=False)
    blocks = [record for record in records if record["t"] == "g"]
    assert len(blocks) > 5
    assert all(block["instances"] > 10 for block in blocks), "a block fills up before the next one starts"
    assert [block["first"] for block in blocks] == sorted(block["first"] for block in blocks)
    assert [step for block in blocks for step, _line in statements_in(block)] == list(range(1, 1001))
    written = there_and_back(data, tmp_path, include_geometry=False)
    assert compare(data, written).identical
    assert StepFile(written).ids() == list(range(1, 1001))


def test_an_owner_history_is_a_node_only_for_the_project() -> None:
    """As in the ordinary form, which keeps only the project's."""
    path_statements = (
        "#1=IFCOWNERHISTORY($,$,$,.NOCHANGE.,$,$,$,1);",
        "#2=IFCOWNERHISTORY($,$,$,.ADDED.,$,$,$,2);",
        "#3=IFCPROJECT('0000000000000000000003',#1,$,$,$,$,$,$,$);",
        "#4=IFCWALL('0000000000000000000004',#1,$,$,$,$,$,$,$);",
        "#5=IFCWALL('0000000000000000000005',#2,$,$,$,$,$,$,$);",
    )
    records = list(convert_lossless_of(exchange(*path_statements)))
    assert {record["step"] for record in records if record["t"] == "n"} == {1, 3, 4, 5}
    edges = [(record["a"], record["type"], record["b"]) for record in records if record["t"] == "e"]
    assert edges == [(3, "OwnerHistory", 1)]
    walls = {record["step"]: record["props"] for record in records if record["t"] == "n"}
    assert walls[4]["OwnerHistory__step"] == 1
    assert walls[5]["OwnerHistory__step"] == 2
    block = next(record for record in records if record["t"] == "g")
    assert [step for step, _line in statements_in(block)] == [2]


def convert_lossless_of(data: bytes) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "source.ifc"
        path.write_bytes(data)
        return list(convert_lossless(path))


def test_a_block_compresses(tmp_path: Path) -> None:
    lines = b"".join(b"#%d=IFCCARTESIANPOINT((0.,0.,0.));\n" % step for step in range(1, 5000))
    text = encode_block(lines)
    assert decode_block(text) == lines
    assert len(text) < len(lines) / 4
    assert text.isascii(), "a string both databases store the same way"


def test_lines_are_merged_in_order_of_id(tmp_path: Path) -> None:
    out = StringIO()
    nodes = [node_line(2, {"a": 1}, []), node_line(10, {"b": 2}, [])]
    block = list(block_lines(encode_block(b"#1=IFCX(1);\n#3=IFCY('r\xc3\xa5\nline');\n#11=IFCZ(1);\n")))
    write_merged(out, nodes, block)
    steps = [json.loads(line)["step"] for line in out.getvalue().splitlines()]
    assert steps == [1, 2, 3, 10, 11], "a raw line break in a string does not split an instance"
    assert json.loads(out.getvalue().splitlines()[2])["line"].encode("latin-1") == b"#3=IFCY('r\xc3\xa5\nline');"


def test_what_ifcopenshell_would_change_is_carried_through(tmp_path: Path) -> None:
    """These are the reason the conversion reads files itself. Each is checked against IfcOpenShell too, so that this
    test says when a new version stops changing them, and the reason goes away."""
    for statement in (
        "#1=IFCWALL('0000000000000000000016',$,$,$,$,$,$,$,.NULLENUM.);",
        "#1=IFCMATERIALPROPERTIES('n',$,($,$),$);",
        "#1=IFCBLOBTEXTURE(.T.,.F.,$,$,$,'png',\"15\");",
    ):
        data = exchange(statement)
        through_ifcopenshell = ifcopenshell.file.from_string(data.decode("ascii")).to_string().encode("ascii")
        assert not compare(data, through_ifcopenshell).same_model, statement
        assert compare(data, there_and_back(data, tmp_path)).identical, statement


def test_a_value_goes_where_a_query_looks_for_it(tmp_path: Path) -> None:
    records = records_of(
        exchange(
            "#1=IFCPROPERTYSINGLEVALUE('a',$,IFCLABEL('3'),$);",
            "#2=IFCCARTESIANPOINT((1.,2.,3.));",
            "#3=IFCPOLYLINE((#2,#2));",
            "#4=IFCWALL('0000000000000000000004',$,'Wall',$,$,$,$,$,.SOLIDWALL.);",
            "#5=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);",
            "#6=IFCCARTESIANPOINTLIST3D(((0.,1.),(2.,3.)));",
            "#7=IFCBSPLINESURFACE(1,1,((#2,#2),(#2)),.UNSPECIFIED.,.T.,.F.,.U.);",
            "#8=IFCRELDEFINESBYPROPERTIES('0000000000000000000008',$,$,$,(#4),IFCPROPERTYSETDEFINITIONSET((#9)));",
            "#9=IFCPROPERTYSET('0000000000000000000009',$,$,$,());",
            "#10=IFCPROPERTYLISTVALUE('b',$,(IFCLABEL('p'),IFCREAL(1.5)),$);",
            "#11=IFCTRIMMEDCURVE($,(IFCPARAMETERVALUE(0.),#2),$,.T.,.PARAMETER.);",
        ),
        tmp_path,
    )
    assert node_of(records, 1)["props"] == {
        "ifc_class": "IfcPropertySingleValue",
        "Name": "a",
        "NominalValue": "3",
        "NominalValue__type": "IFCLABEL",
    }
    assert node_of(records, 2)["props"]["Coordinates"] == [1.0, 2.0, 3.0]
    assert references_of(records, 3) == [("Points", 0, 2), ("Points", 1, 2)]
    wall = node_of(records, 4)
    assert wall["props"]["PredefinedType"] == "SOLIDWALL" and wall["props"]["Name"] == "Wall"
    assert "Description" not in wall["props"], "what the file leaves out is left out"
    assert {"IfcWall", "IfcProduct", "IfcRoot"} <= set(wall["labels"])
    assert node_of(records, 5)["props"] == {
        "ifc_class": "IfcSIUnit",
        "UnitType": "LENGTHUNIT",
        "Prefix": "MILLI",
        "Name": "METRE",
    }
    assert json.loads(node_of(records, 6)["props"]["CoordList"]) == [[0.0, 1.0], [2.0, 3.0]]
    assert references_of(records, 7) == [
        ("ControlPointsList", [0, 0], 2),
        ("ControlPointsList", [0, 1], 2),
        ("ControlPointsList", [1, 0], 2),
    ]
    relation = node_of(records, 8)
    assert relation["props"]["RelatingPropertyDefinition__type"] == "IFCPROPERTYSETDEFINITIONSET"
    assert ("RelatingPropertyDefinition", 0, 9) in references_of(records, 8)
    assert node_of(records, 9)["props"]["HasProperties"] == []
    listed = node_of(records, 10)["props"]
    assert listed["ListValues__type"] == TAGGED
    assert json.loads(listed["ListValues"]) == [{"t": "IFCLABEL", "v": ["p"]}, {"t": "IFCREAL", "v": [1.5]}]
    trimmed = node_of(records, 11)["props"]
    assert json.loads(trimmed["Trim1"]) == [{"t": "IFCPARAMETERVALUE", "v": [0.0]}, {"r": 0}]
    assert ("Trim1", 0, 2) in references_of(records, 11), "a reference in tagged JSON is still a relationship"


@pytest.mark.parametrize(
    ("statement", "attribute", "value"),
    [
        ("#1=IFCBLOBTEXTURE(.T.,.F.,$,$,$,'png',\"0FF\");", "RasterCode", "0FF"),
        ("#1=IFCBLOBTEXTURE(.T.,.F.,$,$,$,'png',\"0FF\");", "RepeatS", True),
        ("#1=IFCBLOBTEXTURE(.T.,.F.,$,$,$,'png',\"0FF\");", "RepeatT", False),
        ("#1=IFCBSPLINESURFACE(1,1,$,.UNSPECIFIED.,.T.,.F.,.U.);", "SelfIntersect", "UNKNOWN"),
        ("#1=IFCBSPLINESURFACE(1,1,$,.UNSPECIFIED.,.T.,.F.,.U.);", "UClosed", True),
        ("#1=IFCBSPLINESURFACE(1,1,$,.UNSPECIFIED.,.T.,.F.,.U.);", "SurfaceForm", "UNSPECIFIED"),
        ("#1=IFCPROPERTYSINGLEVALUE('a',$,IFCINTEGER(9223372036854775807),$);", "NominalValue", 9223372036854775807),
        ("#1=IFCCARTESIANPOINT((1,2,3));", "Coordinates", [1, 2, 3]),
        ("#1=IFCSITE('g',$,$,$,$,$,$,$,$,(1,2,3,4),$,$,$,$);", "RefLatitude", [1, 2, 3, 4]),
    ],
)
def test_a_plain_value_stays_plain(statement: str, attribute: str, value: Any, tmp_path: Path) -> None:
    properties = node_of(records_of(exchange(statement), tmp_path), 1)["props"]
    assert properties[attribute] == value
    assert type(properties[attribute]) is type(value)
    assert properties.get(attribute + "__type") != TAGGED


@pytest.mark.parametrize(
    ("statement", "attribute"),
    [
        ("#1=IFCCARTESIANPOINT((1.E+999,0.,0.));", "Coordinates"),
        ("#1=IFCCARTESIANPOINT((1,2.,3));", "Coordinates"),
        ("#1=IFCCOLOURRGB($,1.E+999,0.,0.);", "Red"),
        ("#1=IFCPROPERTYSINGLEVALUE('a',$,IFCINTEGER(9223372036854775808),$);", "NominalValue"),
        ("#1=IFCMATERIAL('\\X\\00',$,$);", "Name"),
        ("#1=IFCMATERIAL('\\X2\\D83D\\X0\\',$,$);", "Name"),
        ("#1=IFCMATERIAL('r\xc3\xa5',$,$);", "Name"),
        ("#1=IFCMATERIAL(.NOTASTRING.,$,$);", "Name"),
        ("#1=IFCWALL('g',$,$,$,$,$,$,$,'NOTDEFINED');", "PredefinedType"),
        ("#1=IFCMATERIAL(*,$,$);", "Name"),
        ("#1=IFCSIUNIT($,.LENGTHUNIT.,$,.METRE.);", "Dimensions"),
        ("#1=IFCPOLYLINE(#1);", "Points"),
        ("#1=IFCLINE((#1),$);", "Pnt"),
        ("#1=IFCPOLYLINE((#1,#9));", "Points"),
    ],
)
def test_what_has_no_plain_form_is_tagged(statement: str, attribute: str, tmp_path: Path) -> None:
    data = exchange(statement.encode("latin-1"))
    properties = node_of(records_of(data, tmp_path), 1)["props"]
    assert properties[attribute + "__type"] == TAGGED
    json.loads(properties[attribute])
    assert compare(data, there_and_back(data, tmp_path)).identical


def test_a_form_that_does_not_give_back_the_value_is_not_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Whatever is wrong with the plain form, tagged JSON gives the value back, and this is what makes that so."""
    data = exchange("#1=IFCMATERIAL('a',$,$);", "#2=IFCCARTESIANPOINT((1.,2.,3.));")
    monkeypatch.setattr(lossless, "_natural_atom", lambda _atom, _leaf: 1.5)
    assert compare(data, there_and_back(data, tmp_path)).identical
    assert node_of(records_of(data, tmp_path), 1)["props"]["Name__type"] == TAGGED


def test_what_the_schema_does_not_know_is_kept_whole_and_gets_no_label(tmp_path: Path) -> None:
    records = records_of(
        exchange("#1=IFCNOSUCHCLASS(1,#2);", "#2=IFCMATERIAL('too few');", "#3=(IFCA(1)IFCB(2));"), tmp_path
    )
    unknown = node_of(records, 1)
    assert unknown["labels"] == []
    assert unknown["props"]["ifc_class"] == "IFCNOSUCHCLASS"
    assert ALL_ARGUMENTS in unknown["props"]
    assert references_of(records, 1) == [("ARGUMENT", 0, 2)]
    too_few = node_of(records, 2)
    assert "IfcMaterial" in too_few["labels"] and ALL_ARGUMENTS in too_few["props"]
    complex_instance = node_of(records, 3)
    assert complex_instance["labels"] == [] and complex_instance["props"]["ifc_class"] == "(IFCA IFCB)"


def test_a_lossless_graph_answers_the_queries_of_the_ordinary_one() -> None:
    """Same properties and same inverse relationships, so that nothing written for one breaks on the other."""
    ordinary = list(convert(MODEL, include_geometry=True))
    lossless = list(convert_lossless(MODEL, include_geometry=True))
    ours = {record["step"]: record for record in lossless if record["t"] == "n"}
    for record in ordinary:
        if record["t"] != "n":
            continue
        node = ours[record["step"]]
        assert node["labels"] == record["labels"]
        for name, value in record["props"].items():
            assert node["props"].get(name) == value, (record["step"], name)
    forward = {(record["a"], record["type"], record["b"]) for record in lossless if record["t"] == "e"}
    missing = [
        edge
        for edge in ((record["a"], record["type"], record["b"]) for record in ordinary if record["t"] == "e")
        if edge not in forward
    ]
    assert not missing
    inverse = {
        (record["a"], record["type"], record["b"])
        for record in lossless
        if record["t"] == "e" and "position" not in record
    }
    assert inverse, "the inverse relationships are there"
    ordinary_edges = {(record["a"], record["type"], record["b"]) for record in ordinary if record["t"] == "e"}
    assert inverse <= ordinary_edges, "and no others than IfcOpenShell gives"


def test_the_summary_says_what_the_conversion_did(tmp_path: Path) -> None:
    records = records_of(MODEL.read_bytes(), tmp_path)
    header = next(record for record in records if record["t"] == "h")
    nodes = [record for record in records if record["t"] == "n"]
    edges = [record for record in records if record["t"] == "e"]
    assert header["lossless"] is True and header["schema"] == "IFC2X3"
    assert header["entities"] == 248 == len(nodes)
    assert header["relationships"] == len(edges)
    assert header["skipped"] == 0
    assert header["ifc_project_guid"] == "1CGyzxdzHaJybf9L4wHy3R"
    assert sum(header["classes"].values()) == 248 and header["classes"]["IfcWallStandardCase"] == 3
    assert records[-1]["t"] == "e" and nodes[-1] is not records[-1], "nodes before the header, edges after it"
    assert records.index(header) == len(nodes)


def test_the_graph_is_what_gets_written_not_a_copy_of_the_file() -> None:
    """What is changed in a node or a relationship shows up in the file, and what a node has picked up does not."""
    schema = Schema("IFC4")
    keyword, parameters = parse_statement(b"IFCPOLYLINE((#2,#3))")
    known = {2, 3, 4}
    properties, references = encode_instance(keyword, parameters, schema, known)
    assert properties == {} and references == [("Points", 0, 2), ("Points", 1, 3)]
    as_read = [(relationship_type(name), position, target) for name, position, target in references]
    assert statement_text(keyword, decode_instance(keyword, properties, as_read, schema)) == b"IFCPOLYLINE((#2,#3))"
    moved = [("POINTS", 1, 2), ("POINTS", 0, 4)]
    assert statement_text(keyword, decode_instance(keyword, {}, moved, schema)) == b"IFCPOLYLINE((#4,#2))"

    keyword, parameters = parse_statement(b"IFCMATERIAL('a',$,$)")
    properties, references = encode_instance(keyword, parameters, schema, known)
    edited = {**properties, "Name": "b", "Category": "c"}
    assert statement_text(keyword, decode_instance(keyword, edited, [], schema)) == b"IFCMATERIAL('b',$,'c')"
    picked_up = {
        **properties,
        "id": "m:1",
        "model_id": "m",
        "step_id": 1,
        "ifc_class": "IfcMaterial",
        "gtin": "123",
        "HasRepresentation": "an inverse attribute's name",
    }
    other_relationships = [("SAME_AS", 0, 2), ("HAS_REPRESENTATION", 0, 3)]
    assert statement_text(keyword, decode_instance(keyword, picked_up, other_relationships, schema)) == (
        b"IFCMATERIAL('a',$,$)"
    )


def test_a_node_that_lost_its_class_is_refused_rather_than_written_wrong() -> None:
    with pytest.raises(ValueError, match="no class of the schema"):
        decode_instance(b"IFCNOSUCHCLASS", {}, [], Schema("IFC4"))
    with pytest.raises(ValueError, match="no type of the schema"):
        decode_instance(b"IFCMATERIAL", {"Name": "a", "Name__type": "IFCNOSUCHTYPE"}, [], Schema("IFC4"))


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (b"r" + (1.0).hex().encode(), b"1."),
        (b"r" + (100.0).hex().encode(), b"100."),
        (b"r" + (0.0).hex().encode(), b"0."),
        (b"r" + (-0.0).hex().encode(), b"-0."),
        (b"r" + (0.1).hex().encode(), b"0.1"),
        (b"r" + (1e22).hex().encode(), b"1.E+22"),
        (b"r" + (1.5e-07).hex().encode(), b"1.5E-07"),
        (b"r" + (5e-324).hex().encode(), b"5.E-324"),
        (b"r" + (1.7976931348623157e308).hex().encode(), b"1.7976931348623157E+308"),
        (b"i-12", b"-12"),
        (b"s0:", b"''"),
        (b"s4:it's", b"'it''s'"),
        (b"s2:\\n", b"'\\\\n'"),
        ("sÅ".encode()[:1] + b"2:" + "å".encode(), b"'\\X2\\00E5\\X0\\'"),
        (b"s4:" + "😀".encode(), b"'\\X4\\0001F600\\X0\\'"),
        (b"s1:\n", b"'\\X2\\000A\\X0\\'"),
        (b"x3:\xc3\xa5'", b"'\xc3\xa5'''"),
        (b".T.", b".T."),
        (b"$", b"$"),
        (b"*", b"*"),
        (b'"0FF"', b'"0FF"'),
        (12, b"#12"),
        ([], b"()"),
        ([12, b"$", [b"i1"]], b"(#12,$,(1))"),
        ((b"IFCLABEL", [b"s1:a"]), b"IFCLABEL('a')"),
    ],
)
def test_a_value_is_written_as_the_standard_says(value: Any, text: bytes) -> None:
    assert value_text(value) == text
    assert parse_statement(b"IFCX(" + text + b")")[1][0] == value, "and it reads back as itself"


def test_ifcopenshell_reads_what_is_written_as_the_same_values(tmp_path: Path) -> None:
    data = exchange(
        "#1=IFCCOLOURRGB($,0.1,-0.,0.30000000000000004);",
        "#2=IFCCARTESIANPOINT((1.E+22,1.5E-07,5.E-324));",
        "#3=IFCMATERIAL('\\X2\\00E5\\X0\\\\X4\\0001F600\\X0\\''\\\\',$,$);",
    )
    written = ifcopenshell.file.from_string(there_and_back(data, tmp_path).decode("ascii"))
    assert list(written.by_id(1))[1:] == [0.1, -0.0, 0.30000000000000004]
    assert str(written.by_id(1)[2]) == "-0.0"
    assert written.by_id(2).Coordinates == (1e22, 1.5e-07, 5e-324)
    assert written.by_id(3).Name == "å😀'\\"


def test_a_file_that_cannot_be_read_stops_the_conversion(tmp_path: Path) -> None:
    path = tmp_path / "broken.ifc"
    path.write_bytes(exchange("#1=IFCDIRECTION((.5,0.));"))
    with pytest.raises(ConversionError, match="cannot stand"):
        list(convert_lossless(path))
    path.write_bytes(b"not a file")
    with pytest.raises(ConversionError):
        list(convert_lossless(path))
    path.write_bytes(exchange("#1=IFCDIRECTION((1.,0.));", schema="IFC2X_FINAL"))
    with pytest.raises(ConversionError, match="no schema named"):
        list(convert_lossless(path))
    path.write_bytes(exchange("#1=IFCDIRECTION((1.,0.));", "#2=IFCDIRECTION((1.,0.));"))
    with pytest.raises(ConversionError, match="more than 1 entities"):
        list(convert_lossless(path, max_entities=1))


def test_the_worker_and_the_writer_run_as_processes_would(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records = tmp_path / "records.jsonl"
    assert worker_main([str(MODEL), str(records), "--lossless", "--include-geometry"]) == 0
    header = json.loads(capsys.readouterr().out)
    assert header["lossless"] is True and header["entities"] == 248 and header["skipped"] == 0
    assert worker_main([str(MODEL), str(records), "--lossless"]) == 0
    header = json.loads(capsys.readouterr().out)
    assert header["lossless"] is True and header["entities"] + header["skipped"] == 248 and header["skipped"] > 0
    lines = [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines()]
    instances = as_the_graph_holds_them(lines, tmp_path / "instances.jsonl")
    written = tmp_path / "written.ifc"
    assert writer_main([str(instances), str(written)]) == 0
    assert compare(MODEL.read_bytes(), written.read_bytes()).identical

    assert writer_main([str(tmp_path / "missing.jsonl"), str(written)]) == 3
    assert "error" in json.loads(capsys.readouterr().err)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert writer_main([str(empty), str(written)]) == 3


def test_the_file_is_written_in_the_order_it_is_given(tmp_path: Path) -> None:
    data = exchange("#9=IFCDIRECTION((1.,0.));", "#3=IFCDIRECTION((0.,1.));")
    written = there_and_back(data, tmp_path)
    assert written.index(b"#3=") < written.index(b"#9="), "by id, as the records come from the graph"
    assert StepFile(written).ids() == [3, 9]
