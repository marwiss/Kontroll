# This file was generated with the assistance of an AI coding tool.
"""The reader the IFC comparison stands on: what it reads as the same, and what it refuses."""

from __future__ import annotations

import pytest

from opencde.ifcgraph.step import MAX_NESTING, StepError, StepFile, exact_text, parse_statement
from tests.conftest import FIXTURES_DIR

HEAD = (
    b"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [x]'),'2;1');\n"
    b"FILE_NAME('t.ifc','2026-11-07T00:00:00',(''),(''),'','','');\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
)
TAIL = b"ENDSEC;\nEND-ISO-10303-21;\n"


def value(text: bytes) -> bytes:
    """The canonical text of one value."""
    _keyword, parameters = parse_statement(b"IFCX(" + text + b")")
    return exact_text(parameters[0])


@pytest.mark.parametrize(
    ("one", "other"),
    [
        (b"1.", b"1.0"),
        (b"1.", b"1.0E0"),
        (b"1.", b"10.E-1"),
        (b"1.", b"+1."),
        (b"1.", b"1.e0"),
        (b"1E3", b"1000."),
        (b"0.1", b"0.1000000000000000055511151231257827"),  # the same double, written long
        (b"1", b"+1"),
        (b"1", b"0001"),
        (rb"'\X2\00E5\X0\'", rb"'\X\E5'"),
        (rb"'\X2\00E5\X0\'", rb"'\S\e'"),
        (rb"'\X2\00E5\X0\'", rb"'\PA\\S\e'"),
        (rb"'\X2\00E5\X0\'", rb"'\X4\000000E5\X0\'"),
        (rb"'\X2\D83DDE00\X0\'", rb"'\X4\0001F600\X0\'"),  # a character outside the 16-bit range, both ways
        (rb"'a\\b'", rb"'a\X\5Cb'"),
        (b"'it''s'", rb"'it\X\27s'"),
        (rb"'C:\Users'", rb"'C:\\Users'"),  # a backslash that starts no escape stands for itself
        (b"IFCLABEL('a')", b"ifclabel( 'a' )"),
        (b"( 1 , 2 )", b"(1,2)"),
        (b"(1,/* a comment; with a 'quote */2)", b"(1,2)"),
    ],
)
def test_two_spellings_of_a_value_are_the_same_value(one: bytes, other: bytes) -> None:
    assert value(one) == value(other)


@pytest.mark.parametrize(
    ("one", "other"),
    [
        (b"0.1", b"0.10000000000000002"),  # one unit in the last place
        (b"9060000.123456789", b"9060000.123456791"),
        (b"0.", b"-0."),
        (b"1", b"1."),
        (b"$", b"*"),
        (b"$", b"''"),
        (b"$", b"()"),
        (b"()", b"(())"),
        (b".T.", b".F."),
        (b".T.", b".U."),
        (b".X.", b"'X'"),
        (b"'a'", b"'A'"),
        (b"#1", b"#2"),
        (b"#1", b"1"),
        (b"(1,2)", b"(2,1)"),
        (b"((1,2),(3))", b"((1),(2,3))"),
        (b"('a,s1:b')", b"('a','b')"),  # text that looks like two values is one value
        (b"('a','b')", b"('ab')"),
        (b"IFCLABEL('a')", b"IFCTEXT('a')"),
        (b"IFCLABEL('a')", b"'a'"),
        (b'"0FF"', b'"1FF"'),
        (rb"'\PA\\S\e'", rb"'\PB\\S\e'"),  # the same byte in two code pages
        (b"'\xe5'", rb"'\X\E5'"),  # raw bytes are not taken for the character they might mean
        (b"'\xc3\xa5'", rb"'\X\E5'"),
    ],
)
def test_two_different_values_stay_different(one: bytes, other: bytes) -> None:
    assert value(one) != value(other)


