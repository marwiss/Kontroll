# This file was generated with the assistance of an AI coding tool.
"""An upload checked against buildingSMART's Data Dictionary (bSDD), off until enabled (OB-42).

A model names a bSDD class with an ``IfcClassificationReference`` whose URI is
``https://identifier.buildingsmart.org/uri/<organisation>/<dictionary>/<version>/class/<code>``, or a property with
``…/prop/<code>``, also in a property's ``Specification`` (IFC 4.3) or ``Description``; the worker ``bsdd_refs.py``
reads them out of the file, with the ``Pset_`` and ``Qto_`` sets, and out of the project's IDS documents, whose
classification and property facets may name theirs by such a URI. The client asks the configured bSDD API about each
URI, with a time limit and a small retry, and keeps the answer in memory, so that a server process asks about a URI
once a day however many uploads or IDS documents name it. Nothing a file names is fetched: a URI goes to bSDD's API as
a parameter, and one on a host other than bSDD's identifier host is reported instead.

Every finding is a warning: a reference or a property bSDD does not know, since a model may use a dictionary bSDD has
not published, and, in a file of IFC 4.3, a ``Pset_`` or ``Qto_`` set that bSDD's IFC dictionary does not have, or a
property it does not list in that set. bSDD publishes that one IFC dictionary, so the sets of an IFC4 or IFC2X3 file,
whose schemas define them otherwise, are not checked. A URI of an IDS document that bSDD does not know is a warning in
the report of every file checked against that document, with the document and its specification named. bSDD out of
reach fails the check, never the file.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urlsplit

import httpx

from opencde import __version__

IDENTIFIER_HOST = "identifier.buildingsmart.org"
IFC_DICTIONARY = "buildingsmart/ifc/4.3"  # the one IFC dictionary bSDD publishes (November 2026)
IFC_SCHEMA = "IFC4X3"  # the schema whose sets it describes
# IFC 4.3 gives nearly every set a `Reference`, and bSDD's IFC dictionary leaves it out of all of them.
LEFT_OUT = frozenset({"Reference"})
CLASS_PATH = "/api/Class/v1"
PROPERTY_PATH = "/api/Property/v5"  # v4 is deprecated
CLASS_PROPERTIES_PATH = "/api/Class/Properties/v1"  # what bSDD asks for in place of IncludeClassProperties
PAGE = 1_000  # the properties of a class asked for at once
MAX_PAGES = 5
RETRY_SECONDS = (1.0, 3.0)  # after a 5xx or a 429: a small retry, then bSDD is out of reach
MAX_RETRY_AFTER = 10.0
MAX_CACHE = 10_000
MAX_MESSAGE = 1_000  # as the other checks cut theirs
MAX_QUOTED = 120  # of a name or a URI quoted in a message
MAX_NAMED = 20  # properties named in a message

_URI = re.compile(
    r"^(?i:https?://identifier\.buildingsmart\.org)/uri/(?P<organisation>[^/\s?#]+)/(?P<dictionary>[^/\s?#]+)"
    r"/(?P<version>[^/\s?#]+)(?:/(?P<kind>class|prop)/(?P<code>[^/\s?#]+))?/?$"
)
T = TypeVar("T")


@dataclass(frozen=True)
class BsddUri:
    """What a bSDD URI names: a dictionary, or a class or property (``kind``) of it."""

    uri: str  # as bSDD's API wants it: https, without a trailing slash
    dictionary: str  # organisation/dictionary/version
    kind: str | None  # class, prop, or None for a dictionary's own URI
    code: str | None


def parse_uri(text: Any) -> BsddUri | None:
    """What a bSDD URI names, or None for anything else: a text that is no URI, or one on another host."""
    if not isinstance(text, str):
        return None
    match = _URI.match(text.strip())
    if match is None:
        return None
    dictionary = "/".join(match.group("organisation", "dictionary", "version"))
    kind, code = match.group("kind"), match.group("code")
    uri = f"https://{IDENTIFIER_HOST}/uri/{dictionary}" + (f"/{kind}/{code}" if kind else "")
    return BsddUri(uri, dictionary, kind, code)


def class_uri(dictionary: str, code: str) -> str:
    """The URI of a class of a dictionary, such as a property set of the IFC dictionary."""
    return f"https://{IDENTIFIER_HOST}/uri/{dictionary}/class/{code}"


def ifc_dictionary(schema: str) -> str | None:
    """bSDD's IFC dictionary for the sets of a file of this schema, when bSDD publishes one."""
    return IFC_DICTIONARY if schema.upper().startswith(IFC_SCHEMA) else None


