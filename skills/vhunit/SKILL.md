---
name: vhunit
description: Author, repair, and migrate VUnit runners (run.py) and VHDL-2008 testbenches — direct VUnit work, VUnit 4 to 5 migration
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# VUnit Authoring & Migration

Read `shared/Vunit.md` first — it is authoritative for the VUnit-5 API
(runner, CLI, testbench phases, check_pkg, attributes, randomization,
queues, verification components, good practices, VUnit 4 vs 5 deltas).
Do not rely on memory for VUnit API details; verify against
`shared/Vunit.md` (and the installed VUnit source when in doubt).

Read `shared/McpToolPolicy.md` for tool fallbacks.

## When this skill applies

- Creating a new VUnit `run.py` and/or testbenches from scratch.
- Repairing a failing VUnit run (compile errors, elaboration, missing
  builtins, wrong registration, seed/reproducibility issues).
- Migrating a VUnit 4.x project to VUnit 5 (or this fork).
- Adding verification components (scoreboards, AXI/stream BFMs, memory
  models) to an existing testbench.

`vhtestgen` owns the test-plan flow (tc_list, test planning) and delegates
the actual authoring to this skill's rules and `shared/Vunit.md`.
`vhtestrun` owns running/reporting. Upstream `vunit-mcp` owns its own
tool usage. This skill owns the VHDL + Python.

## Determine the VUnit version first

1. Check `vunit-mcp` `vunit_status` / the project's `run.py` imports /
   installed package version.
2. If the project is on VUnit 4.x, write against VUnit 4 (see
   `shared/Vunit.md` §14 deltas) and state which version the code targets.
3. If `vunit-mcp` is the backend, target VUnit 5 (`ru551n/vunit` fork):
   `add_vhdl_builtins()` is required, `-- vunit: .name` attribute syntax.

## run.py rules (VUnit 5)

- Canonical skeleton per `shared/Vunit.md` §2:
  `VUnit.from_argv()` → `PROJ.add_vhdl_builtins()` → libraries via
  `add_library` + `add_source_files` → `PROJ.main()` (never code after it).
- One `run.py` per VUnit project (or one shared runner per repo, matching
  the existing project).
- Library name = module name; RTL added to simulation too (a broken
  "sim-only" file still breaks the run).
- `add_osvvm()` before any library that uses `random_pkg` or
  verification components.
- Preserve the existing project's `run.py` conventions (library layout,
  source globs, `main(post_run=...)`) when repairing — change only what
  is broken.

## Testbench rules (VUnit 5)

- VHDL-2008; `library vunit_lib; context vunit_lib.vunit_context;`
- `runner_cfg` generic; `test_runner_setup(runner, runner_cfg)` as the
  first statement of the test process.
- **Watchdog always**: `test_runner_watchdog(runner, <real budget>);` as a
  **concurrent statement at architecture level** (after `end process;`,
  outside the test process — a sequential call inside the test process
  blocks the test body; `shared/Vunit.md` §2/§13). Real budget: a few ×
  expected worst-case runtime, never a placeholder like `100 s`.
- Named test cases: `while test_suite loop` + `run("test_*")`, one per
  functional scenario; cover the test-plan scenarios (reset, nominal,
  min/max, backpressure, boundaries, errors).
- Self-checking: VUnit `check_*` procedures only (see `shared/Vunit.md`
  §8 for the complete VUnit-5 `check_pkg`; VUnit-4 helpers like
  `check_zero`/`check_range` do not exist here).
- **Seeds**: declare `variable rnd : RandomPType;` and
  `rnd.InitSeed(get_string_seed(runner_cfg));` once in the test process;
  report the seed on failure so the run is replayable with `--seed`.
- Scoreboards: write DUT outputs into a `memory_t` and call
  `check_expected_was_written` at cleanup — not ad-hoc comparisons
  (`shared/Vunit.md` §12).
- Back-pressure by default on all slave-side interfaces (random stall
  probability + random latencies with verification components).

## Checker process rules (mandatory)

Any checker/scoreboard process with pending work at end-of-simulation
must respect the test phases — pick one, per `shared/Vunit.md` §7.1/§7.2:

- **Pending work before exit** (drain, final checks with a queue): use
  the **phase gate lock** — `lock(runner, get_entry_key(test_runner_cleanup), logger)`
  while work is pending, unlock only after the queue is drained; keep the
  unlock `if` separate from the wait (do not combine `unlock` and the
  next `wait` in one `if` block).
- **Final-state check that must not block exit**: wait on
  `wait until is_active(runner_phase) and is_within_gates_of(test_runner_cleanup);`
  and finish the check within a single delta cycle.
- Never finish a checker process without its final check, and never let
  it race `test_runner_cleanup`.

## Verification

1. `vunit_status` → `vunit_compile` (fix compile/elaboration errors;
   common causes: missing `add_vhdl_builtins()`, VUnit-4 `add_vhdl`
   calls, wrong context).
2. `vunit_run_tests` with the smallest relevant test pattern; pass
   `waveform_format` (`vcd` on GHDL, `fst` on NVC) so failures can be
   diagnosed at signal level — without it no waveform is recorded.
3. `vunit_get_report` → on failure `vunit_get_test_log` → waveform
   (`vunit_get_test_waveform` + `waver-mcp`) when signal-level diagnosis
   is needed.
4. Fallback per `shared/McpToolPolicy.md`: run the project's `run.py`
   directly (note: `--waves`/`--wave --viewer-fmt` for waveforms on the
   fork; `--stop-on-failure` does not exist, use `--fail-fast`).

Never claim tests pass unless the actual backend reports success.

## Migration VUnit 4 → 5 (this fork)

Per `shared/Vunit.md` §14:
1. `add_vhdl` → `add_source_file`/`add_source_files`.
2. Add `PROJ.add_vhdl_builtins()` after `VUnit.from_argv()`.
3. `-- vunit_attr -- key: value` → `-- vunit: .key` (user attributes
   start with a dot); file-global pragmas `run_all_in_same_sim` /
   `fail_on_warning` become `-- vunit: run_all_in_same_sim` style.
4. Re-implement removed `check_*` helpers (`check_range`, `check_zero`,
   `check_equal_strict`, …) with `check_equal`/`check_robust` or plain
   `assert`.
5. `vunit_lib.array_util` is gone — replace with `data_types` helpers or
   manual loops.
6. Compile, run the full suite, and compare pass/fail parity against the
   last known-good VUnit 4 result before declaring the migration done.

## Completion quality gate

- `run.py` compiles and `vunit_list_tests` discovers every intended test.
- Every testbench has a watchdog, seeded RNG, and `test_runner_cleanup`.
- Every checker process uses §7.1 or §7.2 discipline (state which).
- All scenarios from the test plan covered by named `run("test_*")`.
- Suite green through the real backend (or status `BLOCKED` with the
  exact failing backend output quoted).
- Targeted VUnit version stated in the summary (4.x vs 5/fork).