# vhdl-tools nav Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Claude Code what tree-sitter's `index` gives Maki, for VHDL: a `vhdl-tools nav index` skeleton with line ranges that a plugin Read hook serves in place of large full-file reads, plus exact cross-file lookups (find, def, refs, show, tree, init), all through the stock `vhdl_ls` binary.

**Architecture:** Each command finds the project's `vhdl_ls.toml`, starts `vhdl_ls --silent --no-lint [-l <stdlib dir>]` over stdio, sends a few LSP requests through a ~150-line stdlib-only client, formats the replies compactly and stops the process (~0.1 s cold). A `PreToolUse` hook on `Read` (shipped in the plugin's `hooks/hooks.json`) denies full reads of VHDL files of 150+ lines and hands Claude the index instead; it allows the read whenever the index cannot be built. Pure modules (symbol parsing, config, formatting, name/position resolution, index layout, hook decision) are unit-tested without vhdl_ls; the commands are tested end to end against a small two-library VHDL fixture.

**Tech Stack:** Python ≥3.10, stdlib (`subprocess`, `threading`, `json`, `tomllib`/`tomli`), the existing `vhdl_tools` CLI generator (`cli.py`, `registry.py`), pytest, vhdl_ls 0.88.0.

**Spec:** `docs/superpowers/specs/2026-09-28-vhdl-tools-nav-design.md`

## Global Constraints

- Code lives in `skills/shared/tools/src/vhdl_tools/nav/`; tests in `skills/shared/tools/tests/nav/`. Run every command below from `skills/shared/tools`.
- No new runtime dependencies except `tomli>=2` for Python < 3.11 (`tomllib` stand-in).
- Command names are the tool function names without the `nav_` prefix (`nav_def` → `vhdl-tools nav def`). Arguments are options (`--name`, `--pos`, `--config`, …), generated from the function signature by `cli.py`.
- Failures return `ToolError("Error: ...")` (exit 1); every error message names the next step. Zero hits for `find`/`refs` is not an error (exit 0).
- `--pos` is `FILE:LINE[:COL]`, 1-based. Output line numbers are 1-based. Output paths are relative to the directory holding `vhdl_ls.toml`.
- vhdl_ls is started with `-l <directory>` (the directory holding the standard libraries' `vhdl_ls.toml`, never the file), found via `$VHDL_LS_LIBRARIES` → vhdl_ls's own install locations (then no `-l`) → `~/.cache/speja/vhdl_libraries-*` (highest version).
- The binary is `$VHDL_LS` → `vhdl_ls` on PATH → `~/.cargo/bin/vhdl_ls`.
- One command = one vhdl_ls process, 30 s timeout over all its requests; no daemon, no cache.
- `nav index` needs no `vhdl_ls.toml` (it uses the nearest one above the file when present).
- The Read hook denies only when: tool is `Read`, no `offset` and no `limit`, suffix `.vhd`/`.vhdl`, file has ≥ `VHDL_NAV_INDEX_MIN_LINES` lines (default 150; `0` disables), and the index was built. Any failure means allow (exit 0, no output).
- Match the existing code style: `from __future__ import annotations`, module docstrings, type hints, comments only where the code does not say it.

## Review Focus

- The Read hook when the index cannot be built (vhdl_ls missing, unparsable input, crash): the Read must go through untouched, never be blocked. Tests: Task 9 `test_decide_allows_when_index_fails`, `test_main_allows_on_bad_input`.
- Running from a subdirectory of the project without `--config`, with a `--pos` path relative to that subdirectory: the config is found upward and the file relative to the cwd. Test: Task 6 `test_def_from_subdirectory_without_config`.
- A library whose globs match no files: the command still answers and says so on a leading `Warning:` line. Test: Task 6 `test_warning_for_library_without_files`.
- Different letter case in names (`LEAF`, `Lib_A.Leaf`): VHDL is case-insensitive, so lookups must be too. Tests: Task 1 `test_matches_name_is_case_insensitive`, Task 6 `test_def_name_case_insensitive`.
- vhdl_ls not installed: a one-line `Error:` naming `cargo install vhdl_ls`, exit 1, no traceback. Test: Task 6 `test_missing_vhdl_ls_is_a_clean_error`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/vhdl_tools/nav/__init__.py` | Package docstring and `NavError` |
| `src/vhdl_tools/nav/symbols.py` | Parse vhdl_ls symbol names/locations into `Hit`, `Node`, `TreeNode` records; name matching |
| `src/vhdl_tools/nav/config.py` | Find/read/check `vhdl_ls.toml`, expand library globs, write one (`init`) |
| `src/vhdl_tools/nav/lsp.py` | Locate vhdl_ls and its standard libraries; `LspSession` stdio client |
| `src/vhdl_tools/nav/formatting.py` | All text output: hits, context, references, hover, outline, tree |
| `src/vhdl_tools/nav/resolve.py` | `--name` → declaration (`find_hits`, `resolve_one`), `--pos` → position |
| `src/vhdl_tools/nav/index.py` | Per-file skeleton with line ranges (the Maki-style index); instance target parsing |
| `src/vhdl_tools/nav/tree.py` | Instantiation tree below an entity |
| `src/vhdl_tools/nav/server.py` | `ToolRegistry` and the seven `nav_*` commands |
| `src/vhdl_tools/nav/hook.py` | Claude Code `PreToolUse` hook logic for `Read` |
| `skills/shared/bin/vhdl-read-hook` (repo root path) | Hook launcher: cheap `.vhd` pre-filter, then `uv run` |
| `hooks/hooks.json` (repo root path) | Registers the hook with the plugin |
| `src/vhdl_tools/cli.py` | Register the `nav` group |
| `pyproject.toml`, `uv.lock` | `tomli` for Python 3.10 |
| `tests/nav/fixture/**` | Two-library VHDL project used by the end-to-end tests |
| `tests/nav/fake_lsp.py` | Stand-in language server for `LspSession` tests |
| `tests/nav/conftest.py` | `nav` / `nav_cli` fixtures that run the CLI |
| `tests/nav/test_*.py` | Unit and end-to-end tests |
| `../ToolPolicy.md`, `README.md` (tools), `../../../SETUP.md`, `../../../README.md`, `../../../validate.sh` | Wiring and docs |

---

### Task 1: Symbol records and name matching

**Files:**
- Create: `src/vhdl_tools/nav/__init__.py`
- Create: `src/vhdl_tools/nav/symbols.py`
- Test: `tests/nav/__init__.py` (empty), `tests/nav/test_symbols.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `NavError(Exception)` in `vhdl_tools.nav`.
  - `parse_symbol_name(text: str) -> tuple[str, str, str]` → `(kind, name, detail)`.
  - `uri_to_path(uri: str) -> Path`.
  - `@dataclass(frozen=True) Hit(kind: str, name: str, container: str, path: Path, line: int, col: int, detail: str = "")` with property `library -> str` (first segment of `container`). `line`/`col` 0-based.
  - `hit_from_symbol(symbol: dict) -> Hit` (one `workspace/symbol` entry).
  - `@dataclass Node(kind, name, detail, line, col, start_line, end_line, children: list[Node])` (0-based; `line`/`col` = the name, `start_line`/`end_line` = the whole range).
  - `nodes_from_document_symbols(items: list[dict] | None) -> list[Node]`.
  - `locations(result: object) -> list[tuple[Path, int, int]]` (Location, Location[], LocationLink[] or None → `(path, line0, col0)`).
  - `split_name(name: str) -> tuple[str | None, str]`.
  - `kind_matches(kind: str, wanted: str) -> bool`.
  - `matches_name(hit: Hit, name: str) -> bool`.
  - `prefer_declarations(hits: list[Hit]) -> list[Hit]`.
  - `@dataclass TreeNode(label: str, target: str, unit: Hit | None, note: str = "", children: list[TreeNode] = [])`.

- [ ] **Step 1: Write the failing tests**

`tests/nav/__init__.py`: empty file.

`tests/nav/test_symbols.py`:

```python
"""Parsing vhdl_ls symbol replies and matching names."""

from __future__ import annotations

from pathlib import Path

from vhdl_tools.nav.symbols import (
    Hit,
    hit_from_symbol,
    kind_matches,
    locations,
    matches_name,
    nodes_from_document_symbols,
    parse_symbol_name,
    prefer_declarations,
    split_name,
)


def _hit(kind: str, name: str, container: str, line: int = 0) -> Hit:
    return Hit(kind, name, container, Path(f"/p/{name}.vhd"), line, 7)


def test_parse_quoted_names():
    assert parse_symbol_name("entity 'fifo'") == ("entity", "fifo", "")
    assert parse_symbol_name("package body 'axi_pkg'") == ("package body", "axi_pkg", "")
    assert parse_symbol_name("record type 'axi_m2s_r_t'") == ("record type", "axi_m2s_r_t", "")
    assert parse_symbol_name("port 'clk' : in") == ("port", "clk", ": in")


def test_parse_subprograms_and_literals():
    assert parse_symbol_name("function add1[NATURAL return NATURAL]") == (
        "function",
        "add1",
        "[NATURAL return NATURAL]",
    )
    assert parse_symbol_name("procedure WRITELINE[TEXT, LINE]") == (
        "procedure",
        "WRITELINE",
        "[TEXT, LINE]",
    )
    assert parse_symbol_name("idle[return state_t]") == ("literal", "idle", "[return state_t]")
    assert parse_symbol_name("something odd") == ("", "something odd", "")
    assert parse_symbol_name("if statement") == ("", "if statement", "")


def test_parse_unlabelled_process():
    assert parse_symbol_name("process") == ("process", "", "")


def test_hit_from_symbol():
    hit = hit_from_symbol(
        {
            "name": "entity 'fifo'",
            "kind": 2,
            "containerName": "fifo",
            "location": {
                "uri": "file:///proj/modules/fifo/src/fifo%20x.vhd",
                "range": {"start": {"line": 64, "character": 7}, "end": {"line": 64, "character": 11}},
            },
        }
    )
    assert hit == Hit("entity", "fifo", "fifo", Path("/proj/modules/fifo/src/fifo x.vhd"), 64, 7)
    assert hit.library == "fifo"
    nested = Hit("type", "state_t", "lib_a.pkg_a", Path("/p"), 4, 7)
    assert nested.library == "lib_a"


def test_nodes_from_document_symbols():
    def rng(a: int, b: int) -> dict:
        return {"start": {"line": a, "character": 2}, "end": {"line": b, "character": 9}}

    nodes = nodes_from_document_symbols(
        [
            {
                "name": "architecture 'rtl'",
                "range": rng(13, 34),
                "selectionRange": rng(13, 13),
                "children": [
                    {"name": "instance 'leaf_inst'", "range": rng(16, 24), "selectionRange": rng(16, 16)},
                ],
            }
        ]
    )
    assert len(nodes) == 1
    arch = nodes[0]
    assert (arch.kind, arch.name, arch.line, arch.start_line, arch.end_line) == ("architecture", "rtl", 13, 13, 34)
    inst = arch.children[0]
    assert (inst.kind, inst.name, inst.line, inst.col, inst.end_line) == ("instance", "leaf_inst", 16, 2, 24)
    assert nodes_from_document_symbols(None) == []


def test_locations_accepts_every_shape():
    loc = {"uri": "file:///a/x.vhd", "range": {"start": {"line": 5, "character": 7}, "end": {"line": 5, "character": 9}}}
    link = {
        "targetUri": "file:///a/y.vhd",
        "targetRange": {"start": {"line": 0, "character": 0}, "end": {"line": 9, "character": 0}},
        "targetSelectionRange": {"start": {"line": 3, "character": 1}, "end": {"line": 3, "character": 4}},
    }
    assert locations(loc) == [(Path("/a/x.vhd"), 5, 7)]
    assert locations([loc, link]) == [(Path("/a/x.vhd"), 5, 7), (Path("/a/y.vhd"), 3, 1)]
    assert locations(None) == []
    assert locations([]) == []


def test_split_name():
    assert split_name("fifo") == (None, "fifo")
    assert split_name("fifo.fifo") == ("fifo", "fifo")
    assert split_name("lib_a.pkg_a.add1") == ("lib_a.pkg_a", "add1")
    assert split_name("work.mid") == (None, "mid")
    assert split_name("WORK.mid") == (None, "mid")


def test_kind_matches():
    assert kind_matches("entity", "entity")
    assert kind_matches("record type", "type")
    assert kind_matches("array type", "TYPE")
    assert not kind_matches("package body", "package")
    assert not kind_matches("subtype", "type")


def test_matches_name_exact_and_qualified():
    leaf = _hit("entity", "leaf", "lib_a")
    add1 = _hit("function", "add1", "lib_a.pkg_a")
    assert matches_name(leaf, "leaf")
    assert matches_name(leaf, "lib_a.leaf")
    assert matches_name(leaf, "work.leaf")
    assert not matches_name(leaf, "lib_b.leaf")
    assert not matches_name(leaf, "lea")
    assert matches_name(add1, "lib_a.pkg_a.add1")
    assert matches_name(add1, "lib_a.add1")


def test_matches_name_is_case_insensitive():
    leaf = _hit("entity", "leaf", "lib_a")
    assert matches_name(leaf, "LEAF")
    assert matches_name(leaf, "Lib_A.Leaf")
    upper = _hit("type", "SEVERITY_LEVEL", "std.standard")
    assert matches_name(upper, "severity_level")


def test_prefer_declarations_drops_matching_bodies_only():
    pkg = _hit("package", "pkg_a", "lib_a", 3)
    body = _hit("package body", "pkg_a", "lib_a", 8)
    other_body = _hit("package body", "pkg_b", "lib_a", 1)
    assert prefer_declarations([pkg, body]) == [pkg]
    assert prefer_declarations([body]) == [body]
    assert prefer_declarations([pkg, other_body]) == [pkg, other_body]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_symbols.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vhdl_tools.nav'`.

- [ ] **Step 3: Write the implementation**

`src/vhdl_tools/nav/__init__.py`:

```python
"""vhdl-tools nav: exact VHDL lookups through vhdl_ls, the VHDL language server."""

from __future__ import annotations


class NavError(Exception):
    """A lookup failed in a way the user can act on; the message says how."""
```

`src/vhdl_tools/nav/symbols.py`:

```python
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


def matches_name(hit: Hit, name: str) -> bool:
    """Exact, case-insensitive; a qualifier must equal the container or library."""
    prefix, ident = split_name(name)
    if hit.name.lower() != ident.lower():
        return False
    return prefix is None or prefix.lower() in (hit.container.lower(), hit.library.lower())


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/nav/test_symbols.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vhdl_tools/nav/__init__.py src/vhdl_tools/nav/symbols.py tests/nav/__init__.py tests/nav/test_symbols.py
git commit -m "feat(nav): parse vhdl_ls symbol replies and match names"
```

---

### Task 2: vhdl_ls.toml handling

**Files:**
- Create: `src/vhdl_tools/nav/config.py`
- Modify: `pyproject.toml` (dependencies), `uv.lock`
- Test: `tests/nav/test_config.py`

**Interfaces:**
- Consumes: `NavError` (Task 1).
- Produces:
  - `CONFIG_NAME = "vhdl_ls.toml"`.
  - `find_config(start: Path, explicit: str | None = None) -> Path` (absolute path of the file).
  - `read_libraries(config: Path) -> dict[str, list[str]]` (library → glob patterns, in file order).
  - `library_files(config: Path, patterns: list[str]) -> list[Path]` (sorted, globs relative to the config's directory, `**` recursive, `~`/`$VAR` expanded).
  - `empty_libraries(config: Path, libraries: dict[str, list[str]]) -> list[str]`.
  - `write_init(directory: Path, layout: str = "auto") -> tuple[Path, list[str]]` (`layout` in `auto|tsfpga|flat`; returns written path and library names).

- [ ] **Step 1: Add the `tomli` dependency for Python 3.10**

In `pyproject.toml`, add to `dependencies` (after `"matplotlib>=3.8",`):

```toml
    "tomli>=2; python_version < '3.11'",
```

Run: `uv lock`
Expected: `uv.lock` updated (tomli gains a direct-dependency marker); exit 0.

- [ ] **Step 2: Write the failing tests**

`tests/nav/test_config.py`:

```python
"""Finding, reading, checking and writing vhdl_ls.toml."""

from __future__ import annotations

from pathlib import Path

import pytest

from vhdl_tools.nav import NavError
from vhdl_tools.nav.config import (
    empty_libraries,
    find_config,
    library_files,
    read_libraries,
    write_init,
)


def _touch(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_find_config_searches_upward(tmp_path):
    config = _touch(tmp_path / "vhdl_ls.toml")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert find_config(deep) == config.resolve()


def test_find_config_explicit_file_or_directory(tmp_path):
    config = _touch(tmp_path / "proj" / "vhdl_ls.toml")
    assert find_config(tmp_path, str(config)) == config.resolve()
    assert find_config(tmp_path, str(config.parent)) == config.resolve()


def test_find_config_explicit_wrong_path(tmp_path):
    other = _touch(tmp_path / "other.toml")
    with pytest.raises(NavError, match="expected a vhdl_ls.toml"):
        find_config(tmp_path, str(other))


def test_find_config_missing_points_to_init(tmp_path):
    with pytest.raises(NavError, match="vhdl-tools nav init"):
        find_config(tmp_path)


def test_read_libraries(tmp_path):
    config = _touch(
        tmp_path / "vhdl_ls.toml",
        '[libraries]\nlib_a.files = ["a/*.vhd"]\nlib_b.files = ["b/*.vhd", "c/**/*.vhd"]\n'
        "lib_b.is_third_party = false\n",
    )
    assert read_libraries(config) == {"lib_a": ["a/*.vhd"], "lib_b": ["b/*.vhd", "c/**/*.vhd"]}


