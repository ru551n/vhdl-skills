# VUnit Testbench & Runner Reference

Authoritative for creating and working with VUnit test benches and Python
test runners. Covers the VUnit-5 API this stack targets — `vunit-mcp` pins
the `ru551n/vunit` fork (VUnit 5.0.0.dev12 + the `--waves` flag). VUnit 4.x
differences are listed at the end; verify against the installed version
before relying on them.

## 1. Project structure

Conventions proven by tsfpga and hdl-modules:
- one `run.py` per VUnit project (or one shared runner for a whole repo);
- one VHDL library per module folder; library name = module name;
- `src/` or `rtl/` = synthesizable files (added to simulation too),
  `sim/` = simulation-only models and BFMs, `test/` = test benches;
- one testbench per top entity: `test/tb_<entity>.vhd`;
- test case names `test_*`, one per functional scenario.

## 2. Python test runner (`run.py`)

This section covers a plain VUnit project (hand-added libraries/files). If
`run.py` instead discovers modules via `tsfpga.module.get_modules()` (a
`modules/<name>/{src,test,doc}` folder-per-library layout), see
`shared/TsfpgaModules.md` for that framework's own conventions
(`BaseModule`/`module_<name>.py`, `names_avoid`, cross-module-library
instantiation) — it builds on top of everything below, not instead of it.

### Canonical minimal run.py (VUnit 5)

```python
from pathlib import Path
from vunit import VUnit

HERE = Path(__file__).parent

PROJ = VUnit.from_argv()
# VUnit 5: HDL builtins are no longer compiled by default (issue #777).
# Required for any VHDL project.
PROJ.add_vhdl_builtins()

rtl = PROJ.add_library("rtl")
rtl.add_source_files(HERE / "rtl" / "*.vhd")

tb = PROJ.add_library("tb")
tb.add_source_files(HERE / "tb" / "*.vhd")

PROJ.main()  # exits the process (sys.exit) — never returns
```

Notes:
- `main()` calls `sys.exit` — code after it (e.g. `RESULT = PROJ.main()`)
  is dead.
- `main(post_run=callback)` accepts a post-run callback receiving a
  `Results` object (`Results.get_report()` → per-test status/path).
- `add_vhdl_builtins()` adds `data_types`, logging, `core`, `string_ops`,
  `check`, `dictionary`, `run`, `path` into `vunit_lib`.

### Libraries

- `add_library(name, vhdl_standard=None, allow_duplicate=False)` — create a
  library; output dir `<out>/<simulator>/libraries/<name>`.
- `add_external_library(name, path, vhdl_standard=None)` — consume a
  library compiled elsewhere.
- `library(name)` — handle for per-library operations.
- `get_libraries(pattern="*")`.

### Adding sources

- `add_source_file(file_name, library_name, preprocessors=None,
  include_dirs=None, defines=None, vhdl_standard=None, no_parse=False,
  file_type=None)` — `file_type` is `"vhdl"`/`"verilog"`/
  `"systemverilog"` or `None` for suffix auto-detect.
- `add_source_files(pattern, library_name, ...)` — glob pattern.
- `add_source_files_from_csv(path, library_name)`.
- Test benches are **discovered automatically**: any added file containing
  `test_runner_setup(` is a testbench; no manual registration.
- `testbench.scan_tests_from_file(path)` re-scans after generation.

### Builtins (VUnit 5)

- `add_vhdl_builtins()` — **required** for VHDL projects.
- `add_verilog_builtins()` — for Verilog/SystemVerilog.
- Optional, on demand: `add_com()`, `add_random()` (requires
  `add_osvvm()`), `add_verification_components()` (requires osvvm),
  `add_osvvm()` (OSVVM subset incl. `RandomPType`), `add_package(name)`.
- `array_util` was removed in VUnit 5.

### Test discovery and per-test configuration

```python
lib = PROJ.library("lib")
tb = lib.test_bench("tb_foo")              # entity name
test = tb.test("test_random_addresses")    # run("...") name
test.add_config(name="cfg_small", generics=dict(width=8, depth=16),
                pre_config=None, post_check=None, sim_options=None,
                attributes=None, vhdl_configuration_name=None)
```

- `generics`: dict of generic overrides.
- `pre_config` / `post_check`: Python callables around the test; hdl-modules
  uses `post_check` for Python-side analysis of simulation output.
- `vhdl_configuration_name`: select a specific VHDL `configuration` unit.
- Multiple configs per test = multiple runs of the same testcase with
  different generics — the standard generic-matrix pattern.

#### `pre_config` / `post_check` exact signatures (VUnit 5, verified from source)

`vunit/configuration.py`: both are called with `inspect.getfullargspec` —
only the parameter names present in the callable's own signature are
supplied, so declare only what is needed.

```python
def pre_config(output_path=None, simulator_output_path=None, seed=None):
    ...
    return True   # anything else (None, False) fails the test before sim runs

def post_check(output_path=None, output=None):
    # output_path: str, the test's own output directory
    # output: str, the captured simulation stdout/log text
    ...
    return True   # anything else (None, False) fails the test even if all
                   # VHDL asserts passed
```

Both **must explicitly `return True`**; a bare fall-off-the-end (`None`)
is treated as failure.

### Python reference models (golden models)

When a DUT implements a specifiable numeric/algorithmic transform (DSP,
image/pixel processing, codec, protocol datapath, fixed-point
approximation) with a precise enough functional spec to re-implement in
plain Python, prefer a **Python reference model** as the single source of
expected-behavior truth over hand-computing expected values inside the
testbench or re-deriving them ad hoc per test case.

Pattern:

- `<module>_model.py` (or `<ip>_model.py` for a full-pipeline/integration
  test) next to `run.py`, implementing the same integer/fixed-point
  approximations documented in the module's requirement/architecture doc
  (e.g. the same truncation, rounding, and saturation behavior — not a
  higher-precision "more correct" version that would produce mismatches
  against a deliberately-approximate DUT).
- Keep the model importable both from `run.py`/test configs and
  standalone (e.g. from a plain `pytest` unit test of the model itself) —
  do not embed it only as inline closures inside `run.py`.
- `pre_config(output_path, ...)`: call the model with the same
  generics/seed the VUnit `add_config` uses, to generate stimulus and the
  model's precomputed expected-output file(s) into `output_path` before
  the simulation runs. The testbench reads the stimulus file back
  (typically via `integer_array_pkg.load_csv`/`load_raw`, or plain
  `std.textio`) and drives it in, generic-matched, cycle-accurate or
  randomized-backpressure order.
