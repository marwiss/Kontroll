# This file was generated with the assistance of an AI coding tool.
"""A file into the graph and out of it again, on each database, compared with the original."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from ifc_lpg.convert import write_jsonl
from ifc_lpg.equivalence import compare, compare_files
from ifc_lpg.exporter import NotExportable, export_records
from ifc_lpg.importer import delete_model, import_records
from ifc_lpg.writer import write_records
from typer.testing import CliRunner

from opencde import backup
from opencde import seed as seeding
from opencde.bootstrap import make_graph, make_storage
from opencde.cli import app
from opencde.graph.graph import Graph
from opencde.graph.schema import apply_schema
from opencde.ifcgraph.service import IfcGraphService
from opencde.settings import Settings
from opencde.store.accounts.projects import ProjectRepository
from tests import conftest
from tests.integration.conftest import GraphTarget

pytestmark = pytest.mark.integration
pytest.importorskip("ifcopenshell", reason="the ifc-lpg extra is not installed")

HEAD = (
    b"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [x]'),'2;1');\n"
    b"FILE_NAME('t.ifc','2026-11-07T00:00:00',('A'),('O'),'pre','sys',$);\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
)
TAIL = b"ENDSEC;\nEND-ISO-10303-21;\n"

# What a database could change: the bits of a double, the kind of a number, the characters of a string, an empty list.
HARD_VALUES = b"""
#1=IFCCOLOURRGB($,0.,-0.,0.30000000000000004);
#2=IFCCARTESIANPOINT((5.E-324,1.7976931348623157E+308,-2.2250738585072014E-308));
#3=IFCCARTESIANPOINT((0.1,1.E+22,1.E-07));
#4=IFCCARTESIANPOINT((1.E+999,-1.E+999,0.));
#5=IFCPROPERTYSINGLEVALUE('a',$,IFCINTEGER(9223372036854775807),$);
#6=IFCPROPERTYSINGLEVALUE('b',$,IFCINTEGER(-9223372036854775808),$);
#7=IFCPROPERTYSINGLEVALUE('c',$,IFCINTEGER(9223372036854775808),$);
#8=IFCCARTESIANPOINT((1,2,3));
#9=IFCCARTESIANPOINT((1,2.,3));
#10=IFCMATERIAL('\\X2\\00E5\\X0\\ \\X4\\0001F600\\X0\\ it''s \\\\ ;,()#1 $ *',$,$);
#11=IFCMATERIAL('',$,$);
#12=IFCMATERIAL('\\X\\00',$,$);
#13=IFCMATERIAL('\\X2\\D83D\\X0\\',$,$);
#14=IFCMATERIAL('r\xc3\xa5 \xe5',$,$);
#15=IFCWALL('0000000000000000000015',$,$,$,$,$,$,$,.NULLENUM.);
#16=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#17=IFCSIUNIT($,.LENGTHUNIT.,$,.METRE.);
#18=IFCPROPERTYSET('0000000000000000000018',$,$,$,());
#19=IFCMATERIALPROPERTIES('n',$,($,$),#11);
#20=IFCPROPERTYSINGLEVALUE('d',$,IFCLOGICAL(.U.),$);
#21=IFCPROPERTYSINGLEVALUE('e',$,IFCBOOLEAN(.T.),$);
#22=IFCPROPERTYSINGLEVALUE('f',$,IFCCOMPOUNDPLANEANGLEMEASURE((1,2,3,4)),$);
#23=IFCPROPERTYLISTVALUE('g',$,(IFCLABEL('p'),IFCINTEGER(3),IFCREAL(1.5)),$);
#24=IFCRELDEFINESBYPROPERTIES('0000000000000000000024',$,$,$,(#15),IFCPROPERTYSETDEFINITIONSET((#18,#25)));
#25=IFCPROPERTYSET('0000000000000000000025',$,$,$,(#20,#21,#20));
#26=IFCTRIMMEDCURVE(#27,(IFCPARAMETERVALUE(0.),#2),(#3,IFCPARAMETERVALUE(1.)),.T.,.PARAMETER.);
#27=IFCLINE(#2,$);
#28=IFCCARTESIANPOINTLIST3D(((0.,-0.,1.E-07),(1,2.5,3)));
#29=IFCTRIANGULATEDFACESET(#28,$,$,((1,2,3),(3,2,1)),$);
#30=IFCBSPLINESURFACE(1,1,((#2,#3,#2),(#3)),.UNSPECIFIED.,.T.,.F.,.U.);
#31=IFCPOLYLINE((#2,#3,#2,#2,#9,#8,#3,#3,#2,#9,#8,#3));
#32=IFCCARTESIANPOINT((0.,0.,0.));
#33=IFCCARTESIANPOINT((0.,0.,0.));
#34=IFCPOLYLINE((#2,#9999));
#35=IFCRELSPACEBOUNDARY2NDLEVEL('0000000000000000000035',$,$,$,$,$,$,.PHYSICAL.,.EXTERNAL.,$,#36);
#36=IFCRELSPACEBOUNDARY2NDLEVEL('0000000000000000000036',$,$,$,$,$,$,.PHYSICAL.,.EXTERNAL.,$,#35);
#37=IFCLOCALPLACEMENT(#37,$);
#38=IFCBLOBTEXTURE(.T.,.F.,$,$,$,'png',"15");
#39=IFCNOSUCHCLASS(1,'a',#2,(#3,$),IFCLABEL('x'));
#40=IFCMATERIAL('too few');
#41=(IFCA(1,#2)IFCB('x'));
"""


def settings_for(graph_target: GraphTarget, tmp_path: Path, **overrides: object) -> Settings:
    return conftest.test_settings(
        tmp_path,
        graph_dialect=graph_target.dialect,
        graph_uri=graph_target.uri,
        graph_user=graph_target.user,
        graph_password=graph_target.password,
        graph_connect_timeout_seconds=10.0,
        ifcgraph_enabled=True,
        ifcgraph_timeout_seconds=300,
        **overrides,
    )


async def through_the_graph(graph: Graph, source: Path, workdir: Path, *, as_nodes: bool) -> Path:
    """A file into the graph and out again, without the upload around it."""
    records = workdir / "records.jsonl"
    header = write_jsonl(source, records, lossless=True, include_geometry=as_nodes)
    await graph.run(
        "CREATE (:Model {id: 'model', state: 'done', lossless: true, skipped: $skipped, schema: $schema, ifc_header: $header})",
        skipped=header["skipped"],
        schema=header["schema"],
        header=header["ifc_header"],
    )
    await import_records(graph, "model", records)
    exported = workdir / "exported.jsonl"
    await export_records(graph, "model", exported)
    written = workdir / "written.ifc"
    write_records(exported, written)
    return written


BOTH_FORMS = pytest.mark.parametrize("as_nodes", [True, False], ids=["geometry as nodes", "geometry in blocks"])


@BOTH_FORMS
def test_a_file_comes_back_from_the_database_as_it_went_in(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path, as_nodes: bool
) -> None:
    settings = settings_for(graph_target, tmp_path)
    source = tmp_path / "hard.ifc"
    source.write_bytes(HEAD + HARD_VALUES.lstrip() + TAIL)

    async def work() -> Path:
        graph = make_graph(settings)
        try:
            await apply_schema(graph)
            return await through_the_graph(graph, source, tmp_path, as_nodes=as_nodes)
        finally:
            await graph.close()

    written = asyncio.run(work())
    comparison = compare(source.read_bytes(), written.read_bytes())
    assert comparison.identical, comparison.checks


@BOTH_FORMS
def test_a_large_value_and_a_real_model_come_back(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path, as_nodes: bool
) -> None:
    """A coordinate list of a megabyte, for what a batch and a property have to hold, next to a real model."""
    settings = settings_for(graph_target, tmp_path)
    points = b",".join(b"(%d.5,-0.,1.E-07)" % number for number in range(50_000))
    model = (conftest.FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes()
    large = model.replace(b"ENDSEC;\n\nEND-ISO", b"ENDSEC;\nEND-ISO").rsplit(b"ENDSEC;", 1)
    source = tmp_path / "large.ifc"
    source.write_bytes(large[0] + b"#900000=IFCCARTESIANPOINTLIST3D((" + points + b"));\nENDSEC;" + large[1])

    async def work() -> Path:
        graph = make_graph(settings)
        try:
            await apply_schema(graph)
            return await through_the_graph(graph, source, tmp_path, as_nodes=as_nodes)
        finally:
            await graph.close()

    written = asyncio.run(work())
    comparison = compare_files(source, written, geometry=False)
    assert comparison.identical, comparison.checks


@BOTH_FORMS
def test_an_upload_comes_back_builds_the_same_and_answers_the_same_queries(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path, as_nodes: bool
) -> None:
    """The whole way, as a server does it, with the viewpoint's link and the GTIN query from the documentation."""
    settings = settings_for(graph_target, tmp_path, ifcgraph_lossless=True, ifcgraph_include_geometry=as_nodes)

    async def work() -> tuple[dict, list[dict], list[dict], int, dict]:
        graph = make_graph(settings)
        storage = make_storage(settings)
        try:
            await apply_schema(graph)
            loaded = await seeding.seed(graph, storage=storage)
            model = await seeding.build_sample_graph(graph, storage, settings, loaded)
            links = await graph.run("MATCH (c:Component), (w:IfcWall {GlobalId: c.ifc_guid}) RETURN w.GlobalId AS guid")
            gtins = await graph.run(
                """
                MATCH (w:IfcWall)-[:IS_DEFINED_BY]->(:IfcRelDefinesByProperties)-[:RELATING_PROPERTY_DEFINITION]
                      ->(:IfcPropertySet {Name: 'Reuse'})-[:HAS_PROPERTIES]->(p:IfcPropertySingleValue {Name: 'GTIN'})
                RETURN w.GlobalId AS guid, p.NominalValue AS gtin
                """
            )
            service = IfcGraphService(graph, storage, settings)
            instances = await service.export(model["id"], tmp_path / "written.ifc")
            answer = await service.compare_with_upload(model["id"], tmp_path / "written.ifc", geometry=True)
            return model, links, gtins, instances, answer
        finally:
            await graph.close()

    model, links, gtins, instances, answer = asyncio.run(work())
    assert model["state"] == "done", model.get("error")
    assert model["lossless"] is True
    assert model["entities"] + model["skipped"] == instances == 248
    assert (model["skipped"] == 0) is as_nodes
    assert json.loads(model["ifc_header"])
    assert [link["guid"] for link in links] == [next(iter(seeding.SAMPLE_MODEL_WALLS))], "the viewpoint's wall"
    assert len(gtins) == 3 and all(row["gtin"] for row in gtins)
    assert answer["same_model"] is True and answer["identical"] is True, answer["checks"]
    assert {check["name"]: check["passed"] for check in answer["checks"]}["geometry"] is True