def test_read_libraries_bad_toml(tmp_path):
    config = _touch(tmp_path / "vhdl_ls.toml", "[libraries\n")
    with pytest.raises(NavError, match="cannot read"):
        read_libraries(config)


def test_library_files_relative_recursive_and_env(tmp_path, monkeypatch):
    config = _touch(tmp_path / "vhdl_ls.toml")
    a = _touch(tmp_path / "a" / "x.vhd")
    deep = _touch(tmp_path / "c" / "d" / "e" / "y.vhd")
    _touch(tmp_path / "a" / "notes.txt")
    monkeypatch.setenv("NAV_TEST_DIR", str(tmp_path / "c"))
    assert library_files(config, ["a/*.vhd"]) == [a]
    assert library_files(config, ["c/**/*.vhd"]) == [deep]
    assert library_files(config, ["$NAV_TEST_DIR/**/*.vhd"]) == [deep]
    assert library_files(config, [str(tmp_path / "a" / "*.vhd")]) == [a]


def test_empty_libraries(tmp_path):
    config = _touch(tmp_path / "vhdl_ls.toml")
    _touch(tmp_path / "a" / "x.vhd")
    libs = {"lib_a": ["a/*.vhd"], "ghost": ["nope/*.vhd"]}
    assert empty_libraries(config, libs) == ["ghost"]


def test_init_tsfpga_layout(tmp_path):
    _touch(tmp_path / "modules" / "fifo" / "src" / "fifo.vhd")
    _touch(tmp_path / "modules" / "common" / "test" / "tb.vhd")
    (tmp_path / "modules" / "empty").mkdir()
    path, names = write_init(tmp_path)
    assert path == tmp_path / "vhdl_ls.toml"
    assert names == ["common", "fifo"]
    libs = read_libraries(path)
    assert libs["fifo"] == ["modules/fifo/**/*.vhd", "modules/fifo/**/*.vhdl"]
    assert library_files(path, libs["common"]) == [tmp_path / "modules" / "common" / "test" / "tb.vhd"]


def test_init_flat_layout(tmp_path):
    _touch(tmp_path / "rtl" / "top.vhd")
    path, names = write_init(tmp_path)
    assert names == ["lib"]
    assert read_libraries(path) == {"lib": ["**/*.vhd", "**/*.vhdl"]}


def test_init_explicit_tsfpga_without_modules(tmp_path):
    _touch(tmp_path / "rtl" / "top.vhd")
    with pytest.raises(NavError, match="modules/<name>/"):
        write_init(tmp_path, "tsfpga")


def test_init_never_overwrites(tmp_path):
    _touch(tmp_path / "rtl" / "top.vhd")
    existing = _touch(tmp_path / "vhdl_ls.toml", "# mine\n")
    with pytest.raises(NavError, match="already exists"):
        write_init(tmp_path)
    assert existing.read_text() == "# mine\n"


def test_init_without_vhdl(tmp_path):
    with pytest.raises(NavError, match="no .vhd or .vhdl files"):
        write_init(tmp_path)


def test_init_missing_directory(tmp_path):
    with pytest.raises(NavError, match="no directory"):
        write_init(tmp_path / "nope")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vhdl_tools.nav.config'`.

- [ ] **Step 4: Write the implementation**

`src/vhdl_tools/nav/config.py`:

```python
"""The project's vhdl_ls.toml: find it, read its libraries, check them, write one.

nav never edits an existing vhdl_ls.toml. Globs resolve relative to the file's
directory with ``**`` recursive, as vhdl_lang does.
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from vhdl_tools.nav import NavError

CONFIG_NAME = "vhdl_ls.toml"

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def find_config(start: Path, explicit: str | None = None) -> Path:
    """``--config`` (a vhdl_ls.toml or a directory holding one), else the
    nearest vhdl_ls.toml in ``start`` or a parent."""
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_dir():
            path = path / CONFIG_NAME
        if path.name != CONFIG_NAME or not path.is_file():
            raise NavError(
                f"--config {explicit}: expected a {CONFIG_NAME} file or a directory holding one"
            )
        return path.resolve()
    start = start.resolve()
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise NavError(
        f"No {CONFIG_NAME} in {start} or any parent directory. "
        "Create one: vhdl-tools nav init"
    )


def read_libraries(config: Path) -> dict[str, list[str]]:
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise NavError(f"cannot read {config}: {exc}") from exc
    libraries = data.get("libraries", {})
    return {
        name: [str(pattern) for pattern in spec.get("files", [])]
        for name, spec in libraries.items()
        if isinstance(spec, dict)
    }


def library_files(config: Path, patterns: list[str]) -> list[Path]:
    files: set[Path] = set()
    for pattern in patterns:
        pattern = os.path.expandvars(os.path.expanduser(pattern))
        if not os.path.isabs(pattern):
            pattern = str(config.parent / pattern)
        files.update(Path(p) for p in glob.glob(pattern, recursive=True) if os.path.isfile(p))
    return sorted(files)


def empty_libraries(config: Path, libraries: dict[str, list[str]]) -> list[str]:
    return [name for name, patterns in libraries.items() if not library_files(config, patterns)]


def _has_vhdl(directory: Path) -> bool:
    return any(directory.rglob("*.vhd")) or any(directory.rglob("*.vhdl"))


def _key(name: str) -> str:
    return name if _BARE_KEY.fullmatch(name) else json.dumps(name)


def write_init(directory: Path, layout: str = "auto") -> tuple[Path, list[str]]:
    """Write ``directory/vhdl_ls.toml`` listing the project's own libraries."""
    if not directory.is_dir():
        raise NavError(f"no directory {directory}")
    target = directory / CONFIG_NAME
    if target.exists():
        raise NavError(f"{target} already exists; nav init never overwrites it")
    modules_dir = directory / "modules"
    modules = (
        sorted(d for d in modules_dir.iterdir() if d.is_dir() and _has_vhdl(d))
        if modules_dir.is_dir()
        else []
    )
    if layout == "auto":
        layout = "tsfpga" if modules else "flat"
    if layout == "tsfpga":
        if not modules:
            raise NavError(
                f"--layout tsfpga: no modules/<name>/ directories with VHDL files in {directory}"
            )
        libraries = {
            m.name: [f"modules/{m.name}/**/*.vhd", f"modules/{m.name}/**/*.vhdl"] for m in modules
        }
    else:
        if not _has_vhdl(directory):
            raise NavError(f"no .vhd or .vhdl files under {directory}")
        libraries = {"lib": ["**/*.vhd", "**/*.vhdl"]}
    lines = [
        "# Written by vhdl-tools nav init. The standard libraries (std, ieee) come",
        "# from vhdl_ls's library directory; add third-party libraries by hand.",
        "[libraries]",
    ]
    for name, patterns in libraries.items():
        lines.append(f"{_key(name)}.files = [{', '.join(json.dumps(p) for p in patterns)}]")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target, list(libraries)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/nav/test_config.py -v`
Expected: 14 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/vhdl_tools/nav/config.py tests/nav/test_config.py
git commit -m "feat(nav): find, check and write vhdl_ls.toml"
```

---

### Task 3: vhdl_ls discovery and the LSP session

**Files:**
- Create: `src/vhdl_tools/nav/lsp.py`
- Create: `tests/nav/fake_lsp.py`
- Test: `tests/nav/test_lsp.py`

**Interfaces:**
- Consumes: `NavError` (Task 1).
- Produces:
  - `DEFAULT_TIMEOUT = 30.0`, `INSTALLED_LIBRARY_DIRS`, `STD_LIBRARIES_HELP`.
  - `find_vhdl_ls() -> Path`.
  - `find_std_libraries(vhdl_ls: Path) -> Path | None`.
  - `vhdl_ls_command(vhdl_ls: Path, libraries: Path | None) -> list[str]`.
  - `class LspSession(root: Path, command: list[str], timeout: float = DEFAULT_TIMEOUT)`: context manager; `request(method: str, params: Any) -> Any`; `notify(method: str, params: Any) -> None`; `open(path: Path) -> None` (didOpen once per file); `close() -> None`. Raises `NavError` on timeout, crash, or an LSP error reply.

- [ ] **Step 1: Write the stand-in server**

`tests/nav/fake_lsp.py`:

```python
"""Stand-in language server for LspSession tests.

Mode (argv[1]): echo | crash | hang | server_request | error. Every mode
answers ``initialize``; other requests get an echo of their method, params and
the notifications seen so far, unless the mode says otherwise.
"""

from __future__ import annotations

import json
import sys
import time


