---
name: vhflow
description: Scan and orchestrate the complete MCP-first VHDL RTL design flow
allowed-tools: Read, Write, Bash, Grep, Glob
---

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
| Synthesis | `yosynth-mcp` | local Yosys+GHDL |

## Availability probing

Do not guess availability from documentation.

If exposed in the current host:
- `vhdl-rag-mcp`: call `repository_status` when retrieval is needed
- `vunit-mcp`: call `vunit_status`
- `yosynth-mcp`: call `yosynth_status`
- `waver-mcp`: call `waver_open` only after a waveform path exists

If an MCP server is not exposed, use fallback without treating that as a project failure.

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
