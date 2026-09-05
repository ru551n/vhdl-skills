---
name: vhdebug
description: Diagnose VHDL regression failures using VUnit logs, waveform MCP analysis, and RAG-assisted source tracing
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# VHDL Debugger

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## Rule

Diagnose only. Do not modify RTL unless the user explicitly asks for a fix after diagnosis.

## Preferred evidence pipeline

### 1. Test evidence — vunit-mcp

When available:
1. `vunit_get_report`
2. `vunit_get_test_log` for the failing test
3. `vunit_get_test_waveform` if a waveform was recorded

If the prior run did not record a waveform and signal-level evidence is necessary, re-run the smallest failing test with `vunit_run_tests` and `waveform_format` (`vcd` on GHDL, `fst` on NVC) — runs without `waveform_format` record no waveform.

### 2. Waveform evidence — peeper-mcp

Given the waveform path:
1. `peeper_open`
2. `peeper_search` for exact hierarchical signal names
3. focus around the failing-check simulation time
4. use:
   - `peeper_value_at` for exact values at a timestamp
   - `peeper_values` for transitions in a small window
   - `peeper_find` for state/value occupancy
   - `peeper_latency` for event-to-event cycle/time relationships
   - `peeper_analyze` for clocks, pulses, X/Z and distributions
   - `peeper_plot` only when visual context adds value

### 3. Source/context evidence — vhdl-rag-mcp

When available:
- `search_vhdl` / `search_hdl` for driving logic and symbol references
- `search_docs` / `search_knowledge` for intended behavior/conventions
- `get_source` for exact source before concluding root cause

Fall back to local Read/Grep when unavailable.

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
- delta-cycle assumptions
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

Write `issue/<ip>/debug_NNN_<name>.md` with:
- evidence sources/backends
- failing check/log evidence
- waveform measurements when available
- source trace
- root cause and confidence
- unresolved uncertainty
- optional remediation ideas clearly separated from proven diagnosis

Batch runs update `debug_summary.md`.

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
