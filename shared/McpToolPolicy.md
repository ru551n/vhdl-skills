# MCP Tool Policy

## Principle

The VHDL flow is **MCP-first, local-tool fallback**.

When an MCP server/tool is available in the current agent environment, prefer it for the task it was designed to perform.
If it is unavailable, misconfigured, or cannot perform the requested operation, fall back to the local alternative listed below.

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
2. Search narrowly first.
3. Use `get_source` for exact source before copying or relying on an implementation detail.
4. Do not assume indexed material is current if status reports sync/index errors.

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
5. Ask for a waveform during the run when waveform-debug may be required.
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

### 4. `yosynth-mcp`

Repository:
`https://github.com/ru551n/yosynth-mcp`

Preferred for:
- VHDL hierarchy/source inspection before synthesis
- supported synthesis-target discovery
- synthesis through GHDL + Yosys
- concise top-port and resource summaries

Relevant tools when exposed:
- `yosynth_status`
- `yosynth_targets`
- `yosynth_inspect`
- `yosynth_synthesize`

Usage rule:
1. Call `yosynth_status` first.
2. Use `yosynth_inspect` when top/architecture/generics are uncertain.
3. Use `yosynth_targets` before choosing a chip/family unless the user already supplied it.
4. Never infer required top-level architecture, chip/family, or generic overrides.
5. Pass the complete source dependency set to `yosynth_synthesize`.

Fallback:
1. Vivado for Xilinx-specific synthesis/timing/power.
2. Yosys + GHDL plugin locally for generic/open-source synthesis.
3. Vendor tools for vendor-specific implementation requirements.

`yosynth-mcp` provides synthesis/resource reporting, not a substitute for vendor place-and-route timing or vendor power analysis.

## Availability decision

For each phase:

1. If the corresponding MCP tools are exposed by the host, use them.
2. If a status tool exists, call it before substantive operations.
3. If the server is present but unhealthy, report the health issue and use fallback when appropriate.
4. If the MCP tool is not exposed at all, use fallback without repeatedly probing for it.
5. Record which backend produced a result:
   - `backend: vunit-mcp`
   - `backend: ghdl`
   - `backend: yosynth-mcp`
   - `backend: vivado`
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
