"""Per-file skeleton with line ranges: the VHDL counterpart of the tree-sitter
``index`` tool in the Maki harness. Built from vhdl_ls documentSymbol (which is
syntactic, so it needs no library map) plus declaration text from the source.
Nodes carry 0-based lines; the output uses 1-based ``[start-end]`` ranges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vhdl_tools.nav.symbols import Node

#: What follows an instance label: ``: [entity|component|configuration] name``.
TARGET = re.compile(
    r"\s*:\s*(?:(?P<how>entity|component|configuration)\s+)?"
    r"(?P<unit>[A-Za-z]\w*(?:\s*\.\s*[A-Za-z]\w*)*)",
    re.IGNORECASE,
)

_CONTEXT = re.compile(r"\s*(library|use|context)\s+([^;]+);", re.IGNORECASE)
_ARCH_OF = re.compile(r"\s*architecture\s+\w+\s+of\s+(\w+)", re.IGNORECASE)
_INTERFACE = ("generic", "port")
#: One line each, in source order; generate and block bodies are nested.
_ITEMS = frozenset(
    {"process", "function", "procedure", "instance", "generate", "block"}
    | {"protected type", "protected type body"}
)
#: Regions whose contents are listed too (a protected type's methods, say).
_NESTED = frozenset({"generate", "block", "protected type", "protected type body"})
_HIDDEN = frozenset({"parameter", "literal"})
#: Names shown per declaration kind; generated register packages hold thousands.
_GROUP_NAME_CAP = 20
#: Declaration kinds shown with their type (``count : natural [3]``).
_TYPED = frozenset({"signal", "constant", "variable", "shared variable", "file"})
_SENSITIVITY = re.compile(r"\bprocess\s*\(([^)]*)\)", re.IGNORECASE)
_GENERIC_MAP = re.compile(r"\bgeneric\s+map\s*\(", re.IGNORECASE)
#: Characters of an instance's generic map shown in the index.
_GENERIC_MAP_CAP = 120
#: Start lines listed for the other overloads of a subprogram.
_OVERLOAD_STARTS_SHOWN = 6


def span(start: int, end: int) -> str:
    return f"[{start + 1}]" if start == end else f"[{start + 1}-{end + 1}]"


def declared_text(line: str, col: int) -> str:
    """``clk : in std_ulogic;`` with ``col`` at ``clk`` -> ``in std_ulogic``."""
    text = line[col:].split("--", 1)[0]
    _, colon, rest = text.partition(":")
    if not colon:
        return ""
    out = []
    depth = 0
    for char in rest:
        if char == ";" and depth == 0:
            break
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        out.append(char)
    return " ".join("".join(out).split())


def declaration_text(lines: list[str], node: Node) -> str:
    """``declared_text`` over every line of a declaration that spans several."""
    if not 0 <= node.line < len(lines):
        return ""
    last = min(max(node.end_line, node.line), len(lines) - 1)
    parts = [lines[node.line][node.col :], *lines[node.line + 1 : last + 1]]
    text = declared_text(" ".join(part.split("--", 1)[0] for part in parts), 0)
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", text))


def instance_target(instance: Node, lines: list[str]) -> tuple[str, str, int, int] | None:
    """``(how, unit, line, col)`` for an instance: how it instantiates, the unit
    name as written, and where that name's last segment is (0-based)."""
    statement = "\n".join(lines[instance.start_line : instance.end_line + 1])
    label_end = (
        sum(len(lines[i]) + 1 for i in range(instance.start_line, instance.line))
        + instance.col
        + len(instance.name)
    )
    match = TARGET.match(statement, label_end)
    if match is None:
        return None
    unit = re.sub(r"\s+", "", match["unit"])
    last = unit.rsplit(".", 1)[-1]
    index = statement.rfind(last, match.start("unit"), match.end("unit"))
    line = instance.start_line + statement.count("\n", 0, index)
    col = index - (statement.rfind("\n", 0, index) + 1)
    return (match["how"] or "component").lower(), unit, line, col


