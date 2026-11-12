# This file was generated with the assistance of an AI coding tool.
"""The change sets of the MCP endpoint (ADR 0028, the design's §2): open one, fill it step by step, propose it.

``open_changeset`` makes a draft (``store/jobs/drafts.py``) on a version of an IFC document and answers its handle,
``changeset_id``. The write tools are Dataspatium's, in its order, each with its schema unchanged and
``changeset_id`` beside it, and a call becomes one operation of ``ops`` exactly as the app's ``build()`` makes it
(``write_tools.py``, a copy); ``manage_changeset`` lists the steps and removes the last or all, and
``change_attribute`` adds a post in ``changes``, checked as the change set's schema checks it. ``propose_changes``
makes the topic with the change set as its snippet and queues its trial through the code the server's own proposals
use (``documents/proposing.py``), never through HTTP; a later call with the same handle puts the change set as it is
then on the same topic and tries it again. A person approves it in Dataspatium: no tool approves.

Every call needs ``mcp:propose``, the role ``editor`` or ``manager`` in the draft's project, checked each time as REST
checks it (F35 a; ``mcp.denied`` with the reason ``role`` otherwise), the project's AI policy, and a draft that is the
caller's: an unknown or expired handle asks the AI to open a new one. The audit log records ``mcp.changeset.opened``
and ``mcp.changeset.proposed`` with identifiers and counts, never an argument or a text but the AI model it names.
"""

from __future__ import annotations

import copy
import functools
import operator
from collections.abc import Callable
from dataclasses import replace
from typing import Annotated, Any, Literal

from fastapi import HTTPException
from pydantic import AfterValidator, AllowInfNan, ConfigDict, Field, Strict, WithJsonSchema, create_model

from opencde.accounts.roles import PROPOSER, Role, at_least
from opencde.auth.scopes import MCP_PROPOSE
from opencde.bcf.schemas import TEXT_MAX
from opencde.documents.changes import ATTRIBUTE, GUID, OPS_FORM, PATH, SCHEMA_PATH, SNIPPET_TYPE
from opencde.documents.changes import problems as change_set_problems
from opencde.documents.proposing import Proposing
from opencde.ids import is_uuid, normalize_guid
from opencde.ifcgraph.service import IfcGraphService
from opencde.mcp import write_tools
from opencde.mcp.registry import Arguments, Tool, ToolContext, ToolRefusal, member_project
from opencde.store.accounts.projects import ProjectRepository
from opencde.store.bcf.topic_links import TopicLinkRepository
from opencde.store.bcf.topics import TopicRepository
from opencde.store.documents.versions import DocumentRepository
from opencde.store.jobs.drafts import MAX_OPEN, MAX_STEPS, ChangeSetDraft, ChangeSetDraftRepository, DraftRefused
from opencde.timeutil import now_iso

UNKNOWN = (
    "There is no open change set with this changeset_id: it is unknown, someone else's, or it expired 24 hours after "
    "its last use. Open a new one with open_changeset."
)
NO_DOCUMENT = "There is no document with this id among your projects"
MODULE_OFF = "Change sets are not tried on this server: the IFC-LPG module is off"
REFERENCE = "changes.json"  # the snippet's file name, as Dataspatium names it
MAX_AUDIT_TEXT = 100  # how much of the AI model it names goes to the audit log
#: What ``tool_call`` holds in the provenance, as Dataspatium writes it: the steps' tools after this.
TOOL_CALL_PREFIX = "mcp:"

TITLES = {
    "create_storeys_and_grid": "Add storeys and a grid",
    "define_type": "Define a type",
    "create_wall": "Add a wall",
    "create_slab": "Add a slab",
    "create_roof": "Add a roof",
    "create_opening": "Cut an opening",
    "create_element": "Add a building element",
    "create_spaces": "Make the rooms spaces",
    "set_properties": "Set properties",
    "set_classification": "Classify elements",
    "assign": "Assign a storey or a material",
    "edit_element": "Change an element in place",
    "transform_elements": "Move elements",
    "delete_elements": "Delete elements",
    "set_site": "Place the model on earth",
    "manage_changeset": "List or mend the change set",
}

ChangesetId = Annotated[
    str, Field(max_length=64, description="The change set's handle, as open_changeset gave it; the step joins it.")
]


class ChangesetArguments(Arguments):
    """The arguments of a tool on an open change set: its handle first."""

    changeset_id: ChangesetId


def _drafts(context: ToolContext) -> ChangeSetDraftRepository:
    return ChangeSetDraftRepository(context.graph)


