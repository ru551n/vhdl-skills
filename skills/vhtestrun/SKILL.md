---
name: vhtestrun
description: Run VHDL regressions using vunit-mcp when available, collect reports/logs/waveforms, and create issue reports
allowed-tools: Read, Write, Bash, Grep, Glob
---

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

Use `vunit_run_tests`.

Prefer the smallest requested test pattern; use full regression only when required.

When failures may require signal-level debug, request waveform recording in the run.

### 3. Read result

Use `vunit_get_report`.

For every failing test, use `vunit_get_test_log`.

When waveform debug is useful:
1. `vunit_get_test_waveform`
2. pass returned path to `waver-mcp`

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
1. run the project's VUnit `run.py` directly
2. use standalone GHDL only for a non-VUnit project

For standalone tests, process exit status plus the final `[FINISH] PASS/FAIL` token determine verdict.

Never fabricate a regression result.
