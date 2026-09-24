---
name: vhtest
description: Use when writing, extending, repairing or running VHDL testbenches and VUnit projects — new test cases, run.py setup, verification components or BFMs, backpressure and randomized tests, Python reference models, VUnit 4 to 5 migration, or running a regression on GHDL or NVC. Typical requests include "add a test for...", "write a testbench", "run the tests", "set up VUnit", "VUnit doesn't find my test".
---

# VHDL Testing

## Before you start

- `shared/` means the `shared/` folder next to this skill's folder (`../shared/`). Those docs are large: run `grep -n '^#' shared/<Doc>.md` and read only the sections the task touches.
- The project's own conventions win. Copy the structure of existing testbenches and `run.py` before inventing any; ask when there is nothing to copy and the choice matters.
- Flow files are optional. If `ddoc/`, `tb/<ip>/tc_list.md`, `issue/` or `flow_status.md` exist, use and update them. Otherwise report in the reply, and create flow files only when the user asks or `vhflow` is driving.
- Tools: `vhdl-tools` (`shared/bin/vhdl-tools`) for VUnit and waveforms, and `corvidex-mcp` when connected; `shared/ToolPolicy.md` has the commands and fallbacks. Never report a pass that no tool run produced.
- Never open a waveform file (`.vcd`, `.fst`, `.ghw`) directly: no Read, `cat`, `head`, `grep` or script, not even to look at its header. Only `vhdl-tools wave` reads them. A waveform can be hundreds of megabytes, and one read of it can use up the whole context.
- Layout: when the project uses speja (a `speja.yaml` or `vsg.yaml`, or the user asked), run `speja --fix` on the testbench files you wrote instead of laying them out by hand.

## Pick the task

| Task | Read (this skill's folder) |
|---|---|
| Plan tests, or write a new testbench from a requirement (test-first by default) | `planning.md` |
| Author or repair `run.py`, testbench VHDL, verification components, checker processes; migrate VUnit 4 to 5 | `authoring.md` |
| Run a regression and report the results | `running.md` |

A new testbench usually needs `planning.md` then `authoring.md`. A failing test whose cause is unknown belongs to `vhdebug`.

## Rules that always apply

- Self-checking with VUnit `check_*`, a watchdog with a real time budget, and a seeded RNG whose seed is reported.
- Drive AXI4, AXI4-Lite and AXI4-Stream with premade verification components or BFMs, with randomized `stall_config` backpressure on both sides plus one zero-stall case.
- Take expected values from a reference model when the DUT computes anything non-trivial. Generate vectors per test run; never check them in.
- A test never seen to fail proves nothing: break the DUT once, watch the test fail, restore the DUT, and re-run the whole suite.
- Keep every testbench under about 5 minutes of wall time. Shrink the scenario, never the assertions.

## Core commands

- `vhdl-tools vunit elaborate --test-patterns '<pattern>'`: elaborate without simulating, which catches port, generic and type mismatches that analyze-only compilation misses.
- `vhdl-tools vunit run-tests --test-patterns '<pattern>' --num-threads 0`: run on all CPUs. Pass `--simulator nvc` or `--simulator ghdl` whenever more than one simulator is on `PATH`.
- `vhdl-tools vunit get-report --only-failing`, then `get-test-log --test-name <test>`.
- Without `uv`, the fallback is the project's `python run.py` (`--elaborate`, `-p 0`, `VUNIT_SIMULATOR=nvc`).

## References

- VUnit API (runner, phases and gate locks, checks, randomization, verification components, 4 to 5 deltas): `shared/Vunit.md`
- tsfpga module layout (`module_<name>.py`, `get_modules()`): `shared/TsfpgaModules.md`
- Protocol rules the tests must check: `shared/Axi4.md`
