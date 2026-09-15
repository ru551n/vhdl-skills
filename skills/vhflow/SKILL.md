---
name: vhflow
description: Use when taking a whole VHDL IP through design, implementation, verification, synthesis and documentation across several modules, or when resuming or checking the status of such multi-phase work recorded in flow_status.md. Typical requests include "build this IP end to end", "run the full flow", "where are we in the flow", "continue the flow".
---

# VHDL Flow Orchestrator

## Before you start

- `shared/` means the `shared/` folder next to this skill's folder (`../shared/`). Those docs are large: run `grep -n '^#' shared/<Doc>.md` and read only the sections the task touches.
- The project's own conventions win. If the repository has a style guide, CLAUDE.md/AGENTS.md rules, or existing modules to copy, follow them over `shared/HouseStyle.md`.
- This skill owns `flow_status.md` and the flow files (`ddoc/`, `doc/`, `issue/`, `synth/`); create them as the phases run. Follow the project's existing layout when it differs from the conventional one.
- Tools: `vhdl-tools` (`shared/bin/vhdl-tools`) for VUnit, synthesis, Vivado reports and waveforms, and `corvidex-mcp` when connected; `shared/ToolPolicy.md` has the commands and fallbacks. Never report a compile, test, synthesis or timing result that no tool produced.

## Purpose

Inspect the project, check which tools work, and maintain a resumable `flow_status.md`.

## Tools by phase

| Phase | Tool | Fallback |
|---|---|---|
| Architecture, design, docs | `corvidex-mcp` search and navigation (routing in `shared/ToolPolicy.md`) | Read/Grep |
| Compile and test | `vhdl-tools vunit compile`, `elaborate` (after every interface change), `run-tests` | the project's `run.py`, GHDL |
| Waveform debug | `vhdl-tools wave` | GTKWave |
| Synthesis | `vhdl-tools synth synthesize`; `project-build` and the report commands for Vivado | Yosys by hand, `build_fpga.py` |

## Phases

1. Architecture — `vhdesign`
2. Module design — `vhdesign`
3. Per-module TDD loop (`vhtest` → `vhfill`, repeated per module) —
   per `shared/Vunit.md` §16, generate the module's unit testbench from
   its `<module>_req.md` first (red), then implement with `vhfill` until
   that same testbench passes (green). `vhtest` and `vhfill` alternate
   per module here; they are not two separate whole-project passes.
   Once a module goes green, run `vhsynth`'s per-module smoke check
   (`--chip generic` synthesis of that module alone) before moving to the
   next module — see `vhsynth`'s "Per-module smoke check" section. Do not
   defer this to phase 7; it is part of the per-module loop.
4. IP-level test generation — `vhtest`, integration test(s) across
   already-green modules (e.g. a full-pipeline golden-model comparison)
5. Regression — `vhtest`
6. Debug loop — `vhdebug` → requested fix via `vhfill` → `vhtest`
7. Synthesis — `vhsynth`
8. Documentation — `vhdoc`

## Optional variant: stub-first top-level integration

An alternative to phases 3-4's default bottom-up order, for a team that
wants early architecture-level validation across submodule boundaries
before every leaf module is green: build the real top-level entity
first, against behavioral stand-ins (`architecture model`) for
not-yet-built submodules, and replace them with real RTL one at a time.
Full write-up, when it's a good fit, and when it isn't: `shared/Vunit.md`
§"Stub-first top-level integration testing". Does not replace the
default per-module TDD loop in phase 3 above — it changes when true
top-level integration testing (phase 4) starts, not whether phase 3
still happens per module.

## Checking tools

Check each tool before the first phase that needs it, not from documentation:
- `vhdl-tools vunit status` and `vhdl-tools synth status`
- `vhdl-tools wave open --file <path>`, once a waveform exists
- corvidex `repository_status`, when retrieval is needed and it is connected

A missing tool means using its fallback, not a project failure. Record it in `flow_status.md`.

## Subagent delegation

Delegate only when the host provides a subagent/task tool; otherwise run phases inline.

Delegate self-contained phases:
- `vhfill` for one module
- `vhtest` for one module/IP test project
- `vhsynth` for one module
- `vhdoc` for the IP doc

Delegate independent modules in parallel only for work that neither builds nor simulates. Only one agent may compile, simulate or synthesize in a shared working tree at a time: separate output directories are not isolation, because every build reads the same, possibly half-edited, sources. Give each concurrent builder its own git worktree, or serialize.

Each delegation prompt must contain:
- IP and module name
- the phase and its completion criteria from below
- input paths to read (`ddoc/...`, `rtl/...`, current `flow_status.md`)
- the expected outputs and the `backend:` record per tool phase
- the instruction to use real tools per `shared/ToolPolicy.md`

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
- tool availability and health
- actual backend used per completed tool phase
- blockers
- latest real verification/synthesis results
- stale downstream artifacts
- next recommended action

Statuses:
`PENDING / IN PROGRESS / COMPLETE / BLOCKED / FAILED`

Never infer successful tool phases merely from files existing.
