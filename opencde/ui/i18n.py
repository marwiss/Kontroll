# This file was generated with the assistance of an AI coding tool.
"""The language layer of the server's pages.

Every text a page shows comes from a flat catalogue per language
(``opencde/ui/i18n/<lang>.json``, dotted keys, ``{name}`` parameters), the
key style Dataspatium uses, with the same key names where the two products
share a concept (``opencde.signin``, ``opencde.project``, ``common.cancel`` ...).
English is the source; a key missing from another language falls back to
English, and a key missing everywhere renders as the key itself so that the
gap is visible.

The language of a request is chosen in this order: ``?lang=`` in the query
string (remembered in a cookie), the cookie, the browser's ``Accept-Language``,
English. Rendering runs synchronously inside one request, so the chosen
language sits in a context variable that the ``t()`` function of the
templates, and the macros they import, read.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request

LANGUAGES: tuple[str, ...] = ("sv", "da", "nb", "nn", "fi", "is", "en")
LANGUAGE_NAMES: dict[str, str] = {
    "sv": "Svenska",
    "da": "Dansk",
    "nb": "Norsk bokmål",
    "nn": "Norsk nynorsk",
    "fi": "Suomi",
    "is": "Íslenska",
    "en": "English",
}
DEFAULT_LANGUAGE = "en"
COOKIE_NAME = "opencde_lang"
COOKIE_MAX_AGE = 365 * 24 * 3600
QUERY_PARAM = "lang"

_CATALOGUE_DIR = Path(__file__).resolve().parent / "i18n"
_catalogues: dict[str, dict[str, str]] = {
    lang: json.loads((_CATALOGUE_DIR / f"{lang}.json").read_text(encoding="utf-8")) for lang in LANGUAGES
}

current_language: ContextVar[str] = ContextVar("opencde_language", default=DEFAULT_LANGUAGE)


class _Params(dict[str, Any]):
    """Leaves unknown ``{placeholders}`` visible instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def catalogue(lang: str) -> dict[str, str]:
    return _catalogues[lang]


def translate(lang: str, key: str, **params: Any) -> str:
    text = _catalogues.get(lang, {}).get(key) or _catalogues[DEFAULT_LANGUAGE].get(key) or key
    return text.format_map(_Params(params)) if params else text


def t(key: str, **params: Any) -> str:
    """The template function: the current request's language, set by ``render()``."""
    return translate(current_language.get(), key, **params)


def tr(request: Request, key: str, **params: Any) -> str:
    """For Python code that builds page texts before ``render()`` runs."""
    return translate(negotiate(request), key, **params)


def tr_error(request: Request, exc: Exception) -> str:
    """A :class:`~opencde.errors.UserFacingError` in the request's language, or any other error's message."""
    key = getattr(exc, "key", None)
    if not key:
        return str(exc)
    lang = negotiate(request)
    return _translate_value(lang, exc)


def _translate_value(lang: str, value: Any) -> Any:
    """Values that carry ``key`` and ``params`` are translated, lists of them joined; anything else passes through."""
    if isinstance(value, list | tuple):
        return "; ".join(str(_translate_value(lang, item)) for item in value)
    key = getattr(value, "key", None)
    if not key:
        return value
    params = {name: _translate_value(lang, item) for name, item in getattr(value, "params", {}).items()}
    return translate(lang, key, **params)


def _accept_language(header: str) -> list[str]:
    """Language tags from ``Accept-Language`` in preference order, lowercased, without quality values."""
    choices: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        tag, _, rest = part.strip().partition(";")
        if not tag:
            continue
        quality = 1.0
        if rest.strip().startswith("q="):
            try:
                quality = float(rest.strip()[2:])
            except ValueError:
                quality = 0.0
        choices.append((-quality, index, tag.lower()))
    return [tag for _, _, tag in sorted(choices)]


def _supported(tag: str) -> str | None:
    tag = tag.lower().replace("_", "-")
    if tag in LANGUAGES:
        return tag
    primary = tag.split("-")[0]
    if primary in LANGUAGES:
        return primary
    if primary == "no":  # plain Norwegian: Bokmål is the common written standard
        return "nb"
    return None


def negotiate(request: Request) -> str:
    """The language for this request: query, cookie, browser preference, English."""
    requested = request.query_params.get(QUERY_PARAM)
    if requested and (lang := _supported(requested)):
        return lang
    remembered = request.cookies.get(COOKIE_NAME)
    if remembered and (lang := _supported(remembered)):
        return lang
    for tag in _accept_language(request.headers.get("accept-language", "")):
        if lang := _supported(tag):
            return lang
    return DEFAULT_LANGUAGE


def requested_explicitly(request: Request) -> str | None:
    """The language the query string asks for, when it is one we have (to be remembered in the cookie)."""
    requested = request.query_params.get(QUERY_PARAM)
    return _supported(requested) if requested else None


def language_links(request: Request) -> list[tuple[str, str, str]]:
    """``(code, name, url)`` for the language switcher: the same page with ``?lang=`` set."""
    base = [(key, value) for key, value in request.query_params.multi_items() if key != QUERY_PARAM]
    links = []
    for lang in LANGUAGES:
        query = urlencode([*base, (QUERY_PARAM, lang)])
        links.append((lang, LANGUAGE_NAMES[lang], f"{request.url.path}?{query}"))
    return links
