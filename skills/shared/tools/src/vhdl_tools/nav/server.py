"""vhdl-tools nav: exact VHDL lookups through vhdl_ls, the VHDL language server."""

from __future__ import annotations

import functools
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from vhdl_tools.nav import NavError
from vhdl_tools.nav.config import (
    DIRECTORY_MAP_NOTE,
    empty_libraries,
    find_config,
    library_files,
    read_libraries,
    write_directory_map,
    write_init,
)
from vhdl_tools.nav.formatting import (
    count,
    format_context,
    format_hits,
    format_outline,
    format_refs,
    format_tree,
    header,
    hover_text,
    rel,
    source_lines,
)
from vhdl_tools.nav.index import FileIndex, build_index, regions
from vhdl_tools.nav.lsp import DEFAULT_TIMEOUT, LspSession, find_std_libraries, find_vhdl_ls, vhdl_ls_command
from vhdl_tools.nav.resolve import (
    Position,
    find_hits,
    hit_at,
    identifier_at,
    not_found_message,
    parse_pos,
    position_params,
    resolve_one,
)
from vhdl_tools.nav.symbols import Hit, Node, locations, nodes_from_document_symbols
from vhdl_tools.nav.tree import build_tree
from vhdl_tools.registry import ToolError, ToolRegistry

tools = ToolRegistry(
    "vhdl_tools.nav",
    instructions=(
        "VHDL through vhdl_ls, the VHDL language server: a file's skeleton with "
        "line ranges to read from (index), where a name is declared (find, def), "
        "who uses it (refs), its declaration or a package's contents (show), and "
        "an entity's instantiation tree. Names are identifiers, optionally library-qualified "
        "(fifo, fifo.fifo); --pos is FILE:LINE[:COL], 1-based. The project's "
        "vhdl_ls.toml (found upward from the current directory, or --config) "
        "defines the libraries; nav init writes one. Output paths are relative "
        "to that file's directory."
    ),
    error_prefixes=("Error:",),
)

#: Reference lines that are part of the declaration itself, not uses of it.
_STRUCTURAL = re.compile(r"\s*(end|architecture|package\s+body)\b", re.IGNORECASE)


@dataclass
class Project:
    config: Path
    root: Path
    libraries: dict[str, list[str]]
    #: Lines shown with the answer (or under the error) about how input was read.
    notes: list[str] = field(default_factory=list)

    @property
    def library_names(self) -> list[str]:
        return list(self.libraries)

    @functools.cached_property
    def files(self) -> dict[Path, str]:
        """Project file -> library, for searching past vhdl_ls's symbol cap."""
        return {
            path: library
            for library, patterns in self.libraries.items()
            for path in library_files(self.config, patterns)
        }


def _run(config: str | None, body: Callable[[Project, LspSession], str]) -> str:
    project: Project | None = None
    try:
        path = find_config(Path.cwd(), config)
        project = Project(path, path.parent, read_libraries(path))
        empty = empty_libraries(path, project.libraries)
        warning = (
            f"Warning: no files match the globs of {', '.join(empty)} in {path}; "
            "lookups there come back empty.\n"
            if empty
            else ""
        )
        vhdl_ls = find_vhdl_ls()
        command = vhdl_ls_command(vhdl_ls, find_std_libraries(vhdl_ls))
        with LspSession(project.root, command) as session:
            text = body(project, session)
        return warning + "".join(f"{note}\n" for note in project.notes) + text
    except NavError as exc:
        notes = "".join(f"\n{note}" for note in project.notes) if project else ""
        return ToolError(f"Error: {exc}{notes}")


def _target(
    project: Project,
    session: LspSession,
    name: str | None,
    pos: str | None,
    kind: str | None,
) -> tuple[Position, Hit | None]:
    if (name is None) == (pos is None):
        raise NavError("give exactly one of --name or --pos")
    if name is not None:
        hit = resolve_one(session, name, project.root, project.library_names, kind, project.files)
        return Position(hit.path, hit.line, hit.col), hit
    position = parse_pos(pos, project.root)
    if position.guessed:
        word = identifier_at(position.path, position.line, position.col)
        project.notes.append(
            f"Note: --pos {pos} has no column, so it looked up {word} "
            f"(column {position.col + 1}), the first name on that line; "
            "add :COL for another name."
        )
    return position, None


