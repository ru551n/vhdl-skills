---
name: vhfill
description: Implement VHDL-2008 from an approved proposal, then analyze, elaborate, and simulate with GHDL
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.
> **Layout note:** `ddoc/`, `rtl/`, `doc/`, `lib/` are the conventional tsfpga layout. When the project uses a different layout (e.g. `modules/<name>/{src,test,doc}`), follow the project's layout and keep the same file-naming conventions (`<ip>_arch.md`, `<module>_req.md`, `<module>.md`, `<module>.vhd`).


# VHDL Writer

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## MCP preference

- Use `vhdl-rag-mcp` for precedent/convention lookup when implementation details need grounding.
- Use `vunit-mcp` for compile and unit-test execution when a VUnit project exists.
- Use `peeper-mcp` for waveform-based failure analysis when a recorded waveform is available.

## Inputs

Read:
1. `rtl/<module>.vhd`
2. `ddoc/<module>_proposal.md`
3. `shared/CodingStyle.md`
4. `shared/DesignPatterns.md`
5. `shared/Axi4.md` when the module exposes an AXI4/AXI4-Stream interface
6. **Under the TDD policy (`shared/Vunit.md` §15, default)**: the module's
   testbench already exists and is currently failing/red — it was written
   by `vhtestgen` *before* this skill ran. Read it before implementing;
   treat it as an executable spec alongside the proposal, not as something
   this skill still needs to author from scratch.

## Tool prerequisites and backend selection

Preferred verification backend: `vunit-mcp`.

If `vunit-mcp` tools are exposed:
1. Call `vunit_status`.
2. Use `vunit_list_files` / `vunit_test_dependencies` as appropriate.
3. Compile with `vunit_compile`.
4. Run the relevant unit test with `vunit_run_tests`.
5. Pass `waveform_format` (`vcd` on GHDL, `fst` on NVC) to `vunit_run_tests` when failure diagnosis may need it; without it, no waveform is recorded.
6. Read results with `vunit_get_report` and `vunit_get_test_log`.
7. On waveform-debug, resolve it with `vunit_get_test_waveform` and analyze via `peeper-mcp`.

Fallback:
1. existing project VUnit `run.py`
2. GHDL for a simple standalone unit test

If no verification backend is available, implementation may proceed but compile/simulation status is `BLOCKED`.

## Re-run safety

- `--@` markers present → first fill.
- no markers / real logic present → make an incremental change; do not regenerate from scratch.

## Step 1 — Implement

Resolve every `--@` marker using the approved proposal.

**Under the TDD policy (default)**: a red testbench from `vhtestgen`
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

**Under the TDD policy (default, `shared/Vunit.md` §15)**: the unit
testbench for this module was already created by `vhtestgen` before this
skill ran (red-first). This step is normally a no-op — do not regenerate or
duplicate it. Only add to it here if implementation surfaces a gap
`vhtestgen` missed (an untested corner case discovered while implementing);
in that case, extend the existing testbench in place rather than writing a
parallel one, and prefer feeding the gap back into `vhtestgen`'s test plan
for future modules.

The rest of this step (style/registration rules) still applies to any
standalone-GHDL fallback project, or to the rare case where no pre-existing
testbench was found and one must be authored here instead (non-TDD
fallback, e.g. `vhtestgen` unavailable).

When the project already uses VUnit, the unit testbench must be VUnit — infer the project's existing VUnit style (`run.py` registration, `tb/` layout, check style) from the current tests. If the conventions cannot be inferred, ask the user; do not guess.

VUnit-5 API rules (phases and gate locks, seeded RNG, `check_pkg`, watchdog, `run.py` style) are authoritative in `shared/Vunit.md`; the `vhunit` skill covers direct authoring and VUnit 4→5 migration.

When creating new VUnit tests:
- use VHDL-2008
- use `vunit_lib`
- use `test_runner_setup` / `test_runner_cleanup`
- use VUnit check procedures rather than a custom final verdict protocol
- register the source/test in the project's `run.py`

Only create a standalone `<module>_tb.vhd` with `[FINISH] PASS/FAIL` when VUnit is unavailable, the project explicitly uses standalone GHDL tests, or the user explicitly asks for a standalone testbench.

## Step 3 — Compile

### Preferred: vunit-mcp

- `vunit_status`
- `vunit_compile`

Do not duplicate VUnit's compile-order logic manually.

### Fallback: direct GHDL

Build a dependency filelist according to `shared/HierarchyFilelist.md`, then analyze/elaborate with `ghdl --std=08`.

Never claim success unless the actual backend reports success.

## Step 4 — Simulate

### Preferred: vunit-mcp

Run the smallest relevant test pattern with `vunit_run_tests`, passing `waveform_format` (`vcd` on GHDL, `fst` on NVC) so a failure can be diagnosed at signal level.

Then:
1. `vunit_get_report`
2. on failure, `vunit_get_test_log`
3. if signal-level diagnosis is needed and waveform was recorded:
   - `vunit_get_test_waveform`
   - `peeper_open`
   - `peeper_search`
   - `peeper_value_at` / `peeper_values` / `peeper_find` / `peeper_latency` as needed

### Fallback

Run the project's `run.py`, or direct GHDL for standalone tests.

Record the backend used in the implementation notes.


## Completion quality gate

Before marking RTL implemented:
- no unresolved `--@`
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
