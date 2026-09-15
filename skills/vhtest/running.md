# VHDL Test Runner

## Preferred backend — `vhdl-tools vunit`

### 1. Status and discovery

1. `vhdl-tools vunit status`
2. `vhdl-tools vunit list-tests`

For a compile-only check, run `vhdl-tools vunit compile`. After an RTL or
interface edit, `vhdl-tools vunit elaborate --test-patterns '<pattern>'`
catches port, generic and type mismatches between units that analyze-only
compilation misses, without simulating anything.

### 2. Run tests

`vhdl-tools vunit run-tests --test-patterns '<pattern>' --num-threads 0`

- **Parallelism.** `--num-threads 0` uses every logical CPU. GHDL's per-test elaborate-and-start cost dominates at the default of one thread, so always pass it unless debugging one test interactively.
- **Scope.** Run the smallest pattern that answers the question; run full regressions only when required.
- **Waveforms.** Add `--waveform-format vcd` (GHDL) or `--waveform-format fst` (NVC) so a failing test can be diagnosed at signal level. Skip it when the run is expected to be green and no debugging is planned.
- **Simulator.** VUnit 5 has no `--simulator` flag of its own; it reads `VUNIT_SIMULATOR`. `vhdl-tools vunit run-tests --simulator nvc` sets it for one call, and `VUNIT_MCP_SIMULATOR` sets it for every call. Pass it whenever more than one simulator is on `PATH`. Prefer NVC for speed (about 0.1 s per test against 1-5 s on GHDL 7.0); use GHDL when its tooling is required.
- **Waveform size.** Prefer FST on NVC for debug runs. GHDL's VCD dump includes every signal of every compiled package, and multi-hundred-MB files for 100 ms of simulated time have been observed; keep the simulated window short on GHDL.

### 3. Read results

1. `vhdl-tools vunit get-report --only-failing`
2. `vhdl-tools vunit get-test-log --test-name <test>` for every failing test
3. For signal-level debugging, `vhdl-tools vunit get-test-waveform --test-name <test>`, then pass the path to `vhdl-tools wave`

### 4. Report

For each failing test, report:
- exact VUnit test name
- backend
- pass/fail
- failing check count if available
- first useful failure/log excerpt
- simulation time when known
- waveform path when recorded
- reproduction test pattern

Put this in the reply. When flow files are in use (`issue/` exists, or `vhflow` is driving), also write `issue/<ip>/run_summary.md` and one `issue/<ip>/issue_NNN_<name>.md` per failing test.

Do not claim a root cause unless it is directly obvious; `vhdebug` owns diagnosis.

## Fallback order

If `vhdl-tools` cannot run (no `uv`, or a project it cannot drive):
1. run the project's VUnit `run.py` directly — select the simulator with
   the `VUNIT_SIMULATOR` env var (`VUNIT_SIMULATOR=nvc python run.py ...`),
   and pass `-p 0` for all-CPU parallelism
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
