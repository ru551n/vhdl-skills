---
name: vhfill
description: Use when writing or changing synthesizable VHDL RTL — implementing a module or a `--@` backbone, adding a feature or pipeline stage, fixing an RTL bug whose cause is known, or refactoring an entity or architecture — and checking that it compiles, elaborates and passes its tests. Typical requests include "implement...", "write the VHDL for...", "add a register stage", "fix this in the RTL".
---

# VHDL Implementation

## Before you start

- `shared/` means the `shared/` folder next to this skill's folder (`../shared/`). Those docs are large: run `grep -n '^#' shared/<Doc>.md` and read only the sections the task touches.
- The project's own conventions win. If the repository has a style guide, CLAUDE.md/AGENTS.md rules, or existing modules to copy, follow them over `shared/HouseStyle.md`.
- Flow files are optional. If `ddoc/`, `*_req.md`, `*_proposal.md`, `issue/` or `flow_status.md` exist, use and update them. Otherwise work from the request and the source files, report in the reply, and create flow files only when the user asks or `vhflow` is driving.
- Tools: `vhdl-tools` (`shared/bin/vhdl-tools`) for VUnit, synthesis and waveforms, and `corvidex-mcp` when connected; `shared/ToolPolicy.md` has the commands and fallbacks. Never report a compile, test, synthesis or timing result that no tool produced.

## What to work from

Use whichever exist, in this order: the module's existing testbench (under test-first it is already failing), `ddoc/<module>_proposal.md`, the requirement, the user's request. With no written spec, restate the intended behavior in a short paragraph before editing, and ask when it is ambiguous.

## References by topic

- Before writing VHDL: `shared/HouseStyle.md`, then the sections of `shared/CodingStyle.md` you need.
- Datapaths and timing structure: `shared/TimingAndResources.md` sections 2 (per-command configuration), 5 (freezing a pipeline), 7 (template-sensitive inference); `shared/DesignPatterns.md`
- AXI interfaces: `shared/Axi4.md`; CDC: `shared/CdcPolicy.md`; reset versus initial values: `shared/FpgaInitialization.md`
- AMD/Xilinx inference templates and attributes: the `vivado` skill

## Tools

- `corvidex-mcp`, when connected, for precedent and convention lookup (`search_hdl`/`search_knowledge` for concepts; `find_definition`/`find_references` once the exact symbol is known). Routing in `shared/ToolPolicy.md`.
- `vhdl-tools vunit` for compiling, elaborating and running the module's tests. Run `vhdl-tools vunit elaborate` right after every interface edit, before a full simulation run.
- `vhdl-tools wave` for waveform-based failure analysis when a waveform was recorded.
- `speja`, when the project has a `speja.yaml` or `vsg.yaml` or the user asks for it: `speja --fix` on the files you changed instead of laying them out by hand, then `speja --check style,lint`. `shared/ToolPolicy.md` has the details.

## Inputs

Read the module's VHDL source, then the spec sources listed under "What to work from". Under test-first (`shared/Vunit.md` §16, the default) the module's testbench already exists and fails; treat it as an executable spec next to the proposal, not as something to author here.

## Tool prerequisites and backend selection

Preferred verification backend: `vhdl-tools vunit`, run from the project root.

1. `vhdl-tools vunit status`
2. `vhdl-tools vunit list-files` or `test-dependencies --test-name <test>` as needed
3. `vhdl-tools vunit compile`
4. `vhdl-tools vunit elaborate --test-patterns '<pattern>'` before a full
   run — it catches port, generic and type mismatches between units that
   analyze-only `compile` cannot.
5. `vhdl-tools vunit run-tests --test-patterns '<pattern>'`
6. Add `--waveform-format vcd` (GHDL) or `fst` (NVC) when failure diagnosis may need it; without it, no waveform is recorded.
7. `vhdl-tools vunit get-report` and `get-test-log --test-name <test>`
8. For waveform debugging, `get-test-waveform --test-name <test>`, then `vhdl-tools wave`.

Fallback:
1. existing project VUnit `run.py`
2. GHDL for a simple standalone unit test

If no verification backend is available, implementation may proceed but compile/simulation status is `BLOCKED`.

## Re-run safety

- `--@` markers present → first fill.
- no markers / real logic present → make an incremental change; do not regenerate from scratch.

## Step 1 — Implement

