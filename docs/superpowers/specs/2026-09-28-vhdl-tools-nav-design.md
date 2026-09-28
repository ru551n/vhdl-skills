# `vhdl-tools nav`: exact VHDL lookups through vhdl_ls

Date: 2026-09-28
Status: approved design, awaiting spec review

## Goal

Answer "where is X declared", "who uses X", "what are X's ports" and "what does
this design look like" for a VHDL project in a few hundred tokens instead of
reading whole files, with the same semantics as the editor's language server.

Success criteria:

- Each lookup returns an exact answer (no similarity ranking) resolved through
  the project's `vhdl_ls.toml` library map.
- Output is plain text sized for a conversation: one line per hit, source
  context only where asked for.
- A call finishes in well under a second on a project of ~1000 files.
- It needs nothing beyond the `vhdl_ls` binary: no MCP server, no index to
  build, no corvidex.

Non-goals: semantic or concept search (corvidex covers that), editing or
renaming code, linting (speja covers that), diagnostics.

## Relationship to corvidex

corvidex also wraps vhdl_ls (`find_symbol`, `find_definition`,
`find_references`, `hover_info`), but its navigation is coupled to its
embedding index: it only opens files the index holds (capped at
`MAX_SESSION_FILES = 200` per call) and generates its own `vhdl_ls.toml`
with libraries inferred from the directory layout. `nav` needs no index and
uses the project's own library map, so its scope is exactly the files that
map lists.

Division of labour after this change: `nav` for exact lookups, corvidex for
semantic/concept search. corvidex's navigation tools are left as they are
here; retiring them is a separate decision. corvidex's configuration and
the plugin's `.mcp.json` are out of scope.

## Evidence (spike, 2026-09-28, vhdl_ls 0.88.0)

Measured over LSP on `hdl-modules` (181 files, one library per module) and
`vhdl-ai-test` (887 files):

- Cold start + analysis + one query: ~0.09 s on both. No daemon is needed.
- `workspace/symbol`: exact hits with kind, library (`containerName`) and
  location; capped at 200 results.
- `textDocument/references` on entity `fifo`: both instantiations in `src`
  (including `entity fifo.fifo` from another library) plus the declaration and
  `end entity`; matches grep.
- `textDocument/definition` from `entity work.fifo`: resolves to `fifo.vhd:65`.
- `textDocument/hover` on an entity: the full normalised declaration, every
  generic and port with mode, type and default (~1.1k chars for `fifo`).
- `textDocument/documentSymbol`: hierarchical, e.g. `generic 'width'`,
  `port 'clk' : in`, with ranges.
- Raw LSP JSON is verbose (48 symbol hits = 14k chars); compression is the
  tool's job.