def ruleset(host: str, dictionaries: list[str] | None = None) -> str:
    """What the check asked: bSDD at its host and, once the check is made, the dictionaries that the file and its IDS
    documents were checked against."""
    if dictionaries is None:
        return f"bSDD at {host}"
    return f"bSDD at {host}: " + (", ".join(dictionaries) or "no dictionary referenced")


class BsddUnavailable(RuntimeError):
    """bSDD could not be reached, or did not answer as its API does; never an error of the model."""


class NotBsdd(ValueError):
    """A URI that is not bSDD's: it is reported, never asked about."""


def _bsdd_uri(uri: str, kinds: tuple[str, ...]) -> BsddUri:
    parsed = parse_uri(uri)
    if parsed is None or parsed.kind not in kinds:
        raise NotBsdd(f"{str(uri)[:MAX_QUOTED]} is not the URI of a bSDD {' or '.join(kinds)}")
    return parsed


def _not_found(response: httpx.Response) -> bool:
    """Whether a 400 of bSDD says that it does not know the URI, as in ``{"message": "Class with URI '…' not
    found"}``; any other 400 means that the API did not take the question."""
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and "not found" in str(body.get("message", "")).lower()


def _retry_after(response: httpx.Response, default: float) -> float:
    """How long bSDD asks a client to wait, within reason; else the retry's own wait."""
    try:
        return min(max(float(response.headers.get("Retry-After", "")), default), MAX_RETRY_AFTER)
    except ValueError:
        return default


def _brief(body: dict[str, Any]) -> dict[str, Any]:
    """What is kept of bSDD's answer about a class or property: what names it, not its whole definition."""
    return {key: body[key] for key in ("uri", "code", "name", "status", "dictionaryUri") if key in body}


