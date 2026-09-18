---
name: vhdebug
description: Use when a VHDL simulation or VUnit test fails, hangs, hits its watchdog, or produces wrong output and the cause is not yet known — a failing check or assertion, a mismatch against a reference model, X or U values, or a waveform that needs explaining. Typical requests include "why does this test fail", "debug this", "the output is wrong", "find the root cause".
---

# VHDL Debugging

## Before you start

- `shared/` means the `shared/` folder next to this skill's folder (`../shared/`). Those docs are large: run `grep -n '^#' shared/<Doc>.md` and read only the sections the task touches.
- The project's own conventions win. If the repository has a style guide, CLAUDE.md/AGENTS.md rules, or existing modules to copy, follow them over `shared/HouseStyle.md`.
- Flow files are optional. If `ddoc/`, `*_req.md`, `*_proposal.md`, `issue/` or `flow_status.md` exist, use and update them. Otherwise work from the request and the source files, report in the reply, and create flow files only when the user asks or `vhflow` is driving.
- Tools: `vhdl-tools` (`shared/bin/vhdl-tools`) for VUnit results and waveforms, and `corvidex-mcp` when connected; `shared/ToolPolicy.md` has the commands and fallbacks. Never report a result that no tool produced.

## References by topic

- Checker or cleanup behavior at end of test (phases, gate locks): `shared/Vunit.md` section 8
- Verification component behavior (blocking versus non-blocking calls, `stall_config`, draining before cleanup): `shared/Vunit.md` section 13
- Failures that cross clock domains: `shared/CdcPolicy.md`
- Waveform commands: `shared/ToolPolicy.md`, `vhdl-tools wave` section

## Rule

Diagnose only. Do not modify RTL unless the user explicitly asks for a fix after diagnosis.

## Preferred evidence pipeline

### 1. Test evidence — `vhdl-tools vunit`

1. `vhdl-tools vunit get-report --only-failing`
2. `vhdl-tools vunit get-test-log --test-name <test>` for the failing test
3. `vhdl-tools vunit get-test-waveform --test-name <test>` if a waveform was recorded

If no waveform was recorded and signal-level evidence is needed, re-run only the failing test: `vhdl-tools vunit run-tests --test-patterns '<test>' --waveform-format vcd` on GHDL, or `--waveform-format fst` on NVC. A run without `--waveform-format` records nothing.

A test that passes suspiciously fast, or whose `simulation stopped @` time is near zero, may not have tested anything: check that its verification components were drained before cleanup (`shared/Vunit.md` section 13).

### 2. Waveform evidence — `vhdl-tools wave`

Given the waveform path (`--file <path>`):
1. `vhdl-tools wave open`
2. `vhdl-tools wave search --pattern <name>` for exact hierarchical signal names
3. focus on the window around the failing check's simulation time
4. use:
   - `value-at --time <t> --signals ...` for exact values at a timestamp
   - `values --signal <s> --start <t> --end <t>` for transitions in a small window
   - `find --signal <s> --value <v>` for state or value occupancy
   - `latency --a <s> --b <s>` for event-to-event cycle or time relationships
   - `analyze --signal <s>` for clocks, pulses, X/Z and distributions
   - `plot --signals ... --out <file>.png` only when a picture adds something

### 3. Source/context evidence — corvidex-mcp

When available:
- `search_hdl` for driving logic and symbol references (conceptual discovery — "what drives this kind of signal")
- `search_docs` / `search_knowledge` for intended behavior/conventions
- `get_source` for exact source before concluding root cause
- once the suspect signal/generic/port name is known, prefer `find_definition`/`find_references` (LSP/compiler-backed exact resolution) over `search_hdl` or grep to trace every declaration and usage precisely — e.g. tracing a signal backward through entity boundaries or confirming every instantiation site of a generic implicated in a mismatch
- a "does this signal exist / is it driven anywhere" concept search that comes back empty is not conclusive — cross-check with `find_symbol` before ruling it out (see `shared/ToolPolicy.md`'s known retrieval weaknesses)

Fall back to local Read/Grep when unavailable.

A suspected generic-map or port mismatch can be confirmed before a full
source trace with `vhdl-tools vunit elaborate --test-patterns '<test>'`.
Elaboration binds entities and resolves generics, so it reports
mismatches between units that `compile` (analyze only) misses, even when
the original regression compiled cleanly.

## Trace method

Identify:
- first incorrect observable
- expected cycle/value
- actual cycle/value

Trace backwards through:
- output assignment/process
- state/register driving it
- combinational decisions
- entity boundaries
- package functions/types

Pay special attention to:
- `downto`/`to` range direction
- signed/unsigned conversion
- resize/truncation
- signal vs variable update semantics
- incomplete combinational assignments
- delta-cycle assumptions, including testbench checks that read a signal before the assigning process has suspended
- reset polarity/synchrony
- generic map mismatches
- off-by-one range/counter errors
- multiple drivers

## Root-cause classification

- RTL implementation
- design/proposal
- architecture/integration
- testcase/BFM
- requirement ambiguity
- tool/configuration

## Output

Report in the reply:
- evidence sources and backends
- failing check or log evidence
- waveform measurements when available
- source trace
- root cause and confidence
- unresolved uncertainty
- remediation ideas, clearly separated from the proven diagnosis

When flow files are in use (`issue/` exists, or `vhflow` is driving), also write the same content to `issue/<ip>/debug_NNN_<name>.md`; batch runs update `debug_summary.md`.

## CDC debugging caution

When a failure crosses clock domains, do not assume a functional RTL bug first.

Check:
- clock relationships
- CDC module choice
- missing/incorrect constraints
- reset release behavior
- event rate assumptions
- FIFO/handshake fullness or acknowledgment
- synthesis attributes and implementation warnings

Escalate uncertain/custom CDC structures explicitly.
