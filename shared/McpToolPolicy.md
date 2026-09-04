# MCP Tool Policy

## Principle

The VHDL flow is **MCP-first, local-tool fallback**.

When an MCP server/tool is available in the current agent environment, prefer it for the task it was designed to perform.
If it is unavailable, misconfigured, or cannot perform the requested operation, fall back to the local alternative listed below.

This is not a soft preference: reaching for local `grep`/`find` on a repository
that `vhdl-rag-mcp` already has configured/indexed is a policy violation, not
a stylistic choice, even when it "would also work". See the `vhdl-rag-mcp`
section below for the exact boundary of what still legitimately falls back
to local tools.

Never invent MCP availability or tool results. If the host exposes no corresponding MCP tool, treat it as unavailable.

## Preferred servers

### 1. `vhdl-rag-mcp`

Repository:
`https://github.com/ru551n/vhdl-rag-mcp`

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
- `search_vhdl`
- `search_docs`
- `search_code`
- `search_knowledge`
- `get_source`
- `sync_repositories`
- `reindex_repository`

Usage rule:
1. Call `repository_status` when repository/index health matters.
2. Search at topic granularity, not module granularity and not item
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
3. Use `get_source` for exact source before copying or relying on an implementation detail.
4. Do not assume indexed material is current if status reports sync/index errors.

**ALWAYS prefer `vhdl-rag-mcp` over local `grep`/`find`/`git grep` for any code,
docs, or knowledge that lives in a repository the server has configured/indexed**
(check `repository_status` for the configured repository list). This applies
even when the local checkout is also present on disk and grep "would work" —
searching it locally anyway is exactly the anti-pattern this policy exists to
prevent: it bypasses the semantic index, skips commit attribution, and
duplicates work the MCP server already does better. Reach for local
`Read`/`Glob`/`Grep` only for:
- material the server does not index at all for this project (e.g. Python
  build/config scripts like `run.py`/`module_*.py`, non-HDL project files),
- the current in-progress, uncommitted working tree of the project actively
  being authored (not yet sync-able into the index),
- confirmed server unavailability/unhealth (per the Availability decision
  below) or a `repository_status` sync error for the repository in question.
When in doubt whether something is covered, call `repository_status`/
`search_hdl`/`search_docs`/`search_code`/`search_knowledge` first rather than
defaulting to grep.

Fallback (only per the exclusions above):
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
7. Use `vunit_get_test_waveform` to obtain the waveform path and pass it to `waver-mcp`.

Fallback:
1. Project `run.py` directly, using VUnit.
2. GHDL (`ghdl -a/-e/-r`) for simple non-VUnit unit tests.
3. NVC if the project is already configured for it.

Do not silently replace an existing VUnit project with a custom GHDL harness.

### 3. `waver-mcp`

Repository:
`https://github.com/ru551n/waver-mcp`

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
- `waver_open` — call first for a new waveform
- `waver_search`
- `waver_values`
- `waver_value_at`
- `waver_analyze`
- `waver_latency`
- `waver_find`
- `waver_plot`

Usage rule:
1. Obtain a waveform path, preferably through `vunit_get_test_waveform`.
2. Call `waver_open`.
3. Locate exact signal names with `waver_search`.
4. Query the smallest useful time window around the failure.
5. Use measured values/latencies in debug reports.
6. Use `waver_plot` only when visual inspection materially helps.

Fallback:
- GTKWave for manual inspection
- `ghdl --read-wave-opt`/wave dump tooling if available
- Python/VCD parsing only when no suitable waveform tool exists

Do not parse huge waveforms manually if Waver is available.

### 4. `tsfpga-mcp`

Repository:
`https://github.com/ru551n/tsfpga-mcp`

Preferred for:
- VHDL/Verilog hierarchy/source inspection before synthesis
- supported synthesis-target discovery (which chips/flows the installed Yosys provides)
- synthesis through `tsfpga.yosys.project` (GHDL + Yosys)
- aggregated resource-count summaries (no per-port netlist)

Relevant tools when exposed:
- `tsfpga_status`
- `tsfpga_targets`
- `tsfpga_inspect`
- `tsfpga_synthesize`

Usage rule:
1. Call `tsfpga_status` first.
2. Use `tsfpga_inspect` when top/generics are uncertain, or multiple architectures may exist.
3. Use `tsfpga_targets` before choosing a chip/family unless the user already supplied it.
4. Never infer required top level, chip/family, or generic overrides.
5. There is no architecture-selection parameter. If `tsfpga_inspect` reports more than one architecture for the top, ask the user which one, then include only that architecture's source file in the source set passed to `tsfpga_synthesize`.
6. Pass the complete source dependency set to `tsfpga_synthesize`; when `top` is not a VHDL entity, also pass the VHDL entity names it instantiates via `vhdl_entities`.

Fallback:
Yosys + GHDL plugin locally for generic/open-source synthesis.

`tsfpga-mcp` provides synthesis/resource reporting, not a substitute for vendor place-and-route timing or vendor power analysis.

## Tool argument conventions

- `vunit-mcp` tools that take arguments wrap them in a top-level `input` object, e.g. `vunit_get_test_log` with `{"input": {"test_name": "..."}}`.
- `tsfpga-mcp` `tsfpga_synthesize`/`tsfpga_inspect` take an `input` object with `sources` (required), `top`, `chip`, `family`, `vhdl_entities`, `generics`, `vhdl_standard`, `discard_ffinit`.
- `vhdl-rag-mcp` and `waver-mcp` take flat arguments (e.g. `waver_open` with `{"file": "..."}`).

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