def read() -> dict:
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            sys.exit(0)
        if line in (b"\r\n", b"\n"):
            break
        name, _, value = line.decode().partition(":")
        if name.strip().lower() == "content-length":
            length = int(value)
    return json.loads(sys.stdin.buffer.read(length))


def send(message: dict) -> None:
    body = json.dumps(message).encode()
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    sys.stdout.buffer.flush()


mode = sys.argv[1]
notifications: list[str] = []
while True:
    message = read()
    if "id" not in message:
        notifications.append(message["method"])
        continue
    if message["method"] == "initialize":
        send({"jsonrpc": "2.0", "id": message["id"], "result": {"capabilities": {}}})
        continue
    if mode == "crash":
        sys.stderr.write("thread 'main' panicked at config.rs: boom\n")
        sys.stderr.flush()
        sys.exit(101)
    if mode == "hang":
        time.sleep(60)
    if mode == "error":
        send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "no such method"}})
        continue
    if mode == "server_request":
        send({"jsonrpc": "2.0", "id": 99, "method": "workspace/configuration", "params": {}})
        reply = read()
        if reply.get("id") != 99 or reply.get("result", "missing") is not None:
            sys.exit(3)
        send({"jsonrpc": "2.0", "method": "window/logMessage", "params": {"type": 3, "message": "hi"}})
    send(
        {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {"method": message["method"], "params": message["params"], "notifications": notifications},
        }
    )
```

- [ ] **Step 2: Write the failing tests**

`tests/nav/test_lsp.py`:

```python
"""LspSession against a stand-in server, and finding vhdl_ls and its libraries."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from vhdl_tools.nav import NavError
from vhdl_tools.nav.lsp import (
    STD_LIBRARIES_HELP,
    LspSession,
    find_std_libraries,
    find_vhdl_ls,
    vhdl_ls_command,
)

FAKE = Path(__file__).parent / "fake_lsp.py"


def _session(tmp_path: Path, mode: str, timeout: float = 10.0) -> LspSession:
    return LspSession(tmp_path, [sys.executable, str(FAKE), mode], timeout=timeout)


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def _libraries(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "vhdl_ls.toml").write_text("[libraries]\n")
    return directory


def test_request_round_trip(tmp_path):
    with _session(tmp_path, "echo") as session:
        result = session.request("workspace/symbol", {"query": "fifo"})
    assert result["method"] == "workspace/symbol"
    assert result["params"] == {"query": "fifo"}
    assert result["notifications"] == ["initialized"]


def test_open_sends_did_open_once(tmp_path):
    source = tmp_path / "a.vhd"
    source.write_text("entity a is end entity;\n")
    with _session(tmp_path, "echo") as session:
        session.open(source)
        session.open(source)
        result = session.request("x", {})
    assert result["notifications"].count("textDocument/didOpen") == 1


def test_server_requests_are_answered(tmp_path):
    with _session(tmp_path, "server_request") as session:
        result = session.request("workspace/symbol", {"query": ""})
    assert result["method"] == "workspace/symbol"


def test_error_reply(tmp_path):
    with _session(tmp_path, "error") as session, pytest.raises(NavError, match="no such method"):
        session.request("bogus", {})


def test_crash_reports_stderr_tail(tmp_path):
    with _session(tmp_path, "crash") as session, pytest.raises(NavError) as exc:
        session.request("workspace/symbol", {"query": ""})
    message = str(exc.value)
    assert "exited with code 101" in message
    assert "boom" in message


def test_timeout(tmp_path):
    start = time.monotonic()
    with _session(tmp_path, "hang", timeout=1.0) as session, pytest.raises(NavError, match="within 1 s"):
        session.request("workspace/symbol", {"query": ""})
    assert time.monotonic() - start < 10


def test_start_failure(tmp_path):
    with pytest.raises(NavError, match="cannot start"):
        LspSession(tmp_path, [str(tmp_path / "missing")])


def test_command():
    assert vhdl_ls_command(Path("/x/vhdl_ls"), None) == ["/x/vhdl_ls", "--silent", "--no-lint"]
    assert vhdl_ls_command(Path("/x/vhdl_ls"), Path("/libs")) == [
        "/x/vhdl_ls",
        "--silent",
        "--no-lint",
        "-l",
        "/libs",
    ]


def test_find_vhdl_ls_from_env(tmp_path, monkeypatch):
    exe = _executable(tmp_path / "bin" / "vhdl_ls")
    monkeypatch.setenv("VHDL_LS", str(exe))
    assert find_vhdl_ls() == exe


def test_find_vhdl_ls_bad_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VHDL_LS", str(tmp_path / "nope"))
    with pytest.raises(NavError, match="not an executable"):
        find_vhdl_ls()


def test_find_vhdl_ls_cargo_bin(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    exe = _executable(tmp_path / ".cargo" / "bin" / "vhdl_ls")
    assert find_vhdl_ls() == exe


def test_find_vhdl_ls_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(NavError, match="cargo install vhdl_ls"):
        find_vhdl_ls()


def test_std_libraries_env_first(tmp_path, monkeypatch):
    libs = _libraries(tmp_path / "libs")
    monkeypatch.setenv("VHDL_LS_LIBRARIES", str(libs))
    assert find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls")) == libs


def test_std_libraries_env_without_toml(tmp_path, monkeypatch):
    (tmp_path / "libs").mkdir()
    monkeypatch.setenv("VHDL_LS_LIBRARIES", str(tmp_path / "libs"))
    with pytest.raises(NavError, match="holds no vhdl_ls.toml"):
        find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls"))


def test_std_libraries_next_to_binary_need_no_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS_LIBRARIES", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _libraries(tmp_path / "vhdl_libraries")
    assert find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls")) is None


def test_std_libraries_speja_cache_highest_version(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS_LIBRARIES", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    cache = tmp_path / "home" / ".cache" / "speja"
    _libraries(cache / "vhdl_libraries-0.9.0")
    newest = _libraries(cache / "vhdl_libraries-0.14.6")
    assert find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls")) == newest


@pytest.mark.skipif(
    any(Path(p, "vhdl_ls.toml").is_file() for p in ("/usr/lib/rust_hdl/vhdl_libraries", "/usr/local/lib/rust_hdl/vhdl_libraries")),
    reason="this machine has system-wide vhdl_ls libraries",
)
def test_std_libraries_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS_LIBRARIES", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    with pytest.raises(NavError) as exc:
        find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls"))
    assert str(exc.value) == STD_LIBRARIES_HELP
    assert "VHDL_LS_LIBRARIES" in STD_LIBRARIES_HELP and "rust_hdl" in STD_LIBRARIES_HELP
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_lsp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vhdl_tools.nav.lsp'`.

- [ ] **Step 4: Write the implementation**

`src/vhdl_tools/nav/lsp.py`:

```python
"""A minimal LSP client for vhdl_ls over stdio.

Each nav command starts vhdl_ls, asks its questions and stops it: a cold start
including analysis takes ~0.1 s even on ~900-file projects, so there is no
daemon and no cache.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from vhdl_tools.nav import NavError

DEFAULT_TIMEOUT = 30.0

#: Where vhdl_ls looks for its standard libraries by itself (vhdl_lang's
#: config.rs); relative entries are relative to the binary's directory.
INSTALLED_LIBRARY_DIRS = (
    "../vhdl_libraries",
    "../../vhdl_libraries",
    "/usr/lib/rust_hdl/vhdl_libraries",
    "/usr/local/lib/rust_hdl/vhdl_libraries",
    "../share/vhdl_libraries",
)

STD_LIBRARIES_HELP = (
    "No VHDL standard libraries (std, ieee) for vhdl_ls found. Searched "
    "$VHDL_LS_LIBRARIES, vhdl_ls's own install locations and "
    "~/.cache/speja/vhdl_libraries-*. Get them with:\n"
    "  git clone --depth 1 https://github.com/VHDL-LS/rust_hdl ~/.local/share/rust_hdl\n"
    "  export VHDL_LS_LIBRARIES=~/.local/share/rust_hdl/vhdl_libraries"
)


def find_vhdl_ls() -> Path:
    """``$VHDL_LS``, else ``vhdl_ls`` on PATH, else ``~/.cargo/bin/vhdl_ls``."""
    env = os.environ.get("VHDL_LS")
    if env:
        path = Path(env).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise NavError(f"$VHDL_LS={env} is not an executable file")
    for candidate in (shutil.which("vhdl_ls"), Path.home() / ".cargo" / "bin" / "vhdl_ls"):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return Path(candidate)
    raise NavError(
        "vhdl_ls not found (checked $VHDL_LS, PATH, ~/.cargo/bin). Install: cargo install vhdl_ls"
    )


def _version_key(path: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", path.name))


def find_std_libraries(vhdl_ls: Path) -> Path | None:
    """The directory to pass as ``-l`` (it holds the libraries' vhdl_ls.toml;
    vhdl_ls appends the file name itself), or None when vhdl_ls finds its own."""
    env = os.environ.get("VHDL_LS_LIBRARIES")
    if env:
        directory = Path(env).expanduser()
        if (directory / "vhdl_ls.toml").is_file():
            return directory
        raise NavError(f"$VHDL_LS_LIBRARIES={env} holds no vhdl_ls.toml")
    exe_dir = vhdl_ls.resolve().parent
    for location in INSTALLED_LIBRARY_DIRS:
        if (exe_dir / location / "vhdl_ls.toml").is_file():
            return None
    cache = Path.home() / ".cache" / "speja"
    for directory in sorted(cache.glob("vhdl_libraries-*"), key=_version_key, reverse=True):
        if (directory / "vhdl_ls.toml").is_file():
            return directory
    raise NavError(STD_LIBRARIES_HELP)


def vhdl_ls_command(vhdl_ls: Path, libraries: Path | None) -> list[str]:
    command = [str(vhdl_ls), "--silent", "--no-lint"]
    if libraries is not None:
        command += ["-l", str(libraries)]
    return command


class LspSession:
    """One language-server process for one command; ``timeout`` covers all of
    its requests together."""

    def __init__(self, root: Path, command: list[str], timeout: float = DEFAULT_TIMEOUT) -> None:
        self.root = root
        self._timeout = timeout
        self._deadline = time.monotonic() + timeout
        self._stderr = tempfile.TemporaryFile()
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
            )
        except OSError as exc:
            self._stderr.close()
            raise NavError(f"cannot start {command[0]}: {exc}") from exc
        self._inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
        threading.Thread(target=self._read_loop, daemon=True).start()
        self._next_id = 0
        self._opened: set[Path] = set()
        try:
            self.request(
                "initialize",
                {
                    "processId": os.getpid(),
                    "rootUri": root.as_uri(),
                    "capabilities": {
                        "textDocument": {"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}}
                    },
                },
            )
            self.notify("initialized", {})
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> LspSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _read_loop(self) -> None:
        stream = self._proc.stdout
        assert stream is not None
        while True:
            length = None
            while True:
                line = stream.readline()
                if not line:
                    self._inbox.put(None)
                    return
                if line in (b"\r\n", b"\n"):
                    break
                name, _, value = line.decode("ascii", "replace").partition(":")
                if name.strip().lower() == "content-length":
                    length = int(value)
            if length is not None:
                self._inbox.put(json.loads(stream.read(length)))

    def _send(self, message: dict[str, Any]) -> None:
        body = json.dumps(message).encode()
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self._proc.stdin.flush()
        except OSError as exc:  # BrokenPipeError: the server is gone
            raise self._crashed(message.get("method", "a reply")) from exc

    def notify(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: Any) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise NavError(f"vhdl_ls did not answer {method} within {self._timeout:g} s")
            try:
                message = self._inbox.get(timeout=remaining)
            except queue.Empty:
                continue
            if message is None:
                self._inbox.put(None)  # later calls see the exit too
                raise self._crashed(method)
            if "method" in message:  # a server request or notification
                if "id" in message:
                    self._send({"jsonrpc": "2.0", "id": message["id"], "result": None})
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise NavError(f"vhdl_ls {method} failed: {error.get('message', error)}")
            return message.get("result")

    def open(self, path: Path) -> None:
        """Tell the server about a file (once) before file-scoped requests."""
        if path in self._opened:
            return
        self._opened.add(path)
        self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": path.as_uri(),
                    "languageId": "vhdl",
                    "version": 1,
                    "text": path.read_text(encoding="utf-8", errors="replace"),
                }
            },
        )

    def _crashed(self, method: str) -> NavError:
        try:
            code: int | None = self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            code = None
        self._stderr.seek(0)
        tail = self._stderr.read().decode("utf-8", "replace").splitlines()[-20:]
        status = f"exited with code {code}" if code is not None else "closed its output"
        text = "\n".join(f"  {line}" for line in tail) or "  (nothing on stderr)"
        return NavError(f"vhdl_ls {status} during {method}. Last stderr lines:\n{text}")

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                self.notify("exit", None)
            except NavError:
                pass
            try:
                self._proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        self._stderr.close()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/nav/test_lsp.py -v`
Expected: 17 passed (`test_std_libraries_missing` may be skipped on machines with system-wide libraries).

- [ ] **Step 6: Commit**

```bash
git add src/vhdl_tools/nav/lsp.py tests/nav/fake_lsp.py tests/nav/test_lsp.py
git commit -m "feat(nav): stdio LSP session and vhdl_ls/std library discovery"
```

---

### Task 4: Output formatting

**Files:**
- Create: `src/vhdl_tools/nav/formatting.py`
- Test: `tests/nav/test_formatting.py`

**Interfaces:**
- Consumes: `Hit`, `Node`, `TreeNode` (Task 1).
- Produces:
  - `CAP_NOTE: str`.
  - `count(n: int, word: str, plural: str | None = None) -> str` (`"1 hit"`, `"2 files"`, `"3 libraries"`).
  - `rel(path: Path, root: Path) -> str`.
  - `describe(hit: Hit) -> str` (`"entity leaf"`, `"port clk : in"`, `"function add1[NATURAL return NATURAL]"`).
  - `header(hit: Hit, root: Path) -> str` (`"entity leaf  [lib_a]  lib_a/leaf.vhd:6"`).
  - `format_hits(hits: list[Hit], root: Path, truncated: bool = False) -> str`.
  - `source_lines(path: Path, cache: dict[Path, list[str]]) -> list[str]`.
  - `format_context(path: Path, line: int, context: int, title: str) -> str`.
  - `format_refs(refs: list[tuple[Path, int, int]], root: Path) -> str`.
  - `hover_text(result: object) -> str`.
  - `format_outline(nodes: list[Node], indent: int = 0) -> list[str]` (skips `parameter` and `literal` nodes).
  - `format_tree(node: TreeNode, root: Path, indent: int = 0) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

