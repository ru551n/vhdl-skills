"""Compact text for nav results. Records carry 0-based lines; output is 1-based."""

from __future__ import annotations

from pathlib import Path

from vhdl_tools.nav.symbols import Hit, Node, TreeNode

CAP_NOTE = (
    "vhdl_ls returns at most 200 symbols per query, so this list may be "
    "incomplete; use a longer name or --kind"
)

#: documentSymbol children that repeat what their parent's line already says.
_OUTLINE_SKIP = frozenset({"parameter", "literal"})


def count(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _label(kind: str, name: str, detail: str) -> str:
    text = f"{kind} {name}" if kind else name
    if not detail:
        return text
    return text + detail if detail.startswith("[") else f"{text} {detail}"


def describe(hit: Hit) -> str:
    return _label(hit.kind, hit.name, hit.detail)


def header(hit: Hit, root: Path) -> str:
    return f"{describe(hit)}  [{hit.container}]  {rel(hit.path, root)}:{hit.line + 1}"


def format_hits(hits: list[Hit], root: Path, truncated: bool = False) -> str:
    rows = [(describe(h), f"[{h.container}]", f"{rel(h.path, root)}:{h.line + 1}") for h in hits]
    lines = []
    if rows:
        widths = [max(len(row[i]) for row in rows) for i in range(3)]
        lines = ["  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip() for row in rows]
    lines.append(count(len(hits), "hit"))
    if truncated:
        lines.append(CAP_NOTE)
    return "\n".join(lines)


def source_lines(path: Path, cache: dict[Path, list[str]]) -> list[str]:
    if path not in cache:
        cache[path] = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return cache[path]


def format_context(path: Path, line: int, context: int, title: str) -> str:
    """``title``, then source line ``line`` and ``context`` lines after it."""
    lines = source_lines(path, {})
    end = min(len(lines), line + 1 + context)
    width = len(str(end))
    return "\n".join([title, *(f"{n + 1:>{width}}  {lines[n]}" for n in range(line, end))])


def format_refs(refs: list[tuple[Path, int, int]], root: Path) -> str:
    cache: dict[Path, list[str]] = {}
    by_file: dict[Path, list[tuple[int, int]]] = {}
    for path, line, col in sorted(refs, key=lambda r: (rel(r[0], root), r[1], r[2])):
        by_file.setdefault(path, []).append((line, col))
    out = []
    for path, spots in by_file.items():
        out.append(rel(path, root))
        text = source_lines(path, cache)
        for line, col in spots:
            source = text[line].strip() if line < len(text) else ""
            out.append(f"  {line + 1:>5}:{col + 1:<4}{source}")
    out.append(f"{count(len(refs), 'reference')} in {count(len(by_file), 'file')}")
    return "\n".join(out)


def hover_text(result: object) -> str:
    contents = result.get("contents") if isinstance(result, dict) else result
    parts = contents if isinstance(contents, list) else [contents]
    texts = []
    for part in parts:
        if isinstance(part, dict):
            texts.append(str(part.get("value", "")))
        elif isinstance(part, str):
            texts.append(part)
    lines = "\n".join(t.strip() for t in texts if t and t.strip()).splitlines()
    return "\n".join(line for line in lines if not line.startswith("```")).strip()


def format_outline(nodes: list[Node], indent: int = 0) -> list[str]:
    out = []
    for node in nodes:
        if node.kind in _OUTLINE_SKIP:
            continue
        out.append(f"{'  ' * indent}{_label(node.kind, node.name, node.detail)}  L{node.line + 1}")
        out.extend(format_outline(node.children, indent + 1))
    return out


def format_tree(node: TreeNode, root: Path, indent: int = 0) -> list[str]:
    where = header(node.unit, root) if node.unit is not None else node.target
    text = f"{node.label} : {where}" if node.label else where
    if node.note:
        text += f"  ({node.note})"
    out = ["  " * indent + text]
    for child in node.children:
        out.extend(format_tree(child, root, indent + 1))
    return out
