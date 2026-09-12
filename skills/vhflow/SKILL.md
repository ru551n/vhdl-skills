---
name: vhflow
description: Scan and orchestrate the complete MCP-first VHDL RTL design flow
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.
> **Layout note:** `ddoc/`, `rtl/`, `doc/`, `lib/` are the conventional tsfpga layout. When the project uses a different layout (e.g. `modules/<name>/{src,test,doc}`), follow the project's layout and keep the same file-naming conventions (`<ip>_arch.md`, `<module>_req.md`, `<module>.md`, `<module>.vhd`).

# VHDL Flow Orchestrator

Read `shared/ModernVHDL.md`, `shared/CodingStyle.md`, and `shared/HouseStyle.md`; they are authoritative for language revision, modern RTL practice, and concrete naming/style conventions.


Read `shared/McpToolPolicy.md`.

## Purpose

Inspect the project, detect available MCP backends, and maintain a resumable `flow_status.md`.

## General principle: MCP-first, local-tool fallback

Every phase below has a corresponding MCP server that is strictly preferred
over the equivalent manual/local approach whenever it is exposed in the
current host (`shared/McpToolPolicy.md` is authoritative; this is a
summary for the orchestrator):

- **`corvidex-mcp`** — semantic search and exact code/doc navigation. Route
  by question type, not by habit — see `shared/McpToolPolicy.md`'s
  cost-aware routing table: `search_hdl`/`search_knowledge` for conceptual
  discovery (grep genuinely cannot do this); `find_definition`/
  `find_references`/`find_symbol`/`hover_info` (exact, LSP/compiler-backed)
  once the exact symbol name/location is already known — far cheaper than a
  `search_hdl` guess; local `grep`/`find` for exhaustive literal-string
  enumeration or material outside the index. A thin/empty concept-search
  result is not proof something doesn't exist — cross-check with
  `find_symbol` first.
- **`vunit-mcp`** — VUnit project discovery, compile, elaborate, run,
  report/log/waveform retrieval. Prefer it over manually invoking
  `ghdl`/`run.py` via `bash` or manually grepping VUnit logs. Use
  `vunit_elaborate` liberally right after RTL is written or edited — it is
  a real GHDL elaboration pass that catches cross-unit port/generic/type
  mismatches `vunit_compile` (analyze-only) cannot, and is cheap because it
  does not simulate anything.
- **`tsfpga-mcp`** — portable Yosys+GHDL synthesis/resource summaries and
  real per-project Vivado builds. Prefer it over manually shelling out to
  `yosys`/`ghdl`/`build_fpga.py` or manually reading generated report
  files. Use `tsfpga_hierarchy` instead of a full `tsfpga_synthesize` run
  when the question is about instance hierarchy/generic resolution rather
  than resource counts — it is far cheaper.
- **`peeper-mcp`** — waveform inspection. Prefer it over manually parsing
  VCD/FST files or eyeballing a waveform viewer when the question is about
  signal timing/values/clock period/latency.

## Phases

1. Architecture — `vharch`
2. Module design — `vhdesign`
3. Per-module TDD loop (`vhtestgen` → `vhfill`, repeated per module) —
   per `shared/Vunit.md` §15, generate the module's unit testbench from
   its `<module>_req.md` first (red), then implement with `vhfill` until
   that same testbench passes (green). `vhtestgen` and `vhfill` alternate
   per module here; they are not two separate whole-project passes.
   Once a module goes green, run `vhsynth`'s per-module smoke check
   (`chip=generic` synthesis of that module alone) before moving to the
   next module — see `vhsynth`'s "Per-module smoke check" section. Do not
   defer this to phase 7; it is part of the per-module loop.
4. IP-level test generation — `vhtestgen`, integration test(s) across
   already-green modules (e.g. a full-pipeline golden-model comparison)
5. Regression — `vhtestrun`
6. Debug loop — `vhdebug` → requested fix via `vhfill` → `vhtestrun`
7. Synthesis — `vhsynth`
8. Documentation — `vhdoc`

## Backend preference by phase

| Phase | Preferred MCP | Fallback |
|---|---|---|
| Architecture/design/docs | `corvidex-mcp` (`search_hdl`/`search_knowledge`, and `find_definition`/`find_references`/`find_symbol` for exact lookups) | Read/Grep |
| Compile/test | `vunit-mcp` (`vunit_compile` then `vunit_elaborate` before a full run) | VUnit run.py / GHDL |
| Waveform debug | `peeper-mcp` | GTKWave/manual |
| Synthesis | `tsfpga-mcp` (`tsfpga_hierarchy` for structure-only questions, `tsfpga_synthesize` for resource counts) | local Yosys+GHDL |

## Availability probing

Do not guess availability from documentation.

If exposed in the current host:
- `corvidex-mcp`: call `repository_status` when retrieval is needed
- `vunit-mcp`: call `vunit_status`
- `tsfpga-mcp`: call `tsfpga_status`
- `peeper-mcp`: call `peeper_open` only after a waveform path exists

If an MCP server is not exposed, use fallback without treating that as a project failure.

## Subagent delegation

Delegate only when the host provides a subagent/task tool; otherwise run phases inline.

Delegate self-contained phases:
- `vhfill` for one module
- `vhtestgen` for one module/IP test project
- `vhsynth` for one module
- `vhdoc` for the IP doc

Delegate independent modules in parallel. Never run two regressions against the same VUnit project at the same time (the vunit-mcp server serializes runs per project).

Each delegation prompt must contain:
- IP and module name
- the phase and its completion criteria from below
- input paths to read (`ddoc/...`, `rtl/...`, current `flow_status.md`)
- the expected outputs and the `backend:` record per tool phase
- the instruction to use real tools, MCP-first per `shared/McpToolPolicy.md`

Do not delegate:
- `flow_status.md` updates — the orchestrator verifies artifacts and records status
- cross-module or architecture decisions
- the debug loop while the failure is not yet localized

A subagent's summary is not evidence. Before marking a phase `COMPLETE`, verify the artifacts exist and the recorded tool results (reports, `backend:` lines) are real.

## Completion signals

Architecture:
- architecture doc, top skeleton and module requirement files exist

Design:
- proposal, doc and backbone exist

Implementation:
- no unresolved `--@`
- real compile/unit-test status recorded, or verification marked BLOCKED

Testing:
- tests are discoverable
- real regression report exists

Debug:
- each relevant failure has a debug report or explicit unresolved status

Synthesis:
- real synthesis report exists, with backend noted

Documentation:
- IP doc reflects the current design

## flow_status.md

Include:
- IP
- phase status
- affected modules
- MCP availability/health
- actual backend used per completed tool phase
- blockers
- latest real verification/synthesis results
- stale downstream artifacts
- next recommended action

Statuses:
`PENDING / IN PROGRESS / COMPLETE / BLOCKED / FAILED`

Never infer successful tool phases merely from files existing.