`tests/nav/test_formatting.py`:

```python
"""Compact text output."""

from __future__ import annotations

from pathlib import Path

from vhdl_tools.nav.formatting import (
    CAP_NOTE,
    count,
    describe,
    format_context,
    format_hits,
    format_outline,
    format_refs,
    format_tree,
    header,
    hover_text,
    rel,
)
from vhdl_tools.nav.symbols import Hit, Node, TreeNode

ROOT = Path("/proj")


def test_count():
    assert count(1, "hit") == "1 hit"
    assert count(0, "hit") == "0 hits"
    assert count(3, "library", "libraries") == "3 libraries"


def test_rel():
    assert rel(Path("/proj/a/b.vhd"), ROOT) == "a/b.vhd"
    assert rel(Path("/elsewhere/c.vhd"), ROOT) == "/elsewhere/c.vhd"


def test_describe_and_header():
    leaf = Hit("entity", "leaf", "lib_a", Path("/proj/lib_a/leaf.vhd"), 5, 7)
    port = Hit("port", "clk", "lib_a.leaf", Path("/proj/lib_a/leaf.vhd"), 10, 4, ": in")
    add1 = Hit("function", "add1", "lib_a.pkg_a", Path("/proj/lib_a/pkg_a.vhd"), 5, 11, "[NATURAL return NATURAL]")
    assert describe(leaf) == "entity leaf"
    assert describe(port) == "port clk : in"
    assert describe(add1) == "function add1[NATURAL return NATURAL]"
    assert header(leaf, ROOT) == "entity leaf  [lib_a]  lib_a/leaf.vhd:6"


def test_format_hits_aligned():
    hits = [
        Hit("entity", "dup", "lib_a", Path("/proj/lib_a/dup.vhd"), 0, 7),
        Hit("package body", "dup", "lib_b", Path("/proj/lib_b/longer/dup.vhd"), 8, 13),
    ]
    assert format_hits(hits, ROOT) == (
        "entity dup        [lib_a]  lib_a/dup.vhd:1\n"
        "package body dup  [lib_b]  lib_b/longer/dup.vhd:9\n"
        "2 hits"
    )


def test_format_hits_truncated():
    assert format_hits([], ROOT, truncated=True) == f"0 hits\n{CAP_NOTE}"


def test_format_context(tmp_path):
    source = tmp_path / "leaf.vhd"
    source.write_text("\n".join(f"line {n}" for n in range(1, 21)) + "\n")
    assert format_context(source, 9, 2, "TITLE") == "TITLE\n10  line 10\n11  line 11\n12  line 12"
    assert format_context(source, 19, 5, "T") == "T\n20  line 20"


def test_format_refs_grouped(tmp_path):
    a = tmp_path / "a.vhd"
    b = tmp_path / "b.vhd"
    a.write_text("x\n  u1 : entity lib.leaf\n")
    b.write_text("  u2 : entity work.leaf\n")
    text = format_refs([(b, 0, 16), (a, 1, 15)], tmp_path)
    assert text == (
        "a.vhd\n"
        "      2:16  u1 : entity lib.leaf\n"
        "b.vhd\n"
        "      1:17  u2 : entity work.leaf\n"
        "2 references in 2 files"
    )


def test_hover_text_shapes():
    marked = {"contents": {"language": "vhdl", "value": "entity leaf is\nend entity;"}}
    markup = {"contents": {"kind": "markdown", "value": "```vhdl\nfunction f\n```"}}
    listed = {"contents": ["a", {"language": "vhdl", "value": "b"}]}
    assert hover_text(marked) == "entity leaf is\nend entity;"
    assert hover_text(markup) == "function f"
    assert hover_text(listed) == "a\nb"
    assert hover_text(None) == ""


def test_format_outline_skips_parameters_and_literals():
    nodes = [
        Node("package", "pkg_a", "", 3, 8, 3, 6, [
            Node("type", "state_t", "", 4, 7, 4, 4, [Node("literal", "idle", "[return state_t]", 4, 18, 4, 4)]),
            Node("function", "add1", "[NATURAL return NATURAL]", 5, 11, 5, 5, [Node("parameter", "x", "", 5, 16, 5, 5)]),
            Node("port", "clk", ": in", 7, 4, 7, 7),
        ])
    ]
    assert format_outline(nodes) == [
        "package pkg_a  L4",
        "  type state_t  L5",
        "  function add1[NATURAL return NATURAL]  L6",
        "  port clk : in  L8",
    ]


def test_format_tree():
    top = Hit("entity", "top", "lib_b", Path("/proj/lib_b/top.vhd"), 5, 7)
    leaf = Hit("entity", "leaf", "lib_a", Path("/proj/lib_a/leaf.vhd"), 5, 7)
    tree = TreeNode("", "top", top, children=[
        TreeNode("u_leaf", "lib_a.leaf", leaf),
        TreeNode("u_comp", "leaf", leaf, "component"),
        TreeNode("u_bad", "work.gone", None, "unresolved"),
    ])
    assert format_tree(tree, ROOT) == [
        "entity top  [lib_b]  lib_b/top.vhd:6",
        "  u_leaf : entity leaf  [lib_a]  lib_a/leaf.vhd:6",
        "  u_comp : entity leaf  [lib_a]  lib_a/leaf.vhd:6  (component)",
        "  u_bad : work.gone  (unresolved)",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_formatting.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vhdl_tools.nav.formatting'`.

- [ ] **Step 3: Write the implementation**

`src/vhdl_tools/nav/formatting.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/nav/test_formatting.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vhdl_tools/nav/formatting.py tests/nav/test_formatting.py
git commit -m "feat(nav): compact text formatting"
```

---

### Task 5: Resolving --name and --pos

**Files:**
- Create: `src/vhdl_tools/nav/resolve.py`
- Test: `tests/nav/test_resolve.py`

**Interfaces:**
- Consumes: Task 1 (`Hit`, `hit_from_symbol`, `kind_matches`, `matches_name`, `prefer_declarations`, `split_name`), Task 4 (`count`, `format_hits`), `NavError`.
- Produces:
  - `WORKSPACE_SYMBOL_CAP = 200`.
  - `class Requester(Protocol)`: `request(method: str, params: Any) -> Any`.
  - `@dataclass Found(hits: list[Hit], truncated: bool)`.
  - `@dataclass(frozen=True) Position(path: Path, line: int, col: int)` (0-based).
  - `find_hits(session: Requester, name: str, kind: str | None = None, substring: bool = False, libraries: Iterable[str] = ()) -> Found` (sorted by path, line).
  - `not_found_message(name: str, libraries: list[str], kind: str | None = None) -> str`.
  - `resolve_one(session: Requester, name: str, root: Path, libraries: list[str], kind: str | None = None) -> Hit`.
  - `hit_at(session: Requester, path: Path, line: int, name: str) -> Hit` (falls back to `Hit("", name, "", path, line, 0)`).
  - `existing_file(file: str, root: Path) -> Path` (cwd first, then `root`; resolved).
  - `parse_pos(pos: str, root: Path) -> Position`.
  - `identifier_at(path: Path, line: int, col: int) -> str`.
  - `position_params(position: Position) -> dict`.

- [ ] **Step 1: Write the failing tests**

`tests/nav/test_resolve.py`:

```python
"""--name and --pos resolution, with a stand-in for the LSP session."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from vhdl_tools.nav import NavError
from vhdl_tools.nav.resolve import (
    Position,
    existing_file,
    find_hits,
    hit_at,
    identifier_at,
    not_found_message,
    parse_pos,
    position_params,
    resolve_one,
)
from vhdl_tools.nav.symbols import Hit

ROOT = Path("/proj")


def sym(name: str, container: str, file: str, line: int, col: int = 7) -> dict:
    return {
        "name": name,
        "kind": 2,
        "containerName": container,
        "location": {
            "uri": f"file:///proj/{file}",
            "range": {"start": {"line": line, "character": col}, "end": {"line": line, "character": col + 3}},
        },
    }


class FakeSession:
    def __init__(self, symbols: list[dict]) -> None:
        self.symbols = symbols
        self.queries: list[str] = []

    def request(self, method: str, params: Any) -> Any:
        assert method == "workspace/symbol"
        self.queries.append(params["query"])
        return self.symbols


SYMBOLS = [
    sym("entity 'leaf'", "lib_a", "lib_a/leaf.vhd", 5),
    sym("constant 'VitalDefaultPortFlag'", "ieee.Vital_Memory", "ieee/memory_p.vhdl", 318),
    sym("entity 'dup'", "lib_b", "lib_b/dup.vhd", 0),
    sym("entity 'dup'", "lib_a", "lib_a/dup.vhd", 0),
    sym("package 'pkg_a'", "lib_a", "lib_a/pkg_a.vhd", 3, 8),
    sym("package body 'pkg_a'", "lib_a", "lib_a/pkg_a.vhd", 8, 13),
    sym("instance 'leaf_inst'", "lib_b.top", "lib_b/top.vhd", 16, 2),
]


def test_find_hits_is_exact_and_sends_the_bare_identifier():
    session = FakeSession(SYMBOLS)
    found = find_hits(session, "lib_a.leaf")
    assert session.queries == ["leaf"]
    assert [(h.kind, h.name, h.library) for h in found.hits] == [("entity", "leaf", "lib_a")]
    assert not found.truncated


def test_find_hits_sorted_and_kind_filter():
    found = find_hits(FakeSession(SYMBOLS), "dup")
    assert [h.library for h in found.hits] == ["lib_a", "lib_b"]
    assert find_hits(FakeSession(SYMBOLS), "pkg_a", kind="package").hits[0].kind == "package"


def test_find_hits_substring_stays_in_own_libraries():
    found = find_hits(FakeSession(SYMBOLS), "lea", substring=True, libraries=["lib_a", "lib_b"])
    assert sorted(h.name for h in found.hits) == ["leaf", "leaf_inst"]
    assert all(h.library != "ieee" for h in found.hits)


def test_find_hits_reports_the_cap():
    many = [sym(f"signal 's{i}'", "lib_a.x", "lib_a/x.vhd", i) for i in range(200)]
    assert find_hits(FakeSession(many), "s1").truncated


def test_resolve_one_prefers_package_over_body():
    hit = resolve_one(FakeSession(SYMBOLS), "pkg_a", ROOT, ["lib_a"])
    assert (hit.kind, hit.line) == ("package", 3)


def test_resolve_one_ambiguous_lists_candidates():
    with pytest.raises(NavError) as exc:
        resolve_one(FakeSession(SYMBOLS), "dup", ROOT, ["lib_a", "lib_b"])
    message = str(exc.value)
    assert "ambiguous" in message
    assert "lib_a/dup.vhd:1" in message and "lib_b/dup.vhd:1" in message


def test_resolve_one_not_found_names_libraries():
    with pytest.raises(NavError) as exc:
        resolve_one(FakeSession(SYMBOLS), "nothing", ROOT, ["lib_a", "lib_b"])
    assert str(exc.value) == not_found_message("nothing", ["lib_a", "lib_b"])
    assert "2 libraries: lib_a, lib_b" in str(exc.value)


def test_not_found_message_shortens_long_library_lists():
    libs = [f"l{i}" for i in range(12)]
    message = not_found_message("x", libs, kind="entity")
    assert message.startswith("No entity named x ")
    assert "12 libraries: l0, l1, l2, l3, l4, l5, l6, l7, l8, l9, ..." in message


def test_hit_at_matches_location_or_falls_back():
    session = FakeSession(SYMBOLS)
    hit = hit_at(session, Path("/proj/lib_b/dup.vhd"), 0, "dup")
    assert hit.library == "lib_b"
    fallback = hit_at(session, Path("/proj/other.vhd"), 4, "dup")
    assert fallback == Hit("", "dup", "", Path("/proj/other.vhd"), 4, 0)


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "lib_b").mkdir()
    (tmp_path / "lib_b" / "top.vhd").write_text(
        "entity top is\n"
        "  leaf_inst : entity lib_a.leaf\n"
        "  -- just a comment\n"
    )
    monkeypatch.chdir(tmp_path / "lib_b")
    return tmp_path


def test_parse_pos_with_column(project):
    pos = parse_pos("top.vhd:2:28", project)
    assert pos == Position((project / "lib_b" / "top.vhd").resolve(), 1, 27)


def test_parse_pos_relative_to_root_when_not_in_cwd(project):
    pos = parse_pos("lib_b/top.vhd:1", project)
    assert (pos.line, pos.col) == (0, 7)  # 'top', skipping the keyword 'entity'


def test_parse_pos_without_column_takes_first_identifier(project):
    assert parse_pos("top.vhd:2", project).col == 2  # the label 'leaf_inst'


def test_parse_pos_not_on_identifier_shows_caret(project):
    with pytest.raises(NavError) as exc:
        parse_pos("top.vhd:2:12", project)
    assert "not on an identifier" in str(exc.value)
    assert str(exc.value).endswith("\n  " + " " * 11 + "^")


def test_parse_pos_errors(project):
    with pytest.raises(NavError, match="expected FILE:LINE"):
        parse_pos("top.vhd", project)
    with pytest.raises(NavError, match="has 3 lines"):
        parse_pos("top.vhd:9", project)
    with pytest.raises(NavError, match="no identifier"):
        parse_pos("top.vhd:3", project)
    with pytest.raises(NavError, match="no file"):
        parse_pos("gone.vhd:1", project)


def test_existing_file_and_identifier_at(project):
    path = existing_file("lib_b/top.vhd", project)
    assert path == (project / "lib_b" / "top.vhd").resolve()
    assert identifier_at(path, 1, 28) == "leaf"
    assert identifier_at(path, 1, 11) == ""


def test_position_params():
    params = position_params(Position(Path("/proj/a.vhd"), 3, 4))
    assert params == {"textDocument": {"uri": "file:///proj/a.vhd"}, "position": {"line": 3, "character": 4}}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_resolve.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vhdl_tools.nav.resolve'`.

