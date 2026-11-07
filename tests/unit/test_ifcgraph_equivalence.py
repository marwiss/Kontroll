# This file was generated with the assistance of an AI coding tool.
"""Whether two IFC files hold the same model. Skipped when IfcOpenShell is not installed.

A comparison that passes everything looks the same as one that works, so most of this shows that it can fail: each
change below is one that published comparators and IfcOpenShell's own ``==`` and IfcDiff let through.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FIXTURES_DIR

pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

import ifcopenshell
from ifcopenshell import ifcopenshell_wrapper

from opencde.ifcgraph import equivalence
from opencde.ifcgraph.equivalence import compare, compare_files, main
from opencde.ifcgraph.schema import Schema, relationship_type
from opencde.ifcgraph.step import StepFile

MODEL = FIXTURES_DIR / "three_walls_gtin.ifc"
ORIGINAL = MODEL.read_bytes()


def exchange(*statements: str, schema: str = "IFC4") -> bytes:
    body = "\n".join(statements)
    return (
        "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [x]'),'2;1');\n"
        "FILE_NAME('t.ifc','2026-11-07T00:00:00',(''),(''),'','','');\n"
        f"FILE_SCHEMA(('{schema}'));\nENDSEC;\nDATA;\n{body}\nENDSEC;\nEND-ISO-10303-21;\n"
    ).encode("latin-1")


_STATEMENTS = re.compile(rb"#\d+\s*=(?:[^;']|'[^']*')*;")
_IDS_OUTSIDE_STRINGS = re.compile(rb"'[^']*'|#\d+")


def renumbered_and_shuffled(data: bytes, seed: int = 1) -> bytes:
    """The same model with other ids, in another order."""
    head, rest = data.split(b"DATA;", 1)
    body, tail = rest.rsplit(b"ENDSEC;", 1)
    statements = _STATEMENTS.findall(body)
    ids = [int(re.match(rb"#(\d+)", statement).group(1)) for statement in statements]  # ty: ignore[union-attr]
    generator = random.Random(seed)  # noqa: S311 - not for anything secret
    fresh = list(range(1000, 1000 + 7 * len(ids), 7))
    generator.shuffle(fresh)
    renamed = dict(zip(ids, fresh, strict=True))

    def rename(match: re.Match[bytes]) -> bytes:
        token = match.group(0)
        return token if token[:1] == b"'" else b"#%d" % renamed[int(token[1:])]

    statements = [_IDS_OUTSIDE_STRINGS.sub(rename, statement) for statement in statements]
    generator.shuffle(statements)
    return head + b"DATA;\n" + b"\n".join(statements) + b"\nENDSEC;" + tail


def rewritten(change: Callable[[Any], None] = lambda _model: None) -> bytes:
    """The fixture as IfcOpenShell writes it, after a change."""
    model = ifcopenshell.open(str(MODEL))
    change(model)
    return model.to_string().encode("ascii")


def context_of(model: Any) -> Any:
    return model.by_type("IfcGeometricRepresentationContext", include_subtypes=False)[0]


def _reverse_list(model: Any) -> None:
    line = next(item for item in model.by_type("IfcPolyline") if len(item.Points) > 2)
    line.Points = tuple(reversed(line.Points))


def _one_unit_in_the_last_place(model: Any) -> None:
    point = next(item for item in model.by_type("IfcCartesianPoint") if item.Coordinates[0] > 1)
    x, *rest = point.Coordinates
    point.Coordinates = (x + x * 2**-52, *rest)


def _set_attribute(find: Callable[[Any], Any], name: str, value: Any) -> Callable[[Any], None]:
    def change(model: Any) -> None:
        setattr(find(model), name, value)

    return change


def _length_unit(model: Any) -> Any:
    return next(unit for unit in model.by_type("IfcSIUnit") if unit.UnitType == "LENGTHUNIT")


CHANGES_THAT_KEEP_THE_COUNTS = {
    "the order of a LIST": _reverse_list,
    "one unit in the last place": _one_unit_in_the_last_place,
    "the precision": _set_attribute(context_of, "Precision", 1.0),
    "the world coordinate system": _set_attribute(
        lambda model: context_of(model).WorldCoordinateSystem.Location, "Coordinates", (1.0, 2.0, 3.0)
    ),
    "true north": _set_attribute(lambda model: context_of(model).TrueNorth, "DirectionRatios", (0.6, 0.8)),
    "the length unit": _set_attribute(_length_unit, "Prefix", "CENTI"),
    "a colour": _set_attribute(lambda model: model.by_type("IfcColourRgb")[0], "Red", 0.123),
    "a material": _set_attribute(lambda model: model.by_type("IfcMaterial")[0], "Name", "x"),
    "a latitude": _set_attribute(lambda model: model.by_type("IfcSite")[0], "RefLatitude", (1, 2, 3)),
    "a name on a wall": _set_attribute(lambda model: model.by_type("IfcWall")[0], "Name", "x"),
    "a GlobalId": _set_attribute(lambda model: model.by_type("IfcWall")[0], "GlobalId", "0" * 22),
    "the owner history": _set_attribute(lambda model: model.by_type("IfcOwnerHistory")[0], "CreationDate", 1),
}


def test_a_file_is_the_same_as_itself_and_as_ifcopenshell_writes_it() -> None:
    for other in (ORIGINAL, rewritten()):
        comparison = compare(ORIGINAL, other)
        assert comparison.same_model and comparison.identical, comparison.checks


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_other_ids_and_another_order_are_the_same_model_but_not_identical(seed: int) -> None:
    comparison = compare(ORIGINAL, renumbered_and_shuffled(ORIGINAL, seed))
    assert comparison.same_model
    assert not comparison.identical
    assert comparison.passed("exact") is False
    assert comparison.passed("classes") is True
    assert comparison.passed("georeference") is True


def test_the_order_of_a_set_is_the_same_model_but_not_identical() -> None:
    def reverse(model: Any) -> None:
        walls = model.by_type("IfcRelContainedInSpatialStructure")[0]
        assert len(walls.RelatedElements) > 1
        walls.RelatedElements = tuple(reversed(walls.RelatedElements))

    comparison = compare(ORIGINAL, rewritten(reverse))
    assert comparison.same_model
    assert not comparison.identical


@pytest.mark.parametrize("name", CHANGES_THAT_KEEP_THE_COUNTS)
def test_a_change_to_the_model_fails_though_the_counts_stay(name: str) -> None:
    comparison = compare(ORIGINAL, rewritten(CHANGES_THAT_KEEP_THE_COUNTS[name]))
    assert comparison.passed("classes") is True, "counting classes cannot see this change"
    assert comparison.passed("exact") is False
    assert comparison.passed("same_model") is False
    assert not comparison.same_model and not comparison.identical
    assert comparison.checks[-1].name == "georeference"


def test_changes_are_found_without_trusting_the_ids() -> None:
    """The same changes, in a file with other ids and another order."""
    for name, change in CHANGES_THAT_KEEP_THE_COUNTS.items():
        comparison = compare(ORIGINAL, renumbered_and_shuffled(rewritten(change)))
        assert comparison.passed("same_model") is False, name


def test_removing_or_merging_an_instance_fails_with_the_class_named() -> None:
    comparison = compare(ORIGINAL, rewritten(lambda model: model.remove(model.by_type("IfcMaterialLayer")[0])))
    assert comparison.passed("classes") is False
    assert "IFCMATERIALLAYER 1 and 0" in next(c.detail for c in comparison.checks if c.name == "classes")
    assert not comparison.same_model


POINTS = ("#1=IFCCARTESIANPOINT((0.,0.,0.));", "#2=IFCCARTESIANPOINT((0.,0.,0.));")


def shapes_with_styles(first_style: str, second_style: str) -> bytes:
    """Two equal shapes of two walls, each with a style. What differs lies on the inverse side of the shapes."""
    return exchange(
        "#2=IFCCARTESIANPOINTLIST3D(((0.,0.,0.),(1.,0.,0.),(0.,1.,0.)),$);",
        "#3=IFCTRIANGULATEDFACESET(#2,$,$,((1,2,3)),$);",
        "#4=IFCCARTESIANPOINTLIST3D(((0.,0.,0.),(1.,0.,0.),(0.,1.,0.)),$);",
        "#5=IFCTRIANGULATEDFACESET(#4,$,$,((1,2,3)),$);",
        "#6=IFCCOLOURRGB('red',1.,0.,0.);",
        "#7=IFCCOLOURRGB('green',0.,1.,0.);",
        "#8=IFCSURFACESTYLESHADING(#6,$);",
        "#9=IFCSURFACESTYLESHADING(#7,$);",
        "#10=IFCSURFACESTYLE('red',.BOTH.,(#8));",
        "#11=IFCSURFACESTYLE('green',.BOTH.,(#9));",
        f"#12=IFCSTYLEDITEM(#3,({first_style}),$);",
        f"#13=IFCSTYLEDITEM(#5,({second_style}),$);",
        "#20=IFCCARTESIANPOINT((0.,0.,0.));",
        "#21=IFCAXIS2PLACEMENT3D(#20,$,$);",
        "#22=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#21,$);",
        "#23=IFCSHAPEREPRESENTATION(#22,'Body','Tessellation',(#3));",
        "#24=IFCSHAPEREPRESENTATION(#22,'Body','Tessellation',(#5));",
        "#25=IFCPRODUCTDEFINITIONSHAPE($,$,(#23));",
        "#26=IFCPRODUCTDEFINITIONSHAPE($,$,(#24));",
        "#27=IFCWALL('0000000000000000000001',$,$,$,$,$,#25,$,$);",
        "#28=IFCWALL('0000000000000000000002',$,$,$,$,$,#26,$,$);",
    )


def sharing(third_point: str) -> bytes:
    return exchange(
        "#1=IFCCARTESIANPOINT((1.,2.,3.));",
        "#2=IFCCARTESIANPOINT((1.,2.,3.));",
        "#10=IFCAXIS2PLACEMENT3D(#1,$,$);",
        f"#11=IFCAXIS2PLACEMENT3D({third_point},$,$);",
        "#12=IFCAXIS2PLACEMENT3D(#2,$,$);",
        "#13=IFCLOCALPLACEMENT($,#10);",
    )


def boundaries(*rings: tuple[int, ...], kind: str = ".PHYSICAL.") -> bytes:
    """Space boundaries that each point at the next in their ring. All look alike from anywhere but the rings' size."""
    statements = [
        "#100=IFCSPACE('0000000000000000000011',$,$,$,$,$,$,$,$,$,$);",
        "#101=IFCWALL('0000000000000000000012',$,$,$,$,$,$,$,$);",
    ]
    for ring in rings:
        for place, step_id in enumerate(ring):
            following = ring[(place + 1) % len(ring)]
            statements.append(
                f"#{step_id}=IFCRELSPACEBOUNDARY2NDLEVEL('0000000000000000000013',$,$,$,#100,#101,$,{kind},"
                f".EXTERNAL.,$,#{following});"
            )
    return exchange(*statements)