- A `cargo install vhdl_ls` binary ships no standard libraries. Without them
  it panics at startup (`vhdl_lang/src/config.rs`: "Couldn't find installed
  libraries") or, when the path given is wrong, during analysis
  (`analysis/standard.rs`). `-l` takes the *directory* holding the libraries'
  `vhdl_ls.toml` (vhdl_ls appends the file name); passing the file itself
  silently loads nothing. With `-l <dir>` the 887-file project analyses in
  0.10 s with no `std`/`ieee` in the project config.
- `documentSymbol` lists instances as `instance '<label>'` (kind 2), nested
  under `generate` blocks where they sit, so the instantiation tree needs no
  text scanning.
- Symbol names follow `<kind words> '<identifier>'` (`entity 'fifo'`,
  `package body 'axi_pkg'`, `record type 'axi_m2s_r_t'`,
  `port 'clk' : in`); subprograms are `function <name>[<signature>]`.
  `containerName` is the library for design units and `lib.unit` for
  declarations inside a unit (an architecture's container is
  `lib.<entity>`). Enumeration literals have no kind word
  (`idle[return state_t]`).
- `workspace/symbol` matching is fuzzy (subsequence), not substring: the
  query `leaf` also returns `VitalDefaultPortFlag` from ieee. Every mode
  filters vhdl_ls's hits itself.
- `textDocument/references` ignores `includeDeclaration`: the result always
  holds the declaration and, for an entity, the `architecture <a> of <e>`
  line(s), which is how `nav tree` finds an entity's architectures.
- `hover` on an entity or subprogram returns the full declaration; on a
  package only `package <name>`.
- Fixture probe (planned `tests/nav/fixture`): no diagnostics; definition
  resolves `entity lib_a.leaf`, `entity work.mid` (inside a `generate`) and a
  component instantiation (to the component declaration).

## Placement

A new command group in the existing CLI in `skills/shared/tools`, next to
`vunit`, `synth` and `wave`:

```
skills/shared/tools/src/vhdl_tools/nav/
  __init__.py
  lsp.py          # minimal stdio JSON-RPC/LSP client, stdlib only
  config.py       # locate, validate and generate vhdl_ls.toml
  symbols.py      # parse vhdl_ls symbol names and locations into Hit records
  resolve.py      # NAME / lib.NAME / FILE:LINE[:COL] -> declaration or position
  tree.py         # instantiation tree from an entity
  formatting.py   # Hit / reference / outline / tree -> compact text
  server.py       # ToolRegistry + @tools.tool() commands
```

It registers in `cli.py` like the other groups. No new Python dependencies.

## Commands

`NAME` is a design-unit or declaration name, optionally library-qualified
(`fifo`, `fifo.fifo`, `common.types_pkg`). Matching is case-insensitive and
exact on the identifier (vhdl_ls's `workspace/symbol` is a fuzzy match;
`nav` filters it). When both a package and its body match, the package
wins; likewise an entity wins over same-named components only when `--kind
entity` is given (otherwise it is ambiguous). A `POS` is `FILE:LINE[:COL]`, 1-based as displayed by
editors and grep; `nav` converts to LSP's 0-based positions. Without COL, the
first identifier on the line is used.

Arguments are options, as for every vhdl-tools group (the CLI is generated
from the tool signatures): `--name NAME`, `--pos POS`, `--config PATH`. The
table below writes them positionally for brevity; `nav find NAME` means
`vhdl-tools nav find --name NAME`.

Paths in output are relative to the directory holding `vhdl_ls.toml`.
Line numbers in output are 1-based.

| Command | LSP | Output |
|---|---|---|
| `nav find NAME [--kind K] [--substring]` | `workspace/symbol` | One line per hit: `entity fifo  [fifo]  modules/fifo/src/fifo.vhd:65`. `--substring` keeps names containing NAME instead of equal to it, from the project's own libraries only. Reports when the 200-hit cap was reached. |
| `nav def NAME\|POS [-C N]` | `workspace/symbol` or `definition` | Declaration location plus N (default 3) lines of context after it. |
| `nav refs NAME\|POS [--with-decl]` | `references` | Grouped by file: `  98:28  fifo_inst : entity fifo.fifo`. Summary line with the hit and file counts. Without `--with-decl`, the declaration itself and `end`/`architecture ... of` lines are dropped. |
| `nav show NAME\|POS` | `hover`, `documentSymbol` for packages | The declaration text vhdl_ls returns (entity/component with generics and ports, subprogram signature, type). For a package: one line per declaration in it (types, constants, subprograms with signatures), since hover has only its name. |
| `nav outline FILE\|LIB` | `documentSymbol` | Indented tree: design units, then generics, ports (with mode), signals, constants, processes, instances. `LIB` outlines every file in that library, units only. |
| `nav tree TOP [--depth N]` | `workspace/symbol` + `documentSymbol` + `definition` | Instantiation tree: `fifo_inst : fifo.fifo  modules/fifo/src/fifo.vhd:65`, children indented. Default depth unlimited; cycles and unresolved instances are marked. |
| `nav init [--layout auto\|tsfpga\|flat] [--directory D]` | none | Writes `vhdl_ls.toml` (see Configuration). |

`--kind` takes `entity`, `architecture`, `package`, `component`, `function`,
`procedure`, `type`, `signal`, `constant`, `port`, `generic`; it filters on the
kind word in vhdl_ls's symbol name (`entity 'fifo'`).

### Ambiguity

When `NAME` matches more than one declaration (same name in two libraries, or
overloads), `def`, `refs`, `show` and `tree` print the candidates as `nav find`
would and exit non-zero, asking for `lib.NAME` or a `POS`. They never pick
one silently.

### Output examples

```
$ vhdl-tools nav find resync --kind entity
entity resync_level    [resync]  modules/resync/src/resync_level.vhd:68
entity resync_counter  [resync]  modules/resync/src/resync_counter.vhd:47
...
8 hits
```

```
$ vhdl-tools nav refs fifo.fifo
modules/common/src/clean_packet_dropper.vhd
   98:29  fifo_inst : entity fifo.fifo
modules/fifo/src/fifo_wrapper.vhd
  138:29  fifo_inst : entity work.fifo
2 references in 2 files
```

## Per-call flow

1. Locate `vhdl_ls.toml`: `--config PATH`, else search upward from the
   current directory. The directory holding it is the project root.
2. Validate it (see Configuration).
3. Locate the binary: `$VHDL_LS`, else `vhdl_ls` on `PATH`, else
   `~/.cargo/bin/vhdl_ls`.
4. Locate the standard libraries (see Configuration).
5. Spawn `vhdl_ls --silent --no-lint [-l <stdlib dir>]` with cwd = project
   root; send
   `initialize` (rootUri = project root, hierarchical documentSymbol support)
   and `initialized`.
6. For file-scoped requests, `didOpen` the file first.
7. Issue the request(s), answer any server-to-client requests with `null`,
   ignore notifications.
8. Format, print, send `shutdown`/`exit`, kill after 1 s if still alive.

A command has a 30 s timeout covering all its LSP calls. No cache and no daemon:
the spike measured ~0.1 s per cold call. Revisit only if a real project
measures above ~1 s.

## Configuration

`nav` uses the project's own `vhdl_ls.toml`; it never edits one.

Standard libraries (`std`, `ieee`, …): vhdl_ls needs a directory holding a
`vhdl_ls.toml` that maps them. `nav` looks, in order, for:

1. `$VHDL_LS_LIBRARIES` (a directory);
2. the places vhdl_ls searches itself (`../vhdl_libraries`,
   `../../vhdl_libraries` and `../share/vhdl_libraries` relative to the
   binary, `/usr/lib/rust_hdl/vhdl_libraries`,
   `/usr/local/lib/rust_hdl/vhdl_libraries`); if found there, `-l` is not
   passed;
3. speja's cache, `~/.cache/speja/vhdl_libraries-*` (highest version).

If none exists it stops with an error explaining how to get them (a shallow
clone of `rust_hdl`, then `VHDL_LS_LIBRARIES`).

Validation before spawning: every library's globs (resolved relative to the
`vhdl_ls.toml`, `**` recursive as in vhdl_lang) must match at least one file.
Libraries matching nothing are listed as a warning line at the top of the
output, since every lookup in them will come back empty.