- `post_check(output_path, output)`: load whatever the testbench itself
  dumped during simulation (typically via `integer_array_pkg.save_csv`)
  and compare it value-for-value against the model's precomputed expected
  file from `pre_config`. Return `True` only on an exact match; otherwise
  return `False` (or raise) with a useful diff (index, expected, actual)
  printed for triage.
- One model instance, parameterized identically to the DUT's generics for
  that `add_config`, covers exactly one test run — do not share mutable
  model state across configs in the same `run.py` process.
- The model is not a replacement for in-VHDL protocol assertions
  (handshake stability, no beat loss/duplication) — those stay as VHDL
  checks; the model only owns "is the computed value correct."
- `tb.get_tests(pattern="*")`.
- `test.set_generic(...)` / `test.set_attribute(".name", value)`.

### Bulk options (scope warning)

`set_generic`, `set_parameter`, `set_sim_option`, `set_compile_option`,
`add_compile_option`, `set_attribute` applied to `PROJ`/`lib`/`tb`/`test`
only affect testbenches **added before the call**:

```python
tb.set_generic("message", "set-for-entity")      # entity-level
test.set_generic("message", "set-for-test")      # test-level
lib.set_sim_option("enable_coverage", True)
lib.set_sim_option("nvc.elab_flags", ["--cover=branch,statement"])
```

- `set_generic` lowercases the name.
- `update_test_pattern(include_dependent_on=..., exclude_dependent_on=...)`
  — restrict the run to tests depending on a file set (CI subset).

### Custom CLI arguments

```python
from vunit import VUnit, VUnitCLI
cli = VUnitCLI()
cli.parser.add_argument("--custom", default="x")
PROJ = VUnit.from_args(cli.parse_args())
# use PROJ._args.custom in set_generic(...) etc.
```

### Preprocessing hooks

- `enable_location_preprocessing()` — file/line info on log messages.
- `enable_check_preprocessing(order=200)` — decorate check messages with
  location.

## 3. `run.py` CLI reference (VUnit 5)

Positional: `tests` — fnmatch test patterns, default `*` (quote patterns to
avoid shell globbing).

| Flag | Meaning |
|---|---|
| `--with-attributes X` (repeatable) | only run tests having attribute X |
| `--without-attributes X` (repeatable) | only run tests lacking attribute X |
| `-l`, `--list` | list matching test cases (no run) |
| `-f`, `--files` | list files in compile order (`lib, file` lines) |
| `--compile` | compile only, do not run |
| `-m`, `--minimal` | compile only what the filtered tests need |
| `-k`, `--keep-compiling` | continue past compile errors |
| `--fail-fast` | stop at the first failing test |
| `--elaborate` | elaborate testbenches without running |
| `--clean` | remove the output path first |
| `-o`, `--output-path` | output dir (default `<cwd>/vunit_out`) |
| `--changed` | only tests affected by files changed since last run |
| `--test-prio {opt,ordered}` | `opt` (default, fail-early + balance) or added order |
| `-x`, `--xunit-xml FILE` | write JUnit XML to FILE (no junit by default) |
| `--xunit-xml-format {jenkins,bamboo}` | JUnit dialect (default `jenkins`) |
| `--exit-0` | exit 0 even if tests fail (still 1 on compile/fatal errors) |
| `--dont-catch-exceptions` | let exceptions bubble (debugging) |
| `-v`, `--verbose` | stream test output live |
| `-q`, `--quiet` | no output even on failure |
| `--no-color` | disable ANSI colors |
| `--log-level {info,error,warning,debug}` | VUnit log level (default `warning`) |
| `-p`, `--num-threads N` | parallel test threads; `0` = all logical CPUs |
| `-u`, `--unique-sim` | no simulator process reuse between tests |
| `--export-json FILE` | export files/tests/attributes as JSON |
| `--seed SEED` | 16-hex-digit base seed, or `repeat` to reuse previous base seed(s) |
| `-g`, `--gui` | open tests in the simulator GUI |
| `--wave` | generate a waveform file (GHDL/NVC) — see waveforms below |
| `--viewer-fmt {vcd,fst,ghw}` | waveform format (aliases `--wave-fmt`, `--gtkwave-fmt`) |
| `--viewer-args ARGS` | viewer command args (alias `--gtkwave-args`) |
| `--viewer CMD` | viewer command (default None → `gtkwave`/`surfer`) |
| `--version` | print version |

There is no `--stop-on-failure` (it is `--fail-fast`), no `--requirements`
flag (use `--with-attributes`), and no `--show-window` (it is `--gui`).

## 4. Environment variables

- `VUNIT_SIMULATOR` — select simulator (`ghdl`, `nvc`, `modelsim`, ...).
- `VUNIT_<SIM>_PATH` — toolchain prefix for a simulator.
- `VUNIT_MODELSIM_PATH`, `VUNIT_MODELSIM_INI`.
- `VUNIT_VHDL_STANDARD` — default `2008`.
- `GHDL`, `NVC` — override the executable name used.
- `VUNIT_SHORT_TEST_OUTPUT_PATHS=true` — hash-only output dir names
  (avoids `OSError: File name too long` with long test names).
- `VUNIT_TEST_OUTPUT_PATH_MARGIN` — extra path-length margin (Windows).

There is no `VUNIT_NUM_THREADS` env var (use `-p`).

## 5. Output, results, waveforms

Layout under `-o` (default `./vunit_out`):
```text
vunit_out/
├── project_database/          # persistent DB (compile state, test parse)
├── preprocessed/
├── codecs/
├── <simulator>/libraries/<lib>/
└── test_output/
    ├── test_name_to_path_mapping.txt   # "<dir_name> <full_test_name>"
    └── <test_name>_<hash>/
        ├── output.txt
        ├── output_with_color.txt
        ├── vunit_results
        ├── ghdl/wave.<fmt>             # GHDL waveform (--wave --viewer-fmt)
        └── nvc/<entity>.<fmt>          # NVC waveform (--wave)
```

- JUnit XML only via `-x FILE`.
- Exit codes: `0` all OK (or `--exit-0`); `1` on test failure, compile
  error, missing simulator, or uncaught exception.
- **Waveforms:** `--wave` alone generates **no** file on GHDL — the format
  must be given with `--viewer-fmt` (vcd → `--vcd=`, fst → `--fst=`,
  ghw → `--wave=`). NVC defaults to `fst`; `ghw` is unsupported (warns,
  falls back to fst). `vunit-mcp` wraps this via its `waveform_format`
  parameter (`vcd` on GHDL, `fst` on NVC), so prefer
  `vunit_get_test_waveform`.
