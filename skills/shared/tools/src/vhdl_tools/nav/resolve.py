"""Turn ``--name`` and ``--pos`` into declarations and LSP positions.

vhdl_ls's workspace/symbol match is fuzzy (``leaf`` also returns
``VitalDefaultPortFlag``), so every lookup filters the hits itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from vhdl_tools.nav import NavError
from vhdl_tools.nav.formatting import count, format_hits
from vhdl_tools.nav.symbols import (
    Hit,
    hit_from_symbol,
    kind_matches,
    matches_name,
    prefer_declarations,
    qualifier_matches,
    split_name,
)

WORKSPACE_SYMBOL_CAP = 200

_POS = re.compile(r"(?P<file>.+?):(?P<line>\d+)(?::(?P<col>\d+))?")
_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_KEYWORDS = frozenset(
    """abs access after alias all and architecture array assert attribute begin block
    body buffer bus case component configuration constant context disconnect downto
    else elsif end entity exit file for function generate generic group guarded if
    impure in inertial inout is label library linkage literal loop map mod nand new
    next nor not null of on open or others out package parameter port postponed
    procedure process protected pure range record register reject rem report return
    rol ror select severity shared signal sla sll sra srl subtype then to transport
    type unaffected units until use variable wait when while with xnor xor""".split()
)


class Requester(Protocol):
    def request(self, method: str, params: Any) -> Any: ...


@dataclass
class Found:
    hits: list[Hit]
    truncated: bool


@dataclass(frozen=True)
class Position:
    """A place in a file, 0-based like LSP. ``guessed``: no column was given,
    so ``col`` is the first name on the line."""

    path: Path
    line: int
    col: int
    guessed: bool = False


def find_hits(
    session: Requester,
    name: str,
    kind: str | None = None,
    substring: bool = False,
    libraries: Iterable[str] = (),
) -> Found:
    """Declarations named ``name`` (or, with ``substring``, containing it and in
    one of ``libraries``)."""
    prefix, ident = split_name(name)
    raw = session.request("workspace/symbol", {"query": ident}) or []
    hits = [hit_from_symbol(symbol) for symbol in raw]
    if substring:
        own = {library.lower() for library in libraries}
        hits = [
            h
            for h in hits
            if ident.lower() in h.name.lower()
            and h.library.lower() in own
            and qualifier_matches(h, prefix)
        ]
    else:
        hits = [h for h in hits if matches_name(h, name)]
    if kind:
        hits = [h for h in hits if kind_matches(h.kind, kind)]
    hits.sort(key=lambda h: (str(h.path), h.line, h.col))
    return Found(hits, len(raw) >= WORKSPACE_SYMBOL_CAP)


def not_found_message(name: str, libraries: list[str], kind: str | None = None) -> str:
    what = f"{kind} named {name}" if kind else f"declaration named {name}"
    if libraries:
        shown = ", ".join(libraries[:10]) + (", ..." if len(libraries) > 10 else "")
        where = f"the library map ({count(len(libraries), 'library', 'libraries')}: {shown})"
    else:
        where = "the library map (it defines no libraries)"
    return (
        f"No {what} in {where} or the standard libraries. "
        "The file may be outside the map in vhdl_ls.toml."
    )


def resolve_one(
    session: Requester, name: str, root: Path, libraries: list[str], kind: str | None = None
) -> Hit:
    """The one declaration ``name`` means; NavError when there is none or several."""
    found = find_hits(session, name, kind)
    hits = prefer_declarations(found.hits)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise NavError(not_found_message(name, libraries, kind))
    ident = split_name(name)[1]
    raise NavError(
        f"{name} is ambiguous; pass lib.{ident}, --kind or --pos:\n"
        + format_hits(hits, root, found.truncated)
    )


def hit_at(session: Requester, path: Path, line: int, name: str) -> Hit:
    """The declaration of ``name`` at ``path:line`` (0-based), if workspace/symbol
    lists it; else a bare Hit for that place."""
    for hit in find_hits(session, name).hits:
        if hit.path == path and hit.line == line:
            return hit
    return Hit("", name, "", path, line, 0)


def existing_file(file: str, root: Path) -> Path:
    """``file`` relative to the current directory, else to the project root."""
    given = Path(file).expanduser()
    candidates = (given,) if given.is_absolute() else (given, root / given)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise NavError(
        f"no file {file} (relative paths are tried from the current directory, then from {root})"
    )


def parse_pos(pos: str, root: Path) -> Position:
    """``FILE:LINE[:COL]`` (1-based). Without COL, the first identifier on the line
    that is not a VHDL keyword."""
    match = _POS.fullmatch(pos.strip())
    if not match:
        raise NavError(f"--pos {pos!r}: expected FILE:LINE or FILE:LINE:COL (1-based)")
    path = existing_file(match["file"], root)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    line = int(match["line"]) - 1
    if not 0 <= line < len(lines):
        raise NavError(f"--pos {pos}: {path.name} has {len(lines)} lines")
    text = lines[line]
    if match["col"] is not None:
        col = int(match["col"]) - 1
        if not any(t.start() <= col < t.end() for t in _IDENT.finditer(text)):
            raise NavError(f"--pos {pos} is not on an identifier:\n  {text}\n  {' ' * max(col, 0)}^")
        return Position(path, line, col)
    code = text.split("--", 1)[0]
    for token in _IDENT.finditer(code):
        if token.group().lower() not in _KEYWORDS:
            return Position(path, line, token.start(), guessed=True)
    raise NavError(f"--pos {pos}: no identifier on that line: {text.strip()}")


def identifier_at(path: Path, line: int, col: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not 0 <= line < len(lines):
        return ""
    for token in _IDENT.finditer(lines[line]):
        if token.start() <= col < token.end():
            return token.group()
    return ""


def position_params(position: Position) -> dict:
    return {
        "textDocument": {"uri": position.path.as_uri()},
        "position": {"line": position.line, "character": position.col},
    }
