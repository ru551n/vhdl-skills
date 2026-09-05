---
name: vhtestrun
description: Run VHDL regressions using vunit-mcp when available, collect reports/logs/waveforms, and create issue reports
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# VHDL Test Runner

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## Preferred backend — vunit-mcp

### 1. Status and discovery

Call:
1. `vunit_status`
2. `vunit_list_tests`

If a source-level compile check is needed first, use `vunit_compile`.

### 2. Run tests

Use `vunit_run_tests` with `waveform_format` (`vcd` on GHDL, `fst` on NVC) so failing tests can be diagnosed at signal level.

Prefer the smallest requested test pattern; use full regression only when required.

If the run is expected to be green and no debug is planned, `waveform_format` may be omitted to save compile/sim time.

**Simulator selection.** VUnit 5 has no `--simulator` CLI flag — the
simulator is chosen via the `VUNIT_SIMULATOR` environment variable
(vunit-mcp exposes it as the `VUNIT_MCP_SIMULATOR` env var and the
per-call `simulator` parameter of `vunit_run_tests`/`vunit_compile`).
Prefer **nvc** for speed (~0.1 s per test vs 1–5 s on GHDL 7.0 on this
stack); use GHDL when its tooling is required.

**Waveform format.** Prefer `fst` (NVC) for debug runs: GHDL's `--wave`
VCD dump includes every signal of every compiled package — multi-hundred-MB
VCDs for a 100 ms simulation have been observed. When VCD on GHDL is
required, keep the simulated window short.

### 3. Read result

Use `vunit_get_report`.

For every failing test, use `vunit_get_test_log`.

When waveform debug is useful:
1. `vunit_get_test_waveform`
2. pass returned path to `peeper-mcp`

### 4. Report

Write `issue/<ip>/run_summary.md`.

For each failing test write `issue/<ip>/issue_NNN_<name>.md` with:
- exact VUnit test name
- backend
- pass/fail
- failing check count if available
- first useful failure/log excerpt
- simulation time when known
- waveform path when recorded
- reproduction test pattern

Do not claim root cause unless directly obvious; `vhdebug` owns diagnosis.

## Fallback order

If `vunit-mcp` is unavailable:
1. run the project's VUnit `run.py` directly — select the simulator with
   the `VUNIT_SIMULATOR` env var (`VUNIT_SIMULATOR=nvc run.py ...`); VUnit 5
   has no `--simulator` flag
2. use standalone GHDL only for a non-VUnit project

For standalone tests, process exit status plus the final `[FINISH] PASS/FAIL` token determine verdict.

Never fabricate a regression result.