@pytest.mark.parametrize(
    ("one", "other"),
    [
        pytest.param(
            (
                "#1=IFCPROPERTYSINGLEVALUE('a',$,$,$);",
                "#2=IFCPROPERTYSINGLEVALUE('b',$,$,$);",
                "#3=IFCPROPERTYSET('0000000000000000000001',$,$,$,(#1,#2));",
            ),
            (
                "#1=IFCPROPERTYSINGLEVALUE('a',$,$,$);",
                "#2=IFCPROPERTYSINGLEVALUE('b',$,$,$);",
                "#3=IFCPROPERTYSET('0000000000000000000001',$,$,$,(#2,#1));",
            ),
            id="a SET of references",
        ),
        pytest.param(
            (
                "#1=IFCPROPERTYSET('0000000000000000000001',$,$,$,(#3));",
                "#2=IFCPROPERTYSET('0000000000000000000002',$,$,$,(#3));",
                "#3=IFCPROPERTYSINGLEVALUE('a',$,$,$);",
                "#4=IFCRELDEFINESBYPROPERTIES('0000000000000000000003',$,$,$,(#5),"
                "IFCPROPERTYSETDEFINITIONSET((#1,#2)));",
                "#5=IFCWALL('0000000000000000000004',$,$,$,$,$,$,$,$);",
            ),
            (
                "#1=IFCPROPERTYSET('0000000000000000000001',$,$,$,(#3));",
                "#2=IFCPROPERTYSET('0000000000000000000002',$,$,$,(#3));",
                "#3=IFCPROPERTYSINGLEVALUE('a',$,$,$);",
                "#4=IFCRELDEFINESBYPROPERTIES('0000000000000000000003',$,$,$,(#5),"
                "IFCPROPERTYSETDEFINITIONSET((#2,#1)));",
                "#5=IFCWALL('0000000000000000000004',$,$,$,$,$,$,$,$);",
            ),
            id="a typed SET",
        ),
        pytest.param(
            (
                "#1=IFCCARTESIANPOINT((0.,0.));",
                "#2=IFCDIRECTION((1.,0.));",
                "#3=IFCVECTOR(#2,1.);",
                "#4=IFCLINE(#1,#3);",
                "#5=IFCTRIMMEDCURVE(#4,(IFCPARAMETERVALUE(0.),#1),(IFCPARAMETERVALUE(1.)),.T.,.PARAMETER.);",
            ),
            (
                "#1=IFCCARTESIANPOINT((0.,0.));",
                "#2=IFCDIRECTION((1.,0.));",
                "#3=IFCVECTOR(#2,1.);",
                "#4=IFCLINE(#1,#3);",
                "#5=IFCTRIMMEDCURVE(#4,(#1,IFCPARAMETERVALUE(0.)),(IFCPARAMETERVALUE(1.)),.T.,.PARAMETER.);",
            ),
            id="a SET of a typed value and a reference",
        ),
    ],
)
def test_a_set_has_no_order(one: tuple[str, ...], other: tuple[str, ...]) -> None:
    comparison = compare(exchange(*one), exchange(*other))
    assert comparison.same_model
    assert comparison.passed("exact") is False


