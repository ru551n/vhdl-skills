# MCP Tool Policy

## Principle

The VHDL flow is **MCP-first, local-tool fallback**.

When an MCP server/tool is available in the current agent environment, prefer it for the task it was designed to perform.
If it is unavailable, misconfigured, or cannot perform the requested operation, fall back to the local alternative listed below.

For `corvidex-mcp` specifically, "prefer" is a routing decision, not a
blanket "always semantic search, never grep" rule: the right tool depends
on what the question actually is (an already-known exact identifier vs. a
concept/pattern vs. an exhaustive literal-string enumeration). See the
`corvidex-mcp` section below for the routing table, the measurements it is
based on, and the boundary of what still legitimately falls back to local
tools.

Never invent MCP availability or tool results. If the host exposes no corresponding MCP tool, treat it as unavailable.

## Preferred servers

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
habit or by "corvidex first, always". Measured on a real project (empirical
review, 2026-09-12): looking up a known identifier
(`cnn_accel_bias_requant`) cost 0.62 s / ~54.8 KB (~13,700 tokens) / 8
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
`vhdl-ai-test-582e8509`), not the plain directory name. Any call that takes
a `repository=` argument must read the real name from `repository_status`
first — guessing the plain directory name (e.g. `vhdl-ai-test`) fails with
an unknown-repository error.

Launcher trap: registering the server with `uv --directory DIR run ...`
changes the server process's working directory to `DIR`; for corvidex that
means it indexes its *own* source tree instead of the target project —
silently, with no error. Use `uv --project DIR run ...` instead (this does
not change the working directory), or set `CORVIDEX_MCP_PROJECT_DIR` when
the launcher command can't be edited. After setup, confirm with
`repository_status` that the indexed repository is the target project, not
`corvidex-mcp` itself.

Pending-PR-dependent behavior — do not describe these as current until the
named PR is confirmed merged:
- **Once upstream PR #31 lands** (compact search results): `search_hdl`/
  `search_docs`/`search_code`/`search_knowledge` results will carry 1-based
  line-number gutters, bodies capped to ~40 lines with a `get_source(...)`
  follow-up marker for anything longer, and a weak-match warning when
  relevance is low. The line numbers are what makes a search →
  `find_definition`/`find_references` handoff practical — but the
  navigation tools take 0-based line numbers, so pass (displayed line
  number − 1).
- **Once upstream PR #32 lands** (multi-library `vhdl_ls` config):
  library-qualified instantiations (`entity cnn_accel.foo`, tsfpga's
  per-module-folder convention) will resolve correctly in all four
  navigation tools. Before that fix, `find_definition`/`find_references`/
  `find_symbol`/`hover_info` silently return "No definition found" (or an
  equivalent empty result) on such references — treat an empty result on a
  library-qualified instantiation as suspect, not as proof the target
  doesn't exist, until that PR is confirmed merged.

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

### 2. `vunit-mcp`

Repository:
`https://github.com/ru551n/vunit-mcp`

Preferred for:
- discovering the VUnit project
- source compile order
- compiling
- listing tests
- running regressions
- reading JUnit-derived status
- reading individual test logs
- resolving testcase dependencies
- locating recorded test waveforms

Relevant tools when exposed:
- `vunit_status` — call first
- `vunit_list_tests`
- `vunit_list_files`
- `vunit_compile`
- `vunit_elaborate` — runs VUnit's `--elaborate` flag, a real GHDL
  elaboration pass
- `vunit_run_tests`
- `vunit_get_report`
- `vunit_get_test_log`
- `vunit_get_test_waveform`
- `vunit_test_dependencies`
- `vunit_export_json`