- [ ] **Step 3: Write the implementation**

`src/vhdl_tools/nav/resolve.py`:

```python
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
    """A place in a file, 0-based like LSP."""

    path: Path
    line: int
    col: int


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
            and (prefix is None or prefix.lower() in (h.container.lower(), h.library.lower()))
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
            return Position(path, line, token.start())
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/nav/test_resolve.py -v`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vhdl_tools/nav/resolve.py tests/nav/test_resolve.py
git commit -m "feat(nav): resolve --name and --pos"
```

---

### Task 6: Fixture project, `find`/`def`/`refs`/`show` commands and CLI registration

**Files:**
- Create: `tests/nav/fixture/vhdl_ls.toml`, `tests/nav/fixture/lib_a/{pkg_a,leaf,dup}.vhd`, `tests/nav/fixture/lib_b/{dup,mid,top,comp_user}.vhd`
- Create: `tests/nav/conftest.py`
- Create: `src/vhdl_tools/nav/server.py`
- Modify: `src/vhdl_tools/cli.py` (`GROUPS`, parser description)
- Test: `tests/nav/test_e2e.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces (used by Tasks 7–8):
  - `tools: ToolRegistry` (`error_prefixes=("Error:",)`).
  - `@dataclass Project(config: Path, root: Path, libraries: dict[str, list[str]])` with property `library_names -> list[str]`.
  - `_run(config: str | None, body: Callable[[Project, LspSession], str]) -> str` (finds the config, prefixes the empty-library warning, opens a session, turns `NavError` into `ToolError("Error: ...")`).
  - `_document_symbols(session: LspSession, path: Path) -> list[Node]`.
  - Commands `nav_find`, `nav_def`, `nav_refs`, `nav_show`.

- [ ] **Step 1: Create the fixture project**

These files were checked with vhdl_ls 0.88.0: no diagnostics, and the line numbers used in the tests below are the real ones.

`tests/nav/fixture/vhdl_ls.toml`:

```toml
[libraries]
lib_a.files = ["lib_a/*.vhd"]
lib_b.files = ["lib_b/*.vhd"]
```

`tests/nav/fixture/lib_a/pkg_a.vhd`:

```vhdl
library ieee;
use ieee.std_logic_1164.all;

package pkg_a is
  type state_t is (idle, busy);
  function add1(x : natural) return natural;
end package;

package body pkg_a is
  function add1(x : natural) return natural is
  begin
    return x + 1;
  end function;
end package body;
```

`tests/nav/fixture/lib_a/leaf.vhd`:

```vhdl
library ieee;
use ieee.std_logic_1164.all;

use work.pkg_a.all;

entity leaf is
  generic (
    width : positive := 8
  );
  port (
    clk : in std_ulogic;
    d : in std_ulogic_vector(width - 1 downto 0);
    q : out std_ulogic_vector(width - 1 downto 0)
  );
end entity;

architecture rtl of leaf is
  signal state : state_t := idle;
begin
  process (clk)
  begin
    if rising_edge(clk) then
      q <= d;
      state <= busy;
    end if;
  end process;
end architecture;
```

`tests/nav/fixture/lib_a/dup.vhd` and `tests/nav/fixture/lib_b/dup.vhd` (identical):

```vhdl
entity dup is
end entity;

architecture rtl of dup is
begin
end architecture;
```

`tests/nav/fixture/lib_b/mid.vhd`:

```vhdl
library ieee;
use ieee.std_logic_1164.all;

library lib_a;

entity mid is
  port (
    clk : in std_ulogic;
    d : in std_ulogic_vector(7 downto 0);
    q : out std_ulogic_vector(7 downto 0)
  );
end entity;

architecture rtl of mid is
begin
  leaf_inst : entity lib_a.leaf
    port map (
      clk => clk,
      d => d,
      q => q
    );
end architecture;
```

`tests/nav/fixture/lib_b/top.vhd`:

```vhdl
library ieee;
use ieee.std_logic_1164.all;

library lib_a;

entity top is
  port (
    clk : in std_ulogic;
    d : in std_ulogic_vector(7 downto 0);
    q : out std_ulogic_vector(7 downto 0)
  );
end entity;

architecture rtl of top is
  signal mid_q : std_ulogic_vector(7 downto 0);
begin
  leaf_inst : entity lib_a.leaf
    generic map (
      width => 8
    )
    port map (
      clk => clk,
      d => d,
      q => mid_q
    );

  gen_mid : if true generate
    mid_inst : entity work.mid
      port map (
        clk => clk,
        d => mid_q,
        q => q
      );
  end generate;
end architecture;
```

`tests/nav/fixture/lib_b/comp_user.vhd`:

```vhdl
library ieee;
use ieee.std_logic_1164.all;

entity comp_user is
  port (
    clk : in std_ulogic
  );
end entity;

architecture rtl of comp_user is
  component leaf is
    generic (
      width : positive := 8
    );
    port (
      clk : in std_ulogic;
      d : in std_ulogic_vector(width - 1 downto 0);
      q : out std_ulogic_vector(width - 1 downto 0)
    );
  end component;

  signal d, q : std_ulogic_vector(7 downto 0);
begin
  leaf_comp_inst : leaf
    port map (
      clk => clk,
      d => d,
      q => q
    );
end architecture;
```

Check: `grep -n "entity leaf is" tests/nav/fixture/lib_a/leaf.vhd` prints `6:entity leaf is`; `grep -n "mid_inst" tests/nav/fixture/lib_b/top.vhd` prints `28:    mid_inst : entity work.mid`.

- [ ] **Step 2: Write the conftest**

`tests/nav/conftest.py`:

```python
"""Run ``vhdl-tools nav`` commands against the fixture project."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from vhdl_tools import cli
from vhdl_tools.nav import NavError
from vhdl_tools.nav.lsp import find_std_libraries, find_vhdl_ls

FIXTURE = Path(__file__).parent / "fixture"

NavRunner = Callable[..., tuple[int, str]]


def _vhdl_ls_ready() -> bool:
    try:
        find_std_libraries(find_vhdl_ls())
    except NavError:
        return False
    return True


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE


@pytest.fixture
def fixture_copy(tmp_path) -> Path:
    target = tmp_path / "fixture"
    shutil.copytree(FIXTURE, target)
    return target


@pytest.fixture
def nav_cli(capsys) -> NavRunner:
    """``run("find", "--name", "x", config=...)`` -> (exit code, stdout).
    ``config=None`` leaves ``--config`` out."""

    def run(*args: str, config: Path | None = FIXTURE) -> tuple[int, str]:
        argv = ["nav", *args]
        if config is not None:
            argv += ["--config", str(config)]
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        return exc.value.code, capsys.readouterr().out

    return run


@pytest.fixture
def nav(nav_cli) -> NavRunner:
    """``nav_cli``, skipped when vhdl_ls or its standard libraries are missing."""
    if not _vhdl_ls_ready():
        pytest.skip("vhdl_ls or its standard libraries are not installed")
    return nav_cli
```

- [ ] **Step 3: Write the failing end-to-end tests**

`tests/nav/test_e2e.py`:

```python
"""vhdl-tools nav against the fixture project and a real vhdl_ls."""

from __future__ import annotations

from vhdl_tools import cli


def test_nav_group_is_registered(capsys):
    assert "nav" in cli.GROUPS


def test_find_exact_filters_fuzzy_hits(nav):
    code, out = nav("find", "--name", "leaf")
    assert code == 0
    assert out.splitlines() == ["entity leaf  [lib_a]  lib_a/leaf.vhd:6", "1 hit"]


def test_find_same_name_in_two_libraries(nav):
    code, out = nav("find", "--name", "dup")
    assert code == 0
    assert "[lib_a]  lib_a/dup.vhd:1" in out
    assert "[lib_b]  lib_b/dup.vhd:1" in out
    assert out.rstrip().endswith("2 hits")


def test_find_substring_stays_in_project(nav):
    code, out = nav("find", "--name", "lea", "--substring")
    assert code == 0
    assert "entity leaf" in out
    assert "Vital" not in out


def test_find_nothing_is_not_an_error(nav):
    code, out = nav("find", "--name", "nothing_here")
    assert code == 0
    assert out.startswith("No declaration named nothing_here in the library map (2 libraries: lib_a, lib_b)")


def test_find_standard_library_name(nav):
    code, out = nav("find", "--name", "std_ulogic", "--kind", "type")
    assert code == 0
    assert "std_logic_1164" in out.lower()


def test_def_by_name(nav):
    code, out = nav("def", "--name", "lib_a.leaf", "--context", "2")
    assert code == 0
    assert out.splitlines() == [
        "entity leaf  [lib_a]  lib_a/leaf.vhd:6",
        "6  entity leaf is",
        "7    generic (",
        "8      width : positive := 8",
    ]


def test_def_name_case_insensitive(nav):
    code, out = nav("def", "--name", "Lib_A.LEAF", "--context", "0")
    assert code == 0
    assert out.splitlines()[0] == "entity leaf  [lib_a]  lib_a/leaf.vhd:6"


def test_def_by_pos(nav, fixture_dir, monkeypatch):
    monkeypatch.chdir(fixture_dir)
    code, out = nav("def", "--pos", "lib_b/top.vhd:28:29", "--context", "0")
    assert code == 0
    assert out.splitlines()[0] == "entity mid  [lib_b]  lib_b/mid.vhd:6"


def test_def_from_subdirectory_without_config(nav, fixture_dir, monkeypatch):
    monkeypatch.chdir(fixture_dir / "lib_b")
    code, out = nav("def", "--pos", "top.vhd:17:30", "--context", "0", config=None)
    assert code == 0
    assert out.splitlines()[0] == "entity leaf  [lib_a]  lib_a/leaf.vhd:6"


def test_def_ambiguous(nav):
    code, out = nav("def", "--name", "dup")
    assert code == 1
    assert out.startswith("Error: dup is ambiguous")
    assert "lib_a/dup.vhd:1" in out and "lib_b/dup.vhd:1" in out


def test_def_needs_name_or_pos(nav):
    code, out = nav("def")
    assert code == 1
    assert "exactly one of --name or --pos" in out


def test_refs_skip_declaration_lines(nav):
    code, out = nav("refs", "--name", "lib_a.leaf")
    assert code == 0
    assert out.splitlines() == [
        "lib_b/mid.vhd",
        "     16:28  leaf_inst : entity lib_a.leaf",
        "lib_b/top.vhd",
        "     17:28  leaf_inst : entity lib_a.leaf",
        "2 references in 2 files",
    ]


def test_refs_with_declaration(nav):
    code, out = nav("refs", "--name", "lib_a.leaf", "--with-decl")
    assert code == 0
    assert "architecture rtl of leaf is" in out
    assert out.rstrip().endswith("4 references in 3 files")


def test_show_entity(nav):
    code, out = nav("show", "--name", "leaf")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "entity leaf  [lib_a]  lib_a/leaf.vhd:6"
    assert "    q : out std_ulogic_vector(width - 1 downto 0)" in lines
    assert lines[-1] == "end entity;"


def test_show_package_lists_declarations(nav):
    code, out = nav("show", "--name", "pkg_a")
    assert code == 0
    assert out.splitlines() == [
        "package pkg_a  [lib_a]  lib_a/pkg_a.vhd:4",
        "  type state_t  L5",
        "  function add1[NATURAL return NATURAL]  L6",
    ]


def test_show_function(nav):
    code, out = nav("show", "--name", "add1")
    assert code == 0
    assert out.splitlines()[0] == "function add1[NATURAL return NATURAL]  [lib_a.pkg_a]  lib_a/pkg_a.vhd:6"
    assert "return natural" in out


def test_warning_for_library_without_files(nav, fixture_copy):
    config = fixture_copy / "vhdl_ls.toml"
    config.write_text(config.read_text() + 'ghost.files = ["nope/*.vhd"]\n')
    code, out = nav("find", "--name", "leaf", config=fixture_copy)
    assert code == 0
    assert out.startswith("Warning: no files match the globs of ghost")
    assert "entity leaf  [lib_a]" in out


def test_missing_config_is_a_clean_error(nav_cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out = nav_cli("find", "--name", "leaf", config=None)
    assert code == 1
    assert out.startswith("Error: No vhdl_ls.toml in")
    assert "vhdl-tools nav init" in out


def test_missing_vhdl_ls_is_a_clean_error(nav_cli, tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    code, out = nav_cli("find", "--name", "leaf")
    assert code == 1
    assert out.strip() == (
        "Error: vhdl_ls not found (checked $VHDL_LS, PATH, ~/.cargo/bin). Install: cargo install vhdl_ls"
    )
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_e2e.py -v`
Expected: FAIL — `test_nav_group_is_registered` fails (`assert 'nav' in {...}`); the command tests fail with `SystemExit(2)` / `invalid choice: 'nav'`.

