---
name: vhtestrun
description: Run VHDL regressions using vunit-mcp when available, collect reports/logs/waveforms, and create issue reports
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# VHDL Test Runner

Read `shared/ModernVHDL.md`, `shared/CodingStyle.md`, and `shared/HouseStyle.md`; they are authoritative for language revision, modern RTL practice, and concrete naming/style conventions.


Read `shared/McpToolPolicy.md`.

## Preferred backend — vunit-mcp

### 1. Status and discovery

Call:
1. `vunit_status`
2. `vunit_list_tests`

If a source-level compile check is needed first, use `vunit_compile`. If the
regression follows a recent RTL edit and a quick structural sanity check is
warranted before committing to a full run, use `vunit_elaborate` (recently
added) after `vunit_compile` — it performs a real GHDL elaboration pass and
catches cross-unit port/generic/type mismatches that analyze-only
`vunit_compile` can miss, without the cost of simulating any test.

### 2. Run tests

Use `vunit_run_tests` with `waveform_format` (`vcd` on GHDL, `fst` on NVC) so failing tests can be diagnosed at signal level.

**Parallelism.** Always pass `num_threads=0` (VUnit's `-p 0` / `--num-threads 0`, "use all logical CPUs") unless debugging a single test interactively — this speeds up GHDL regressions substantially (GHDL's per-test elaborate+simulate startup cost dominates at the default `-p 1`/sequential setting). Applies to every `vunit_run_tests` call, not just full regressions.

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
   has no `--simulator` flag; pass `-p0` (`run.py -p0 ...`) for the same
   all-CPU parallelism as `num_threads=0` above
2. use standalone GHDL only for a non-VUnit project

For standalone tests, process exit status plus the final `[FINISH] PASS/FAIL` token determine verdict.

Never fabricate a regression result.

## Re-verify after deliberately breaking something

Deliberately breaking the design to confirm a new test actually fails
without the fix is good practice — a guard never seen to fail is not known
to guard anything. But it leaves the tree in a knowingly-broken state, so
it must be bracketed: restore the fix, then re-run the full suite, and only
then report completion. Real case: a fix was reverted to confirm a guard
test caught its absence, and never restored; the work was reported
complete and green, but a real run showed 98 of 190 Python tests failing.
The narrative and the tool output disagreed, and only the tool output was
true. Never report a state that has not just been measured — this applies
with particular force across a session/agent handoff, where a summary is
all that survives and cannot be trusted over a real run.