def test_an_edit_in_the_graph_shows_up_in_the_file(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    """The graph is what gets written, not a copy of the file."""
    settings = settings_for(graph_target, tmp_path)
    source = tmp_path / "small.ifc"
    source.write_bytes(
        HEAD
        + b"#1=IFCMATERIAL('before',$,$);\n#2=IFCDIRECTION((1.,0.));\n#3=IFCDIRECTION((0.,1.));\n"
        + b"#4=IFCPOLYLINE((#2,#3));\n"
        + TAIL
    )

    async def work() -> Path:
        graph = make_graph(settings)
        try:
            await apply_schema(graph)
            await through_the_graph(graph, source, tmp_path, as_nodes=True)
            await graph.run("MATCH (n:IfcMaterial {model_id: 'model'}) SET n.Name = 'after'")
            await graph.run(
                """
                MATCH (:IfcPolyline {model_id: 'model'})-[r:POINTS]->(t {step_id: 2})
                MATCH (:IfcPolyline {model_id: 'model'})-[s:POINTS]->(u {step_id: 3})
                SET r.position = 1, s.position = 0
                """
            )
            await export_records(graph, "model", tmp_path / "again.jsonl")
            write_records(tmp_path / "again.jsonl", tmp_path / "again.ifc")
            return tmp_path / "again.ifc"
        finally:
            await graph.close()

    written = asyncio.run(work()).read_bytes()
    assert b"#1=IFCMATERIAL('after',$,$);" in written
    assert b"#4=IFCPOLYLINE((#3,#2));" in written
    assert not compare(source.read_bytes(), written).same_model


def test_a_model_goes_with_its_blocks(graph_target: GraphTarget, clean_database: None, tmp_path: Path) -> None:
    settings = settings_for(graph_target, tmp_path)
    source = tmp_path / "small.ifc"
    source.write_bytes((conftest.FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())

    async def work() -> tuple[int, int, int, int]:
        graph = make_graph(settings)
        try:
            await apply_schema(graph)
            await through_the_graph(graph, source, tmp_path, as_nodes=False)
            blocks = (await graph.run("MATCH (b:StepBlock) RETURN count(b) AS n"))[0]["n"]
            texts = await graph.run("MATCH (:Model {id: 'model'})-[:HAS_STEP_BLOCK]->(b) RETURN b.instances AS n")
            await delete_model(graph, "model", keep_model=True)
            after_failure = (await graph.run("MATCH (b:StepBlock) RETURN count(b) AS n"))[0]["n"]
            await graph.run("MATCH (m:Model {id: 'model'}) DETACH DELETE m")
            await through_the_graph(graph, source, tmp_path, as_nodes=False)
            await delete_model(graph, "model")
            left = await graph.run("MATCH (n) WHERE n:StepBlock OR n:Entity OR n:Model RETURN count(n) AS n")
            return blocks, sum(row["n"] for row in texts), after_failure, left[0]["n"]
        finally:
            await graph.close()

    blocks, instances, after_failure, left = asyncio.run(work())
    assert blocks == 1 and instances > 0
    assert after_failure == 0
    assert left == 0


def test_a_lost_block_stops_the_export(graph_target: GraphTarget, clean_database: None, tmp_path: Path) -> None:
    """A file without the instances of one block would be a wrong file nobody can tell from a right one."""
    settings = settings_for(graph_target, tmp_path)
    source = tmp_path / "small.ifc"
    source.write_bytes((conftest.FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes())

    async def work() -> str:
        graph = make_graph(settings)
        try:
            await apply_schema(graph)
            await through_the_graph(graph, source, tmp_path, as_nodes=False)
            await graph.run("MATCH (b:StepBlock) DETACH DELETE b")
            with pytest.raises(NotExportable) as caught:
                await export_records(graph, "model", tmp_path / "out.jsonl")
            return str(caught.value)
        finally:
            await graph.close()

    # the number of instances in blocks depends on IFC-LPG's form (98 with geometry in blocks, fewer in the skeleton)
    assert re.search(r"of the \d+ instances", asyncio.run(work()))


@BOTH_FORMS
def test_a_model_survives_a_backup(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path, as_nodes: bool
) -> None:
    settings = settings_for(graph_target, tmp_path)
    source = tmp_path / "hard.ifc"
    source.write_bytes(HEAD + HARD_VALUES.lstrip() + TAIL)

    async def work() -> tuple[Path, int]:
        graph = make_graph(settings)
        storage = make_storage(settings)
        try:
            await apply_schema(graph)
            await through_the_graph(graph, source, tmp_path, as_nodes=as_nodes)
            manifest = await backup.export(graph, storage, tmp_path / "backup")
            await graph.run("MATCH (n) DETACH DELETE n")
            await backup.restore(graph, storage, tmp_path / "backup")
            await export_records(graph, "model", tmp_path / "again.jsonl")
            write_records(tmp_path / "again.jsonl", tmp_path / "again.ifc")
            return tmp_path / "again.ifc", manifest.skipped_nodes
        finally:
            await graph.close()

    again, skipped = asyncio.run(work())
    assert skipped == 0, "every node is in the backup"
    comparison = compare(source.read_bytes(), again.read_bytes())
    assert comparison.identical, comparison.checks


@pytest.mark.parametrize(
    ("lossless", "as_nodes"),
    [(False, False), (False, True), (True, False), (True, True)],
    ids=["ordinary", "ordinary with geometry", "geometry in blocks", "geometry as nodes"],
)
def test_deleting_a_project_leaves_nothing_of_its_models(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path, lossless: bool, as_nodes: bool
) -> None:
    """Its entities reach further into the graph than deleting what hangs off a project does."""
    settings = settings_for(graph_target, tmp_path, ifcgraph_lossless=lossless, ifcgraph_include_geometry=as_nodes)

    async def work() -> tuple[list[str], list[str]]:
        graph = make_graph(settings)
        storage = make_storage(settings)
        try:
            await apply_schema(graph)
            loaded = await seeding.seed(graph, storage=storage)
            await seeding.build_sample_graph(graph, storage, settings, loaded)
            checks = await graph.run("MATCH (r:Validation) RETURN r.state AS state")
            await ProjectRepository(graph).delete(loaded.projects["Building permit"])
            rows = await graph.run(
                """
                MATCH (n) WHERE n:Entity OR n:Model OR n:StepBlock OR n:Validation
                RETURN DISTINCT labels(n)[0] AS label
                """
            )
            return [row["state"] for row in checks], [row["label"] for row in rows]
        finally:
            await graph.close()

    checks, left = asyncio.run(work())
    assert checks == ["done"], "the sample model is checked against the IFC schema as an upload is"
    assert left == []


def test_the_command_line_writes_a_model_back_and_says_how_it_went(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_for(graph_target, tmp_path, ifcgraph_lossless=True)
    monkeypatch.setattr("opencde.cli._settings", lambda: settings)

    async def build() -> str:
        graph = make_graph(settings)
        storage = make_storage(settings)
        try:
            await apply_schema(graph)
            loaded = await seeding.seed(graph, storage=storage)
            model = await seeding.build_sample_graph(graph, storage, settings, loaded)
            await graph.run("CREATE (:Model {id: 'ordinary', state: 'done'})")
            return model["id"]
        finally:
            await graph.close()

    model_id = asyncio.run(build())
    target = tmp_path / "written.ifc"
    runner = CliRunner()

    done = runner.invoke(app, ["ifc-lpg", "export", model_id, str(target)])
    assert done.exit_code == 0, done.output
    assert "248 instances" in done.output
    assert compare((conftest.FIXTURES_DIR / "three_walls_gtin.ifc").read_bytes(), target.read_bytes()).identical

    done = runner.invoke(app, ["ifc-lpg", "export", model_id, str(target), "--verify", "--geometry"])
    assert done.exit_code == 0, done.output
    assert "OK      same_model" in done.output
    assert "OK      exact" in done.output
    assert "OK      georeference" in done.output
    assert "OK      geometry" in done.output

    other = tmp_path / "other.ifc"
    done = runner.invoke(app, ["ifc-lpg", "export", "ordinary", str(other)])
    assert done.exit_code == 1
    assert "OPENCDE_IFC_LPG_LOSSLESS" in done.output
    assert not other.exists()
    done = runner.invoke(app, ["ifcgraph", "export", "missing", str(other)])  # the old name still works
    assert done.exit_code == 1
    assert "no such model" in done.output


def sample_model_with(settings: Settings, *changes: str) -> str:
    """The sample model in the graph, as it is after these Cypher statements. ``$id`` is the model's id."""

    async def build() -> str:
        graph = make_graph(settings)
        storage = make_storage(settings)
        try:
            await apply_schema(graph)
            loaded = await seeding.seed(graph, storage=storage)
            model = await seeding.build_sample_graph(graph, storage, settings, loaded)
            for change in changes:
                await graph.run(change, id=model["id"])
            return model["id"]
        finally:
            await graph.close()

    return asyncio.run(build())


def test_a_valid_change_is_reported_as_a_change_and_as_valid(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_for(graph_target, tmp_path)
    monkeypatch.setattr("opencde.cli._settings", lambda: settings)
    model = sample_model_with(settings, "MATCH (n:IfcWall {model_id: $id}) SET n.Name = 'changed'")
    done = CliRunner().invoke(app, ["ifc-lpg", "export", model, str(tmp_path / "w.ifc"), "--verify"])
    assert done.exit_code == 1
    assert "DIFFERS same_model" in done.output
    assert "does not hold the same model" in done.output
    assert "OK      validation: 0 issues the upload does not have" in done.output

    done = CliRunner().invoke(app, ["ifc-lpg", "export", model, str(tmp_path / "w.ifc")])
    assert done.exit_code == 0, done.output


@pytest.mark.parametrize(
    ("change", "said"),
    [
        pytest.param(
            "MATCH (n:IfcWall {model_id: $id}) WITH n LIMIT 1 SET n.Name = 5",
            "",
            id="a number where the schema has a string",
        ),
        pytest.param(
            "MATCH (n:IfcWall {model_id: $id}) WITH n LIMIT 1 SET n.GlobalId = 'not a GlobalId'",
            "GlobalId",
            id="a GlobalId of the wrong form",
        ),
        pytest.param(
            "MATCH (n:IfcWall {model_id: $id}) WITH n LIMIT 1 REMOVE n.GlobalId",
            "",
            id="an attribute that is not optional gone",
        ),
        pytest.param(
            "MATCH (n:IfcWall {model_id: $id}) WITH n LIMIT 1 SET n.ObjectPlacement__step = 999999",
            "",
            id="a reference into a block to nothing",
        ),
        pytest.param(
            "MATCH (n:Entity {model_id: $id}) WHERE n:IfcMaterialLayerSet OR n:IfcMaterialLayer DETACH DELETE n",
            "",
            id="deleted nodes that others refer to",
        ),
    ],
)
def test_a_change_that_breaks_the_standard_is_stopped(
    graph_target: GraphTarget,
    clean_database: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    said: str,
) -> None:
    """A graph database has no schema to hold a change to, so this is where it gets held to one."""
    settings = settings_for(graph_target, tmp_path)
    monkeypatch.setattr("opencde.cli._settings", lambda: settings)
    done = CliRunner().invoke(app, ["ifc-lpg", "export", sample_model_with(settings, change), str(tmp_path / "w.ifc")])
    assert done.exit_code == 1, done.output
    assert "INVALID validation" in done.output
    assert "breaks the IFC standard" in done.output
    assert said in done.output


def test_validation_can_be_left_out(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_for(graph_target, tmp_path)
    monkeypatch.setattr("opencde.cli._settings", lambda: settings)
    model = sample_model_with(settings, "MATCH (n:IfcWall {model_id: $id}) WITH n LIMIT 1 SET n.Name = 5")
    done = CliRunner().invoke(app, ["ifc-lpg", "export", model, str(tmp_path / "w.ifc"), "--no-validate"])
    assert done.exit_code == 0, done.output
    assert "validation:" not in done.output


def test_a_model_that_does_not_hold_it_all_is_not_written(
    graph_target: GraphTarget, clean_database: None, tmp_path: Path
) -> None:
    settings = settings_for(graph_target, tmp_path)

    async def work() -> list[str]:
        graph = make_graph(settings)
        service = IfcGraphService(graph, make_storage(settings), settings)
        messages = []
        try:
            await apply_schema(graph)
            await graph.run("CREATE (:Model {id: 'ordinary', state: 'done'})")
            await graph.run("CREATE (:Model {id: 'running', state: 'running', lossless: true})")
            for model_id in ("ordinary", "running", "missing"):
                with pytest.raises(NotExportable) as caught:
                    await service.export(model_id, tmp_path / "out.ifc")
                messages.append(str(caught.value))
        finally:
            await graph.close()
        return messages

    ordinary, running, missing = asyncio.run(work())
    assert "OPENCDE_IFC_LPG_LOSSLESS" in ordinary, "Dataregium names its setting"
    assert "running" in running and "OPENCDE_" not in running
    assert "no such model" in missing