- [ ] **Step 5: Register the group in `cli.py`**

In `src/vhdl_tools/cli.py`, add to `GROUPS` after the `"wave"` entry:

```python
    "nav": (
        "vhdl_tools.nav.server",
        "nav_",
        "VHDL file index and exact lookups through vhdl_ls (index, find, def, refs, show, tree)",
    ),
```

and change the parser description in `main`:

```python
        description="VUnit, synthesis, waveform and VHDL lookup tools for HDL projects.",
```

- [ ] **Step 6: Write `server.py` with `find`, `def`, `refs`, `show`**

`src/vhdl_tools/nav/server.py`:

```python
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
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/nav/test_e2e.py tests/test_cli.py -v`
Expected: all passed (`test_every_tool_gets_a_command` in `tests/test_cli.py` now also covers the four `nav` commands).

- [ ] **Step 8: Commit**

```bash
git add tests/nav/fixture tests/nav/conftest.py tests/nav/test_e2e.py src/vhdl_tools/nav/server.py src/vhdl_tools/cli.py
git commit -m "feat(nav): find, def, refs and show commands"
```

---

### Task 7: The per-file index

**Files:**
- Create: `src/vhdl_tools/nav/index.py`
- Modify: `src/vhdl_tools/nav/server.py` (add `nav_index`, imports)
- Test: `tests/nav/test_index.py`, `tests/nav/test_e2e.py` (append)

**Interfaces:**
- Consumes: `Node` (Task 1), `NavError`, `find_config` (Task 2), `LspSession`, `find_vhdl_ls`, `find_std_libraries`, `vhdl_ls_command` (Task 3), `source_lines` (Task 4), `_document_symbols` (Task 6).
- Produces:
  - `TARGET: re.Pattern` (what follows an instance label).
  - `span(start: int, end: int) -> str` (0-based in, `"[a-b]"` / `"[a]"` 1-based out).
  - `declared_text(line: str, col: int) -> str` (text after the `:` of the declaration whose name starts at `col`, up to `;` or the closing parenthesis, whitespace collapsed).
  - `instance_target(instance: Node, lines: list[str]) -> tuple[str, str, int, int] | None` → `(how, unit, line, col)`: `how` in `entity|component|configuration`, `unit` as written without spaces (`work.mid`), `line`/`col` 0-based of the unit name's last segment.
  - `build_index(title: str, nodes: list[Node], lines: list[str]) -> str`.
  - Command `nav_index(file: str, config: str | None = None) -> str`.

- [ ] **Step 1: Write the failing unit tests**

`tests/nav/test_index.py`:

```python
"""Index layout and instantiation parsing, without vhdl_ls."""

from __future__ import annotations

from vhdl_tools.nav.index import build_index, declared_text, instance_target, span
from vhdl_tools.nav.symbols import Node


def N(kind, name, line, col, start, end, children=(), detail=""):
    return Node(kind, name, detail, line, col, start, end, list(children))


def test_span():
    assert span(4, 4) == "[5]"
    assert span(4, 9) == "[5-10]"


def test_declared_text():
    assert declared_text("    clk : in std_ulogic;", 4) == "in std_ulogic"
    assert declared_text("    q : out std_ulogic_vector(width - 1 downto 0)", 4) == (
        "out std_ulogic_vector(width - 1 downto 0)"
    )
    assert declared_text("    width : positive := 8", 4) == "positive := 8"
    assert declared_text("    level : out natural range 0 to depth := 0; -- note", 4) == (
        "out natural range 0 to depth := 0"
    )
    assert declared_text("  port (a, b : in bit);", 11) == "in bit"
    assert declared_text("  process (clk)", 2) == ""


def test_instance_target_forms():
    lines = [
        "  u1 : entity lib_a.leaf",
        "    generic map (width => 8)",
        "    port map (clk => clk);",
        "  u2 : leaf port map (clk);",
        "  u3 : configuration lib.cfg_top;",
        "  u4 : entity work.mid(rtl) port map (clk);",
    ]
    assert instance_target(N("instance", "u1", 0, 2, 0, 2), lines) == ("entity", "lib_a.leaf", 0, 20)
    assert instance_target(N("instance", "u2", 3, 2, 3, 3), lines) == ("component", "leaf", 3, 7)
    assert instance_target(N("instance", "u3", 4, 2, 4, 4), lines) == ("configuration", "lib.cfg_top", 4, 25)
    assert instance_target(N("instance", "u4", 5, 2, 5, 5), lines) == ("entity", "work.mid", 5, 19)
    assert instance_target(N("instance", "u5", 0, 2, 0, 0), ["  u5"]) is None


def test_build_index():
    lines = [
        "library ieee;",
        "use ieee.std_logic_1164.all;",
        "entity e is",
        "  generic (ram_type : ram_style_t := auto);",
        "  port (clk : in std_ulogic;",
        "        q : out std_ulogic := '0');",
        "end entity;",
        "architecture a of e is",
        "  signal x, y : bit;",
        "  signal z : bit;",
        "begin",
        "  g : if true generate",
        "    u : entity work.leaf port map (clk);",
        "  end generate;",
        "  process begin wait; end process;",
        "end architecture;",
    ]
    entity = N("entity", "e", 2, 7, 2, 6, [
        N("signal", "ram_type", 3, 11, 3, 3),  # an unresolved generic type, as vhdl_ls reports it
        N("port", "clk", 4, 8, 4, 4, detail=": in"),
        N("port", "q", 5, 8, 5, 5, detail=": out"),
    ])
    arch = N("architecture", "a", 7, 13, 7, 15, [
        N("signal", "x", 8, 9, 8, 8),
        N("signal", "y", 8, 12, 8, 8),
        N("signal", "z", 9, 9, 9, 9),
        N("generate", "g", 11, 2, 11, 13, [N("instance", "u", 12, 4, 12, 12)]),
        N("process", "", 14, 2, 14, 14, [N("", "if statement", 14, 10, 14, 14)]),
    ])
    assert build_index("e.vhd", [entity, arch], lines) == "\n".join([
        "e.vhd  16 lines",
        "context [1-2]: ieee.std_logic_1164.all",
        "entity e [3-7]",
        "  generics:",
        "    ram_type : ram_style_t := auto [4]",
        "  ports:",
        "    clk : in std_ulogic [5]",
        "    q : out std_ulogic [6]",
        "architecture a of e [8-16]",
        "  signals: x, y [9]; z [10]",
        "  generate g [12-14]",
        "    instance u : entity work.leaf [13]",
        "  process [15]",
    ])
```

- [ ] **Step 2: Append the failing end-to-end tests**

Append to `tests/nav/test_e2e.py`:

```python


def test_index_top(nav, fixture_dir, monkeypatch):
    monkeypatch.chdir(fixture_dir)
    code, out = nav("index", "--file", "lib_b/top.vhd", config=None)
    assert code == 0
    assert out.splitlines() == [
        "lib_b/top.vhd  35 lines",
        "context [1-4]: ieee.std_logic_1164.all",
        "entity top [6-12]",
        "  ports:",
        "    clk : in std_ulogic [8]",
        "    d : in std_ulogic_vector(7 downto 0) [9]",
        "    q : out std_ulogic_vector(7 downto 0) [10]",
        "architecture rtl of top [14-35]",
        "  signals: mid_q [15]",
        "  instance leaf_inst : entity lib_a.leaf [17-25]",
        "  generate gen_mid [27-34]",
        "    instance mid_inst : entity work.mid [28-33]",
    ]


def test_index_generics_and_unlabelled_process(nav, fixture_dir, monkeypatch):
    monkeypatch.chdir(fixture_dir)
    code, out = nav("index", "--file", "lib_a/leaf.vhd", config=None)
    assert code == 0
    assert out.splitlines() == [
        "lib_a/leaf.vhd  27 lines",
        "context [1-4]: ieee.std_logic_1164.all, work.pkg_a.all",
        "entity leaf [6-15]",
        "  generics:",
        "    width : positive := 8 [8]",
        "  ports:",
        "    clk : in std_ulogic [11]",
        "    d : in std_ulogic_vector(width - 1 downto 0) [12]",
        "    q : out std_ulogic_vector(width - 1 downto 0) [13]",
        "architecture rtl of leaf [17-27]",
        "  signals: state [18]",
        "  process [20-26]",
    ]


def test_index_package_and_body(nav, fixture_dir, monkeypatch):
    monkeypatch.chdir(fixture_dir)
    code, out = nav("index", "--file", "lib_a/pkg_a.vhd", config=None)
    assert code == 0
    assert out.splitlines() == [
        "lib_a/pkg_a.vhd  14 lines",
        "context [1-2]: ieee.std_logic_1164.all",
        "package pkg_a [4-7]",
        "  types: state_t [5]",
        "  function add1[NATURAL return NATURAL] [6]",
        "package body pkg_a [9-14]",
        "  function add1[NATURAL return NATURAL] [10-13]",
    ]


def test_index_component_declaration(nav, fixture_dir, monkeypatch):
    monkeypatch.chdir(fixture_dir)
    code, out = nav("index", "--file", "lib_b/comp_user.vhd", config=None)
    assert code == 0
    assert out.splitlines()[-3:] == [
        "  components: leaf [11-20]",
        "  signals: d, q [22]",
        "  instance leaf_comp_inst : component leaf [24-29]",
    ]


def test_index_without_any_config(nav, fixture_dir, tmp_path, monkeypatch):
    import shutil

    lone = tmp_path / "lone" / "leaf.vhd"
    lone.parent.mkdir()
    shutil.copy(fixture_dir / "lib_a" / "leaf.vhd", lone)
    monkeypatch.chdir(lone.parent)
    code, out = nav("index", "--file", "leaf.vhd", config=None)
    assert code == 0
    assert "entity leaf [6-15]" in out
    assert "  process [20-26]" in out


def test_index_missing_file(nav_cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out = nav_cli("index", "--file", "nope.vhd", config=None)
    assert code == 1
    assert out.strip() == "Error: no file nope.vhd"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_index.py tests/nav/test_e2e.py -k "index or span or declared or instance_target" -v`
Expected: `test_index.py` fails with `ModuleNotFoundError: No module named 'vhdl_tools.nav.index'`; the e2e index tests fail with `invalid choice: 'index'` (exit 2).

- [ ] **Step 4: Write `index.py`**

`src/vhdl_tools/nav/index.py`:

```python
"""Per-file skeleton with line ranges: the VHDL counterpart of the tree-sitter
``index`` tool in the Maki harness. Built from vhdl_ls documentSymbol (which is
syntactic, so it needs no library map) plus declaration text from the source.
Nodes carry 0-based lines; the output uses 1-based ``[start-end]`` ranges.
"""

from __future__ import annotations

import re

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
_ITEMS = frozenset({"process", "function", "procedure", "instance", "generate", "block"})
_NESTED = frozenset({"generate", "block"})
_HIDDEN = frozenset({"parameter", "literal"})


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
            text = declared_text(lines[member.line], member.col) if member.line < len(lines) else ""
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
        parts = "; ".join(f"{', '.join(names)} {span(a, b)}" for a, b, names in runs)
        out.append(f"{pad}{_plural(kind)}: {parts}")
    for item in items:
        where = span(item.start_line, item.end_line)
        label = " ".join(part for part in (item.kind, item.name) if part)
        if item.kind in ("function", "procedure"):
            out.append(f"{pad}{label}{item.detail} {where}")
        elif item.kind == "instance":
            target = instance_target(item, lines)
            via = f" : {target[0]} {target[1]}" if target else ""
            out.append(f"{pad}{label}{via} {where}")
        else:
            out.append(f"{pad}{label} {where}")
            if item.kind in _NESTED:
                out.extend(_body(item, lines, indent + 1))
    return out


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
```