def _code(lines: list[str], start: int, end: int) -> str:
    """Lines ``start``..``end`` without comments, whitespace collapsed."""
    return " ".join(" ".join(line.split("--", 1)[0] for line in lines[start : end + 1]).split())


def _sensitivity(process: Node, lines: list[str]) -> str:
    match = _SENSITIVITY.search(_code(lines, process.start_line, min(process.end_line, process.start_line + 2)))
    if not match:
        return ""
    return " (" + ", ".join(name.strip() for name in match[1].split(",")) + ")"


def _generic_map(instance: Node, lines: list[str]) -> str:
    text = _code(lines, instance.start_line, instance.end_line)
    match = _GENERIC_MAP.search(text)
    if not match:
        return ""
    depth = 1
    for end in range(match.end(), len(text)):
        depth += {"(": 1, ")": -1}.get(text[end], 0)
        if depth == 0:
            break
    inner = text[match.end() : end].strip()
    if len(inner) > _GENERIC_MAP_CAP:
        inner = inner[:_GENERIC_MAP_CAP].rstrip(" ,") + " ..."
    return f" generic map ({inner})"


def _plural(kind: str) -> str:
    return kind + ("es" if kind.endswith("s") else "s")


def _context(lines: list[str], start: int, end: int) -> str | None:
    first = last = None
    names: list[str] = []
    for n in range(start, min(end, len(lines))):
        match = _CONTEXT.match(lines[n])
        if not match:
            continue
        first = n if first is None else first
        last = n
        if match[1].lower() != "library":
            names += [name.strip() for name in match[2].split(",")]
    if first is None or last is None:
        return None
    return f"context {span(first, last)}" + (f": {', '.join(names)}" if names else "")


def _unit_header(unit: Node, lines: list[str]) -> str:
    text = " ".join(part for part in (unit.kind, unit.name) if part)
    if unit.kind == "architecture" and unit.line < len(lines):
        match = _ARCH_OF.match(lines[unit.line])
        if match:
            text += f" of {match[1]}"
    return f"{text} {span(unit.start_line, unit.end_line)}"


def _body(node: Node, lines: list[str], indent: int) -> list[str]:
    pad = "  " * indent
    interface: dict[str, list[Node]] = {kind: [] for kind in _INTERFACE}
    groups: dict[str, list[Node]] = {}
    items: list[Node] = []
    seen_port = False
    for child in node.children:
        kind = child.kind
        if not kind or kind in _HIDDEN:
            continue
        if node.kind == "entity" and kind == "signal" and not seen_port:
            kind = "generic"  # a generic whose type vhdl_ls could not resolve
        seen_port = seen_port or kind == "port"
        if kind in interface:
            interface[kind].append(child)
        elif kind in _ITEMS:
            items.append(child)
        else:
            groups.setdefault(kind, []).append(child)

    out = []
    for kind, members in interface.items():
        if not members:
            continue
        out.append(f"{pad}{_plural(kind)}:")
        for member in members:
            text = declaration_text(lines, member)
            if kind == "port":
                text = text.split(":=")[0].strip()
            where = span(member.start_line, member.end_line)
            out.append(f"{pad}  {member.name} : {text} {where}" if text else f"{pad}  {member.name} {where}")
    for kind, members in groups.items():
        runs: list[tuple[int, int, list[str]]] = []
        for member in members:
            if runs and (runs[-1][0], runs[-1][1]) == (member.start_line, member.end_line):
                runs[-1][2].append(member.name)
            else:
                runs.append((member.start_line, member.end_line, [member.name]))
        total = sum(len(names) for _, _, names in runs)
        if total > _GROUP_NAME_CAP:
            shown = ", ".join([name for _, _, names in runs for name in names][:_GROUP_NAME_CAP])
            where = span(runs[0][0], runs[-1][1])
            out.append(f"{pad}{_plural(kind)}: {shown}, ... (+{total - _GROUP_NAME_CAP} more) {where}")
        else:
            parts = []
            for a, b, names in runs:
                first = next(m for m in members if m.name == names[0] and m.start_line == a)
                of_type = declaration_text(lines, first).split(":=")[0].strip() if kind in _TYPED else ""
                parts.append(f"{', '.join(names)}{f' : {of_type}' if of_type else ''} {span(a, b)}")
            out.append(f"{pad}{_plural(kind)}: {'; '.join(parts)}")
    overloads: dict[tuple[str, str], list[Node]] = {}
    for item in items:
        if item.kind in ("function", "procedure"):
            overloads.setdefault((item.kind, item.name.lower()), []).append(item)
    for item in items:
        where = span(item.start_line, item.end_line)
        label = " ".join(part for part in (item.kind, item.name) if part)
        if item.kind in ("function", "procedure"):
            same = overloads[(item.kind, item.name.lower())]
            if item is not same[0]:
                continue  # listed on the first overload's line
            others = ""
            if len(same) > 1:
                starts = [str(o.start_line + 1) for o in same[1 : 1 + _OVERLOAD_STARTS_SHOWN]]
                more = ", ..." if len(same) - 1 > _OVERLOAD_STARTS_SHOWN else ""
                others = f" +{len(same) - 1} overloads at {', '.join(starts)}{more}"
            out.append(f"{pad}{label}{item.detail} {where}{others}")
        elif item.kind == "instance":
            target = instance_target(item, lines)
            via = f" : {target[0]} {target[1]}" if target else ""
            out.append(f"{pad}{label}{via}{_generic_map(item, lines)} {where}")
        elif item.kind == "process":
            out.append(f"{pad}{label}{_sensitivity(item, lines)} {where}")
        else:
            out.append(f"{pad}{label} {where}")
            if item.kind in _NESTED:
                out.extend(_body(item, lines, indent + 1))
    return out


