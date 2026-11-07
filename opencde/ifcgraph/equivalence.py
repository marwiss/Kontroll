# This file was generated with the assistance of an AI coding tool.
"""Whether two IFC files hold the same model: ``python -m opencde.ifcgraph.equivalence A B [--geometry]``.

"The same model" means there is a pairing of the instances of the two files in which paired instances have the same
class and the same values, their references lead to paired instances, every LIST has its order, and every SET and BAG
has the same members. Instance ids, the order of the file, layout and how a value is spelled do not count. REALs are
compared by their bits, with no tolerance. ADR 0009 says why.

"Identical" asks more: the same ids and the same order in SETs too, with the same header. That is what a store that
keeps a file's ids can promise, and it implies the same model.

Hashes over forward references alone, which is what the published methods use, miss styles swapped between two equal
shapes, and anything in a cycle of references. So the check here refines classes of instances in both directions until
they are stable, in one graph over both files, and ends by building the pairing and checking it value by value: "the
same" is only ever said of a pairing that was checked. Where instances are alike all the way (two equal properties in
one SET), one of each file is paired by choice and refinement goes on, going back on the choice if it leads nowhere.
A limit on that search means the answer can also be that nothing could be shown, which never counts as the same.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from array import array
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from opencde.ifcgraph.schema import Schema
from opencde.ifcgraph.step import StepError, StepFile, exact_text

MAX_FAILED_PAIRINGS = 10_000
MAX_EXPANDED_VALUES = 1_000_000
_UNORDERED = frozenset(("set", "bag"))
_REFERENCE = b"#"
_NOTHING_THERE = b"#?"
_SOURCE_BITS = 32
_SOURCE_MASK = (1 << _SOURCE_BITS) - 1
_MAX_SHOWN = 5

# What says where a model is, by class, with the attributes that say it (None for all of them). Everything here also
# falls under the same-model check; this names it, and it is what stands between a report and "the model moved 1 km".
_GEOREFERENCE: dict[bytes, tuple[str, ...] | None] = {
    b"IFCMAPCONVERSION": None,
    b"IFCMAPCONVERSIONSCALED": None,
    b"IFCRIGIDOPERATION": None,
    b"IFCPROJECTEDCRS": None,
    b"IFCGEOGRAPHICCRS": None,
    b"IFCGEOMETRICREPRESENTATIONCONTEXT": None,
    b"IFCGEOMETRICREPRESENTATIONSUBCONTEXT": None,
    b"IFCSITE": ("ObjectPlacement", "RefLatitude", "RefLongitude", "RefElevation", "SiteAddress"),
    b"IFCPROJECT": ("UnitsInContext",),
}
_GEOREFERENCE_PROPERTY_SETS = frozenset((b"s19:ePSet_MapConversion", b"s18:ePSet_ProjectedCRS"))  # how IFC2X3 says it
_HEX_FLOAT = re.compile(rb"r(-?0x[0-9a-f.]+p[+-]\d+)")


@dataclass(frozen=True)
class Check:
    """One question. ``passed`` is None when it could not be answered, which counts as not passed."""

    name: str
    passed: bool | None
    detail: str = ""


@dataclass(frozen=True)
class Comparison:
    checks: tuple[Check, ...]

    def passed(self, name: str) -> bool | None:
        return next((check.passed for check in self.checks if check.name == name), None)

    @property
    def same_model(self) -> bool:
        return self.passed("same_model") is True

    @property
    def identical(self) -> bool:
        return self.passed("exact") is True and self.passed("header") is True

    def to_dict(self) -> dict[str, Any]:
        return {
            "same_model": self.same_model,
            "identical": self.identical,
            "checks": [asdict(check) for check in self.checks],
        }


def _kinds_of_type(schema: Schema, keyword: bytes) -> tuple[str, ...]:
    """The aggregates of a typed value. What the schema has no such type for counts as ordered."""
    shape = schema.defined_type(keyword)
    return shape[0] if shape else ()


class _Matching:
    """The instances of two files as one graph, split into classes until each holds one instance from either file.

    A class stays balanced, with as many instances from one file as from the other, for as long as a pairing can
    exist: refinement treats alike what is alike, so an unbalanced class shows that none does.
    """

    def __init__(self, first: StepFile, second: StepFile, schema: Schema) -> None:
        self.files = (first, second)
        self.schema = schema
        self.split = len(first)
        self.ids = array("Q", first.ids() + second.ids())
        size = len(self.ids)
        self.ordered: list[tuple[int, ...]] = [()] * size
        self.unordered: list[tuple[tuple[int, ...], ...]] = [()] * size
        self.incoming: list[list[int]] = [[] for _ in range(size)]
        self.skeleton = array("I", [0]) * size
        self.members: list[set[int]] = []
        self.balance: list[int] = []
        self.tied: set[int] = set()
        self.log: list[tuple[int, int]] = []
        skeletons: dict[bytes, int] = {}
        self._compile(first, 0, skeletons)
        self._compile(second, self.split, skeletons)
        self.colour = array("I", self.skeleton)
        for _ in skeletons:
            self.members.append(set())
            self.balance.append(0)
        for node, cls in enumerate(self.colour):
            self.members[cls].add(node)
            self.balance[cls] += 1 if node < self.split else -1
        for cls in range(len(self.members)):
            self._note_tie(cls)

    def _compile(self, file: StepFile, base: int, skeletons: dict[bytes, int]) -> None:
        nodes = {step_id: base + offset for offset, step_id in enumerate(file.ids())}
        for step_id, keyword, parameters in file:
            node = nodes[step_id]
            ordered: list[int] = []
            groups: list[tuple[int, ...]] = []
            attributes = self.schema.attributes(keyword) or ()
            parts = [keyword]
            for position, value in enumerate(parameters):
                if isinstance(value, bytes):
                    parts.append(value)
                else:
                    kinds = attributes[position].kinds if position < len(attributes) else ()
                    parts.append(self._fold(value, kinds, nodes, ordered, groups))
            self.skeleton[node] = skeletons.setdefault(b"|".join(parts), len(skeletons))
            if ordered:
                self.ordered[node] = tuple(ordered)
            if groups:
                self.unordered[node] = tuple(groups)
            for slot, target in enumerate(ordered):
                self.incoming[target].append((slot * 2) << _SOURCE_BITS | node)
            for slot, group in enumerate(groups):
                for target in group:
                    self.incoming[target].append((slot * 2 + 1) << _SOURCE_BITS | node)

    def _fold(
        self,
        value: Any,
        kinds: tuple[str, ...],
        nodes: dict[int, int],
        ordered: list[int],
        groups: list[tuple[int, ...]],
    ) -> bytes:
        """A value as text without its references, which go to ``ordered`` and ``groups``."""
        if isinstance(value, bytes):
            return value
        if isinstance(value, int):
            node = nodes.get(value)
            if node is None:
                return _NOTHING_THERE
            ordered.append(node)
            return _REFERENCE
        if isinstance(value, tuple):
            keyword, items = value
            inner = _kinds_of_type(self.schema, keyword)
            return b"%s(%s)" % (keyword, b",".join([self._fold(item, inner, nodes, ordered, groups) for item in items]))
        rest = kinds[1:]
        if kinds and kinds[0] in _UNORDERED:
            parts = self._fold_unordered(value, rest, nodes, groups)
            if parts is not None:
                return b"(%s)" % b",".join(parts)
        return b"(%s)" % b",".join([self._fold(item, rest, nodes, ordered, groups) for item in value])

    def _fold_unordered(
        self, value: list[Any], kinds: tuple[str, ...], nodes: dict[int, int], groups: list[tuple[int, ...]]
    ) -> list[bytes] | None:
        """The sorted members of a SET or BAG, or None when a member holds references inside it, which no IFC schema
        allows (a test reads them all). Such a SET then counts as ordered, which can only ever say "not the same"."""
        parts: list[bytes] = []
        members: list[int] = []
        for item in value:
            if isinstance(item, int):
                node = nodes.get(item)
                if node is None:
                    parts.append(_NOTHING_THERE)
                else:
                    members.append(node)
                    parts.append(_REFERENCE)
                continue
            inside: list[int] = []
            nested: list[tuple[int, ...]] = []
            part = self._fold(item, kinds, nodes, inside, nested)
            if inside or nested:
                return None
            parts.append(part)
        parts.sort()
        if members:
            groups.append(tuple(members))
        return parts

    def _note_tie(self, cls: int) -> None:
        if len(self.members[cls]) > 2:
            self.tied.add(cls)
        else:
            self.tied.discard(cls)

    def _split_off(self, cls: int, nodes: list[int]) -> int:
        """Move ``nodes`` to a new class, and remember how to undo that."""
        fresh = len(self.members)
        moved = set(nodes)
        self.members.append(moved)
        self.members[cls] -= moved
        delta = 0
        colour = self.colour
        for node in nodes:
            colour[node] = fresh
            delta += 1 if node < self.split else -1
        self.balance.append(delta)
        self.balance[cls] -= delta
        self.log.append((cls, fresh))
        self._note_tie(cls)
        self._note_tie(fresh)
        return fresh

    def _undo(self, mark: int) -> None:
        """Go back to how the classes stood when the log was ``mark`` long."""
        colour = self.colour
        while len(self.log) > mark:
            cls, fresh = self.log.pop()
            moved = self.members.pop()
            self.balance[cls] += self.balance.pop()
            self.members[cls] |= moved
            for node in moved:
                colour[node] = cls
            self.tied.discard(fresh)
            self._note_tie(cls)

    def _signature(self, node: int) -> tuple[Any, ...]:
        colour = self.colour
        return (
            tuple([colour[target] for target in self.ordered[node]]),
            tuple([tuple(sorted([colour[target] for target in group])) for group in self.unordered[node]]),
            tuple(sorted([(edge >> _SOURCE_BITS, colour[edge & _SOURCE_MASK]) for edge in self.incoming[node]])),
        )

    def _neighbours(self, node: int) -> Iterable[int]:
        yield from self.ordered[node]
        for group in self.unordered[node]:
            yield from group
        for edge in self.incoming[node]:
            yield edge & _SOURCE_MASK

    def refine(self, dirty: Iterable[int]) -> int | None:
        """Split classes until they are stable. Returns a class that lost its balance, or None.

        ``dirty`` holds the instances with a neighbour in a new class. Those differ from the rest of their class, whose
        neighbours have not moved, so only they need looking at. When a whole class is dirty, the largest part stays,
        so that an instance is rarely moved twice.
        """
        members = self.members
        balance = self.balance
        colour = self.colour
        pending = set(dirty)
        while pending:
            touched: defaultdict[int, list[int]] = defaultdict(list)
            for node in pending:
                touched[colour[node]].append(node)
            pending = set()
            for cls, nodes in touched.items():
                parts: defaultdict[tuple[Any, ...], list[int]] = defaultdict(list)
                for node in nodes:
                    parts[self._signature(node)].append(node)
                moving = list(parts.values())
                if len(nodes) == len(members[cls]):
                    moving.remove(max(moving, key=len))
                for part in moving:
                    fresh = self._split_off(cls, part)
                    if balance[fresh]:
                        return fresh
                    for node in part:
                        pending.update(self._neighbours(node))
        return None

    def search(self) -> bool | None:
        """Settle the classes that are still tied. True when every class is a pair, False when no pairing exists,
        None when the limit on the search was reached first."""
        failures = 0
        frames: list[tuple[int, int, set[int], int]] = []
        while self.tied:
            cls = next(iter(self.tied))
            node = next(member for member in self.members[cls] if member < self.split)
            frames.append((cls, node, set(), len(self.log)))
            while frames:
                cls, node, tried, mark = frames[-1]
                self._undo(mark)
                partner = next(
                    (other for other in self.members[cls] if other >= self.split and other not in tried),
                    None,
                )
                if partner is None:
                    frames.pop()
                    continue
                tried.add(partner)
                self._split_off(cls, [node, partner])
                dirty = [*self._neighbours(node), *self._neighbours(partner)]
                if self.refine(dirty) is None:
                    break
                failures += 1
                if failures > MAX_FAILED_PAIRINGS:
                    return None
            else:
                return False
        return True

    def pairing(self) -> dict[int, int]:
        pairs: dict[int, int] = {}
        for members in self.members:
            if members:
                one, other = sorted(members)
                pairs[one] = other
        return pairs

    def first_wrong(self, pairs: dict[int, int]) -> int | None:
        """Check a pairing from the start, against nothing but the files. The instance it fails on, or None."""
        for one, other in pairs.items():
            if (
                self.skeleton[one] != self.skeleton[other]
                or tuple([pairs[target] for target in self.ordered[one]]) != self.ordered[other]
                or any(
                    sorted([pairs[target] for target in ours]) != sorted(theirs)
                    for ours, theirs in zip(self.unordered[one], self.unordered[other], strict=True)
                )
            ):
                return one
        return None

    def without_partner(self, cls: int, how: str) -> str:
        """Words for a class that lost its balance, naming an instance from the file with too many."""
        in_first = self.balance[cls] > 0
        node = min(member for member in self.members[cls] if (member < self.split) == in_first)
        here, there = ("first", "second") if in_first else ("second", "first")
        written = self.files[0 if in_first else 1].text_of(self.ids[node])
        return f"No instance in the {there} file {how} {written} in the {here}."


def same_model(first: StepFile, second: StepFile) -> Check:
    """Whether the pairing that defines the same model exists, and it is shown if it does."""
    name = "same_model"
    if first.schema != second.schema:
        return Check(name, False, f"The schemas differ: {first.schema} and {second.schema}.")
    if len(first) != len(second):
        return Check(name, False, f"The files have {len(first)} and {len(second)} instances.")
    matching = _Matching(first, second, Schema(first.schema))
    for cls, balance in enumerate(matching.balance):
        if balance:
            return Check(name, False, matching.without_partner(cls, "has the values of"))
    lost = matching.refine(range(len(matching.ids)))
    if lost is not None:
        return Check(name, False, matching.without_partner(lost, "has the place in the model of"))
    matching.log.clear()
    settled = matching.search()
    if settled is None:
        return Check(name, None, f"No answer after {MAX_FAILED_PAIRINGS} tries at pairing instances that look alike.")
    if not settled:
        return Check(name, False, "No pairing exists, though every instance has others that look alike.")
    wrong = matching.first_wrong(matching.pairing())
    if wrong is not None:
        return Check(name, None, f"The pairing found does not hold at #{matching.ids[wrong]} in the first file.")
    return Check(name, True, f"{len(first)} instances are paired one to one, and every pair was checked.")


def _is_georeference_property_set(keyword: bytes, parameters: list[Any]) -> bool:
    if keyword != b"IFCPROPERTYSET" or len(parameters) <= 2:
        return False
    name = parameters[2]
    return isinstance(name, bytes) and name in _GEOREFERENCE_PROPERTY_SETS


def _digests(file: StepFile) -> tuple[dict[int, bytes], Counter[bytes], dict[bytes, list[int]]]:
    """What the checks that read every instance once need: a digest per id, classes, and where the georeference is."""
    digests: dict[int, bytes] = {}
    classes: Counter[bytes] = Counter()
    named: defaultdict[bytes, list[int]] = defaultdict(list)
    for step_id, keyword, parameters in file:
        text = b"|".join([keyword, *[exact_text(value) for value in parameters]])
        digests[step_id] = hashlib.blake2b(text, digest_size=20).digest()
        classes[keyword] += 1
        if keyword in _GEOREFERENCE or _is_georeference_property_set(keyword, parameters):
            named[keyword].append(step_id)
    return digests, classes, named


def _check_header(first: StepFile, second: StepFile) -> Check:
    keys = first.header.keys() | second.header.keys()
    differing = sorted(key for key in keys if first.header.get(key) != second.header.get(key))
    if differing:
        return Check("header", False, f"These differ: {', '.join(key.decode('ascii') for key in differing)}.")
    return Check("header", True)


def _check_classes(first: Counter[bytes], second: Counter[bytes]) -> Check:
    differing = sorted(key for key in first.keys() | second.keys() if first[key] != second[key])
    if differing:
        shown = ", ".join(f"{key.decode('ascii')} {first[key]} and {second[key]}" for key in differing[:_MAX_SHOWN])
        more = f", and {len(differing) - _MAX_SHOWN} more" if len(differing) > _MAX_SHOWN else ""
        return Check("classes", False, f"The number of instances per class differs: {shown}{more}.")
    return Check("classes", True)


def _check_exact(first: StepFile, second: StepFile, ours: dict[int, bytes], theirs: dict[int, bytes]) -> Check:
    if ours == theirs:
        return Check("exact", True)
    for step_id in sorted(ours.keys() | theirs.keys()):
        if ours.get(step_id) != theirs.get(step_id):
            if step_id not in theirs:
                return Check("exact", False, f"Only the first file has {first.text_of(step_id)}.")
            if step_id not in ours:
                return Check("exact", False, f"Only the second file has {second.text_of(step_id)}.")
            return Check("exact", False, f"These differ: {first.text_of(step_id)} and {second.text_of(step_id)}.")
    raise AssertionError("two different dicts have a key on which they differ")  # pragma: no cover


class _Expander:
    """Instances with their references written out as far as they lead, to compare what they say by themselves.

    A reference back into the instances being written out reads ``#cycle``. Nothing is remembered between instances,
    since what a cycle writes out depends on where it was entered, and the limit is on the work, not on the depth.
    """

    def __init__(self, file: StepFile, schema: Schema) -> None:
        self.file = file
        self.schema = schema
        self._written = 0

    def _value(self, value: Any, kinds: tuple[str, ...], path: set[int]) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, int):
            return self._instance(value, path)
        if isinstance(value, tuple):
            inner = _kinds_of_type(self.schema, value[0])
            return b"%s(%s)" % (value[0], b",".join([self._value(item, inner, path) for item in value[1]]))
        parts = [self._value(item, kinds[1:], path) for item in value]
        if kinds and kinds[0] in _UNORDERED:
            parts.sort()
        return b"(%s)" % b",".join(parts)

    def _instance(self, step_id: int, path: set[int]) -> bytes:
        if step_id in path:
            return b"#cycle"
        if step_id not in self.file:
            return _NOTHING_THERE
        keyword, parameters = self.file[step_id]
        self._written += len(keyword) + len(parameters)
        if self._written > MAX_EXPANDED_VALUES:
            raise StepError(f"writing out what #{step_id} refers to takes more than {MAX_EXPANDED_VALUES} values")
        path.add(step_id)
        attributes = self.schema.attributes(keyword) or ()
        parts = [
            self._value(item, attributes[position].kinds if position < len(attributes) else (), path)
            for position, item in enumerate(parameters)
        ]
        path.discard(step_id)
        return b"%s(%s)" % (keyword, b",".join(parts))

    def named_attributes(self, step_id: int) -> dict[str, bytes]:
        self._written = 0
        keyword, parameters = self.file[step_id]
        wanted = _GEOREFERENCE.get(keyword)
        said: dict[str, bytes] = {}
        for position, attribute in enumerate(self.schema.attributes(keyword) or ()):
            if position < len(parameters) and (wanted is None or attribute.name in wanted):
                said[attribute.name] = self._value(parameters[position], attribute.kinds, {step_id})
        return said


def _readable(text: bytes) -> str:
    """What a canonical value says, for a report."""
    shown = _HEX_FLOAT.sub(lambda match: repr(float.fromhex(match.group(1).decode("ascii"))).encode("ascii"), text)
    return shown[:120].decode("utf-8", "replace")


def _check_georeference(
    first: StepFile, second: StepFile, ours: dict[bytes, list[int]], theirs: dict[bytes, list[int]]
) -> Check:
    name = "georeference"
    if first.schema != second.schema:
        return Check(name, None, "The schemas differ.")
    schema = Schema(first.schema)
    expand_first, expand_second = _Expander(first, schema), _Expander(second, schema)
    differences: list[str] = []
    compared = 0
    for keyword in sorted(ours.keys() | theirs.keys()):
        left = [expand_first.named_attributes(step_id) for step_id in ours.get(keyword, ())]
        right = [expand_second.named_attributes(step_id) for step_id in theirs.get(keyword, ())]
        compared += len(left)
        label = keyword.decode("ascii")
        if len(left) != len(right):
            differences.append(f"{label}: {len(left)} and {len(right)} instances")
        elif len(left) == 1:
            for attribute, said in left[0].items():
                if right[0].get(attribute) != said:
                    differences.append(
                        f"{label}.{attribute}: {_readable(said)} and {_readable(right[0].get(attribute, b''))}"
                    )
        elif sorted(sorted(entry.items()) for entry in left) != sorted(sorted(entry.items()) for entry in right):
            differences.append(f"{label}: the {len(left)} instances do not say the same")
    if differences:
        return Check(name, False, "; ".join(differences[:_MAX_SHOWN]))
    return Check(name, True, f"{compared} instances say the same.")


def _mesh_digest(vertices: Sequence[float], faces: Sequence[int]) -> bytes:
    """Bit for bit: a rounded hash fails on values next to the rounding's edge, and the kernel's ids hold STEP ids."""
    digest = hashlib.blake2b(digest_size=20)
    digest.update(array("d", vertices).tobytes())
    digest.update(array("q", faces).tobytes())
    return digest.digest()


def _meshes(path: Path) -> tuple[dict[str, list[bytes]], set[str]]:
    """The mesh of every product as the geometry kernel builds it, by GlobalId, and the products that have a body."""
    import ifcopenshell
    import ifcopenshell.geom

    model = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    meshes: defaultdict[str, list[bytes]] = defaultdict(list)
    iterator = ifcopenshell.geom.iterator(settings, model, 4)
    if iterator.initialize():
        while True:
            shape: Any = iterator.get()
            geometry = shape.geometry
            meshes[shape.guid].append(_mesh_digest(geometry.verts, geometry.faces))
            if not iterator.next():
                break
    bodies = {
        product.GlobalId
        for product in model.by_type("IfcProduct")
        if product.Representation is not None
        and any(item.RepresentationIdentifier == "Body" for item in product.Representation.Representations)
    }
    for digests in meshes.values():
        digests.sort()
    return dict(meshes), bodies


def _check_geometry(first: Path, second: Path) -> Check:
    """Whether the files build the same meshes, bit for bit. Order counts here (the kernel's result can change with the
    order of a SET), so this says something only of files that keep it. A pass needs something to have been built."""
    name = "geometry"
    ours, bodies = _meshes(first)
    theirs, their_bodies = _meshes(second)
    if bodies != their_bodies:
        return Check(name, False, f"{len(bodies ^ their_bodies)} products have a body in only one of the files.")
    if bodies and not ours:
        return Check(name, None, "None of the bodies could be built.")
    differing = sorted(guid for guid in ours.keys() | theirs.keys() if ours.get(guid) != theirs.get(guid))
    if differing:
        return Check(name, False, f"{len(differing)} products build differently, the first {differing[0]}.")
    missing = len(bodies - ours.keys())
    tail = f", and neither file builds the {missing} others with a body" if missing else ""
    return Check(name, True, f"{len(ours)} products build the same{tail}.")


def _read(data: bytes, which: str) -> tuple[StepFile, tuple[dict[int, bytes], Counter[bytes], dict[bytes, list[int]]]]:
    try:
        file = StepFile(data)
        return file, _digests(file)
    except StepError as exc:
        raise StepError(f"The {which} file: {exc}") from exc


def _answer(name: str, question: Callable[[], Check]) -> Check:
    try:
        return question()
    except (StepError, RecursionError) as exc:
        return Check(name, None, str(exc)[:300])


def compare(first: bytes, second: bytes) -> Comparison:
    """Compare two files in memory, without generating geometry."""
    try:
        ours, (our_digests, our_classes, our_named) = _read(first, "first")
        theirs, (their_digests, their_classes, their_named) = _read(second, "second")
    except StepError as exc:
        return Comparison((Check("read", False, str(exc)),))
    raw = [
        f"the {which} file has {file.raw_bytes()}"
        for which, file in (("first", ours), ("second", theirs))
        if file.raw_bytes()
    ]
    exact = _check_exact(ours, theirs, our_digests, their_digests)
    return Comparison(
        (
            Check("read", True, f"Bytes above 0x7F, which IfcOpenShell drops: {', '.join(raw)}." if raw else ""),
            _check_header(ours, theirs),
            _check_classes(our_classes, their_classes),
            exact,
            Check("same_model", True, "The instances are the same, with the same ids.")
            if exact.passed and ours.schema == theirs.schema
            else _answer("same_model", lambda: same_model(ours, theirs)),
            _answer("georeference", lambda: _check_georeference(ours, theirs, our_named, their_named)),
        )
    )


def compare_files(first: Path, second: Path, *, geometry: bool = False) -> Comparison:
    comparison = compare(first.read_bytes(), second.read_bytes())
    if not geometry:
        return comparison
    try:
        built = _check_geometry(first, second)
    except Exception as exc:  # the kernel and its reader raise more than one kind, and any of them is an answer
        built = Check("geometry", None, f"{type(exc).__name__}: {str(exc)[:300]}")
    return Comparison((*comparison.checks, built))


def keep_stdout_for_the_answer() -> None:
    """Send what anything else writes to stdout to stderr instead. The geometry kernel writes to it from C++, past
    ``sys.stdout`` and at times of its own, and the answer on stdout has to stand alone to be read."""
    answer = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = answer


def main(argv: list[str] | None = None) -> int:
    """Exit 0 for the same model, 1 for not the same or not shown, 2 for no file, with the answer as JSON on stdout."""
    parser = argparse.ArgumentParser(prog="opencde-ifcgraph-equivalence")
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--geometry", action="store_true", help="also build every product's mesh, and compare those")
    parser.add_argument("--memory-mb", type=int, default=0)
    args = parser.parse_args(argv)
    if args.memory_mb:
        from opencde.ifcgraph.worker import limit_memory

        limit_memory(args.memory_mb)
    try:
        comparison = compare_files(args.first, args.second, geometry=args.geometry)
    except OSError as exc:
        sys.stderr.write(json.dumps({"error": f"{type(exc).__name__}: {exc}"}) + "\n")
        return 2
    sys.stdout.write(json.dumps(comparison.to_dict(), indent=2) + "\n")
    sys.stdout.flush()
    return 0 if comparison.same_model else 1


if __name__ == "__main__":
    keep_stdout_for_the_answer()
    sys.exit(main())