- [ ] **Step 5: Add `nav_index` to `server.py`**

Add imports:

```python
from vhdl_tools.nav.index import build_index
```

and append:

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/nav tests/test_cli.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add src/vhdl_tools/nav/index.py src/vhdl_tools/nav/server.py tests/nav/test_index.py tests/nav/test_e2e.py
git commit -m "feat(nav): Maki-style per-file index"
```

---

### Task 8: The instantiation tree

**Files:**
- Create: `src/vhdl_tools/nav/tree.py`
- Modify: `src/vhdl_tools/nav/server.py` (add `nav_tree`, imports)
- Test: `tests/nav/test_e2e.py` (append)

**Interfaces:**
- Consumes: `LspSession` (Task 3), `source_lines`, `format_tree` (Task 4), `find_hits`, `hit_at`, `resolve_one` (Task 5), `instance_target` (Task 7), `Hit`, `Node`, `TreeNode`, `locations`, `nodes_from_document_symbols`, `prefer_declarations` (Task 1), `_run`, `Project` (Task 6).
- Produces: `build_tree(session: LspSession, top: Hit, depth: int = 0) -> TreeNode`; command `nav_tree(top: str, depth: int = 0, config: str | None = None) -> str`.

- [ ] **Step 1: Append the failing end-to-end tests**

Append to `tests/nav/test_e2e.py`:

```python


def test_tree(nav):
    code, out = nav("tree", "--top", "top")
    assert code == 0
    assert out.splitlines() == [
        "entity top  [lib_b]  lib_b/top.vhd:6",
        "  leaf_inst : entity leaf  [lib_a]  lib_a/leaf.vhd:6",
        "  mid_inst : entity mid  [lib_b]  lib_b/mid.vhd:6",
        "    leaf_inst : entity leaf  [lib_a]  lib_a/leaf.vhd:6",
    ]


def test_tree_depth(nav):
    code, out = nav("tree", "--top", "top", "--depth", "1")
    assert code == 0
    assert len(out.splitlines()) == 3


def test_tree_component_instantiation(nav):
    code, out = nav("tree", "--top", "comp_user")
    assert code == 0
    assert out.splitlines() == [
        "entity comp_user  [lib_b]  lib_b/comp_user.vhd:4",
        "  leaf_comp_inst : entity leaf  [lib_a]  lib_a/leaf.vhd:6  (component)",
    ]


def test_tree_unknown_entity(nav):
    code, out = nav("tree", "--top", "nope")
    assert code == 1
    assert out.startswith("Error: No entity named nope")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_e2e.py -k tree -v`
Expected: FAIL with `invalid choice: 'tree'` (exit 2).

- [ ] **Step 3: Write `tree.py`**

`src/vhdl_tools/nav/tree.py`:

```python
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
from collections.abc import Iterator
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


def _instances(nodes: list[Node]) -> Iterator[Node]:
    for node in nodes:
        if node.kind == "instance":
            yield node
        else:
            yield from _instances(node.children)


def _key(hit: Hit) -> tuple[str, str]:
    return hit.library.lower(), hit.name.lower()


def _add_note(note: str, extra: str) -> str:
    return f"{note}; {extra}" if note else extra


class _TreeBuilder:
    def __init__(self, session: LspSession, depth: int) -> None:
        self.session = session
        self.depth = depth
        self.cache: dict[Path, list[str]] = {}

    def expand(self, node: TreeNode, seen: tuple[tuple[str, str], ...], level: int) -> None:
        assert node.unit is not None
        architectures = self.architectures(node.unit)
        if len(architectures) > 1:
            names = ", ".join(arch.name for _, arch in architectures)
            node.note = _add_note(node.note, f"{len(architectures)} architectures: {names}")
        for path, arch in architectures:
            for instance in _instances(arch.children):
                child = self.resolve_instance(path, instance)
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
            entities = prefer_declarations(find_hits(self.session, last, kind="entity").hits)
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
        return TreeNode(instance.name, unit, hit_at(self.session, target_path, target_line, last))


def build_tree(session: LspSession, top: Hit, depth: int = 0) -> TreeNode:
    """The instances below ``top``; ``depth`` 0 means no limit."""
    root = TreeNode("", top.name, top)
    _TreeBuilder(session, depth).expand(root, (_key(top),), 1)
    return root
```

- [ ] **Step 4: Add `nav_tree` to `server.py`**

Extend the formatting import with `format_tree`, add `from vhdl_tools.nav.tree import build_tree`, and append:

```python
@tools.tool()
def nav_tree(top: str, depth: int = 0, config: str | None = None) -> str:
    """The instantiation tree below an entity: one line per instance (label,
    instantiated entity, file:line), indented by level.

    --top is an entity name (fifo, fifo.fifo); --depth limits the levels shown
    (0 = all). Component instantiations are matched to the one entity of that
    name; notes in parentheses mark components, cycles and unresolved units."""

    def body(project: Project, session: LspSession) -> str:
        hit = resolve_one(session, top, project.root, project.library_names, kind="entity")
        return "\n".join(format_tree(build_tree(session, hit, depth), project.root))

    return _run(config, body)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/nav tests/test_cli.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add src/vhdl_tools/nav/tree.py src/vhdl_tools/nav/server.py tests/nav/test_e2e.py
git commit -m "feat(nav): instantiation tree"
```

---

### Task 9: The Read hook

**Files:**
- Create: `src/vhdl_tools/nav/hook.py`
- Create (repo root paths): `skills/shared/bin/vhdl-read-hook` (executable), `hooks/hooks.json`
- Test: `tests/nav/test_hook.py`

**Interfaces:**
- Consumes: `nav_index` (Task 7), `ToolError`.
- Produces: `MIN_LINES_ENV = "VHDL_NAV_INDEX_MIN_LINES"`, `DEFAULT_MIN_LINES = 150`, `min_lines() -> int`, `decide(event: dict) -> dict | None` (the hook's JSON output, or None to allow), `main() -> None` (stdin event → stdout JSON; `python -m vhdl_tools.nav.hook`).

- [ ] **Step 1: Write the failing tests**

`tests/nav/test_hook.py`:

```python
"""The Claude Code Read hook: deny big full VHDL reads with the index, allow the rest."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vhdl_tools.nav import hook
from vhdl_tools.registry import ToolError

LAUNCHER = Path(__file__).parents[3] / "bin" / "vhdl-read-hook"
HOOKS_JSON = Path(__file__).parents[5] / "hooks" / "hooks.json"


def _event(path: Path, tool: str = "Read", **extra: object) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": str(path), **extra},
    }


def _vhdl(tmp_path: Path, lines: int, name: str = "big.vhd") -> Path:
    path = tmp_path / name
    path.write_text("-- line\n" * lines)
    return path


@pytest.fixture
def fake_index(monkeypatch):
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    monkeypatch.setattr(hook, "nav_index", lambda file: "INDEX")


def test_decide_denies_big_full_read(tmp_path, fake_index):
    big = _vhdl(tmp_path, 200)
    output = hook.decide(_event(big))["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert reason.startswith(f"{big} has 200 lines")
    assert "offset=1, limit=200" in reason
    assert reason.endswith("\n\nINDEX")


def test_decide_threshold_is_inclusive(tmp_path, fake_index):
    assert hook.decide(_event(_vhdl(tmp_path, 149, "a.vhd"))) is None
    assert hook.decide(_event(_vhdl(tmp_path, 150, "b.vhdl"))) is not None


def test_decide_allows_ranged_reads(tmp_path, fake_index):
    big = _vhdl(tmp_path, 200)
    assert hook.decide(_event(big, offset=1)) is None
    assert hook.decide(_event(big, limit=50)) is None


def test_decide_allows_other_files_and_tools(tmp_path, fake_index):
    text = tmp_path / "notes.txt"
    text.write_text("x\n" * 500)
    assert hook.decide(_event(text)) is None
    assert hook.decide(_event(_vhdl(tmp_path, 200), tool="Edit")) is None
    assert hook.decide(_event(tmp_path / "missing.vhd")) is None
    assert hook.decide({}) is None


def test_env_threshold(tmp_path, fake_index, monkeypatch):
    small = _vhdl(tmp_path, 20)
    monkeypatch.setenv(hook.MIN_LINES_ENV, "10")
    assert hook.decide(_event(small)) is not None
    monkeypatch.setenv(hook.MIN_LINES_ENV, "0")
    assert hook.decide(_event(_vhdl(tmp_path, 500, "huge.vhd"))) is None
    monkeypatch.setenv(hook.MIN_LINES_ENV, "junk")
    assert hook.min_lines() == hook.DEFAULT_MIN_LINES


def test_decide_allows_when_index_fails(tmp_path, monkeypatch):
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    monkeypatch.setattr(hook, "nav_index", lambda file: ToolError("Error: vhdl_ls not found"))
    assert hook.decide(_event(_vhdl(tmp_path, 200))) is None


def test_main_prints_the_decision(tmp_path, fake_index, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_event(_vhdl(tmp_path, 200)))))
    hook.main()
    output = json.loads(capsys.readouterr().out)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_allows_on_bad_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    hook.main()
    assert capsys.readouterr().out == ""


def test_main_allows_when_decide_raises(tmp_path, monkeypatch, capsys):
    def boom(event: dict) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(hook, "decide", boom)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_event(_vhdl(tmp_path, 200)))))
    hook.main()
    assert capsys.readouterr().out == ""


def test_hook_with_real_index(nav, fixture_dir, monkeypatch):
    """``nav`` only supplies the skip when vhdl_ls is missing."""
    monkeypatch.setenv(hook.MIN_LINES_ENV, "10")
    leaf = fixture_dir / "lib_a" / "leaf.vhd"
    reason = hook.decide(_event(leaf))["hookSpecificOutput"]["permissionDecisionReason"]
    assert "entity leaf [6-15]" in reason
    assert "  process [20-26]" in reason


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_launcher_skips_non_vhdl_quickly(tmp_path):
    result = subprocess.run(
        [str(LAUNCHER)],
        input=json.dumps(_event(tmp_path / "x.py")),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert (result.returncode, result.stdout) == (0, "")


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_launcher_denies_big_vhdl(nav, fixture_dir, monkeypatch):
    monkeypatch.setenv(hook.MIN_LINES_ENV, "10")
    result = subprocess.run(
        [str(LAUNCHER)],
        input=json.dumps(_event(fixture_dir / "lib_a" / "leaf.vhd")),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"


def test_hooks_json_points_at_the_launcher():
    config = json.loads(HOOKS_JSON.read_text())
    (entry,) = config["hooks"]["PreToolUse"]
    assert entry["matcher"] == "Read"
    (command,) = entry["hooks"]
    assert command["type"] == "command"
    assert command["command"] == '"${CLAUDE_PLUGIN_ROOT}/skills/shared/bin/vhdl-read-hook"'
    assert LAUNCHER.is_file()
```

Path check: `tests/nav/test_hook.py` → `parents[3]` is `skills/shared`, `parents[5]` is the repo root.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_hook.py -v`
Expected: FAIL with `ImportError: cannot import name 'hook' from 'vhdl_tools.nav'`.

- [ ] **Step 3: Write `hook.py`**

`src/vhdl_tools/nav/hook.py`:

```python
"""Claude Code ``PreToolUse`` hook for ``Read``.

A full read (no offset, no limit) of a VHDL file with at least
``VHDL_NAV_INDEX_MIN_LINES`` lines (default 150; 0 turns the hook off) is
denied, and the reason Claude sees is the file's ``vhdl-tools nav index``, so
it reads only the ranges it needs. Anything unexpected allows the read: this
hook must never be the reason a file cannot be read.