class BsddClient:
    """Asks bSDD's API about classes and properties by URI, keeping each answer in memory while it is fresh.

    A server process asks about a URI once while its answer is fresh, however many uploads name it, and keeps a
    bounded number of answers. The transport, the clock and the sleep can be replaced in tests.
    """

    def __init__(
        self,
        api_url: str,
        *,
        timeout_seconds: float = 10.0,
        cache_seconds: float = 86_400,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.host = urlsplit(api_url).hostname or api_url
        self._client = httpx.AsyncClient(
            base_url=api_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": f"Dataregium/{__version__}"},
        )
        self._cache_seconds = cache_seconds
        self._cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._sleep = sleep
        self._clock = clock

    async def aclose(self) -> None:
        await self._client.aclose()

    async def lookup(self, uri: str) -> dict[str, Any] | None:
        """What bSDD says of a class or property URI, briefly, or None when it does not know it.

        Raises ``NotBsdd`` for a URI that is not bSDD's, which is never asked about, and ``BsddUnavailable`` when bSDD
        cannot be reached or does not answer as its API does.
        """
        parsed = _bsdd_uri(uri, ("class", "prop"))
        path = CLASS_PATH if parsed.kind == "class" else PROPERTY_PATH

        async def ask() -> dict[str, Any] | None:
            answer = await self._ask(path, {"uri": parsed.uri})
            return None if answer is None else _brief(answer)

        return await self._cached((str(parsed.kind), parsed.uri), ask)

    async def properties_of(self, uri: str) -> frozenset[str]:
        """The codes of the properties bSDD lists for a class, such as a property set of its IFC dictionary; none for
        a class it does not know. Raises as ``lookup`` does."""
        parsed = _bsdd_uri(uri, ("class",))

        async def ask() -> frozenset[str]:
            codes: set[str] = set()
            offset = 0
            for _ in range(MAX_PAGES):
                params = {"ClassUri": parsed.uri, "Offset": str(offset), "Limit": str(PAGE)}
                page = await self._ask(CLASS_PROPERTIES_PATH, params) or {}
                listed = [entry for entry in page.get("classProperties") or [] if isinstance(entry, dict)]
                codes.update(str(entry["propertyCode"]) for entry in listed if entry.get("propertyCode"))
                offset += len(listed)
                total = page.get("totalCount")
                if not listed or not isinstance(total, int) or offset >= total:
                    break
            return frozenset(codes)

        return await self._cached(("properties", parsed.uri), ask)

    async def _cached(self, key: tuple[str, str], ask: Callable[[], Awaitable[T]]) -> T:
        now = self._clock()
        kept = self._cache.get(key)
        if kept is not None and kept[0] > now:
            return kept[1]
        answer = await ask()
        if self._cache_seconds > 0:
            if len(self._cache) >= MAX_CACHE:
                self._cache.clear()
            self._cache[key] = (now + self._cache_seconds, answer)
        return answer

    async def _ask(self, path: str, params: dict[str, str]) -> dict[str, Any] | None:
        """One question to bSDD: the answer, None for a URI it does not know, a retry on a 5xx or a 429."""
        attempt = 0
        while True:
            try:
                response = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                raise BsddUnavailable(f"bSDD at {self.host} could not be reached: {type(exc).__name__}") from exc
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    raise BsddUnavailable(f"bSDD at {self.host} answered with something other than JSON") from None
                if not isinstance(body, dict):
                    raise BsddUnavailable(f"bSDD at {self.host} answered with something other than an object")
                return body
            if response.status_code == 400 and _not_found(response):
                return None
            if response.status_code in (429, 500, 502, 503, 504) and attempt < len(RETRY_SECONDS):
                await self._sleep(_retry_after(response, RETRY_SECONDS[attempt]))
                attempt += 1
                continue
            raise BsddUnavailable(f"bSDD at {self.host} answered {response.status_code} for {path}")


def _quoted(value: Any) -> str:
    return str(value)[:MAX_QUOTED]


def _where(entry: dict[str, Any]) -> str:
    """Which objects a reference or a set is on, for a message: their number, and one of them by class and GlobalId."""
    count = int(entry.get("object_count") or 0)
    objects = entry.get("objects") or []
    if not count or not objects:
        return "on no object"
    first = objects[0]
    one = f"the {first.get('ifc_class') or 'object'} {first.get('global_id')}"
    return f"on {one}" if count == 1 else f"on {count} objects, among them {one}"


def _issue(entry: dict[str, Any], message: str, *, rule: str | None, attribute: str | None) -> dict[str, Any]:
    """A warning on the reference's or set's own instance, with the GlobalId of an object it is on where it has one."""
    issue: dict[str, Any] = {"kind": "bsdd", "severity": "warning", "message": message[:MAX_MESSAGE]}
    if rule:
        issue["rule"] = rule
    if entry.get("step_id") is not None:
        issue["step_id"] = int(entry["step_id"])
    objects = entry.get("objects") or []
    if objects and objects[0].get("global_id"):
        issue["global_id"] = str(objects[0]["global_id"])
    if attribute:
        issue["attribute"] = attribute
    return issue


def _reference_words(reference: dict[str, Any]) -> str:
    """How the file names a reference, for a message: its identification and name, and its classification's name."""
    parts = []
    if reference.get("identification"):
        parts.append(f"identification '{_quoted(reference['identification'])}'")
    if reference.get("name"):
        parts.append(f"name '{_quoted(reference['name'])}'")
    classification = reference.get("classification") or {}
    if classification.get("name"):
        parts.append(f"in the classification '{_quoted(classification['name'])}'")
    return f" ({', '.join(parts)})" if parts else ""


async def _reference_issues(
    references: list[dict[str, Any]], client: BsddClient, dictionaries: dict[str, None]
) -> list[dict[str, Any]]:
    """A warning for each classification reference bSDD does not know, or that names a URI that is not bSDD's."""
    issues = []
    for reference in references:
        uri = str(reference.get("uri") or "")
        step = reference.get("step_id")
        attribute = reference.get("attribute")
        try:
            answer = await client.lookup(uri)
        except NotBsdd:
            message = (
                f"The classification reference #{step} names {_quoted(uri)}, which is not the URI of a class or "
                f"property at bSDD ({IDENTIFIER_HOST}), so it was not looked up; it is {_where(reference)}."
            )
            issues.append(_issue(reference, message, rule=None, attribute=attribute))
            continue
        parsed = parse_uri(uri)
        if parsed is None:  # the lookup took it, so it is bSDD's
            continue
        dictionaries.setdefault(parsed.dictionary)
        if answer is None:
            kind = "property" if parsed.kind == "prop" else "class"
            message = (
                f"bSDD does not know the {kind} {_quoted(parsed.uri)} of the classification reference "
                f"#{step}{_reference_words(reference)}; it is {_where(reference)}."
            )
            issues.append(_issue(reference, message, rule=parsed.dictionary, attribute=attribute))
    return issues


async def _property_issues(
    properties: list[dict[str, Any]], client: BsddClient, dictionaries: dict[str, None]
) -> list[dict[str, Any]]:
    """A warning for each property whose ``Specification`` or ``Description`` names a bSDD property that bSDD does not
    know, with its set and name as the attribute, as the sets' own findings have them."""
    issues = []
    for entry in properties:
        parsed = parse_uri(entry.get("uri"))
        if parsed is None or parsed.kind != "prop":  # the worker lists only bSDD's properties
            continue
        dictionaries.setdefault(parsed.dictionary)
        if await client.lookup(parsed.uri) is not None:
            continue
        name, in_set = _quoted(entry.get("name") or ""), _quoted(entry.get("set") or "")
        message = (
            f"bSDD does not know the property {_quoted(parsed.uri)} that the property '{name}' of the set "
            f"'{in_set}' (#{entry.get('step_id')}) names in its {entry.get('attribute') or 'Specification'}; it is "
            f"{_where(entry)}."
        )
        issues.append(_issue(entry, message, rule=parsed.dictionary, attribute=f"{in_set}.{name}"))
    return issues


def _facet_words(entry: dict[str, Any]) -> str:
    """What an IDS facet names beside its URI, for a message: the property and its set, or the class and its system."""
    named, within = ("name", "set") if entry.get("facet") == "property" else ("value", "system")
    what = f"the {'property' if named == 'name' else 'value'} '{_quoted(entry[named])}'" if entry.get(named) else ""
    where = f"in the {within} '{_quoted(entry[within])}'" if entry.get(within) else ""
    if what:
        return f", for {what}" + (f" {where}" if where else "")
    return f", {where}" if where else ""


async def _ids_issues(
    documents: list[dict[str, Any]], client: BsddClient, dictionaries: dict[str, None]
) -> list[dict[str, Any]]:
    """A warning for each bSDD URI of an IDS document of the project that bSDD does not know, once a specification,
    with the document's id; it says nothing of the file, which is checked against the document all the same."""
    issues = []
    for document in documents:
        document_id = str(document["document_id"])
        title = _quoted(document.get("title") or document_id)
        for entry in document.get("uris") or []:
            parsed = parse_uri(entry.get("uri"))
            if parsed is None or parsed.kind is None:  # the worker lists only bSDD's classes and properties
                continue
            dictionaries.setdefault(parsed.dictionary)
            if await client.lookup(parsed.uri) is not None:
                continue
            kind = "property" if parsed.kind == "prop" else "class"
            specification = f"'{_quoted(entry.get('specification') or '')}'"
            if entry.get("identifier"):
                specification += f" ({_quoted(entry['identifier'])})"
            message = (
                f"bSDD does not know the {kind} {_quoted(parsed.uri)} that the IDS document '{title}' names in a "
                f"{entry.get('facet') or 'classification'} facet of the {entry.get('clause') or 'requirements'} of "
                f"its specification {specification}{_facet_words(entry)}."
            )
            issues.append(
                {
                    "kind": "bsdd",
                    "severity": "warning",
                    "message": message[:MAX_MESSAGE],
                    "rule": parsed.dictionary,
                    "document_id": document_id,
                }
            )
        if document.get("cut"):
            message = (
                f"The IDS document '{title}' names more bSDD URIs than the check reads, so only the first were looked "
                "up."
            )
            issues.append({"kind": "bsdd", "severity": "warning", "message": message, "document_id": document_id})
    return issues


async def _set_issues(sets: dict[str, dict[str, Any]], dictionary: str, client: BsddClient) -> list[dict[str, Any]]:
    """A warning for each set that bSDD's IFC dictionary does not have, and each property it does not list in its set."""
    issues = []
    for name in sorted(sets):
        entry = sets[name]
        properties = [str(prop) for prop in entry.get("properties") or []]
        listed = await client.properties_of(class_uri(dictionary, name))
        if not listed:
            named = ", ".join(_quoted(prop) for prop in properties[:MAX_NAMED]) + (
                ", …" if len(properties) > MAX_NAMED else ""
            )
            message = (
                f"bSDD's IFC dictionary ({dictionary}) has no property set {_quoted(name)}, which the file has "
                f"{_where(entry)}" + (f", with the properties {named}." if named else ".")
            )
            issues.append(_issue(entry, message, rule=dictionary, attribute=name))
            continue
        for prop in properties:
            if prop not in listed and prop not in LEFT_OUT:
                message = (
                    f"bSDD's IFC dictionary ({dictionary}) has no property {_quoted(prop)} in {_quoted(name)}, which "
                    f"the file has {_where(entry)}."
                )
                issues.append(_issue(entry, message, rule=dictionary, attribute=f"{name}.{prop}"))
    return issues


async def check(found: dict[str, Any], client: BsddClient, ids: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The check ``bsdd`` on what the worker found in the file and in the IDS documents it is checked against (``ids``:
    each with its ``document_id``, ``title``, ``uris`` and ``cut``), in the form the other checks give: ``{"check",
    "issues", "error_count", "truncated"}``. Every issue is a warning. Raises ``BsddUnavailable`` when bSDD could not
    be asked."""
    dictionaries: dict[str, None] = {}  # in the order the file and then the IDS documents name them
    issues = await _reference_issues(list(found.get("references") or []), client, dictionaries)
    issues += await _property_issues(list(found.get("properties") or []), client, dictionaries)
    dictionary = ifc_dictionary(str(found.get("schema") or ""))
    sets = dict(found.get("property_sets") or {})
    if dictionary is not None and sets:
        dictionaries.setdefault(dictionary)
        issues += await _set_issues(sets, dictionary, client)
    if found.get("cut"):
        message = (
            "The file has more classification references, properties naming bSDD or property sets than the check "
            "reads, so only the first were looked up."
        )
        issues.append({"kind": "bsdd", "severity": "warning", "message": message})
    issues += await _ids_issues(list(ids or []), client, dictionaries)
    return {
        "check": {
            "name": "bsdd",
            "state": "done",
            "ruleset": ruleset(client.host, list(dictionaries)),
            "issue_count": len(issues),
        },
        "issues": issues,
        "error_count": 0,
        "truncated": False,
    }
