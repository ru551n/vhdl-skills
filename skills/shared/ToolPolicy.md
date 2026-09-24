# Tool Policy

## Principle

Use the purpose-built tool before the manual equivalent:

- `vhdl-tools` (the skills' `shared/bin/vhdl-tools`) for VUnit, synthesis,
  Vivado reports and waveforms. It runs the project's own VUnit and build
  scripts and returns compact summaries, so prefer it over calling
  `run.py`, `ghdl`, `yosys` or Vivado by hand and over reading raw logs,
  reports or waveform files.
- `corvidex-mcp`, when the host has it connected, for semantic search and
  exact code navigation. "Prefer" is a routing decision there, not a
  blanket "never grep" rule; see its section below.
- `speja`, when the project or the user has chosen it, for VHDL layout:
  it formats, so layout is never done by hand. Optional; see its section
  below.

`vhdl-tools <group> <command> --help` shows every option, and
`shared/tools/README.md` has the full command table. Every command also
accepts `--json-input '<json>'`. Exit status is 0 on success, 1 when the
tool reports a failure, 2 on invalid input, and 127 when `uv` is missing.

Run it from the HDL project's root: the project directory defaults to the
current directory. Configuration uses the environment variables the
earlier MCP servers used (`VUNIT_MCP_PROJECT_DIR`, `VUNIT_MCP_SIMULATOR`,
`TSFPGA_MCP_*`).

Only one compile, simulation or build runs per project at a time:
`vhdl-tools` takes a lock file and says when it had to wait. Run long
builds in a background shell.

Never invent a tool result. When a tool is unavailable, say so and use the
fallback listed for it.

**Never open a waveform file (`.vcd`, `.fst`, `.ghw`) directly**: no Read,
`cat`, `head`, `tail`, `grep` or ad-hoc script, not even to look at its
header, whatever its size appears to be. Only `vhdl-tools wave` reads them,
and it answers with a few lines. A waveform can be hundreds of megabytes,
and one direct read of it can use up the whole context.

## Tools

### 1. `corvidex-mcp`

Repository:
`https://github.com/ru551n/corvidex-mcp`

Preferred for:
- semantic search across VHDL, documentation, and related source code
- finding existing implementations before creating new RTL
- finding coding conventions and architectural precedents
- cross-referencing symbols across docs, VHDL and test code
- retrieving exact source ranges with commit attribution
- debug-context discovery

Relevant tools when exposed:
- `repository_status`
- `search_hdl`
- `search_vhdl` — alias for `search_hdl(language="vhdl")`. A pending
  upstream tool-selection-clarity PR removes this alias in favor of the
  explicit form; prefer `search_hdl(language="vhdl")` in new usage, but the
  alias still works until that PR merges.
- `search_docs`
- `search_code`
- `search_knowledge`
- `get_source`
- `sync_repositories`
- `reindex_repository`
- `find_definition` — exact, LSP/compiler-backed go-to-definition via
  `vhdl_ls`/Veridian
- `find_references` — exact find-all-usages
- `hover_info` — exact type/signature info at a location
- `find_symbol` — exact symbol-name search (workspace symbol lookup), not
  similarity search

Cost-aware routing — pick the tool by what kind of question this is, not by
habit or by "corvidex first, always". Measured on a real project : looking up a known entity
name cost 0.62 s / ~54.8 KB (~13,700 tokens) / 8
chunks across 5 files via `search_hdl`, vs. <0.1 s / ~16 KB / 180 lines
across 38 files via `grep -rn` (*more* complete, for that case), vs. 2.5 s /
421 chars (~105 tokens) via `find_symbol` — the exact declaration with
context, and the clear winner whenever the name is already known.
`find_references` on a signal was similarly cheap and exact (~385 tokens,
file:line:col). Route like this:

- **Exact identifier already known** (you have the name and want its
  declaration, its callers, its type, or "does this exist") →
  `find_symbol` / `find_definition` / `find_references` / `hover_info`
  first. Cheapest and exact. Never run a `search_*` query for a name you
  already know.
- **Concept, pattern, or "where/how does X happen"** (no exact name yet) →
  `search_hdl`/`search_knowledge`. This is what the semantic index is for;
  `grep` genuinely cannot answer this kind of question.
- **Cross-domain question spanning docs, RTL, and tests** →
  `search_knowledge`. Measurably excellent: a single `DEPTH_TO_SPACE` query
  mapped that opcode across the compiler, the model, the tests, and the RTL
  in one call.
- **Exhaustive mechanical enumeration of a literal string across every file
  type** (completeness matters more than ranking, including files outside
  the index) → local `grep` is a legitimate, often better, choice — use it
  and say so, rather than treating it as a last resort. See the exclusion
  list under Fallback below for other cases where local tools are the
  right call, not just an allowed one.

This replaces a blanket "always prefer corvidex over grep" rule: that rule
was too blunt, because for an already-known identifier `search_hdl` burns
roughly two orders of magnitude more tokens than `find_symbol` for a worse
answer. The spirit survives — do not bypass the semantic index for a
genuinely semantic/conceptual question just because grep is more familiar —
but grep is not automatically the wrong choice.

Known retrieval weaknesses (measured, not hypothetical) — treat a thin,
empty, or oddly ranked concept-search result as inconclusive, not as proof
the thing doesn't exist:
- A "reset synchroniser" concept query surfaced *none* of the 8 `resync_*`
  entities that exist in the indexed `hdl-modules` submodule, while
  `find_symbol("resync")` listed all of them immediately.
- An "AXI stream FIFO with backpressure" concept query ranked a testbench
  architecture above the actual `axi_stream_fifo` entity.
- Mitigation: when a concept search looks thin, empty, or suspiciously
  ranked, cross-check with `find_symbol` on the likely entity/signal name
  before concluding the target does not exist in the repository.

Zero-config repository naming: with no `[[repositories]]` entry configured,
the repository is auto-named `<dirname>-<8 hex hash>` (e.g.
`my_fpga-582e8509`), not the plain directory name. Any call that takes
a `repository=` argument must read the real name from `repository_status`
first — guessing the plain directory name (e.g. `my_fpga`) fails with
an unknown-repository error.

Launcher trap: registering the server with `uv --directory DIR run ...`
changes the server process's working directory to `DIR`; for corvidex that
means it indexes its *own* source tree instead of the target project —
silently, with no error. Use `uv --project DIR run ...` instead (this does
not change the working directory), or set `CORVIDEX_MCP_PROJECT_DIR` when
the launcher command can't be edited. After setup, confirm with
`repository_status` that the indexed repository is the target project, not
`corvidex-mcp` itself.

Search results carry line-number gutters, cap long bodies with a
`get_source(...)` follow-up marker, and warn on weak matches. Check the
navigation tools' parameter descriptions for whether they take 0- or
1-based lines before passing a displayed line number to
`find_definition`/`find_references`. Library-qualified instantiations
(`entity <lib>.<name>`, tsfpga's per-module-folder convention) resolve in
the navigation tools; if one still comes back empty, check that corvidex
generated a library-aware `vhdl_ls.toml` for the project before
concluding the target doesn't exist.

Usage rule:
1. Call `repository_status` when repository/index health matters, and
   always to get the real (possibly zero-config-generated) repository name
   before passing `repository=` to any other tool.
2. Choose the right tool per the cost-aware routing table above, not just
   the familiar one.
3. Search at topic granularity, not module granularity and not item
   granularity. Neither extreme works well: one query for "the whole
   module" returns a diffuse mix of unrelated chunks, but one query per
   individual port/signal/constant over-fragments a coherent unit and wastes
   calls on pieces that belong together. Group each query around one
   coherent topic/concern of the thing you're studying — e.g. "entity ports
   and generics", "the arbitration process", "a specific procedure's
   signature", "the reset/clock handling" — each as its own query, run
   several of these topic-scoped queries in parallel (`batch`/concurrent
   tool calls) rather than one broad query or a flood of single-item ones.
   Example for a VC like `axi_stream_master`: one query for its entity
   ports/generics, a separate query for `axi_stream_pkg`'s constructor
   functions (`new_axi_stream_master`/`new_axi_stream_slave`), a third for
   its push/check procedures — not one query per port, and not one query
   trying to cover the whole file.
4. Use `get_source` for exact source before copying or relying on an implementation detail.
5. Do not assume indexed material is current if status reports sync/index errors.
6. When a concept/semantic search result looks thin, empty, or oddly
   ranked, cross-check with `find_symbol` before concluding the thing
   you're looking for doesn't exist (see "known retrieval weaknesses"
   above) — don't take a weak `search_hdl`/`search_knowledge` result as
   the final word.

Local `Read`/`Glob`/`Grep`/`git grep`/`find` are the right call, not just an
allowed fallback, for:
- an exhaustive mechanical enumeration of a literal string across every
  file type (per the routing table above),
- material the server does not index at all for this project (e.g. Python
  build/config scripts like `run.py`/`module_*.py`, non-HDL project files),
- the current in-progress, uncommitted working tree of the project actively
  being authored (not yet sync-able into the index),
- confirmed server unavailability/unhealth (per the Availability decision
  below) or a `repository_status` sync error for the repository in question.
For a conceptual question or an already-known exact identifier, route per
the table above rather than defaulting to grep out of habit.

Fallback:
- project-local `Read`, `Glob`, `Grep`
- `git grep`
- `find`
- VHDL language server if independently available

### 2. `vhdl-tools vunit`

Discovering, compiling, elaborating and running a VUnit project, and
reading its results.

| Command | Use |
|---|---|
| `status` | First, when anything about the setup is unclear: project dir, interpreter, VUnit version, simulators, waveform support |
| `list-tests`, `list-files` | Test names (`lib.entity.test_case`) and compile order |
| `test-dependencies --test-name T` | The files one test needs |
| `compile` | Analyze only |
| `elaborate --test-patterns P` | Elaborate without simulating. Catches port, generic and type mismatches that `compile` misses; run it after every RTL or testbench interface change |
| `run-tests --test-patterns P` | Run tests, on half the logical CPUs unless `--num-threads N` is given. Add `--waveform-format vcd` (GHDL) or `fst` (NVC) when a failure may need signal-level debugging |
| `get-report --only-failing` | Pass/fail summary of the last run |
| `get-test-log --test-name T` | A failing test's log tail and check results |
| `get-test-waveform --test-name T` | Waveform path and failing check time, for `vhdl-tools wave` |
| `export-json` | VUnit's full project export |

Rules:
1. Pass `--simulator ghdl` or `--simulator nvc` (or set
   `VUNIT_MCP_SIMULATOR`) whenever more than one simulator is on `PATH`.
   Otherwise VUnit picks one itself; with an unusable `vsim` on `PATH`,
   tests fail in a fraction of a second with an empty log.
2. Run the smallest test pattern that answers the question; run full
   regressions at integration points.
3. Read `get-report` before logs, and logs before waveforms.
4. Headless NVC waveforms need the `--wave` flag in the project's own
   VUnit; `status` reports whether it has it. GHDL records either way.

Fallback: the project's `run.py` directly (`--elaborate`, `-p $(( $(nproc) / 2 ))`,
`VUNIT_SIMULATOR=nvc`), then plain GHDL for a non-VUnit testbench. Never
replace an existing VUnit project with a custom GHDL harness.

### 3. `vhdl-tools wave`

Signal-level measurements in VCD or FST files, usually the path from
`vhdl-tools vunit get-test-waveform`. Every command takes `--file`. Times
are strings like `10ns` or integer file ticks; signal names accept unique
suffixes (`clk` matches `tb.dut.clk`).

| Command | Use |
|---|---|
| `open` | Timescale, duration, signal count |
| `search --pattern P` | Exact hierarchical signal names |
| `value-at --time T --signals S...` | Values at one instant |
| `values --signal S --start T --end T` | Transitions in a window |
| `find --signal S --value V` | When a signal held a value |
| `latency --a A --b B` | Edge-to-edge delay; with A and B the same signal, the interval between its edges |
| `analyze --signal S` | Clock period and duty, X/Z fraction, value statistics |
| `plot --signals S... --out F.png` | A picture, only when it adds something |

Query the smallest window around the failing check's time. Never read the
file any other way (see Principle above). When `vhdl-tools wave` cannot run,
say so and stop: the fallback is GTKWave, for a person to open, not a direct
read of the file.

### 4. `vhdl-tools synth`

Open-source synthesis (GHDL + Yosys through tsfpga) for resource counts,
and a tsfpga project's own Vivado builds and reports.

| Command | Use |
|---|---|
| `status`, `targets` | Yosys, the GHDL plugin, and which chips and families are available |
| `inspect --sources F...` | Entities, architectures and generics, to pick a top level |
| `synthesize --sources F... --top T --chip C [--family F] [--generics JSON]` | Aggregated resource counts |
| `project-status`, `project-list-builds` | The project's build script and its builds |
| `project-build --project-filters P...` | Netlist builds; add `--no-netlist-builds` for a top-level Vivado build (`--synth-only`, `--from-impl`) |
| `project-get-timing-report --project NAME` | Vivado timing (`--report-type summary\|pulse_width\|bus_skew\|clock_interaction`) |
| `project-get-utilization-report --project NAME` | Hierarchical utilization |
| `project-get-drc-report --project NAME` | DRC or methodology checks |

Rules:
1. Never guess the top level, chip, family or a generic value; ask.
2. There is no architecture option. If `inspect` finds several
   architectures for the top, ask which one, and pass only that
   architecture's file.
3. Pass the complete source set. Designs that span several VHDL libraries
   use `--libraries` (below).
4. The three report commands need a `vivado` executable; the other
   commands do not.
5. Resource synthesis is not timing closure. Label every timing number as
   a synthesis estimate or a routed result.
6. Project builds can run for hours. Run them in a background shell, and
   never start a second build in the same project.

Fallback: Yosys with the GHDL plugin by hand, or the project's
`build_fpga.py` and its generated report files.

### Multi-library designs

When the design under synthesis spans more than one VHDL library — e.g. a
top level using `library <name>; entity <name>.<entity>` to cross into a
sibling library, as produced by tsfpga's own per-module-folder convention
(`tsfpga.module.get_modules()`, see `shared/TsfpgaModules.md` §1) — pass
each library's files with `vhdl-tools synth synthesize --libraries
'{"<lib>": ["<file>", ...]}'` (one entry per library), not flattened into
`--sources`. Use `corvidex-mcp` to trace the full transitive dependency
closure first (own modules + any vendored dependency's modules) so no
library is missed; a design that only fails to *resolve* a cross-library
reference (GHDL: `cannot find resource library "..."` / `failed to find
library '...'`) rather than reporting a real syntax/semantic error is the
tell that a library was flattened into `sources` instead of given its own
`--libraries` entry.

### Backend-limitation workaround protocol

A synthesis failure is not automatically a `vhdl-tools` bug or a design
bug — it can be a genuine limitation of the underlying open-source GHDL/
Yosys backend hit by otherwise-correct, already-simulated-passing RTL
(e.g. GHDL's synth backend rejecting a dynamic-width slice construct that
GHDL's simulator accepts fine — a known, still-open GHDL issue). Before
assuming the RTL or the tool is wrong:

1. Isolate the exact failing construct/statement from the diagnostics
   (don't just retry blindly).
2. Check whether it matches a known upstream GHDL/Yosys issue (web search
   the exact error wording) rather than assuming it's project-specific.
3. If it is a genuine backend limitation and a workaround is warranted,
   apply it to a **local, synth-only scratch copy** of the affected
   file(s) only — never edit a vendored/reused module in place (per
   `shared/ReusableRTL.md`'s reuse-unmodified policy) without the user's
   explicit sign-off first.
4. Prove the scratch copy is behaviorally equivalent to the original
   (e.g. a standalone GHDL testbench comparing both across a
   representative input matrix) before trusting any resource count
   produced with it.
5. Record the workaround's scope and expiry condition (e.g. "drop once
   GHDL issue #NNNN is fixed, or once the vendored module is patched
   upstream") so it isn't mistaken for a permanent part of the design.

### 5. `speja` (optional)

[speja](https://github.com/ru551n/speja) formats VHDL and checks it, with
the VHDL Style Guide's rule set and a lint layer. It is not required: use it
when the project has a `speja.yaml` or `vsg.yaml`, or the user asks for it.
Check it is installed first (`speja --version`; `pip install speja`).

After writing or changing VHDL, over the files you touched:

| Command | Use |
|---|---|
| `speja --fix FILE...` | Lay the files out, and apply the safe rule fixes |
| `speja --check style,lint FILE...` | What is left; exit status 0 means no error |
| `speja --explain RULE` | What a rule id means |

Rules:
1. The project's own configuration wins. When the project has none and the
   user wants speja, copy `shared/speja.yaml` into the project root as
   `speja.yaml`, so the editor, the command line and CI agree; it encodes
   `shared/HouseStyle.md`'s layout.
2. Do not lay out by hand what speja will lay out: its next run would undo
   it. The conventions in `shared/HouseStyle.md` above its Layout part
   (naming, reset policy, architecture names) are still yours to follow.
3. speja finds a `speja.yaml` by itself, from each file's directory upwards.
   A project that configures it in a `vsg.yaml` instead needs `-c vsg.yaml`
   on every command.
4. speja does not change a file with a syntax error. Fix the syntax first.

Fallback: without speja, follow the Layout part of `shared/HouseStyle.md`
by hand.

## Recording the backend

Record which backend produced each result, for example
`backend: vhdl-tools vunit (ghdl)`, `backend: vhdl-tools synth (yosys)`,
`backend: vivado`, or `backend: run.py` for a fallback run.

## Evidence rule

No tool result means no claim.

Never claim:
- compile success
- test pass/fail
- waveform timing/value
- synthesis resource count
- Fmax/timing closure
- power result
- repository match

unless it came from an actual tool invocation or a user-provided artifact.

Absence of an error is not the same as evidence: a diagnostics tail can be
truncated (line-count-limited) and bury the actual root-cause error under
later, unrelated, benign warnings/notes (e.g. a tool repeating one note
per elaborated instance after the real fatal error already occurred).
Treat a failure message that looks suspiciously short, generic, or
templated as potentially truncated rather than accepting it as the full
root cause; prefer a tool/log view that surfaces every error-containing
line (not just a blind tail) when available.
