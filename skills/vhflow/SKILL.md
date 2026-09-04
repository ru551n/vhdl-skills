---
name: vhflow
description: Scan and orchestrate the complete MCP-first VHDL RTL design flow
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.
> **Layout note:** `ddoc/`, `rtl/`, `doc/`, `lib/` are the conventional tsfpga layout. When the project uses a different layout (e.g. `modules/<name>/{src,test,doc}`), follow the project's layout and keep the same file-naming conventions (`<ip>_arch.md`, `<module>_req.md`, `<module>.md`, `<module>.vhd`).

# VHDL Flow Orchestrator

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## Purpose

Inspect the project, detect available MCP backends, and maintain a resumable `flow_status.md`.

## Phases

1. Architecture — `vharch`
2. Module design — `vhdesign`
3. Implementation/unit verification — `vhfill`
4. IP test generation — `vhtestgen`
5. Regression — `vhtestrun`
6. Debug loop — `vhdebug` → requested fix via `vhfill` → `vhtestrun`
7. Synthesis — `vhsynth`
8. Documentation — `vhdoc`

## Backend preference by phase

| Phase | Preferred MCP | Fallback |
|---|---|---|
| Architecture/design/docs | `vhdl-rag-mcp` | Read/Grep |
| Compile/test | `vunit-mcp` | VUnit run.py / GHDL |
| Waveform debug | `waver-mcp` | GTKWave/manual |
| Synthesis | `tsfpga-mcp` | local Yosys+GHDL |

## Availability probing

Do not guess availability from documentation.

If exposed in the current host:
- `vhdl-rag-mcp`: call `repository_status` when retrieval is needed
- `vunit-mcp`: call `vunit_status`
- `tsfpga-mcp`: call `tsfpga_status`
- `waver-mcp`: call `waver_open` only after a waveform path exists

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