- Each test case runs in its own simulation by default (trustworthy,
  parallelizable); `-- vunit: run_all_in_same_sim` forces one simulation
  per testbench (disables per-test configs).

## 6. VHDL testbench

### Canonical skeleton

```vhdl
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library vunit_lib;
context vunit_lib.vunit_context;

entity tb_foo is
  generic (runner_cfg : string);
end entity;

architecture sim of tb_foo is
  -- signals, DUT, BFM/checker instantiations
begin
  proc: process
  begin
    test_runner_setup(runner, runner_cfg);

    -- hard hang protection (budget = expected worst-case runtime + margin)
    test_runner_watchdog(runner, 1 ms);

    if run("test_init_state") then
      -- deterministic checks
    elsif run("test_random_addresses") then
      -- seeded randomized scenario
    end if;

    test_runner_cleanup(runner);
    wait;
  end process;
end architecture;
```

- `runner` is a **package signal** from `vunit_lib.run_pkg` (via
  `vunit_context`) — do not declare it.
- `run("name")` returns true only when the case is enabled in
  `runner_cfg` and not yet run. A testbench with no `run(...)` becomes a
  single implicit test. Duplicate `run("...")` names are an error.
- Two contexts: `vunit_context` (full: check, logger, data_types, run, ...)
  and `vunit_run_context` (minimal: run only — for integrating an external
  checking framework).

### `run_pkg` API

| Function | Meaning |
|---|---|
| `test_suite` | loop condition (true until cleanup) |
| `run(name)` | start test case `name` if enabled |
| `enabled(name)` | is `name` in the enabled set |
| `active_test_case`, `running_test_case` | current test case name |
| `test_case_error`, `test_suite_error` | abort current case / suite with failure |
| `test_case_exit`, `test_suite_exit`, `test_exit` | exit without failure |
| `test_runner_setup`, `test_runner_cleanup` | suite boundaries |
| `test_runner_watchdog(runner, t)`, `set_timeout(runner, t)` | hang protection |
| `get_phase` | current `runner_phase_t` |
| `wait_until(runner, phase)` | wait until a phase is entered |
| `get_entry_key(phase)` / `get_exit_key(phase)` | unique `key_t` for a phase gate |
| `is_within_gates_of(phase)` | inside the entry/exit gates of `phase` |
| `lock(runner, key, logger)`, `unlock(runner, key, logger)`, `is_locked(key)` | phase gate locks |
| `get_seed(runner_cfg, salt)` (string/unsigned/signed/integer) | derived seed, FNV-1a |
| `get_string_seed(runner_cfg[, salt])` | alias of `get_seed` (string form) — **the standard seed source** |
| `get_uniform_seed` | uniform integer seed |

`runner_cfg` keys injected by VUnit: `enabled_test_cases`, `seed`,
`use_color`, `output path`, `active python runner`, `tb path`; a declared
`output_path` generic (optional) is filled too. `core_pkg.stop(status)`
aborts immediately.

## 7. VUnit phases

Phases a testbench traverses, in order:
`test_runner_entry` → `test_runner_setup` → `test_suite_setup` →
(`test_case_setup` → `test_case` → `test_case_cleanup`)* →
`test_suite_cleanup` → `test_runner_cleanup` → `test_runner_exit`.

The `runner` signal carries the `runner_phase` event, which is activated on
**every phase change and on gate-lock activity**. `test_runner_cleanup`
halts on its entry/exit gates while any gate lock is held — that is the
mechanism below.

### 7.1 Phase gate locks — checker processes that must finish before exit

For any process with pending work at end-of-simulation (scoreboards, data
checkers, drain logic): lock the entry gate of `test_runner_cleanup` so
VUnit cannot end the simulation before the work is done. Do **not** use a
done-event + `wait until is_active(...)` in the runner for this — the lock
scales to any number of processes, has no ordering races, and requires no
runner changes.

Pattern (locking is idempotent — locking a locked gate keeps it locked,
unlocking an unlocked gate keeps it unlocked):

```vhdl
dut_checker : process
  constant key : key_t := get_entry_key(test_runner_cleanup);
begin
  if is_empty(queue) then
    wait until is_active(new_data_set);
  end if;
  lock(runner, key, dut_checker_logger);

  for i in 1 to pop(queue) loop
    wait until (rising_edge(clk) and output_tvalid = '1')
       or log_active(vunit_error, decorate("while waiting on output data"),
                     logger => dut_checker_logger);
    check_equal(output_tdata, calculate_expected_output(pop(queue)));
  end loop;

  if is_empty(queue) then
    unlock(runner, key, dut_checker_logger);
  end if;
end process;
```

Rules:
- Acquire the key once with `get_entry_key(test_runner_cleanup)` (a
  constant per process); unique keys prevent one process from removing
  another process's lock.
- Lock when work is pending; **check the queue before unlocking** — unlock
  first and the simulation can end with data still queued.
- Do **not** combine `unlock` and the next `wait` in one `if` block: the
  `unlock` consumes delta cycles (`runner_phase` activation) during which a
  new data set can arrive and the event is missed — a time-of-check-to-
  time-of-use bug. Keep two separate `if is_empty(queue)` statements.
- Keep the unlock `if` at the bottom of the process body.
- `log_active(vunit_error, msg, logger)` in the wait keeps the process alive
  through the VUnit error abort path.
- The runner process needs no changes — the checker owns its completion
  (high cohesion) and makes no assumptions about runner timing (low
  coupling).

### 7.2 Phase transition events — final checks that must not block exit

For checkers that must **not** delay the simulation but need a last chance
to verify a final-state invariant (e.g. the AXI4-Stream
`AXI4STREAM_ERRM_STREAM_ALL_DONE_EOS` assertion: every stream saw `TLAST`
before end of simulation):

```vhdl
end_of_simulation_process : process
begin
  wait until is_active(runner_phase) and is_within_gates_of(test_runner_cleanup);
  check_stream_activity;   -- must complete within a single delta cycle
  wait;
end process;
```

- `runner_phase` fires on all phase changes and lock activity, so always
  confirm with `is_within_gates_of(test_runner_cleanup)` (past the entry
  gate, before the exit gate) that the simulation is about to exit.
- The check must complete in a single delta cycle — it is the window
  between the cleanup entry and exit gates.
- Use the gate-lock form (7.1) instead when the check could still be
  running or needs to drain data.

## 8. Checks (`check_pkg` — VUnit 5, complete)

Every check has variants: plain, `pass: out boolean`, with `checker: in
checker_t`, and as impure function returning boolean. Common args: `msg`
(default `check_result_tag`), `level` (default `null_log_level`), plus
location args.

