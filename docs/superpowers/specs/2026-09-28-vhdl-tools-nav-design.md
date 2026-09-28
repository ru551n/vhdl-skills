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
- vhdl_ls panics (`vhdl_lang/src/analysis/standard.rs`) when the config does
  not define `std` and `ieee`; `-l <libraries toml>` did not prevent it.

## Placement

A new command group in the existing CLI in `skills/shared/tools`, next to
`vunit`, `synth` and `wave`:

```
skills/shared/tools/src/vhdl_tools/nav/
  __init__.py
  lsp.py          # minimal stdio JSON-RPC/LSP client, stdlib only
  config.py       # locate, validate and generate vhdl_ls.toml
  resolve.py      # NAME / lib.NAME / FILE:LINE:COL -> LSP position
  formatting.py   # LSP results -> compact text
  server.py       # ToolRegistry + @tools.tool() commands
```

It registers in `cli.py` like the other groups. No new Python dependencies.

## Commands

`NAME` is a design-unit or declaration name, optionally library-qualified
(`fifo`, `fifo.fifo`, `common.types_pkg`). Matching is case-insensitive and
exact on the identifier (vhdl_ls's `workspace/symbol` is a substring match;
`nav` filters it). A `POS` is `FILE:LINE[:COL]`, 1-based as displayed by
editors and grep; `nav` converts to LSP's 0-based positions. Without COL, the
first identifier on the line is used.

Paths in output are relative to the directory holding `vhdl_ls.toml`.
Line numbers in output are 1-based.

| Command | LSP | Output |
|---|---|---|
| `nav find NAME [--kind K] [--prefix]` | `workspace/symbol` | One line per hit: `entity fifo  [fifo]  modules/fifo/src/fifo.vhd:65`. `--prefix` keeps substring hits instead of exact ones. Reports when the 200-hit cap was reached. |
| `nav def NAME\|POS [-C N]` | `workspace/symbol` or `definition` | Declaration location plus N (default 3) lines of context after it. |
| `nav refs NAME\|POS [--with-decl]` | `references` | Grouped by file: `  98:28  fifo_inst : entity fifo.fifo`. Summary line with the hit and file counts. |
| `nav show NAME\|POS` | `hover` | The declaration text vhdl_ls returns (entity/component with generics and ports, package header, subprogram signature, type). |
| `nav outline FILE\|LIB` | `documentSymbol` | Indented tree: design units, then generics, ports (with mode), signals, constants, processes, instances. `LIB` outlines every file in that library, units only. |
| `nav tree TOP [--depth N]` | `documentSymbol` + `definition` | Instantiation tree: `fifo_inst : fifo.fifo  modules/fifo/src/fifo.vhd:65`, children indented. Default depth unlimited; cycles and unresolved instances are marked. |
| `nav init [--layout tsfpga\|flat] [--dir D]` | none | Writes `vhdl_ls.toml` (see Configuration). |

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
4. Spawn `vhdl_ls --silent --no-lint` with cwd = project root; send
   `initialize` (rootUri = project root, hierarchical documentSymbol support)
   and `initialized`.
5. For file-scoped requests, `didOpen` the file first.
6. Issue the request(s), answer any server-to-client requests with `null`,
   ignore notifications.
7. Format, print, send `shutdown`/`exit`, kill after 1 s if still alive.

A command has a 30 s timeout covering all its LSP calls. No cache and no daemon:
the spike measured ~0.1 s per cold call. Revisit only if a real project
measures above ~1 s.

## Configuration

`nav` uses the project's own `vhdl_ls.toml`; it never edits one.

Validation before spawning:

- Both `std` and `ieee` libraries must be defined. If not: exit with an error
  naming the missing libraries and showing the lines to add (paths from the
  vhdl_ls standard library directory found on the machine, if any). This
  avoids the vhdl_lang panic seen in the spike.
- Every other library's globs must match at least one file. Libraries whose
  globs match nothing are listed as a warning on stderr (the spike's `**` map
  silently matched nothing and every query returned 0 hits).

`nav init` writes `vhdl_ls.toml` in `--dir` (default current directory) and
refuses if one exists:

- `--layout tsfpga` (default when `modules/*/src` exists): one library per
  `modules/<name>/`, files `src/*.vhd`, `test/*.vhd`, `sim/*.vhd`, plus any
  `*.vhdl` equivalents present.
- `--layout flat`: one library `work` listing each directory that contains
  VHDL files, as explicit per-directory globs.
- `std`/`ieee`: pointed at the standard-library directory found next to the
  vhdl_ls installation or in a known location (e.g. speja's
  `~/.cache/speja/vhdl_libraries-*`), marked `is_third_party = true`. If none
  is found, `init` says so and writes the file without them, and the error
  from validation will tell the user what is missing.
- `vunit_lib`/`osvvm`: added as third-party libraries when a VUnit install is
  found through the project's Python (`python -c "import vunit"`); skipped
  silently otherwise.

## Errors

Every error names the next step. Exit code is non-zero; the text starts with
`Error:` (the vhdl-tools convention, via `ToolError`).

| Situation | Message gist |
|---|---|
| vhdl_ls not found | `vhdl_ls not found (checked $VHDL_LS, PATH, ~/.cargo/bin). Install: cargo install vhdl_ls` |
| no `vhdl_ls.toml` | `No vhdl_ls.toml above <cwd>. Create one: vhdl-tools nav init` |
| std/ieee missing | names the missing libraries and prints the lines to add |
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
- Unit tests without vhdl_ls: `formatting.py` against recorded LSP JSON
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
- `nav tree` depends on `documentSymbol` exposing instances; if 0.88.0 does not,
  fall back to scanning instantiation statements in the architecture range and
  resolving each with `definition`. Checked first during implementation.
