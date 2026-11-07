# This file was generated with the assistance of an AI coding tool.
"""Read and write an ISO 10303-21 exchange file, without IfcOpenShell.

The comparison of two IFC files in ``equivalence.py`` has to see what a file says, and IfcOpenShell does not always
tell. It reads ``.5`` in a list of REALs as nothing, drops bytes above 0x7F from strings and leaves out complex
instances, all without an error, so a loss on the way out could go unseen if it also did the reading. This reader is
small and strict: what it cannot read it refuses.

The writer is the reader's inverse, for a round trip through the graph that has to carry what IfcOpenShell would change.
It writes a REAL in the shortest form that reads back as the same double, and a string in escapes.

A value is one of these:

* ``int``: a reference to the instance with that id.
* ``bytes``: anything else that stands alone, in a canonical form, so that two spellings of a value (``1.`` and
  ``1.0E0``, ``\\X\\E5`` and ``\\X2\\00E5\\X0\\``) are equal and two different values never are. A REAL is kept by
  its bits, so ``-0.`` is not ``0.``, and ``1.`` is not the INTEGER ``1``.
* ``list``: an aggregate.
* ``tuple``: ``(keyword, parameters)``, a typed value such as ``IFCLABEL('x')``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any, BinaryIO

MAX_NESTING = 32
MAX_INSTANCE_ID = 2**63 - 1
_BYTE_ORDER_MARK = b"\xef\xbb\xbf"
_NEWLINE = b"\n"

_STATEMENT = re.compile(
    rb"""(?:\s++|/\*.*?\*/)*+                 # layout and comments between statements
         (?:\#(\d++)\s*+=\s*+)?               # the id of an instance
         ((?:[^;'"/]++|'[^']*+'|"[^"]*+"|/\*.*?\*/)*+)  # the rest; a semicolon in a string does not end it
         ;""",
    re.VERBOSE | re.DOTALL,
)
_TOKEN = re.compile(
    rb"""'[^']*+(?:''[^']*+)*+'               # a string, in which '' is one quote
       | "[^"]*+"                             # binary
       | \#\d++                               # a reference
       | [+-]?\d++(?:\.\d*+)?(?:[eE][+-]?\d++)?   # a number
       | \.[A-Za-z0-9_]++\.                   # an enumeration or a logical
       | !?[A-Za-z_][A-Za-z0-9_]*+            # a keyword
       | /\*.*?\*/                            # a comment
       | \S                                   # punctuation, or something that is not allowed here
    """,
    re.VERBOSE | re.DOTALL,
)
_ESCAPE = re.compile(
    rb"""\\\\                                 # one backslash
       | \\P([A-I])\\                         # the code page for what follows
       | \\S\\(.)                             # one character from the code page's upper half
       | \\X\\([0-9A-F]{2})                   # one character of ISO 8859-1
       | \\X2\\((?:[0-9A-F]{4})*+)\\X0\\      # UTF-16
       | \\X4\\((?:[0-9A-F]{8})*+)\\X0\\      # UTF-32
    """,
    re.VERBOSE | re.DOTALL,
)
_HASH, _OPEN, _QUOTE, _BINARY, _DOT = 0x23, 0x28, 0x27, 0x22, 0x2E
_NUMBER_START = frozenset(b"+-0123456789")
_KEYWORD_START = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_!")
_ALONE = frozenset((b"$", b"*"))
_KEYWORD = re.compile(rb"\s*+(!?[A-Za-z_][A-Za-z0-9_]*+)")
_ASCII = bytes(range(0x80))
_NEEDS_ESCAPE = re.compile(r"[^\x20-\x7e]+|['\\]")
_LAST_BMP = 0xFFFF


class StepError(ValueError):
    """The file is not an exchange structure this reader can stand behind."""


def _decoded(inner: bytes) -> str:
    """The characters of a string that holds escapes. A backslash that starts no escape stands for itself."""
    parts: list[str] = []
    position = 0
    page = "iso-8859-1"
    for match in _ESCAPE.finditer(inner):
        parts.append(inner[position : match.start()].decode("ascii"))
        position = match.end()
        code_page, upper, single, wide, wider = match.groups()
        if code_page is not None:
            page = f"iso-8859-{code_page[0] - 0x40}"
        elif upper is not None:
            parts.append(bytes((upper[0] + 0x80,)).decode(page, "replace"))
        elif single is not None:
            parts.append(chr(int(single, 16)))
        elif wide is not None:
            parts.append(bytes.fromhex(wide.decode("ascii")).decode("utf-16-be", "surrogatepass"))
        elif wider is not None:
            try:
                parts.append(bytes.fromhex(wider.decode("ascii")).decode("utf-32-be", "surrogatepass"))
            except UnicodeDecodeError as exc:
                raise StepError("a \\X4\\ escape names no character") from exc
        else:
            parts.append("\\")
    parts.append(inner[position:].decode("ascii"))
    return "".join(parts)


def _string(token: bytes) -> bytes:
    inner = token[1:-1]
    if b"''" in inner:
        inner = inner.replace(b"''", b"'")
    if not inner.isascii():
        # Not valid STEP. Which encoding the bytes were meant in is a guess, so they stand as they are, and they
        # cannot come to equal a string that says the same in escapes.
        return b"x%d:%s" % (len(inner), inner)
    if b"\\" in inner:
        return string_atom(_decoded(inner))
    return b"s%d:%s" % (len(inner), inner)


def string_atom(text: str) -> bytes:
    """The canonical form of a string."""
    encoded = text.encode("utf-8", "surrogatepass")
    return b"s%d:%s" % (len(encoded), encoded)


def string_of_atom(atom: bytes) -> str:
    return atom.split(b":", 1)[1].decode("utf-8", "surrogatepass")


def _number(token: bytes) -> bytes:
    try:
        if b"." in token or b"e" in token or b"E" in token:
            return b"r%s" % float(token).hex().encode("ascii")
        return b"i%d" % int(token)
    except ValueError as exc:  # more digits than Python reads
        raise StepError("a number cannot be read") from exc


def _instance_id(digits: bytes) -> int:
    """An id, which has to fit where the databases keep it. The zeros in front of one carry no meaning."""
    try:
        step_id = int(digits)
    except ValueError as exc:  # more digits than Python reads
        raise StepError("an instance id cannot be read") from exc
    if step_id > MAX_INSTANCE_ID:
        raise StepError(f"the instance id {digits[:40]!r} is too large")
    return step_id


def _parameters(tokens: list[bytes], index: int, depth: int) -> tuple[list[Any], int]:
    """The values up to the closing parenthesis, which is at or after ``index``, and the place after it."""
    if depth > MAX_NESTING:
        raise StepError(f"parameters are nested deeper than {MAX_NESTING} levels")
    items: list[Any] = []
    if tokens[index] == b")":
        return items, index + 1
    while True:
        token = tokens[index]
        index += 1
        first = token[0]
        if first in _NUMBER_START:
            items.append(_number(token))
        elif first == _HASH:
            items.append(_instance_id(token[1:]))
        elif first == _QUOTE:
            items.append(_string(token))
        elif first == _OPEN:
            nested, index = _parameters(tokens, index, depth + 1)
            items.append(nested)
        elif token in _ALONE or first == _BINARY or (first == _DOT and len(token) > 1):
            items.append(token)
        elif first in _KEYWORD_START:
            if tokens[index] != b"(":
                raise StepError(f"{token!r} is not followed by parameters")
            nested, index = _parameters(tokens, index + 1, depth + 1)
            items.append((token.upper(), nested))
        else:
            raise StepError(f"{token!r} cannot stand where a value should")
        token = tokens[index]
        index += 1
        if token == b",":
            continue
        if token == b")":
            return items, index
        raise StepError(f"{token!r} cannot follow a value")


def _keyword_and_parameters(tokens: list[bytes], index: int) -> tuple[bytes, list[Any], int]:
    keyword = tokens[index]
    if keyword[0] not in _KEYWORD_START:
        raise StepError(f"{keyword!r} is not a keyword")
    if tokens[index + 1] != b"(":
        raise StepError(f"{keyword!r} is not followed by parameters")
    parameters, index = _parameters(tokens, index + 2, 1)
    return keyword.upper(), parameters, index


def parse_statement(body: bytes) -> tuple[bytes, list[Any]]:
    """The keyword and the parameters of one statement, with its id and its semicolon taken off.

    A complex instance, ``(IFCA(1)IFCB(2))``, has the keywords together as its keyword and a typed value per part
    as its parameters. No IFC schema has one, so it matches nothing but its own spelling.
    """
    tokens = _TOKEN.findall(body)
    if b"/*" in body:
        tokens = [token for token in tokens if not token.startswith(b"/*")]
    try:
        if tokens[0] != b"(":
            keyword, parameters, index = _keyword_and_parameters(tokens, 0)
        else:
            parameters = []
            names: list[bytes] = []
            index = 1
            while tokens[index] != b")":
                name, nested, index = _keyword_and_parameters(tokens, index)
                names.append(name)
                parameters.append((name, nested))
            index += 1
            keyword = b"(%s)" % b" ".join(names)
    except IndexError as exc:
        raise StepError("a statement ends too early") from exc
    if index != len(tokens):
        raise StepError("a statement goes on after its parameters")
    return keyword, parameters


def exact_text(value: Any) -> bytes:
    """A value with references and order as they stand. Two values with the same text are the same value."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, int):
        return b"#%d" % value
    if isinstance(value, list):
        return b"(%s)" % b",".join([exact_text(item) for item in value])
    return b"%s(%s)" % (value[0], b",".join([exact_text(item) for item in value[1]]))


def _real_text(value: float) -> bytes:
    if value in (float("inf"), float("-inf")):  # what a REAL beyond a double's range was read as, and reads as again
        return b"1.E+999" if value > 0 else b"-1.E+999"
    mantissa, _e, exponent = repr(value).partition("e")
    if "." not in mantissa:
        mantissa += "."
    elif mantissa.endswith(".0"):
        mantissa = mantissa[:-1]
    return f"{mantissa}E{exponent}".encode("ascii") if exponent else mantissa.encode("ascii")


def _escaped(match: re.Match[str]) -> str:
    found = match.group(0)
    if found == "'":
        return "''"
    if found == "\\":
        return "\\\\"
    if max(found) <= chr(_LAST_BMP):
        return f"\\X2\\{found.encode('utf-16-be', 'surrogatepass').hex().upper()}\\X0\\"
    return f"\\X4\\{found.encode('utf-32-be', 'surrogatepass').hex().upper()}\\X0\\"


def value_text(value: Any) -> bytes:
    """A value as an exchange file writes it."""
    if isinstance(value, int):
        return b"#%d" % value
    if isinstance(value, list):
        return b"(%s)" % b",".join([value_text(item) for item in value])
    if isinstance(value, tuple):
        return b"%s(%s)" % (value[0], b",".join([value_text(item) for item in value[1]]))
    first = value[:1]
    if first == b"r":
        return _real_text(float.fromhex(value[1:].decode("ascii")))
    if first == b"i":
        return value[1:]
    if first == b"s":
        return b"'%s'" % _NEEDS_ESCAPE.sub(_escaped, string_of_atom(value)).encode("ascii")
    if first == b"x":
        return b"'%s'" % value.split(b":", 1)[1].replace(b"'", b"''")
    return value


def statement_text(keyword: bytes, parameters: list[Any]) -> bytes:
    """A keyword and its parameters as a file writes them; a complex instance has no commas between its parts."""
    if keyword[:1] == b"(":
        return b"(%s)" % b"".join([value_text(part) for part in parameters])
    return b"%s(%s)" % (keyword, b",".join([value_text(item) for item in parameters]))


def write_exchange(out: BinaryIO, header: Iterable[tuple[bytes, list[Any]]], instances: Iterable[bytes]) -> None:
    """Write a whole file. ``instances`` are finished lines, ``#id=...;``, in the order they should have."""
    out.write(b"ISO-10303-21;\nHEADER;\n")
    for keyword, parameters in header:
        out.write(b"%s;\n" % statement_text(keyword, parameters))
    out.write(b"ENDSEC;\nDATA;\n")
    for line in instances:
        out.write(line)
    out.write(b"ENDSEC;\nEND-ISO-10303-21;\n")


def statements_of(text: bytes) -> Iterator[tuple[int, bytes]]:
    """The instances in a run of ``#id=...;`` lines, with what ends each: a raw string can hold a line break."""
    position = 0
    while position < len(text):
        match = _STATEMENT.match(text, position)
        if match is None or match.group(1) is None:
            raise StepError("a block of instances holds something else")
        yield int(match.group(1)), text[position : match.end()].lstrip()
        position = match.end()
        if text[position : position + 1] == _NEWLINE:
            position += 1


def _schema_name(parameters: list[Any]) -> str:
    names = parameters[0] if parameters else None
    if isinstance(names, list) and len(names) == 1 and isinstance(names[0], bytes) and names[0][:1] == b"s":
        return names[0].split(b":", 1)[1].decode("utf-8", "surrogatepass")
    raise StepError("FILE_SCHEMA does not name one schema")


class StepFile:
    """One exchange structure. Statements are parsed when they are asked for; only the file's bytes are kept."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.header: dict[bytes, bytes] = {}
        self.header_values: list[tuple[bytes, list[Any]]] = []
        self.schema = ""
        self._spans: dict[int, tuple[int, int]] = {}
        self._scan()

    def _statement(self, position: int) -> re.Match[bytes]:
        match = _STATEMENT.match(self.data, position)
        if match is None:
            raise StepError(f"line {self.data.count(_NEWLINE, 0, position) + 1} starts no statement")
        return match

    def _word(self, position: int, word: bytes) -> int:
        match = self._statement(position)
        found = match.group(2).strip()
        if found != word:
            raise StepError(f"{word.decode('ascii')} is what should come here, not {found[:40]!r}")
        return match.end()

    def _scan(self) -> None:
        position = len(_BYTE_ORDER_MARK) if self.data.startswith(_BYTE_ORDER_MARK) else 0
        position = self._word(position, b"ISO-10303-21")
        position = self._word(position, b"HEADER")
        while True:
            match = self._statement(position)
            position = match.end()
            body = match.group(2)
            if body.strip() == b"ENDSEC":
                break
            keyword, parameters = parse_statement(body)
            self.header[keyword] = b",".join([exact_text(item) for item in parameters])
            self.header_values.append((keyword, parameters))
            if keyword == b"FILE_SCHEMA":
                self.schema = _schema_name(parameters)
        position = self._word(position, b"DATA")
        spans = self._spans
        while True:
            match = self._statement(position)
            position = match.end()
            number = match.group(1)
            if number is None:
                if match.group(2).strip() != b"ENDSEC":
                    raise StepError(f"line {self.data.count(_NEWLINE, 0, match.start()) + 1} is not an instance")
                break
            step_id = _instance_id(number)
            if step_id in spans:
                raise StepError(f"instance #{step_id} is defined twice")
            spans[step_id] = match.span(2)
        self._word(position, b"END-ISO-10303-21")

    def __len__(self) -> int:
        return len(self._spans)

    def __contains__(self, step_id: int) -> bool:
        return step_id in self._spans

    def __getitem__(self, step_id: int) -> tuple[bytes, list[Any]]:
        start, end = self._spans[step_id]
        return parse_statement(self.data[start:end])

    def __iter__(self) -> Iterator[tuple[int, bytes, list[Any]]]:
        data = self.data
        for step_id, (start, end) in self._spans.items():
            keyword, parameters = parse_statement(data[start:end])
            yield step_id, keyword, parameters

    def ids(self) -> list[int]:
        return list(self._spans)

    def keyword_of(self, step_id: int) -> bytes:
        """An instance's keyword, without parsing it where that can be helped."""
        start, end = self._spans[step_id]
        match = _KEYWORD.match(self.data, start, end)
        return match.group(1).upper() if match else self[step_id][0]

    def text_of(self, step_id: int, limit: int = 200) -> str:
        """How the instance is written, for a report."""
        start, end = self._spans[step_id]
        text = self.data[start : min(end, start + limit)].decode("ascii", "replace")
        return f"#{step_id}={text}…" if end - start > limit else f"#{step_id}={text}"

    def raw_bytes(self) -> int:
        """How many bytes above 0x7F the file holds. None of them belongs in an exchange structure."""
        return len(self.data.translate(None, _ASCII))