| Function | Meaning |
|---|---|
| `check(expr)` | check a boolean expression |
| `check_true(expr)`, `check_false(expr)` | incl. clocked variants (`clock, en, active_clock_edge`) |
| `check_passed(msg)`, `check_failed(msg, level)` | explicit pass/fail |
| `check_implication(antecedent, consequent)` | only check when antecedent holds |
| `check_stable(value, clock)` | value unchanged over a clock edge |
| `check_not_unknown(value)` | no 'U'/'X' (std_logic / vector) |
| `check_zero_one_hot`, `check_one_hot` | one-hot encodings |
| `check_next(value, ...)` | value at next cycle |
| `check_sequence(seq, clock, en, trigger_event, active_clock_edge)` | pattern of rising/falling/both edges over `seq` |
| `check_relation(expr, msg, context_msg)` | boolean relation with a rich message (protocol invariants) |
| `check_equal(got, expected)` | equality — 154 overloads across the type matrix below |
| `check_match(got, expected)` | wildcard match, `'-'` = don't care (unsigned / slv) |

`check_equal` type matrix (VUnit 5): boolean↔{boolean, std_logic},
character, integer↔{integer, signed}, natural↔{natural, unsigned,
std_logic_vector}, real, signed↔{signed, integer}, std_logic,
std_logic_vector↔{std_logic_vector, unsigned, natural}, string, time,
unsigned↔{unsigned, natural, std_logic_vector}; VHDL-2008 additions:
sfixed/ufixed↔sfixed/ufixed and ↔real.

Stats/utilities: `get_checker_stat`, `reset_checker_stat`,
`log(check_result)`, `notify_if_fail(check_result, event)`. Constants:
`default_checker`, `check_logger`, `check_enabled`.

Note: the VUnit-4 helpers `check_equal_strict`, `check_range`,
`check_between`, `check_ascending`/`check_descending`, `check_zero`,
`check_non_zero` do **not** exist in the VUnit-5 fork — express those with
`check_relation` or explicit checks.

### Checkers (`checker_pkg`)

- `new_checker(name|logger, default_log_level := error)`
- `passing_check(checker, msg)`, `failing_check(checker, msg, level)`
- `log_passing_check`, `log_failing_check`
- `get_logger`, `get/set_default_log_level`, `is_pass_visible`
- `checker_stat_t(n_checks, n_failed, n_passed)` with `+`, `-`, `to_string`
- `to_integer` / `to_checker` conversions

## 9. Attributes, requirements & traceability

VUnit 5 (this fork):
- Syntax: `-- vunit: <name>` in a comment, placed after the `run("...")`
  line it belongs to (attached to the **preceding** test case).
- Built-in (file-global): `run_all_in_same_sim`, `fail_on_warning` (raises
  the assert stop level to `warning`).
- Any other name is a **user attribute and must start with a dot**:
  `-- vunit: .requirement-117`.
- Legacy file-global pragma: `vunit_pragma <name>`.
- Values are not supported in this fork (presence only); duplicates raise.

VUnit 4 (stable releases): the older syntax `-- vunit_attr -- key: value`
(e.g. `-- vunit_attr -- requirement: "id"`) and `-- vunit_pragma
run_all_in_same_sim` / `fail_on_warning`. When a project is on VUnit 4.x,
use its syntax (verify against the installed version).

Usage:
- Requirements/traceability = user attributes (`.requirement-*`); select
  runs with `--with-attributes .requirement-117` /
  `--without-attributes`; export with `--export-json`.
- Set from Python: `test.set_attribute(".name", value)`.
- `--export-json` structure: `{export_format_version, files:
  [{file_name, library_name}], tests: [{name, location: {file_name,
  offset, length}, attributes: {name: value}}]}`.

## 10. Randomization & seeds

- The **base seed** is a 64-bit value VUnit derives from time + thread;
  every test gets a distinct one. Pass `--seed <16-hex>` (e.g. `--seed
  1234567812345678`) to make runs reproducible, or `--seed repeat` for the
  same seed across all test cases.
- `get_string_seed(runner_cfg)` / `get_unsigned_seed(runner_cfg)` /
  `get_signed_seed(runner_cfg)` read the per-test seed (plus optional
  `salt`) — all aliases of `run_pkg.get_seed`.
- **One seed source drives all RNGs.** Seed from `runner_cfg` in the test
  process and report the seed with `report` on failure so a bad run can
  be re-executed with `--seed`.
- Per-scenario variation: `get_string_seed(runner_cfg, "scenario-b")`.

```vhdl
test_runner_setup(runner, runner_cfg);
rnd.InitSeed(get_string_seed(runner_cfg));
```

`random_pkg` (in `vunit_lib`, requires OSVVM):

```python
PROJ.add_osvvm()
lib = PROJ.add_library("tb")
lib.add_source_files(..., "random_pkg.vhd")  # or vunit/vhdl/random/src/random_pkg.vhd
```

```vhdl
use vunit_lib.random_pkg.all;

-- Random words within an explicit range:
random_integer_vector_ptr(rnd, vec, length => 16, min_value => 0, max_value => 2**32 - 1);
-- Random words by bit width (signed/unsigned):
random_integer_vector_ptr(rnd, vec, length => 16, bits_per_word => 32, is_signed => false);
-- 1D/2D/3D arrays:
random_integer_array(rnd, arr, width => 8, height => 4, depth => 2, bits_per_word => 8);
```

The `impure function` forms (no `rnd` parameter) use a shared RNG seeded
from the test seed — convenient for one-offs, but prefer an explicit
`RandomPType` for reproducible sequences.

## 11. Queues & data types

`vunit_lib.data_types_context` (pulled in by `add_vhdl_builtins()`):
`queue_pkg`, `dict_pkg`, `id_pkg`, `integer_array_pkg`,
`integer_vector_ptr_pkg`, `byte_vector_ptr_pkg`, `string_ptr_pkg`,
`event_pkg`, `codec_pkg`.

### `queue_t`

```vhdl
use vunit_lib.queue_pkg.all;

constant q : queue_t := new_queue;
if not is_empty(q) then ... end if;
length(q);            -- element count
flush(q);             -- remove all
copy(q);              -- duplicate

push(q, value);       -- bit, bit_vector, boolean, character, integer, real,
                      -- std_ulogic, std_ulogic_vector, string, time,
                      -- signed, unsigned, severity_level, complex
pop(q, value);        -- same types; raises if empty
push_ref(q, value);   -- / pop_ref: reference types (e.g. integer_array_t)
encode(q, encoder) / decode(q, decoder, value);
```