def _definitions(session: LspSession, position: Position) -> list[tuple[Path, int, int]]:
    session.open(position.path)
    return locations(session.request("textDocument/definition", position_params(position)))


def _declaration_at(project: Project, session: LspSession, path: Path, line: int, col: int) -> Hit:
    return hit_at(session, path, line, identifier_at(path, line, col), project.files)


def _document_symbols(session: LspSession, path: Path) -> list[Node]:
    session.open(path)
    return nodes_from_document_symbols(
        session.request("textDocument/documentSymbol", {"textDocument": {"uri": path.as_uri()}})
    )


def _title(hit: Hit, root: Path) -> str:
    return header(hit, root) if hit.kind else f"{rel(hit.path, root)}:{hit.line + 1}"


@tools.tool()
def nav_find(
    name: str, kind: str | None = None, substring: bool = False, config: str | None = None
) -> str:
    """Declarations with this name: one line each (kind, name, [library], file:line).

    --name is an identifier, optionally library-qualified (fifo, fifo.fifo,
    lib.pkg.const). Exact and case-insensitive; --substring lists names that
    contain it, from the project's own libraries only. --kind filters: entity,
    architecture, package, component, function, procedure, type, signal,
    constant, port, generic."""

    def body(project: Project, session: LspSession) -> str:
        found = find_hits(session, name, kind, substring, project.library_names, project.files)
        if not found.hits and (not found.truncated or found.completed):
            return not_found_message(name, project.library_names, kind)
        return format_hits(found.hits, project.root, found.truncated, found.completed)

    return _run(config, body)


@tools.tool()
def nav_def(
    name: str | None = None,
    pos: str | None = None,
    kind: str | None = None,
    context: int = 3,
    config: str | None = None,
) -> str:
    """Where a name is declared, with --context lines of source after it.

    Give --name (see find) or --pos FILE:LINE[:COL] (1-based, e.g. from grep or
    an error message; without COL, the first identifier on the line)."""

    def body(project: Project, session: LspSession) -> str:
        position, hit = _target(project, session, name, pos, kind)
        if hit is not None:
            return format_context(hit.path, hit.line, context, header(hit, project.root))
        found = _definitions(session, position)
        if not found:
            word = identifier_at(position.path, position.line, position.col)
            raise NavError(f"vhdl_ls found no declaration for {word} at {pos}")
        blocks = []
        for path, line, col in found:
            decl = _declaration_at(project, session, path, line, col)
            blocks.append(format_context(path, line, context, _title(decl, project.root)))
        return "\n\n".join(blocks)

    return _run(config, body)


@tools.tool()
def nav_refs(
    name: str | None = None,
    pos: str | None = None,
    kind: str | None = None,
    with_decl: bool = False,
    config: str | None = None,
) -> str:
    """Every use of a declaration, grouped by file (line:col and the source line).

    Give --name or --pos as for def. Without --with-decl the declaration itself
    and its end/architecture-of/package-body lines are left out."""

    def body(project: Project, session: LspSession) -> str:
        position, hit = _target(project, session, name, pos, kind)
        if hit is None:
            found = _definitions(session, position)
            declaration = found[0] if found else None
            label = identifier_at(position.path, position.line, position.col)
        else:
            declaration = (hit.path, hit.line, hit.col)
            label = hit.name
        session.open(position.path)
        refs = locations(
            session.request(
                "textDocument/references",
                {**position_params(position), "context": {"includeDeclaration": True}},
            )
        )
        if not with_decl:
            cache: dict[Path, list[str]] = {}

            def structural(ref: tuple[Path, int, int]) -> bool:
                lines = source_lines(ref[0], cache)
                return ref[1] < len(lines) and bool(_STRUCTURAL.match(lines[ref[1]]))

            refs = [r for r in refs if r != declaration and not structural(r)]
        if not refs:
            return f"No references to {label} outside its declaration"
        return format_refs(refs, project.root)

    return _run(config, body)


