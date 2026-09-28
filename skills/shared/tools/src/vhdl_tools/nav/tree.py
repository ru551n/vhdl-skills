"""Instantiation tree below an entity.

An entity's architectures are the ``architecture <a> of <entity>`` lines among
its references (vhdl_ls always includes them); their instances come from
documentSymbol, also inside generate blocks. An entity or configuration
instantiation is resolved with ``definition`` on the unit name. A component
instantiation resolves to the component declaration, so the tree uses the
one entity of that name instead, when there is exactly one.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import Path

from vhdl_tools.nav.formatting import source_lines
from vhdl_tools.nav.index import instance_target
from vhdl_tools.nav.lsp import LspSession
from vhdl_tools.nav.resolve import find_hits, hit_at
from vhdl_tools.nav.symbols import (
    Hit,
    Node,
    TreeNode,
    locations,
    nodes_from_document_symbols,
    prefer_declarations,
)


#: A branch header inside a generate: ``[label :] if/elsif ... generate``,
#: ``else generate`` or ``when choice =>``.
_BRANCH = re.compile(
    r"\s*(?:\w+\s*:\s*)?(?:(?P<cond>(?:if|elsif)\b.*?|else)\s*generate\b|when\s+(?P<choice>.*?)=>)",
    re.IGNORECASE,
)


def _instances(nodes: list[Node], parent: Node | None = None) -> Iterator[tuple[Node, Node | None]]:
    """Instances with the generate (or block) directly around them, if any."""
    for node in nodes:
        if node.kind == "instance":
            yield node, parent
        else:
            yield from _instances(node.children, node if node.kind == "generate" else parent)


def _branch(lines: list[str], instance: Node, generate: Node | None) -> str:
    """The generate branch an instance sits in, from the nearest header above it."""
    if generate is None:
        return ""
    for n in range(instance.start_line - 1, generate.start_line - 1, -1):
        match = _BRANCH.match(lines[n]) if n < len(lines) else None
        if match:
            if match["cond"]:
                return "branch: " + " ".join(match["cond"].split())
            return "branch: when " + " ".join(match["choice"].split())
    return ""


def _key(hit: Hit) -> tuple[str, str]:
    return hit.library.lower(), hit.name.lower()


def _add_note(note: str, extra: str) -> str:
    return f"{note}; {extra}" if note else extra


class _TreeBuilder:
    def __init__(self, session: LspSession, depth: int, files: Mapping[Path, str] | None) -> None:
        self.session = session
        self.depth = depth
        self.files = files
        self.cache: dict[Path, list[str]] = {}

    def expand(self, node: TreeNode, seen: tuple[tuple[str, str], ...], level: int) -> None:
        assert node.unit is not None
        architectures = self.architectures(node.unit)
        if len(architectures) > 1:
            names = ", ".join(arch.name for _, arch in architectures)
            node.note = _add_note(node.note, f"{len(architectures)} architectures: {names}")
        for path, arch in architectures:
            instances = list(_instances(arch.children))
            labels = [instance.name.lower() for instance, _ in instances]
            for instance, generate in instances:
                child = self.resolve_instance(path, instance)
                if labels.count(instance.name.lower()) > 1:
                    branch = _branch(source_lines(path, self.cache), instance, generate)
                    if branch:
                        child.note = _add_note(child.note, branch)
                node.children.append(child)
                if child.unit is None or child.unit.kind != "entity":
                    continue
                key = _key(child.unit)
                if key in seen:
                    child.note = _add_note(child.note, "cycle")
                elif not self.depth or level < self.depth:
                    self.expand(child, (*seen, key), level + 1)

    def architectures(self, entity: Hit) -> list[tuple[Path, Node]]:
        self.session.open(entity.path)
        refs = locations(
            self.session.request(
                "textDocument/references",
                {
                    "textDocument": {"uri": entity.path.as_uri()},
                    "position": {"line": entity.line, "character": entity.col},
                    "context": {"includeDeclaration": True},
                },
            )
        )
        pattern = re.compile(
            rf"\s*architecture\s+\w+\s+of\s+{re.escape(entity.name)}\b", re.IGNORECASE
        )
        found = []
        for path, line, _ in refs:
            lines = source_lines(path, self.cache)
            if line < len(lines) and pattern.match(lines[line]):
                self.session.open(path)
                nodes = nodes_from_document_symbols(
                    self.session.request(
                        "textDocument/documentSymbol", {"textDocument": {"uri": path.as_uri()}}
                    )
                )
                found += [(path, n) for n in nodes if n.kind == "architecture" and n.line == line]
        return found

    def resolve_instance(self, path: Path, instance: Node) -> TreeNode:
        target = instance_target(instance, source_lines(path, self.cache))
        if target is None:
            return TreeNode(instance.name, "?", None, "could not read the instantiation")
        how, unit, line, col = target
        last = unit.rsplit(".", 1)[-1]
        if how == "component":
            entities = prefer_declarations(find_hits(self.session, last, kind="entity", files=self.files).hits)
            if len(entities) == 1:
                return TreeNode(instance.name, unit, entities[0], "component")
            return TreeNode(instance.name, unit, None, f"component; no unique entity named {last}")
        found = locations(
            self.session.request(
                "textDocument/definition",
                {"textDocument": {"uri": path.as_uri()}, "position": {"line": line, "character": col}},
            )
        )
        if not found:
            return TreeNode(instance.name, unit, None, "unresolved")
        target_path, target_line, _ = found[0]
        return TreeNode(instance.name, unit, hit_at(self.session, target_path, target_line, last, self.files))


def build_tree(
    session: LspSession, top: Hit, depth: int = 0, files: Mapping[Path, str] | None = None
) -> TreeNode:
    """The instances below ``top``; ``depth`` 0 means no limit. ``files`` (project
    file -> library) lets name lookups search past vhdl_ls's symbol cap."""
    root = TreeNode("", top.name, top)
    _TreeBuilder(session, depth, files).expand(root, (_key(top),), 1)
    return root