@dataclass(frozen=True)
class Region:
    """A named item of the index (process, subprogram, instance, generate,
    block, protected type), 0-based lines."""

    label: str
    name: str
    start: int
    end: int


@dataclass(frozen=True)
class FileIndex:
    """An index with what the hooks need to quote source: its named regions
    and the file's lines."""

    text: str
    regions: list[Region]
    lines: list[str]


def regions(nodes: list[Node]) -> list[Region]:
    """Every named item, at every level, in source order."""
    found = []
    for node in nodes:
        if node.kind in _ITEMS and node.name:
            found.append(Region(f"{node.kind} {node.name}", node.name, node.start_line, node.end_line))
        found.extend(regions(node.children))
    return sorted(found, key=lambda r: (r.start, -r.end))


def excerpt(
    request: str, found: list[Region], lines: list[str], max_lines: int = 150, max_regions: int = 3
) -> str:
    """Source of the regions whose names ``request`` mentions, in source order,
    within ``max_lines`` lines and ``max_regions`` regions; "" if none."""
    words = {word.lower() for word in re.findall(r"[A-Za-z]\w{2,}", request)}
    chosen: list[Region] = []
    used = 0
    for region in found:
        size = region.end - region.start + 1
        if region.name.lower() not in words or used + size > max_lines:
            continue
        chosen.append(region)
        used += size
        if len(chosen) == max_regions:
            break
    if not chosen:
        return ""
    width = len(str(max(r.end for r in chosen) + 1))
    out = ["Source of the regions your request names (read anything else by range):"]
    for region in chosen:
        out.append(f"--- {region.label} {span(region.start, region.end)}")
        out.extend(f"{n + 1:>{width}}  {lines[n]}" for n in range(region.start, min(region.end + 1, len(lines))))
    return "\n".join(out)


def build_index(title: str, nodes: list[Node], lines: list[str]) -> str:
    out = [f"{title}  {len(lines)} lines"]
    previous_end = 0
    for unit in nodes:
        context = _context(lines, previous_end, unit.start_line)
        if context:
            out.append(context)
        out.append(_unit_header(unit, lines))
        out.extend(_body(unit, lines, 1))
        previous_end = unit.end_line + 1
    return "\n".join(out)
