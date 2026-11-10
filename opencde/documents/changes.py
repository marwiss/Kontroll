# This file was generated with the assistance of an AI coding tool.
"""The change set: the form of a proposed change to an IFC model, and its published schema (ADR 0021).

A change travels as the ``bim_snippet`` of a BCF 3.0 topic whose ``snippet_type`` is ``DataregiumIfcChangeSet`` and
whose ``reference_schema`` is ``GET /documents/1.0/ifc-changes/schema``: this module's model, as JSON Schema. The
snippet names its base version, who proposed it (and which AI model and tool call, where an AI did) and the changes,
each on one attribute of one instance: the instance by a GlobalId and a path from the rooted entity, or by its
STEP id only where no GlobalId reaches it (the owner's rule of 2026-11-10); the path is in IFC's attribute names
with indexes, such as ``IsDefinedBy[0].RelatingPropertyDefinition.HasProperties[2]``.
A change to an instance that several share changes it for all of them, unless ``copy`` asks for a copy. The server
checks the form here; what the changes do to the model is checked when a proposal is tried (the next step).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SNIPPET_TYPE = "DataregiumIfcChangeSet"
SCHEMA_PATH = "/documents/1.0/ifc-changes/schema"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
MAX_CHANGES = 10_000
MAX_CHANGE_SET_BYTES = 16 * 1024 * 1024

GUID = r"^[0-9A-Za-z_$]{22}$"
# A path from the rooted entity: attribute names, each with an index where the attribute is an aggregate.
PATH = r"^[A-Z][A-Za-z0-9]*(\[[0-9]+\])?(\.[A-Z][A-Za-z0-9]*(\[[0-9]+\])?)*$"
ATTRIBUTE = r"^[A-Z][A-Za-z0-9]*$"
IFC_TYPE = r"^Ifc[A-Za-z0-9]+$"
ENUMERATION = r"^[A-Z_][A-Z0-9_]*$"


Text = Annotated[str, StringConstraints(max_length=10_000)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(_Strict):
    """Another instance of the model, as a value: by a GlobalId and a path from it, or by its STEP id where no
    GlobalId reaches it."""

    step_id: int | None = Field(
        None, ge=1, description="The instance's number in the STEP file (`#123`); only where no GlobalId reaches it."
    )
    guid: str | None = Field(None, pattern=GUID, description="The GlobalId of a rooted entity.")
    path: str | None = Field(
        None, max_length=1000, pattern=PATH, description="From the rooted entity to the instance, where it is not it."
    )

    @model_validator(mode="after")
    def _one_of_step_id_and_guid(self) -> Reference:
        if (self.step_id is None) == (self.guid is None):
            raise ValueError("name the instance by step_id or by guid, not both and not neither")
        if self.path is not None and self.guid is None:
            raise ValueError("a path starts from a guid")
        return self


class Typed(_Strict):
    """A value of a defined type, such as `IfcLabel('Wall 1')` or `IfcLengthMeasure(3.2)`."""

    type: str = Field(pattern=IFC_TYPE, max_length=100)
    value: Text | float | bool


class Enumeration(_Strict):
    """An enumeration value, such as `.NOTDEFINED.`, written without its dots."""

    enum: str = Field(pattern=ENUMERATION, max_length=100)


# A value: a scalar, an instance, a typed or enumerated value, or an aggregate of them, which may itself hold
# aggregates (a list of coordinates); deeper nesting does not occur in IFC's attributes.
Item = Text | int | float | bool | None | Reference | Typed | Enumeration
Value = Item | list[Item | list[Item]]


class Change(_Strict):
    """One attribute of one instance: set to a value, or an aggregate's member added or removed; or an instance that
    only its STEP id names, deleted (IFC-LPG F13 a: what no GlobalId reaches)."""

    step_id: int | None = Field(
        None,
        ge=1,
        description="The instance changed, by its number in the STEP file; only where no GlobalId and path reach it.",
    )
    guid: str | None = Field(None, pattern=GUID, description="The rooted entity the path starts from.")
    path: str | None = Field(
        None,
        max_length=1000,
        pattern=PATH,
        description="From the rooted entity to the instance changed, in IFC's attribute names with indexes; absent "
        "when the rooted entity itself is changed.",
    )
    attribute: str | None = Field(
        None,
        pattern=ATTRIBUTE,
        max_length=100,
        description="The attribute changed, by its IFC name; none for `delete`.",
    )
    op: Literal["set", "add", "remove", "delete"] = Field(
        description="`set` gives the attribute a value; `add` and `remove` change one member of an aggregate; "
        "`delete` removes an instance named by its STEP id that nothing refers to."
    )
    index: int | None = Field(None, ge=0, description="The member added before, or removed; `add` appends without.")
    old: Value = Field(None, description="The value before, as the proposer saw it; checked when the change is tried.")
    new: Value = Field(None, description="The value after; `null` unsets.")
    copy_: bool = Field(
        False,
        alias="copy",
        description="Change a copy of the instance, for the rooted entity alone, instead of the instance that several "
        "may share.",
    )

    @model_validator(mode="after")
    def _consistent(self) -> Change:
        if (self.step_id is None) == (self.guid is None):
            raise ValueError("name the instance by step_id or by guid, not both and not neither")
        if self.path is not None and self.guid is None:
            raise ValueError("a path starts from a guid")
        if self.op == "delete":
            if self.step_id is None:
                raise ValueError("delete names an instance by its step_id: one that no GlobalId reaches")
            if self.attribute is not None or self.index is not None or self.new is not None or self.copy_:
                raise ValueError("delete takes no attribute, index, new value or copy")
            return self
        if self.attribute is None:
            raise ValueError("set, add and remove name the attribute they change")
        if self.op == "remove" and self.index is None and self.old is None:
            raise ValueError("remove names the member by index or by its old value")
        return self


class Base(_Strict):
    """The document version the changes were made against."""

    document_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    version_index: int = Field(ge=1, le=1_000_000_000)


class Provenance(_Strict):
    """Who proposed the change, and with what."""

    user: str = Field(min_length=1, max_length=200, description="The user name of the proposer.")
    ai_model: str | None = Field(None, max_length=200, description="The AI model that proposed it, where one did.")
    tool_call: str | None = Field(None, max_length=200, description="The tool call the AI made, where one did.")
    created_at: str | None = Field(None, max_length=40, description="When it was proposed, ISO 8601 in UTC.")


class IfcChangeSet(_Strict):
    """A proposed change to an IFC model: its base, its provenance and its changes (ADR 0021)."""

    schema_: str = Field(
        alias="schema", max_length=1000, description="The address of this schema, as the topic's `reference_schema`."
    )
    base: Base
    provenance: Provenance
    changes: list[Change] = Field(min_length=1, max_length=MAX_CHANGES)


def change_set_schema(public_url: str) -> dict[str, Any]:
    """The change set as JSON Schema 2020-12, with its `$id` on this server."""
    schema = IfcChangeSet.model_json_schema(mode="validation")
    return {"$schema": SCHEMA_DIALECT, "$id": f"{public_url}{SCHEMA_PATH}", **schema, "title": SNIPPET_TYPE}


def problems(data: Any) -> list[str]:
    """What keeps `data` from being a change set, in words that never repeat the data; empty when it is one."""
    from pydantic import ValidationError

    try:
        IfcChangeSet.model_validate(data)
    except ValidationError as exc:
        found: list[str] = []
        for error in exc.errors(include_input=False, include_url=False):
            # The location up to the field: the names of the union's members that follow say nothing to a client.
            pieces: list[str] = []
            for piece in error.get("loc", ()):
                if isinstance(piece, str) and not piece.replace("_", "").isalpha():
                    break
                pieces.append(str(piece))
            problem = f"{'.'.join(pieces) or 'change set'}: {error.get('msg', 'invalid')}"
            if problem not in found:
                found.append(problem)
        return found[:5]
    return []