Usage rule:
1. Call `vunit_status` first.
2. Prefer `vunit_list_files` over manually guessing compile order.
3. Prefer `vunit_compile` over direct compiler commands when a VUnit project exists.
4. Prefer `vunit_run_tests` for regressions.
5. Pass `waveform_format` to `vunit_run_tests` when waveform debug may be required (`vcd` on GHDL, `fst` on NVC); a run without it records no waveform. Skip it only when the run is expected green and no debug is planned.
6. Use `vunit_get_report` before fetching detailed failure logs.
7. Use `vunit_get_test_waveform` to obtain the waveform path and pass it to `peeper-mcp`.
8. **Use `vunit_elaborate` liberally right after writing or modifying RTL**,
   as a validation step before a full `vunit_run_tests` is warranted.
   `vunit_compile` is analyze-only (GHDL `-a`/`--compile`) and can report
   clean success on code that still has a cross-unit port/generic/type
   mismatch — elaboration is what actually binds entities/architectures and
   resolves generics, so it catches that class of error `vunit_compile`
   silently misses. This is the closest free/open equivalent to a
   commercial compiler's incremental-validation feedback loop; do not skip
   straight from `vunit_compile` to a full test run when the goal is just
   "did this edit break anything structurally".

Fallback:
1. Project `run.py` directly, using VUnit.
2. GHDL (`ghdl -a/-e/-r`) for simple non-VUnit unit tests.
3. NVC if the project is already configured for it.

Do not silently replace an existing VUnit project with a custom GHDL harness.

### 3. `peeper-mcp`

Repository:
`https://github.com/ru551n/peeper-mcp`

Reads both FST (NVC's default) and VCD (GHDL's default) waveforms directly —
no conversion step is needed for waveforms recorded by `vunit-mcp`.

Preferred for:
- waveform inspection
- exact signal values at a time
- transition/value histories
- clock period/frequency/duty measurement
- X/Z detection
- event-to-event latency
- locating state/value intervals
- rendering waveform plots

Relevant tools when exposed:
- `peeper_open` — call first for a new waveform
- `peeper_search`
- `peeper_values`
- `peeper_value_at`
- `peeper_analyze`
- `peeper_latency`
- `peeper_find`
- `peeper_plot`

Usage rule:
1. Obtain a waveform path, preferably through `vunit_get_test_waveform`.
2. Call `peeper_open`.
3. Locate exact signal names with `peeper_search`.
4. Query the smallest useful time window around the failure.
5. Use measured values/latencies in debug reports.
6. Use `peeper_plot` only when visual inspection materially helps.

Fallback:
- GTKWave for manual inspection
- `ghdl --read-wave-opt`/wave dump tooling if available
- Python/VCD parsing only when no suitable waveform tool exists

Do not parse huge waveforms manually if Peeper is available.

### 4. `tsfpga-mcp`

Repository:
`https://github.com/ru551n/tsfpga-mcp`

Preferred for:
- VHDL/Verilog hierarchy/source inspection before synthesis
- supported synthesis-target discovery (which chips/flows the installed Yosys provides)
- synthesis through `tsfpga.yosys.project` (GHDL + Yosys)
- aggregated resource-count summaries (no per-port netlist)
- real per-project Vivado builds and their timing/utilization/DRC reports

Relevant tools when exposed:
- `tsfpga_status`
- `tsfpga_targets`
- `tsfpga_inspect`
- `tsfpga_hierarchy` — a GHDL-elaborated, generics-resolved
  instance/hierarchy tree (generate-block-expanded instance names, resolved
  generics) **without** running full technology-mapping synthesis
- `tsfpga_synthesize`
- `tsfpga_project_status`
- `tsfpga_project_list_builds`
- `tsfpga_project_build`
- `tsfpga_project_get_timing_report`
- `tsfpga_project_get_utilization_report`
- `tsfpga_project_get_drc_report`

Usage rule:
1. Call `tsfpga_status` first.
2. Use `tsfpga_inspect` when top/generics are uncertain, or multiple architectures may exist.
3. Use `tsfpga_targets` before choosing a chip/family unless the user already supplied it.
4. Never infer required top level, chip/family, or generic overrides.
5. There is no architecture-selection parameter. If `tsfpga_inspect` reports more than one architecture for the top, ask the user which one, then include only that architecture's source file in the source set passed to `tsfpga_synthesize`.
6. Pass the complete source dependency set to `tsfpga_synthesize`; when `top` is not a VHDL entity, also pass the VHDL entity names it instantiates via `vhdl_entities`.
7. **Prefer `tsfpga_hierarchy` over `tsfpga_synthesize` (or manually
   shelling out to `ghdl`/`yosys`) when the question is about design
   structure** — instance hierarchy, generate-block expansion, resolved
   generics — rather than resource counts. It is far cheaper than a full
   technology-mapping synthesis run because it stops at GHDL elaboration.