Queues are the standard workhorse for reference-data pipelines in BFMs
(see §12) and scoreboard designs.

### `integer_array_t` / `integer_vector_t` / `dict_t` / `id_t`

```vhdl
use vunit_lib.integer_array_pkg.all;   -- 1D/2D/3D signed/unsigned integer arrays
constant a1 : integer_array_t := new_1d(width => 8, bit_width => 16, is_signed => false);
constant a2 : integer_array_t := new_2d(width => 4, height => 4, bit_width => 8, is_signed => true);
constant a3 : integer_array_t := new_3d(width, height, depth, bit_width, is_signed);
width(a1); height(a2); depth(a3); bit_width(a1); is_signed(a1);
get(a1, 0, 0) / set(a1, 0, 0, value);
copy(a1);

use vunit_lib.integer_vector_ptr_pkg.all;  -- length-unbounded 1D integer vector
use vunit_lib.dict_pkg.all;                -- associative map: insert/get/delete
use vunit_lib.id_pkg.all;                  -- unique id_t (get_id, increment)
```

## 12. Verification components (VCs)

VUnit ships behavioral testbench components in
`vunit/vhdl/verification_components/` (package + entity per IP). Requires
OSVVM:

```python
PROJ.add_osvvm()
vc = PROJ.add_verification_components()  # or:
# PROJ.add_external_library("vunit_vc", <path>)
```

All components are reachable from `vunit_lib` (via `vc_context.vhd`):
`vc_pkg`, `bus_master_pkg`, `memory_pkg`, `memory_utils_pkg`, `axi_pkg`,
`axi_lite_master_pkg`, `axi_slave_pkg`, `axi_statistics_pkg`,
`axi_stream_pkg`, `signal_checker_pkg`, `stream_master_pkg`,
`stream_slave_pkg`, `sync_pkg`, `uart_pkg`, `avalon_pkg`,
`avalon_stream_pkg`, `wishbone_pkg`.

### `memory_pkg` — the standard scoreboard

```vhdl
use vunit_lib.memory_pkg.all;

constant mem : memory_t := new_memory;
buf := allocate(mem, num_bytes => 4096);
clear(mem);
write_byte(mem, address, data);      -- / write_word / write_integer
set_expected_byte(mem, address, data);  -- / set_expected_word
clear_expected_byte(mem, address);
read_byte(mem, address, data) / read_word(mem, address, num_bytes, data);
-- Scoreboard check: every expected byte was written with the right value:
check_expected_was_written(mem);                 -- whole memory
check_expected_was_written(mem, address, num_bytes);  -- address range
```

Write the DUT output into `mem`, then `check_expected_was_written` —
this is the canonical "scoreboard" pattern (see hdl-modules
`tb_axi_lite_cdc`).

### `bus_master_pkg` — bus abstraction

```vhdl
use vunit_lib.bus_master_pkg.all;

constant bus : bus_master_t := new_bus(data_length => 32, address_length => 24);
data_length(bus); address_length(bus);

-- Non-blocking (queues the transaction; the entity drives it):
write_bus(net, bus, address, data);
burst_write_bus(net, bus, address, data_queue, burst_length);
read_bus(net, bus, address, reference);          -- returns bus_reference_t
burst_read_bus(net, bus, address, burst_length, reference);
-- Blocking reply handling:
await_read_bus_reply(net, reference, data);
await_burst_read_bus_reply(net, bus, data_queue, reference);  -- pushes words
check_bus(net, bus, address, expected, msg => "");            -- read+check
wait_until_read_equals(net, bus, address, expected);
wait_until_read_bit_equals(net, bus, address, bit_index, expected);
wait_until_idle(net, bus, wait_time => 1 us);
```

### AXI-4(-Lite) components

- **`axi_pkg`**: types `axi_t`/`axi_read_request_t`/`axi_write_request_t`,
  `create_*` helpers, `push_*`/`pop_*` transaction functions.
- **`axi_lite_master`** (entity): generics
  `bus_handle : bus_master_t`, `drive_invalid : boolean := true`,
  `drive_invalid_val : std_logic := 'X'` — set
  `drive_invalid_val => '0'` to keep NUMERIC_STD from complaining about
  meta-values on X-driven buses.
- **`axi_slave_pkg`**: `new_axi_slave(memory, address_fifo_depth,
  write_response_fifo_depth, address_stall_probability,
  data_stall_probability, write_response_stall_probability,
  min_response_latency, max_response_latency, logger)` → `axi_slave_t`.
  Entities `axi_read_slave`, `axi_write_slave`,
  `axi_lite_read_slave`, `axi_lite_write_slave` implement the slave
  side with randomized back-pressure (the hdl-modules TBs set
  `*_stall_probability` ≈ 0.3 and random latencies — a DUT that only
  works when the slave is eager is a DUT bug).
- **`axi_stream_pkg`**: `axi_stream_transaction_t`
  (`data`, `strobe`, `last`, `user`), `new_axi_stream_transaction`,
  `push_axi_stream`/`pop_axi_stream` (queue-based),
  `check_axi_stream`; entities `axi_stream_master`,
  `axi_stream_slave`, `axi_stream_monitor`, `axi_stream_protocol_checker`.
- **`axi_statistics_pkg`**: throughput/latency counters for AXI.

### Other components

- `signal_checker_pkg`: `check_signal(signal, expected, msg)`,
  `check_signals`, `await_rising_edge` — for single-signal checks.
- `stream_master_pkg` / `stream_slave_pkg`: generic `valid/ready/data`
  stream drivers/loaders with queues.
- `uart_pkg` (+ `uart_master`/`uart_slave` entities): UART BFM.
- `avalon_pkg` / `avalon_stream_pkg` (+ `avalon_master`, `avalon_slave`,
  `avalon_source`, `avalon_sink`): Avalon-MM / Avalon-ST BFMs.
- `wishbone_pkg`: Wishbone BFM.
- `bus2memory` entity: routes a generic bus into a `memory_t`
  scoreboard directly.
- `ram_master` entity: simple `bus_handle`-driven RAM read/write.
- `std_logic_checker` entity: flags X/Z on observed signals.

### Blocking vs. non-blocking VC calls (prefer non-blocking for stimulus/checks)

Every VUnit VC procedure that sends a message via `net` and does not wait
for a reply returns immediately ("non-blocking"/fire-and-forget); a
procedure that waits for a reply message blocks the calling process until
that reply arrives. **Default to the non-blocking form when generating
stimulus or queuing expected-result checks** — it lets the driving/checking
process issue a whole frame/packet's worth of transactions up front without
stalling cycle-by-cycle on the DUT's actual backpressure timing; the VC's
internal message queue (and, on the DUT side, its `tready`/`tvalid`
handshake) absorbs the timing, which is exactly the "no bubble/no loss by
construction" property already noted above for the `axi_*_bfm` queue-driven
variants. Reserve the blocking form for the (rare) case where the test
process genuinely needs a value back before deciding its next action.

