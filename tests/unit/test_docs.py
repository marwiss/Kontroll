# This file was generated with the assistance of an AI coding tool.
"""The documentation stays whole: links resolve, and the translations keep up with English.

English is the source under ``docs/``; every other language has the same pages under
``docs/<lang>/``. A page added or changed in English without its translations fails here, as a
new key in one language catalogue does in ``test_i18n.py``.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LANGUAGES = ("sv", "da", "nb", "nn", "fi", "is")
# Project logs, decisions and drafts are written for developers and stay in English.
ENGLISH_ONLY_PAGES = {"acceptance.md", "inventory.md", "dataspatium-coordination.md"}
ENGLISH_ONLY_FOLDERS = {"adr", "upstream", "examples", "images", "en", *LANGUAGES}

FENCED = re.compile(r"^[ \t]*```.*?^[ \t]*```[ \t]*$", re.DOTALL | re.MULTILINE)
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|src=\"([^\"]+)\"")
SETTING = re.compile(r"OPENCDE_[A-Z0-9_]+")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def english_pages() -> list[str]:
    pages = []
    for path in DOCS.rglob("*.md"):
        relative = path.relative_to(DOCS)
        if relative.parts[0] not in ENGLISH_ONLY_FOLDERS and relative.name not in ENGLISH_ONLY_PAGES:
            pages.append(relative.as_posix())
    return sorted(pages)


def markdown_files() -> list[Path]:
    top_level = [ROOT / name for name in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md")]
    return top_level + sorted(DOCS.rglob("*.md"))


def relative_targets(text: str) -> list[str]:
    """Link and image targets of a page, leaving out code, other sites and anchors on the page."""
    prose = INLINE_CODE.sub("", FENCED.sub("", text))
    targets = [first or second for first, second in LINK.findall(prose)]
    return [
        target.split("#", 1)[0] for target in targets if not target.startswith(("http://", "https://", "mailto:", "#"))
    ]


def shape(text: str) -> dict[str, object]:
    """What a translation must keep: its sections, tables, code lines and settings."""
    fenced = FENCED.findall(text)
    prose = FENCED.sub("", text)
    return {
        "headings": len(re.findall(r"^#{1,6} ", prose, re.MULTILINE)),
        "table rows": len(re.findall(r"^[ \t]*\|", prose, re.MULTILINE)),
        "code blocks": len(fenced),
        "code lines": sum(block.count("\n") for block in fenced),
        "settings": sorted(set(SETTING.findall(text))),
    }


def test_the_english_pages_are_found() -> None:
    pages = english_pages()
    assert {"client-guide.md", "quickstart.md", "deploy/local.md", "security/controls.md"} <= set(pages)
    assert not ENGLISH_ONLY_PAGES & set(pages)


@pytest.mark.parametrize("path", markdown_files(), ids=lambda path: path.relative_to(ROOT).as_posix())
def test_relative_links_point_at_something(path: Path) -> None:
    broken = [target for target in relative_targets(read(path)) if not (path.parent / target).exists()]
    assert not broken, f"{path.relative_to(ROOT)} links to what does not exist: {broken}"


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("page", english_pages())
def test_every_page_has_its_translation_and_keeps_its_shape(lang: str, page: str) -> None:
    translation = DOCS / lang / page
    assert translation.is_file(), f"docs/{page} has no translation in docs/{lang}/"
    assert shape(read(translation)) == shape(read(DOCS / page))


@pytest.mark.parametrize("lang", LANGUAGES)
def test_a_translation_has_no_page_without_a_source(lang: str) -> None:
    folder = DOCS / lang
    extra = {path.relative_to(folder).as_posix() for path in folder.rglob("*.md")} - set(english_pages())
    assert extra <= {"README.md"}, f"docs/{lang}/ has pages English does not: {extra}"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_a_translated_page_links_to_the_translation(lang: str) -> None:
    """A link from a translated page goes to the same language when that page is translated."""
    folder = DOCS / lang
    translated = {(DOCS / page).resolve() for page in english_pages()}
    for path in folder.rglob("*.md"):
        for target in relative_targets(read(path)):
            assert (path.parent / target).resolve() not in translated, (
                f"{path.relative_to(ROOT)} links to the English {target}; link to docs/{lang}/ instead"
            )