@pytest.mark.parametrize(
    ("one", "other"),
    [
        pytest.param(
            ("#1=IFCDIRECTION((1.,0.));", "#2=IFCDIRECTION((0.,1.));", "#3=IFCPROPERTYSET('g',$,$,$,(#1));"),
            ("#1=IFCDIRECTION((1.,0.));", "#2=IFCDIRECTION((0.,1.));", "#3=IFCPROPERTYSET('g',$,$,$,(#2));"),
            id="another member of a SET",
        ),
        pytest.param(
            ("#1=IFCDIRECTION((1.,0.));", "#3=IFCPROPERTYSET('g',$,$,$,(#1));"),
            ("#1=IFCDIRECTION((1.,0.));", "#3=IFCPROPERTYSET('g',$,$,$,(#1,#1));"),
            id="a member of a SET twice",
        ),
        pytest.param(
            (
                "#1=IFCPROPERTYSET('g',$,$,$,(#2));",
                "#2=IFCDIRECTION((1.,0.));",
                "#3=IFCDIRECTION((0.,1.));",
                "#4=IFCRELDEFINESBYPROPERTIES('h',$,$,$,(#1),IFCPROPERTYSETDEFINITIONSET((#2)));",
            ),
            (
                "#1=IFCPROPERTYSET('g',$,$,$,(#2));",
                "#2=IFCDIRECTION((1.,0.));",
                "#3=IFCDIRECTION((0.,1.));",
                "#4=IFCRELDEFINESBYPROPERTIES('h',$,$,$,(#1),IFCPROPERTYSETDEFINITIONSET((#3)));",
            ),
            id="another member of a typed SET",
        ),
        pytest.param(
            ("#1=IFCTRIMMEDCURVE($,(IFCPARAMETERVALUE(0.)),$,.T.,.PARAMETER.);",),
            ("#1=IFCTRIMMEDCURVE($,(IFCPARAMETERVALUE(1.)),$,.T.,.PARAMETER.);",),
            id="another typed value in a SET",
        ),
        pytest.param(("#1=IFCDIRECTION((1.,0.));",), ("#1=IFCDIRECTION((1,0.));",), id="an INTEGER for a REAL"),
        pytest.param(("#1=IFCDIRECTION((1.,0.));",), ("#1=IFCDIRECTION((1.,-0.));",), id="the sign of a zero"),
        pytest.param(
            ("#1=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",), ("#1=IFCSIUNIT($,.LENGTHUNIT.,$,.METRE.);",), id="* or $"
        ),
        pytest.param(("#1=IFCMATERIAL('a',$,$);",), ("#1=IFCMATERIAL('a','',$);",), id="$ or an empty string"),
        pytest.param(("#1=IFCPROPERTYSET('g',$,$,$,());",), ("#1=IFCPROPERTYSET('g',$,$,$,$);",), id="() or $"),
        pytest.param(("#1=IFCMATERIAL('a',$,$);",), ("#1=IFCMATERIALLAYER('a',$,$);",), id="another class"),
        pytest.param(
            ("#1=IFCPROPERTYSINGLEVALUE('a',$,IFCLABEL('x'),$);",),
            ("#1=IFCPROPERTYSINGLEVALUE('a',$,IFCTEXT('x'),$);",),
            id="another type of a typed value",
        ),
        pytest.param(("#1=IFCMATERIAL('\xe5',$,$);",), ("#1=IFCMATERIAL('\\X2\\00E5\\X0\\',$,$);",), id="raw bytes"),
        pytest.param((*POINTS, "#3=IFCPOLYLINE((#1,#2));"), (*POINTS, "#3=IFCPOLYLINE((#1,#1));"), id="another point"),
        pytest.param(
            ("#1=IFCPROPERTYSINGLEVALUE('a',$,$,$);", "#3=IFCPROPERTYSET('g',$,$,$,(#1));"),
            ("#1=IFCPROPERTYSINGLEVALUE('a',$,$,$);", "#3=IFCPROPERTYSET('g',$,$,$,(#99));"),
            id="a reference to nothing in a SET",
        ),
        pytest.param(
            ("#1=IFCDIRECTION((1.,0.));", "#2=IFCPOLYLINE((#1,#99));"),
            ("#1=IFCDIRECTION((1.,0.));", "#2=IFCPOLYLINE((#99,#1));"),
            id="a reference to nothing in a LIST",
        ),
    ],
)
def test_these_are_not_the_same_model(one: tuple[str, ...], other: tuple[str, ...]) -> None:
    comparison = compare(exchange(*one), exchange(*other))
    assert comparison.passed("exact") is False
    assert comparison.passed("same_model") is False
    assert not comparison.same_model