def test_a_file_is_read_with_its_layout_comments_and_header() -> None:
    data = b"\xef\xbb\xbf/* a comment */" + HEAD.replace(b"\n", b"\r\n")
    data += b"/* #9=IFCNOT(1); */\r\n#00012 =\r\n IFCX( 'a;b' , /* ; */ #13 ) ;\n#13=ifcy(.T.);\n"
    data += b"#14=(IFCA(1)IFCB('b'));\n" + TAIL + b"anything after the end\n"
    file = StepFile(data)
    assert file.schema == "IFC4"
    assert len(file) == 3 and 12 in file and 9 not in file
    assert file.header[b"FILE_SCHEMA"] == b"(s4:IFC4)"
    assert file[12] == (b"IFCX", [b"s3:a;b", 13])
    assert file[13] == (b"IFCY", [b".T."])
    assert file[14] == (b"(IFCA IFCB)", [(b"IFCA", [b"i1"]), (b"IFCB", [b"s1:b"])])
    assert [step_id for step_id, _keyword, _parameters in file] == [12, 13, 14]
    assert file.text_of(13) == "#13=ifcy(.T.)"
    assert file.text_of(12, limit=5) == "#12=IFCX(…"
    assert file.raw_bytes() == 3  # the byte order mark


def test_bytes_above_ascii_are_counted() -> None:
    assert StepFile(HEAD + b"#1=IFCX('\xc3\xa5');\n" + TAIL).raw_bytes() == 2


@pytest.mark.parametrize(
    "body",
    [
        b"#1=IFCX(.5);",  # IfcOpenShell reads this list as one value shorter, without an error
        b"#1=IFCX((.5,0.,0.));",
        b"#1=IFCX(1 2);",
        b"#1=IFCX(1,);",
        b"#1=IFCX(,1);",
        b"#1=IFCX(1;",
        b"#1=IFCX(1));",
        b"#1=IFCX;",
        b"#1=IFCX(FOO);",
        b"#1=1;",
        b"#1=;",
        b"#1=IFCX('open);",
        b"#1=IFCX(/* open);",
        b"#1=IFCX(1 / 2);",
        b"#1=IFCX(\xe5);",  # a raw byte outside a string
        b"IFCX(1);",
        b"#1=IFCX(1);#1=IFCX(2);",
        b"#1=IFCX(" + b"(" * (MAX_NESTING + 1) + b")" * (MAX_NESTING + 1) + b");",
        b"#1=IFCX(" + b"9" * 5000 + b");",
        rb"#1=IFCX('\X4\FFFFFFFF\X0\');",
        b"#1=(IFCA(1)IFCB(2);",
    ],
)
def test_what_the_reader_cannot_stand_behind_is_refused(body: bytes) -> None:
    with pytest.raises(StepError):
        for _record in StepFile(HEAD + body + b"\n" + TAIL):
            pass


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"404: Not Found",
        HEAD,  # cut off before the end of the data section
        HEAD + b"#1=IFCX(1);\n#2=IFCX('",  # cut off in the middle of a statement
        HEAD + b"#1=IFCX(1);\nENDSEC;\n",  # no end
        HEAD + TAIL.replace(b"END-ISO-10303-21", b"ANCHOR"),
        HEAD + b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",  # a second data section
        HEAD.replace(b"HEADER;", b"HEADERS;") + TAIL,
        HEAD.replace(b"DATA;", b"DATA('x');") + TAIL,
        HEAD.replace(b"(('IFC4'))", b"(('IFC4','IFC2X3'))") + TAIL,
        HEAD.replace(b"(('IFC4'))", b"()") + TAIL,
    ],
)
def test_what_is_no_whole_exchange_structure_is_refused(data: bytes) -> None:
    with pytest.raises(StepError):
        StepFile(data)


def test_a_hostile_file_cannot_make_the_reader_backtrack() -> None:
    size = 2_000_000
    for body in (b"#1=IFCX(" + b"a" * size, b"#1=IFCX('" + b"''" * size, b"#1=IFCX(" + b"/" * size):
        with pytest.raises(StepError):
            StepFile(HEAD + body)


def test_the_fixture_model_reads_completely() -> None:
    file = StepFile((FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())
    assert file.schema == "IFC2X3"
    assert len(file) == 248
    assert sum(1 for _record in file) == 248