`nav init` writes `vhdl_ls.toml` in `--directory` (default current
directory) and refuses if one exists. It lists project libraries only; the
standard libraries come from the lookup above, and third-party libraries
(VUnit, OSVVM) are added by hand when wanted.

- `--layout tsfpga` (`auto` picks it when `modules/*/` holds VHDL): one
  library per `modules/<name>/`, files `modules/<name>/**/*.vhd` and
  `**/*.vhdl`, the same shape tsfpga's own generator writes.
- `--layout flat`: one library `lib` with `**/*.vhd` and `**/*.vhdl`.
  (`work` is not a legal library name in vhdl_ls.)

## Errors

Every error names the next step. Exit code is non-zero; the text starts with
`Error:` (the vhdl-tools convention, via `ToolError`).

| Situation | Message gist |
|---|---|
| vhdl_ls not found | `vhdl_ls not found (checked $VHDL_LS, PATH, ~/.cargo/bin). Install: cargo install vhdl_ls` |
| no `vhdl_ls.toml` | `No vhdl_ls.toml above <cwd>. Create one: vhdl-tools nav init` |
| no standard libraries found | lists the places searched and how to get them |
| library globs match nothing | warning line naming the libraries |
| vhdl_ls exits or crashes | exit code and last 20 lines of its stderr |
| timeout | which request timed out, after how long |
| no hits | `No declaration named X in the library map (<n> libraries: a, b, ...). The file may be outside the map.` Never "X does not exist". |
| ambiguous | candidate list, see Ambiguity |
| `POS` not on an identifier | the source line with a caret under COL |

## Skill wiring

- `skills/shared/ToolPolicy.md`: in the cost-aware routing, "exact identifier
  already known" goes to `vhdl-tools nav find/def/refs/show` first (local,
  ~0.1 s, no MCP); corvidex's `find_symbol` etc. remain valid when that server
  is connected. "Orienting in an unfamiliar project" goes to
  `nav outline`/`nav tree` before reading files. Keep the existing corvidex
  guidance for concept search.
- `skills/shared/tools/README.md`: a `nav` section with the commands, the
  vhdl_ls install line and `nav init`.
- `README.md` / `SETUP.md`: add `cargo install vhdl_ls` as an optional
  prerequisite.
- `validate.sh`: no change unless it enumerates CLI groups; check during
  implementation.

## Testing

- Fixture project `tests/nav/fixture/`: libraries `lib_a` and `lib_b`,
  a package in `lib_a` with a type and a function, an entity in `lib_a`, an
  entity in `lib_b` instantiating it as `entity lib_a.x` and a second
  instantiation through `work`, two same-named entities in different libraries
  (for ambiguity), and a `vhdl_ls.toml`.
- End-to-end pytest per command against the fixture, marked skip when vhdl_ls
  is not installed.
- Unit tests without vhdl_ls: `formatting.py` and `symbols.py` against LSP JSON
  responses (captured from the fixture), `resolve.py` position conversion,
  `config.py` validation and `init` generation on temporary directories.
- One manual measurement on `hdl-modules`, recorded in the PR description:
  output characters for `nav show fifo.fifo` and `nav refs fifo.fifo` versus
  reading `fifo.vhd` and grepping.

## Open risks

- `workspace/symbol` hit cap (200): `nav find` with a short prefix can be
  truncated; the output says so. Exact lookups filter after the cap, so a
  very common substring could push an exact match out. Mitigation: when the
  cap is hit and no exact match is present, retry with the full
  library-qualified name if given, else report truncation explicitly.
- vhdl_ls symbol-name format (`entity 'fifo'`) is not a stable API; parsing is
  isolated in `formatting.py` and covered by recorded-response tests, pinned
  to the vhdl_ls version recorded in the fixture.
- `nav tree` resolves each instance by calling `definition` on the unit name
  inside the instantiation statement, found by a regex over the statement's
  source range. Component instantiations resolve to the component
  declaration; `nav` then looks for a unique entity of that name and marks
  the instance unresolved otherwise.