async def _proposer(context: ToolContext, project_id: str, role: Role) -> None:
    """The role that proposes change sets, ``editor`` or higher (F35 a), as REST's ``require_proposer``."""
    if not at_least(role, PROPOSER):
        await context.deny(
            "role",
            f"Your role in this project, {role.value}, does not propose change sets; that takes the role editor or "
            "manager",
            project_id=project_id,
        )


async def _owned(context: ToolContext, changeset_id: str) -> ChangeSetDraft:
    """The caller's open draft, in a project that this server may give to AI tools and where the caller proposes."""
    found = None
    if is_uuid(changeset_id):
        found = await _drafts(context).get(user_id=context.principal.user_id, changeset_id=normalize_guid(changeset_id))
    if found is None:
        raise ToolRefusal(UNKNOWN)
    _project, role = await member_project(context, found.project_id)
    await _proposer(context, found.project_id, role)
    return found


async def _change(
    context: ToolContext, draft: ChangeSetDraft, change: Callable[[ChangeSetDraft], ChangeSetDraft]
) -> ChangeSetDraft:
    """The draft changed in one transaction, as it is when the change is made."""
    try:
        changed = await _drafts(context).update(
            user_id=context.principal.user_id, changeset_id=draft.changeset_id, change=change
        )
    except DraftRefused as refused:
        raise ToolRefusal(str(refused)) from None
    if changed is None:
        raise ToolRefusal(UNKNOWN)
    return changed


# -- open_changeset ---------------------------------------------------------------------------------------------------


class OpenChangesetArguments(Arguments):
    document_id: str = Field(max_length=64, description="The IFC document to change, as list_models gives it.")
    version_index: int | None = Field(
        ge=1, le=1_000_000_000, description="The version the changes build on; null for the latest."
    )


async def open_changeset(context: ToolContext, arguments: OpenChangesetArguments) -> dict[str, Any]:
    user_id = context.principal.user_id
    documents = DocumentRepository(context.graph)
    document_id = normalize_guid(arguments.document_id) if is_uuid(arguments.document_id) else None
    latest = await documents.latest(user_id=user_id, document_id=document_id) if document_id else None
    if latest is None or document_id is None:
        raise ToolRefusal(NO_DOCUMENT)
    _project, role = await member_project(context, latest.project_id)
    await _proposer(context, latest.project_id, role)
    version, wanted = latest, arguments.version_index
    if wanted is not None and wanted != latest.version_index:
        version = await documents.version(user_id=user_id, document_id=document_id, version_index=wanted)
    if version is None:
        raise ToolRefusal("The document has no version with this version_index")
    if not IfcGraphService.wants(version.file_name):
        raise ToolRefusal("The version is no IFC model (.ifc or .ifczip): a change set changes an IFC model")
    draft = await _drafts(context).open(
        user_id=user_id, project_id=latest.project_id, document_id=document_id, version_index=version.version_index
    )
    if draft is None:
        raise ToolRefusal(
            f"You have {MAX_OPEN} open change sets, the most one user has. Propose one of them, or wait: each closes "
            "24 hours after its last use."
        )
    await context.record(
        "mcp.changeset.opened",
        project_id=draft.project_id,
        document_id=draft.document_id,
        version_index=draft.version_index,
        changeset_id=draft.changeset_id,
    )
    return {
        "changeset_id": draft.changeset_id,
        "base": draft.base,
        "expires_at": draft.expires_at,
        "max_steps": MAX_STEPS,
    }


OPEN_CHANGESET = Tool(
    name="open_changeset",
    title="Open a change set",
    description=(
        "Open a change set on a version of an IFC document of a project where you are an editor or a manager: the "
        "write tools then add its steps, manage_changeset lists and mends them, and propose_changes makes it a "
        "proposal that the server tries on the version and a person approves. Answers its changeset_id, the base "
        "(document_id and version_index), when it closes (expires_at, 24 hours after its last use) and max_steps "
        f"({MAX_STEPS}). A user has at most {MAX_OPEN} open."
    ),
    arguments=OpenChangesetArguments,
    run=open_changeset,
    scope=MCP_PROPOSE,
    read_only=False,
    needs_ifcgraph=True,
)


# -- the write tools, with Dataspatium's schemas ---------------------------------------------------------------------

_EXACT = 2**53  # the integers a double holds exactly; a larger one is read as a double, as JavaScript reads it
_Int = Annotated[int, Strict(), Field(ge=-_EXACT, le=_EXACT)]
_Float = Annotated[float, Strict(), AllowInfNan(False)]