Run as ``python -m vhdl_tools.nav.hook`` (see ``skills/shared/bin/vhdl-read-hook``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from vhdl_tools.nav.server import nav_index
from vhdl_tools.registry import ToolError

MIN_LINES_ENV = "VHDL_NAV_INDEX_MIN_LINES"
DEFAULT_MIN_LINES = 150
VHDL_SUFFIXES = frozenset({".vhd", ".vhdl"})


def min_lines() -> int:
    try:
        return int(os.environ.get(MIN_LINES_ENV, DEFAULT_MIN_LINES))
    except ValueError:
        return DEFAULT_MIN_LINES


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """The hook output that denies this Read, or None to allow it."""
    if event.get("tool_name") != "Read":
        return None
    tool_input = event.get("tool_input") or {}
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        return None
    path = Path(str(tool_input.get("file_path") or ""))
    if path.suffix.lower() not in VHDL_SUFFIXES or not path.is_file():
        return None
    threshold = min_lines()
    if threshold <= 0:
        return None
    with path.open(encoding="utf-8", errors="replace") as handle:
        lines = sum(1 for _ in handle)
    if lines < threshold:
        return None
    index = nav_index(str(path))
    if isinstance(index, ToolError) or index.startswith("Error:"):
        return None
    reason = (
        f"{path} has {lines} lines, so the vhdl-tools nav hook shows its index "
        "instead of the full text. Read the ranges you need with offset and limit "
        "(a range [a-b] is offset=a, limit=b-a+1). To read the whole file anyway, "
        f"use offset=1, limit={lines}.\n\n{index}"
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main() -> None:
    try:
        decision = decide(json.load(sys.stdin))
    except Exception:  # a broken hook must never block a read
        decision = None
    if decision is not None:
        json.dump(decision, sys.stdout)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write the launcher and register it** (paths from the repo root)

`skills/shared/bin/vhdl-read-hook`:

```bash
#!/usr/bin/env bash
# Claude Code PreToolUse hook for Read, registered in hooks/hooks.json: a full
# read of a large VHDL file gets its `vhdl-tools nav index` instead (see
# vhdl_tools/nav/hook.py). Exits 0 with no output, which allows the read,
# whenever the input is not about a VHDL file or anything is missing or fails.
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
input="$(cat)"
pattern='\.[vV][hH][dD]([lL])?"'
[[ $input =~ $pattern ]] || exit 0
command -v uv >/dev/null 2>&1 || exit 0
printf '%s' "$input" | uv run --quiet --frozen --project "$here/../tools" python -m vhdl_tools.nav.hook 2>/dev/null
exit 0
```

Run: `chmod +x skills/shared/bin/vhdl-read-hook`

`hooks/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/skills/shared/bin/vhdl-read-hook\"",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: Run the tests and the plugin validator**

Run (from `skills/shared/tools`): `uv run pytest tests/nav/test_hook.py -v`
Expected: all passed (the two vhdl_ls-backed tests skip without vhdl_ls).

Run (from the repo root): `claude plugin validate --strict .claude-plugin/plugin.json`
Expected: exit 0, no errors about `hooks/hooks.json`.

- [ ] **Step 6: Commit**

```bash
git add src/vhdl_tools/nav/hook.py tests/nav/test_hook.py
git -C ~/git/vhdl-skills add skills/shared/bin/vhdl-read-hook hooks/hooks.json
git commit -m "feat(nav): Read hook serves the index for large VHDL files"
```

---

### Task 10: `init`, docs, validation and measurement

**Files:**
- Modify: `src/vhdl_tools/nav/server.py` (add `nav_init`)
- Modify (repo root paths): `skills/shared/ToolPolicy.md`, `skills/shared/tools/README.md`, `SETUP.md`, `README.md`, `validate.sh`, `install.sh`
- Test: `tests/nav/test_e2e.py` (append)

**Interfaces:**
- Consumes: `write_init` (Task 2), `find_vhdl_ls`, `find_std_libraries` (Task 3), `count` (Task 4), `tools` (Task 6).
- Produces: command `nav_init(layout: Literal["auto", "tsfpga", "flat"] = "auto", directory: str = ".") -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/nav/test_e2e.py`:

```python


def test_init_then_lookup(nav, tmp_path, fixture_dir):
    import shutil

    project = tmp_path / "proj"
    for library in ("lib_a", "lib_b"):
        shutil.copytree(fixture_dir / library, project / "modules" / library)
    code, out = nav("init", "--directory", str(project), config=None)
    assert code == 0
    assert out.splitlines()[0] == f"Wrote {project / 'vhdl_ls.toml'} with 2 libraries: lib_a, lib_b"
    code, out = nav("find", "--name", "leaf", config=project)
    assert code == 0
    assert "entity leaf  [lib_a]  modules/lib_a/leaf.vhd:6" in out


def test_init_refuses_to_overwrite(nav_cli, fixture_dir):
    code, out = nav_cli("init", "--directory", str(fixture_dir), config=None)
    assert code == 1
    assert "already exists" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/nav/test_e2e.py -k init -v`
Expected: FAIL — `invalid choice: 'init'` (exit 2).

- [ ] **Step 3: Add `nav_init`**

In `src/vhdl_tools/nav/server.py` add `from typing import Literal`, add `write_init` to the config import, and append:

```python
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
```

(`count` comes from the formatting import; add it there if Task 8 did not.)

- [ ] **Step 4: Run the whole nav suite**

Run: `uv run pytest tests/nav tests/test_cli.py -v`
Expected: all passed.

- [ ] **Step 5: Wire the docs** (paths from the repo root, `~/git/vhdl-skills`)

`validate.sh`: change `for group in vunit synth wave; do` to `for group in vunit synth wave nav; do`.

`install.sh`, in `install_claude()`, after the line `copy_or_link_dir "$ROOT/agents" "$PROJECT/.claude/agents"` insert:

```bash
  echo "Note: the VHDL Read hook (large .vhd reads get their vhdl-tools nav index) comes with the plugin install only."
```

`skills/shared/ToolPolicy.md`, section "Principle": after the `vhdl-tools` bullet insert:

```markdown
- `vhdl-tools nav` for VHDL structure and exact lookups. `nav index --file F`
  is a compact skeleton of a file with `[start-end]` line ranges: look at it
  first, then read only the ranges you need. With the Claude Code plugin, a
  full Read of a VHDL file of 150+ lines is answered with that index
  automatically. `find`/`def`/`refs`/`show`/`tree` answer "where is X
  declared, who uses it, what are its ports, what instantiates what" through
  vhdl_ls in a few lines, with no index to build.
```

In the corvidex section, replace the bullet that starts `- **Exact identifier already known**` (five lines, ending `already know.`) with:

```markdown
- **Exact identifier already known** (you have the name and want its
  declaration, its callers, its type, or "does this exist") →
  `vhdl-tools nav find`/`def`/`refs`/`show` first: local, exact, no index.
  corvidex's `find_symbol` / `find_definition` / `find_references` /
  `hover_info` are the fallback when nav cannot run. Never run a
  `search_*` query for a name you already know.
```

Insert before `### Multi-library designs`:

```markdown
### 5. `vhdl-tools nav`

VHDL structure and exact lookups through vhdl_ls, the VHDL language server.
Needs `vhdl_ls` (`cargo install vhdl_ls`) and its standard libraries (found
automatically in speja's cache, else set `VHDL_LS_LIBRARIES`). `index` works
on any file; the other commands need a `vhdl_ls.toml` in the project
(`vhdl-tools nav init` writes one; it never overwrites). Names may be
library-qualified (`fifo.fifo`); `--pos` is `FILE:LINE[:COL]`, 1-based.

| Command | Use |
|---|---|
| `index --file F` | Skeleton of one file with line ranges; read the ranges you need after it |
| `find --name N [--kind K] [--substring]` | Declarations with that name, one line each |
| `def --name N \| --pos P [--context C]` | Where it is declared, with source lines |
| `refs --name N \| --pos P [--with-decl]` | Every use, grouped by file |
| `show --name N \| --pos P` | Ports/generics, a signature, or a package's declarations |
| `tree --top E [--depth D]` | Instantiation tree below an entity |
| `init [--layout auto\|tsfpga\|flat]` | Write `vhdl_ls.toml` |

The Claude Code plugin's Read hook denies a full Read of a `.vhd`/`.vhdl`
file of 150+ lines (`VHDL_NAV_INDEX_MIN_LINES`, 0 = off) and returns the
index instead: read ranges with offset/limit, or `offset=1, limit=<lines>`
for the whole file. An ambiguous name lists the candidates and exits 1: pass
`lib.name`, `--kind` or `--pos`. "No declaration named X in the library map"
means the map does not cover it, not that it does not exist. A leading
`Warning:` line names libraries whose globs match no files. Fallback: grep,
then read the file.
```

`skills/shared/tools/README.md`:
- After the ported-groups table, add: ``The `nav` group is native, not a port: a per-file VHDL index and exact lookups through vhdl_ls (see below).``
- Under "Requirements", add: ``- `nav`: `vhdl_ls` (`cargo install vhdl_ls`) and its standard libraries: `$VHDL_LS_LIBRARIES`, else vhdl_ls's own install locations, else `~/.cache/speja/vhdl_libraries-*`. All commands but `index` need a `vhdl_ls.toml` (`vhdl-tools nav init`).``
- In the exit-code `1` bullet, append: ``For nav it is `Error: ...`.``
- After the `### wave` section, add:

```markdown
### nav

Names are identifiers, optionally library-qualified (`fifo`, `fifo.fifo`), matched exactly and case-insensitively. `--pos` is `FILE:LINE[:COL]`, 1-based, relative to the current directory or the project root. Every command except `init` takes `--config` (a `vhdl_ls.toml` or its directory; default: the nearest one upward). Output paths are relative to that file's directory.

| Command | Options | Purpose |
|---|---|---|
| `index` | `--file F` (required) | Skeleton with `[start-end]` ranges: context clauses, units, generics/ports with types, declarations, subprograms, processes, generates, instances. No `vhdl_ls.toml` needed |
| `find` | `--name N` (required), `--kind K`, `--substring` | Declarations with that name: kind, name, [library], file:line |
| `def` | `--name N` or `--pos P`, `--kind K`, `--context C` (default 3) | Declaration location plus source lines |
| `refs` | `--name N` or `--pos P`, `--kind K`, `--with-decl` | Uses, grouped by file |
| `show` | `--name N` or `--pos P`, `--kind K` | Declaration text (entity ports/generics, signature); a package's declarations |
| `tree` | `--top E` (required), `--depth D` (default 0 = all) | Instantiation tree below an entity |
| `init` | `--layout {auto,tsfpga,flat}`, `--directory D` (default `.`) | Write `vhdl_ls.toml`; never overwrites |

Each command starts vhdl_ls (`--silent --no-lint`, `-l <std library dir>`), asks, and stops it: ~0.1 s, no daemon or cache. Binary: `$VHDL_LS`, else PATH, else `~/.cargo/bin/vhdl_ls`.

The plugin's `hooks/hooks.json` runs `skills/shared/bin/vhdl-read-hook` before every Claude Code Read. A Read without offset/limit of a `.vhd`/`.vhdl` file with at least `VHDL_NAV_INDEX_MIN_LINES` lines (default 150, `0` = off) is denied with the file's `nav index` as the reason. Non-VHDL Reads exit in the bash pre-filter without starting uv; any failure allows the Read.
```

`SETUP.md`, under "Requirements", add after the waveform bullets:

```markdown
- For `vhdl-tools nav` (VHDL index and exact lookups) and the plugin's Read hook: `vhdl_ls` (`cargo install vhdl_ls`) and its VHDL standard libraries (picked up from speja's cache when present; otherwise `git clone --depth 1 https://github.com/VHDL-LS/rust_hdl ~/.local/share/rust_hdl` and `export VHDL_LS_LIBRARIES=~/.local/share/rust_hdl/vhdl_libraries`). Lookups other than `index` need a `vhdl_ls.toml` in the project (`vhdl-tools nav init`). Without vhdl_ls the hook simply lets reads through.
```

`README.md`: change `#   VUnit, synthesis and waveform command-line tool` to `#   VUnit, synthesis, waveform and VHDL index/lookup command-line tool`, add a tree line `├── hooks/hooks.json           # Read hook: large VHDL reads get the nav index` after the `.mcp.json` line, and after the paragraph starting `` `vhdl-tools` replaces the vunit-mcp`` add: ``Its `nav` group gives a per-file VHDL index with line ranges (served automatically by the plugin's Read hook for large files) and exact lookups (declarations, references, ports, instantiation trees) through vhdl_ls.``

- [ ] **Step 6: Run validation and the full test suite**

Run (from the repo root): `./validate.sh`
Expected: exit 0; no `documented command does not exist` errors; `claude plugin validate --strict` passes with `hooks/hooks.json`.

Run (from `skills/shared/tools`): `uv run pytest`
Expected: all passed (the existing groups' suites unchanged).

- [ ] **Step 7: Measure on hdl-modules**

```bash
S=$(mktemp -d)
cp -r ~/lance-compare/hdl-modules/modules "$S/"
cd "$S"
T=~/git/vhdl-skills/skills/shared/bin/vhdl-tools
$T nav index --file modules/fifo/src/fifo.vhd | wc -c
wc -c modules/fifo/src/fifo.vhd
$T nav init
$T nav show --name fifo.fifo | wc -c
$T nav refs --name fifo.fifo | wc -c
grep -rn "fifo" modules --include=*.vhd | wc -c
time $T nav tree --top fifo.fifo_wrapper
printf '{"tool_name":"Read","tool_input":{"file_path":"%s"}}' "$S/modules/fifo/src/fifo.vhd" \
  | time ~/git/vhdl-skills/skills/shared/bin/vhdl-read-hook | head -c 300
```

Expected: the index is a small fraction of `fifo.vhd` (the Maki-style 70–90% saving); `nav show`/`nav refs` well under reading the file or the grep output; `nav tree` and the hook each about a second or less including `uv run` start-up. Record the sizes and times for the final summary.

- [ ] **Step 8: Commit**

```bash
git add src/vhdl_tools/nav/server.py tests/nav/test_e2e.py
git -C ~/git/vhdl-skills add validate.sh install.sh skills/shared/ToolPolicy.md skills/shared/tools/README.md SETUP.md README.md
git commit -m "feat(nav): init command; document nav index, lookups and the Read hook"
```