Resolve every `--@` marker using the approved proposal.

**Under the TDD policy (default)**: a red testbench from `vhtest`
already exists for this module. Implement, then compile/simulate (Steps
3-4) iteratively against that existing testbench until it goes green;
do not wait until the whole module is "done" to run it for the first time.
If the red testbench reveals the proposal itself is wrong/incomplete
(missing case, wrong latency, ...), fix the proposal/architecture doc first
and say so in the implementation notes, rather than quietly changing the
RTL to match a flawed spec.

Requirements:
- synthesizable VHDL-2008
- `numeric_std`
- explicit signedness/resizing
- deterministic combinational logic
- documented clock/reset behavior
- no accidental latches
- direct entity instantiation preferred
- no unresolved `--@` markers at completion

Update `## Implementation Notes (vhfill)` in the proposal with meaningful as-built decisions.
True up `doc/<module>.md` if actual latency, reset values, interfaces, or behavior differ from proposal intent.

## Step 2 — Unit testbench

**Under the TDD policy (default, `shared/Vunit.md` §16)**: the unit
testbench for this module was already created by `vhtest` before this
skill ran (red-first). This step is normally a no-op — do not regenerate or
duplicate it. Only add to it here if implementation surfaces a gap
`vhtest` missed (an untested corner case discovered while implementing);
in that case, extend the existing testbench in place rather than writing a
parallel one, and prefer feeding the gap back into `vhtest`'s test plan
for future modules.

The rest of this step (style/registration rules) still applies to any
standalone-GHDL fallback project, or to the rare case where no pre-existing
testbench was found and one must be authored here instead (non-TDD
fallback, e.g. `vhtest` unavailable).

When the project already uses VUnit, the unit testbench must be VUnit — infer the project's existing VUnit style (`run.py` registration, `tb/` layout, check style) from the current tests. If the conventions cannot be inferred, ask the user; do not guess.

VUnit-5 API rules (phases and gate locks, seeded RNG, `check_pkg`, watchdog, `run.py` style) are authoritative in `shared/Vunit.md`; the `vhtest` skill covers direct authoring and VUnit 4→5 migration.

When creating new VUnit tests:
- use VHDL-2008
- use `vunit_lib`
- use `test_runner_setup` / `test_runner_cleanup`
- use VUnit check procedures rather than a custom final verdict protocol
- register the source/test in the project's `run.py`

Only create a standalone `<module>_tb.vhd` with `[FINISH] PASS/FAIL` when VUnit is unavailable, the project explicitly uses standalone GHDL tests, or the user explicitly asks for a standalone testbench.

## Step 3 — Compile and elaborate

### Preferred: `vhdl-tools vunit`

- `vhdl-tools vunit status`
- `vhdl-tools vunit compile`
- `vhdl-tools vunit elaborate --test-patterns '<pattern>'` as soon as
  `compile` succeeds, before Step 4. `compile` only analyzes, so it reports
  success on a port, generic or type mismatch between units that
  elaboration catches. Elaborating costs no simulation time and is the
  fastest way to confirm a just-edited entity's interface binds.

Do not duplicate VUnit's compile-order logic manually.

### Fallback: direct GHDL

Build a dependency filelist according to `shared/HierarchyFilelist.md`, then analyze and elaborate with `ghdl -a --std=08` and `ghdl -e --std=08`.

Never claim success unless the actual backend reports success.

## Step 4 — Simulate

### Preferred: `vhdl-tools vunit`

Run the smallest relevant pattern with `vhdl-tools vunit run-tests --test-patterns '<pattern>' --waveform-format vcd` (or `fst` on NVC), so a failure can be diagnosed at signal level.

Then:
1. `vhdl-tools vunit get-report`
2. on failure, `vhdl-tools vunit get-test-log --test-name <test>`
3. if signal-level diagnosis is needed and a waveform was recorded:
   - `vhdl-tools vunit get-test-waveform --test-name <test>`
   - `vhdl-tools wave open --file <path>` and `search --pattern <name>`
   - `value-at` / `values` / `find` / `latency` as needed

### Fallback

Run the project's `run.py`, or direct GHDL for standalone tests.

Record the backend used in the implementation notes.

## Completion quality gate