@tools.tool()
def nav_show(
    name: str | None = None,
    pos: str | None = None,
    kind: str | None = None,
    config: str | None = None,
) -> str:
    """A declaration as vhdl_ls reads it: an entity's or component's generics and
    ports, a subprogram's signature, a type. For a package: one line per
    declaration in it.

    Give --name or --pos as for def."""

    def body(project: Project, session: LspSession) -> str:
        position, hit = _target(project, session, name, pos, kind)
        if hit is None:
            found = _definitions(session, position)
            if found:
                path, line, col = found[0]
                hit = _declaration_at(project, session, path, line, col)
                position = Position(path, line, col)
        title = (
            _title(hit, project.root)
            if hit is not None
            else f"{rel(position.path, project.root)}:{position.line + 1}"
        )
        if hit is not None and hit.kind == "package":
            for node in _document_symbols(session, hit.path):
                if node.kind == "package" and node.line == hit.line:
                    return "\n".join([title, *format_outline(node.children, indent=1)])
        session.open(position.path)
        text = hover_text(session.request("textDocument/hover", position_params(position)))
        if not text:
            word = hit.name if hit is not None else identifier_at(position.path, position.line, position.col)
            raise NavError(f"vhdl_ls has no declaration text for {word}")
        return f"{title}\n{text}"

    return _run(config, body)


def file_index(file: str | Path, config: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> FileIndex:
    """The index of one file, its named regions and its lines; NavError on failure.

    Uses the nearest vhdl_ls.toml above the file (or ``config``); without one,
    the file's directory is mapped as one library so sibling files resolve."""
    path = Path(file).expanduser()
    if not path.is_file():
        raise NavError(f"no file {file}")
    path = path.resolve()
    try:
        root = find_config(path.parent, config).parent
        directory_map = None
    except NavError:
        if config:
            raise
        root = path.parent
        directory_map = write_directory_map(path.parent)
    vhdl_ls = find_vhdl_ls()
    command = vhdl_ls_command(vhdl_ls, find_std_libraries(vhdl_ls))
    try:
        env = {"VHDL_LS_CONFIG": str(directory_map)} if directory_map else None
        with LspSession(root, command, timeout, env) as session:
            nodes = _document_symbols(session, path)
    finally:
        if directory_map:
            shutil.rmtree(directory_map.parent, ignore_errors=True)
    lines = source_lines(path, {})
    text = build_index(str(file), nodes, lines)
    if directory_map:
        title, _, rest = text.partition("\n")
        text = "\n".join(part for part in (title, DIRECTORY_MAP_NOTE, rest) if part)
    return FileIndex(text, regions(nodes), lines)


@tools.tool()
def nav_index(file: str, config: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> str:
    """A compact skeleton of one VHDL file with [start-end] line ranges: context
    clauses, units, generics and ports with their types, declarations with
    types, subprograms, processes with sensitivity lists, generates and
    instances with generic maps. Use it before reading a VHDL file, then read
    only the ranges you need.

    Needs no vhdl_ls.toml; the nearest one above the file (or --config) is
    used when present, so types resolve. --timeout is in seconds."""
    try:
        return file_index(file, config, timeout).text
    except NavError as exc:
        return ToolError(f"Error: {exc}")


@tools.tool()
def nav_tree(top: str, depth: int = 0, config: str | None = None) -> str:
    """The instantiation tree below an entity: one line per instance (label,
    instantiated entity, file:line), indented by level.

    --top is an entity name (fifo, fifo.fifo); --depth limits the levels shown
    (0 = all). Component instantiations are matched to the one entity of that
    name; notes in parentheses mark components, cycles and unresolved units."""

    def body(project: Project, session: LspSession) -> str:
        hit = resolve_one(
            session, top, project.root, project.library_names, "entity", project.files
        )
        tree = build_tree(session, hit, depth, project.files)
        return "\n".join(format_tree(tree, project.root))

    return _run(config, body)


@tools.tool()
def nav_init(layout: Literal["auto", "tsfpga", "flat"] = "auto", directory: str = ".") -> str:
    """Write a vhdl_ls.toml for the project in --directory (never overwrites one).

    tsfpga: one library per modules/<name>/ (auto picks it when modules/ holds
    VHDL); flat: one library 'lib' with every .vhd/.vhdl file. The standard
    libraries come from vhdl_ls's library directory; add third-party libraries
    (VUnit, OSVVM) by hand."""
    try:
        path, names = write_init(Path(directory).expanduser().resolve(), layout)
    except NavError as exc:
        return ToolError(f"Error: {exc}")
    lines = [f"Wrote {path} with {count(len(names), 'library', 'libraries')}: {', '.join(names)}"]
    try:
        find_std_libraries(find_vhdl_ls())
    except NavError as exc:
        lines.append(f"Note: lookups need vhdl_ls and its standard libraries first. {exc}")
    return "\n".join(lines)
