# vhdl-tools

One CLI, `vhdl-tools <group> <command> [options]`, replacing three MCP servers:

| Group | Ported from | Commit |
|---|---|---|
| `vunit` | [ru551n/vunit-mcp](https://github.com/ru551n/vunit-mcp) (`vunit_mcp`) | `ba2a225` |
| `synth` | [ru551n/tsfpga-mcp](https://github.com/ru551n/tsfpga-mcp) (`tsfpga_mcp`) | `04ba5de` |
| `wave` | [ru551n/peeper-mcp](https://github.com/ru551n/peeper-mcp) (`peeper_mcp`) | `d468acf` |

Command = MCP tool name without its prefix, `_` -> `-` (`vunit_run_tests` -> `vunit run-tests`).
Run it through `skills/shared/bin/vhdl-tools`, which calls `uv run --project` on this directory and keeps your working directory.

## Requirements

- [uv](https://docs.astral.sh/uv/). It builds `.venv` here on the first call from `uv.lock`: pydantic, tsfpga (git), pywellen, numpy, matplotlib.
- System tools, as needed: GHDL and/or NVC (vunit), Yosys + ghdl-yosys-plugin + GHDL (synth), Vivado (only the `synth project-get-*-report` commands).
- VUnit comes from the HDL project, not from here. `vunit` commands run the project's own `run.py` with the project's interpreter. That is its `.venv`/`venv`, which is created with uv from `pyproject.toml`/`requirements.txt` if missing, else `python3` on PATH. `synth project-*` does the same with `build.py`/`build_fpga.py`.

## Conventions

- The project dir is the current working directory, unless the env vars below say otherwise.
- All configuration uses the original env vars, unchanged: `VUNIT_MCP_*` (`PROJECT_DIR`, `RUN_SCRIPT`, `PYTHON`, `AUTO_VENV`, `UV`, `VENV_TIMEOUT`, `SIMULATOR`, `OUTPUT_DIR`, `TIMEOUT`, `EXTRA_ARGS`, `FINGERPRINT_EXCLUDE`), `TSFPGA_MCP_*` (`YOSYS`, `GHDL`, `GHDL_PLUGIN`, `GHDL_PREFIX`, `TIMEOUT`, `PROJECT_DIR`, `BUILD_SCRIPT`, `PROJECT_PYTHON`, `PROJECT_AUTO_VENV`, `UV`, `PROJECT_VENV_TIMEOUT`, `PROJECTS_PATH`, `PROJECT_TIMEOUT`, `PROJECT_EXTRA_ARGS`, `VIVADO`), `PEEPER_MCP_*` (`MAX_ROWS`, `MAX_FILES`, `MAX_SEARCH_RESULTS`). See the origin READMEs for what each one does.
- Options:
  - Bools are `--x` / `--no-x`.
  - Lists are `--x A B`, and the flag can be repeated.
  - Dicts are a JSON string.
  - Every command also accepts `--json-input '<whole input as JSON object>'`; explicit options override its keys.
- Output is the tool's text on stdout.
- Exit codes:
  - `0`: success.
  - `1`: the tool reported a failure. For vunit that is `Error: ...`, `Run FAILED.` or `Elaboration FAILED.`. For synth it is `Error: ...`, `Configuration error: ...`, `Timeout: ...`, `Synthesis FAILED`, `Listing failed` or `Build failed`. For wave it is any error message (not found, unknown/ambiguous signal, bad time, empty window).
  - `2`: invalid input.
  - `127`: uv is not installed.
- Serialization:
  - `vunit compile|run-tests|elaborate` hold a lock at `<project>/.vunit-mcp-cache/run.lock`.
  - `synth synthesize` holds a per-user lock at `$TMPDIR/vhdl-tools-synth.lock`.
  - `synth project-build` holds `<projects path>/../.vhdl-tools-build.lock`.
  - A second call waits, and prints one line on stderr while it does.
- The last completed run's output dir is remembered in `<project>/.vunit-mcp-cache/last_output_dir`, so `get-report`/`get-test-log`/`get-test-waveform` follow a `run-tests --output-dir`.

## Command reference

`vhdl-tools <group> <command> --help` prints each option's full description.

### vunit

| Command | Options | Purpose |
|---|---|---|
| `status` | `--simulator S` | Project dir, run script, venv/interpreter, VUnit version, simulators, waveform-flag support |
| `list-tests` | — | All tests (`lib.entity[.test_case]`) via `run.py --list`; no simulator |
| `list-files` | — | Project source files in compile order via `--files`; no simulator |
| `compile` | `--simulator S` | Compile all sources (`--compile`) |
| `run-tests` | `--test-patterns P [P ...]` (default `*`), `--num-threads N`, `--output-dir D`, `--timeout SEC`, `--simulator S`, `--clean/--no-clean`, `--verbose/--no-verbose`, `--fail-fast/--no-fail-fast`, `--with-attributes A [A ...]`, `--without-attributes A [A ...]`, `--waveform-format {vcd,ghw,fst}` | Run tests; pass/fail summary + failing tests; writes JUnit; optional waveforms (vcd on GHDL, fst on NVC) |
| `elaborate` | same as `run-tests` minus `--waveform-format` | Elaborate test benches only (`run.py --elaborate`); pass/fail per test |
| `get-report` | `--only-failing/--no-only-failing`, `--slowest N` | Which tests passed/failed in the last run (re-reads JUnit, no re-run) |
| `get-test-log` | `--test-name NAME` (required), `--lines N` (default 100) | Why one test failed: tail of its `output.txt` + parsed check results |
| `get-test-waveform` | `--test-name NAME` (required), `--waveform-format {vcd,ghw,fst}` | Path/format/size of a test's recorded waveform + failing check time |
| `export-json` | — | Project files, tests, attributes via `--export-json` (cached in `.vunit-mcp-cache`) |
| `test-dependencies` | `--test-name NAME_OR_PATTERN` (required) | Source files needed to elaborate one test, by library, compile order |

### synth

| Command | Options | Purpose |
|---|---|---|
| `synthesize` | `--sources F [F ...]`, `--libraries JSON` (`{"lib": ["f.vhd"]}`), `--top NAME` (required), `--chip {generic,xilinx,intel,microchip}` (default generic), `--family F`, `--vhdl-entities E [E ...]`, `--generics JSON` (`{"WIDTH": "8"}`), `--vhdl-standard {93,08,19}` (default 08), `--discard-ffinit/--no-discard-ffinit`, `--timeout SEC` | Ad-hoc Yosys+GHDL synthesis of the given sources; resource counts or diagnostics (needs `--sources` and/or `--libraries`) |
| `status` | — | yosys version, synthesis flows, ghdl plugin, GHDL prefix, timeout |
| `inspect` | `--sources F [F ...]` (required) | Static scan: VHDL entities/architectures/generics, Verilog modules/parameters |
| `targets` | — | Chip targets, their yosys flow, availability, known families |
| `project-status` | — | Project mode: project dir, build script, interpreter, projects path, timeout, vivado |
| `project-list-builds` | `--netlist-builds/--no-netlist-builds` (default on), `--project-filters P [P ...]` | List the project's build projects (`build script --list-only`) |
| `project-build` | `--project-filters P [P ...]`, `--netlist-builds/--no-netlist-builds` (default on), `--use-existing-project/--no-use-existing-project` (default on), `--num-parallel-builds N`, `--num-threads-per-build N`, `--synth-only/--no-synth-only`, `--from-impl/--no-from-impl`, `--timeout SEC` | Run the project's own build script (netlist builds by default; Vivado with `--no-netlist-builds`) |
| `project-get-timing-report` | `--project NAME` (required), `--run-index N` (default 1), `--synth-only/--no-synth-only`, `--report-type {summary,pulse_width,bus_skew,clock_interaction}` (default summary), `--verbosity {full,summary}` (default full), `--force-regenerate/--no-force-regenerate`, `--timeout SEC` | Vivado timing report for a built run (cached or regenerated) |
| `project-get-utilization-report` | `--project NAME` (required), `--run-index N` (default 1), `--synth-only/--no-synth-only`, `--hierarchical-depth N` (default 4), `--force-regenerate/--no-force-regenerate`, `--timeout SEC` | Hierarchical Vivado utilization report for a built run |
| `project-get-drc-report` | `--project NAME` (required), `--run-index N` (default 1), `--synth-only/--no-synth-only`, `--report-type {drc,methodology}` (default drc), `--force-regenerate/--no-force-regenerate`, `--timeout SEC` | Vivado DRC or methodology report for a built run |

### wave

Times are `10ns` / `1.5us` or integer file ticks. Signals are full names or unique suffixes, matched case-insensitively.

| Command | Options | Purpose |
|---|---|---|
| `open` | `--file F` (required) | Format, writer, timescale, duration, scopes, signal count |
| `search` | `--file F` (required), `--pattern S`, `--limit N` (default 100) | List signals (substring filter) |
| `values` | `--file F` (required), `--signal S` (required), `--start T` (default 0), `--end T`, `--max-changes N` (default 1000) | Change list of one signal in `[start, end)` |
| `value-at` | `--file F` (required), `--time T` (required), `--signals S [S ...]` (required) | Values of several signals at one time |
| `sample` | `--file F` (required), `--clock C` (required), `--signals S [S ...]` (required), `--start T` (default 0), `--end T`, `--max-rows N` (default 100) | One row per rising edge of C: each signal's value just before the edge, as a register samples it |
| `analyze` | `--file F` (required), `--signal S` (required), `--start T` (default 0), `--end T` | Period/frequency/duty, pulse widths, X/Z time, min/max/mean, value distribution |
| `latency` | `--file F` (required), `--a S` (required), `--b S` (required), `--edge {rise,any}` (default rise), `--start T` (default 0), `--end T` | Edge-to-edge delay A -> B: min/max/mean/p50/stddev. A and B the same signal: the interval between its edges |
| `find` | `--file F` (required), `--signal S` (required), `--value V` (required), `--start T` (default 0), `--limit N` (default 100) | Intervals where a signal holds a value |
| `plot` | `--file F` (required), `--signals S [S ...]` (required), `--start T` (default 0), `--end T`, `--out PNG` (default: new temp file), `--mark T [T ...]`, `--clock C` | Write a PNG plot: numeric lanes as steps labelled with their values and range, flat lanes with their level, X/U/Z in red, a dashed line at each mark, dots at C's rising edges on the sampled values, no-data region shaded; prints its path (`image:` line) + per-trace summary |

## Development

```sh
uv run --project skills/shared/tools pytest     # perf gates: add -m perf
```