Verified from `axi_stream_pkg.vhd` (VUnit 5, this stack) — exact
blocking/non-blocking status per procedure/overload:

| Procedure | Blocking? | Notes |
|---|---|---|
| `push_axi_stream(net, master, tdata, tlast, ..., tuser)` | **Non-blocking** | Only form that exists; always queues the beat and returns immediately. Use this for all stimulus generation. |
| `pop_axi_stream(net, slave, tdata, tlast, tkeep, tstrb, tid, tdest, tuser)` (7-out-param form) | Blocking | Waits for the popped beat before returning. |
| `pop_axi_stream(net, slave, tdata, tlast)` (2-out-param form) | Blocking | Short form of the same blocking pop. |
| `pop_axi_stream(net, slave, reference)` | **Non-blocking** | Queues the pop request, returns a `axi_stream_reference_t` handle immediately. Redeem later with `await_pop_axi_stream_reply` (blocking) once the value is actually needed — lets the test process issue many pops back-to-back, then drain replies in a second pass or a separate checker process. |
| `await_pop_axi_stream_reply(net, reference, tdata, tlast, ...)` | Blocking | Companion to the non-blocking `pop_axi_stream(..., reference)` above. |
| `check_axi_stream(net, slave, expected, ..., blocking => true\|false)` | **Either, via `blocking` generic** (default `true`) | Set `blocking => false` to queue an expected-value check without stalling the checking process — **prefer this for verification data**: queue every expected beat for a frame up front (mirrors how `push_axi_stream` queues stimulus), and let the VC report mismatches asynchronously as they're popped from the DUT, rather than hand-writing a wait-per-beat loop. |

Practical pattern for this project's per-module testbenches: in the
stimulus process, `push_axi_stream` every beat of a frame (including the
`tuser`/`tlast` passenger bits) back-to-back with no explicit `wait`
between beats; in the checking process, `check_axi_stream(..., blocking =>
false)` every expected beat back-to-back the same way, sourced from the
Python golden model's precomputed expected file (see "Python reference
models" above). Only fall back to the blocking forms for a targeted
directed test that must inspect one value before deciding what to drive
next (e.g. a reset-recovery or error-injection sequence).

### Randomized backpressure via `stall_config` (mandatory default)

Per `shared/Axi4.md`'s mandatory-backpressure design rule, a testbench must
actually **exercise** backpressure, not just assume the DUT implements it
correctly. **Every VUnit `axi_stream_master`/`axi_stream_slave` (and the
other queue/handshake-based VCs — `bus_master_t`, `bfm.handshake_master`/
`handshake_slave`, etc.) instantiated against a link with real
`tready`/`tvalid` handshaking must be given a non-zero randomized
`stall_config` by default**, on both sides of the link:

