"""vhdl-tools nav: exact VHDL lookups through vhdl_ls, the VHDL language server."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vhdl_tools.nav import NavError
from vhdl_tools.nav.config import empty_libraries, find_config, read_libraries
from vhdl_tools.nav.formatting import (
    format_context,
    format_hits,
    format_outline,
    format_refs,
    header,
    hover_text,
    rel,
    source_lines,
)
from vhdl_tools.nav.index import build_index
from vhdl_tools.nav.lsp import LspSession, find_std_libraries, find_vhdl_ls, vhdl_ls_command
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

    @property
    def library_names(self) -> list[str]:
        return list(self.libraries)


def _run(config: str | None, body: Callable[[Project, LspSession], str]) -> str:
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
            return warning + body(project, session)
    except NavError as exc:
        return ToolError(f"Error: {exc}")


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
        hit = resolve_one(session, name, project.root, project.library_names, kind)
        return Position(hit.path, hit.line, hit.col), hit
    return parse_pos(pos, project.root), None


def _definitions(session: LspSession, position: Position) -> list[tuple[Path, int, int]]:
    session.open(position.path)
    return locations(session.request("textDocument/definition", position_params(position)))


def _declaration_at(session: LspSession, path: Path, line: int, col: int) -> Hit:
    return hit_at(session, path, line, identifier_at(path, line, col))


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
        found = find_hits(session, name, kind, substring, project.library_names)
        if not found.hits and not found.truncated:
            return not_found_message(name, project.library_names, kind)
        return format_hits(found.hits, project.root, found.truncated)

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
            decl = _declaration_at(session, path, line, col)
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
                hit = _declaration_at(session, path, line, col)
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


@tools.tool()
def nav_index(file: str, config: str | None = None) -> str:
    """A compact skeleton of one VHDL file with [start-end] line ranges: context
    clauses, units, generics and ports with their types, declarations,
    subprograms, processes, generates and instances. Use it before reading a
    VHDL file, then read only the ranges you need.

    Needs no vhdl_ls.toml; the nearest one above the file (or --config) is
    used when present, so types resolve."""
    try:
        path = Path(file).expanduser()
        if not path.is_file():
            raise NavError(f"no file {file}")
        path = path.resolve()
        try:
            root = find_config(path.parent, config).parent
        except NavError:
            if config:
                raise
            root = path.parent
        vhdl_ls = find_vhdl_ls()
        command = vhdl_ls_command(vhdl_ls, find_std_libraries(vhdl_ls))
        with LspSession(root, command) as session:
            nodes = _document_symbols(session, path)
        return build_index(file, nodes, source_lines(path, {}))
    except NavError as exc:
        return ToolError(f"Error: {exc}")