def test_styles_swapped_between_equal_shapes_are_found() -> None:
    """Hashes over forward references alone say these are the same."""
    comparison = compare(shapes_with_styles("#10", "#11"), shapes_with_styles("#11", "#10"))
    assert comparison.passed("classes") is True
    assert comparison.passed("same_model") is False


def test_a_shared_instance_is_not_two_equal_ones() -> None:
    """So are these."""
    comparison = compare(sharing("#1"), sharing("#2"))
    assert comparison.passed("classes") is True
    assert comparison.passed("same_model") is False


def test_a_duplicate_is_part_of_the_model() -> None:
    merged = exchange("#1=IFCCARTESIANPOINT((1.,2.,3.));", "#3=IFCPOLYLINE((#1,#1));")
    apart = exchange(
        "#1=IFCCARTESIANPOINT((1.,2.,3.));", "#2=IFCCARTESIANPOINT((1.,2.,3.));", "#3=IFCPOLYLINE((#1,#2));"
    )
    comparison = compare(merged, apart)
    assert comparison.passed("classes") is False
    assert not comparison.same_model


def test_references_in_a_cycle_are_followed_both_when_they_agree_and_when_they_do_not() -> None:
    """Bottom-up hashing never reaches these, and IfcOpenShell's ``==`` ends the process on them."""
    pair = boundaries((1, 2))
    assert compare(pair, pair).same_model
    assert compare(pair, boundaries((11, 12))).same_model
    assert compare(pair, renumbered_and_shuffled(pair)).same_model
    assert not compare(pair, boundaries((1, 2), kind=".VIRTUAL.")).same_model
    # One of the two changed, written by hand, because a change to all is not the point.
    one_changed = pair.replace(
        b"#1=IFCRELSPACEBOUNDARY2NDLEVEL('0000000000000000000013',$,$,$,#100,#101,$,.PHYSICAL.",
        b"#1=IFCRELSPACEBOUNDARY2NDLEVEL('0000000000000000000013',$,$,$,#100,#101,$,.VIRTUAL.",
    )
    assert one_changed != pair
    comparison = compare(pair, one_changed)
    assert comparison.passed("classes") is True
    assert comparison.passed("same_model") is False


def test_instances_alike_all_the_way_are_paired_by_choice() -> None:
    orphans = exchange(*[f"#{step_id}=IFCCARTESIANPOINT((1.,2.,3.));" for step_id in range(1, 6)])
    assert compare(orphans, renumbered_and_shuffled(orphans)).same_model

    twins_in_a_set = exchange(
        "#1=IFCPROPERTYSINGLEVALUE('a',$,IFCLABEL('x'),$);",
        "#2=IFCPROPERTYSINGLEVALUE('a',$,IFCLABEL('x'),$);",
        "#3=IFCPROPERTYSINGLEVALUE('a',$,IFCLABEL('x'),$);",
        "#4=IFCPROPERTYSET('0000000000000000000001',$,$,$,(#1,#2,#3));",
    )
    assert compare(twins_in_a_set, renumbered_and_shuffled(twins_in_a_set)).same_model


def test_rings_that_refinement_cannot_tell_apart_are_told_apart_by_the_search() -> None:
    """Every boundary has one before it and one after it, in a ring of six and in two rings of three alike, so
    refinement stops with all of them in one class. Only trying a pairing shows that there is none."""
    six = boundaries((1, 2, 3, 4, 5, 6))
    three_and_three = boundaries((1, 2, 3), (4, 5, 6))
    assert compare(six, renumbered_and_shuffled(six)).same_model
    assert compare(three_and_three, renumbered_and_shuffled(three_and_three)).same_model
    comparison = compare(six, three_and_three)
    assert comparison.passed("classes") is True
    assert comparison.passed("same_model") is False
    assert "No pairing exists" in next(c.detail for c in comparison.checks if c.name == "same_model")


def test_a_wrong_choice_is_taken_back() -> None:
    """Half of the choices for the first instance lead nowhere, whichever instance that is."""
    rings = boundaries((1, 2, 3, 4, 5, 6), (7, 8, 9), (10, 11, 12))
    for seed in range(5):
        assert compare(rings, renumbered_and_shuffled(rings, seed)).same_model