8. For real Vivado-project work (an actual tsfpga project's own
   `build_fpga.py`, not the portable Yosys flow), prefer
   `tsfpga_project_status`/`tsfpga_project_list_builds`/
   `tsfpga_project_build` over invoking Vivado/`build_fpga.py` manually via
   `bash`, and prefer `tsfpga_project_get_timing_report`/
   `tsfpga_project_get_utilization_report`/`tsfpga_project_get_drc_report`
   over manually grepping/opening the generated Vivado report files
   (`timing.rpt`, `utilization.rpt`, DRC report). See the `vivado-gotchas`
   skill for the underlying Vivado report/hook behaviors these tools read.

Fallback:
Yosys + GHDL plugin locally for generic/open-source synthesis; direct
Vivado/`build_fpga.py` invocation and manual report reading when
`tsfpga-mcp` project-mode tools are unavailable.

`tsfpga-mcp` provides synthesis/resource reporting, not a substitute for vendor place-and-route timing or vendor power analysis.

### Multi-library designs

When the design under synthesis spans more than one VHDL library — e.g. a
top level using `library <name>; entity <name>.<entity>` to cross into a
sibling library, as produced by tsfpga's own per-module-folder convention
(`tsfpga.module.get_modules()`, see `shared/TsfpgaModules.md` §1) — pass
each library's files under `tsfpga_synthesize`'s `libraries` parameter
(one dict entry per library, keyed by library name), not flattened into
`sources`. Use `corvidex-mcp` to trace the full transitive dependency
closure first (own modules + any vendored dependency's modules) so no
library is missed; a design that only fails to *resolve* a cross-library
reference (GHDL: `cannot find resource library "..."` / `failed to find
library '...'`) rather than reporting a real syntax/semantic error is the
tell that a library was flattened into `sources` instead of given its own
`libraries` entry.

### Backend-limitation workaround protocol

A synthesis failure is not automatically a `tsfpga-mcp` bug or a design
bug — it can be a genuine limitation of the underlying open-source GHDL/
Yosys backend hit by otherwise-correct, already-simulated-passing RTL
(e.g. GHDL's synth backend rejecting a dynamic-width slice construct that
GHDL's simulator accepts fine — a known, still-open GHDL issue). Before
assuming the RTL or the MCP tool is wrong:

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

## Tool argument conventions

- `vunit-mcp` tools that take arguments wrap them in a top-level `input` object, e.g. `vunit_get_test_log` with `{"input": {"test_name": "..."}}`.
- `tsfpga-mcp` `tsfpga_synthesize`/`tsfpga_inspect` take an `input` object with `sources`, `libraries`, `top`, `chip`, `family`, `vhdl_entities`, `generics`, `vhdl_standard`, `discard_ffinit`. At least one of `sources`/`libraries` is required; `libraries` is a `{library_name: [file, ...]}` map for designs spanning more than one VHDL library (see "Multi-library designs" above).
- `corvidex-mcp` and `peeper-mcp` take flat arguments (e.g. `peeper_open` with `{"file": "..."}`).

## Availability decision

For each phase:

1. If the corresponding MCP tools are exposed by the host, use them.
2. If a status tool exists, call it before substantive operations.
3. If the server is present but unhealthy, report the health issue and use fallback when appropriate.
4. If the MCP tool is not exposed at all, use fallback without repeatedly probing for it.
5. Record which backend produced a result:
   - `backend: vunit-mcp`
   - `backend: ghdl`
   - `backend: tsfpga-mcp`
   - etc.

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
