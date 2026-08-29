---
name: vhtestgen
description: Generate a VUnit-first self-checking VHDL-2008 test project, with standalone GHDL fallback
allowed-tools: Read, Write, Bash, Grep, Glob
---

# VHDL Test Generator

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/Vunit.md` (VUnit-5 API: runner, phases, gate locks, checks, seeds, verification components) and `shared/McpToolPolicy.md`.

## Preferred verification architecture

If the project uses VUnit (a VUnit `run.py` exists, or `vunit_status`/`vunit_list_tests` succeed), always generate VUnit testbenches — never standalone ones. Authoring rules for generated runners/testbenches come from `shared/Vunit.md` (see the `vhunit` skill).

Infer the project's test conventions from the existing project:
- `run.py` registration style (VUnit-5 builtins, library dependencies)
- existing testbench structure under `tb/`
- test case naming, check style, and shared helpers
- simulator and output settings

If the conventions cannot be inferred (no existing tests to copy from, ambiguous or mixed structure, missing or broken `run.py`), ask the user which conventions to follow. Do not guess and do not invent a new structure silently.

If `vunit-mcp` is available:
1. call `vunit_status`
2. inspect project with `vunit_export_json`, `vunit_list_tests`, and `vunit_list_files`
3. preserve the existing `run.py` conventions
4. add tests in the same project style
5. validate discovery with `vunit_list_tests`

If VUnit is not present in the project, a standalone GHDL testbench may be generated instead (see Fallback standalone tests).

## Inputs

Use:
- `ddoc/<ip>_arch.md`
- module/IP docs
- top entity
- requirements
- register/protocol docs
- relevant precedent from `vhdl-rag-mcp` when available

## Recommended VUnit structure

```text
run.py
tb/
├── tb_<ip>.vhd
├── tb_pkg.vhd
└── ...
```

Project-specific structures may differ; follow the existing VUnit project.

## VUnit testbench rules

Authoring is delegated to `shared/Vunit.md` (authoritative VUnit-5 API) and
the `vhunit` skill: VHDL-2008, `vunit_context` + `runner_cfg`, named
`run("test_*")` cases, self-checking via `check_pkg`, a watchdog with a real
budget, seeded RNG, `run.py` in the VUnit-5 style with
`add_vhdl_builtins()`, and checker processes that respect the test phases
(gate locks / `runner_phase` events per `shared/Vunit.md` §7).

The testbench skeleton, `check_pkg` reference, randomization/queue/VC
references, and VUnit 4 vs 5 deltas live in `shared/Vunit.md` — do not
duplicate them here.

## Test plan

Cover:
- reset/default state
- nominal flow
- legal min/max values
- handshake/backpressure
- boundary/wrap/saturation
- specified error cases
- latency/pipeline behavior
- register access where present
- concurrent interface behavior where relevant

Maintain `tb/<ip>/tc_list.md` if the project uses that artifact, mapping test names to requirements.

## Waveform readiness

For tests likely to need signal-level debug, design them so `vunit_run_tests` can be invoked with waveform recording. Waveform files are consumed by `waver-mcp`.

## Fallback standalone tests

Only when the project does not use VUnit, or the user explicitly requests standalone tests:
- generate standalone VHDL-2008 TB
- use assertions
- emit exactly one `[FINISH] PASS` or `[FINISH] FAIL`
- terminate via `std.env.finish`


## Modern verification rules

- Prefer independent named VUnit testcases.
- Use deterministic tests by default.
- For randomized tests, record/report the seed and make failure reproducible.
- Prefer scoreboards/reference models over checking implementation-internal signals.
- Test protocol invariants: stability under stall, ordering, no loss/duplication.
- Test reset during relevant traffic/state when allowed by the requirement.
- Test min/max/boundary generic configurations when practical.
- Add functional coverage only when it has a clear requirement mapping.
- Preserve existing OSVVM/UVVM infrastructure rather than replacing it.
- Generate waveforms for diagnosis, not as the primary pass/fail mechanism.

## CDC verification tests

When CDC logic is present:
- vary source/destination clock periods and relative phases
- exercise reset sequencing in both domains
- stress back-to-back events/transactions
- test FIFO overflow/underflow protections where relevant
- use assertions/checkers for handshake/data-stability assumptions

Simulation complements but does not replace static CDC/timing analysis.

## Generic configuration coverage

Exercise representative generic configurations: minimum valid, default/common,
boundary values, and enabled/disabled feature variants where applicable.