def test_a_search_that_reaches_its_limit_says_nothing_and_counts_as_not_the_same(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(equivalence, "MAX_FAILED_PAIRINGS", 0)
    comparison = compare(boundaries((1, 2, 3, 4, 5, 6)), boundaries((1, 2, 3), (4, 5, 6)))
    assert comparison.passed("same_model") is None
    assert not comparison.same_model


def matching_of(one: tuple[str, ...], other: tuple[str, ...]) -> equivalence._Matching:
    return equivalence._Matching(StepFile(exchange(*one)), StepFile(exchange(*other)), Schema("IFC4"))


def test_a_pairing_is_checked_against_the_files_alone() -> None:
    directions = "#1=IFCDIRECTION((1.,0.));", "#2=IFCDIRECTION((0.,1.));"
    in_a_list = matching_of((*directions, "#3=IFCPOLYLINE((#1,#2));"), (*directions, "#3=IFCPOLYLINE((#1,#2));"))
    assert in_a_list.first_wrong({0: 3, 1: 4, 2: 5}) is None
    swapped = matching_of((*directions, "#3=IFCPOLYLINE((#1,#2));"), (*directions, "#3=IFCPOLYLINE((#2,#1));"))
    assert swapped.first_wrong({0: 3, 1: 4, 2: 5}) == 2, "the order of the references"
    alone = matching_of(directions, directions)
    assert alone.first_wrong({0: 2, 1: 3}) is None
    assert alone.first_wrong({0: 3, 1: 2}) == 0, "the values"

    in_a_set = (*directions, "#3=IFCPROPERTYSET('g',$,$,$,(#1));", "#4=IFCPROPERTYSET('g',$,$,$,(#2));")
    sets = matching_of(in_a_set, in_a_set)
    assert sets.first_wrong({0: 4, 1: 5, 2: 6, 3: 7}) is None
    assert sets.first_wrong({0: 4, 1: 5, 2: 7, 3: 6}) == 2, "the members of a SET"


@pytest.mark.parametrize(
    "statements",
    [
        pytest.param(
            (
                "#1=IFCLOCALPLACEMENT($,#3);",
                "#2=IFCLOCALPLACEMENT($,#4);",
                "#3=IFCAXIS2PLACEMENT3D(#5,$,$);",
                "#4=IFCAXIS2PLACEMENT3D(#6,$,$);",
                "#5=IFCCARTESIANPOINT((1.,0.,0.));",
                "#6=IFCCARTESIANPOINT((0.,1.,0.));",
            ),
            id="values two references down, in forward references",
        ),
        pytest.param(
            (
                "#1=IFCPROPERTYSET('0000000000000000000001',$,$,$,(#3));",
                "#2=IFCPROPERTYSET('0000000000000000000001',$,$,$,(#4));",
                "#3=IFCPROPERTYSINGLEVALUE('a',$,$,$);",
                "#4=IFCPROPERTYSINGLEVALUE('b',$,$,$);",
            ),
            id="values in a SET",
        ),
        pytest.param(
            (
                "#1=IFCCARTESIANPOINT((1.,2.,3.));",
                "#2=IFCCARTESIANPOINT((1.,2.,3.));",
                "#3=IFCPOLYLINE((#1));",
                "#4=IFCPOLYLINE((#2,#2));",
            ),
            id="equal points used in other ways, in inverse references",
        ),
    ],
)
def test_refinement_alone_tells_apart_what_differs_anywhere(statements: tuple[str, ...]) -> None:
    """No choices are needed for these, and a search would be the slow way to the same answer."""
    matching = matching_of(statements, statements)
    assert matching.tied
    assert matching.refine(range(len(matching.ids))) is None
    assert not matching.tied


def test_a_difference_in_values_is_named_as_that() -> None:
    comparison = compare(exchange("#1=IFCMATERIAL('a',$,$);"), exchange("#1=IFCMATERIAL('b',$,$);"))
    detail = next(check.detail for check in comparison.checks if check.name == "same_model")
    assert detail == "No instance in the second file has the values of #1=IFCMATERIAL('a',$,$) in the first."
    comparison = compare(sharing("#1"), sharing("#2"))
    detail = next(check.detail for check in comparison.checks if check.name == "same_model")
    assert "has the place in the model of" in detail


GEOREFERENCED = (
    "#1=IFCCARTESIANPOINT((0.,0.,0.));",
    "#2=IFCAXIS2PLACEMENT3D(#1,$,$);",
    "#3=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#2,$);",
    "#4=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",
    "#5=IFCPROJECTEDCRS('EPSG:3006',$,$,$,$,$,#4);",
    "#6=IFCMAPCONVERSION(#3,#5,674000.,6580000.,10.,1.,0.,1.);",
)


def test_georeferencing_outside_every_rooted_instance_is_compared_by_name() -> None:
    """The map conversion is reached from no IfcRoot, so ``==`` per GlobalId and IfcDiff with every option say nothing."""
    moved = tuple(line.replace("674000.", "675000.") for line in GEOREFERENCED)
    comparison = compare(exchange(*GEOREFERENCED), exchange(*moved))
    assert comparison.passed("classes") is True
    assert comparison.passed("same_model") is False
    assert comparison.passed("georeference") is False
    detail = next(check.detail for check in comparison.checks if check.name == "georeference")
    assert "IFCMAPCONVERSION.Eastings" in detail and "674000.0" in detail and "675000.0" in detail

    other_crs = tuple(line.replace("EPSG:3006", "EPSG:3011") for line in GEOREFERENCED)
    assert compare(exchange(*GEOREFERENCED), exchange(*other_crs)).passed("georeference") is False
    unit = tuple(line.replace("$,.METRE.", ".MILLI.,.METRE.") for line in GEOREFERENCED)
    assert compare(exchange(*GEOREFERENCED), exchange(*unit)).passed("georeference") is False
    gone = (*GEOREFERENCED[:-1], "#6=IFCPROPERTYSINGLEVALUE('a',$,$,$);")
    assert compare(exchange(*GEOREFERENCED), exchange(*gone)).passed("georeference") is False
    same = compare(exchange(*GEOREFERENCED), renumbered_and_shuffled(exchange(*GEOREFERENCED)))
    assert same.passed("georeference") is True


@pytest.mark.parametrize(
    ("name", "said"),
    [
        ("the precision", "IFCGEOMETRICREPRESENTATIONCONTEXT.Precision"),
        ("the world coordinate system", "IFCGEOMETRICREPRESENTATIONCONTEXT.WorldCoordinateSystem"),
        ("true north", "IFCGEOMETRICREPRESENTATIONCONTEXT.TrueNorth"),
        ("the length unit", "IFCPROJECT.UnitsInContext"),
        ("a latitude", "IFCSITE.RefLatitude"),
    ],
)
def test_where_the_model_is_named_in_the_report(name: str, said: str) -> None:
    comparison = compare(ORIGINAL, rewritten(CHANGES_THAT_KEEP_THE_COUNTS[name]))
    assert comparison.passed("georeference") is False
    assert said in next(check.detail for check in comparison.checks if check.name == "georeference")


def test_what_says_nothing_of_where_leaves_the_georeference_alone() -> None:
    for name in ("a colour", "a material", "a name on a wall", "the order of a LIST"):
        assert compare(ORIGINAL, rewritten(CHANGES_THAT_KEEP_THE_COUNTS[name])).passed("georeference") is True, name


def test_the_order_of_a_set_says_nothing_of_where() -> None:
    def reverse(model: Any) -> None:
        units = model.by_type("IfcUnitAssignment")[0]
        units.Units = tuple(reversed(units.Units))

    comparison = compare(ORIGINAL, rewritten(reverse))
    assert comparison.same_model
    assert comparison.passed("exact") is False
    assert comparison.passed("georeference") is True


def test_writing_out_a_georeference_has_a_limit_on_the_work() -> None:
    """Each instance refers twice to the one before, so this writes out to 2**60 of them."""
    chain = ["#1=IFCDIRECTION((1.,0.));"]
    chain += [f"#{step_id}=IFCVECTOR(#{step_id - 1},#{step_id - 1});" for step_id in range(2, 61)]
    file = exchange(*chain, "#100=IFCMAPCONVERSION(#60,$,0.,0.,0.,$,$,$);")
    comparison = compare(file, file)
    assert comparison.passed("georeference") is None
    assert "more than" in next(check.detail for check in comparison.checks if check.name == "georeference")


def test_ifc2x3_says_its_georeference_in_property_sets() -> None:
    def statements(easting: str) -> tuple[str, ...]:
        return (
            f"#1=IFCPROPERTYSINGLEVALUE('Eastings',$,IFCLENGTHMEASURE({easting}),$);",
            "#2=IFCPROPERTYSET('0000000000000000000001',$,'ePSet_MapConversion',$,(#1));",
            "#3=IFCPROPERTYSINGLEVALUE('Name',$,IFCLABEL('EPSG:3006'),$);",
            "#4=IFCPROPERTYSET('0000000000000000000002',$,'ePSet_ProjectedCRS',$,(#3));",
            "#5=IFCPROPERTYSINGLEVALUE('Other',$,IFCLABEL('x'),$);",
            "#6=IFCPROPERTYSET('0000000000000000000003',$,'Pset_Other',$,(#5));",
        )

    one = exchange(*statements("674000."), schema="IFC2X3")
    other = exchange(*statements("675000."), schema="IFC2X3")
    assert compare(one, other).passed("georeference") is False
    assert compare(one, renumbered_and_shuffled(one)).passed("georeference") is True
    elsewhere = one.replace(b"IFCLABEL('x')", b"IFCLABEL('y')")
    assert compare(one, elsewhere).passed("georeference") is True, "another property set says nothing of where"
    assert compare(one, elsewhere).passed("same_model") is False


def test_the_written_out_georeference_holds_for_a_cycle_entered_anywhere() -> None:
    """Which instance of a ring comes first must not change what the rest of the ring writes out to."""
    context = (
        "#{}=IFCGEOMETRICREPRESENTATIONSUBCONTEXT($,$,$,$,$,$,#{},$,.MODEL_VIEW.,$);",
        "#{}=IFCGEOMETRICREPRESENTATIONSUBCONTEXT($,$,$,$,$,$,#{},$,.PLAN_VIEW.,$);",
    )
    one = exchange(context[0].format(1, 2), context[1].format(2, 1))
    other = exchange(context[1].format(1, 2), context[0].format(2, 1))
    comparison = compare(one, other)
    assert comparison.passed("georeference") is True
    assert comparison.passed("same_model") is True


def test_a_header_is_compared_apart_from_the_model() -> None:
    other_name = ORIGINAL.replace(b"2023-09-04T21:58:54", b"2026-11-07T00:00:00")
    assert other_name != ORIGINAL
    comparison = compare(ORIGINAL, other_name)
    assert comparison.same_model
    assert comparison.passed("exact") is True
    assert comparison.passed("header") is False
    assert not comparison.identical
    assert "FILE_NAME" in next(check.detail for check in comparison.checks if check.name == "header")


def test_another_schema_is_another_model() -> None:
    statements = ("#1=IFCDIRECTION((1.,0.));",)
    comparison = compare(exchange(*statements, schema="IFC4"), exchange(*statements, schema="IFC2X3"))
    assert comparison.passed("exact") is True
    assert comparison.passed("header") is False
    assert comparison.passed("same_model") is False
    assert not comparison.same_model and not comparison.identical


def test_a_schema_that_is_not_known_gets_no_answer() -> None:
    statements = ("#1=IFCDIRECTION((1.,0.));", "#2=IFCDIRECTION((1.,0.));")
    one = exchange(*statements, schema="IFC2X_FINAL")
    comparison = compare(one, renumbered_and_shuffled(one))
    assert comparison.passed("same_model") is None
    assert not comparison.same_model


def test_a_file_that_cannot_be_read_gets_no_answer_and_is_named() -> None:
    comparison = compare(ORIGINAL, ORIGINAL[:-100])
    assert comparison.checks[0].passed is False
    assert "second file" in comparison.checks[0].detail
    assert not comparison.same_model and not comparison.identical
    statement = exchange("#1=IFCDIRECTION((.5,0.));")
    comparison = compare(statement, ORIGINAL)
    assert "first file" in comparison.checks[0].detail


def test_raw_bytes_are_reported() -> None:
    raw = exchange("#1=IFCMATERIAL('\xc3\xa5',$,$);")
    comparison = compare(raw, raw)
    assert "the first file has 2, the second file has 2" in comparison.checks[0].detail


def test_every_schema_keeps_order_inside_a_set_out_of_it() -> None:
    """A SET whose members hold references inside them counts as ordered, so it must be something no schema allows."""
    for name in ("IFC2X3", "IFC4", "IFC4X3_ADD2"):
        schema = ifcopenshell_wrapper.schema_by_name(name)
        for declaration in schema.declarations():
            entity = declaration.as_entity()
            if not entity:
                continue
            for attribute in Schema(name).attributes(declaration.name().upper().encode("ascii")) or ():
                assert not (set(attribute.kinds[:-1]) & {"set", "bag"}), (name, declaration.name(), attribute.name)


def attribute_of(schema: Schema, keyword: bytes, name: str) -> Any:
    return next(attribute for attribute in schema.attributes(keyword) or () if attribute.name == name)


def test_the_schema_says_what_an_attribute_holds() -> None:
    schema = Schema("IFC4")
    held = {
        (b"IFCPROPERTYSET", "HasProperties"): (("set",), "entity"),
        (b"IFCPOLYLINE", "Points"): (("list",), "entity"),
        (b"IFCCARTESIANPOINTLIST3D", "CoordList"): (("list", "list"), "real"),
        (b"IFCBSPLINESURFACE", "ControlPointsList"): (("list", "list"), "entity"),
        (b"IFCTRIMMEDCURVE", "Trim1"): (("set",), "select"),
        (b"IFCPROPERTYSINGLEVALUE", "NominalValue"): ((), "select"),
        (b"IFCWALL", "PredefinedType"): ((), "enumeration"),
        (b"IFCWALL", "Name"): ((), "string"),
        (b"IFCSITE", "RefLatitude"): (("list",), "integer"),
        (b"IFCBSPLINESURFACE", "UClosed"): ((), "logical"),
        (b"IFCTRIMMEDCURVE", "SenseAgreement"): ((), "boolean"),
        (b"IFCBLOBTEXTURE", "RasterCode"): ((), "binary"),
    }
    for (keyword, name), (kinds, leaf) in held.items():
        attribute = attribute_of(schema, keyword, name)
        assert (attribute.kinds, attribute.leaf) == (kinds, leaf), (keyword, name)
    assert attribute_of(schema, b"IFCSIUNIT", "Dimensions").derived
    assert not attribute_of(schema, b"IFCSIUNIT", "UnitType").derived
    assert attribute_of(schema, b"IFCRELDEFINESBYPROPERTIES", "RelatingPropertyDefinition").relationship == (
        "RELATING_PROPERTY_DEFINITION"
    )
    assert schema.defined_type(b"IFCPROPERTYSETDEFINITIONSET") == (("set",), "entity")
    assert schema.defined_type(b"IFCLABEL") == ((), "string")
    assert schema.defined_type(b"IFCLOGICAL") == ((), "logical")
    assert schema.defined_type(b"IFCWALL") is None
    assert schema.attributes(b"IFCNOSUCHTHING") is None
    assert schema.attributes(b"IFCLABEL") is None
    assert schema.defined_type(b"IFCNOSUCHTHING") is None
    assert (
        schema.chain(b"IFCWALL")[:2] == ("IfcWall", "IfcBuildingElement") and schema.chain(b"IFCWALL")[-1] == "IfcRoot"
    )
    assert schema.chain(b"IFCNOSUCHTHING") == ()


def test_the_schema_says_what_refers_back() -> None:
    schema = Schema("IFC4")
    assert schema.refers_back(b"IFCRELDEFINESBYPROPERTIES", "RelatedObjects", b"IFCWALL") == ["IsDefinedBy"]
    assert schema.refers_back(b"IFCRELASSOCIATESMATERIAL", "RelatedObjects", b"IFCWALL") == ["HasAssociations"]
    assert schema.refers_back(b"IFCWALL", "Name", b"IFCWALL") == []
    assert schema.refers_back(b"IFCPOLYLINE", "Points", b"IFCCARTESIANPOINT") == []
    assert schema.refers_back(b"IFCNOSUCHTHING", "RelatedObjects", b"IFCWALL") == []
    assert schema.refers_back(b"IFCRELDEFINESBYPROPERTIES", "RelatedObjects", b"IFCNOSUCHTHING") == []


def test_no_class_has_two_attributes_of_one_relationship_type() -> None:
    """The writer finds an attribute's references by the relationship's type, and an inverse attribute's relationships
    are never read, so a forward and an inverse attribute of one class must not end up with one type."""
    for name in ("IFC2X3", "IFC4", "IFC4X3_ADD2"):
        schema = ifcopenshell_wrapper.schema_by_name(name)
        for declaration in schema.declarations():
            entity = declaration.as_entity()
            if not entity:
                continue
            types = [relationship_type(attribute.name()) for attribute in entity.all_attributes()]
            types += [relationship_type(inverse.name()) for inverse in entity.all_inverse_attributes()]
            assert len(types) == len(set(types)), (name, declaration.name())


def test_generated_geometry_is_compared_bit_for_bit(tmp_path: Path) -> None:
    written = tmp_path / "written.ifc"
    written.write_bytes(rewritten())
    comparison = compare_files(MODEL, written, geometry=True)
    assert comparison.same_model and comparison.identical
    built = next(check for check in comparison.checks if check.name == "geometry")
    assert built.passed is True
    assert built.detail.startswith("3 products build the same")

    def move(model: Any) -> None:
        for point in model.by_type("IfcCartesianPoint"):
            point.Coordinates = tuple(coordinate + 0.25 for coordinate in point.Coordinates)

    moved = tmp_path / "moved.ifc"
    moved.write_bytes(rewritten(move))
    assert compare_files(MODEL, moved, geometry=True).passed("geometry") is False


def wall_with_a_body(body_name: str, *items: str) -> bytes:
    return exchange(
        "#1=IFCCARTESIANPOINT((0.,0.,0.));",
        "#2=IFCAXIS2PLACEMENT3D(#1,$,$);",
        "#3=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#2,$);",
        "#4=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",
        "#5=IFCUNITASSIGNMENT((#4));",
        "#6=IFCPROJECT('0000000000000000000001',$,'p',$,$,$,$,(#3),#5);",
        *items,
        f"#20=IFCSHAPEREPRESENTATION(#3,'{body_name}','Tessellation',({'#11' if items else ''}));",
        "#21=IFCPRODUCTDEFINITIONSHAPE($,$,(#20));",
        "#22=IFCLOCALPLACEMENT($,#2);",
        "#23=IFCWALL('0000000000000000000002',$,$,$,$,#22,#21,$,$);",
    )


TRIANGLES = (
    "#10=IFCCARTESIANPOINTLIST3D(((0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)),$);",
    "#11=IFCTRIANGULATEDFACESET(#10,$,$,((1,3,2),(1,2,4),(2,3,4),(3,1,4)),$);",
)


def test_a_model_whose_bodies_cannot_be_built_gets_no_answer(tmp_path: Path) -> None:
    """A comparison that built nothing has compared nothing, which is how IfcDiff came to report 0 changes."""
    path = tmp_path / "nothing.ifc"
    path.write_bytes(wall_with_a_body("Body"))
    built = compare_files(path, path, geometry=True)
    assert built.passed("geometry") is None
    assert built.same_model


def test_a_product_that_gains_or_loses_a_body_fails(tmp_path: Path) -> None:
    with_body, without = tmp_path / "with.ifc", tmp_path / "without.ifc"
    with_body.write_bytes(wall_with_a_body("Body", *TRIANGLES))
    without.write_bytes(wall_with_a_body("Other", *TRIANGLES))
    assert compare_files(with_body, with_body, geometry=True).passed("geometry") is True
    comparison = compare_files(with_body, without, geometry=True)
    assert comparison.passed("geometry") is False
    assert "1 products have a body in only one" in next(c.detail for c in comparison.checks if c.name == "geometry")


def test_a_mesh_digest_holds_every_bit_of_vertices_and_faces() -> None:
    digest = equivalence._mesh_digest
    assert digest((0.0, 1.0), (0, 1, 2)) == digest((0.0, 1.0), (0, 1, 2))
    assert digest((0.0, 1.0), (0, 1, 2)) != digest((0.0, 1.0), (0, 2, 1))
    assert digest((0.0, 1.0), (0, 1, 2)) != digest((-0.0, 1.0), (0, 1, 2))
    assert digest((0.0, 1.0), (0, 1, 2)) != digest((0.0, 1.0000000000000002), (0, 1, 2))


def test_a_model_without_bodies_passes_on_nothing_built(tmp_path: Path) -> None:
    empty = tmp_path / "empty.ifc"
    empty.write_bytes(exchange("#1=IFCDIRECTION((1.,0.));"))
    assert compare_files(empty, empty, geometry=True).passed("geometry") is True


def test_a_kernel_that_cannot_read_a_file_gets_no_answer(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.ifc"
    unknown.write_bytes(exchange("#1=IFCDIRECTION((1.,0.));", schema="IFC2X_FINAL"))
    comparison = compare_files(unknown, unknown, geometry=True)
    assert comparison.passed("geometry") is None
    assert comparison.same_model, "the instances can still be shown the same, for they are"


def test_the_module_can_be_run_as_a_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    written = tmp_path / "written.ifc"
    written.write_bytes(renumbered_and_shuffled(ORIGINAL))
    assert main([str(MODEL), str(written)]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["same_model"] is True and answer["identical"] is False

    changed = tmp_path / "changed.ifc"
    changed.write_bytes(rewritten(CHANGES_THAT_KEEP_THE_COUNTS["a colour"]))
    assert main([str(MODEL), str(changed)]) == 1
    assert json.loads(capsys.readouterr().out)["same_model"] is False

    assert main([str(MODEL), str(tmp_path / "missing.ifc")]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_the_answer_stands_alone_on_stdout_whatever_the_kernel_writes() -> None:
    """The geometry kernel writes to stdout from C++, which is what a write to the file descriptor stands in for."""
    script = (
        "import os, sys\n"
        "from opencde.ifcgraph.worker import keep_stdout_for_the_answer\n"
        "keep_stdout_for_the_answer()\n"
        "os.write(1, b'noise from the kernel\\n')\n"
        "sys.stdout.write('the answer\\n')\n"
    )
    done = subprocess.run(  # noqa: S603 - this very interpreter, on the text above
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=True
    )
    assert done.stdout.strip() == "the answer"
    assert "noise from the kernel" in done.stderr


def test_the_module_answers_in_a_process_of_its_own(tmp_path: Path) -> None:
    written = tmp_path / "written.ifc"
    written.write_bytes(renumbered_and_shuffled(ORIGINAL))
    done = subprocess.run(  # noqa: S603 - this very interpreter, on files the test wrote
        [sys.executable, "-m", "opencde.ifcgraph.equivalence", str(MODEL), str(written), "--geometry"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["same_model"] is True