def _whole(value: float) -> int:
    """JSON Schema's integer: a number without a fraction, 2.0 as well as 2."""
    if not float(value).is_integer():
        raise ValueError("must be a whole number")
    if abs(value) > _EXACT:
        raise ValueError("must be at most 2^53")
    return int(value)


_Whole = Annotated[_Int | _Float, AfterValidator(_whole)]
_KINDS: dict[str, Any] = {
    "string": Annotated[str, Strict()],
    "boolean": Annotated[bool, Strict()],
    "integer": _Whole,
    "null": type(None),
}
# The forms that make the types at run time, from the app's schemas.
_LIST: Any = list
_ANNOTATED: Any = Annotated


def _python(schema: dict[str, Any], name: str) -> Any:
    """The type that takes what a JSON schema of Dataspatium's takes, and keeps a number as JSON wrote it."""
    options: list[Any] = []
    for kind in schema["type"] if isinstance(schema["type"], list) else [schema["type"]]:
        if kind == "number":
            options += [_Int, _Float]
        elif kind == "array":
            options.append(_LIST[_python(schema["items"], name)])
        elif kind == "object":
            fields: dict[str, Any] = {
                key: (_python(sub, f"{name}_{key}"), ...) for key, sub in schema["properties"].items()
            }
            options.append(create_model(name, __config__=ConfigDict(extra="forbid", frozen=True), **fields))
        else:
            options.append(_KINDS[kind])
    return functools.reduce(operator.or_, options)


def arguments_of(spec: dict[str, Any]) -> type[ChangesetArguments]:
    """A write tool's arguments: ``changeset_id``, and the app's parameters with their schema as the app gives it."""
    camel = "".join(part.title() for part in spec["name"].split("_"))
    fields: dict[str, Any] = {
        key: (_ANNOTATED[_python(sub, f"{camel}_{key}"), WithJsonSchema(copy.deepcopy(sub))], ...)
        for key, sub in spec["properties"].items()
    }
    return create_model(f"{camel}Arguments", __base__=ChangesetArguments, **fields)