- On the **master** (driving stimulus into the DUT's slave/input port):
  randomized stalls simulate an upstream producer that doesn't always have
  a beat ready — exercises the DUT's tolerance for `tvalid` gaps.
- On the **slave** (checking the DUT's master/output port): randomized
  stalls simulate a downstream consumer that isn't always ready — exercises
  the DUT's actual `tready`-driven backpressure path (line buffers/FIFOs
  holding state, no bubble insertion/drop/duplication), which is the entire
  point of the Option-B "full per-stage AXI-Stream" design decision. A
  testbench that only ever holds `tready`/`m_axis_tready` high cannot
  distinguish a correct elastic implementation from a free-running one that
  merely happens to work when nothing ever stalls.

API (verified from `axi_stream_pkg.vhd`, VUnit 5, this stack):

```vhdl
function new_stall_config(
  stall_probability : real range 0.0 to 1.0;
  min_stall_cycles  : natural;
  max_stall_cycles  : natural
) return stall_config_t;
```

Pass it either at construction:

```vhdl
constant master_stall : stall_config_t := new_stall_config(
  stall_probability => 0.5, min_stall_cycles => 1, max_stall_cycles => 4
);
constant m : axi_stream_master_t := new_axi_stream_master(
  data_length => ..., user_length => ..., stall_config => master_stall
);
constant s : axi_stream_slave_t := new_axi_stream_slave(
  data_length => ..., user_length => ..., stall_config => master_stall  -- independent instance per side
);
```

or change it mid-test via `set_stall_config(net, master_or_slave,
stall_config)` (readable back with `get_stall_config`) — useful for a test
case that wants an initial no-stall "sanity" pass before switching to a
randomized-backpressure pass in the same run.

- **Seed `stall_probability`/`min_stall_cycles`/`max_stall_cycles` from the
  test's own seeded RNG** (`get_string_seed(runner_cfg)`, see §10), not a
  fixed literal, so different seeded runs exercise different stall
  patterns and a failure is reproducible via `--seed`. hdl-modules'
  `tb_axi_stream_bfm` pattern (`rnd.Uniform(0, 90)` percent, `min=1,
  max=3` cycles) is a reasonable default shape to copy.
- **Always include at least one directed, zero-stall configuration/test
  case too** (`null_stall_config`) as the simplest possible sanity check
  before the randomized-backpressure cases — if that fails, debug that
  first rather than a randomized run.
- This applies independently of the blocking-vs-non-blocking call style
  above: a non-blocking `push_axi_stream`/`check_axi_stream(...,
  blocking => false)` still stalls exactly as configured at the actual
  bus signals; the non-blocking call style only affects when the *test
  process* is released, not the VC's own drive/sample timing.
- Skip this for a link that is provably unable to stall (documented
  exception per `shared/Axi4.md`), not by default omission.

### BFM wrapper pattern (hdl-modules)

hdl-modules wraps the VUnit entities in the `bfm` library with clean
record ports and **protocol checkers on every channel**:

```vhdl
entity bfm.axi_lite_master
  generic (bus_handle : bus_master_t; logger_name_suffix : string := "");
  port (clk : in std_ulogic;
        axi_lite_m2s : out axi_lite_m2s_t;   -- record ports instead of 5 buses
        axi_lite_s2m : in  axi_lite_s2m_t);
-- Internally: entity vunit_lib.axi_lite_master (drive_invalid_val => '0')
--   + 5x entity common.axi_stream_protocol_checker (one per AXI channel).
```

Ready wrappers: `bfm.axi_master`, `bfm.axi_lite_master`
(+`_bfm`, `_read_slave`, `_write_slave`, `_slave`), `bfm.axi_stream_master`,
`bfm.axi_stream_slave`, `bfm.handshake_master`, `bfm.handshake_slave`,
`bfm.memory`, `bfm.queue`, `bfm.integer_array`. The `axi_*_bfm` variants
take `job_queue`/`data_queue` generics — drive transactions by pushing
into queues; "no loss / no bubble" properties fall out of the queue
back-pressure by construction.

**Caveat, verified this session**: `bfm.axi_stream_master`/`bfm.axi_stream_slave`
(hdl-modules' own wrapper, `modules/bfm/sim/axi_stream_{master,slave}.vhd`)
enforce `user_width mod 8 = 0` ("This entity works on a byte-by-byte basis")
— they assume any `tuser` payload is byte-aligned auxiliary data, not a
narrow passenger-bit field. **Do not use this wrapper for a `tuser` field
narrower than 8 bits and not a multiple of 8** (e.g. a 1-2 bit
SOF/border/sideband field, as in a raster-image AXI4-Stream pipeline) —
the entity's own assertion will fail at elaboration. In that case, use
VUnit's raw `vunit_lib.axi_stream_master`/`axi_stream_slave` entities and
`axi_stream_pkg.new_axi_stream_master`/`new_axi_stream_slave` directly
(arbitrary `user_length`, no alignment constraint) instead of the
hdl-modules wrapper, and add the protocol-checker instance yourself
(`common.axi_stream_protocol_checker`, generic-mapped to the link's actual
`data_width`/`user_width`) if per-channel checking is still wanted. This is
the general rule, not just a one-off workaround: **before reusing any
higher-level BFM/VC wrapper, check its generic-range assertions against
the actual interface width being tested** — a wrapper built for a common
case (byte-aligned buses) can silently be the wrong tool for a
deliberately narrow project-specific field.

### Writing a custom VC (only when no adequate built-in/wrapper exists)

Per the VC-preference rule above, only write a custom VC after confirming no
built-in VC/VCI (§12 lists) and no thin wrapper around one covers the
interface — for this project's AXI4-Stream links, that bar is essentially
never met (raw `vunit_lib.axi_stream_master`/`axi_stream_slave` already
handle arbitrary `user_length`, see the BFM-wrapper caveat above), so expect
this to stay unused unless a genuinely new, non-AXI4-Stream, non-bus
interface shows up. Verified this session against VUnit's own docs
(`docs/verification_components/user_guide.rst`, `vci.rst`) and real source
(`uart_pkg.vhd` / `uart_master.vhd` / `vc_pkg.vhd`, `verification_components/src`).

**Concepts** (from VUnit's own docs):
- A **Verification Component (VC)** is a simulation-only entity wired to the
  DUT via a real bus/protocol interface, controlled by a **handle record**
  (a generic on the entity, e.g. `uart_master_t`) and driven by test code via
  **procedures that send messages** over `com`/`net` to the handle's actor —
  not by writing to signals directly from the test process.
- A **Verification Component Interface (VCI)** is a *generic* procedural API
  (e.g. `stream_master_pkg`'s push/pop, `sync_pkg`'s
  `wait_until_idle`/`is_idle`) that several different VCs can implement by
  providing an `as_stream`/`as_sync`-style adapter function from their own
  handle type to the VCI's handle type — this lets generic testbench code
  (e.g. a scoreboard driver) work unmodified against a UART, Avalon-ST, or
  AXI-Stream VC. Implement the relevant `as_*` adapter(s) for a new VC
  whenever an existing VCI already covers part of its behavior (see
  `uart_pkg.as_stream`/`as_sync` below) instead of inventing new procedures.

**Minimal skeleton** (mirrors `uart_pkg.vhd` + `uart_master.vhd`, the
smallest complete built-in VC):

```vhdl
-- 1. Handle type + constructor + message types, in a package
package my_vc_pkg is
  type my_vc_t is record
    p_actor : actor_t;      -- required: the VC's message-passing identity
    p_cfg   : natural;      -- any config fields the VC needs
  end record;

  impure function new_my_vc(cfg : natural := 0) return my_vc_t;

  -- One procedure per command; each just builds and sends a msg (non-blocking
  -- by default, matching the project's blocking/non-blocking preference above)
  procedure my_vc_do_thing(signal net : inout network_t; vc : my_vc_t; arg : integer);

  constant my_vc_do_thing_msg : msg_type_t := new_msg_type("my_vc do thing");
end package;

package body my_vc_pkg is
  impure function new_my_vc(cfg : natural := 0) return my_vc_t is
  begin
    return (p_actor => new_actor, p_cfg => cfg);
  end;

  procedure my_vc_do_thing(signal net : inout network_t; vc : my_vc_t; arg : integer) is
    variable msg : msg_t := new_msg(my_vc_do_thing_msg);
  begin
    push(msg, arg);
    send(net, vc.p_actor, msg);   -- non-blocking: returns once queued
  end;
end package body;
```

```vhdl
-- 2. Entity: handle is a generic; one process receives and dispatches
entity my_vc is
  generic (vc : my_vc_t);
  port (some_signal : out std_logic);
end entity;

architecture a of my_vc is
begin
  main : process
    variable msg : msg_t;
    variable msg_type : msg_type_t;
  begin
    receive(net, vc.p_actor, msg);
    msg_type := message_type(msg);
    if msg_type = my_vc_do_thing_msg then
      -- pop(msg) the pushed fields, drive some_signal over time
    else
      unexpected_msg_type(msg_type);   -- or std_cfg-based variant, see below
    end if;
  end process;
end architecture;
```

**Prefer `vc_pkg.create_std_cfg`/`std_cfg_t` over a bare `p_actor`** for
anything beyond a one-off/local VC: it bundles an `id_t` (for
enumerated/discoverable instance naming), a dedicated `logger_t`, a
`checker_t`, and an `unexpected_msg_type_policy_t` (`fail`/`ignore`) in one
opaque record, with `get_id`/`get_actor`/`get_logger`/`get_checker`/
`unexpected_msg_type` accessors and a ready-made `unexpected_msg_type(msg_type,
std_cfg)` procedure to call in the dispatch `else` branch — this is the
pattern the more full-featured built-in VCs (AXI, Avalon, Wishbone) use, and
gives consistent logging/failure reporting for free instead of a bespoke
`report`/`assert`.

**Request/reply (non-blocking-first)**: if a command needs to return data,
prefer the same non-blocking-then-redeem shape already established for
`pop_axi_stream`/`await_pop_axi_stream_reply` (§ above) — send a request
`msg` and immediately return a reference/handle to the caller; provide a
separate blocking `await_<x>_reply` procedure to redeem it only when the
value is actually needed, rather than making every query block the calling
process by default.

**Register with `vc_context`**: built-in VCs are exposed via
`vc_context.vhd` (a single `context` aggregating all VC packages) — do the
equivalent for a set of project-local custom VCs (one `context` declaration
in a shared package) so testbenches pull them in with one `context work.*`
line instead of per-package `use` clauses.

## 13. Good practices (tsfpga + hdl-modules)

1. **Watchdog in every testbench**:
   `test_runner_watchdog(runner, <budget>);` as a **concurrent statement at
   architecture level** (outside the test process, after `end process;`) —
   a sequential call inside the test process blocks the test body and every
   test "fails" with the watchdog timeout. Use a real budget (a few × the
   expected worst-case runtime, e.g. `1 ms` in hdl-modules TBs), never
   `100 s`.
2. **One `run("test_*")` per scenario**; test names describe the
   scenario, not the procedure.
3. **Seeds**: `rnd.InitSeed(get_string_seed(runner_cfg))` once in the
   test process; report the seed in failure messages so the exact
   randomization can be replayed with `--seed`.
4. **Scoreboards over inline compares**: write DUT outputs into a
   `memory_t`, `check_expected_was_written` at cleanup (or use
   `bus2memory`).
5. **Protocol checking in the BFM layer**, not the test body: VUnit's
   `axi_stream_protocol_checker` (or hdl-modules' synthesizable
   `common.axi_stream_protocol_checker`, ~45% faster than the VUnit
   version) on every AXI channel inside the BFM wrapper.
6. **Back-pressure is the default**, not the corner case: random
   `stall_probability` + random response latencies on all slave sides.
7. **Checker processes** (scoreboard/protocol monitors running in their
   own process) must respect the test phases: either lock the
   `test_runner_cleanup` gate until their pending checks are done
   (§7.1) or wait on `runner_phase` events (§7.2). Never finish a
   checker process without checking the final DUT state, and never let
   it race `test_runner_cleanup`.
8. **No-loss / no-bubble by construction**: queue-driven BFM generics
   (`job_queue`, `data_queue`, `reference_data_queue`) — if the queue
   back-pressures, the DUT sees correct handshakes for free.
9. Keep `sim/` models and BFMs simulation-only; the same `run.py`
   compiles RTL for simulation too, so a compile error in a "sim-only"
   file still breaks the run.

## 14. VUnit 4 vs 5 differences

This stack targets **VUnit 5** (`ru551n/vunit` fork 5.0.0.dev12, `--waves`).
When a project is on a stable VUnit 4.x, these are the deltas to check:

| area | VUnit 5 (this stack) | VUnit 4 |
|---|---|---|
| Test runner builtins | `PROJ.add_vhdl_builtins()` **required** | compiled by default |
| Add VHDL files | `add_source_file` / `add_source_files` | `add_vhdl` |
| Test-case attribute | `-- vunit: .name` | `-- vunit_attr -- name: value` (file-global `-- vunit_pragma run_all_in_same_sim` / `fail_on_warning`) |
| Check helpers | `check_equal`/`check_robust`/… only (154 overloads) | also `check_range`, `check_zero`, `check_equal_strict`, `check_bit`, `check_bit_vector`, `check_character`, `check_string`, `check_time`, `check_robust_real`, `check_close`… |
| Array utilities | removed (use `data_types` / manual) | `vunit_lib.array_util` |
| `main()` | `sys.exit` — nothing after it runs | same |
| Waveforms | `--waves` (fork) / `--wave --viewer-fmt` | `--wave` + `--viewer-fmt` |

When migrating a VUnit-4 TB: replace `add_vhdl` with `add_source_file`,
add `add_vhdl_builtins()`, convert `vunit_attr` comments to
`-- vunit: .name`, and re-implement removed `check_*` helpers with
`check_equal`/`check_robust` or plain `assert`.

## 15. Test-driven development (TDD) for RTL modules

Default workflow for a new module (project-wide policy, not just a
suggestion): **write the VUnit testbench from the requirement doc before
the module's RTL body exists**, confirm it is red (fails, or the DUT
doesn't even exist yet so the testbench can't elaborate against real
logic), then implement the RTL until the same testbench goes green. Do not
write the testbench after the implementation "to confirm it works" as the
default order — that verifies the implementation against itself in the
implementer's own mental model, not against the independently-derived
requirement.

Per-module loop:
1. From `<module>_req.md` (ports/generics/protocol above the marker,
   behavior below it), author `tb_<module>.vhd` and register it in
   `run.py` — this is `vhtestgen`'s job, run *before* `vhfill` for that
   module.
2. Compile/run it once against either a `--@`-stub entity or no entity at
   all, and confirm it fails for the *expected* reason (missing
   implementation), not a testbench authoring bug. Record this red result.
3. `vhfill` implements the module until the same, unmodified testbench
   passes (green). Do not relax or rewrite the testbench to make it pass
   unless the requirement doc itself was wrong — if so, fix the req doc
   first, then the testbench, then continue implementing.
4. Move to the next module in pipeline order. Integration-level testing
   (e.g. a full-IP golden-model comparison, see §"Python reference
   models" above) happens after the individual modules it depends on are
   green, as its own later step — it is not a substitute for per-module
   TDD.

This changes the phase order documented in the `vhflow` skill: unit test
generation for a given module precedes that module's implementation, not
the other way around; `vhtestgen` and `vhfill` alternate per module rather
than running as two separate whole-project passes.

Combine with the rest of this document by default for every generated
testbench under this policy:
- prefer built-in VUnit verification components over a hand-rolled
  driver/checker (§12); write a custom VC only when no built-in one fits,
  and verify a candidate wrapper's generic-range assertions against the
  actual interface width before reusing it (see the `bfm.axi_stream_*`
  byte-alignment caveat in §12) — do not discover a mismatched assertion
  only after wiring the whole testbench around it.
- prefer non-blocking VC calls (`push_axi_stream`, `check_axi_stream(...,
  blocking => false)`, non-blocking `pop_axi_stream(..., reference)`) for
  generating stimulus/verification data (§12).
- give every VC instance driving or checking a real `tready`/`tvalid`
  link a non-zero randomized `stall_config` by default, seeded from the
  test's own RNG (§12).
- use a Python reference model via `pre_config`/`post_check` instead of
  hand-computed expected values whenever the module implements a
  specifiable numeric/algorithmic transform (§"Python reference models").