Before marking RTL implemented:
- no unresolved `--@`
- laid out by `speja --fix` when the project uses speja, with `speja --check style,lint` clean of errors; otherwise by the Layout part of `shared/HouseStyle.md`
- compile/analyze the complete affected dependency set
- explain or remove meaningful warnings
- no accidental latches/multiple drivers
- arithmetic widths/ranges reviewed
- reset behavior matches the domain contract
- CDC is implemented through an explicit recognized structure
- protocol payload/control stay aligned through pipelines
- unit tests pass through the real verification backend, or status is `BLOCKED`

## Numeric type gate

Before accepting a design or implementation:

1. Confirm `ieee.numeric_std` is used for arithmetic.
2. Reject imports of:
   - `ieee.std_logic_arith`
   - `ieee.std_logic_unsigned`
   - `ieee.std_logic_signed`
3. Review every arithmetic datapath/control value:
   - counters
   - addresses
   - accumulators
   - thresholds
   - lengths/depths
   - arithmetic operands/results
   - numeric state used in `<`, `>`, `<=`, `>=`
4. Prefer the declared type `unsigned`, `signed`, or a constrained integer subtype.
5. Treat `std_logic_vector` as an opaque representation/interface type, not the default arithmetic type.
6. Keep conversions at clear representation boundaries and avoid cast-heavy arithmetic.
7. Make numeric resizing/narrowing explicit and document overflow/truncation behavior.

Flag an implementation for revision when repeated expressions such as:

```vhdl
std_logic_vector(unsigned(x) + 1)
```

appear on an internal state signal that should simply have been declared `unsigned`.

## Static arithmetic hygiene scan

As part of the completion quality gate, inspect affected VHDL for arithmetic hygiene.

At minimum flag:

### Error

Any import matching:

```text
std_logic_arith
std_logic_unsigned
std_logic_signed
```

### Review warning

Internal `std_logic_vector` signals repeatedly cast to `unsigned(...)` or `signed(...)` solely to perform arithmetic.

Examples that deserve review:

```vhdl
count <= std_logic_vector(unsigned(count) + 1);
addr  <= std_logic_vector(unsigned(addr) + stride);
```

Prefer changing the declaration itself:

```vhdl
signal count : unsigned(...);
signal addr  : unsigned(...);
```

Do not flag legitimate representation-boundary conversions such as protocol ports, packed register buses, serialized fields, or vendor interfaces.

Also review:
- implicit narrowing through slicing after arithmetic
- arithmetic result widths that depend on assumptions rather than `resize`
- signed/unsigned comparisons with mismatched semantic domains
- integer conversions that can exceed the destination subtype/range

## FPGA-aware reset quality gate

Before adding a reset branch to a register, classify why it is needed:

- `RUNTIME_RESET_REQUIRED`
- `POWERUP_ONLY`
- `VALUE_IRRELEVANT_UNTIL_VALID`

For `POWERUP_ONLY`, consult `FpgaInitialization.md`.

If target support is `VERIFIED_SUPPORTED`, prefer a declaration initial value
when it improves timing/area/inference and preserves requirements.

If support is `UNKNOWN` or `VERIFIED_UNSUPPORTED`, keep reset or otherwise
provide a target-valid initialization mechanism.

For `VALUE_IRRELEVANT_UNTIL_VALID`, prefer resetting/initializing the validity
or control bit instead of the datapath itself.

Never remove reset solely as an optimization without recording the target
capability evidence.

## Pipeline alignment naming check

Review pipeline naming and alignment:
- `_pN` = N stages after the reference signal
- `_mN` = N stages before the reference signal
- unsuffixed = reference stage 0
- aligned data/control/metadata use the same coordinate

Flag mixed delay naming (`_dN`, `_rr`, `_stageN`, etc.) when `_mN`/`_pN`
coordinates are already the project convention.

## CDC implementation quality gate

A CDC implementation cannot be marked complete unless:
- the crossing class is documented
- a suitable predefined/proven module is used when available
- required constraints/attributes are present when supported
- supplied module constraints have been included where applicable
- reset behavior is valid in both domains
- static CDC/timing checks are clean or explained where available

If no predefined module exists, explicitly report that a custom CDC structure
was required and request/flag extra review.

## Synthesizability gate

For production RTL reject simulation-only constructs, flag tool-dependent
constructs for verification, and verify vendor-specific constructs against the
active toolchain.

## Portability implementation gate

Prefer portable VHDL inference. Do not introduce vendor dependencies silently.
Report the portability class and reason.