async def _step(context: ToolContext, changeset_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """One call of a write tool on the caller's draft, as the app's ``call()`` makes it: an operation appended with
    its ref, or the steps listed or removed; the app's error is the tool's."""
    draft = await _owned(context, changeset_id)
    answer: dict[str, Any] = {}

    def add(found: ChangeSetDraft) -> ChangeSetDraft:
        cs = {"ops": list(found.steps), "refs": found.refs}
        out = write_tools.call(cs, name, arguments)
        if "error" in out:
            raise ToolRefusal(str(out["error"]))
        answer.clear()
        answer.update(out)
        return replace(found, steps=cs["ops"], refs=cs["refs"])

    await _change(context, draft, add)
    return answer


def _write_tool(spec: dict[str, Any]) -> Tool:
    name = spec["name"]

    async def run(context: ToolContext, arguments: ChangesetArguments) -> dict[str, Any]:
        return await _step(context, arguments.changeset_id, name, arguments.model_dump(exclude={"changeset_id"}))

    return Tool(
        name=name,
        title=TITLES[name],
        description=spec["description"],
        arguments=arguments_of(spec),
        run=run,
        scope=MCP_PROPOSE,
        read_only=False,
        needs_ifcgraph=True,
    )


WRITE_TOOLS: tuple[Tool, ...] = tuple(_write_tool(spec) for spec in write_tools.TOOLS)


# -- change_attribute -------------------------------------------------------------------------------------------------

_VALUES = ["string", "number", "boolean", "null", "object", "array"]
_FORMS = (
    "A value as the change set's schema writes one: a string, a number, a boolean or null; another instance as "
    '{"guid", "path"} or {"step_id"}; a defined type as {"type": "IfcLabel", "value": …}; an enumeration as '
    '{"enum": "NOTDEFINED"}; or a list of these.'
)
OLD = {
    "type": _VALUES,
    "description": "The value before, as you saw it, checked when the change is tried; null leaves it unchecked. "
    + _FORMS,
}
NEW = {"type": _VALUES, "description": "The value after; null unsets. " + _FORMS}


class ChangeAttributeArguments(ChangesetArguments):
    guid: str | None = Field(
        pattern=GUID,
        description="The GlobalId of the rooted entity the change starts from, as the base version has it; null "
        "where only step_id names the instance. A ref (new-1 …) is not taken: the changes are to the base's "
        "instances.",
    )
    step_id: int | None = Field(
        ge=1, description="The instance's number in the STEP file, only where no GlobalId reaches it; else null."
    )
    path: str | None = Field(
        max_length=1000,
        pattern=PATH,
        description="From the rooted entity to the instance changed, in IFC's attribute names with indexes, such as "
        "IsDefinedBy[0].RelatingPropertyDefinition.HasProperties[2]; null for the rooted entity itself.",
    )
    attribute: str = Field(
        max_length=100, pattern=ATTRIBUTE, description="The attribute changed, by its IFC name, such as Name."
    )
    op: Literal["set", "add", "remove"] = Field(
        description="set gives the attribute a value; add and remove change one member of an aggregate."
    )
    index: int | None = Field(ge=0, description="The member added before, or removed; null appends, or removes by old.")
    old: Annotated[Any, WithJsonSchema(OLD)]
    new: Annotated[Any, WithJsonSchema(NEW)]
    copy_: bool | None = Field(
        alias="copy",
        description="true changes a copy of the instance for the rooted entity alone, where several share it; null "
        "or false the shared instance.",
    )


def _plain(problem: str) -> str:
    """A problem of the one change, without the place in the change set the AI did not write."""
    for prefix, instead in (("changes.0.", ""), ("changes.0:", "the change:")):
        if problem.startswith(prefix):
            return instead + problem[len(prefix) :]
    return problem


async def change_attribute(context: ToolContext, arguments: ChangeAttributeArguments) -> dict[str, Any]:
    draft = await _owned(context, arguments.changeset_id)
    given = {
        "guid": arguments.guid,
        "step_id": arguments.step_id,
        "path": arguments.path,
        "attribute": arguments.attribute,
        "op": arguments.op,
        "index": arguments.index,
    }
    change: dict[str, Any] = {key: value for key, value in given.items() if value is not None}
    change |= {"old": arguments.old, "new": arguments.new} | ({"copy": True} if arguments.copy_ else {})
    probe = {"schema": SCHEMA_PATH, "base": draft.base, "provenance": {"user": "-"}, "changes": [change]}
    found = change_set_problems(probe)
    if found:
        raise ToolRefusal("The change is not one: " + "; ".join(_plain(problem) for problem in found))
    answer: dict[str, Any] = {}

    def add(fresh: ChangeSetDraft) -> ChangeSetDraft:
        if len(fresh.steps) >= write_tools.MAX_OPS:
            raise ToolRefusal(
                f"the change set holds {write_tools.MAX_OPS} steps already; ask the person to approve it first"
            )
        step = {"tool": write_tools.CHANGE_ATTRIBUTE, "change": change}
        answer.update(ok=True, step=len(fresh.steps) + 1, description=write_tools.describe(step))
        return replace(fresh, steps=[*fresh.steps, step])

    await _change(context, draft, add)
    return answer


CHANGE_ATTRIBUTE = Tool(
    name="change_attribute",
    title="Change an attribute",
    description=(
        "Add a step that changes one attribute of one instance of the base version, as a post in the change set's "
        "changes: the instance by the GlobalId of a rooted entity and a path from it, or by its STEP id only where "
        "no GlobalId reaches it; set gives a value, add and remove change one member of an aggregate. old is "
        "checked when the change set is tried. For what the write tools do (walls, openings, properties, storeys, "
        "moves, deletions), use them instead. Answers the step and its description, as the write tools do."
    ),
    arguments=ChangeAttributeArguments,
    run=change_attribute,
    scope=MCP_PROPOSE,
    read_only=False,
    needs_ifcgraph=True,
)


# -- propose_changes --------------------------------------------------------------------------------------------------


class ProposeChangesArguments(ChangesetArguments):
    title: str = Field(
        min_length=1, max_length=200, description="The topic's title, what the person reads first: what it changes."
    )
    description: str | None = Field(
        max_length=TEXT_MAX,
        description="The topic's description: why, and what to look at; null for the steps' own lines.",
    )
    ai_model: str | None = Field(
        max_length=200,
        description="The AI model that made the change set, as you know yourself; kept with the proposal and in the "
        "version's metadata when it is approved, never checked.",
    )


async def _topic_of(context: ToolContext, draft: ChangeSetDraft) -> str | None:
    """The topic the draft was proposed on, while it is there and still carries a change set."""
    if not draft.topic_guid:
        return None
    topics = TopicRepository(context.graph, id_prefix=context.settings.server_assigned_id_prefix)
    topic = await topics.get(user_id=context.principal.user_id, project_id=draft.project_id, guid=draft.topic_guid)
    if topic is None or topic.bim_snippet is None or topic.bim_snippet.snippet_type != SNIPPET_TYPE:
        return None
    return topic.guid


async def propose_changes(context: ToolContext, arguments: ProposeChangesArguments) -> dict[str, Any]:
    draft = await _owned(context, arguments.changeset_id)
    if context.ifcgraph is None or context.storage is None:
        raise ToolRefusal(MODULE_OFF)
    ops, changes = write_tools.to_wheel(draft.steps), write_tools.changes(draft.steps)
    if not ops and not changes:
        raise ToolRefusal("The change set is empty: add a step with a write tool or change_attribute first")
    public_url = context.settings.public_url
    tools = ",".join(str(step["tool"]) for step in draft.steps)
    change_set: dict[str, Any] = {
        "schema": f"{public_url}{SCHEMA_PATH}",
        "base": draft.base,
        "provenance": {
            "user": context.principal.username,
            "ai_model": arguments.ai_model or None,
            "tool_call": f"{TOOL_CALL_PREFIX}{tools}"[:200],
            "created_at": now_iso(),
        },
        "changes": changes,
    }
    if ops:
        change_set |= {"ops_form": OPS_FORM, "ops": ops}
    found = change_set_problems(change_set)
    if found:
        raise ToolRefusal("The change set is not one: " + "; ".join(found))
    topics = TopicRepository(context.graph, id_prefix=context.settings.server_assigned_id_prefix)
    proposing = Proposing(
        topics=topics,
        links=TopicLinkRepository(context.graph, topics),
        projects=ProjectRepository(context.graph),
        storage=context.storage,
        ifcgraph=context.ifcgraph,
        public_url=public_url,
    )
    author = context.principal.username
    topic_guid = await _topic_of(context, draft)
    try:
        if topic_guid is not None:
            await proposing.snippet(
                project_id=draft.project_id,
                topic_guid=topic_guid,
                author=author,
                change_set=change_set,
                reference=REFERENCE,
            )
        else:
            topic = await proposing.topic(
                project_id=draft.project_id,
                author=author,
                title=arguments.title,
                description=arguments.description
                or "\n".join(write_tools.describe(step) for step in draft.steps)[:TEXT_MAX],
                change_set=change_set,
                reference=REFERENCE,
            )
            topic_guid = topic.guid
    except HTTPException as refused:
        if refused.status_code != 400:
            raise
        raise ToolRefusal(
            "This project's topics do not take a change set (DataregiumIfcChangeSet) as their snippet; a manager of "
            "the project can allow it"
        ) from None
    proposed: str = topic_guid

    def on_topic(fresh: ChangeSetDraft) -> ChangeSetDraft:
        return replace(fresh, topic_guid=proposed)

    await _change(context, draft, on_topic)
    await context.record(
        "mcp.changeset.proposed",
        project_id=draft.project_id,
        document_id=draft.document_id,
        version_index=draft.version_index,
        changeset_id=draft.changeset_id,
        topic_guid=proposed,
        ops=len(ops),
        changes=len(changes),
        ai_model=(arguments.ai_model or "")[:MAX_AUDIT_TEXT] or None,
    )
    return {
        "project_id": draft.project_id,
        "topic_guid": proposed,
        "state": "queued",
        "ops": len(ops),
        "changes": len(changes),
    }


PROPOSE_CHANGES = Tool(
    name="propose_changes",
    title="Propose the change set",
    description=(
        "Propose the change set: a BCF topic in its project with the change set as its snippet, which the server "
        "tries on the base version (get_proposal reports the trial) and a person approves in Dataspatium; no tool "
        "approves. Calling it again with the same changeset_id, after mending the steps, puts the change set as it "
        "is then on the same topic and tries it again; the topic keeps its title and description. Answers the "
        "project_id, the topic_guid, the trial's state (queued) and how many operations and changes it holds."
    ),
    arguments=ProposeChangesArguments,
    run=propose_changes,
    scope=MCP_PROPOSE,
    read_only=False,
    needs_ifcgraph=True,
)

#: In Dataspatium's order: the handle, the write tools with manage_changeset last, the server's own step, the proposal.
CHANGE_SET_TOOLS: tuple[Tool, ...] = (OPEN_CHANGESET, *WRITE_TOOLS, CHANGE_ATTRIBUTE, PROPOSE_CHANGES)
