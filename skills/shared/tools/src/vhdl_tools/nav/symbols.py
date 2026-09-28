"""Records for vhdl_ls symbol replies (workspace/symbol, documentSymbol, locations).

vhdl_ls names symbols ``<kind words> '<identifier>'<detail>`` (``entity 'fifo'``,
``record type 'axi_m2s_r_t'``, ``port 'clk' : in``). Subprograms are
``function <name>[<signature>]`` and enumeration literals ``<name>[return <type>]``.
``containerName`` is the library for design units and ``lib.unit`` for
declarations inside one. Lines and columns here are 0-based, as on the wire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

_QUOTED = re.compile(r"(?P<kind>[a-z][a-z ]*?) '(?P<name>[^']+)'(?P<detail>.*)")
#: Statements vhdl_ls lists without a label (``'process'``): kind only, no name.
_UNLABELLED = frozenset({"process", "block", "generate"})
_SUBPROGRAM = re.compile(r"(?P<kind>function|procedure) (?P<name>[^\[\s]+)(?P<detail>.*)")
_LITERAL = re.compile(r"(?P<name>[^\[\s]+)(?P<detail>\[.*)")


def parse_symbol_name(text: str) -> tuple[str, str, str]:
    """``"port 'clk' : in"`` -> ``("port", "clk", ": in")``."""
    if text in _UNLABELLED:
        return text, "", ""
    match = _QUOTED.fullmatch(text) or _SUBPROGRAM.fullmatch(text)
    if match:
        return match["kind"], match["name"], match["detail"].strip()
    match = _LITERAL.fullmatch(text)
    if match:
        return "literal", match["name"], match["detail"].strip()
    return "", text, ""


def uri_to_path(uri: str) -> Path:
    return Path(unquote(urlparse(uri).path))


@dataclass(frozen=True)
class Hit:
    """One declaration, as workspace/symbol reports it."""

    kind: str
    name: str
    container: str
    path: Path
    line: int
    col: int
    detail: str = ""

    @property
    def library(self) -> str:
        return self.container.split(".")[0]


def hit_from_symbol(symbol: dict) -> Hit:
    kind, name, detail = parse_symbol_name(symbol["name"])
    location = symbol["location"]
    start = location["range"]["start"]
    return Hit(
        kind,
        name,
        symbol.get("containerName") or "",
        uri_to_path(location["uri"]),
        start["line"],
        start["character"],
        detail,
    )


@dataclass
class Node:
    """One documentSymbol entry: ``line``/``col`` is its name, the range spans
    ``start_line``..``end_line``."""

    kind: str
    name: str
    detail: str
    line: int
    col: int
    start_line: int
    end_line: int
    children: list[Node] = field(default_factory=list)


def nodes_from_document_symbols(items: list[dict] | None) -> list[Node]:
    nodes = []
    for item in items or []:
        kind, name, detail = parse_symbol_name(item["name"])
        name_start = item.get("selectionRange", item["range"])["start"]
        nodes.append(
            Node(
                kind,
                name,
                detail,
                name_start["line"],
                name_start["character"],
                item["range"]["start"]["line"],
                item["range"]["end"]["line"],
                nodes_from_document_symbols(item.get("children")),
            )
        )
    return nodes


def locations(result: object) -> list[tuple[Path, int, int]]:
    """Location / Location[] / LocationLink[] / None -> ``(path, line, col)``."""
    if not result:
        return []
    items = result if isinstance(result, list) else [result]
    found = []
    for item in items:
        uri = item.get("uri") or item["targetUri"]
        start = (item.get("range") or item["targetSelectionRange"])["start"]
        found.append((uri_to_path(uri), start["line"], start["character"]))
    return found


def split_name(name: str) -> tuple[str | None, str]:
    """``"lib.unit.x"`` -> ``("lib.unit", "x")``. ``work.`` means any library."""
    prefix, _, ident = name.rpartition(".")
    if not prefix or prefix.lower() == "work":
        return None, ident
    return prefix, ident


def kind_matches(kind: str, wanted: str) -> bool:
    """``--kind type`` matches ``type``, ``record type``, ``array type``..."""
    wanted = wanted.lower()
    return kind == wanted or kind.endswith(" " + wanted)


def qualifier_matches(hit: Hit, prefix: str | None) -> bool:
    """A qualifier is any run of whole dotted parts of the container: the
    library, a package (``types_pkg`` in ``common.types_pkg``), a package and
    type, and so on. Case-insensitive."""
    if prefix is None:
        return True
    return f".{prefix.lower()}." in f".{hit.container.lower()}."


def matches_name(hit: Hit, name: str) -> bool:
    """Exact and case-insensitive, qualified as ``qualifier_matches`` allows."""
    prefix, ident = split_name(name)
    return hit.name.lower() == ident.lower() and qualifier_matches(hit, prefix)


def prefer_declarations(hits: list[Hit]) -> list[Hit]:
    """Drop ``package body X`` when ``package X`` of the same library is present."""
    declared = {(h.library.lower(), h.name.lower(), h.kind) for h in hits}
    return [
        h
        for h in hits
        if not (
            h.kind.endswith(" body")
            and (h.library.lower(), h.name.lower(), h.kind.removesuffix(" body")) in declared
        )
    ]


@dataclass
class TreeNode:
    """One entry of an instantiation tree. The root has an empty ``label``."""

    label: str
    target: str
    unit: Hit | None
    note: str = ""
    children: list[TreeNode] = field(default_factory=list)
